"""Release ('created') date, price and settings of candidate OpenRouter models.

Usage: python3 -I or_created.py <openrouter_models.json> <comma-separated id substrings>
"""
import datetime as dt
import json
import sys

d = json.load(open(sys.argv[1]))["data"]
subs = [s.strip() for s in sys.argv[2].split(",")]
for m in sorted(d, key=lambda m: m["id"]):
    if not any(s in m["id"] for s in subs):
        continue
    pr = m.get("pricing") or {}
    per_m = lambda k: "-" if pr.get(k) in (None, "") else f"{float(pr[k]) * 1e6:.3f}"
    sp = set(m.get("supported_parameters") or [])
    r = m.get("reasoning") or {}
    print(f"{m['id']:<48} created {dt.datetime.fromtimestamp(m['created'], dt.timezone.utc):%Y-%m-%d}"
          f" | in {per_m('prompt')} out {per_m('completion')} reasoning {per_m('internal_reasoning')}"
          f" | cutoff {m.get('knowledge_cutoff')} | expires {m.get('expiration_date')}"
          f" | temp {'temperature' in sp} seed {'seed' in sp} json {bool({'response_format', 'structured_outputs'} & sp)}"
          f" | reasoning mandatory {r.get('mandatory')} default_on {r.get('default_enabled')} efforts {r.get('supported_efforts')}")
