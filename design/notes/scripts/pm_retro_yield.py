"""Count retro-window Polymarket items under the open-at-F rule. Counts only, no outcomes.

Usage: python3 -I pm_retro_yield.py <polymarket_dir> <F iso> <end_min YYYY-MM-DD> <end_max YYYY-MM-DD>

Reads the saved tier_one event pages (closed events, Sports/Crypto/Esports/Recurring
excluded, event volume >= 10k at fetch time). Applies the design rule: Yes/No market,
trading start at or before F, closedTime after F, market endDate inside the window.
Drops series events and template-tag events (the agent's list plus the tags it missed).
Never prints which way any market resolved.
"""
import collections
import datetime as dt
import glob
import gzip
import json
import os
import sys

TEMPLATE_TAGS = {"Tweet Markets", "Finance Updown", "Pyth Finance", "Hide From New", "Recurring",
                 "Up or Down", "Daily", "Weekly", "Mention Markets", "Mentions", "Daily Close",
                 "Daily-Close", "Hit Price", "Equity Daily Pyth", "Monthly"}


def ts(s):
    if not s:
        return None
    s = s.replace(" ", "T").replace("+00:00:00", "+00:00")
    if s.endswith("+00"):
        s += ":00"
    s = s.replace("Z", "+00:00")
    return dt.datetime.fromisoformat(s)


def jl(s):
    if isinstance(s, list):
        return s
    try:
        return json.loads(s)
    except Exception:
        return None


def main():
    pdir, f_iso, lo, hi = sys.argv[1:5]
    F = ts(f_iso)
    evs = {}
    for p in sorted(glob.glob(os.path.join(pdir, "tier_one_events", "*.json.gz"))):
        if lo <= os.path.basename(p)[:10] <= hi:
            for e in json.load(gzip.open(p)).get("data") or []:
                evs[e["id"]] = e
    print(f"events loaded (event end date {lo} to {hi}): {len(evs)}")
    ser = {k for k, e in evs.items() if e.get("seriesSlug") or e.get("series")}
    tmpl = {k for k, e in evs.items() if {t.get("label") for t in (e.get("tags") or [])} & TEMPLATE_TAGS}
    print(f"dropped: series {len(ser)}, template tag {len(tmpl)}, either {len(ser | tmpl)}")
    per_event, why = {}, collections.Counter()
    for k, e in evs.items():
        if k in ser or k in tmpl:
            continue
        keep = []
        for m in e.get("markets") or []:
            if jl(m.get("outcomes")) != ["Yes", "No"]:
                why["not Yes/No"] += 1
                continue
            start = ts(m.get("startDate") or m.get("acceptingOrdersTimestamp") or m.get("createdAt"))
            closed, end = ts(m.get("closedTime")), ts(m.get("endDate"))
            if not (start and closed and end):
                why["missing time field"] += 1
                continue
            if start > F:
                why["opened after F"] += 1
                continue
            if closed <= F:
                why["closed at or before F"] += 1
                continue
            if not (lo <= end.date().isoformat() <= hi):
                why["market endDate outside window"] += 1
                continue
            keep.append(m)
        if keep:
            per_event[k] = keep
    print("markets dropped, by first failed rule:", dict(why))
    ms = [m for v in per_event.values() for m in v]
    clean = [m for m in ms if sorted(str(x) for x in (jl(m.get("outcomePrices")) or [])) == ["0", "1"]]
    print(f"qualifying: {len(per_event)} events, {len(ms)} markets; resolved cleanly (0/1 prices): {len(clean)}")
    capped = sum(min(3, len(v)) for v in per_event.values())
    print(f"after a cap of 3 markets per event: {capped} items (cap 2: {sum(min(2, len(v)) for v in per_event.values())}, cap 1: {len(per_event)})")
    print("markets per event:", dict(sorted(collections.Counter(min(len(v), 10) for v in per_event.values()).items())), "(10 = 10 or more)")
    print("negRisk markets:", sum(bool(m.get("negRisk")) for m in ms), "of", len(ms))
    early = sum(ts(m["closedTime"]) < ts(m["endDate"]) for m in ms)
    print("closed before scheduled end (early closes, kept by the rule):", early)
    horizon = sorted((ts(m["endDate"]) - F).days for m in ms)
    print("days from F to scheduled end, quartiles:", [horizon[int(q * (len(horizon) - 1))] for q in (0, .25, .5, .75, 1)])
    age = sorted((F - ts(m.get("startDate") or m.get("acceptingOrdersTimestamp") or m["createdAt"])).days for m in ms)
    print("market age at F in days, quartiles:", [age[int(q * (len(age) - 1))] for q in (0, .25, .5, .75, 1)])
    byday = collections.Counter(ts(m["endDate"]).date().isoformat() for m in ms)
    evday = collections.Counter(min(ts(m["endDate"]).date().isoformat() for m in v) for v in per_event.values())
    print("by scheduled end day (markets / events):")
    for d in sorted(byday):
        print(f"  {d}: {byday[d]:4d} / {evday.get(d, 0):3d}")
    tags = collections.Counter(t.get("label") for k in per_event for t in (evs[k].get("tags") or []))
    print("top event tags:", tags.most_common(25))


if __name__ == "__main__":
    main()
