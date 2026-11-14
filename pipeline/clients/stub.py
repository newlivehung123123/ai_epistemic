"""Made-up replies for testing the pipeline with no network and no key (run.py --stub).

Each reply is fixed by a hash of its custom_id, so a stub run gives the same replies every time. The replies cover
what the parser and run.py must handle: plain JSON, fenced JSON, a bare percent sign, a refusal, a reply cut at the
output cap, a probability sent as a string, a missing field, a known outcome in the probe, and a thinking text in
the settings that think. Batches live as files in the store folder of the stub run."""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import re
import time
from pathlib import Path

from pipeline import build, settings
from pipeline.clients.common import ClientError, SubmitUncertain
from pipeline.util import UTC, read_json, write_json

ERROR_IDS: set = set()        # custom_ids that fail: HTTP 400 for a sync request, an errored line in a batch
BATCH_POLLS_BEFORE_END = 0    # polls a batch stays in progress before it ends
RESULTS_NULL_POLLS = 0        # OpenRouter: further polls a completed batch still shows results null
SUBMIT_FAILS = None           # None, "certain", "uncertain_created" or "uncertain_lost"; used once, then reset

ANTHROPIC_STOP = {"normal": "end_turn", "cut": "max_tokens", "refusal": "refusal"}
CHAT_STOP = {"normal": "stop", "cut": "length", "refusal": "content_filter"}
SHIFT = {"control": 0, "enthusiast": 5, "skeptic": -5}


def _hash(cid: str) -> int:
    return int(hashlib.sha256(cid.encode("utf-8")).hexdigest(), 16)


def _now_iso() -> str:
    return dt.datetime.now(UTC).isoformat(timespec="seconds")


