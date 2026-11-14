"""Count Polymarket events and markets from the saved gamma API responses.

Run with python3 -I. Usage: python3 -I pm_count.py <polymarket_dir> <start YYYY-MM-DD> <end YYYY-MM-DD> <n_samples>
Reads daily_counts/{day}_{tier}.json.gz (limit=1 responses; pagination.totalResults per day)
and tier_one_events/{day}_off{k}.json.gz (full event pages with nested markets).
Writes samples_tier_one_markets.json (n samples) and tier_one_market_ids.json in <polymarket_dir>.
"""
import collections
import glob
import gzip
import json
import os
import random
import re
import sys

TIERS = ["tier_all", "tier_nsc", "tier_vol", "tier_one"]


def jl(s):
    if isinstance(s, list):
        return s
    try:
        return json.loads(s)
    except Exception:
        return None


def main():
    pdir, start, end, n = sys.argv[1], sys.argv[2], sys.argv[3], int(sys.argv[4])
    # 1. daily event counts per tier
    days = collections.defaultdict(dict)
    for p in glob.glob(os.path.join(pdir, "daily_counts", "*.json.gz")):
        b = os.path.basename(p)[:-8]
        day, tier = b[:10], b[11:]
        pg = json.load(gzip.open(p)).get("pagination") or {}
        days[day][tier] = (pg.get("totalResults"), pg.get("hasMore"))
    days = {d: v for d, v in days.items() if start <= d <= end}
    print("days with counts:", len(days), min(days), "to", max(days))
    incomplete = [d for d, v in days.items() if set(v) != set(TIERS)]
    print("days missing a tier:", incomplete[:10])
    capped = [(d, t) for d, v in days.items() for t, (tot, more) in v.items() if tot == 2 and more]
    print("possible capped day counts (totalResults==2 with hasMore):", capped[:10], len(capped))
    print("\n== Closed EVENTS by end-date month (sum of exact one-day totals)")
    print("month    " + " ".join(f"{t:>9s}" for t in TIERS))
    tot = collections.Counter()
    for mon in sorted({d[:7] for d in days}):
        row = [sum((days[d].get(t) or (0, 0))[0] or 0 for d in days if d[:7] == mon) for t in TIERS]
        for t, r in zip(TIERS, row):
            tot[t] += r
        print(f"{mon}  " + " ".join(f"{r:9d}" for r in row))
    print("TOTAL    " + " ".join(f"{tot[t]:9d}" for t in TIERS))
    # 2. tier_one events and their markets
    evs = {}
    for p in sorted(glob.glob(os.path.join(pdir, "tier_one_events", "*.json.gz"))):
        day = os.path.basename(p)[:10]
        if not (start <= day <= end):
            continue
        for e in json.load(gzip.open(p)).get("data") or []:
            evs[e["id"]] = (day, e)
    print("\n== tier_one events loaded (unique ids):", len(evs), "| sum of tier_one daily totals:", tot["tier_one"])
    mk = []
    for eid, (day, e) in evs.items():
        for m in e.get("markets") or []:
            mk.append((day, e, m))
    print("markets nested in those events:", len(mk))
    c = collections.Counter()
    keep = []
    for day, e, m in mk:
        outs = jl(m.get("outcomes"))
        prices = jl(m.get("outcomePrices"))
        yesno = outs == ["Yes", "No"]
        two = isinstance(outs, list) and len(outs) == 2
        resolved = isinstance(prices, list) and sorted(str(x) for x in prices) == ["0", "1"]
        vol = float(m.get("volumeNum") or 0)
        ct = (m.get("closedTime") or "")[:10]
        ed = (m.get("endDate") or "")[:10]
        c["two outcomes"] += two
        c["Yes/No outcomes"] += yesno
        c["closed"] += bool(m.get("closed"))
        c["prices 1/0 (resolved)"] += resolved
        c["uma status resolved"] += (m.get("umaResolutionStatus") == "resolved")
        ok = two and bool(m.get("closed")) and resolved
        c["two outcomes + closed + 1/0"] += ok
        c["... and market volume > 10k"] += ok and vol > 10000
        c["... and Yes/No labels"] += ok and vol > 10000 and yesno
        inwin_ct = start <= ct <= end
        inwin_ed = start <= ed <= end
        c["... and closedTime in window"] += ok and vol > 10000 and yesno and inwin_ct
        c["... and market endDate in window"] += ok and vol > 10000 and yesno and inwin_ct and inwin_ed
        if ok and vol > 10000 and yesno and inwin_ct and inwin_ed:
            keep.append((day, e, m))
    for k, v in c.items():
        print(f"  {k:40s} {v}")
    print("\n== Kept markets (Yes/No, resolved 1/0, volume>10k, closedTime and endDate in window):", len(keep))
    print("  by end-date month:", dict(sorted(collections.Counter(m["endDate"][:7] for _, _, m in keep).items())))
    print("  YES share:", round(sum(jl(m["outcomePrices"])[0] in ("1", 1) for _, _, m in keep) / max(1, len(keep)), 3))
    print("  description present (>=50 chars):", sum(len(m.get("description") or "") >= 50 for _, _, m in keep))
    print("  resolutionSource non-empty:", sum(bool((m.get("resolutionSource") or e.get("resolutionSource") or "").strip()) for _, e, m in keep))
    print("  negRisk (member of multi-outcome group):", sum(bool(m.get("negRisk")) for _, _, m in keep))
    print("  unique events:", len({e["id"] for _, e, _ in keep}))
    print("  events with 1 kept market:", sum(1 for v in collections.Counter(e["id"] for _, e, _ in keep).values() if v == 1))
    gap = [(m["closedTime"][:10], m["endDate"][:10]) for _, _, m in keep]
    late = sum(1 for ctd, edd in gap if ctd > edd)
    print("  closedTime after endDate:", late)
    vols = sorted(float(m["volumeNum"]) for _, _, m in keep)
    if vols:
        print("  market volume quartiles:", [round(vols[int(q * (len(vols) - 1))]) for q in (0, .25, .5, .75, 1)])
    # repetitiveness: series and title templates
    print("  top event series:", collections.Counter(e.get("seriesSlug") for _, e, _ in keep if e.get("seriesSlug")).most_common(6))
    tmpl = collections.Counter(re.sub(r"\d+", "#", " ".join((m.get("question") or "").split()[:4])) for _, _, m in keep)
    print("  top question openings:", tmpl.most_common(10))
    tags = collections.Counter(t.get("label") for _, e, _ in keep for t in (e.get("tags") or []))
    print("  top event tags:", tags.most_common(15))
    # one market per event (to limit near-duplicates)
    one = {}
    for day, e, m in sorted(keep, key=lambda x: -float(x[2]["volumeNum"])):
        one.setdefault(e["id"], (day, e, m))
    print("  one highest-volume market per event:", len(one), dict(sorted(collections.Counter(m["endDate"][:7] for _, _, m in one.values()).items())))
    with open(os.path.join(pdir, "tier_one_market_ids.json"), "w") as fh:
        json.dump(sorted(m["id"] for _, _, m in keep), fh)
    rng = random.Random(20261031)
    smp = rng.sample(keep, min(n, len(keep)))
    out = [{"market_id": m["id"], "event_id": e["id"], "event_title": e.get("title"), "question": m.get("question"),
            "description_first_400": (m.get("description") or "")[:400], "description_chars": len(m.get("description") or ""),
            "startDate": m.get("startDate"), "endDate": m.get("endDate"), "closedTime": m.get("closedTime"),
            "outcomes": m.get("outcomes"), "outcomePrices": m.get("outcomePrices"), "volumeNum": m.get("volumeNum"),
            "negRisk": m.get("negRisk"), "clobTokenIds": m.get("clobTokenIds"), "slug": m.get("slug"),
            "tags": [t.get("label") for t in e.get("tags") or []]} for _, e, m in smp]
    with open(os.path.join(pdir, "samples_tier_one_markets.json"), "w") as fh:
        json.dump(out, fh, indent=1)
    for s in out:
        print("   -", s["endDate"][:10], s["outcomePrices"], round(float(s["volumeNum"])), "|", (s["question"] or "")[:100])


if __name__ == "__main__":
    main()
