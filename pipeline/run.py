"""Send the requests of a run and collect the replies (PLAN 5.2 to 5.7 and 10).

    python3 -I pipeline/run.py COMMAND --run RUN [--stub] [options]

Commands
    prepare  write the request file of one round: round 1 from the item files, round 2 also from the turn-1
             results (PLAN 4.3: a chain whose turn 1 did not parse ends there and is logged as not sent)
    send     send the prepared requests that have no result yet: batches first (Anthropic, OpenRouter batch
             route), then sync requests (OpenRouter sync, Hugging Face). Needs --yes, and --spend-cap without --stub
    collect  fetch the results of open batches (--wait keeps polling once a minute)
    status   counts from the files, with no network
    cancel   cancel an open Anthropic batch
    batches  list the provider's recent batches and the submission each belongs to
    adopt    tie a batch to a submission whose create request ended without a reply
    release  give up a submission, so that its requests can be sent again
    summary  statistics per setting, written to summary.json

Paid steps: send (without --stub or --dry-run) and the results it produces. collect, cancel and batches read the
provider with the key but cost nothing. prepare, status, summary, a dry run and every --stub command touch no
network and need no key. A stub run writes to data/runs/{run}-stub and never mixes with a real run.

Exit codes: 0 done, 1 error, 2 send without --yes, 3 worst case over --spend-cap, 4 stopped after a batch create
failed (the message says what to run next)."""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import datetime as dt
import json
import math
import os
import sys
import threading
import time
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from pipeline import build, clients, config, keys, parse, pricing, prompts, settings  # noqa: E402
from pipeline.clients import anthropic_client, openrouter_client  # noqa: E402
from pipeline.clients.common import RETRYABLE, ClientError, SubmitUncertain  # noqa: E402
from pipeline.util import (UTC, append_jsonl, append_jsonl_many, jsonl_text, now_utc, read_json,  # noqa: E402
                           read_jsonl, sha256_file, sha256_text, write_json, write_jsonl)

SLEEP = time.sleep          # the tests replace it
POLL_S = 60                 # seconds between batch polls
POLL_429_S = 120            # after HTTP 429 or 503 on a poll
SYNC_RETRIES = 5            # HTTP 429 and 503 only; a timeout is never sent again
CHUNK = {"anthropic": 10_000, "openrouter": 1_000}
LOCK_STALE_S = 10
BASE_FIELDS = ("run", "setting", "custom_id", "item_id", "set", "chain", "part", "kind", "arm", "fields",
               "stubborn", "round", "max_tokens")

OK, ERROR, NO_YES, OVER_CAP, SUBMIT_STOPPED = 0, 1, 2, 3, 4


class RunError(RuntimeError):
    pass


# ----------------------------------------------------------------------------------------------- paths and logs

def run_dir(run: str, stub: bool) -> Path:
    return config.RUNS / (f"{run}-stub" if stub else run)


def rel(rdir: Path, path: Path) -> str:
    return str(Path(path).relative_to(rdir))


def requests_path(rdir, name, rnd):
    return rdir / "requests" / f"{name}-r{rnd}.jsonl"


def not_sent_path(rdir, name):
    return rdir / "requests" / f"{name}-r2-not_sent.jsonl"


def results_path(rdir, name):
    return rdir / "results" / f"{name}.jsonl"


def stamp() -> str:
    return dt.datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")


def now_ms() -> str:
    return dt.datetime.now(UTC).isoformat(timespec="milliseconds")


def iso_time(x):
    """A provider time as ISO: unix seconds (or milliseconds) are converted, strings pass through."""
    if x is None:
        return None
    if isinstance(x, (int, float)) and not isinstance(x, bool):
        return dt.datetime.fromtimestamp(x / 1000 if x > 1e12 else x, UTC).isoformat(timespec="seconds")
    return str(x)


def log_event(rdir: Path, event: str, **fields) -> None:
    append_jsonl(rdir / "manifest.jsonl", {"time": now_utc(), "event": event, **fields})


