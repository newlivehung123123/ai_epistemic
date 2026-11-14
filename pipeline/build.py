"""Request builder (PLAN 4.1 to 4.7 and 5.2). Turns the item files and, for round 2, the parsed turn-1 replies
into request records that name no API. No network and no keys: pipeline/clients turns a record into the body
of one API.

A request record holds
    run, setting, custom_id, item_id, set, chain, part, kind, arm, fields, stubborn, round,
    system, messages, max_tokens

custom_id is {setting}-{item_id}-c{chain}-{part} for turn 1 (part t1) and for turn 2 (part is the arm, with
_nf added when the two self-report fields are left out), and {setting}-{item_id}-probe for the knowledge
probe. Every custom_id matches ^[a-zA-Z0-9_-]{1,64}$ (PLAN 5.2) and is unique within a run.

Round 1 holds every turn-1 request (re-draws included) and the probe; round 2 holds the turn-2 replays, built
only from turn-1 replies that parsed (PLAN 4.3: if turn 1 fails to parse, the chain ends). A run with
"turn1_from" has no round 1 and replays the turn-1 replies of the run it names (PLAN 10.4).

The half split of PLAN 6.3 (triggered by pilot rule 6 on 8 November 2026): in each chain listed under "split", the
items of the no-fields half of each set receive turn 2 without the two self-report fields.
"""
from __future__ import annotations

import re

from pipeline import config, prompts, settings
from pipeline.util import read_json

CUSTOM_ID = re.compile(r"^[a-zA-Z0-9_-]{1,64}$")

FULL = tuple((arm, True) for arm in prompts.ARMS)          # the six arms with the two self-report fields
NO_FIELDS = tuple((arm, False) for arm in prompts.ARMS)    # PLAN 4.5, chain 3 of Haiku 5.5 off
SELF_REPORT = (("enthusiast", False), ("skeptic", False))  # PLAN 6.3 self-report check, pilot only
REDRAW = ()                                                # a turn-1 request only (PLAN 4.5)

STUBBORN_N = 100   # PLAN 4.7


def _spec(items, chains, probe_sets=(), route=None, split=()):
    """items: None for every item of the run's sets, a pilot subset name, or "stubborn" for the PLAN 4.7 draw.
    chains: {chain number: the (arm, fields) pairs of its turn 2}. probe_sets: the sets whose items get the
    knowledge probe. route: batch or sync when the run departs from settings.route(). split: the chains whose
    turn 2 follows the half split of PLAN 6.3 (the arms lose the two fields on the no-fields half)."""
    return {"items": items, "chains": chains, "probe_sets": tuple(probe_sets), "route": route,
            "split": tuple(split)}


RUNS = {
    # PLAN 10 pilot and cost_model.pilot_lines: Haiku 5.5 off 50 items, 2 chains, probe, self-report check on
    # chain 1; Haiku 5.5 medium 50 items; Sonnet 5.5 off 20 items, 2 chains, probe; Sonnet 5.5 high 10 items;
    # each panel model 20 items, 1 chain, probe (no re-draw in the pilot)
    "pilot": {
        "phase": "pilot",
        "sets": ("pilot",),
        "settings": {
            "haiku_off": _spec(None, {1: FULL + SELF_REPORT, 2: FULL}, ("pilot",)),
            "haiku_medium": _spec(None, {1: FULL}),
            "sonnet_off": _spec("sub20", {1: FULL, 2: FULL}, ("pilot",)),
            "sonnet_high": _spec("sub10", {1: FULL}),
            **{name: _spec("sub20", {1: FULL}, ("pilot",)) for name in settings.PANEL},
        },
    },
    # PLAN 10.3 rule 8: turn 1 only on 10 items for each OR batch model, sent through the OR batch route
    "pilot_batch_test": {
        "phase": "pilot",
        "sets": ("pilot",),
        "settings": {name: _spec("sub10", {1: REDRAW}, route="batch") for name in ("gpt6luna", "deepseek_flash")},
    },
    # PLAN 10.4: the turn-2 wording of 8 November 2026 checked on 10 pilot items per sprint setting, turn 2 only,
    # replayed on the chain-1 turn-1 replies of the pilot run
    "pilot_wording": {
        "phase": "pilot",
        "sets": ("pilot",),
        "turn1_from": "pilot",
        "settings": {name: _spec("sub10", {1: FULL})
                     for name in ("haiku_off", "haiku_medium", "sonnet_off", *settings.PANEL)},
    },
    # PLAN 4.5 to 4.7 and 5.2: the sprint run of 13 November 2026 under Option A, with the half split of PLAN 6.3
    # on chain 1 of every setting
    "sprint": {
        "phase": "sprint",
        "sets": ("retro", "prospective"),
        "settings": {
            "haiku_off": _spec(None, {1: FULL, 2: FULL, 3: NO_FIELDS}, ("retro",), split=(1,)),
            "haiku_medium": _spec(None, {1: FULL, 2: REDRAW}, split=(1,)),
            "sonnet_off": _spec(None, {1: FULL, 2: REDRAW}, ("retro",), split=(1,)),
            **{name: _spec(None, {1: FULL, 2: REDRAW}, ("retro",), split=(1,)) for name in settings.PANEL},
            "haiku_off_stub": _spec("stubborn", {1: FULL}, split=(1,)),
        },
    },
}


