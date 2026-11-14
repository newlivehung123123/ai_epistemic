import json, sys, datetime
p = sys.argv[1]
prefixes = sys.argv[2].split(",")
d = json.load(open(p))
rows = []
for m in d["data"]:
    mid = m["id"]
    if not any(mid.startswith(px + "/") for px in prefixes):
        continue
    pr = m.get("pricing", {}) or {}
    def pm(k):
        v = pr.get(k)
        if v is None: return "-"
        try: return "%.3f" % (float(v) * 1e6)
        except: return str(v)
    r = m.get("reasoning") or {}
    created = datetime.datetime.utcfromtimestamp(m["created"]).strftime("%Y-%m-%d")
    sp = m.get("supported_parameters") or []
    rows.append((mid.split("/")[0], created, mid, pm("prompt"), pm("completion"), pm("input_cache_read"), pm("input_cache_write"), pm("internal_reasoning"), m.get("context_length"), "T" if "temperature" in sp else "-", "R" if "reasoning" in sp else "-", r.get("mandatory"), r.get("default_enabled"), ",".join(r.get("supported_efforts") or []), r.get("default_effort"), m.get("knowledge_cutoff"), m.get("expiration_date")))
rows.sort(key=lambda x: (x[0], x[1]), reverse=False)
for row in rows:
    print(" | ".join(str(x) for x in row))
