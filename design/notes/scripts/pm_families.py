"""Split qualifying Polymarket items into families. Counts only, no outcomes.

Usage: python3 -I pm_families.py <window_dir> <F iso> <end_min YYYY-MM-DD> <end_max YYYY-MM-DD> <out_json>

Families (fixed before any price or outcome is looked at):
  us_midterms     event tag Midterms or Nov 4 Elections
  other_elections title or tag names an election, a vote, a race or a referendum
  ai_companies    title names an AI lab, product or model (value-leakage flag)
  other           everything else
Writes the qualifying market ids per event and family to <out_json> for the
price-band check, and prints the markets-per-event spread per family.
"""
import collections
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pm_retro_yield import TEMPLATE_TAGS, jl, ts  # noqa: E402
from pm_window_yield import load, qualifying  # noqa: E402

MIDTERM_TAGS = {"Midterms", "Nov 4 Elections"}
ELECTION = re.compile(r"election|elections|electoral|vote|voting|referendum|ballot|primary|runoff|mayor|senate|governor|"
                      r"house race|parliament|prime minister|president of|presidential|candidate|seats|win the", re.I)
AI = re.compile(r"\bAI\b|OpenAI|Anthropic|Claude|Gemini|Google|DeepMind|Meta\b|Meta's|xAI|Grok|DeepSeek|Qwen|Mistral|"
                r"\bSSI\b|Muse|GPT|LLM|model|training pause|third party vetting|SpaceXAI|Situational Awareness", re.I)


def family(e):
    labels = {t.get("label") or "" for t in (e.get("tags") or [])}
    title = e.get("title") or ""
    if labels & MIDTERM_TAGS:
        return "us_midterms"
    if ELECTION.search(title) or any(ELECTION.search(x) for x in labels):
        return "other_elections"
    if AI.search(title):
        return "ai_companies"
    return "other"


def main():
    wdir, f_iso, lo, hi, out = sys.argv[1:6]
    F = ts(f_iso)
    evs = load(wdir, lo, hi)
    ser = {k for k, e in evs.items() if e.get("seriesSlug") or e.get("series")}
    tmpl = {k for k, e in evs.items() if {t.get("label") for t in (e.get("tags") or [])} & TEMPLATE_TAGS}
    per_event = qualifying(evs, F, lo, hi, ser | tmpl, collections.Counter())
    fam = collections.defaultdict(dict)
    for k, ms in per_event.items():
        fam[family(evs[k])][k] = ms
    rows = {}
    for f in ("us_midterms", "other_elections", "ai_companies", "other"):
        d = fam.get(f, {})
        nm = sum(len(v) for v in d.values())
        spread = collections.Counter(min(len(v), 10) for v in d.values())
        months = collections.Counter(min(ts(m["endDate"]).date().isoformat() for m in v)[:7] for v in d.values())
        print(f"{f}: {len(d)} events, {nm} markets, cap-3 items {sum(min(3, len(v)) for v in d.values())}, "
              f"cap-1 {len(d)}; events by month of end {dict(sorted(months.items()))}")
        print(f"  markets per event (10 = 10 or more): {dict(sorted(spread.items()))}")
        rows[f] = {k: [{"id": m["id"], "token": (jl(m.get("clobTokenIds")) or [None])[0],
                        "volume": float(m.get("volumeNum") or m.get("volume") or 0),
                        "end": m.get("endDate"), "question": m.get("question")} for m in v]
                   for k, v in d.items()}
    if fam.get("us_midterms"):
        sub = collections.Counter()
        for k in fam["us_midterms"]:
            labels = {t.get("label") for t in (evs[k].get("tags") or [])}
            sub["Midterm MOV or Margin of Victory" if labels & {"Midterm MOV", "Margin of Victory"} else
                "Senate" if "Senate Elections" in labels else "Governor" if "Governor Elections" in labels else
                "House" if "House Elections" in labels else "other midterm"] += 1
        print("  us_midterms events by kind:", dict(sub))
    with open(out, "w") as fh:
        json.dump(rows, fh)
    print("wrote", out)


if __name__ == "__main__":
    main()
