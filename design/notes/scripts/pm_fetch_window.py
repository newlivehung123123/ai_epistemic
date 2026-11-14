"""Fetch Polymarket events, open and closed, whose end date falls in a window.

Run with python3 -I. Public Gamma reads, no key. Writes gzipped raw pages only.
Usage: python3 -I pm_fetch_window.py <out_dir> <start YYYY-MM-DD> <end YYYY-MM-DD>

Same filter as tier_one in pm_fetch.py (Sports, Crypto, Esports and Recurring
tags excluded, event volume at least 10k at fetch time), run once with
closed=true and once with closed=false, so events still open on the fetch day
are counted as well. The 31 Oct fetch saved closed events only.
"""
import datetime
import gzip
import json
import os
import sys
import time
import urllib.request

BASE = "https://gamma-api.polymarket.com/events/pagination"
TIER_ONE = "&exclude_tag_id=1&exclude_tag_id=21&exclude_tag_id=64&exclude_tag_id=101757&volume_min=10000"


def get(url):
    last = None
    for attempt in range(5):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "research-count/0.1"})
            with urllib.request.urlopen(req, timeout=60) as r:
                return r.read()
        except Exception as e:  # retry on transient errors
            last = e
            time.sleep(2 + attempt * 3)
    raise last


def main():
    out, start, end = sys.argv[1], sys.argv[2], sys.argv[3]
    stop = datetime.date.fromisoformat(end)
    log = []
    for closed in ("true", "false"):
        folder = os.path.join(out, f"closed_{closed}")
        os.makedirs(folder, exist_ok=True)
        d = datetime.date.fromisoformat(start)
        while d <= stop:
            win = f"closed={closed}&end_date_min={d}T00:00:00Z&end_date_max={d}T23:59:59.999Z"
            offset, n = 0, 0
            while True:
                raw = get(f"{BASE}?{win}&limit=100&offset={offset}{TIER_ONE}")
                with gzip.open(os.path.join(folder, f"{d}_off{offset}.json.gz"), "wb") as fh:
                    fh.write(raw)
                data = json.loads(raw).get("data") or []
                n += len(data)
                time.sleep(0.12)
                if len(data) < 100:
                    break
                offset += 100
            log.append(f"{d} closed={closed} events={n}")
            print(log[-1], flush=True)
            d += datetime.timedelta(days=1)
    stamp = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
    with open(os.path.join(out, "fetch_log.txt"), "w") as fh:
        fh.write(f"fetched {stamp}\n" + "\n".join(log) + "\n")


if __name__ == "__main__":
    main()
