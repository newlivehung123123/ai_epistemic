import json, sys
q = json.load(open(sys.argv[1]))
print("QSET top keys:", list(q.keys()) if isinstance(q, dict) else type(q))
for k, v in q.items():
    if not isinstance(v, list):
        print(" ", k, "=", str(v)[:300])
qs = q["questions"]
print("n questions:", len(qs))
print("question keys:", list(qs[0].keys()))
from collections import Counter
print(Counter(x["source"] for x in qs))
for src in sorted(set(x["source"] for x in qs)):
    ex = next(x for x in qs if x["source"] == src)
    print("=== example", src)
    print(json.dumps(ex, indent=1)[:1800])
r = json.load(open(sys.argv[2]))
print("RSET top keys:", list(r.keys()) if isinstance(r, dict) else type(r))
for k, v in r.items():
    if not isinstance(v, list):
        print(" ", k, "=", str(v)[:300])
rs = r["resolutions"]
print("n resolutions:", len(rs))
print("res keys:", list(rs[0].keys()))
print(json.dumps(rs[:3], indent=1))