def run_spec(run: str) -> dict:
    if run not in RUNS:
        raise KeyError(f"unknown run {run}; known: {', '.join(RUNS)}")
    return RUNS[run]


def route(run: str, name: str) -> str:
    spec = run_spec(run)["settings"][name]
    r = spec["route"] or settings.route(name, run_spec(run)["phase"])
    if r not in ("batch", "sync"):
        raise ValueError(f"{name} has no route in the {run} run")
    if settings.setting(name)["api"] == "anthropic" and r != "batch":
        raise ValueError("every Anthropic request goes through Message Batches (PLAN 5.2)")
    if settings.setting(name)["api"] == "hf" and r != "sync":
        raise ValueError("HF has no batch route (PLAN 5.4)")
    return r


def load_items(set_name: str) -> list[dict]:
    path = config.ITEMS / f"{set_name}_items.json"
    if not path.exists():
        raise FileNotFoundError(f"{path} does not exist; run the item stages of pipeline/fetch_items.py first")
    return read_json(path)["items"]


def load_run_items(run: str) -> dict:
    return {s: load_items(s) for s in run_spec(run)["sets"]}


def stubborn_ids(retro_items: list[dict]) -> list[str]:
    """PLAN 4.7: 100 retro items by a seeded random draw from the sorted item IDs."""
    ids = sorted(it["item_id"] for it in retro_items)
    if len(ids) < STUBBORN_N:
        raise ValueError(f"the stubbornness draw needs {STUBBORN_N} retro items; the retro file holds {len(ids)}")
    return sorted(config.rng(config.RUN_SEED, "stubbornness").sample(ids, STUBBORN_N))


