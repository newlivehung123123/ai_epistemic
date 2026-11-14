"""Count Manifold resolved binary markets closing in a window.

Run with python3 -I.
Usage: python3 -I mf_count.py <newest_pages_dir> <resolve_date_pages_dir> <start> <end> <min_traders> [extra_dirs...]
"""
import collections
import datetime
import glob
import gzip
import json
import os
import sys


def load(d):
    out = {}
    for p in sorted(glob.glob(os.path.join(d, "*.json.gz"))):
        for m in json.load(gzip.open(p)):
            out[m["id"]] = m
    return out


def ms(s, end=False):
    t = datetime.datetime.fromisoformat(s + ("T23:59:59.999+00:00" if end else "T00:00:00+00:00"))
    return int(t.timestamp() * 1000)


def mon(t):
    return datetime.datetime.fromtimestamp(t / 1000, datetime.timezone.utc).strftime("%Y-%m")


def main():
    newest, resdate, start, end, k = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4], int(sys.argv[5])
    extra = sys.argv[6:]  # further page dirs, e.g. markets created before the newest coverage
    a, b = ms(start), ms(end, True)
    allm = load(newest)
    print("markets loaded (newest pages):", len(allm))
    for d in extra:
        e = load(d)
        print("extra dir", os.path.basename(d.rstrip('/')), len(e), "new ids", len(set(e) - set(allm)))
        allm.update(e)
    oldest = min(m["createdTime"] for m in allm.values())
    print("oldest createdTime covered:", mon(oldest), datetime.datetime.fromtimestamp(oldest / 1000, datetime.timezone.utc))
    inwin = [m for m in allm.values() if m.get("closeTime") and a <= m["closeTime"] <= b]
    print("closeTime in window, any resolution, any traders:", len(inwin))
    print("  resolution counts:", collections.Counter(m.get("resolution") for m in inwin))
    yn = [m for m in inwin if m.get("resolution") in ("YES", "NO")]
    print("  YES/NO only:", len(yn))
    keep = [m for m in yn if (m.get("uniqueBettorCount") or 0) >= k]
    print(f"  YES/NO and uniqueBettorCount >= {k}:", len(keep))
    print("  by close month:", dict(sorted(collections.Counter(mon(m["closeTime"]) for m in keep).items())))
    print("  YES share:", round(sum(m["resolution"] == "YES" for m in keep) / max(1, len(keep)), 3))
    print("  token:", collections.Counter(m.get("token") for m in keep))
    print("  outcomeType/mechanism:", collections.Counter((m.get("outcomeType"), m.get("mechanism")) for m in keep))
    print("  by creation month:", dict(sorted(collections.Counter(mon(m["createdTime"]) for m in keep).items())))
    for t in (10, 20, 30, 50, 100):
        print(f"  traders >= {t}:", sum((m.get('uniqueBettorCount') or 0) >= t for m in yn))
    # tail check: markets in the resolve-date pages (most recent 2000 resolutions) not in the newest pages
    rd = load(resdate)
    rdk = [m for m in rd.values() if m.get("closeTime") and a <= m["closeTime"] <= b
           and m.get("resolution") in ("YES", "NO") and (m.get("uniqueBettorCount") or 0) >= k]
    missing = [m for m in rdk if m["id"] not in allm]
    print("tail check: resolve-date pages qualifying:", len(rdk), "of which created before newest coverage:", len(missing))
    for m in missing[:10]:
        print("   ", mon(m["createdTime"]), mon(m["closeTime"]), m.get("uniqueBettorCount"), (m.get("question") or "")[:70])
    with open(os.path.join(os.path.dirname(newest.rstrip("/")), "qualifying_ids.json"), "w") as fh:
        json.dump(sorted(m["id"] for m in keep), fh)


if __name__ == "__main__":
    main()
