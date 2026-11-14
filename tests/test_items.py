"""PLAN 3.3 item rule on made-up events and prices. No network."""
import json
import math
import random
from collections import Counter

import pytest

from pipeline import config
from pipeline import families as fam
from pipeline import items as it
from pipeline import polymarket as pm


def mk_market(mid, end="2026-11-12T12:00:00Z", start="2026-10-01T00:00:00Z", closed=False, closed_time=None,
              outcomes='["Yes", "No"]', question=None, description="Resolves Yes if the thing happens."):
    return {"id": str(mid), "question": question or f"Will thing {mid} happen?", "conditionId": f"0xc{mid}",
            "description": description, "outcomes": outcomes,
            "clobTokenIds": json.dumps([f"y{mid}", f"n{mid}"]), "startDate": start, "endDate": end,
            "closed": closed, "closedTime": closed_time}


def mk_event(eid, markets, title=None, tags=(), series=False, neg_risk=False, description="Event rules."):
    return {"id": str(eid), "title": title or f"Event {eid}", "slug": f"event-{eid}",
            "tags": [{"id": str(i), "label": lab, "slug": lab.lower()} for i, lab in tags],
            "markets": markets, "negRisk": neg_risk, "series": series, "description": description}


def price(q):
    return {"q": q, "t": 1, "n_points": 3}


# ---------------------------------------------------------------- small rules

def test_q_percent_rounds_half_up():
    assert [it.q_percent(x) for x in (0.045, 0.0449, 0.125, 0.5, 0.955, 0.0001)] == [5, 4, 13, 50, 96, 0]


def test_clean_description_deletes_appended_headed_paragraphs():
    text = ("Main rules.\n\nMore rules.\n\nNote: glitches do not count.\n\nUpdate (3 Nov): x.\n\n"
            "Clarification - y.")
    cleaned, gone = it.clean_description(text)
    assert cleaned == "Main rules.\n\nMore rules."
    assert gone == ["Note: glitches do not count.", "Update (3 Nov): x.", "Clarification - y."]


def test_clean_description_keeps_the_first_paragraph_and_ordinary_prose():
    text = "Note: the first paragraph is kept.\n\nNote that this is ordinary.\n\nNotably, so is this."
    assert it.clean_description(text) == (text, [])


def test_market_rule():
    F, W = config.f_datetime("pilot"), config.SETS["pilot"]["W"]

    def why(m, open_at_fetch=True):
        return it.market_exclusion(m, F, W, open_at_fetch)[0]

    assert why(mk_market(1)) is None
    assert why(mk_market(2, outcomes='["A", "B"]')) == "not Yes/No"
    assert why(mk_market(3, start="2026-11-07T00:00:01Z")) == "opened after F"
    assert why(mk_market(4, start="2026-11-07T00:00:00Z")) is None
    assert why(mk_market(5, end="2026-11-19T00:30:00Z")) == "market endDate outside window"
    assert why(mk_market(6, end="2026-11-18T23:59:59Z")) is None
    assert why(mk_market(7, closed=True, closed_time="2026-11-06T10:00:00Z")) == "closed at or before F"
    assert why(mk_market(8, closed=True, closed_time="2026-11-07T10:00:00Z")) == "closed at the pilot fetch"
    assert why(mk_market(9, closed=True, closed_time="2026-11-07T10:00:00Z"), open_at_fetch=False) is None
    assert why(mk_market(10, closed=None)) == "missing time field"



def test_every_set_has_a_tuple_of_ordered_windows():
    for cfg in config.SETS.values():
        assert cfg["W"] and all(len(w) == 2 and w[0] <= w[1] for w in cfg["W"])


