import json, sys
from collections import Counter, defaultdict
r = json.load(open(sys.argv[1]))
rs = r["resolutions"]
c = Counter((x["source"], x["resolution_date"], x["resolved"], isinstance(x["id"], list)) for x in rs)
for k in sorted(c): print(k, c[k])
mk = [x for x in rs if x["source"] in ("manifold","metaculus","polymarket","infer")]
print("market entries", len(mk))
byid = defaultdict(list)
for x in mk: byid[x["id"]].append(x)
print("unique market ids", len(byid))
n=0
for k, v in byid.items():
    print(json.dumps(v)[:600]); n+=1
    if n>6: break
print("dirs", Counter(str(x["direction"]) for x in rs))
vals = Counter((x["source"], x["resolved"], x["resolved_to"] in (0,1,0.0,1.0)) for x in rs)
print(vals)
