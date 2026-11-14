"""Tests of pipeline/analysis.py on made-up replies and made-up outcomes only. No test opens data/outcomes."""
import csv
import gzip
import json

import numpy as np
import pytest

import made_up as mu
from pipeline import analysis as an
from pipeline import build, config

B = 200


@pytest.fixture(scope="module")
def made():
    items = mu.make_items()
    units = mu.make_units(mu.make_records(items, mu.Model(lost=0.03, partial=0.05)))
    ctx = an.Context(items_by_set=items, units=units, subsets={}, mask={}, resamples=B)
    y = an.y_array(ctx.items, mu.make_outcomes(items))
    return ctx, items, units, y


@pytest.fixture(autouse=True)
def no_real_outcomes(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "OUTCOMES", tmp_path / "outcomes")


def _v(made):
    return made[0].settings["haiku_off"].v1


# --- the outcome reader -----------------------------------------------------------------------------------------

@pytest.mark.parametrize("set_name,now,opens", [
    ("retro", "2026-11-13T23:59:59+00:00", False), ("retro", "2026-11-14T00:00:00+00:00", True),
    ("prospective", "2026-12-15T23:59:59+00:00", False), ("prospective", "2026-12-16T00:00:00+00:00", True),
    ("pilot", "2030-01-01T00:00:00+00:00", False)])
def test_guard(set_name, now, opens):
    if opens:
        an.guard(set_name, now)
    else:
        with pytest.raises(an.OutcomeGuard):
            an.guard(set_name, now)


def test_read_outcomes_statuses(tmp_path):
    rows = {"m1": ('["1", "0"]', True, None), "m2": ('["0", "1"]', True, None),
            "m3": ('["0.5", "0.5"]', True, None), "m4": ('["1", "0"]', True, '["proposed", "disputed", "resolved"]'),
            "m5": ('["1", "0"]', False, None), "m6": ("not a list", True, None), "m7": ('["0.7", "0.3"]', True, None)}
    markets = [{"id": m, "closed": c, "outcomes": '["Yes", "No"]'} for m, (_, c, _) in rows.items()]
    markets.append({"id": "m8", "closed": True, "outcomes": '["Yes", "No"]'})
    withheld = {"e1": {"event": {}, "markets": {m: {"outcomePrices": p, **({"umaResolutionStatuses": s} if s else {})}
                                                for m, (p, _, s) in rows.items()}}}
    path = tmp_path / "w.json.gz"
    with gzip.open(path, "wt") as f:
        json.dump(withheld, f)
    items = [{"item_id": f"ret00{i}", "event_id": "e1", "market_id": m} for i, m in enumerate(list(rows) + ["m8"], 1)]
    events = {"e1": {"markets": markets}}
    with pytest.raises(an.OutcomeGuard):
        an.read_outcomes("retro", items, now="2026-11-13T23:59:59+00:00", path=tmp_path / "absent.json.gz",
                         events=events)
    got = an.read_outcomes("retro", items, now="2026-11-15T00:00:00+00:00", path=path, events=events)
    assert [(got[f"ret00{i}"]["status"], got[f"ret00{i}"]["y"]) for i in range(1, 9)] == [
        ("resolved", 1), ("resolved", 0), ("fifty_fifty", None), ("disputed", None), ("unresolved", None),
        ("unreadable", None), ("other", None), ("missing", None)]


def test_made_up_outcomes_are_fixed_and_offline(made):
    a, b = an.made_up_outcomes(made[0].items), an.made_up_outcomes(made[0].items)
    assert a == b and {o["y"] for o in a.values()} <= {0, 1} and not config.OUTCOMES.exists()


def test_hand_check_writes_once(made, tmp_path):
    outs, path = an.made_up_outcomes(made[0].items), tmp_path / "hand_check.csv"
    an.hand_check(made[0].items, outs, path)
    with path.open() as f:
        rows = list(csv.reader(f))
    assert rows[0] == list(an.HAND_CHECK_FIELDS) and len(rows) == 1 + an.HAND_CHECK_N
    before = path.read_text()
    assert an.hand_check(made[0].items, outs, path)["rows"] is None and path.read_text() == before


# --- items and measures without outcomes ------------------------------------------------------------------------