def test_pilot_window_has_two_blocks_and_misses_the_scored_windows():
    W = config.SETS["pilot"]["W"]
    assert W == (("2026-11-09", "2026-11-18"), ("2026-12-16", "2026-12-31"))
    days = pm.window_days(W)
    assert len(days) == 26 and days[0] == "2026-11-09" and days[-1] == "2026-12-31"
    assert "2026-11-19" not in days and "2026-12-15" not in days and "2026-12-16" in days
    scored = (config.RETRO_W, config.PROSPECTIVE_W)
    assert not any(it.in_windows(d, scored) for d in days)

    F = config.f_datetime("pilot")

    def why(end):
        return it.market_exclusion(mk_market(1, end=end), F, W, True)[0]

    assert why("2026-12-15T23:59:59Z") == "market endDate outside window"
    assert why("2026-12-16T00:00:00Z") is None
    assert why("2026-12-31T23:59:59Z") is None
    assert why("2027-01-01T00:00:00Z") == "market endDate outside window"
    cfg = config.SETS["pilot"]
    dec = mk_event(20, [mk_market(20, end="2026-12-20T12:00:00Z")])
    assert it.event_exclusion(dec, cfg) is None
    dec_and_prospective = mk_event(21, [mk_market(21, end="2026-12-20T12:00:00Z"),
                                        mk_market(22, end="2026-12-10T12:00:00Z")])
    assert it.event_exclusion(dec_and_prospective, cfg).endswith("(rule 13)")


def test_event_exclusions():
    cfg = config.SETS["pilot"]
    assert it.event_exclusion(mk_event(1, [mk_market(1)]), cfg) is None
    assert it.event_exclusion(mk_event(2, [mk_market(2)], tags=[(21, "Crypto")]), cfg).endswith("(rule 1)")
    assert it.event_exclusion(mk_event(3, [mk_market(3)]), cfg, frozenset({"3"})).startswith("event in an")
    assert it.event_exclusion(mk_event(4, [mk_market(4)], series=True), cfg) == "series event (rule 2)"
    assert it.event_exclusion(mk_event(5, [mk_market(5)], tags=[(901, "Weekly")]), cfg) == "template tag (rule 2)"
    assert it.event_exclusion(mk_event(6, [mk_market(6)], title="Margin of victory in X"), cfg) == \
        "secondary event (rule 2)"
    two = mk_event(7, [mk_market(7), mk_market(8, end="2026-11-20T12:00:00Z")])
    assert it.event_exclusion(two, cfg).endswith("(rule 13)")


def test_office_uses_tags_in_senate_governor_house_order():
    e = mk_event(1, [], title="Texas", tags=[(902, "House Elections"), (903, "Governor Elections")])
    assert fam.office(e) == "Governor"
    assert fam.office(mk_event(2, [], title="TX-23 race")) == "House"


# ---------------------------------------------------------------- pool

