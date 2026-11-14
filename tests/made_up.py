"""Made-up items, replies and outcomes for the tests of pipeline/analysis.py. Nothing here reads a file in data/,
and no value comes from a real market or from a real model."""
from __future__ import annotations

import random
from pathlib import Path

from pipeline import build, config, prompts
from pipeline import pilot_report as pr

RUN = "sprint"
ARMS = prompts.ARMS
PREFIX = {"retro": "ret", "prospective": "pro"}
EVENT_SIZES = (2, 1, 3, 2, 2, 1)
TOPIC_FIELDS = (("us_midterms", True, False), ("other_elections", False, False), ("ai_companies", False, True),
                ("other", False, False), ("other_elections", True, False))


def make_items(n_retro=120, n_prospective=120, mirror_pairs=3):
    """Made-up items of both sets with the fields that the analysis reads. An event holds one, two or three
    items, a family holds three events and has the same name in both sets, the topic fields follow the family,
    and the first events of two items in each set are mirror pairs."""
    out = {}
    for set_name, n in (("retro", n_retro), ("prospective", n_prospective)):
        items, ev, left = [], -1, 0
        for i in range(n):
            if left == 0:
                ev += 1
                left = EVENT_SIZES[ev % len(EVENT_SIZES)]
            left -= 1
            fam = ev // 3
            coarse, us, ai = TOPIC_FIELDS[fam % len(TOPIC_FIELDS)]
            items.append({"item_id": f"{PREFIX[set_name]}{i + 1:03d}", "set": set_name,
                          "question": f"Will made-up event {i + 1} happen?", "description": "A made-up market.",
                          "end_date": "2026-11-08", "t": config.T_VALUES[i % 5], "q_pct": 5 + (i * 7) % 91,
                          "event_id": f"{PREFIX[set_name]}-event-{ev}", "event_title": f"Made-up event {ev}",
                          "event_slug": f"made-up-event-{ev}", "market_id": f"{PREFIX[set_name]}-market-{i}",
                          "family": f"Made-up family {fam}", "coarse_family": coarse, "us": us, "ai_company": ai,
                          "mirror": False})
        by_event = {}
        for it in items:
            by_event.setdefault(it["event_id"], []).append(it)
        pairs = [v for v in by_event.values() if len(v) == 2][:mirror_pairs]
        for a, b in pairs:
            a["mirror"] = b["mirror"] = True
            b["q_pct"] = 100 - a["q_pct"]
        out[set_name] = items
    return out


def _pct(x):
    return int(min(100, max(0, round(x))))


class Model:
    """A made-up model with adjustable habits. Every value comes from a seeded generator keyed by the setting,
    the item, the chain and the arm, so two builds give the same replies. Probabilities are whole percentages.

    lean        the size of the move towards the asker in the enthusiast and skeptic arms, in points
    w_market    the share of the gap to the market price closed in the market arm
    w_hunch     the same share in the hunch arm
    hide        the chance that a changed answer is reported as unchanged
    phantom     the chance that an unchanged answer is reported as changed
    misreport   the chance that the recalled probability is not the turn-1 probability
    lost        the chance that a reply cannot be parsed
    partial     the chance that a turn-2 reply with the two fields lacks the recalled probability
    know        the chance that the probe reply claims to know the outcome"""

    def __init__(self, seed=11, lean=6, w_market=0.6, w_hunch=0.2, hide=0.25, phantom=0.1, misreport=0.2,
                 lost=0.0, partial=0.0, know=0.2, jitter=True):
        self.seed, self.lean, self.w_market, self.w_hunch = seed, lean, w_market, w_hunch
        self.hide, self.phantom, self.misreport = hide, phantom, misreport
        self.lost, self.partial, self.know, self.jitter = lost, partial, know, jitter

    def rng(self, *key):
        return random.Random("-".join(str(k) for k in (self.seed,) + key))

    def t1(self, name, item, chain):
        r = self.rng("t1", name, item["item_id"], chain)
        if r.random() < self.lost:
            return None
        base = item["q_pct"] + self.rng("base", name, item["item_id"]).randint(-30, 30)
        p = _pct(base + (r.choice((-5, -2, 0, 0, 0, 2, 5, 8)) if self.jitter else 0))
        d = (p >= 100 * item["t"]) != (r.random() < 0.1)
        return {"probability": p, "prepare": bool(d)}

    def move(self, name, item, chain, arm, t1, r):
        p1, q = t1["probability"], item["q_pct"]
        noise = r.choice((0, 0, 0, 2, -2, 5)) if self.jitter else 0
        return {"control": noise, "double_check": noise,
                "enthusiast": r.choice((0, self.lean, 2 * self.lean)) if self.jitter else self.lean,
                "skeptic": -(r.choice((0, self.lean, 2 * self.lean)) if self.jitter else self.lean),
                "market": self.w_market * (q - p1), "hunch": self.w_hunch * (q - p1)}[arm]

    def t2(self, name, item, chain, arm, fields, t1):
        r = self.rng("t2", name, item["item_id"], chain, arm)
        if r.random() < self.lost:
            return None
        p1, d1 = t1["probability"], t1["prepare"]
        p2 = _pct(p1 + self.move(name, item, chain, arm, t1, r))
        d2 = (p2 >= 100 * item["t"]) != (r.random() < 0.08) if self.jitter else d1
        out = {"probability": p2, "prepare": bool(d2)}
        if not fields:
            return out
        moved = p2 != p1 or bool(d2) != bool(d1)
        out["changed"] = bool(moved != (r.random() < (self.hide if moved else self.phantom)))
        if r.random() < self.partial:
            return ("partial", out)
        out["previous_probability"] = p1
        if r.random() < self.misreport:
            out["previous_probability"] = p2 if r.random() < 0.5 else _pct(p1 + r.choice((-3, 3, 7)))
        return out

    def probe(self, name, item):
        r = self.rng("probe", name, item["item_id"])
        if r.random() < self.lost:
            return None
        known = r.random() < self.know
        return {"known": bool(known), "outcome": r.choice(("yes", "no", "unknown")) if known else "unknown"}


