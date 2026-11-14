"""Check tier_one page event counts for given days and summarise saved CLOB price-history files.

Run with python3 -I. Usage: python3 -I pm_check_days.py <polymarket_dir> <day,day,...>
"""
import datetime
import glob
import gzip
import json
import os
import sys

pdir, days = sys.argv[1], sys.argv[2].split(",")
for d in days:
    n = sum(len(json.load(gzip.open(p)).get("data") or []) for p in glob.glob(os.path.join(pdir, "tier_one_events", d + "_off*.json.gz")))
    pg = json.load(gzip.open(os.path.join(pdir, "daily_counts", d + "_tier_one.json.gz"))).get("pagination")
    print(d, "events in full pages:", n, "| limit=1 pagination:", pg)
for p in sorted(glob.glob(os.path.join(pdir, "clob_prices_history_*.json"))):
    h = json.load(open(p)).get("history") or []
    ts = [x.get("t") for x in h if isinstance(x, dict)]
    rng = (datetime.datetime.fromtimestamp(min(ts), datetime.timezone.utc).date(), datetime.datetime.fromtimestamp(max(ts), datetime.timezone.utc).date()) if ts else None
    print(os.path.basename(p), "points:", len(h), "range:", rng, "first:", h[:1], "last:", h[-1:])