def _tokens(text) -> int:
    return max(1, len(text or "") // 4)


def reply(cid: str, messages: list[dict]) -> tuple[str, str, str | None]:
    """The made-up reply to a request: (text, stop, thinking), where stop is normal, cut or refusal."""
    info = build.parse_custom_id(cid)
    h = _hash(cid)
    r = h % 100
    thinking = f"Stub thinking for {cid}." if settings.setting(info["setting"]).get("thinks") else None
    if info["kind"] == "probe":
        obj = ({"known": True, "outcome": "yes" if h % 2 else "no"} if r < 5
               else {"known": False, "outcome": "unknown"})
        return json.dumps(obj), "normal", thinking
    if info["kind"] == "t1":
        p = 5 + h % 91
        text = json.dumps({"reasoning": "Stub reasoning for turn 1.", "probability": p, "prepare": p > 50})
        plain = f'"probability": {p},'
        if r <= 2:
            return f"```json\n{text}\n```", "normal", thinking
        if r <= 4:
            return text.replace(plain, f'"probability": {p}%,'), "normal", thinking
        if r == 5:
            return "I can't help with that.", "refusal", thinking
        if r == 6:
            return text[: len(text) // 2], "cut", thinking
        if r == 7:
            return text.replace(plain, f'"probability": "{p}%",'), "normal", thinking
        return text, "normal", thinking
    previous = next((m["content"] for m in messages if m["role"] == "assistant"), "{}")
    try:
        p1 = float(json.loads(previous)["probability"])
    except (ValueError, KeyError, TypeError):
        p1 = 50.0
    found = re.search(r"at (\d+)%\.", messages[-1]["content"])
    q = float(found.group(1)) if found else p1
    arm = info["arm"]
    if arm == "market":
        p2 = p1 + (q - p1) / 2
    elif arm == "hunch":
        p2 = p1 + (q - p1) / 4
    elif arm == "double_check":
        p2 = p1 + (1 if h % 2 else -1)
    else:
        p2 = p1 + SHIFT[arm]
    p2 = int(round(min(100.0, max(0.0, p2))))
    obj = {"reasoning": "Stub reasoning for turn 2.", "probability": p2, "prepare": p2 > 50}
    if info["kind"] == "t2":
        obj["changed"] = p2 != round(p1)
        obj["previous_probability"] = round(p1)
        if r == 3:
            del obj["previous_probability"]
    text = json.dumps(obj)
    return (f"```json\n{text}\n```" if r <= 2 else text), "normal", thinking


def anthropic_message(params: dict, cid: str) -> dict:
    """A Message as the SDK's to_dict gives it. A thinking block comes only when the request sends no thinking
    field, as for Haiku 5.5 medium and Sonnet 5.5 high."""
    text, stop, thinking = reply(cid, params["messages"])
    content = []
    if "thinking" not in params:
        content.append({"type": "thinking", "thinking": thinking or f"Stub thinking for {cid}.",
                        "signature": "stub"})
    content.append({"type": "text", "text": text})
    n_in = _tokens(params["system"] + "".join(m["content"] for m in params["messages"]))
    n_out = sum(_tokens(b.get("text") or b.get("thinking")) for b in content)
    return {"id": f"msg_stub_{_hash(cid) % 10**16:016d}", "type": "message", "role": "assistant",
            "model": f"{params['model']}-STUB", "content": content, "stop_reason": ANTHROPIC_STOP[stop],
            "stop_sequence": None,
            "usage": {"input_tokens": n_in, "output_tokens": n_out, "cache_creation_input_tokens": 0,
                      "cache_read_input_tokens": 0}}


def chat_completion(body: dict, cid: str, model: str, provider: str | None = None, cost: bool = True) -> dict:
    """A chat completion as OpenRouter or the Hugging Face router gives it."""
    text, stop, thinking = reply(cid, body["messages"])
    n_in = _tokens("".join(m["content"] for m in body["messages"]))
    n_think = _tokens(thinking) if thinking else 0
    n_out = _tokens(text) + n_think
    message = {"role": "assistant", "content": text}
    usage = {"prompt_tokens": n_in, "completion_tokens": n_out, "total_tokens": n_in + n_out}
    if thinking:
        message["reasoning"] = thinking
        usage["completion_tokens_details"] = {"reasoning_tokens": n_think}
    if cost:
        usage["cost"] = round((n_in * 0.1 + n_out * 0.5) / 1e6, 10)
    out = {"id": f"gen-stub-{_hash(cid) % 10**12:012d}", "object": "chat.completion", "created": int(time.time()),
           "model": f"{model}-STUB",
           "choices": [{"index": 0, "finish_reason": CHAT_STOP[stop], "native_finish_reason": CHAT_STOP[stop],
                        "message": message}],
           "usage": usage}
    if provider:
        out["provider"] = provider
    return out


def _take_fail():
    global SUBMIT_FAILS
    mode, SUBMIT_FAILS = SUBMIT_FAILS, None
    return mode


def _sync_error(cid):
    if cid in ERROR_IDS:
        raise ClientError("HTTP 400 on POST stub chat completion", kind="http", status=400,
                          body='{"error": {"message": "stub error"}}')


class _BatchStore:
    prefix = "batch"

    def __init__(self, store):
        if store is None:
            raise ValueError("a stub batch client needs a store folder")
        self.store = Path(store)
        self.store.mkdir(parents=True, exist_ok=True)

    def _files(self):
        return sorted(self.store.glob(f"{self.prefix}_stub*.stub.json.gz"))

    def _path(self, bid):
        return self.store / f"{bid}.stub.json.gz"

    def _load(self, bid):
        path = self._path(bid)
        if not path.exists():
            raise ClientError(f"HTTP 404 on stub batch {bid}", kind="http", status=404)
        return read_json(path)

    def _save(self, b):
        write_json(self._path(b["id"]), b, gz=True)

    def _new_id(self, ids):
        digest = hashlib.sha256(json.dumps(ids).encode("utf-8")).hexdigest()[:10]
        return f"{self.prefix}_stub{len(self._files()) + 1:04d}_{digest}"

    @staticmethod
    def _public(b):
        return {k: v for k, v in b.items() if not k.startswith("_")}

    def submit(self, payload):
        mode = _take_fail()
        if mode == "certain":
            raise ClientError("HTTP 400 on stub batch create", kind="http", status=400)
        if mode == "uncertain_lost":
            raise SubmitUncertain("ReadTimeout on stub batch create", kind="timeout")
        batch = self._create(payload)
        if mode == "uncertain_created":
            raise SubmitUncertain("ReadTimeout on stub batch create", kind="timeout")
        return self._public(batch)

    def list_batches(self, limit=20):
        return [self._public(read_json(f)) for f in reversed(self._files())][:limit]


class StubAnthropic(_BatchStore):
    api = "anthropic"
    prefix = "msgbatch"

    def _create(self, requests):
        ids = [r["custom_id"] for r in requests]
        b = {"id": self._new_id(ids), "type": "message_batch", "processing_status": "in_progress",
             "request_counts": {"processing": len(ids), "succeeded": 0, "errored": 0, "canceled": 0, "expired": 0},
             "created_at": _now_iso(), "ended_at": None, "expires_at": None, "cancel_initiated_at": None,
             "archived_at": None, "results_url": None, "_requests": requests, "_polls": 0, "_canceled": False}
        self._save(b)
        return b

    def _outcome(self, b, cid):
        if b["_canceled"]:
            return "canceled"
        return "errored" if cid in ERROR_IDS else "succeeded"

    def retrieve(self, bid):
        b = self._load(bid)
        if b["processing_status"] != "ended":
            b["_polls"] += 1
            if b["_canceled"] or b["_polls"] > BATCH_POLLS_BEFORE_END:
                counts = {"processing": 0, "succeeded": 0, "errored": 0, "canceled": 0, "expired": 0}
                for r in b["_requests"]:
                    counts[self._outcome(b, r["custom_id"])] += 1
                b.update(processing_status="ended", request_counts=counts, ended_at=_now_iso(),
                         results_url=f"stub://{bid}/results")
            self._save(b)
        return self._public(b)

    def results(self, bid):
        b = self._load(bid)
        if b["processing_status"] != "ended":
            raise ClientError(f"stub batch {bid} has not ended", kind="other")
        out = []
        for r in b["_requests"]:
            cid = r["custom_id"]
            outcome = self._outcome(b, cid)
            if outcome == "succeeded":
                res = {"type": "succeeded", "message": anthropic_message(r["params"], cid)}
            elif outcome == "errored":
                res = {"type": "errored", "error": {"type": "error", "error": {"type": "invalid_request_error",
                                                                                "message": "stub error"}}}
            else:
                res = {"type": "canceled"}
            out.append({"custom_id": cid, "result": res})
        return out

    def cancel(self, bid):
        b = self._load(bid)
        if b["processing_status"] == "in_progress":
            b.update(_canceled=True, processing_status="canceling", cancel_initiated_at=_now_iso())
            self._save(b)
        return self._public(b)

    def api_version(self):
        return "2023-06-01"

    def sdk_version(self):
        return "stub"


class StubOpenRouter(_BatchStore):
    api = "openrouter"
    prefix = "batch"

    def send_sync(self, body, cid=None):
        _sync_error(cid)
        provider = "STUB-" + body["provider"]["only"][0]
        return chat_completion(body, cid, body["model"], provider=provider), {"x-request-id": "stub"}

    def _create(self, payload):
        reqs = payload["requests"]
        ids = [r["custom_id"] for r in reqs]
        now = int(time.time())
        b = {"id": self._new_id(ids), "object": "batch", "endpoint": payload["endpoint"], "model": payload["model"],
             "completion_window": payload["completion_window"], "status": "validating", "created_at": now,
             "finalized_at": None, "provider": payload["provider"]["only"][0], "expires_at": now + 86_400,
             "request_counts": {"total": len(ids), "completed": 0, "failed": 0}, "usage": None, "results": None,
             "error": None, "_requests": reqs, "_polls": 0}
        self._save(b)
        return b

    def retrieve(self, bid):
        b = self._load(bid)
        b["_polls"] += 1
        if b["_polls"] <= BATCH_POLLS_BEFORE_END:
            b["status"] = "in_progress"
        else:
            b["status"] = "completed"
            b["finalized_at"] = b["finalized_at"] or int(time.time())
            if b["_polls"] > BATCH_POLLS_BEFORE_END + RESULTS_NULL_POLLS and b["results"] is None:
                self._finish(b)
        self._save(b)
        return self._public(b)

    def _finish(self, b):
        out, ok, failed, n_in, n_out = [], 0, 0, 0, 0
        for r in b["_requests"]:
            cid = r["custom_id"]
            rid = f"req_stub_{_hash(cid) % 10**10:010d}"
            if cid in ERROR_IDS:
                out.append({"id": rid, "custom_id": cid, "response": None,
                            "error": {"type": "invalid_request_error", "message": "stub error", "param": None,
                                      "error_type": "invalid_request"}})
                failed += 1
                continue
            body = chat_completion(r["body"], cid, b["model"])
            out.append({"id": rid, "custom_id": cid,
                        "response": {"status_code": 200, "request_id": rid, "body": body}, "error": None})
            ok += 1
            n_in += body["usage"]["prompt_tokens"]
            n_out += body["usage"]["completion_tokens"]
        b["results"] = out
        b["usage"] = {"prompt_tokens": n_in, "completion_tokens": n_out, "total_tokens": n_in + n_out,
                      "cost": round((n_in * 0.05 + n_out * 0.25) / 1e6, 10), "is_byok": False}
        b["request_counts"] = {"total": len(out), "completed": ok, "failed": failed}


class StubHF:
    api = "hf"

    def __init__(self, store=None):
        self.store = store

    def send_sync(self, body, cid=None):
        _sync_error(cid)
        suffix = body["model"].rsplit(":", 1)[1] if ":" in body["model"] else "auto"
        return chat_completion(body, cid, body["model"], cost=False), {"x-inference-provider": f"STUB-{suffix}"}
