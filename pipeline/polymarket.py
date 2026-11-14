"""Free public Polymarket reads: Gamma events by scheduled end date, CLOB hourly prices, Data API v2 trade counts.

Only the fields named in KEEP_EVENT, KEEP_MARKET and KEEP_TAG reach data/raw. Every other field (outcome
prices, resolution status, volumes, current prices and the rest) goes to data/outcomes for a scored set and
is dropped for the pilot. Nothing in this module prints a withheld field or a trade's contents.
"""
from __future__ import annotations

import datetime as dt
import json
import shutil
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed

from pipeline import config
from pipeline.util import UTC, now_utc, read_json, write_json

KEEP_MARKET = ("id", "question", "conditionId", "slug", "description", "resolutionSource", "outcomes",
               "clobTokenIds", "startDate", "startDateIso", "acceptingOrdersTimestamp", "createdAt", "endDate",
               "endDateIso", "closedTime", "closed", "active", "archived", "negRisk", "groupItemTitle",
               "groupItemThreshold", "questionID")
KEEP_EVENT = ("id", "ticker", "slug", "title", "description", "startDate", "endDate", "creationDate",
              "createdAt", "closed", "active", "archived", "negRisk", "negRiskMarketID", "seriesSlug")
KEEP_TAG = ("id", "label", "slug")


class FetchDayError(RuntimeError):
    pass


def get(url: str, tries: int = 5, timeout: int = 60) -> bytes:
    """GET with retries. A 429 waits longer; any other 4xx is raised at once."""
    last = None
    for attempt in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": config.USER_AGENT,
                                                       "Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read()
        except urllib.error.HTTPError as err:
            last = err
            if err.code == 429:
                time.sleep(15 * (attempt + 1))
                continue
            if 400 <= err.code < 500:
                raise
        except Exception as err:  # network errors and timeouts
            last = err
        time.sleep(2 + attempt * 3)
    raise last


def split_event(e: dict) -> tuple[dict, dict]:
    """Split one Gamma event into the kept fields and everything else."""
    kept = {k: e[k] for k in KEEP_EVENT if k in e}
    kept["series"] = bool(e.get("series"))
    kept["tags"] = [{k: t.get(k) for k in KEEP_TAG} for t in (e.get("tags") or [])]
    kept["markets"] = []
    withheld_markets = {}
    for m in e.get("markets") or []:
        kept["markets"].append({k: m[k] for k in KEEP_MARKET if k in m})
        withheld_markets[str(m.get("id"))] = {k: v for k, v in m.items() if k not in KEEP_MARKET}
    withheld = {"event": {k: v for k, v in e.items() if k not in KEEP_EVENT and k not in ("tags", "markets")},
                "markets": withheld_markets}
    return kept, withheld


def days(lo: str, hi: str) -> list[str]:
    d, end = dt.date.fromisoformat(lo), dt.date.fromisoformat(hi)
    out = []
    while d <= end:
        out.append(d.isoformat())
        d += dt.timedelta(days=1)
    return out


def window_days(ws) -> list[str]:
    """Every UTC day of the windows in ws, in order (the W of a set is a tuple of windows, PLAN 3.2)."""
    return [d for w in ws for d in days(*w)]


def check_fetch_day(set_name: str, today: str | None = None) -> str:
    cfg = config.SETS[set_name]
    today = today or dt.datetime.now(UTC).date().isoformat()
    if today not in cfg["fetch_days"]:
        raise FetchDayError(f"The {set_name} fetch may run only on {', '.join(cfg['fetch_days'])} (UTC); "
                            f"today is {today}. For the pilot, change F and fetch_days in pipeline/config.py "
                            f"together.")
    if set_name == "pilot" and cfg["F"][:10] != today:
        raise FetchDayError(f"Pilot F ({cfg['F'][:10]}) must be the day of the pilot fetch ({today}).")
    return today


