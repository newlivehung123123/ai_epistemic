"""Condensed view of OpenRouter endpoint files: first-party and cheapest endpoints per model.

Run with python3 -I. Usage: python3 -I or_endpoints_brief.py <dir_with_json>
"""
import glob
import json
import os
import sys

FIRST = ("openai", "google", "deepseek", "alibaba", "meta", "mistral", "xai", "x-ai", "moonshot", "z.ai", "z-ai", "zai")


def pm(v):
    try:
        return round(float(v) * 1e6, 4)
    except (TypeError, ValueError):
        return None


def line(e):
    pr = e.get("pricing") or {}
    sp = e.get("supported_parameters") or []
    return (f"{e.get('provider_name')} [{e.get('tag')}] ctx {e.get('context_length')} in/out {pm(pr.get('prompt'))}/{pm(pr.get('completion'))} "
            f"cache r {pm(pr.get('input_cache_read'))} w {pm(pr.get('input_cache_write'))} T={'temperature' in sp} R={'reasoning' in sp} "
            f"q={e.get('quantization')} up1d={round(e.get('uptime_last_1d') or 0)} ov={'y' if pr.get('overrides') else 'n'}")


def main():
    for p in sorted(glob.glob(os.path.join(sys.argv[1], "*.json"))):
        d = json.load(open(p)).get("data") or {}
        eps = d.get("endpoints") or []
        print("==", d.get("id"), f"({len(eps)} endpoints; temperature on all: {all('temperature' in (e.get('supported_parameters') or []) for e in eps)})")
        fp = [e for e in eps if any(k in (e.get("provider_name") or "").lower() for k in FIRST)]
        for e in fp[:2]:
            print("   first-party:", line(e))
        ok = [e for e in eps if (e.get("uptime_last_1d") or 0) >= 90 and (e.get("pricing") or {}).get("prompt") is not None]
        ok.sort(key=lambda e: 3 * float(e["pricing"]["prompt"]) + float(e["pricing"]["completion"]))
        for e in ok[:2]:
            print("   cheapest(up>=90):", line(e))


if __name__ == "__main__":
    main()
