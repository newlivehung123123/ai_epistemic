"""PLAN 3.3 item rule as pure functions on Gamma events that hold only the kept fields.

Rule numbers in the comments are those of PLAN 3.3. Every random draw uses a seeded hash key, so the order of
an event or market never changes when another event or market is added or removed (for example by a by-hand
exclusion), and the draws do not depend on the order of the fetched pages.
"""
from __future__ import annotations

import hashlib
import math
import re
from collections import Counter, defaultdict
from decimal import ROUND_HALF_UP, Decimal
from fractions import Fraction

from pipeline import config
from pipeline import families as fam
from pipeline.util import UTC, jl, ts

# Rule 6: an appended paragraph headed Note, Update or Clarification.
APPENDED_HEADER = re.compile(r"^\s*(notes?|updates?|updated|clarifications?)\b\s*(\(|\[|:|-|–|—|on\b|\d)",
                             re.I)
# Rule 11: candidate markets on the death or health of a named person, checked by hand afterwards.
ETHICS = re.compile(r"\b(die|dies|died|death|dead|alive|pass(es)? away|passed away|assassinat\w*|killed|"
                    r"hospitali[sz]\w*|health|illness|cancer|coma|stroke|heart attack|incapacitat\w*)\b", re.I)

PREFIX = {"pilot": "pil", "retro": "ret", "prospective": "pro"}

ITEM_FIELDS = ("item_id", "set", "event_id", "event_title", "event_slug", "tags", "neg_risk", "n_markets", "n_priced",
               "market_id", "condition_id", "question", "description", "description_source",
               "n_deleted_paragraphs", "start", "end_time", "end_date", "yes_token", "q", "q_pct", "q_time",
               "q_points", "in_narrow_band", "family", "coarse_family", "us", "office", "ai_company", "mirror",
               "pass", "event_rank", "subsets", "t")


def hkey(*parts) -> str:
    """Seeded random key. Sorting by it gives a seeded random order."""
    return hashlib.sha256("|".join(str(p) for p in parts).encode("utf-8")).hexdigest()


