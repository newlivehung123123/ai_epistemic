"""Print the field names of saved source files (keys only, no values).

Run with python3 -I. Usage: python3 -I keys_dump.py <file> [<file> ...]
"""
import gzip
import json
import sys

for p in sys.argv[1:]:
    op = gzip.open if p.endswith(".gz") else open
    d = json.load(op(p))
    print("==", p.split("/raw_sources/")[-1])
    if isinstance(d, dict):
        print("  top keys:", list(d)[:40])
        for k in ("questions", "resolutions", "rows", "features", "data"):
            v = d.get(k)
            if isinstance(v, list) and v:
                x = v[0]
                if isinstance(x, dict) and "row" in x:
                    x = x["row"]
                if isinstance(x, dict) and "feature_idx" in x:
                    print("  features:", [(f.get("name"), (f.get("type") or {}).get("dtype") or (f.get("type") or {}).get("_type")) for f in v])
                    break
                print(f"  {k}[0] keys:", list(x)[:60] if isinstance(x, dict) else type(x))
    elif isinstance(d, list) and d:
        x = d[0]
        print("  list of", len(d), "; [0] keys:", list(x)[:80] if isinstance(x, dict) else type(x))
