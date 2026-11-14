"""Item sets (PLAN 3.3): fetch, price, review, select and the trade-count check. Free public reads only.

Run with python3 -I, one stage at a time, in this order:
  python3 -I pipeline/fetch_items.py pilot fetch     # Gamma events whose scheduled end date is in W
  python3 -I pipeline/fetch_items.py pilot price     # CLOB hourly Yes price at F for every eligible market
  python3 -I pipeline/fetch_items.py pilot review    # counts and the decisions to make by hand
  (write data/items/pilot_by_hand.json from the review)
  python3 -I pipeline/fetch_items.py pilot select    # data/items/pilot_items.json
  python3 -I pipeline/fetch_items.py pilot trades    # trade counts before F for five pilot markets

Nothing here prints an outcome, a price after F or a withheld field. For a scored set the review shows only
the IDs and questions of markets with a deleted paragraph, never the deleted text, which may report events
after F.
"""
from __future__ import annotations

import argparse
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline import config  # noqa: E402
from pipeline import items as it  # noqa: E402
from pipeline import polymarket as pm  # noqa: E402
from pipeline.util import now_utc, read_json, sha256_file, write_json  # noqa: E402

BY_HAND_KEYS = ("families", "exclude", "ethics_readmit", "ethics_exclude_events", "note")


def earlier_event_ids(set_name):
    """Events of the sets selected before this one (PLAN 3.2 disjointness)."""
    ids = set()
    for s in config.SETS[set_name]["exclude_event_sets"]:
        p = config.ITEMS / f"{s}_event_ids.json"
        if not p.exists():
            sys.exit(f"{p.name} is missing: select the {s} set before the {set_name} set (PLAN 3.2).")
        ids |= {str(x) for x in read_json(p)["event_ids"]}
    return frozenset(ids)


def by_hand_path(set_name):
    return config.ITEMS / f"{set_name}_by_hand.json"


def load_by_hand(set_name, required):
    p = by_hand_path(set_name)
    if not p.exists():
        if required:
            sys.exit(f"{p.name} is missing. Run the review stage first and write the decisions made by hand "
                     f"there, with the keys {', '.join(BY_HAND_KEYS)} (empty values are allowed).")
        return {}
    data = read_json(p)
    unknown = set(data) - set(BY_HAND_KEYS)
    if unknown:
        sys.exit(f"{p.name} has unknown keys: {', '.join(sorted(unknown))}")
    return data


def eligible(set_name):
    events = pm.load_events(set_name)
    if not events:
        sys.exit(f"No fetched events for the {set_name} set; run the fetch stage first.")
    earlier = earlier_event_ids(set_name)
    elig, counts = it.eligible_markets(events, set_name, earlier)
    return events, earlier, elig, counts


def priced_pool(set_name, by_hand):
    events, earlier, elig, _ = eligible(set_name)
    prices = pm.load_prices(set_name, {info["yes_token"] for _, _, info in elig})
    try:
        return it.build_pool(events, prices, set_name, by_hand, earlier)
    except (RuntimeError, ValueError) as err:
        sys.exit(str(err))


def print_counts(counts):
    for k in sorted(counts, key=lambda k: (not k.startswith("event"), k)):
        print(f"  {counts[k]:>6}  {k}")


# ---------------------------------------------------------------- stages

def stage_fetch(set_name, refetch):
    try:
        res = pm.fetch_events(set_name, refetch=refetch)
    except pm.FetchDayError as err:
        sys.exit(str(err))
    print(f"{set_name}: {res['events_listed']} events listed over {res['days']} queries (one per UTC day "
          f"and closed state)")


def stage_price(set_name):
    _, _, elig, counts = eligible(set_name)
    tokens = {info["yes_token"] for _, _, info in elig}
    res = pm.fetch_prices(set_name, tokens)
    prices = pm.load_prices(set_name, tokens)
    have = sum(1 for p in prices.values() if "error" not in p and p["q"] is not None)
    none = sum(1 for p in prices.values() if "error" not in p and p["q"] is None)
    err = sum(1 for p in prices.values() if "error" in p)
    print("Rules 1 to 3 and 13:")
    print_counts(counts)
    print(f"Yes tokens of eligible markets {len(tokens)} (requested in this run {res['requested']}): "
          f"hourly price in the 24 hours before F {have}, no such price {none}, request errors {err}")
    if err:
        print("Run the price stage again to retry the errors; the select stage refuses while any remain.")