def q_percent(q) -> int:
    """PLAN 4.3: q rounded half up to a whole percent; the rounded value is used everywhere."""
    return int((Decimal(str(q)) * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def utc_date(d) -> str:
    return d.astimezone(UTC).date().isoformat()


def in_window(day: str, w) -> bool:
    return w[0] <= day <= w[1]


def in_windows(day: str, ws) -> bool:
    """True when the day falls in any window of ws (the W of a set is a tuple of windows, PLAN 3.2)."""
    return any(in_window(day, w) for w in ws)


def yes_token(m):
    toks = jl(m.get("clobTokenIds")) or []
    return str(toks[0]) if toks else None


def event_exclusion(e, cfg, earlier_event_ids=frozenset()):
    """Rules 1, 2 and 13 at the event level. Returns the reason or None."""
    if {str(t.get("id")) for t in (e.get("tags") or [])} & set(config.EXCLUDE_TAG_IDS):
        return "sports, crypto, esports or recurring tag (rule 1)"
    if str(e["id"]) in earlier_event_ids:
        return "event in an earlier set (rule 13)"
    if fam.series(e):
        return "series event (rule 2)"
    if fam.template(e):
        return "template tag (rule 2)"
    if fam.derived(e):
        return "secondary event (rule 2)"
    for m in e.get("markets") or []:
        end = ts(m.get("endDate"))
        if end and in_windows(utc_date(end), cfg["forbidden_windows"]):
            return "a market ends in the retro or prospective window (rule 13)"
    return None


def market_exclusion(m, F, W, open_at_fetch):
    """Rule 3 (notes/scripts/pm_window_yield.py, unchanged), plus PLAN 4.6 for the pilot: open at the fetch."""
    if jl(m.get("outcomes")) != ["Yes", "No"]:
        return "not Yes/No", None
    start = ts(m.get("startDate") or m.get("acceptingOrdersTimestamp") or m.get("createdAt"))
    end = ts(m.get("endDate"))
    closed = ts(m.get("closedTime"))
    still_open = closed is None and m.get("closed") is False
    if not (start and end and (closed or still_open)):
        return "missing time field", None
    if start > F:
        return "opened after F", None
    if closed and closed <= F:
        return "closed at or before F", None
    if not in_windows(utc_date(end), W):
        return "market endDate outside window", None
    if open_at_fetch and m.get("closed") is not False:
        return "closed at the pilot fetch", None
    return None, {"start": start.isoformat(), "end_time": end.astimezone(UTC).isoformat(), "end_date": utc_date(end)}


def clean_description(text):
    """Rule 6: delete each appended paragraph headed Note, Update or Clarification; no truncation."""
    parts = re.split(r"(\n+)", (text or "").strip())
    kept, deleted = [parts[0]], []
    for i in range(1, len(parts) - 1, 2):
        sep, para = parts[i], parts[i + 1]
        if APPENDED_HEADER.match(para):
            deleted.append(para)
        else:
            kept += [sep, para]
    return "".join(kept).strip(), deleted


def eligible_markets(events, set_name, earlier_event_ids=frozenset()):
    """Rules 1 to 3 and 13. Returns [(event, market, info)] and the reasons counted."""
    cfg = config.SETS[set_name]
    F = config.f_datetime(set_name)
    counts = Counter()
    out = []
    for eid in sorted(events, key=int):
        e = events[eid]
        why = event_exclusion(e, cfg, earlier_event_ids)
        if why:
            counts["event excluded: " + why] += 1
            continue
        counts["event kept"] += 1
        for m in e.get("markets") or []:
            why, info = market_exclusion(m, F, cfg["W"], cfg["open_at_fetch"])
            if why:
                counts["market excluded: " + why] += 1
                continue
            tok = yes_token(m)
            if not tok:
                counts["market excluded: no Yes token"] += 1
                continue
            counts["market eligible"] += 1
            out.append((e, m, {**info, "yes_token": tok}))
    return out, counts


def ethics_flag(e, m) -> bool:
    return bool(ETHICS.search(m.get("question") or "") or ETHICS.search(e.get("title") or ""))


def build_pool(events, prices, set_name, by_hand=None, earlier_event_ids=frozenset()):
    """Every eligible market with a price at F, its cleaned text and its family.

    by_hand holds the decisions made by reading items: "families" (event ID to family, rule 7), "exclude"
    (market ID to reason, rule 6: the question cannot be answered without the deleted paragraph) and
    "ethics_readmit" (market ID to reason: flagged by the rule 11 pattern but not about the death or health
    of a named person) and "ethics_exclude_events" (event ID to reason, rule 11: every market of the event
    concerns the death or health of a named person, in words the pattern misses). An ID that names no fetched
    event or market is refused, so that a mistyped ID cannot pass unnoticed.
    """
    by_hand = by_hand or {}
    hand_family = {str(k): v for k, v in (by_hand.get("families") or {}).items()}
    hand_exclude = {str(k) for k in (by_hand.get("exclude") or {})}
    readmit = {str(k) for k in (by_hand.get("ethics_readmit") or {})}
    hand_ethics = {str(k) for k in (by_hand.get("ethics_exclude_events") or {})}
    known_events = {str(k) for k in events}
    known_markets = {str(m["id"]) for e in events.values() for m in e.get("markets") or []}
    unknown = sorted((set(hand_family) | hand_ethics) - known_events) + sorted((hand_exclude | readmit) - known_markets)
    if unknown:
        raise ValueError(f"the by-hand file names IDs that match no fetched event or market: {', '.join(unknown)}")
    elig, counts = eligible_markets(events, set_name, earlier_event_ids)
    pool, deleted, flagged = [], {}, []
    missing = [str(m["id"]) for _, m, info in elig if info["yes_token"] not in prices
               or "error" in prices[info["yes_token"]]]
    if missing:
        raise RuntimeError(f"{len(missing)} eligible markets have no price response; run the price stage again")
    # PLAN 6.8: the eligible markets of each event with a price at F (rule 4), counted before any later rule
    # removes a market from the pool
    n_priced = Counter(str(e["id"]) for e, _, info in elig if prices[info["yes_token"]]["q"] is not None)
    for e, m, info in elig:
        mid, eid = str(m["id"]), str(e["id"])
        pr = prices[info["yes_token"]]
        if pr["q"] is None:
            counts["market excluded: no hourly price in the 24 hours before F (rule 4)"] += 1
            continue
        if mid in hand_exclude:
            counts["market excluded: by hand (rule 6)"] += 1
            continue
        if eid in hand_ethics:
            counts["market excluded: by hand, death or health of a named person (rule 11)"] += 1
            continue
        if ethics_flag(e, m):
            flagged.append(mid)
            if mid not in readmit:
                counts["market excluded: death or health pattern, not re-admitted (rule 11)"] += 1
                continue
        desc, gone = clean_description(m.get("description"))
        source = "market"
        if not desc:
            desc, gone = clean_description(e.get("description"))
            source = "event"
        if not desc:
            counts["market excluded: no description"] += 1
            continue
        if gone:
            deleted[mid] = gone
        coarse = fam.coarse_family(e)
        family = hand_family.get(eid) or fam.fine_family(e, coarse)
        us = family == fam.US
        pool.append({
            "event_id": eid, "event_title": e.get("title") or "", "event_slug": e.get("slug"),
            "tags": sorted(fam.labels(e) - {""}), "neg_risk": bool(e.get("negRisk")),
            "n_markets": len(e.get("markets") or []), "n_priced": n_priced[eid],
            "market_id": mid, "condition_id": m.get("conditionId"), "question": m.get("question") or "",
            "description": desc, "description_source": source, "n_deleted_paragraphs": len(gone),
            "start": info["start"], "end_time": info["end_time"], "end_date": info["end_date"],
            "yes_token": info["yes_token"], "q": pr["q"], "q_pct": q_percent(pr["q"]),
            "q_time": pr["t"], "q_points": pr["n_points"],
            "family": family, "coarse_family": coarse, "us": us, "office": fam.office(e) if us else None,
            "ai_company": coarse == "ai_companies",
        })
        counts["market priced and kept"] += 1
    return pool, counts, deleted, flagged


# ---------------------------------------------------------------- rule 8 quota

def largest_n(avail: dict, cap: float) -> int:
    """Largest N with sum over families of min(available, floor(cap N)) at least N."""
    c = Fraction(str(cap))
    total = sum(avail.values())
    for n in range(total, 0, -1):
        if sum(min(a, math.floor(c * n)) for a in avail.values()) >= n:
            return n
    return 0


def allocate(avail: dict, n: int, cap: float, seed: int) -> dict:
    """Items per family: shares proportional to availability, capped at floor(cap N) and at availability,
    then whole numbers by largest remainder with a seeded tie-break."""
    capn = math.floor(Fraction(str(cap)) * n)
    upper = {f: min(a, capn) for f, a in avail.items()}
    if sum(upper.values()) < n:
        raise ValueError("the family cap does not allow this many items")
    capped = set()
    while True:
        free = [f for f in upper if f not in capped]
        rest = n - sum(upper[f] for f in capped)
        tot = sum(avail[f] for f in free)
        k = Fraction(rest, tot) if tot else Fraction(0)
        over = [f for f in free if k * avail[f] > upper[f]]
        if not over:
            break
        capped.update(over)
    share = {f: Fraction(upper[f]) if f in capped else k * avail[f] for f in upper}
    alloc = {f: math.floor(s) for f, s in share.items()}
    left = n - sum(alloc.values())
    for f in sorted(upper, key=lambda f: (-(share[f] - alloc[f]), hkey(seed, "allocation", f)))[:left]:
        alloc[f] += 1
    return {f: v for f, v in alloc.items() if v}


def take_by_office(members: list, k: int, seed: int) -> list:
    """US items stratified by office: a proportional split by largest remainder, then event order."""
    if k >= len(members):
        return list(members)
    by_office = defaultdict(list)
    for c in members:
        by_office[c["office"]].append(c)
    share = {o: Fraction(k * len(v), len(members)) for o, v in by_office.items()}
    alloc = {o: math.floor(s) for o, s in share.items()}
    left = k - sum(alloc.values())
    for o in sorted(by_office, key=lambda o: (-(share[o] - alloc[o]), hkey(seed, "office", o)))[:left]:
        alloc[o] += 1
    out = []
    for o, v in by_office.items():
        out += v[:alloc[o]]
    return out


def choose(pool, seed, target, band, cap=config.FAMILY_CAP, passes=config.MAX_PASSES):
    """Rule 8. Events in a seeded order; in each pass every event gives one in-band market not yet taken,
    picked in a seeded order, for up to three passes, and a US event gives one market only. The set is then
    sampled to the target, stratified by family under the cap. Within a family items are taken in pass order
    and, within a pass, in the event order, so an event gives a second market only after every event of its
    family has given one."""
    lo, hi = band
    by_event = defaultdict(list)
    for c in pool:
        if lo <= c["q_pct"] <= hi:
            by_event[c["event_id"]].append(c)
    order = sorted(by_event, key=lambda e: hkey(seed, "event-order", e))
    rank = {e: i + 1 for i, e in enumerate(order)}
    for e in order:
        by_event[e].sort(key=lambda c: hkey(seed, "market-order", c["market_id"]))
    picks = []
    for p in range(1, passes + 1):
        for e in order:
            ms = by_event[e]
            if p <= len(ms) and (p == 1 or not ms[0]["us"]):
                picks.append({**ms[p - 1], "pass": p, "event_rank": rank[e]})
    avail = Counter(c["family"] for c in picks)
    n_max = largest_n(avail, cap)
    n = min(target, n_max)
    alloc = allocate(avail, n, cap, seed) if n else {}
    chosen = []
    for f in sorted(alloc):
        members = sorted((c for c in picks if c["family"] == f), key=lambda c: (c["pass"], c["event_rank"]))
        chosen += take_by_office(members, alloc[f], seed) if f == fam.US else members[:alloc[f]]
    info = {"band": list(band), "in_band_markets": sum(len(v) for v in by_event.values()),
            "events_with_in_band_market": len(order), "picks": len(picks),
            "picks_by_pass": dict(sorted(Counter(c["pass"] for c in picks).items())),
            "largest_n_under_cap": n_max, "n": n, "families_available": len(avail),
            "largest_family_share_of_picks": round(max(avail.values()) / len(picks), 3) if picks else None,
            "allocation": dict(sorted(alloc.items(), key=lambda kv: (-kv[1], kv[0])))}
    return chosen, info


def finish(chosen, set_name, seed, narrow_band=config.BAND):
    """Item IDs in a seeded order, nested pilot subsets, the cost-loss threshold t and the mirror flag."""
    cfg = config.SETS[set_name]
    items = sorted(chosen, key=lambda c: hkey(seed, "item-order", c["market_id"]))
    n = len(items)
    for i, c in enumerate(items):
        c["item_id"] = f"{PREFIX[set_name]}{i + 1:03d}"
        c["set"] = set_name
        c["subsets"] = [name for name, size in cfg["subsets"] if i < size]
        c["in_narrow_band"] = narrow_band[0] <= c["q_pct"] <= narrow_band[1]
    # Each block between subset edges cycles through the five t values in a seeded order, so every subset
    # holds the five values in equal numbers when its size is a multiple of five (PLAN 4.2).
    edges = sorted({0, n} | {min(size, n) for _, size in cfg["subsets"]})
    for a, b in zip(edges, edges[1:]):
        block = sorted(items[a:b], key=lambda c: hkey(seed, "threshold", c["market_id"]))
        for j, c in enumerate(block):
            c["t"] = config.T_VALUES[j % len(config.T_VALUES)]
    pairs = mirror_events(items)
    for c in items:
        c["mirror"] = c["event_id"] in pairs
    return [{k: c.get(k) for k in ITEM_FIELDS} for c in items]


def mirror_events(items) -> set:
    """PLAN 6.8, DECIDED by Jason Hung on 11 November 2026: two items of one negRisk event whose title names an
    election form a mirror pair when no other market of the event has a price at F (rule 4) and the two prices at
    F sum to at least config.MIRROR_MIN_SUM points. Polymarket lists placeholder markets beside the two candidates
    of a race, and a placeholder has no price at F. Returns the event IDs of the pairs."""
    by_event = defaultdict(list)
    for c in items:
        by_event[c["event_id"]].append(c)
    return {eid for eid, cs in by_event.items()
            if len(cs) == 2 and cs[0].get("neg_risk") and fam.ELECTION.search(cs[0].get("event_title") or "")
            and cs[0].get("n_priced") == 2 and cs[0]["q_pct"] + cs[1]["q_pct"] >= config.MIRROR_MIN_SUM}


def select(pool, set_name):
    """Rules 5 and 8: the narrow band first, the wide band only if the narrow band allows fewer than the
    target. Returns the items and a log of counts."""
    cfg = config.SETS[set_name]
    chosen, info = choose(pool, cfg["seed"], cfg["N"], config.BAND)
    log = {"narrow": info}
    band = config.BAND
    if info["largest_n_under_cap"] < cfg["N"]:
        chosen_w, info_w = choose(pool, cfg["seed"], cfg["N"], config.WIDE_BAND)
        log["wide"] = info_w
        if info_w["n"] > info["n"]:
            chosen, info, band = chosen_w, info_w, config.WIDE_BAND
    log["band_used"] = list(band)
    items = finish(chosen, set_name, cfg["seed"])
    return items, log