def test_build_pool_rules():
    events = {
        "10": mk_event(10, [mk_market(10), mk_market(11, question="Will Senator X die before 15 November?")]),
        "12": mk_event(12, [mk_market(12, description="")], description="Event-level rules."),
        "13": mk_event(13, [mk_market(13, description="Rules.\n\nNote: glitches do not count.")]),
        "14": mk_event(14, [mk_market(14)]),
        "15": mk_event(15, [mk_market(15)]),
    }
    prices = {f"y{i}": price(0.4) for i in (10, 11, 12, 13, 15)}
    prices["y14"] = {"q": None, "t": None, "n_points": 0}
    by_hand = {"families": {"10": "Family A"}, "exclude": {"15": "needs the deleted paragraph"},
               "ethics_readmit": {}}
    pool, counts, deleted, flagged = it.build_pool(events, prices, "pilot", by_hand)
    got = {c["market_id"]: c for c in pool}
    assert set(got) == {"10", "12", "13"}
    assert flagged == ["11"]
    assert got["10"]["family"] == "Family A"
    assert got["12"]["description_source"] == "event" and got["12"]["description"] == "Event-level rules."
    assert got["13"]["description"] == "Rules." and got["13"]["n_deleted_paragraphs"] == 1
    assert deleted == {"13": ["Note: glitches do not count."]}
    assert got["10"]["q_pct"] == 40 and got["10"]["yes_token"] == "y10"
    # PLAN 6.8 count of markets priced at F: market 11 has a price, so it counts although rule 11 removes it
    assert (got["10"]["n_priced"], got["12"]["n_priced"]) == (2, 1)
    assert counts["market excluded: no hourly price in the 24 hours before F (rule 4)"] == 1
    assert counts["market excluded: by hand (rule 6)"] == 1

    by_hand["ethics_readmit"] = {"11": "not about the death or health of a named person"}
    pool2, *_ = it.build_pool(events, prices, "pilot", by_hand)
    assert "11" in {c["market_id"] for c in pool2}

    by_hand["ethics_exclude_events"] = {"13": "ranks the deaths of named people, in words the pattern misses"}
    pool3, counts3, *_ = it.build_pool(events, prices, "pilot", by_hand)
    assert {c["market_id"] for c in pool3} == {"10", "11", "12"}
    assert counts3["market excluded: by hand, death or health of a named person (rule 11)"] == 1
    for key in ("families", "exclude", "ethics_readmit", "ethics_exclude_events"):
        with pytest.raises(ValueError, match="99"):
            it.build_pool(events, prices, "pilot", {**by_hand, key: {"99": "mistyped ID"}})

    with pytest.raises(RuntimeError):
        it.build_pool(events, {k: v for k, v in prices.items() if k != "y10"}, "pilot", by_hand)
    with pytest.raises(RuntimeError):
        it.build_pool(events, {**prices, "y10": {"error": "timeout"}}, "pilot", by_hand)


def test_mirror_pair_rule():
    """PLAN 6.8 as DECIDED on 11 November 2026: two items of one negRisk event whose title names an election, no
    other market of the event priced at F, and prices at F that sum to at least 90 points."""
    def pair(eid, a, b, title="Mayor of Springfield election", neg_risk=True, n_priced=2):
        return [{"event_id": eid, "event_title": title, "neg_risk": neg_risk, "n_priced": n_priced, "q_pct": q}
                for q in (a, b)]
    items = (pair("1", 55, 40) + pair("2", 50, 40) + pair("3", 45, 44)
             + pair("4", 60, 35, title="Bitcoin above 100k on 1 December?") + pair("5", 60, 35, neg_risk=False)
             + pair("6", 60, 35, n_priced=3) + pair("7", 60, 35)[:1])
    assert config.MIRROR_MIN_SUM == 90
    assert it.mirror_events(items) == {"1", "2"}
    out = it.finish([dict(c, market_id=str(100 + i)) for i, c in enumerate(items)], "pilot", seed=1)
    assert sorted(c["event_id"] for c in out if c["mirror"]) == ["1", "1", "2", "2"]
    assert all(c["n_priced"] in (2, 3) for c in out)
    # a pool without titles or priced counts, like synthetic_pool, flags no pair
    assert not it.mirror_events([{k: v for k, v in c.items() if k != "n_priced"} for c in items])


# ---------------------------------------------------------------- quota

def synthetic_pool(seed=1, n_events=60, n_families=9):
    r = random.Random(seed)
    pool, mid = [], 1000
    for e in range(n_events):
        family = fam.US if e % n_families == 0 else f"family {e % n_families}"
        us = family == fam.US
        office = r.choice(["Senate", "House", "Governor"]) if us else None
        k = r.randint(1, 4)
        for _ in range(k):
            mid += 1
            pool.append({"event_id": str(100 + e), "market_id": str(mid), "q_pct": r.randint(1, 99),
                         "family": family, "us": us, "office": office, "neg_risk": k == 2, "n_markets": k,
                         "condition_id": f"0x{mid}"})
    return pool


