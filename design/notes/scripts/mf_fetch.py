"""Page Manifold search-markets (resolved BINARY, newest resolution first).

Run with python3 -I.
Usage: python3 -I mf_fetch.py <out_dir> <stop_before YYYY-MM-DD>
Saves each page gzipped as page_<offset>.json.gz and stops once the last
market on a page resolved before the stop date.
"""
import datetime
import gzip
import json
import os
import sys
import time
import urllib.request

URL = ("https://api.manifold.markets/v0/search-markets?term=&filter=resolved"
       "&contractType=BINARY&sort=resolve-date&limit=1000&offset={off}")


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
    stop_ms = int(datetime.datetime.fromisoformat(stop + "T00:00:00+00:00").timestamp() * 1000)
    os.makedirs(out, exist_ok=True)
    off = 0
    while True:
        raw = get(URL.format(off=off))
        with gzip.open(os.path.join(out, f"page_{off:06d}.json.gz"), "wb") as fh:
            fh.write(raw)
        data = json.loads(raw)
        if not isinstance(data, list):
            print("non-list response at", off, str(data)[:200], flush=True)
            break
        last = data[-1].get("resolutionTime") if data else None
        print(off, len(data), last and datetime.datetime.fromtimestamp(last / 1000, datetime.timezone.utc), flush=True)
        if len(data) < 1000 or (last is not None and last < stop_ms):
            break
        off += 1000
        time.sleep(0.5)


if __name__ == "__main__":
    main()
