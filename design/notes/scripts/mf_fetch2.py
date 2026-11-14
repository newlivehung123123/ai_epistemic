"""Page Manifold resolved BINARY markets by creation time (sort=newest + beforeTime).

The search endpoint caps offset at 1000, so the documented beforeTime cursor is used.
Run with python3 -I.
Usage: python3 -I mf_fetch2.py <out_dir> <stop_created_before YYYY-MM-DD> [start_before_ms]
Saves each page gzipped and stops once a page reaches markets created before the stop date.
"""
import datetime
import gzip
import json
import os
import sys
import time
import urllib.request

URL = ("https://api.manifold.markets/v0/search-markets?term=&filter=resolved"
       "&contractType=BINARY&sort=newest&limit=1000")


def get(url):
    last = None
    for attempt in range(5):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "research-count/0.1"})
            with urllib.request.urlopen(req, timeout=90) as r:
                return r.read()
        except Exception as e:
            last = e
            time.sleep(3 + attempt * 3)
    raise last


def main():
    out, stop = sys.argv[1], sys.argv[2]
    before = int(sys.argv[3]) if len(sys.argv) > 3 else None
    stop_ms = int(datetime.datetime.fromisoformat(stop + "T00:00:00+00:00").timestamp() * 1000)
    os.makedirs(out, exist_ok=True)
    page = 0
    while True:
        url = URL + (f"&beforeTime={before}" if before else "")
        raw = get(url)
        with gzip.open(os.path.join(out, f"page_{page:03d}.json.gz"), "wb") as fh:
            fh.write(raw)
        data = json.loads(raw)
        if not isinstance(data, list) or not data:
            print("stop: empty or non-list", str(data)[:200], flush=True)
            break
        last = data[-1]["createdTime"]
        print(page, len(data), datetime.datetime.fromtimestamp(last / 1000, datetime.timezone.utc), flush=True)
        if last < stop_ms or len(data) < 1000:
            break
        before = last
        page += 1
        time.sleep(0.5)


if __name__ == "__main__":
    main()