class Lock:
    """One command at a time per run folder. A lock whose process has gone, or an empty lock file older than
    ten seconds, is stale and removed once."""

    def __init__(self, rdir: Path):
        self.path = rdir / ".lock"

    def _pid(self):
        try:
            return int(self.path.read_text().strip())
        except (OSError, ValueError):
            return None

    def _stale(self, pid) -> bool:
        if pid is None:
            try:
                return time.time() - self.path.stat().st_mtime > LOCK_STALE_S
            except OSError:
                return True
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return True
        except PermissionError:
            return False
        except (OverflowError, OSError):
            return True
        return False

    def __enter__(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        for attempt in (1, 2):
            try:
                fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
            except FileExistsError:
                pid = self._pid()
                if attempt == 1 and self._stale(pid):
                    self.path.unlink(missing_ok=True)
                    continue
                raise RunError(f"{self.path} is held by process {pid if pid is not None else '(unknown)'}; wait "
                               "for that command to finish, or delete the file if no command is running") from None
            with os.fdopen(fd, "w") as f:
                f.write(str(os.getpid()))
            return self
        raise RunError(f"could not take {self.path}")

    def __exit__(self, *exc):
        self.path.unlink(missing_ok=True)
        return False


# ------------------------------------------------------------------------------------------ submissions and results

def submissions(rdir: Path) -> dict:
    """The batch submissions of a run folder, replayed from the manifest: {local_id: submitting event plus state,
    batch_id and cancel_requested}. state is uncertain (create sent, outcome unknown), open, failed (create
    refused), released or closed."""
    subs = {}
    for ev in read_jsonl(rdir / "manifest.jsonl"):
        lid, kind = ev.get("local_id"), ev.get("event")
        if kind == "submitting":
            subs[lid] = {**ev, "state": "uncertain", "batch_id": None, "cancel_requested": False, "status": None}
        elif lid not in subs:
            continue
        elif kind in ("submitted", "adopted"):
            subs[lid].update(state="open", batch_id=ev.get("batch_id"))
        elif kind == "submit_failed":
            subs[lid]["state"] = "failed" if ev.get("certain") else "uncertain"
        elif kind == "released":
            subs[lid]["state"] = "released"
        elif kind == "closed":
            subs[lid].update(state="closed", status=ev.get("status"))
        elif kind == "cancel_requested":
            subs[lid]["cancel_requested"] = True
    return subs


def sub_ids(rdir: Path, sub: dict) -> list[str]:
    path = rdir / sub["ids_file"]
    return read_json(path) if path.exists() else []


def in_flight(rdir: Path, subs: dict) -> set:
    out = set()
    for s in subs.values():
        if s["state"] in ("open", "uncertain"):
            out.update(sub_ids(rdir, s))
    return out


def winners(records) -> tuple[dict, set]:
    """The first record that is not an error for each custom_id, and the custom_ids that have only errors."""
    win, errs = {}, set()
    for r in records:
        cid = r.get("custom_id")
        if cid is None or cid in win:
            continue
        if r.get("status") == "error":
            errs.add(cid)
        else:
            win[cid] = r
            errs.discard(cid)
    return win, errs


def save_batch(rdir: Path, batch: dict) -> Path:
    path = rdir / "batches" / f"{batch['id']}.json.gz"
    write_json(path, {k: v for k, v in batch.items() if k != "results"}, gz=True)
    return path


def unique(path: Path) -> Path:
    if not path.exists():
        return path
    n = 2
    while True:
        p = path.with_name(f"{path.stem}-{n}{path.suffix}")
        if not p.exists():
            return p
        n += 1


# ------------------------------------------------------------------------------------------------- settings

def run_settings(run: str) -> list[str]:
    return list(build.run_spec(run)["settings"])


def chosen(a) -> list[str]:
    known = run_settings(a.run)
    names = a.setting or known
    bad = [n for n in names if n not in known]
    if bad:
        raise RunError(f"the {a.run} run has no setting {', '.join(bad)}; it has {', '.join(known)}")
    return [n for n in known if n in names]


def has_round2(run: str, name: str) -> bool:
    return any(build.run_spec(run)["settings"][name]["chains"].values())


def resolve_route(run: str, name: str, override: str | None) -> str:
    try:
        rte = override or build.route(run, name)
    except (ValueError, KeyError) as e:
        raise RunError(str(e)) from None
    st = settings.setting(name)
    if st["api"] == "anthropic" and rte != "batch":
        raise RunError(f"{name}: every Anthropic request goes through Message Batches (PLAN 5.2); leave out --route "
                       "or name the OpenRouter and HF settings with --setting")
    if st["api"] == "hf" and rte != "sync":
        raise RunError("HF has no batch route (PLAN 5.4)")
    if st["api"] == "openrouter" and rte == "batch" and not st.get("batch_provider"):
        raise RunError(f"no OpenRouter batch provider serves {st['model']}; {name} goes by --route sync")
    return rte


def load_items(run: str) -> dict:
    try:
        return build.load_run_items(run)
    except (KeyError, ValueError) as e:
        raise RunError(f"the item files of the {run} run do not load: {e}") from None


# ------------------------------------------------------------------------------------------------------ costs

def _text_len(rec: dict) -> int:
    return len(rec.get("system") or "") + sum(len(m.get("content") or "") for m in rec.get("messages") or [])


def worst_usd(rec: dict, price: dict) -> float:
    """Input tokens taken as one per three characters (more than any English text needs) and the full output
    cap."""
    return (math.ceil(_text_len(rec) / 3) * price["price_in"] + rec["max_tokens"] * price["price_out"]) / 1e6


def expected_usd(rec: dict, price: dict) -> float:
    out = pricing.expected_out(rec["setting"], rec["kind"])
    return (math.ceil(_text_len(rec) / 4) * price["price_in"] + out * price["price_out"]) / 1e6


def cost_of(reply: dict, price: dict | None):
    n_in, n_out = reply.get("input_tokens"), reply.get("output_tokens")
    if price is None or not isinstance(n_in, (int, float)) or not isinstance(n_out, (int, float)):
        return None
    return round((n_in * price["price_in"] + n_out * price["price_out"]) / 1e6, 10)


# ------------------------------------------------------------------------------------------------ result records

def base_of(rec: dict) -> dict:
    return {k: rec.get(k) for k in BASE_FIELDS}


def result_record(rec: dict, ctx: dict, reply: dict | None = None, error: dict | None = None) -> dict:
    """One line of results/{setting}.jsonl (PLAN 5.7)."""
    st = settings.setting(rec["setting"])
    out = base_of(rec)
    out.update(request_time=ctx.get("request_time"), response_time=ctx.get("response_time"), model=st["model"],
               api=st["api"], route=ctx["route"], provider_requested=ctx.get("provider_requested"),
               batch_id=ctx.get("batch_id"), api_version=ctx.get("api_version"),
               sdk_version=ctx.get("sdk_version"), price_file=ctx.get("price_file"),
               price_in=(ctx.get("price") or {}).get("price_in"),
               price_out=(ctx.get("price") or {}).get("price_out"), stub=ctx.get("stub", False))
    if error is not None:
        out.update(status="error", reason=error.get("message"), error=error, parsed=None, core_ok=False,
                   cost_usd=None)
        return out
    out.update(reply)
    out["stop_kind"] = parse.stop_kind(st["api"], reply.get("stop_reason"))
    out.update(parse.parse_reply(reply.get("text") or "", rec["kind"], stop=out["stop_kind"]))
    out["cost_usd"] = cost_of(reply, ctx.get("price"))
    return out


def fallback_request(run: str, cid: str, sub: dict) -> dict:
    """The base fields of a request that is no longer in its request file (prepare --replace ran after the send)."""
    info = build.parse_custom_id(cid)
    st = settings.setting(info["setting"])
    return {"run": run, "custom_id": cid, "set": None, "stubborn": bool(st.get("stubborn")),
            "round": sub.get("round"), "max_tokens": sub.get("max_tokens"), **info}


# ------------------------------------------------------------------------------------------------------ prepare

def cmd_prepare(a) -> int:
    rdir = run_dir(a.run, a.stub)
    names = chosen(a)
    with Lock(rdir):
        items = load_items(a.run)
        items_sha = {s: sha256_file(config.ITEMS / f"{s}_items.json") for s in build.run_spec(a.run)["sets"]}
        source = build.turn1_source(a.run)
        if a.round == 1 and source != a.run:
            raise RunError(f"the {a.run} run reuses the turn-1 replies of the {source} run and has no round 1; "
                           "prepare round 2 only")
        sdir = run_dir(source, a.stub)
        tmpl = prompts.template_hashes()["ALL"]
        set_sha = sha256_text(json.dumps(settings.SETTINGS, sort_keys=True, ensure_ascii=False))
        for name in names:
            not_sent = None
            try:
                if a.round == 1:
                    recs = build.round1(a.run, name, items)
                else:
                    if not has_round2(a.run, name):
                        print(f"{name}: no round 2 in the {a.run} run; skipped")
                        continue
                    win, _ = winners(read_jsonl(results_path(sdir, name)))
                    t1 = {cid: r for cid, r in win.items() if r.get("kind") == "t1"}
                    expected = build.turn1_ids(a.run, name, items)
                    missing = [cid for cid in expected if cid not in t1]
                    if missing and not a.allow_missing:
                        raise RunError(
                            f"{name}: {len(missing)} of {len(expected)} turn-1 requests have no result in the "
                            f"{source} run (first {missing[0]}); collect them, send again with --retry-failed, or "
                            "add --allow-missing to end those chains at turn 1")
                    recs, not_sent = build.round2(a.run, name, items, t1)
            except (ValueError, KeyError) as e:
                raise RunError(f"{name}: {e}") from None
            req_file, ns_file = requests_path(rdir, name, a.round), not_sent_path(rdir, name)
            new = {req_file: recs}
            if not_sent is not None:
                new[ns_file] = not_sent
            old = {p: (p.read_text(encoding="utf-8") if p.exists() else None) for p in new}
            if all(old[p] == jsonl_text(v) for p, v in new.items()):
                print(f"{name}: round {a.round} already prepared and unchanged ({len(recs)} requests)")
                continue
            changed = [p for p, v in new.items() if old[p] is not None and old[p] != jsonl_text(v)]
            if changed:
                if not a.replace:
                    raise RunError(f"{name}: {rel(rdir, changed[0])} exists with other content; add --replace to "
                                   "write the new one (the old one is kept as a backup)")
                for p in changed:
                    os.replace(p, unique(p.with_name(f"{p.name}.replaced-{stamp()}")))
                if results_path(rdir, name).exists():
                    print(f"warning: {name} has results already; requests that have a result are not sent again",
                          file=sys.stderr)
            for p, v in new.items():
                write_jsonl(p, v)
            log_event(rdir, "prepared", setting=name, round=a.round, file=rel(rdir, req_file),
                      sha256=sha256_file(req_file), n=len(recs),
                      not_sent=None if not_sent is None else len(not_sent), items_sha256=items_sha,
                      template_hashes_all=tmpl, settings_sha256=set_sha, replaced=bool(changed))
            extra = "" if not_sent is None else f", {len(not_sent)} not sent (turn 1 did not parse)"
            print(f"{name}: round {a.round} prepared, {len(recs)} requests{extra}")
    return OK


# --------------------------------------------------------------------------------------------------------- send

def plan_setting(a, rdir, name, flight, offline) -> dict | None:
    if a.round == 2 and not has_round2(a.run, name):
        print(f"{name}: no round 2 in the {a.run} run; skipped")
        return None
    path = requests_path(rdir, name, a.round)
    if not path.exists():
        raise RunError(f"{path} does not exist; run prepare --round {a.round} first")
    rte = resolve_route(a.run, name, a.route)
    recs = read_jsonl(path)
    win, errs = winners(read_jsonl(results_path(rdir, name)))
    to_send = [r for r in recs if r["custom_id"] not in win
               and (a.retry_failed or r["custom_id"] not in errs)
               and (a.include_in_flight or r["custom_id"] not in flight)]
    if a.limit is not None:
        to_send = to_send[:a.limit]
    price = pricing.price_record(name, rte, offline=offline)
    return {"name": name, "st": settings.setting(name), "route": rte, "recs": recs, "to_send": to_send,
            "done": sum(r["custom_id"] in win for r in recs),
            "in_flight": sum(r["custom_id"] in flight and r["custom_id"] not in win for r in recs),
            "failed": sum(r["custom_id"] in errs for r in recs), "price": price,
            "worst": sum(worst_usd(r, price) for r in to_send),
            "expected": sum(expected_usd(r, price) for r in to_send)}


def print_plan(plans: list[dict]) -> None:
    head = f"{'setting':<18}{'route':<7}{'to send':>8}{'done':>7}{'in flight':>10}{'failed':>8}" \
           f"{'worst US$':>11}{'expected US$':>14}  prices"
    print(head)
    for p in plans:
        print(f"{p['name']:<18}{p['route']:<7}{len(p['to_send']):>8}{p['done']:>7}{p['in_flight']:>10}"
              f"{p['failed']:>8}{p['worst']:>11.4f}{p['expected']:>14.4f}  {p['price']['source']}")
    print(f"{'total':<25}{sum(len(p['to_send']) for p in plans):>8}{'':>25}"
          f"{sum(p['worst'] for p in plans):>11.4f}{sum(p['expected'] for p in plans):>14.4f}")


def batch_body(api: str, chunk: list[dict], st: dict):
    return clients.ops(api).batch_payload(chunk, st)


def sync_body(api: str, rec: dict, st: dict) -> dict:
    return clients.ops(api).sync_body(rec, st)


def chunks(seq: list, size: int):
    for i in range(0, len(seq), size):
        yield seq[i:i + size]


def dry_run(a, rdir, plans) -> int:
    for p in plans:
        if not p["to_send"]:
            continue
        api, st = p["st"]["api"], p["st"]
        path = rdir / "dryrun" / f"{p['name']}-r{a.round}-{p['route']}.jsonl"
        if p["route"] == "batch":
            lines = []
            for k, chunk in enumerate(chunks(p["to_send"], a.batch_size or CHUNK[api]), 1):
                payload = batch_body(api, chunk, st)
                lines.append({"chunk": k, "payload": {"requests": payload} if isinstance(payload, list) else payload})
        else:
            lines = [{"custom_id": r["custom_id"], "body": sync_body(api, r, st)} for r in p["to_send"]]
        write_jsonl(path, lines)
        print(f"{p['name']}: dry run, {len(p['to_send'])} request bodies written to {rel(rdir, path)}")
    print("dry run: nothing was sent")
    return OK


def save_price(rdir: Path, p: dict) -> str:
    path = unique(rdir / "prices" / f"{p['name']}-{p['route']}-{stamp()}.json")
    write_json(path, p["price"])
    return rel(rdir, path)


def submit_batches(a, rdir, plan, client, subs) -> int:
    name, st, api = plan["name"], plan["st"], plan["st"]["api"]
    price_file = save_price(rdir, plan)
    st_stamp = stamp()
    for k, chunk in enumerate(chunks(plan["to_send"], a.batch_size or CHUNK[api]), 1):
        base = f"{name}-r{a.round}-{st_stamp}-{k}"
        lid, n = base, 2
        while lid in subs or (rdir / "batches" / f"{lid}.ids.json").exists():
            lid, n = f"{base}-{n}", n + 1
        ids = [r["custom_id"] for r in chunk]
        ids_file = rdir / "batches" / f"{lid}.ids.json"
        write_json(ids_file, ids)
        payload = batch_body(api, chunk, st)
        ev = {"local_id": lid, "api": api, "route": "batch", "setting": name, "round": a.round, "n": len(chunk),
              "max_tokens": st["max_tokens"], "worst_case_usd": round(sum(worst_usd(r, plan["price"]) for r in chunk), 6),
              "price_file": price_file, "stub": a.stub, "ids_file": rel(rdir, ids_file),
              "provider_requested": pricing.provider_requested(name, "batch")}
        if api == "anthropic":
            ev.update(api_version=client.api_version(), sdk_version=client.sdk_version())
        log_event(rdir, "submitting", **ev)
        subs[lid] = {**ev, "state": "uncertain"}
        try:
            batch = client.submit(payload)
        except SubmitUncertain as e:
            log_event(rdir, "submit_failed", local_id=lid, certain=False, error=e.to_dict())
            stub = " --stub" if a.stub else ""
            print(f"error: the create request of batch {lid} ({len(chunk)} requests) ended without a reply "
                  f"({e.message}); a batch may or may not exist. Its requests count as in flight until you run\n"
                  f"  python3 -I pipeline/run.py batches --run {a.run} --api {api}{stub}\n"
                  f"then, if a batch of {len(chunk)} requests is tied to no submission,\n"
                  f"  python3 -I pipeline/run.py adopt --run {a.run} --local-id {lid} --batch-id BATCH_ID{stub}\n"
                  f"or, if none is,\n"
                  f"  python3 -I pipeline/run.py release --run {a.run} --local-id {lid}{stub}\n"
                  "and send again.", file=sys.stderr)
            return SUBMIT_STOPPED
        except ClientError as e:
            log_event(rdir, "submit_failed", local_id=lid, certain=True, error=e.to_dict())
            print(f"error: the provider refused batch {lid} ({e.message}); no batch was made and nothing more was "
                  "sent. Its requests can be sent again.", file=sys.stderr)
            return SUBMIT_STOPPED
        log_event(rdir, "submitted", local_id=lid, batch_id=batch["id"])
        subs[lid].update(state="open", batch_id=batch["id"])
        save_batch(rdir, batch)
        print(f"{name}: batch {batch['id']} sent ({len(chunk)} requests, local ID {lid})")
    return OK


class Budget:
    """The spend cap of the sync requests: each request reserves its worst case before it goes, and the actual
    cost replaces the reservation when the reply comes."""

    def __init__(self, cap: float):
        self.cap, self.spent, self.reserved = cap, 0.0, 0.0
        self.lock = threading.Lock()

    def reserve(self, amount: float) -> bool:
        with self.lock:
            if self.spent + self.reserved + amount > self.cap + 1e-12:
                return False
            self.reserved += amount
            return True

    def settle(self, reserved: float, actual: float) -> None:
        with self.lock:
            self.reserved -= reserved
            self.spent += actual


def send_one(a, rdir, plan, rec, client, budget, write_lock, stop, counts, price_file) -> None:
    if stop.is_set():
        return
    name, st, api = plan["name"], plan["st"], plan["st"]["api"]
    worst = worst_usd(rec, plan["price"])
    if not budget.reserve(worst):
        with write_lock:
            counts["stopped_by_cap"] += 1
        return
    ctx = {"route": "sync", "provider_requested": pricing.provider_requested(name, "sync"),
           "price": plan["price"], "price_file": price_file, "stub": a.stub, "request_time": now_ms()}
    body = sync_body(api, rec, st)
    data = headers = error = None
    for attempt in range(SYNC_RETRIES + 1):
        try:
            data, headers = client.send_sync(body, cid=rec["custom_id"])
            break
        except ClientError as e:
            if e.kind == "http" and e.status in RETRYABLE and attempt < SYNC_RETRIES and not stop.is_set():
                SLEEP(min(e.retry_after, 60) if e.retry_after else 2 ** (attempt + 1))
                continue
            error = e.to_dict()
            break
    ctx["response_time"] = now_ms()
    raw = None
    if error is None:
        try:
            reply = clients.ops(api).extract(data, headers)
            out = result_record(rec, ctx, reply=reply)
        except Exception as e:  # noqa: BLE001  (a reply the extraction cannot read is kept as an error record)
            out = result_record(rec, ctx, error={"type": "extract", "status": None,
                                                 "message": f"{type(e).__name__}: {e}"[:500], "body": None,
                                                 "retryable": False})
        raw = {"custom_id": rec["custom_id"], "time": ctx["response_time"], "headers": headers, "body": data}
    else:
        out = result_record(rec, ctx, error=error)
    actual = out.get("reported_cost")
    if not isinstance(actual, (int, float)):
        actual = out.get("cost_usd")
    refused = (error is not None and error.get("type") == "http" and isinstance(error.get("status"), int)
               and 400 <= error["status"] < 500)   # a 4xx refusal is not billed; any other failure may be
    budget.settle(worst, actual if isinstance(actual, (int, float)) else (0.0 if refused else worst))
    with write_lock:
        append_jsonl(results_path(rdir, name), out)
        if raw is not None:
            append_jsonl(rdir / "raw" / f"{name}-sync.jsonl", raw)
        key = "n_error" if out["status"] == "error" else "n_ok"
        counts[key] += 1
        counts["cost"] += actual if isinstance(actual, (int, float)) else 0.0
        done = counts["n_ok"] + counts["n_error"]
        if done % 50 == 0 or done == len(plan["to_send"]):
            print(f"{name}: {done}/{len(plan['to_send'])} replies")


def send_sync_all(a, rdir, plans, client_of, cap) -> int:
    budget, write_lock, stop = Budget(cap), threading.Lock(), threading.Event()
    executors, futures, counts = [], [], {}
    for p in plans:
        price_file = save_price(rdir, p)
        c = counts[p["name"]] = Counter({"n_ok": 0, "n_error": 0, "stopped_by_cap": 0, "cost": 0.0})
        log_event(rdir, "sync_started", setting=p["name"], round=a.round, n=len(p["to_send"]), workers=a.workers,
                  price_file=price_file, provider_requested=pricing.provider_requested(p["name"], "sync"),
                  stub=a.stub)
        ex = cf.ThreadPoolExecutor(max_workers=a.workers, thread_name_prefix=p["name"])
        executors.append(ex)
        client = client_of(p["st"]["api"])
        futures += [ex.submit(send_one, a, rdir, p, r, client, budget, write_lock, stop, c, price_file)
                    for r in p["to_send"]]
    try:
        for f in cf.as_completed(futures):
            f.result()
    except KeyboardInterrupt:
        stop.set()
        for ex in executors:
            ex.shutdown(wait=False, cancel_futures=True)
        log_event(rdir, "interrupted", round=a.round, settings=[p["name"] for p in plans])
        print("interrupted: the requests already sent finish and are written; send again to go on",
              file=sys.stderr)
        try:
            cf.wait([f for f in futures if not f.cancelled()])
        except KeyboardInterrupt:
            pass
        return ERROR
    finally:
        for ex in executors:
            ex.shutdown(wait=True)
    for p in plans:
        c = counts[p["name"]]
        log_event(rdir, "sync_finished", setting=p["name"], round=a.round, n_ok=c["n_ok"], n_error=c["n_error"],
                  stopped_by_cap=c["stopped_by_cap"], cost=round(c["cost"], 6))
        stopped = f", {c['stopped_by_cap']} not sent (spend cap)" if c["stopped_by_cap"] else ""
        print(f"{p['name']}: {c['n_ok']} replies, {c['n_error']} errors{stopped}, cost US${c['cost']:.4f}")
    return OK


def cmd_send(a) -> int:
    rdir = run_dir(a.run, a.stub)
    names = chosen(a)
    if a.yes and not a.stub and not a.dry_run and a.spend_cap is None:
        raise RunError("a paid send needs --spend-cap (US$, the most this send may cost)")
    with Lock(rdir):
        subs = submissions(rdir)
        flight = in_flight(rdir, subs)
        offline = a.stub or a.dry_run or not a.yes
        plans = [p for p in (plan_setting(a, rdir, n, flight, offline) for n in names) if p is not None]
        print_plan(plans)
        plans = [p for p in plans if p["to_send"]]
        if not plans:
            print("nothing to send")
            return OK
        if a.dry_run:
            return dry_run(a, rdir, plans)
        if not a.yes:
            print("not sent: add --yes to send" + ("" if a.stub else " (paid requests; --spend-cap is needed too)"))
            return NO_YES
        worst = sum(p["worst"] for p in plans)
        if a.spend_cap is not None and worst > a.spend_cap:
            print(f"not sent: the worst case US${worst:.4f} exceeds --spend-cap {a.spend_cap}; send fewer settings, "
                  "use --limit, or raise the cap")
            return OVER_CAP
        cache = {}

        def client_of(api):
            if api not in cache:
                cache[api] = clients.make(api, stub=a.stub, store=rdir / "stub_store")
            return cache[api]

        for api in sorted({p["st"]["api"] for p in plans}):   # every key and SDK check before anything is sent
            client_of(api)
        for p in (p for p in plans if p["route"] == "batch"):
            code = submit_batches(a, rdir, p, client_of(p["st"]["api"]), subs)
            if code != OK:
                return code
        sync = [p for p in plans if p["route"] == "sync"]
        if sync:
            batch_worst = sum(p["worst"] for p in plans if p["route"] == "batch")
            cap = math.inf if a.spend_cap is None else a.spend_cap - batch_worst
            return send_sync_all(a, rdir, sync, client_of, cap)
    return OK


# ------------------------------------------------------------------------------------------------------ collect

def request_map(rdir: Path, name: str, rnd) -> dict:
    return {r["custom_id"]: r for r in read_jsonl(requests_path(rdir, name, rnd))}


def batch_context(rdir: Path, sub: dict, batch: dict) -> dict:
    price = None
    if sub.get("price_file") and (rdir / sub["price_file"]).exists():
        price = read_json(rdir / sub["price_file"])
    return {"route": "batch", "batch_id": batch["id"], "provider_requested": sub.get("provider_requested"),
            "api_version": sub.get("api_version"), "sdk_version": sub.get("sdk_version"), "price": price,
            "price_file": sub.get("price_file"), "stub": bool(sub.get("stub")),
            "request_time": iso_time(batch.get("created_at")),
            "response_time": iso_time(batch.get("ended_at") or batch.get("finalized_at"))}


def close_batch(a, rdir, sub, batch, client) -> bool:
    """Write the results of a finished batch. False while the batch is still running."""
    api, name = sub["api"], sub["setting"]
    ids = sub_ids(rdir, sub)
    st = settings.setting(name)
    if api == "anthropic":
        if batch.get("processing_status") != "ended":
            return False
        raw_entries = client.results(batch["id"])
        entries = {}
        for e in raw_entries:
            r = anthropic_client.result_entry(e)
            entries.setdefault(r["custom_id"], r)
        for cid in ids:
            entries.setdefault(cid, {"custom_id": cid, "ok": False,
                                     "error": {"type": "missing", "status": None,
                                               "message": "missing from the batch results", "body": None,
                                               "retryable": True}})
        status = batch.get("processing_status")
    else:
        entries, ready = openrouter_client.batch_entries(batch, ids)
        if not ready:
            return False
        raw_entries = batch.get("results") or []
        status = batch.get("status")
    raw_file = rdir / "raw" / f"{batch['id']}.jsonl.gz"
    if not raw_file.exists():
        write_jsonl(raw_file, raw_entries)
    ctx = batch_context(rdir, sub, batch)
    reqs = request_map(rdir, name, sub.get("round"))
    have = {(r.get("custom_id"), r.get("batch_id")) for r in read_jsonl(results_path(rdir, name))}
    rows, skipped = [], 0
    for cid in ids:
        if (cid, batch["id"]) in have:
            skipped += 1
            continue
        rec = reqs.get(cid) or fallback_request(a.run, cid, sub)
        e = entries[cid]
        if not e["ok"]:
            rows.append(result_record(rec, ctx, error=e["error"]))
            continue
        try:
            if api == "anthropic":
                reply = e["reply"]
            else:
                reply = openrouter_client.extract(e["body"], None,
                                                  batch_provider=batch.get("provider") or st.get("batch_provider"))
            rows.append(result_record(rec, ctx, reply=reply))
        except Exception as ex:  # noqa: BLE001
            rows.append(result_record(rec, ctx, error={"type": "extract", "status": None,
                                                       "message": f"{type(ex).__name__}: {ex}"[:500],
                                                       "body": None, "retryable": False}))
    if rows:
        append_jsonl_many(results_path(rdir, name), rows)
    log_event(rdir, "closed", local_id=sub["local_id"], batch_id=batch["id"], status=status,
              request_counts=batch.get("request_counts"), usage=batch.get("usage"), rows_written=len(rows),
              rows_skipped=skipped, raw_file=rel(rdir, raw_file))
    n_err = sum(r["status"] == "error" for r in rows)
    print(f"{name}: batch {batch['id']} {status}, {len(rows) - n_err} results and {n_err} errors written"
          + (f", {skipped} already written" if skipped else ""))
    return True


def cmd_collect(a) -> int:
    rdir = run_dir(a.run, a.stub)
    names = chosen(a)
    with Lock(rdir):
        pending = [s for s in submissions(rdir).values() if s["state"] == "open" and s["setting"] in names]
        if not pending:
            print("no open batches")
            return OK
        cache = {}

        def client_of(api):
            if api not in cache:
                cache[api] = clients.make(api, stub=a.stub, store=rdir / "stub_store")
            return cache[api]

        polls = max(1, int(a.max_wait)) if a.wait else 1
        for poll in range(polls):
            still, delay = [], POLL_S
            for s in pending:
                client = client_of(s["api"])
                try:
                    batch = client.retrieve(s["batch_id"])
                    save_batch(rdir, batch)
                    if not close_batch(a, rdir, s, batch, client):
                        still.append(s)
                except ClientError as e:
                    if e.status in (429, 503):
                        delay = POLL_429_S
                        still.append(s)
                    elif e.status in (402, 404, 410):
                        print(f"warning: batch {s['batch_id']} ({s['local_id']}) answers HTTP {e.status} and cannot be "
                              f"fetched again; release --local-id {s['local_id']} frees its requests", file=sys.stderr)
                    elif e.status in (400, 401, 403):
                        raise RunError(f"batch {s['batch_id']}: {e.message}") from None
                    else:
                        print(f"warning: batch {s['batch_id']}: {e.message}; tried again at the next poll",
                              file=sys.stderr)
                        still.append(s)
            pending = still
            if not pending:
                break
            if poll < polls - 1:
                SLEEP(delay)
        for s in pending:
            print(f"{s['setting']}: batch {s['batch_id']} ({s['local_id']}) still running")
    return OK


# ------------------------------------------------------------------------------------- status, cancel, batches

def cmd_status(a) -> int:
    rdir = run_dir(a.run, a.stub)
    names = chosen(a)
    subs = submissions(rdir)
    flight = in_flight(rdir, subs)
    print(f"{rdir}")
    print(f"{'setting':<18}{'r1':>6}{'r2':>6}{'not sent':>9}{'results':>9}{'errors only':>12}{'in flight':>10}"
          "  statuses")
    for name in names:
        r1 = read_jsonl(requests_path(rdir, name, 1))
        r2 = read_jsonl(requests_path(rdir, name, 2))
        ns = read_jsonl(not_sent_path(rdir, name))
        win, errs = winners(read_jsonl(results_path(rdir, name)))
        ids = {r["custom_id"] for r in r1 + r2}
        statuses = Counter(r.get("status") for r in win.values())
        print(f"{name:<18}{len(r1):>6}{len(r2):>6}{len(ns):>9}{len(win):>9}{len(errs - set(win)):>12}"
              f"{len((flight & ids) - set(win)):>10}  {dict(sorted(statuses.items()))}")
    shown = [s for s in subs.values() if s["setting"] in names]
    if shown:
        print(f"\n{'local ID':<44}{'round':>6}{'n':>7}  {'state':<10}batch ID")
        for s in shown:
            flag = " (cancel requested)" if s.get("cancel_requested") else ""
            print(f"{s['local_id']:<44}{s.get('round')!s:>6}{s.get('n')!s:>7}  {s['state']:<10}"
                  f"{s.get('batch_id') or '-'}{flag}")
    return OK


def find_sub(rdir, lid) -> tuple[dict, dict]:
    subs = submissions(rdir)
    if lid not in subs:
        raise RunError(f"no submission {lid} in {rdir / 'manifest.jsonl'}")
    return subs, subs[lid]


def cmd_cancel(a) -> int:
    rdir = run_dir(a.run, a.stub)
    with Lock(rdir):
        _, s = find_sub(rdir, a.local_id)
        if s["api"] != "anthropic":
            raise RunError("only an Anthropic batch can be cancelled; an OpenRouter batch runs to its end")
        if s["state"] != "open":
            raise RunError(f"{a.local_id} is {s['state']}, not open")
        batch = clients.make("anthropic", stub=a.stub, store=rdir / "stub_store").cancel(s["batch_id"])
        save_batch(rdir, batch)
        log_event(rdir, "cancel_requested", local_id=a.local_id, batch_id=s["batch_id"])
        print(f"cancel requested for {s['batch_id']}; collect writes its results, cancelled requests as errors "
              "that send --retry-failed sends again")
    return OK


def cmd_batches(a) -> int:
    rdir = run_dir(a.run, a.stub)
    if a.api == "hf":
        raise RunError("HF has no batches")
    tied = {s["batch_id"]: s["local_id"] for s in submissions(rdir).values() if s.get("batch_id")}
    rows = clients.make(a.api, stub=a.stub, store=rdir / "stub_store").list_batches(limit=a.limit)
    print(f"{'batch ID':<44}{'status':<12}{'created':<27}{'requests':>9}  local ID")
    for b in rows:
        counts = b.get("request_counts") or {}
        n = counts.get("total") if "total" in counts else sum(v for v in counts.values() if isinstance(v, int))
        status = b.get("processing_status") or b.get("status")
        print(f"{b.get('id', ''):<44}{status!s:<12}{iso_time(b.get('created_at'))!s:<27}{n!s:>9}  "
              f"{tied.get(b.get('id'), 'tied to no submission')}")
    return OK


def batch_size_of(batch: dict, api: str):
    counts = batch.get("request_counts") or {}
    if api == "anthropic":
        return sum(v for v in counts.values() if isinstance(v, int))
    return counts.get("total")


def cmd_adopt(a) -> int:
    rdir = run_dir(a.run, a.stub)
    with Lock(rdir):
        subs, s = find_sub(rdir, a.local_id)
        if s["state"] != "uncertain":
            raise RunError(f"{a.local_id} is {s['state']}; only a submission whose create ended without a reply "
                           "can adopt a batch")
        other = [x["local_id"] for x in subs.values() if x.get("batch_id") == a.batch_id]
        if other:
            raise RunError(f"batch {a.batch_id} already belongs to {other[0]}")
        batch = clients.make(s["api"], stub=a.stub, store=rdir / "stub_store").retrieve(a.batch_id)
        n = batch_size_of(batch, s["api"])
        if not n and not a.force:
            raise RunError(f"batch {a.batch_id} states no request count yet; wait a minute and adopt again, or add "
                           "--force only if you are sure it is the same batch")
        if n != s["n"] and not a.force:
            raise RunError(f"batch {a.batch_id} holds {n} requests and {a.local_id} sent {s['n']}; add --force "
                           "only if you are sure it is the same batch")
        log_event(rdir, "adopted", local_id=a.local_id, batch_id=a.batch_id, n_batch=n, forced=bool(a.force))
        save_batch(rdir, batch)
        print(f"{a.local_id} now collects batch {a.batch_id}")
    return OK


def cmd_release(a) -> int:
    rdir = run_dir(a.run, a.stub)
    with Lock(rdir):
        _, s = find_sub(rdir, a.local_id)
        if s["state"] not in ("uncertain", "open"):
            raise RunError(f"{a.local_id} is {s['state']}; only an uncertain or open submission can be released")
        log_event(rdir, "released", local_id=a.local_id, batch_id=s.get("batch_id"))
        print(f"{a.local_id} released: its {s['n']} requests can be sent again. A batch that does exist may still "
              "run and be billed, and its results are no longer collected", file=sys.stderr)
    return OK


# ------------------------------------------------------------------------------------------------------ summary

def summarise(records: list[dict], flight_n: int) -> dict:
    win, errs = winners(records)
    w = list(win.values())

    def total(key):
        return round(sum(r.get(key) for r in records if isinstance(r.get(key), (int, float))), 6)

    return {"records": len(records), "results": len(w), "errors_only": len(errs), "in_flight": flight_n,
            "cost_usd": total("cost_usd"), "reported_cost_usd": total("reported_cost"),
            "input_tokens": total("input_tokens"), "output_tokens": total("output_tokens"),
            "reasoning_tokens": total("reasoning_tokens"),
            "status": dict(Counter(r.get("status") for r in w)),
            "kind_status": dict(Counter(f"{r.get('kind')}:{r.get('status')}" for r in w)),
            "flags": dict(Counter(f for r in w for f in r.get("flags") or [])),
            "near_miss": dict(Counter(f for r in w for f in r.get("near_miss") or [])),
            "stop_kind": dict(Counter(r.get("stop_kind") for r in w)),
            "serving_provider": dict(Counter(f"{r.get('serving_provider')} ({r.get('serving_provider_source')})"
                                             for r in w)),
            "model_returned": dict(Counter(r.get("model_returned") for r in w)),
            "with_thinking": sum(bool(r.get("thinking_blocks") or r.get("thinking_text")) for r in w)}


def cmd_summary(a) -> int:
    rdir = run_dir(a.run, a.stub)
    names = chosen(a)
    flight = in_flight(rdir, submissions(rdir))
    out, every = {}, []
    for name in names:
        recs = read_jsonl(results_path(rdir, name))
        every += recs
        ids = {r["custom_id"] for r in read_jsonl(requests_path(rdir, name, 1)) + read_jsonl(requests_path(rdir, name, 2))}
        win, _ = winners(recs)
        out[name] = summarise(recs, len((flight & ids) - set(win)))
    out["total"] = summarise(every, sum(v["in_flight"] for v in out.values()))
    write_json(rdir / "summary.json", {"run": a.run, "stub": a.stub, "written": now_utc(), "settings": out})
    print(f"{'setting':<18}{'results':>8}{'ok':>6}{'errors':>8}{'thinking':>9}{'cost US$':>11}{'reported US$':>14}")
    for name, s in out.items():
        print(f"{name:<18}{s['results']:>8}{s['status'].get('ok', 0):>6}{s['errors_only']:>8}{s['with_thinking']:>9}"
              f"{s['cost_usd']:>11.4f}{s['reported_cost_usd']:>14.4f}")
    print(f"written to {rdir / 'summary.json'}")
    return OK


# ---------------------------------------------------------------------------------------------------------- CLI

def parser() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--run", required=True, choices=list(build.RUNS))
    common.add_argument("--stub", action="store_true", help="made-up replies, no network, data/runs/{run}-stub")
    sel = argparse.ArgumentParser(add_help=False)
    sel.add_argument("--setting", action="append", help="one setting (repeatable); default every setting of the run")
    p = argparse.ArgumentParser(prog="run.py", description=__doc__.split("\n\n")[0])
    sub = p.add_subparsers(dest="command", required=True)

    s = sub.add_parser("prepare", parents=[common, sel])
    s.add_argument("--round", type=int, choices=(1, 2), required=True)
    s.add_argument("--allow-missing", action="store_true", help="round 2: end the chains whose turn 1 has no result")
    s.add_argument("--replace", action="store_true", help="write over a request file with other content")
    s.set_defaults(func=cmd_prepare)

    s = sub.add_parser("send", parents=[common, sel])
    s.add_argument("--round", type=int, choices=(1, 2), required=True)
    s.add_argument("--route", choices=("batch", "sync"), help="send by this route instead of the planned one")
    s.add_argument("--yes", action="store_true", help="send (without it, show the plan only)")
    s.add_argument("--spend-cap", type=float, help="US$, the most this send may cost (needed for a paid send)")
    s.add_argument("--dry-run", action="store_true", help="write the request bodies to dryrun/ and send nothing")
    s.add_argument("--include-in-flight", action="store_true", help="send again requests in open batches")
    s.add_argument("--retry-failed", action="store_true", help="send again requests that have only errors")
    s.add_argument("--workers", type=int, default=4, help="sync requests at once per setting (default 4)")
    s.add_argument("--limit", type=int, help="at most this many requests per setting")
    s.add_argument("--batch-size", type=int, help="requests per batch (default 10,000 Anthropic, 1,000 OpenRouter)")
    s.set_defaults(func=cmd_send)

    s = sub.add_parser("collect", parents=[common, sel])
    s.add_argument("--wait", action="store_true", help="poll once a minute until every batch ends")
    s.add_argument("--max-wait", type=float, default=180, help="minutes of polling with --wait (default 180)")
    s.set_defaults(func=cmd_collect)

    s = sub.add_parser("status", parents=[common, sel])
    s.set_defaults(func=cmd_status)

    s = sub.add_parser("cancel", parents=[common])
    s.add_argument("--local-id", required=True)
    s.set_defaults(func=cmd_cancel)

    s = sub.add_parser("batches", parents=[common])
    s.add_argument("--api", required=True, choices=("anthropic", "openrouter", "hf"))
    s.add_argument("--limit", type=int, default=20)
    s.set_defaults(func=cmd_batches)

    s = sub.add_parser("adopt", parents=[common])
    s.add_argument("--local-id", required=True)
    s.add_argument("--batch-id", required=True)
    s.add_argument("--force", action="store_true", help="adopt although the request count differs")
    s.set_defaults(func=cmd_adopt)

    s = sub.add_parser("release", parents=[common])
    s.add_argument("--local-id", required=True)
    s.set_defaults(func=cmd_release)

    s = sub.add_parser("summary", parents=[common, sel])
    s.set_defaults(func=cmd_summary)
    return p


def main(argv=None) -> int:
    a = parser().parse_args(argv)
    try:
        return a.func(a)
    except (RunError, keys.MissingKey, ClientError, FileNotFoundError) as e:
        print(f"error: {getattr(e, 'message', None) or e}", file=sys.stderr)
        return ERROR


if __name__ == "__main__":
    sys.exit(main())