def half_split_ids(set_name: str, items: list[dict]) -> set[str]:
    """PLAN 6.3: the no-fields half of one set, ceil(n/2) items by a seeded random draw from the sorted item IDs.
    The half depends only on the set, so every setting of a run uses the same half."""
    ids = sorted(it["item_id"] for it in items)
    return set(config.rng(config.RUN_SEED, f"half_split:{set_name}").sample(ids, (len(ids) + 1) // 2))


def no_fields_ids(run: str, items_by_set: dict) -> set[str]:
    """The no-fields half of every set of the run (empty when no setting of the run splits a chain)."""
    spec = run_spec(run)
    if not any(s["split"] for s in spec["settings"].values()):
        return set()
    return set().union(*(half_split_ids(s, items_by_set[s]) for s in spec["sets"]))


def turn2_arms(run: str, name: str, item: dict, chain: int, nf_ids: set) -> tuple:
    """The (arm, fields) pairs of one chain for one item, after the half split of PLAN 6.3."""
    spec = run_spec(run)["settings"][name]
    arms = spec["chains"][chain]
    if chain in spec["split"] and item["item_id"] in nf_ids:
        return tuple((arm, False) for arm, _ in arms)
    return arms


def turn1_source(run: str) -> str:
    """The run whose turn-1 replies feed round 2 of this run."""
    return run_spec(run).get("turn1_from") or run


def turn1_ids(run: str, name: str, items_by_set: dict) -> list[str]:
    """The turn-1 custom_ids that round 2 of this run needs, in the run of turn1_source(run)."""
    spec = run_spec(run)["settings"][name]
    if not run_spec(run).get("turn1_from"):
        return [r["custom_id"] for r in round1(run, name, items_by_set) if r["kind"] == "t1"]
    return [custom_id(name, it["item_id"], chain, "t1") for it in select_items(run, name, items_by_set)
            for chain in sorted(spec["chains"]) if spec["chains"][chain]]


def select_items(run: str, name: str, items_by_set: dict) -> list[dict]:
    spec = run_spec(run)
    which = spec["settings"][name]["items"]
    pool = [it for s in spec["sets"] for it in items_by_set[s]]
    if which is None:
        return pool
    if which == "stubborn":
        keep = set(stubborn_ids(items_by_set["retro"]))
        return [it for it in items_by_set["retro"] if it["item_id"] in keep]
    out = [it for it in pool if which in (it.get("subsets") or [])]
    size = dict(config.SETS[spec["sets"][0]]["subsets"]).get(which)
    if size is not None and len(out) != size:
        raise ValueError(f"subset {which} should hold {size} items; the item file gives {len(out)}")
    return out


def part_name(arm: str, fields: bool) -> str:
    return arm if fields else f"{arm}_nf"


def custom_id(name: str, item_id: str, chain: int | None, part: str) -> str:
    cid = f"{name}-{item_id}-probe" if part == "probe" else f"{name}-{item_id}-c{chain}-{part}"
    if not CUSTOM_ID.match(cid):
        raise ValueError(f"custom_id {cid!r} does not match {CUSTOM_ID.pattern}")
    return cid


def _record(run, name, item, chain, part, kind, rnd, arm=None, fields=None) -> dict:
    st = settings.setting(name)
    return {"run": run, "setting": name, "custom_id": custom_id(name, item["item_id"], chain, part),
            "item_id": item["item_id"], "set": item["set"], "chain": chain, "part": part, "kind": kind,
            "arm": arm, "fields": fields, "stubborn": bool(st.get("stubborn")), "round": rnd,
            "max_tokens": st["max_tokens"]}


def turn1_text(item: dict) -> str:
    return prompts.turn1(item, config.SETS[item["set"]]["F"])


def turn1_request(run: str, name: str, item: dict, chain: int) -> dict:
    rec = _record(run, name, item, chain, "t1", "t1", 1)
    rec["system"] = prompts.system_prompt(rec["stubborn"])
    rec["messages"] = [{"role": "user", "content": turn1_text(item)}]
    return rec


def probe_request(run: str, name: str, item: dict) -> dict:
    rec = _record(run, name, item, None, "probe", "probe", 1)
    rec["system"] = prompts.PROBE_SYSTEM
    rec["messages"] = [{"role": "user", "content": prompts.probe(item)}]
    return rec


def turn2_request(run: str, name: str, item: dict, chain: int, arm: str, fields: bool, parsed_t1: dict) -> dict:
    """PLAN 4.3: the system prompt, the turn-1 message, the model's previous message (the parsed turn-1 object,
    without thinking) and one turn-2 message."""
    rec = _record(run, name, item, chain, part_name(arm, fields), "t2" if fields else "t2_nf", 2, arm, fields)
    rec["system"] = prompts.system_prompt(rec["stubborn"])
    rec["messages"] = [
        {"role": "user", "content": turn1_text(item)},
        {"role": "assistant", "content": prompts.replay(parsed_t1)},
        {"role": "user", "content": prompts.turn2(arm, item["q_pct"], fields)},
    ]
    return rec


def round1(run: str, name: str, items_by_set: dict) -> list[dict]:
    if run_spec(run).get("turn1_from"):
        return []
    spec = run_spec(run)["settings"][name]
    out = []
    for item in select_items(run, name, items_by_set):
        for chain in sorted(spec["chains"]):
            out.append(turn1_request(run, name, item, chain))
        if item["set"] in spec["probe_sets"]:
            out.append(probe_request(run, name, item))
    return out


def round2(run: str, name: str, items_by_set: dict, t1_results: dict) -> tuple[list[dict], list[dict]]:
    """t1_results maps a turn-1 custom_id to its parse result ({"status", "parsed", ...}). Returns the round-2
    requests and a not-sent record for each arm whose chain ended at turn 1."""
    spec = run_spec(run)["settings"][name]
    nf_ids = no_fields_ids(run, items_by_set) if spec["split"] else set()
    requests, not_sent = [], []
    for item in select_items(run, name, items_by_set):
        for chain in sorted(spec["chains"]):
            arms = turn2_arms(run, name, item, chain, nf_ids)
            if not arms:
                continue
            t1_id = custom_id(name, item["item_id"], chain, "t1")
            res = t1_results.get(t1_id)
            ok = res is not None and res.get("status") == "ok" and res.get("parsed") is not None
            for arm, fields in arms:
                if ok:
                    requests.append(turn2_request(run, name, item, chain, arm, fields, res["parsed"]))
                else:
                    rec = _record(run, name, item, chain, part_name(arm, fields), "t2" if fields else "t2_nf",
                                  2, arm, fields)
                    rec["status"] = "not_sent"
                    rec["reason"] = ("turn 1 has no result" if res is None
                                     else f"turn 1 status {res.get('status')}")
                    not_sent.append(rec)
    return requests, not_sent


def expected_counts(run: str, items_by_set: dict) -> dict:
    """Requests per setting if every turn-1 reply parses: items, t1, t2 (with and without the fields), probe and
    the total. A run with turn1_from sends no turn 1 and no probe."""
    out = {}
    replay = bool(run_spec(run).get("turn1_from"))
    for name, spec in run_spec(run)["settings"].items():
        items = select_items(run, name, items_by_set)
        t1 = 0 if replay else len(items) * len(spec["chains"])
        t2 = len(items) * sum(len(a) for a in spec["chains"].values())
        probe = sum(it["set"] in spec["probe_sets"] for it in items)
        out[name] = {"items": len(items), "t1": t1, "t2": t2, "probe": probe, "total": t1 + t2 + probe}
    return out


def all_custom_ids(run: str, items_by_set: dict) -> list[str]:
    """Every custom_id the run can send, with turn 2 built as if every turn-1 reply parsed."""
    ids = []
    for name in run_spec(run)["settings"]:
        ids += [r["custom_id"] for r in round1(run, name, items_by_set)]
        fake = {cid: {"status": "ok", "parsed": {"probability": 50, "prepare": True}}
                for cid in turn1_ids(run, name, items_by_set)}
        ids += [r["custom_id"] for r in round2(run, name, items_by_set, fake)[0]]
    return ids


CHAIN = re.compile(r"^c\d+$")


def parse_custom_id(cid: str) -> dict:
    """The inverse of custom_id: {setting, item_id, chain, part, kind, arm, fields}. Setting names and item IDs
    hold no hyphen, so the hyphens split the parts."""
    if not isinstance(cid, str) or not CUSTOM_ID.match(cid):
        raise ValueError(f"custom_id {cid!r} does not match {CUSTOM_ID.pattern}")
    bits = cid.split("-")
    if len(bits) == 3 and bits[2] == "probe":
        return {"setting": bits[0], "item_id": bits[1], "chain": None, "part": "probe", "kind": "probe",
                "arm": None, "fields": None}
    if len(bits) != 4 or not CHAIN.match(bits[2]):
        raise ValueError(f"custom_id {cid!r} is not a request of this pipeline")
    out = {"setting": bits[0], "item_id": bits[1], "chain": int(bits[2][1:]), "part": bits[3]}
    if bits[3] == "t1":
        return {**out, "kind": "t1", "arm": None, "fields": None}
    fields = not bits[3].endswith("_nf")
    arm = bits[3] if fields else bits[3][:-3]
    if arm not in prompts.ARMS:
        raise ValueError(f"custom_id {cid!r} names no arm")
    return {**out, "kind": "t2" if fields else "t2_nf", "arm": arm, "fields": fields}