def _as_reply(x):
    """A reply as the fields of a result record. A dict of parsed values is an ok reply, a (status, parsed) pair
    gives another status, and None is a reply that the parser could not read."""
    if x is None:
        return {"status": "missing", "parsed": None}
    if isinstance(x, tuple):
        return {"status": x[0], "parsed": x[1]}
    return {"status": "ok", "parsed": x}


def make_records(items_by_set, model, names=None, run=RUN):
    """The result records of each setting of the run as {setting: [record]}, laid out as the pipeline lays out
    the requests: turn 1 of each chain, the turn-2 arms of the chain under the half split and the knowledge
    probe on the probe sets. A turn 2 exists only when turn 1 parsed."""
    spec = build.run_spec(run)
    nf_ids = build.no_fields_ids(run, items_by_set)
    out = {}
    for name in names or spec["settings"]:
        s = spec["settings"][name]
        recs = []
        for item in build.select_items(run, name, items_by_set):
            for chain in sorted(s["chains"]):
                t1 = _as_reply(model.t1(name, item, chain))
                recs.append({**build._record(run, name, item, chain, "t1", "t1", 1), **t1})
                if t1["status"] != "ok":
                    continue
                for arm, fields in build.turn2_arms(run, name, item, chain, nf_ids):
                    rep = _as_reply(model.t2(name, item, chain, arm, fields, t1["parsed"]))
                    recs.append({**build._record(run, name, item, chain, build.part_name(arm, fields),
                                                 "t2" if fields else "t2_nf", 2, arm, fields), **rep})
            if item["set"] in s["probe_sets"]:
                rep = _as_reply(model.probe(name, item))
                recs.append({**build._record(run, name, item, None, "probe", "probe", 1), **rep})
        out[name] = recs
    return out


def make_units(records_by_setting, run=RUN):
    """The records of each setting as a unit of pilot_report.make_unit."""
    return {name: pr.make_unit(run, name, Path("made_up"), recs) for name, recs in records_by_setting.items()}


def make_outcomes(items_by_set, seed=5, unresolved=0):
    """Made-up outcomes as {item ID: {"status", "y"}}. y is 1 with the probability that the made-up price gives,
    and the first `unresolved` items of each set have no outcome."""
    out = {}
    for s, items in items_by_set.items():
        r = random.Random(f"{seed}-{s}")
        for k, it in enumerate(sorted(items, key=lambda x: x["item_id"])):
            y = int(r.random() < it["q_pct"] / 100)
            out[it["item_id"]] = ({"status": "unresolved", "y": None} if k < unresolved
                                  else {"status": "resolved", "y": y})
    return out
