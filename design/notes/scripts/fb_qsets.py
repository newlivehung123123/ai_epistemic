import json, sys, gzip, os
from collections import Counter
d = sys.argv[1]
for f in sorted(os.listdir(d)):
    if not f.endswith(".json.gz"): continue
    q = json.load(gzip.open(os.path.join(d, f)))
    qs = q["questions"]
    src = Counter(x["source"] for x in qs)
    rd = Counter(tuple(x["resolution_dates"]) if isinstance(x["resolution_dates"], list) else x["resolution_dates"] for x in qs)
    print(f, q.get("forecast_due_date"), "n=", len(qs), dict(sorted(src.items())))
    for k, v in rd.most_common(4): print("    resolution_dates", k, v)
    for s in ("kalshi", "serpapi"):
        ex = [x for x in qs if x["source"] == s]
        if ex:
            print("   EXAMPLE", s, json.dumps({k: (str(v)[:400]) for k, v in ex[0].items()}, indent=0)[:1800])
