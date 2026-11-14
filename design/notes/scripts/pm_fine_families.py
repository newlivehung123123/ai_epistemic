"""Fine families, derived-event drop and in-band counts for the retro candidates.

Offline: reads the saved window pages, the candidate list and the saved prices at F.
Uses titles, tags and pre-F prices only; never reads an outcome.
Usage: python3 -I pm_fine_families.py <window_dir> <candidates_json> <prices_json> <end_min> <end_max> <out_json>

Family = one election (one place, one election day) and the events about it; outside
elections, one underlying event or entity; otherwise the event itself. Derived events
(numeric bands, margins, turnout, places below first, sub-national results of one
national race, combos, and markets that resolve on Polymarket's own prices) are
dropped, because each is a slice of a race already in the set. The count then takes
at most k items per event and caps any one family's share of the set.
"""
import collections
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pm_window_yield import load  # noqa: E402

US = "United States general election, 3 Nov"
US_TAGS = {"Midterms", "Nov 4 Elections", "US Election", "Down Ballot", "Mayoral Races", "Ballot Measures",
           "California Midterm", "referendums midterms"}
DERIVED_TAGS = {"Derivatives", "Midterm Combos", "Margin of Victory", "Midterm MOV"}
DERIVED = re.compile(r"margin of victory|vote share|# of seats|lose seats|turnout|most votes ever|hung parliament|"
                     r"coalition wins a majority|\b(2nd|3rd) place|1st place (in|abroad)|combo|odds leader|flips|"
                     r"lose a seat|win by", re.I)
RULES = [  # (family, title regex or None, required tag or None); first match wins
    ("British Columbia municipal elections, 18 Oct", r", BC Mayoral|^(Kelowna|Nanaimo|Richmond|Surrey|Vancouver) Mayoral", None),
    ("British Columbia general election, 24 Oct", r"British Columbia General|Premier of British Columbia", None),
    ("Ontario municipal elections, 26 Oct", r", ON Mayoral|^(Hamilton|Mississauga|Ottawa|Toronto) Mayoral", None),
    ("Manitoba municipal elections, 28 Oct", r", MB Mayoral|^Winnipeg Mayoral", None),
    ("Charlottetown municipal election, 3 Nov", r"PEI Mayoral", None),
    ("Alberta independence referendum, 19 Oct", r"Alberta vote for independence", None),
    ("Yokohama mayoral election, 18 Oct", r"Yokohama", None),
    ("Fukushima governor election, 25 Oct", r"Fukushima", None),
    ("Slovakia regional and municipal elections, 24 Oct", None, "slovakia"),
    ("Bulgaria presidential election, 25 Oct", r"Bulgaria", None),
    ("Serbia parliamentary election, 25 Oct", r"Serbia", None),
    ("Brazil general election second round, 25 Oct", None, "Brazil"),
    ("Israel legislative election, 27 Oct", None, "Israel Election"),
    ("Israel legislative election, 27 Oct", r"Prime Minister of Israel", None),
    ("Tasmania municipal elections, 28 Oct", r"Mayor", "Australia"),
    ("South Africa municipal elections, 4 Nov", None, "South Africa Municipal Elections"),
    ("New Zealand general election, 7 Nov", None, "New Zealand Election"),
    ("AI lab training pause and vetting", r"training pause|resumes training|third party vetting", None),
    ("Google Gemini releases", r"Gemini", None),
    ("Meta model releases", r"Watermelon|Muse Spark", None),
    ("Atlantic hurricane season", r"Isaias|first hurricane form in the Atlantic", None),
    ("Central European river drought", r"Rhine|Danube", None),
    ("Russia-Ukraine front line", r"^Will Russia capture", None),
    ("Israel-Iran incidents", r"stabbing|FlyDubai|Israeli airspace", None),
    ("Kanye West in Russia", r"Kanye West", None),
    ("US fuel prices and policy", r"gas be below|diesel|gas tax", None),
]
BANDS = {"05": (0.05, 0.95), "03": (0.03, 0.97)}


def labels(e):
    return {t.get("label") or "" for t in (e.get("tags") or [])}