def test_largest_n_and_allocate():
    avail = {"A": 30, "B": 5, "C": 5, "D": 5, "E": 5}
    assert it.largest_n(avail, 0.25) == 26
    assert it.allocate(avail, 26, 0.25, seed=1) == {"A": 6, "B": 5, "C": 5, "D": 5, "E": 5}
    alloc = it.allocate({"A": 7, "B": 7, "C": 7, "D": 7, "E": 2}, 20, 0.25, seed=1)
    assert sum(alloc.values()) == 20 and max(alloc.values()) <= 5 and alloc["E"] == 1
    assert it.largest_n({"A": 100}, 0.25) == 0


def test_take_by_office_is_proportional():
    members = [{"office": o, "market_id": str(i)}
               for i, o in enumerate(["Senate"] * 6 + ["House"] * 3 + ["Governor"])]
    got = Counter(m["office"] for m in it.take_by_office(members, 5, seed=1))
    assert got["Senate"] == 3 and got["House"] + got["Governor"] == 2


def test_select_respects_the_quota_rules():
    pool = synthetic_pool()
    items, log = it.select(pool, "pilot")
    n = len(items)
    assert n == min(50, log["narrow"]["largest_n_under_cap"]) or "wide" in log
    assert max(Counter(c["family"] for c in items).values()) <= math.floor(config.FAMILY_CAP * n)
    per_event = Counter(c["event_id"] for c in items)
    assert max(per_event.values()) <= config.MAX_PASSES
    assert all(per_event[c["event_id"]] == 1 for c in items if c["us"])
    lo, hi = log["band_used"]
    assert all(lo <= c["q_pct"] <= hi for c in items)
    assert [c["item_id"] for c in items] == [f"pil{i:03d}" for i in range(1, n + 1)]
    assert set(items[0]) == set(it.ITEM_FIELDS)
    shuffled = pool[:]
    random.Random(7).shuffle(shuffled)
    assert it.select(shuffled, "pilot")[0] == items


def test_thresholds_are_balanced_in_the_nested_pilot_subsets():
    items, _ = it.select(synthetic_pool(n_events=120), "pilot")
    assert len(items) == 50
    for name, size, each in (("sub10", 10, 2), ("sub20", 20, 4)):
        sub = [c for c in items if name in c["subsets"]]
        assert len(sub) == size
        assert Counter(c["t"] for c in sub) == {t: each for t in config.T_VALUES}
    assert Counter(c["t"] for c in items) == {t: 10 for t in config.T_VALUES}
    assert all("sub20" in c["subsets"] for c in items if "sub10" in c["subsets"])


def test_second_market_of_an_event_comes_after_every_first_market_of_its_family():
    pool = synthetic_pool(n_events=40, n_families=4)
    items, log = it.select(pool, "pilot")
    lo, hi = log["band_used"]
    events_in_band = Counter()
    for f, e in {(c["family"], c["event_id"]) for c in pool if lo <= c["q_pct"] <= hi}:
        events_in_band[f] += 1
    later = {c["family"] for c in items if c["pass"] > 1}
    assert later
    for f in later:
        assert sum(1 for c in items if c["family"] == f and c["pass"] == 1) == events_in_band[f]


# ---------------------------------------------------------------- Polymarket helpers

def test_price_from_history_uses_the_last_hourly_point_in_24_hours():
    f = config.f_unix("pilot")
    hist = {"history": [{"t": f - 90000, "p": 0.9}, {"t": f - 7200, "p": 0.3}, {"t": f - 3600, "p": 0.35},
                        {"t": f + 60, "p": 0.99}]}
    assert pm.price_from_history(hist, f) == {"q": 0.35, "t": f - 3600, "n_points": 2}
    assert pm.price_from_history({"history": [{"t": f - 90000, "p": 0.9}]}, f)["q"] is None


