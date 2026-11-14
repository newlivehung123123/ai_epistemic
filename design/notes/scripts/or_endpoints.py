"""Summarise OpenRouter /models/{author}/{slug}/endpoints responses.

Run with python3 -I. Usage: python3 -I or_endpoints.py <dir_with_json>
Prints one line per provider endpoint: provider, tag, context, $/M in/out,
cache read/write $/M, temperature?, reasoning?, implicit caching?, quantization,
uptime_last_1d, and whether long-prompt price overrides exist.
"""
import glob
import json
import os
import sys


def pm(v):
    try:
        return round(float(v) * 1e6, 4)
    except (TypeError, ValueError):
        return None


def main():
    for p in sorted(glob.glob(os.path.join(sys.argv[1], "*.json"))):
        d = json.load(open(p)).get("data") or {}
        print("==", d.get("id"), "| created", d.get("created"))
        for e in d.get("endpoints") or []:
            pr = e.get("pricing") or {}
            sp = e.get("supported_parameters") or []
            ov = pr.get("overrides") or []
            print("   ", e.get("provider_name"), "|", e.get("tag"), "| ctx", e.get("context_length"),
                  "| in/out", pm(pr.get("prompt")), "/", pm(pr.get("completion")),
                  "| cache r/w", pm(pr.get("input_cache_read")), "/", pm(pr.get("input_cache_write")),
                  "| T", "temperature" in sp, "| R", "reasoning" in sp,
                  "| implicit", e.get("supports_implicit_caching"), "| q", e.get("quantization"),
                  "| up1d", e.get("uptime_last_1d"), "| tier", e.get("service_tier"),
                  "| overrides", [o.get("min_prompt_tokens") for o in ov] if ov else "")


if __name__ == "__main__":
    main()