def fetch_events(set_name: str, refetch: bool = False, log=print) -> dict:
    """Fetch every event whose scheduled end date falls in W (rule 1), one UTC day at a time."""
    cfg = config.SETS[set_name]
    check_fetch_day(set_name)
    out = config.RAW / set_name
    if (out / "fetch_log.txt").exists():
        if not refetch:
            raise FetchDayError(f"{out} already holds a fetch; pass --refetch to move it aside and fetch again.")
        aside = config.RAW / f"{set_name}_superseded_{dt.datetime.now(UTC).strftime('%Y%m%dT%H%M%S')}"
        out.rename(aside)
        log(f"moved the earlier fetch to {aside.name}")
    excl = "".join(f"&exclude_tag_id={t}" for t in config.EXCLUDE_TAG_IDS)
    withheld, lines, total = {}, [], 0
    for closed in cfg["closed_values"]:
        for d in window_days(cfg["W"]):
            offset, n = 0, 0
            win = f"closed={closed}&end_date_min={d}T00:00:00Z&end_date_max={d}T23:59:59.999Z"
            while True:
                raw = get(f"{config.GAMMA_EVENTS}?{win}&limit=100&offset={offset}{excl}")
                data = json.loads(raw).get("data") or []
                page = []
                for e in data:
                    kept, held = split_event(e)
                    page.append(kept)
                    withheld[str(e.get("id"))] = held
                write_json(out / f"closed_{closed}" / f"{d}_off{offset}.json.gz", {"data": page}, gz=True)
                n += len(data)
                time.sleep(0.12)
                if len(data) < 100:
                    break
                offset += 100
            lines.append(f"{d} closed={closed} events={n}")
            total += n
            log(lines[-1])
    if set_name != "pilot":
        write_json(config.OUTCOMES / f"{set_name}_withheld_fields.json.gz", withheld, gz=True)
    (out / "fetch_log.txt").write_text(f"fetched {now_utc()}\n" + "\n".join(lines) + "\n", encoding="utf-8")
    return {"events_listed": total, "days": len(lines)}


def load_events(set_name: str) -> dict:
    """Every fetched event of a set, keyed by event ID (later pages replace earlier copies)."""
    out = config.RAW / set_name
    evs = {}
    for closed in config.SETS[set_name]["closed_values"]:
        for p in sorted((out / f"closed_{closed}").glob("*.json.gz")):
            for e in read_json(p).get("data") or []:
                evs[str(e["id"])] = e
    return evs


def fetch_stamp(set_name: str) -> str | None:
    p = config.RAW / set_name / "fetch_log.txt"
    if not p.exists():
        return None
    return p.read_text(encoding="utf-8").splitlines()[0].replace("fetched ", "")


# ---------------------------------------------------------------- prices (rule 4)

def clob_cache(set_name: str):
    return config.RAW / set_name / "clob"


def price_from_history(hist: dict, f_unix: int) -> dict:
    """Last hourly point at or before F and no older than 24 hours (rule 4). No daily fallback."""
    pts = [p for p in (hist.get("history") or [])
           if isinstance(p, dict) and "t" in p and "p" in p
           and f_unix - config.PRICE_LOOKBACK_S <= int(p["t"]) <= f_unix]
    if not pts:
        return {"q": None, "t": None, "n_points": 0}
    last = max(pts, key=lambda p: int(p["t"]))
    return {"q": float(last["p"]), "t": int(last["t"]), "n_points": len(pts)}


def trim_history(hist: dict, f_unix: int) -> dict:
    """Keep only the points at or before F. The CLOB adds a point at the time of the request even when endTs
    is F, and for a scored set that point can come after the outcome, so it never reaches the cache."""
    keep, after, bad = [], 0, 0
    for p in hist.get("history") or []:
        try:
            t = int(p["t"])
            float(p["p"])
        except (TypeError, KeyError, ValueError):
            bad += 1
            continue
        if t <= f_unix:
            keep.append(p)
        else:
            after += 1
    return {"history": keep, "points_after_F_dropped": after, "malformed_points_dropped": bad}


def price_history(token: str, f_unix: int, cache_dir, network: bool = True) -> dict:
    """The CLOB hourly history for the 24 hours before F, cached per token with every point after F removed.
    A failed request is not cached, so running the stage again retries it."""
    path = cache_dir / f"{token}.json"
    if path.exists():
        hist = read_json(path)
        if "points_after_F_dropped" not in hist:   # cached before trim_history existed
            hist = trim_history(hist, f_unix)
            write_json(path, hist)
        return hist
    if not network:
        return {"error": "not fetched"}
    url = (f"{config.CLOB_HISTORY}?market={token}&startTs={f_unix - config.PRICE_LOOKBACK_S}"
           f"&endTs={f_unix}&fidelity={config.PRICE_FIDELITY}")
    try:
        hist = json.loads(get(url, tries=4, timeout=30))
    except Exception as err:
        return {"error": f"{type(err).__name__}: {err}"}
    if not isinstance(hist, dict):
        return {"error": "unexpected reply"}
    hist = trim_history(hist, f_unix)
    write_json(path, hist)
    return hist


