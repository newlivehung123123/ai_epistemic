"""Print title, end date and tags of the candidate events in one coarse family. No prices, no outcomes.

Usage: python3 -I pm_event_titles.py <window_dir> <candidates_json> <family> <end_min> <end_max>
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import json  # noqa: E402
from pm_window_yield import load  # noqa: E402

GENERIC = {"Politics", "Elections", "World", "Global Elections", "World Elections", "All", "Featured", "Trending"}


def main():
    wdir, cand, fam, lo, hi = sys.argv[1:6]
    evs = load(wdir, lo, hi)
    rows = json.load(open(cand))[fam]
    for k in sorted(rows, key=lambda k: (evs[k].get("endDate") or "", evs[k].get("title") or "")):
        e = evs[k]
        tags = sorted({t.get("label") or "" for t in (e.get("tags") or [])} - GENERIC)
        print(f"{(e.get('endDate') or '')[:10]} | {e.get('title')} | n={len(rows[k])} | {', '.join(tags)[:150]}")


if __name__ == "__main__":
    main()
