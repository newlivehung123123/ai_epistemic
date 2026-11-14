"""Fetch Polymarket gamma API data for the 1 Jun to 31 Oct 2026 window.

Run with python3 -I. Writes gzipped raw responses under the output folder.
Usage: python3 -I pm_fetch.py <out_dir> <start YYYY-MM-DD> <end YYYY-MM-DD>

Per day (event end date in that UTC day):
  tier_all  : closed events, no other filter              (limit=1, count only)
  tier_nsc  : excluding tags Sports(1), Crypto(21), Esports(64)
  tier_vol  : tier_nsc plus event volume_min=10000
  tier_one  : tier_vol plus excluding tag Recurring(101757)
The full event pages (with nested markets) are saved for tier_one only.
The API's totalResults is exact for one-day windows; if it looks capped
(totalResults == limit + 1) the day is flagged.
"""
import datetime
import gzip
import json
import os
import sys
import time
import urllib.request

BASE = "https://gamma-api.polymarket.com/events/pagination"
TIERS = {
    "tier_all": "",
    "tier_nsc": "&exclude_tag_id=1&exclude_tag_id=21&exclude_tag_id=64",
    "tier_vol": "&exclude_tag_id=1&exclude_tag_id=21&exclude_tag_id=64&volume_min=10000",
    "tier_one": "&exclude_tag_id=1&exclude_tag_id=21&exclude_tag_id=64&exclude_tag_id=101757&volume_min=10000",
}


def get(url):
    for attempt in range(5):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "research-count/0.1"})
            with urllib.request.urlopen(req, timeout=60) as r:
                return r.read()
        except Exception as e:  # retry on transient errors
            time.sleep(2 + attempt * 3)
            last = e
    raise last


def main():
    out, start, end = sys.argv[1], sys.argv[2], sys.argv[3]
    os.makedirs(os.path.join(out, "daily_counts"), exist_ok=True)
    os.makedirs(os.path.join(out, "tier_one_events"), exist_ok=True)
    d = datetime.date.fromisoformat(start)
    stop = datetime.date.fromisoformat(end)
    summary = {}
    while d <= stop:
        win = f"closed=true&end_date_min={d}T00:00:00Z&end_date_max={d}T23:59:59.999Z"
        row = {}
        for tier, extra in TIERS.items():
            raw = get(f"{BASE}?{win}&limit=1{extra}")
            with gzip.open(os.path.join(out, "daily_counts", f"{d}_{tier}.json.gz"), "wb") as fh:
                fh.write(raw)
            pg = json.loads(raw).get("pagination") or {}
            row[tier] = pg.get("totalResults")
            row[tier + "_hasMore"] = pg.get("hasMore")
            time.sleep(0.12)
        # full pages for tier_one
        offset = 0
        while True:
            raw = get(f"{BASE}?{win}&limit=100&offset={offset}{TIERS['tier_one']}")
            with gzip.open(os.path.join(out, "tier_one_events", f"{d}_off{offset}.json.gz"), "wb") as fh:
                fh.write(raw)
            data = json.loads(raw).get("data") or []
            time.sleep(0.12)
            if len(data) < 100:
                break
            offset += 100
        summary[str(d)] = row
        print(d, row, flush=True)
        d += datetime.timedelta(days=1)
    with open(os.path.join(out, "daily_counts_summary.json"), "w") as fh:
        json.dump(summary, fh, indent=1)


if __name__ == "__main__":
    main()