def fine_family(e, coarse):
    lab, title = labels(e), e.get("title") or ""
    if coarse == "us_midterms" or lab & US_TAGS:
        return US
    for fam, rx, tag in RULES:
        if (rx is None or re.search(rx, title, re.I)) and (tag is None or tag in lab):
            return fam
    return "event: " + title


def derived(e):
    return bool(labels(e) & DERIVED_TAGS) or bool(DERIVED.search(e.get("title") or ""))


def max_n(avail, cap):
    """Largest N with N = sum over families of min(available items, cap * N)."""
    n = sum(avail.values())
    for _ in range(200):
        nxt = sum(min(a, cap * n) for a in avail.values())
        if abs(nxt - n) < 1e-9:
            break
        n = nxt
    return n


def main():
    wdir, cand, prices, lo, hi, out = sys.argv[1:7]
    evs = load(wdir, lo, hi)
    rows, res = json.load(open(cand)), json.load(open(prices))
    info = {}
    for coarse, d in rows.items():
        for k, ms in d.items():
            pr = (res.get(coarse) or {}).get(k)
            rec = {"coarse": coarse, "family": fine_family(evs[k], coarse), "derived": derived(evs[k]),
                   "title": evs[k].get("title"), "markets": len(ms), "checked": len(pr) if pr else 0}
            for b, (lo_p, hi_p) in BANDS.items():
                rec["in" + b] = (sum(1 for m in pr if m["p"] is not None and lo_p <= m["p"] <= hi_p)
                                 if pr else None)
            info[k] = rec
    with open(out, "w") as fh:
        json.dump(info, fh, ensure_ascii=False, indent=0)

    fams = collections.defaultdict(list)
    for k, r in info.items():
        fams[r["family"]].append(r)
    print(f"candidate events {len(info)}; derived and dropped {sum(r['derived'] for r in info.values())}; "
          f"families {len(fams)} ({sum(1 for f in fams if f.startswith('event: '))} single-event)")
    for b in BANDS:
        lo_p, hi_p = BANDS[b]
        print(f"\n== band {lo_p:.2f} to {hi_p:.2f}")
        table, avail = [], {k_: {} for k_ in (1, 2, 3)}
        for f, rs in fams.items():
            kept = [r for r in rs if not r["derived"]]
            chk = [r for r in kept if r["checked"]]
            for k_ in (1, 2, 3):
                avail[k_][f] = 0.0
                for c in {r["coarse"] for r in kept}:  # midterm races: only a random sample was priced
                    kc = [r for r in kept if r["coarse"] == c]
                    cc = [r for r in kc if r["checked"]]
                    if cc:
                        avail[k_][f] += len(kc) / len(cc) * sum(min(k_, r["in" + b]) for r in cc)
            table.append((avail[3][f], f, len(rs), len(rs) - len(kept), len(kept), len(chk),
                          sum(1 for r in chk if r["in" + b]), avail[1][f]))
        table.sort(reverse=True)
        print("items(cap3) | family | events | derived | kept | priced | priced with >=1 in band | items(cap1)")
        for it3, f, n, dv, kp, ch, ib, it1 in table:
            if it3 >= 6 or not f.startswith("event: "):
                print(f"{it3:7.0f} | {f[:60]} | {n} | {dv} | {kp} | {ch} | {ib} | {it1:.0f}")
        single = [t for t in table if t[1].startswith("event: ") and t[0] < 6]
        print(f"{sum(t[0] for t in single):7.0f} | {len(single)} other single-event families with fewer than 6 items")
        for k_ in (1, 2, 3):
            tot = sum(avail[k_].values())
            line = f"at most {k_} per event: pool {tot:.0f} items (US {avail[k_][US]:.0f})"
            for cap in (0.25, 0.15):
                n = max_n(avail[k_], cap)
                top = max((min(a, cap * n), f) for f, a in avail[k_].items() if f != US)
                line += (f"; cap {cap:.0%} gives N {n:.0f} (US {min(avail[k_][US], cap * n):.0f}, "
                         f"largest other {top[0]:.0f} {top[1][:28]})")
            print(line)
    print("\nwrote", out)


if __name__ == "__main__":
    main()