def fetch_prices(set_name: str, tokens, workers: int = 4, log=print) -> dict:
    f_unix = config.f_unix(set_name)
    cache = clob_cache(set_name)
    cache.mkdir(parents=True, exist_ok=True)
    todo = sorted({t for t in tokens if not (cache / f"{t}.json").exists()})
    errors = {}
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futs = {pool.submit(price_history, t, f_unix, cache): t for t in todo}
        for i, fut in enumerate(as_completed(futs), 1):
            res = fut.result()
            if "error" in res:
                errors[futs[fut]] = res["error"]
            if i % 100 == 0:
                log(f"  prices requested {i} of {len(todo)}")
    return {"tokens": len(set(tokens)), "requested": len(todo), "errors": errors}


def load_prices(set_name: str, tokens) -> dict:
    """Prices at F from the cache only (no network)."""
    f_unix = config.f_unix(set_name)
    cache = clob_cache(set_name)
    out = {}
    for t in tokens:
        hist = price_history(t, f_unix, cache, network=False)
        out[t] = {"error": hist["error"]} if "error" in hist else price_from_history(hist, f_unix)
    return out


# ---------------------------------------------------------------- trade counts (PLAN 3.3 rule 4 CHECK)

def trade_count(condition_id: str, f_unix: int, limit: int = 1000, max_pages: int = 20) -> dict:
    """Counts only. Pages through the Data API v2 trades of one market with the cursor of each page, and keeps
    no row: no wallet, name, side, size, price or outcome field is stored or printed. The route serves each
    fill once, on its taker side, and drops fills under 0.01 tokens (its defaults)."""
    seen = before = missing_ts = 0
    oldest = newest = None
    sizes = []
    reached_first = False
    cursor = None
    for page in range(max_pages):
        params = {"condition": condition_id, "cursor": cursor} if cursor else {"condition": condition_id,
                                                                                "limit": limit}
        url = f"{config.DATA_TRADES}?{urllib.parse.urlencode(params)}"
        try:
            reply = json.loads(get(url, tries=4, timeout=30))
        except urllib.error.HTTPError as err:
            return {"condition_id": condition_id, "error": f"HTTP {err.code} on page {page + 1}",
                    "trades_seen": seen, "trades_at_or_before_F": before, "page_sizes": sizes}
        rows = reply.get("data", "absent") if isinstance(reply, dict) else "absent"
        if rows is None:
            rows = []
        if not isinstance(rows, list):
            return {"condition_id": condition_id, "error": "unexpected reply", "page_sizes": sizes}
        sizes.append(len(rows))
        for r in rows:
            t = r.get("timestamp") if isinstance(r, dict) else None
            if t is None:
                missing_ts += 1
                continue
            t = int(t)
            seen += 1
            before += t <= f_unix
            oldest = t if oldest is None else min(oldest, t)
            newest = t if newest is None else max(newest, t)
        pagination = reply.get("pagination") or {}
        del rows, reply
        cursor = pagination.get("next_cursor")
        if not cursor or pagination.get("has_more") is False:
            reached_first = True
            break
        time.sleep(0.2)

    def iso(x):
        return None if x is None else dt.datetime.fromtimestamp(x, UTC).isoformat(timespec="seconds")

    return {"condition_id": condition_id, "trades_seen": seen, "trades_at_or_before_F": before,
            "rows_without_timestamp": missing_ts, "reached_first_trade": reached_first, "page_sizes": sizes,
            "oldest_seen": iso(oldest), "newest_seen": iso(newest)}


def move_aside(path) -> None:
    """Keep an earlier output under a dated name instead of deleting it."""
    if path.exists():
        stamp = dt.datetime.now(UTC).strftime("%Y%m%dT%H%M%S")
        shutil.move(str(path), str(path.with_name(f"{path.stem}_superseded_{stamp}{path.suffix}")))
