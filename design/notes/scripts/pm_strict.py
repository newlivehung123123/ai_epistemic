"""Stricter Polymarket count: drop series and template events, keep one market per event.

Run with python3 -I. Usage: python3 -I pm_strict.py <polymarket_dir> <start> <end> <n_samples>
Same market filter as pm_count.py (Yes/No, closed, prices 1/0, market volume > 10k,
closedTime and endDate in window), applied to the saved tier_one event pages.
Then: (a) drop events that belong to a series (seriesSlug or series list non-empty);
(b) drop events carrying a template tag (listed in TEMPLATE_TAGS);
(c) keep the highest-volume qualifying market per event.
Writes samples_strict_markets.json and strict_market_ids.json in <polymarket_dir>.
"""
import collections
import glob
import gzip
import json
import os
import random
import sys

TEMPLATE_TAGS = {"Tweet Markets", "Finance Updown", "Pyth Finance", "Hide From New", "Recurring",
                 "Up or Down", "Daily", "Weekly", "Mention Markets", "Mentions", "Daily Close"}


def jl(s):
    if isinstance(s, list):
        return s
    try:
        return json.loads(s)
    except Exception:
        return None


def ok(m, start, end):
    outs, prices = jl(m.get("outcomes")), jl(m.get("outcomePrices"))
    return (outs == ["Yes", "No"] and bool(m.get("closed")) and isinstance(prices, list)
            and sorted(str(x) for x in prices) == ["0", "1"] and float(m.get("volumeNum") or 0) > 10000
            and start <= (m.get("closedTime") or "")[:10] <= end and start <= (m.get("endDate") or "")[:10] <= end)


def main():
    pdir, start, end, n = sys.argv[1], sys.argv[2], sys.argv[3], int(sys.argv[4])
    evs = {}
    for p in sorted(glob.glob(os.path.join(pdir, "tier_one_events", "*.json.gz"))):
        if start <= os.path.basename(p)[:10] <= end:
            for e in json.load(gzip.open(p)).get("data") or []:
                evs[e["id"]] = e
    kept = {eid: [m for m in (e.get("markets") or []) if ok(m, start, end)] for eid, e in evs.items()}
    kept = {k: v for k, v in kept.items() if v}
    print("events with >=1 qualifying market:", len(kept), "markets:", sum(map(len, kept.values())))
    tagc = collections.Counter(t.get("label") for k in kept for t in (evs[k].get("tags") or []))
    print("all tag labels on these events (top 60):", tagc.most_common(60))
    ser = {k for k in kept if evs[k].get("seriesSlug") or evs[k].get("series")}
    print("events in a series:", len(ser))
    tmpl = {k for k in kept if {t.get("label") for t in (evs[k].get("tags") or [])} & TEMPLATE_TAGS}
    print("events with a template tag:", len(tmpl), "| overlap with series:", len(ser & tmpl))
    strict = {k: v for k, v in kept.items() if k not in ser and k not in tmpl}
    print("\n== STRICT events (no series, no template tag):", len(strict), "markets inside:", sum(map(len, strict.values())))
    one = {k: max(v, key=lambda m: float(m["volumeNum"])) for k, v in strict.items()}
    bym = collections.Counter(m["endDate"][:7] for m in one.values())
    print("  one market per event, by end-date month:", dict(sorted(bym.items())))
    single = [k for k in strict if len(evs[k].get("markets") or []) == 1]
    print("  events that are a single binary market (no sibling markets):", len(single),
          dict(sorted(collections.Counter(one[k]["endDate"][:7] for k in single).items())))
    print("  YES share (one per event):", round(sum(jl(m["outcomePrices"])[0] in ("1", 1) for m in one.values()) / max(1, len(one)), 3))
    vols = sorted(float(m["volumeNum"]) for m in one.values())
    print("  volume quartiles:", [round(vols[int(q * (len(vols) - 1))]) for q in (0, .25, .5, .75, 1)])
    print("  volume > 100k:", sum(v > 100000 for v in vols), "| > 1m:", sum(v > 1e6 for v in vols))
    print("  description >= 200 chars:", sum(len(m.get("description") or "") >= 200 for m in one.values()))
    print("  top tags among strict:", collections.Counter(t.get("label") for k in strict for t in (evs[k].get("tags") or [])).most_common(20))
    with open(os.path.join(pdir, "strict_market_ids.json"), "w") as fh:
        json.dump(sorted(m["id"] for m in one.values()), fh)
    rng = random.Random(20261031)
    pick = rng.sample(sorted(one), min(n, len(one)))
    out = []
    for k in pick:
        m, e = one[k], evs[k]
        out.append({"market_id": m["id"], "event_id": k, "event_title": e.get("title"), "question": m.get("question"),
                    "description_first_400": (m.get("description") or "")[:400], "description_chars": len(m.get("description") or ""),
                    "startDate": m.get("startDate"), "endDate": m.get("endDate"), "closedTime": m.get("closedTime"),
                    "outcomes": m.get("outcomes"), "outcomePrices": m.get("outcomePrices"), "volumeNum": m.get("volumeNum"),
                    "negRisk": m.get("negRisk"), "clobTokenIds": m.get("clobTokenIds"), "slug": m.get("slug"),
                    "tags": [t.get("label") for t in e.get("tags") or []]})
    with open(os.path.join(pdir, "samples_strict_markets.json"), "w") as fh:
        json.dump(out, fh, indent=1)
    for s in out:
        print("   -", s["endDate"][:10], s["outcomePrices"], round(float(s["volumeNum"])), "|", (s["question"] or "")[:110])


if __name__ == "__main__":
    main()
