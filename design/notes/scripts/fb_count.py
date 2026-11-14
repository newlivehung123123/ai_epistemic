"""Count ForecastBench resolution-set entries whose resolution_date falls in a window.
Usage: python3 -I fb_count.py <resolution_sets_dir> <start YYYY-MM-DD> <end YYYY-MM-DD>
Reads *_resolution_set.json.gz (untrusted data; parsed as JSON only)."""
import json, sys, gzip, os
from collections import Counter, defaultdict
d, start, end = sys.argv[1], sys.argv[2], sys.argv[3]
MARKET = {"manifold", "metaculus", "polymarket", "infer", "kalshi"}
files = sorted(f for f in os.listdir(d) if f.endswith("_resolution_set.json.gz"))
per_set = {}
inst = []           # (fdd, source, id, resdate, resolved, value)
for f in files:
    r = json.load(gzip.open(os.path.join(d, f)))
    fdd = r["forecast_due_date"]
    for x in r["resolutions"]:
        qid = x["id"]
        if isinstance(qid, list):
            qid = tuple(qid)
        inst.append((fdd, x["source"], qid, x["resolution_date"], x["resolved"], x["resolved_to"], x.get("direction")))
print("files:", len(files), "entries:", len(inst))
print("combination entries (id list):", sum(1 for i in inst if isinstance(i[2], tuple)))
inw = [i for i in inst if start <= i[3] <= end]
print("entries with resolution_date in window:", len(inw))
print("  of which resolved==True:", sum(1 for i in inw if i[4]))
print("  resolved and value in {0,1}:", sum(1 for i in inw if i[4] and i[5] in (0, 1)))
print("  resolved and value not 0/1:", Counter((i[1], i[5]) for i in inw if i[4] and i[5] not in (0, 1)).most_common(10))
single = [i for i in inw if i[4] and i[5] in (0, 1) and not isinstance(i[2], tuple)]
print("\n== Resolved binary single questions in window, by source (instances = set x id x resolution date)")
c = Counter(i[1] for i in single)
for k in sorted(c): print(f"  {k:12s} {c[k]}")
print("  TOTAL", sum(c.values()))
print("\n== By source x month")
cm = Counter((i[1], i[3][:7]) for i in single)
months = sorted(set(i[3][:7] for i in single))
print("  source      " + " ".join(f"{m:>8s}" for m in months))
for s in sorted(set(i[1] for i in single)):
    print(f"  {s:11s} " + " ".join(f"{cm[(s,m)]:8d}" for m in months))
print("  ALL         " + " ".join(f"{sum(cm[(s,m)] for s in set(i[1] for i in single)):8d}" for m in months))
print("\n== Market questions: unique (source,id) resolved in window (deduped across question sets)")
mk = {}
for i in single:
    if i[1] in MARKET:
        key = (i[1], i[2])
        mk.setdefault(key, set()).add((i[3], i[5]))
cu = Counter(k[0] for k in mk)
for k in sorted(cu): print(f"  {k:12s} {cu[k]}")
print("  TOTAL unique market questions:", len(mk))
print("  inconsistent res date/value across sets:", sum(1 for v in mk.values() if len(v) > 1))
mm = Counter((k[0], sorted(v)[0][0][:7]) for k, v in mk.items())
print("  by month:", sorted(Counter(sorted(v)[0][0][:7] for v in mk.values()).items()))
yes = Counter(k[0] for k, v in mk.items() if sorted(v)[0][1] == 1)
print("  share YES by source:", {s: f"{yes[s]}/{cu[s]}" for s in cu})
print("\n== Dataset questions: unique (forecast set, source, id) with >=1 resolved date in window; unique (source,id) ignoring set")
ds = [i for i in single if i[1] not in MARKET]
print("  instances:", len(ds))
print("  unique (set,source,id):", len(set((i[0], i[1], i[2]) for i in ds)))
print("  unique (source,id):", len(set((i[1], i[2]) for i in ds)))
print("  by source unique (source,id):", sorted(Counter(s for s, q in set((i[1], i[2]) for i in ds)).items()))
print("  share resolved YES (instances):", sorted({s: round(sum(1 for i in ds if i[1]==s and i[5]==1)/max(1,sum(1 for i in ds if i[1]==s)),3) for s in set(i[1] for i in ds)}.items()))
print("\n== Per question set: resolved binary entries in window (market | dataset)")
ps = defaultdict(lambda: [0, 0])
for i in single:
    ps[i[0]][0 if i[1] in MARKET else 1] += 1
for k in sorted(ps): print(f"  {k}  market={ps[k][0]:4d}  dataset={ps[k][1]:5d}")
print("\n== Unresolved entries (resolved==False) by latest date and source (market questions still open)")
ur = Counter((i[1], i[3]) for i in inst if not i[4])
for k in sorted(ur): print("  ", k, ur[k])
print("unique open market questions:", len(set((i[1], i[2]) for i in inst if not i[4] and i[1] in MARKET)))
print("\n== Combination (id-list) entries with resolution_date in window:", sum(1 for i in inw if isinstance(i[2], tuple)))
print("== Sources present per question set (all entries):")
srcs = defaultdict(set)
for i in inst: srcs[i[0]].add(i[1])
prev = None
for k in sorted(srcs):
    s = ",".join(sorted(srcs[k]))
    if s != prev: print("  from", k, ":", s)
    prev = s
