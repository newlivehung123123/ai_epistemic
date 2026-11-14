"""Top tags and sample titles for one family in a candidates file. No outcomes.

Usage: python3 -I pm_family_tags.py <window_dir> <candidates_json> <family> <end_min> <end_max>
"""
import collections
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import json  # noqa: E402
from pm_window_yield import load  # noqa: E402

wdir, cand, fam, lo, hi = sys.argv[1:6]
evs = load(wdir, lo, hi)
rows = json.load(open(cand))[fam]
tags = collections.Counter(t.get("label") for k in rows for t in (evs[k].get("tags") or []))
print(f"{fam}: {len(rows)} events; top tags:", tags.most_common(40))
for k in sorted(rows, key=lambda k: evs[k].get("endDate") or "")[:400:6]:
    print(f"  {(evs[k].get('endDate') or '')[:10]}  {evs[k].get('title')}  [{len(rows[k])}]")
