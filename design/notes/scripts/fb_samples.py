"""Sample ForecastBench market questions that resolved in a window, joining question and resolution sets.

Run with python3 -I. Usage:
  python3 -I fb_samples.py <question_sets_dir> <resolution_sets_dir> <start> <end> <n> <out_json>
Only question sets present locally are used (the *-llm.json.gz files).
"""
import gzip
import json
import os
import random
import sys
from collections import Counter

MARKET = {"manifold", "metaculus", "polymarket", "infer", "kalshi"}


def main():
    qd, rd, start, end, n, out = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4], int(sys.argv[5]), sys.argv[6]
    pool = {}
    for f in sorted(os.listdir(qd)):
        if not f.endswith("-llm.json.gz"):
            continue
        date = f[:10]
        rp = os.path.join(rd, f"{date}_resolution_set.json.gz")
        if not os.path.exists(rp):
            print("no resolution set for", date)
            continue
        qs = json.load(gzip.open(os.path.join(qd, f)))
        qmap = {(q["source"], q["id"]): q for q in qs["questions"] if not isinstance(q["id"], list)}
        res = json.load(gzip.open(rp))["resolutions"]
        hit = 0
        for r in res:
            if isinstance(r["id"], list) or r["source"] not in MARKET:
                continue
            if not (start <= r["resolution_date"] <= end and r["resolved"] and r["resolved_to"] in (0, 1)):
                continue
            q = qmap.get((r["source"], r["id"]))
            if q is None:
                continue
            hit += 1
            pool.setdefault((r["source"], r["id"]), {
                "question_set": date, "source": r["source"], "id": r["id"], "question": q.get("question"),
                "resolution_criteria": (q.get("resolution_criteria") or "")[:400],
                "background_chars": len(q.get("background") or ""),
                "market_info_open_datetime": q.get("market_info_open_datetime"),
                "market_info_close_datetime": q.get("market_info_close_datetime"),
                "freeze_datetime": q.get("freeze_datetime"), "freeze_datetime_value": q.get("freeze_datetime_value"),
                "resolution_date": r["resolution_date"], "resolved_to": r["resolved_to"], "url": q.get("url")})
        print(date, "in-window resolved market entries with question text:", hit)
    print("unique in-window market questions with text in local sets:", len(pool), dict(Counter(k[0] for k in pool)))
    def num(x):
        try:
            return float(x)
        except (TypeError, ValueError):
            return None
    print("freeze value types:", dict(Counter(type(v["freeze_datetime_value"]).__name__ for v in pool.values())))
    vals = [v for v in pool.values() if num(v["freeze_datetime_value"]) is not None and 0 <= num(v["freeze_datetime_value"]) <= 1]
    if vals:
        brier = sum((num(v["freeze_datetime_value"]) - v["resolved_to"]) ** 2 for v in vals) / len(vals)
        print("crowd baseline Brier (freeze value vs outcome) on these:", round(brier, 4), "n =", len(vals))
        se = [(num(v["freeze_datetime_value"]) - v["resolved_to"]) ** 2 for v in vals]
        sd = (sum((x - brier) ** 2 for x in se) / (len(se) - 1)) ** 0.5
        print("SD of per-question squared error (crowd):", round(sd, 4), "| YES share:", round(sum(v["resolved_to"] for v in vals) / len(vals), 3))
    rng = random.Random(20261031)
    keys = sorted(pool, key=lambda k: (k[0], str(k[1])))
    by_src = {}
    for k in keys:
        by_src.setdefault(k[0], []).append(k)
    picked = []
    while len(picked) < n and any(by_src.values()):
        for s in sorted(by_src):
            if by_src[s] and len(picked) < n:
                picked.append(by_src[s].pop(rng.randrange(len(by_src[s]))))
    sample = [pool[k] for k in picked]
    with open(out, "w") as fh:
        json.dump(sample, fh, indent=1, default=str)
    for s in sample:
        print("-", s["source"], s["resolution_date"], "freeze", s["freeze_datetime_value"], "->", s["resolved_to"], "|", (s["question"] or "")[:110])


if __name__ == "__main__":
    main()
