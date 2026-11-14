import json, sys
p = sys.argv[1]
d = json.load(open(p))
data = d["data"]
print("n models:", len(data))
print("keys of first:", list(data[0].keys()))
print(json.dumps(data[0], indent=1)[:3000])