def stage_review(set_name):
    by_hand = load_by_hand(set_name, required=False)
    pool, counts, deleted, flagged = priced_pool(set_name, by_hand)
    print(f"Counts ({set_name}, by-hand file {'present' if by_hand else 'absent'}):")
    print_counts(counts)

    lo, hi = config.WIDE_BAND
    events = defaultdict(list)
    for c in pool:
        if lo <= c["q_pct"] <= hi:
            events[c["event_id"]].append(c)
    narrow = sum(1 for cs in events.values() for c in cs if config.BAND[0] <= c["q_pct"] <= config.BAND[1])
    print(f"\nEvents with a market in the wide band {len(events)}; markets in the narrow band {narrow}, "
          f"in the wide band {sum(len(v) for v in events.values())}")
    print("Events with a market in the wide band, by family (rule 7: one election day in one place is one "
          "family). Columns: event ID, markets in the narrow band, markets in the wide band, US office, title.")
    by_family = defaultdict(list)
    for eid, cs in events.items():
        by_family[cs[0]["family"]].append(eid)
    for f in sorted(by_family, key=lambda f: (-len(by_family[f]), f)):
        print(f"  [{len(by_family[f])}] {f}")
        for eid in sorted(by_family[f], key=lambda e: events[e][0]["event_title"]):
            cs = events[eid]
            n_narrow = sum(1 for c in cs if config.BAND[0] <= c["q_pct"] <= config.BAND[1])
            office = cs[0]["office"] or ""
            print(f"      {eid:>7}  {n_narrow:>2} {len(cs):>2}  {office:<8} {cs[0]['event_title']}")

    q_by_market = {c["market_id"]: c for c in pool}
    print(f"\nRule 11 pattern hits {len(flagged)} (excluded unless listed under ethics_readmit):")
    readmit = {str(k) for k in (by_hand.get("ethics_readmit") or {})}
    events_all = pm.load_events(set_name)
    by_mid = {str(m["id"]): (e, m) for e in events_all.values() for m in e.get("markets") or []}
    for mid in flagged:
        e, m = by_mid[mid]
        state = "re-admitted" if mid in readmit else "excluded"
        print(f"  {mid:>8}  {state:<11} {m.get('question')}  [event: {e.get('title')}]")
    hand_ethics = by_hand.get("ethics_exclude_events") or {}
    print(f"Rule 11 events excluded by hand {len(hand_ethics)} (ethics_exclude_events), with every market:")
    for eid, why in sorted(hand_ethics.items(), key=lambda kv: int(kv[0])):
        print(f"  {eid:>8}  {(events_all.get(str(eid)) or {}).get('title')}  ({why})")

    print(f"\nRule 6 deletions: {len(deleted)} markets with an appended Note, Update or Clarification paragraph.")
    for mid, paras in sorted(deleted.items(), key=lambda kv: int(kv[0])):
        c = q_by_market.get(mid)
        print(f"  {mid:>8}  {c['question'] if c else ''}")
        if set_name == "pilot":
            for p in paras:
                print("            deleted: " + p.replace("\n", " "))
    if set_name != "pilot" and deleted:
        print("  (The deleted text of a scored set is not shown; judge from the cleaned text alone whether "
              "the question can be answered without it.)")

    for band_name, band in (("narrow", config.BAND), ("wide", config.WIDE_BAND)):
        _, info = it.choose(pool, config.SETS[set_name]["seed"], config.SETS[set_name]["N"], band)
        print(f"\n{band_name} band {band}: picks {info['picks']} from {info['events_with_in_band_market']} "
              f"events in {info['families_available']} families; largest set under the 25% cap "
              f"{info['largest_n_under_cap']} (target {config.SETS[set_name]['N']})")


