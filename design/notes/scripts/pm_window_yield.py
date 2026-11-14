"""Count Polymarket items under the open-at-F rule, open and closed events. Counts only.

Usage: python3 -I pm_window_yield.py <window_dir> <F iso> <end_min YYYY-MM-DD> <end_max YYYY-MM-DD>

Reads <window_dir>/closed_true and <window_dir>/closed_false (pm_fetch_window.py).
A market qualifies if it is Yes/No, trading started at or before F, it was still
open at F (closedTime after F, or not closed yet on the fetch day) and its
scheduled end (endDate) falls inside the window. Never prints outcomes.
Yields are shown under two event rules: series and template-tag events dropped
(the 31 Oct rule), and template-tag events dropped only.
"""
import collections
import glob
import gzip
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pm_retro_yield import TEMPLATE_TAGS, jl, ts  # noqa: E402

ELECTION = re.compile(r"midterm|senate|house|governor|congress|election|primary|mayor|attorney general|secretary of state", re.I)


def load(window_dir, lo, hi):
    evs = {}
    for sub in ("closed_true", "closed_false"):
        for p in sorted(glob.glob(os.path.join(window_dir, sub, "*.json.gz"))):
            if lo <= os.path.basename(p)[:10] <= hi:
                for e in json.load(gzip.open(p)).get("data") or []:
                    evs[e["id"]] = e
    return evs


def qualifying(evs, F, lo, hi, drop, why):
    per_event = {}
    for k, e in evs.items():
        if k in drop:
            continue
        keep = []
        for m in e.get("markets") or []:
            if jl(m.get("outcomes")) != ["Yes", "No"]:
                why["not Yes/No"] += 1
                continue
            start = ts(m.get("startDate") or m.get("acceptingOrdersTimestamp") or m.get("createdAt"))
            end = ts(m.get("endDate"))
            closed = ts(m.get("closedTime"))
            still_open = closed is None and m.get("closed") is False
            if not (start and end and (closed or still_open)):
                why["missing time field"] += 1
                continue
            if start > F:
                why["opened after F"] += 1
                continue
            if closed and closed <= F:
                why["closed at or before F"] += 1
                continue
            if not (lo <= end.date().isoformat() <= hi):
                why["market endDate outside window"] += 1
                continue
            keep.append(m)
        if keep:
            per_event[k] = keep
    return per_event


def report(label, per_event, evs):
    ms = [m for v in per_event.values() for m in v]
    cap3 = sum(min(3, len(v)) for v in per_event.values())
    print(f"{label}: {len(per_event)} events, {len(ms)} markets; cap 3 per event {cap3} items, "
          f"cap 2 {sum(min(2, len(v)) for v in per_event.values())}, cap 1 {len(per_event)}")
    still = sum(m.get("closed") is False for m in ms)
    print(f"  markets not yet closed on the fetch day: {still} of {len(ms)}")
    elec = {k for k in per_event if ELECTION.search(evs[k].get("title") or "")
            or any(ELECTION.search(t.get("label") or "") for t in (evs[k].get("tags") or []))}
    e3 = sum(min(3, len(per_event[k])) for k in elec)
    print(f"  election events (title or tag): {len(elec)} events, {e3} of {cap3} cap-3 items")
    by_month = collections.Counter()
    for k, v in per_event.items():
        by_month[min(ts(m["endDate"]).date().isoformat() for m in v)[:7]] += min(3, len(v))
    print("  cap-3 items by month of scheduled end:", dict(sorted(by_month.items())))
    return elec


def main():
    wdir, f_iso, lo, hi = sys.argv[1:5]
    F = ts(f_iso)
    evs = load(wdir, lo, hi)
    print(f"events loaded (event end date {lo} to {hi}): {len(evs)}")
    ser = {k for k, e in evs.items() if e.get("seriesSlug") or e.get("series")}
    tmpl = {k for k, e in evs.items() if {t.get("label") for t in (e.get("tags") or [])} & TEMPLATE_TAGS}
    print(f"flagged: series {len(ser)}, template tag {len(tmpl)}, either {len(ser | tmpl)}")
    why = collections.Counter()
    strict = qualifying(evs, F, lo, hi, ser | tmpl, why)
    print("markets dropped under the 31 Oct rule, by first failed rule:", dict(why))
    elec = report("31 Oct rule (series and template dropped)", strict, evs)
    loose = qualifying(evs, F, lo, hi, tmpl, collections.Counter())
    report("template tags dropped only", loose, evs)
    tags = collections.Counter(t.get("label") for k in strict for t in (evs[k].get("tags") or []))
    print("top event tags, 31 Oct rule:", tags.most_common(30))
    non = [k for k in strict if k not in elec]
    print("non-election event titles, 31 Oct rule (first 40):")
    for k in sorted(non, key=lambda k: evs[k].get("endDate") or "")[:40]:
        print(f"  {(evs[k].get('endDate') or '')[:10]}  {evs[k].get('title')}  [{len(strict[k])} markets]")


if __name__ == "__main__":
    main()