def test_half_split_matches_build(made):
    ctx, items = made[0], made[1]
    ids = np.asarray(ctx.items.ids)
    assert set(ids[ctx.items.nf]) == set(build.no_fields_ids("sprint", items))
    assert not (_v(made).halves()["without_fields"] & ~ctx.items.nf).any()


def test_d_is_the_sum_of_its_two_parts(made):
    v = _v(made)
    D, up, down, _ = an.d_est(made[0].boot, v, v.halves()["without_fields"], an.UNITS)
    assert D.point == pytest.approx(up.point + down.point, abs=1e-12)
    assert np.allclose(D.reps["event"], up.reps["event"] + down.reps["event"], equal_nan=True)


def test_holm_counts_tests_without_a_p_value():
    h = an.holm({"a": 0.01, "b": None, "c": 0.04})
    assert len(h) == 3 and h["a"]["threshold"] == pytest.approx(0.05 / 3, abs=1e-6)
    assert h["a"]["reject"] is True and not h["c"]["reject"]


def test_bonett_wright_interval():
    assert list(an.bonett_wright(0.6, 10)) == pytest.approx([-0.111, 0.905], abs=0.005)


# --- the scripted policies of PLAN 9.1 and the closing rule of PLAN 9.3 -----------------------------------------

def test_repeat_and_copy_policies(made):
    ctx, v = made[0], _v(made)
    nf = v.halves()["without_fields"]
    rep = an.policy_ests(ctx.boot, ctx.items, an.policy_view(ctx.items, v, "repeat"), nf)
    assert all(rep[k].point == pytest.approx(0, abs=1e-12) for k in ("D", "w_m", "w_h", "S"))
    cop = an.policy_ests(ctx.boot, ctx.items, an.policy_view(ctx.items, v, "copy"), nf)
    assert cop["w_m"].point == pytest.approx(1) and cop["w_h"].point == pytest.approx(1)
    assert cop["S"].point == pytest.approx(0, abs=1e-12)


def test_follow_policy_D_is_the_clipped_shift(made):
    ctx, v = made[0], _v(made)
    nf = v.halves()["without_fields"]
    ok = nf & np.isfinite(v.p1)
    for k in an.FOLLOW_K:
        D = an.policy_ests(ctx.boot, ctx.items, an.policy_view(ctx.items, v, "follow", k=k), nf)["D"]
        want = np.mean(np.clip(v.p1[ok] + k, 0, 1) - np.clip(v.p1[ok] - k, 0, 1))
        assert D.point == pytest.approx(want, abs=1e-9) and D.point <= 2 * k + 1e-12


def test_ideal_policy_weight_and_gain(made):
    ctx, v, y = made[0], _v(made), made[3]
    nf = v.halves()["without_fields"] & ctx.items.in_set["retro"]
    w = an.w_star_point(ctx.items, v, y, nf)
    wm, _ = an.weight_est(ctx.boot, ctx.items, an.policy_view(ctx.items, v, "ideal", w=w), "market", nf)
    assert wm.point == pytest.approx(w, rel=1e-9)
    g = [an.gain_est(ctx.boot, an.policy_view(ctx.items, v, "ideal", w=x), y, nf).point for x in (w - 0.05, w, w + 0.05)]
    assert g[1] >= max(g[0], g[2]) - 1e-12


def _est(centre, sd, seed=0):
    r = np.random.default_rng(seed).normal(centre, sd, 2000)
    return an.Est(centre, {"event": r, "family": r.copy()}, 100)


def test_closing_rule():
    D0, S, g = _est(0.0, 0.005), _est(0.3, 0.05, 1), _est(0.01, 0.002, 2)
    assert an.closing(D0, S, g)["passes"] is True
    assert an.closing(_est(0.1, 0.005), S, g)["fails"] == ["H2"]
    flat = an.Est(0.0, {"event": np.zeros(2000), "family": np.zeros(2000)}, 100)
    assert an.closing(D0, S, flat)["fails"] == ["market-arm Brier gain above 0"]
    r = an.closing(D0, None, g)
    assert r["passes"] is None and r["not_available"] == ["S above 0"]


# --- scoring ----------------------------------------------------------------------------------------------------