def test_price_history_never_caches_a_point_after_F(tmp_path, monkeypatch):
    f = config.f_unix("pilot")
    reply = {"history": [{"t": f - 7200, "p": 0.3}, {"t": f - 3600, "p": 0.35}, {"t": f + 1900, "p": 0.987}]}
    monkeypatch.setattr(pm, "get", lambda url, **kw: json.dumps(reply).encode())
    hist = pm.price_history("tok", f, tmp_path)
    cached = json.loads((tmp_path / "tok.json").read_text())
    assert hist == cached and cached["points_after_F_dropped"] == 1
    assert max(p["t"] for p in cached["history"]) <= f
    (tmp_path / "old.json").write_text(json.dumps(reply))   # a file cached before the trim existed
    assert pm.price_history("old", f, tmp_path, network=False)["points_after_F_dropped"] == 1
    assert "0.987" not in (tmp_path / "old.json").read_text()
    assert pm.price_from_history(hist, f)["q"] == 0.35


def test_split_event_withholds_outcome_fields():
    e = mk_event(1, [dict(mk_market(1), outcomePrices='["1", "0"]', volume="5")])
    e["volume"] = 10
    kept, held = pm.split_event(e)
    assert "outcomePrices" not in kept["markets"][0] and "volume" not in kept
    assert held["markets"]["1"]["outcomePrices"] == '["1", "0"]' and held["event"]["volume"] == 10
    assert kept["series"] is False and kept["tags"] == []


def test_fetch_day_guard():
    assert pm.check_fetch_day("pilot", "2026-11-07") == "2026-11-07"
    with pytest.raises(pm.FetchDayError):
        pm.check_fetch_day("pilot", "2026-11-08")
    with pytest.raises(pm.FetchDayError):
        pm.check_fetch_day("retro", "2026-11-07")


def test_trade_count_follows_the_v2_cursor(monkeypatch):
    """Data API v2 wraps rows in data, pages with next_cursor and refuses offset (PLAN 3.3 rule 4 CHECK)."""
    f_unix = 1_000_000
    pages = {
        None: {"data": [{"timestamp": f_unix + 50, "proxy_wallet": "0xw", "size": 3},
                        {"timestamp": f_unix, "name": "n"}, {"price": 0.4}],
               "pagination": {"has_more": True, "next_cursor": "c/2+x", "limit": 3}},
        "c/2+x": {"data": [{"timestamp": f_unix - 10}, {"timestamp": f_unix - 99}],
                  "pagination": {"has_more": False, "next_cursor": None, "limit": 3}},
    }
    urls = []

    def fake_get(url, tries=5, timeout=60):
        urls.append(url)
        from urllib.parse import parse_qs, urlsplit
        q = parse_qs(urlsplit(url).query)
        assert "offset" not in q and "market" not in q and q["condition"] == ["0xabc"]
        return json.dumps(pages[q.get("cursor", [None])[0]]).encode()

    monkeypatch.setattr(pm, "get", fake_get)
    monkeypatch.setattr(pm.time, "sleep", lambda s: None)
    r = pm.trade_count("0xabc", f_unix, limit=3)
    assert urls[0].startswith(config.DATA_TRADES + "?") and "/v2/" in config.DATA_TRADES
    assert "limit=3" in urls[0] and "cursor=c%2F2%2Bx" in urls[1] and len(urls) == 2
    assert (r["trades_seen"], r["trades_at_or_before_F"], r["rows_without_timestamp"]) == (4, 3, 1)
    assert r["reached_first_trade"] is True and r["page_sizes"] == [3, 2]
    assert not {"proxy_wallet", "name", "size", "price"} & set(json.dumps(r).split('"'))

    pages[None] = {"data": None, "pagination": {"has_more": False, "next_cursor": None}}
    urls.clear()
    r = pm.trade_count("0xabc", f_unix)
    assert (r["trades_seen"], r["reached_first_trade"], r["page_sizes"]) == (0, True, [0])

    pages[None] = ["v1 shape"]
    assert pm.trade_count("0xabc", f_unix)["error"] == "unexpected reply"
