"""Print the field names of one saved Polymarket event and one of its markets (no values).

Usage: python3 -I pm_keys.py <events_file.json.gz>
"""
import gzip
import json
import sys

data = json.load(gzip.open(sys.argv[1])).get("data") or []
e = data[0]
print("event keys:", sorted(e.keys()))
m = (e.get("markets") or [{}])[0]
print("market keys:", sorted(m.keys()))
print("market time fields:", {k: m.get(k) for k in sorted(m) if any(s in k.lower() for s in ("date", "time", "created", "start", "end"))})