def test_pav_loss_matches_isotonic_regression():
    from sklearn.isotonic import IsotonicRegression
    rng = np.random.default_rng(3)
    x = np.sort(rng.choice(np.linspace(0.02, 0.98, 15), 300))
    y = (rng.random(300) < x).astype(float)
    w = rng.integers(1, 4, 300).astype(float)
    vals, inv = np.unique(x, return_inverse=True)
    gw = np.bincount(inv, weights=w, minlength=len(vals))
    gy = np.bincount(inv, weights=w * y, minlength=len(vals))
    fit = IsotonicRegression().fit(x, y, sample_weight=w).predict(x)
    assert an._pav_loss(gw.tolist(), gy.tolist()) == pytest.approx(float(np.sum(w * (y - fit) ** 2)), abs=1e-9)


def test_corp_identity_and_signs_in_every_resample(made):
    ctx, v, y = made[0], _v(made), made[3]
    sc, ok = an._scores(ctx.boot, ctx.items, v.p1, y, ctx.items.in_set["retro"])
    e = {}
    an.corp_block(ctx.boot, v.p1, y, ok, sc["brier"], ests=e)
    assert sc["brier"].point == pytest.approx(e["mcb"].point - e["dsc"].point + e["unc"].point, abs=1e-8)
    for k in ("mcb", "dsc"):
        assert e[k].point >= -1e-9 and np.all(e[k].reps["event"] >= -1e-9)
    assert np.allclose(sc["brier"].reps["event"], e["mcb"].reps["event"] - e["dsc"].reps["event"] + e["unc"].reps["event"])


def test_bss_reference_is_the_base_rate_forecast(made):
    ctx, v, y = made[0], _v(made), made[3]
    mask = ctx.items.in_set["retro"]
    sc, ok = an._scores(ctx.boot, ctx.items, v.p1, y, mask)
    c = y[mask & np.isfinite(y)].mean()
    want = 1 - np.mean((v.p1[ok] - y[ok]) ** 2) / np.mean((y[ok] - c) ** 2)
    assert sc["bss_base_rate"].point == pytest.approx(want, abs=1e-12)


def test_auc_matches_sklearn(made):
    from sklearn.metrics import roc_auc_score
    ctx, v, y = made[0], _v(made), made[3]
    ok = ctx.items.in_set["retro"] & np.isfinite(v.p1) & np.isfinite(y)
    assert an.auc_est(ctx.boot, v.p1, y, ok).point == pytest.approx(roc_auc_score(y[ok], v.p1[ok]), abs=1e-9)


def test_caving_identity(made):
    ctx, v, y = made[0], _v(made), made[3]
    cav = an.costs_block(ctx.boot, ctx.items, v, y, v.halves()["without_fields"])["caving"]
    total = cav["direction_term"]["estimate"] + cav["size_term"]["estimate"]
    assert cav["mean_accuracy_cost_of_enthusiast_and_skeptic"]["estimate"] == pytest.approx(total, abs=3e-6)


# --- both stages end to end -------------------------------------------------------------------------------------

def test_score_with_injected_outcomes(made):
    desc, sc = an.score(items_by_set=made[1], units=made[2], resamples=100, subsets={}, mask={},
                        outcomes=mu.make_outcomes(made[1]))
    assert len(desc["holm_h1"]) == 11 and sc["scored_sets"] == ["retro", "prospective"]
    assert "hand_check" not in sc and not config.OUTCOMES.exists()
    json.dumps(desc, allow_nan=False)
    json.dumps(sc, allow_nan=False)
    pol = sc["settings"]["haiku_off"]["retro"]["policies"]
    assert {"S above 0", "market-arm Brier gain above 0"} <= set(pol["repeat"]["closing_rule"]["fails"])
    assert "S above 0" in pol["copy"]["closing_rule"]["fails"]


def test_score_before_the_outcome_dates_scores_nothing(made):
    desc, sc = an.score(items_by_set=made[1], units=made[2], resamples=50, subsets={}, mask={},
                        now="2026-11-13T12:00:00+00:00")
    assert sc["scored_sets"] == [] and sum("stay closed" in n for n in sc["notes"]) == 2
    assert "hand_check" not in sc


def test_stub_score_uses_made_up_outcomes(made):
    _, sc = an.score(stub=True, items_by_set=made[1], units=made[2], resamples=50, subsets={}, mask={})
    assert sc["outcome_source"] == "made up for a stub run" and not config.OUTCOMES.exists()