def stage_select(set_name):
    cfg = config.SETS[set_name]
    by_hand = load_by_hand(set_name, required=True)
    pool, counts, deleted, flagged = priced_pool(set_name, by_hand)
    items, log = it.select(pool, set_name)
    if not items:
        sys.exit("No item qualifies; nothing written.")

    outs = {
        "items": config.ITEMS / f"{set_name}_items.json",
        "event_ids": config.ITEMS / f"{set_name}_event_ids.json",
        "pool": config.ITEMS / f"{set_name}_pool.json.gz",
        "log": config.ITEMS / f"{set_name}_selection_log.json",
        "deleted": (config.ITEMS if set_name == "pilot" else config.OUTCOMES)
        / f"{set_name}_deleted_paragraphs.json",
    }
    for p in outs.values():
        pm.move_aside(p)

    created = now_utc()
    stamp = pm.fetch_stamp(set_name)
    write_json(outs["items"], {
        "set": set_name, "F": cfg["F"], "W": [list(w) for w in cfg["W"]], "seed": cfg["seed"], "created": created,
        "rule_version": config.RULE_VERSION, "mirror_rule": config.MIRROR_RULE, "fetched": stamp,
        "band": log["band_used"],
        "n_target": cfg["N"], "n": len(items), "items": items})
    write_json(outs["event_ids"], {"set": set_name, "created": created,
                                   "event_ids": sorted({c["event_id"] for c in items}, key=int)})
    write_json(outs["pool"], {"set": set_name, "created": created, "fetched": stamp,
                              "note": "every eligible market with an hourly price at F, before the band",
                              "markets": pool}, gz=True)
    write_json(outs["deleted"], {"set": set_name, "created": created, "paragraphs": deleted})

    us = [c for c in items if c["us"]]
    fam_counts = Counter(c["family"] for c in items)
    summary = {
        "n": len(items), "events": len({c["event_id"] for c in items}), "families": len(fam_counts),
        "largest_family": fam_counts.most_common(1)[0],
        "us_items": len(us), "us_offices": dict(Counter(c["office"] for c in us)),
        "mirror_items": sum(c["mirror"] for c in items),
        "mirror_pairs": len({c["event_id"] for c in items if c["mirror"]}),
        "ai_company_items": sum(c["ai_company"] for c in items),
        "in_narrow_band": sum(c["in_narrow_band"] for c in items),
        "description_from_event": sum(c["description_source"] == "event" for c in items),
        "with_deleted_paragraph": sum(c["n_deleted_paragraphs"] > 0 for c in items),
        "q_pct": {"min": min(c["q_pct"] for c in items), "median": statistics.median(c["q_pct"] for c in items),
                  "max": max(c["q_pct"] for c in items)},
        "t": {"all": dict(sorted(Counter(c["t"] for c in items).items()))},
    }
    for name, _ in cfg["subsets"]:
        summary["t"][name] = dict(sorted(Counter(c["t"] for c in items if name in c["subsets"]).items()))
    write_json(outs["log"], {
        "set": set_name, "created": created, "fetched": stamp, "rule_version": config.RULE_VERSION,
        "mirror_rule": config.MIRROR_RULE,
        "by_hand_sha256": sha256_file(by_hand_path(set_name)), "by_hand_counts":
            {k: len(by_hand.get(k) or {}) for k in ("families", "exclude", "ethics_readmit", "ethics_exclude_events")},
        "counts": dict(sorted(counts.items())), "rule11_pattern_hits": flagged,
        "rule6_markets_with_deleted_paragraph": sorted(deleted, key=int),
        "selection": log, "summary": summary})

    print(f"{set_name}: {len(items)} items from {summary['events']} events in {summary['families']} families "
          f"(largest {summary['largest_family'][0]!r} with {summary['largest_family'][1]}); band "
          f"{log['band_used']}; US items {summary['us_items']} {summary['us_offices']}")
    print(f"  passes {Counter(c['pass'] for c in items)}; mirror items {summary['mirror_items']} in {summary['mirror_pairs']} pairs; "
          f"AI-company items {summary['ai_company_items']}; q_pct {summary['q_pct']}")
    print(f"  t per subset {summary['t']}")
    for k, p in outs.items():
        print(f"  wrote {p.relative_to(config.ROOT)}")


def stage_trades(set_name):
    if set_name != "pilot":
        sys.exit("The trade-count check runs on the pilot only (PLAN 3.3 rule 4 CHECK).")
    data = read_json(config.ITEMS / "pilot_items.json")
    seed = config.SETS["pilot"]["seed"]
    picks = sorted(data["items"], key=lambda c: it.hkey(seed, "trade-check", c["market_id"]))[:5]
    f_unix = config.f_unix("pilot")
    out = []
    for c in picks:
        r = pm.trade_count(c["condition_id"], f_unix)
        r = {"item_id": c["item_id"], "market_id": c["market_id"], **r}
        out.append(r)
        print(f"  {c['item_id']}  trades seen {r.get('trades_seen')}, at or before F "
              f"{r.get('trades_at_or_before_F')}, reached the first trade {r.get('reached_first_trade')}, "
              f"pages {r.get('page_sizes')}, oldest {r.get('oldest_seen')}, error {r.get('error')}")
    path = config.ITEMS / "pilot_trade_check.json"
    pm.move_aside(path)
    write_json(path, {"created": now_utc(), "F": config.SETS["pilot"]["F"],
                      "note": "Counts only. No trade row, wallet, name, side, size or price is stored.",
                      "markets": out})
    print(f"  wrote {path.relative_to(config.ROOT)}")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("set", choices=sorted(config.SETS))
    ap.add_argument("stage", choices=("fetch", "price", "review", "select", "trades"))
    ap.add_argument("--refetch", action="store_true",
                    help="move an earlier fetch of this set aside and fetch again (fetch stage only)")
    a = ap.parse_args(argv)
    if a.stage == "fetch":
        stage_fetch(a.set, a.refetch)
    elif a.stage == "price":
        stage_price(a.set)
    elif a.stage == "review":
        stage_review(a.set)
    elif a.stage == "select":
        stage_select(a.set)
    else:
        stage_trades(a.set)


if __name__ == "__main__":
    main()
