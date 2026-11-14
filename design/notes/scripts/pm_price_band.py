"""Price at F for a sample of candidate markets, and the share inside the price band.

Run with python3 -I. Public CLOB reads, no key. Reads only prices at or before F,
never an outcome. Feasibility count only; the frozen item rule picks markets
without fetch-time volume.
Usage: python3 -I pm_price_band.py <candidates_json> <F iso> <out_json> <per_event> <midterm_events> <seed>

Non-midterm families: every event, up to <per_event> markets, highest fetch-time
volume first. us_midterms: <midterm_events> events drawn at random (seeded) from
the race-winner events (margin-of-victory and combo events skipped, as derivative
of the same race), up to <per_event> markets each.
Price at F = last hourly point in the 24 hours before F; if the range query is
empty, the last daily point in the 48 hours before F (interval=max, fidelity=1440).
"""
import datetime as dt
import json
import random
import sys
import time
import urllib.request

CLOB = "https://clob.polymarket.com/prices-history"
LO, HI = 0.03, 0.97


def get(url):
    last = None
    for attempt in range(4):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "research-count/0.1"})
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.loads(r.read())
        except Exception as e:  # retry on transient errors
            last = e
            time.sleep(2 + attempt * 3)
    return {"error": str(last)}


def price_at(token, f_unix):
    pts = (get(f"{CLOB}?market={token}&startTs={f_unix - 86400}&endTs={f_unix}&fidelity=60").get("history") or [])
    pts = [p for p in pts if p.get("t", 0) <= f_unix]
    if pts:
        return pts[-1]["p"], "hourly"
    time.sleep(0.1)
    pts = get(f"{CLOB}?market={token}&interval=max&fidelity=1440").get("history") or []
    pts = [p for p in pts if f_unix - 2 * 86400 <= p.get("t", 0) <= f_unix]
    if pts:
        return pts[-1]["p"], "daily"
    return None, "none"


def main():
    cand, f_iso, out, per_event, n_mid, seed = sys.argv[1], sys.argv[2], sys.argv[3], int(sys.argv[4]), int(sys.argv[5]), int(sys.argv[6])
    f_unix = int(dt.datetime.fromisoformat(f_iso).timestamp())
    rows = json.load(open(cand))
    picks = {}
    for fam, evs in rows.items():
        keys = sorted(evs)
        if fam == "us_midterms":
            keys = [k for k in keys if not any(s in " ".join(m["question"] or "" for m in evs[k]).lower()
                                               for s in ("margin of victory", "win by", "combo"))]
            keys = random.Random(seed).sample(keys, min(n_mid, len(keys)))
        for k in keys:
            ms = sorted(evs[k], key=lambda m: -m["volume"])[:per_event]
            picks[(fam, k)] = ms
    res, done = {}, 0
    for (fam, k), ms in picks.items():
        for m in ms:
            p, how = price_at(m["token"], f_unix) if m["token"] else (None, "no token")
            res.setdefault(fam, {}).setdefault(k, []).append({"id": m["id"], "p": p, "how": how})
            done += 1
            time.sleep(0.12)
        if done % 200 < len(ms):
            print(f"{done} markets checked", flush=True)
    json.dump(res, open(out, "w"))
    for fam, evs in res.items():
        ms = [m for v in evs.values() for m in v]
        have = [m for m in ms if m["p"] is not None]
        band = [m for m in have if LO <= m["p"] <= HI]
        ev_band = {k: sum(LO <= (m["p"] if m["p"] is not None else -1) <= HI for m in v) for k, v in evs.items()}
        print(f"{fam}: {len(evs)} events checked, {len(ms)} markets; price found {len(have)} "
              f"({sum(m['how'] == 'hourly' for m in ms)} hourly, {sum(m['how'] == 'daily' for m in ms)} daily); "
              f"in band {len(band)}; events with at least one in band {sum(v > 0 for v in ev_band.values())}; "
              f"cap-3 in-band items {sum(min(3, v) for v in ev_band.values())}")


if __name__ == "__main__":
    main()
