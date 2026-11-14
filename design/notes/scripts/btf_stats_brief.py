"""Summarise HF datasets-server /statistics for chosen columns (nan counts, ranges, frequencies).

Run with python3 -I. Usage: python3 -I btf_stats_brief.py <stats_json> <col,col,...>
"""
import json
import sys

d = json.load(open(sys.argv[1]))
want = sys.argv[2].split(",")
print("num_examples:", d.get("num_examples"), "partial:", d.get("partial"))
for s in d.get("statistics") or []:
    if s.get("column_name") in want:
        st = dict(s.get("column_statistics") or {})
        if "histogram" in st:
            st["histogram"] = {"bins": len((st["histogram"] or {}).get("bin_edges") or []), "counts": (st["histogram"] or {}).get("hist")}
        fr = st.get("frequencies")
        if isinstance(fr, dict) and len(fr) > 12:
            st["frequencies"] = dict(sorted(fr.items(), key=lambda kv: -kv[1])[:12])
            st["n_distinct_shown_of"] = len(fr)
        print(s.get("column_name"), s.get("column_type"), json.dumps(st)[:700])
