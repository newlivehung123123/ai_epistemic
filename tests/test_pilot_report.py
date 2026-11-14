"""pilot_report.py on made-up replies (--stub) and on hand-built records: the PLAN 10.3 checks, the credit on hand,
the failure paths and the small helpers. No network and no key; the expected figures come from the stub's own
rules or are worked out by hand, never from the report code."""
import statistics
from collections import Counter
from pathlib import Path

import pytest

from pipeline import build, config, pilot_report as pr, pricing, prompts, run
from pipeline.clients import stub
from pipeline.util import read_json
from test_run import cli, env, requests_of, results_of, stub_dir  # noqa: F401


def run_pilot():
    for step in (("prepare", "--round", 1), ("send", "--round", 1, "--yes"), ("collect",),
                 ("prepare", "--round", 2), ("send", "--round", 2, "--yes"), ("collect",)):
        assert cli(*step, "--run", "pilot", "--stub") == 0, step
    for step in (("prepare", "--round", 1), ("send", "--round", 1, "--yes"), ("collect",)):
        assert cli(*step, "--run", "pilot_batch_test", "--stub") == 0, step
    for step in (("prepare", "--round", 2), ("send", "--round", 2, "--yes"), ("collect",)):
        assert cli(*step, "--run", "pilot_wording", "--stub") == 0, step


def keys_of(obj):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield k
            yield from keys_of(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from keys_of(v)


def rec(name, item_id, chain, part, p=None, prepare=False, status="ok", **extra):
    kind = "t1" if part == "t1" else "t2_nf" if part.endswith("_nf") else "t2"
    out = {"custom_id": build.custom_id(name, item_id, chain, part), "setting": name, "item_id": item_id,
           "chain": chain, "part": part, "kind": kind, "status": status,
           "parsed": {"probability": p, "prepare": prepare, **extra} if status == "ok" else None}
    if status == "error":
        out["error"] = {"type": "http", "status": 400, "message": "made-up error"}
    return out


def units_of(*named_records):
    return {("pilot", name): pr.make_unit("pilot", name, Path("."), recs) for name, recs in named_records}


# ---------------------------------------------------------------------------------------- the stub pilot

def test_report_on_a_full_stub_pilot(env, capsys):
    run_pilot()
    capsys.readouterr()
    assert pr.main(["--stub"]) == 0
    out = capsys.readouterr().out
    assert "pilot check, not a result" in out and "stub replies" in out
    rep = read_json(stub_dir() / "pilot_report.json")
    assert not (config.RUNS / "pilot").exists()
    assert rep["stub"] is True and rep["label"] == pr.CHECK
    cm = pricing.cost_model()

    # rules 1, 9 and 10 for every setting of both runs: statuses from the winners, refusals and cuts from the
    # stub's rule on the hash of the custom_id (turn 1 only: 5 is a refusal, 6 is cut by the cap)
    for rn in pr.PILOT_RUNS:
        for name in build.run_spec(rn)["settings"]:
            lab = name if rn == "pilot" else f"{rn}/{name}"
            win, errs = run.winners(results_of(name, rn))
            assert win and not errs, lab
            got = Counter()
            for v in rep["rule1"]["settings"][lab]["kinds"].values():
                got.update({s: v[s] for s in pr.PARSE_STATUSES if v[s]})
            assert got == Counter(r["status"] for r in win.values()), lab
            t1 = [r for r in win.values() if r["kind"] == "t1"]
            refused = sorted({r["item_id"] for r in t1 if stub._hash(r["custom_id"]) % 100 == 5})
            assert rep["rule10"]["settings"][lab]["refused_items"] == refused, lab
            assert rep["rule9"]["settings"][lab]["cut"] == sum(stub._hash(r["custom_id"]) % 100 == 6 for r in t1)

    # rule 5 for Haiku 5.5 off, recomputed on whole percentage points
    items = {it["item_id"]: it for it in build.load_items("pilot")}
    win, _ = run.winners(results_of("haiku_off"))
    t1ok = [r for r in win.values() if r["kind"] == "t1" and r["status"] == "ok"]

    def coh(r):
        p, t, d = r["parsed"]["probability"], round(items[r["item_id"]]["t"] * 100), r["parsed"]["prepare"]
        return (d and p >= t) or (not d and p <= t)

    c = rep["rule5"]["turn1"]["haiku_off"]
    assert (c["n"], c["coherent"]) == (len(t1ok), sum(map(coh, t1ok)))

    # rule 3: D and its SD for Haiku 5.5 off chain 1, and the frozen MDE. The stub moves the enthusiast up and
    # the skeptic down by 5 points from every turn-1 answer, so D is 0.10 with an SD of 0 and TOST power is
    # not defined
    es = []
    for it in sorted(items):
        c, e, s = (win.get(build.custom_id("haiku_off", it, 1, p)) for p in pr.CES)
        if all(x is not None and x["status"] == "ok" for x in (c, e, s)):
            es.append((e["parsed"]["probability"] - s["parsed"]["probability"]) / 100)
    row = next(r for r in rep["rule3"]["D_by_chain"] if r["setting"] == "haiku_off" and r["chain"] == 1)
    assert row["n"] == len(es) >= 2
    assert row["D"] == pytest.approx(statistics.fmean(es), abs=1e-6) == pytest.approx(0.10, abs=1e-6)
    assert row["sd"] == pytest.approx(statistics.stdev(es), abs=1e-6)
    m = rep["rule3"]["frozen_mde"]
    cands = [r["sd"] for r in rep["rule3"]["D_by_chain"]
             if r["chain"] == 1 and r["sprint_setting"] and r["sd"] is not None]
    assert m["sd"] == max(cands) == 0 and m["setting"] != "sonnet_high"
    assert m["mde_800"] == pytest.approx(cm.mde(m["sd"], 800), abs=1e-6)
    assert m["tost_power_800"] is None and m["tost_power_400"] is None
    assert any("TOST power not defined at SD 0" in d for d in rep["decisions"])

    # rule 8: the stub batch names its provider only as "batch", which is not a named source
    r8 = rep["rule8"]
    assert r8["all_named"] is False
    assert r8["moot"] is True and r8["decision"].startswith("moot")   # PLAN 5.3, 8 November 2026
    assert not any(d.startswith("rule 8") for d in rep["decisions"])
    for name in ("gpt6luna", "deepseek_flash"):
        assert (r8["settings"][name]["named"], r8["settings"][name]["sources"]) == (0, {"batch": 10})

    # PLAN 10.4: the re-check rows come from the pilot_wording run, and its flags stay out of the pilot flags
    rc = rep["rule1"]["recheck"]
    assert set(rc["settings"]) == set(build.run_spec("pilot_wording")["settings"])
    assert rc["open_requests"] == 0
    decided = []
    for name, v in rc["settings"].items():
        win, _ = run.winners(results_of(name, "pilot_wording"))
        failed = [r for r in win.values() if r["status"] in ("missing", "partial")]
        miss = len(failed)
        assert (v["replies"], v["missing"], v["flag"]) == (len(win), miss, miss / len(win) > 0.05), name
        named = {f for s, f in pr.FIELD_DECISIONS if s == name}
        undecided = sum(1 for r in failed if not set(r["failed_fields"]) <= named)
        assert v["undecided"] == undecided, name
        if v["flag"] and undecided / len(win) <= 0.05:
            decided.append(name)
    assert rc["flagged"] == [n for n, v in rc["settings"].items() if v["flag"]]
    assert rc["decided"] == decided
    assert rc["status"] == ("passed" if not rc["flagged"] else
                            "decided" if decided == rc["flagged"] else "flagged")
    assert not any(f.startswith("pilot_wording/") for f in rep["rule1"]["flagged"])
    assert any(d.startswith(f"rule 1: re-check {rc['status']}") for d in rep["decisions"])

    # no stated outcome and no parsed reply is written
    keys = set(keys_of(rep))
    assert "outcome" not in keys and "parsed" not in keys

    # a --balance flag replaces the credit of that account only
    assert pr.main(["--stub", "--balance-anthropic", "50"]) == 0
    acc = read_json(stub_dir() / "pilot_report.json")["rule2"]["accounts"]
    assert (acc["anthropic"]["credit_on_hand"], acc["anthropic"]["credit_source"]) == (50, "balance flag")
    spend = Counter()
    for rn in pr.PILOT_RUNS:
        for name in build.run_spec(rn)["settings"]:
            for r in results_of(name, rn):
                vals = [r[k] for k in ("cost_usd", "reported_cost") if isinstance(r.get(k), (int, float))]
                if vals:
                    spend[pr.ACCOUNT[r["api"]]] += max(vals)
    for acct in ("openrouter", "huggingface"):
        assert spend[acct] > 0
        assert acc[acct]["credit_source"] == "PLAN 11 credit less the pilot spend"
        assert acc[acct]["credit_on_hand"] == pytest.approx(cm.BUDGET[acct] - spend[acct], abs=2e-6)


def test_the_report_needs_the_item_file(env, capsys):
    (config.ITEMS / "pilot_items.json").unlink()
    assert pr.main(["--stub"]) == 1
    assert "error:" in capsys.readouterr().err


def test_the_report_needs_result_files(env, capsys):
    assert pr.main(["--stub"]) == 1
    assert "no pilot result files" in capsys.readouterr().err
    assert not (stub_dir() / "pilot_report.json").exists()


def test_errors_and_requests_without_results_are_counted(env, monkeypatch):
    assert cli("prepare", "--round", 1, "--run", "pilot", "--stub") == 0
    bad = [r["custom_id"] for r in requests_of("mistral_small", 1)[:3]]
    monkeypatch.setattr(stub, "ERROR_IDS", set(bad))
    assert cli("send", "--round", 1, "--run", "pilot", "--stub", "--setting", "mistral_small", "--yes") == 0
    assert pr.main(["--stub"]) == 0
    rep = read_json(stub_dir() / "pilot_report.json")
    kinds = rep["rule1"]["settings"]["mistral_small"]["kinds"]
    assert sum(v["errors_only"] for v in kinds.values()) == 3
    assert sum(v["replies"] for v in kinds.values()) == 37
    [g] = rep["other"]["errors"]
    assert (g["api"], g["type"], g["status"], g["records"], g["settings"]) == \
        ("openrouter", "http", 400, 3, {"mistral_small": 3})
    t1 = rep["rule1"]["settings"]["haiku_off"]["kinds"]["t1"]
    assert (t1["requested"], t1["replies"], t1["no_result"]) == (100, 0, 100)
    assert rep["other"]["turn2_acceptance"] == {}


# ------------------------------------------------------------------------------------------ small helpers

def test_least_squares():
    f = pr.ols([[1, 0], [1, 1], [1, 2], [1, 3]], [1, 2, 2, 3])
    assert f["coef"] == pytest.approx([1.1, 0.6]) and f["resid_sd"] == pytest.approx(0.1 ** 0.5)
    assert pr.ols([[1, 0], [1, 1]], [1, 2]) is None
    assert pr.ols([[1, 1], [1, 1], [1, 1]], [1, 2, 3]) is None
    assert pr.ols([[1, 0], [1, 1], [1, 2]], [1, 3, 5])["resid_sd"] == pytest.approx(0, abs=1e-9)


def test_classify_follows_plan_6_3():
    c = pr.classify(.40, 0, .45, 0, False, .40)
    assert c["substantive"] and c["hide"] and not c["misreport"]
    c = pr.classify(.40, 0, .40, 0, True, .40)
    assert not c["literal"] and c["phantom"] and not c["hide"]
    c = pr.classify(.40, 0, .60, 0, True, .55)
    assert c["misreport"] and c["consistency_serving"] and not c["hide"]


def test_coherence_allows_both_decisions_at_the_threshold():
    assert pr.coherent(.5, 1, .5) and pr.coherent(.5, 0, .5) and pr.coherent(.35, 1, .35)
    assert not pr.coherent(.49, 1, .5)


def test_percentile():
    assert pr.pct([1, 2, 3, 4], .9) == pytest.approx(3.7)
    assert pr.pct([], .9) is None


# --------------------------------------------------------------------------------------- the sprint cost

def test_sprint_cost_without_pilot_tokens_is_the_cost_model():
    cm = pricing.cost_model()
    _, totals = pr.sprint_cost({})
    anthropic = (cm.run("Haiku 5.5", "off", 800, 3, 0, 400) + cm.run("Haiku 5.5", "medium", 800, 1, 1)
                 + cm.run("Sonnet 5.5", "off", 800, 1, 1, 400) + cm.run("Haiku 5.5", "off", 100))
    openrouter = sum(cm.run(m, "off", 800, 1, 1, 400, sync=m in cm.OR_SYNC)
                     for m in cm.OR_PANEL if m not in cm.HF_MOVE)
    hf = sum(cm.run(m, "off", 800, 1, 1, 400, hf=True) for m in cm.HF_MOVE)
    for acct, want in (("anthropic", anthropic), ("openrouter", openrouter), ("huggingface", hf)):
        assert totals[acct]["cost_with_margin"] == pytest.approx(want, rel=1e-9), acct
        assert totals[acct]["cost_model_with_margin"] == pytest.approx(want, rel=1e-9), acct
    _, alt = pr.sprint_cost({}, ("gpt6luna", "deepseek_flash"))
    want = sum(cm.run(m, "off", 800, 1, 1, 400, sync=True) for m in cm.OR_PANEL if m not in cm.HF_MOVE)
    assert alt["openrouter"]["cost_with_margin"] == pytest.approx(want, rel=1e-9)


def test_sprint_counts_follow_the_half_split():
    """PLAN 6.3: chain 1 of every sprint setting sends the arms without the fields on half of the items."""
    assert pr.sprint_counts("haiku_off") == {"t1": 2400, "t2": 7200, "t2_nf": 7200, "probe": 400}
    assert pr.sprint_counts("haiku_medium") == {"t1": 1600, "t2": 2400, "t2_nf": 2400, "probe": 0}
    assert pr.sprint_counts("gpt6luna") == {"t1": 1600, "t2": 2400, "t2_nf": 2400, "probe": 400}
    assert pr.sprint_counts("haiku_off_stub") == {"t1": 100, "t2": 300, "t2_nf": 300, "probe": 0}


def test_turn2_without_fields_is_priced_from_the_replies_with_fields():
    rows, _ = pr.sprint_cost({("gpt6luna", "t2"): {"n": 5, "input": 1000.0, "output": 200.0}})
    r = next(r for r in rows if r["setting"] == "gpt6luna" and r["kind"] == "t2_nf")
    assert (r["tokens_from"], r["input"], r["output"], r["pilot_replies"]) == ("pilot (t2)", 1000.0, 200.0, 5)
    assert next(r for r in rows if r["setting"] == "mistral_small" and r["kind"] == "t2_nf")["tokens_from"] == \
        "cost model"


# ------------------------------------------------------------------------------------- hand-built records

def wording_unit(rn, name, n_missing, n_open=0):
    """60 turn-2 requests of one setting, the first n_missing replies missing and the last n_open without a reply."""
    ids = [(f"pil{i // 6 + 1:03d}", prompts.ARMS[i % 6]) for i in range(60)]
    recs = [rec(name, it, 1, arm, 0.5, status="missing" if i < n_missing else "ok")
            for i, (it, arm) in enumerate(ids[:60 - n_open])]
    return pr.make_unit(rn, name, Path("."), recs, {build.custom_id(name, it, 1, arm): "t2" for it, arm in ids})


def test_the_recheck_reads_the_wording_run_only():
    pilot = {("pilot", "llama4_scout"): wording_unit("pilot", "llama4_scout", 4)}
    r = pr.rule1(pilot)
    assert r["flagged"] == ["llama4_scout"] and r["recheck"]["status"] == "not run"
    for missing, n_open, status in ((3, 0, "passed"), (4, 0, "flagged"), (0, 2, "incomplete")):
        units = {**pilot, ("pilot_wording", "llama4_scout"): wording_unit("pilot_wording", "llama4_scout", missing,
                                                                          n_open),
                 ("pilot_wording", "haiku_off"): wording_unit("pilot_wording", "haiku_off", 0)}
        r = pr.rule1(units)
        assert r["flagged"] == ["llama4_scout"]                     # the pilot flag stays as it was
        rc = r["recheck"]
        assert (rc["status"], rc["open_requests"]) == (status, n_open), status
        assert rc["flagged"] == (["llama4_scout"] if status == "flagged" else [])
        assert rc["settings"]["llama4_scout"]["missing"] == missing


def recheck_units(failed):
    """The pilot flag of llama4_scout and a wording run of 60 turn-2 replies of it, the first replies failing as
    failed lists them: (status, reason, failed_fields or None for a record written before 11 November 2026)."""
    ids = [(f"pil{i // 6 + 1:03d}", prompts.ARMS[i % 6]) for i in range(60)]
    recs = []
    for i, (it, arm) in enumerate(ids):
        r = rec("llama4_scout", it, 1, arm, 0.5, changed=False, previous_probability=50)
        if i < len(failed):
            status, reason, ff = failed[i]
            r.update(status=status, reason=reason,
                     core_ok=not {"probability", "prepare"} & {x.split(" ")[0] for x in reason.split("; ")},
                     parsed={"probability": 50, "prepare": False} if status == "partial" else None)
            if ff is not None:
                r["failed_fields"] = ff
        recs.append(r)
    return {("pilot", "llama4_scout"): wording_unit("pilot", "llama4_scout", 4),
            ("pilot_wording", "llama4_scout"): pr.make_unit(
                "pilot_wording", "llama4_scout", Path("."), recs,
                {build.custom_id("llama4_scout", it, 1, arm): "t2" for it, arm in ids})}


def test_the_recheck_is_decided_when_a_decision_names_every_failed_field():
    """PLAN 10.4 and 15, 11 November 2026: 4 of 60 replies of llama-4-scout failed in previous_probability alone.
    The stored records predate the partial status, so the failed field is read from the reason."""
    old = [("missing", "previous_probability not a number", None)] * 4
    new = [("partial", "previous_probability not a number", ["previous_probability"])] * 4
    for failed in (old, new, old[:2] + new[:2]):
        rep = pr.build_report({}, recheck_units(failed), {}, False)
        rc = rep["rule1"]["recheck"]
        v = rc["settings"]["llama4_scout"]
        assert (rc["status"], rc["flagged"], rc["decided"]) == ("decided", ["llama4_scout"], ["llama4_scout"])
        assert (v["missing"], v["flag"], v["core_failed"], v["undecided"], v["decided"]) == (4, True, 0, 0, True)
        assert v["failed_by_field"] == {"previous_probability": 4}
        assert v["decision"] == [pr.FIELD_DECISIONS[("llama4_scout", "previous_probability")]]
        [line] = [d for d in rep["decisions"] if d.startswith("rule 1: re-check")]
        assert line.startswith("rule 1: re-check decided") and "core fields 0" in line
        assert rep["rule1"]["flagged"] == ["llama4_scout"]       # the pilot flag stays as it was


def test_the_recheck_stays_flagged_when_a_failed_field_has_no_decision():
    pp = ("missing", "previous_probability not a number", None)
    for extra in (("missing", "probability not a number", None),          # a core field, read from the reason
                  ("missing", "no complete JSON object", None),           # every field
                  ("partial", "changed missing", ["changed"])):           # a field that no decision names
        failed = [pp] + [extra] * 4                  # 4 of 60 with a field that no decision names, above 5%
        rc = pr.build_report({}, recheck_units(failed), {}, False)["rule1"]["recheck"]
        v = rc["settings"]["llama4_scout"]
        assert (rc["status"], rc["flagged"], rc["decided"]) == ("flagged", ["llama4_scout"], []), extra
        assert (v["missing"], v["undecided"], v["decided"], v["decision"]) == (5, 4, False, []), extra
        assert v["core_failed"] == (4 if "probability not" in extra[1] or extra[1].startswith("no ") else 0)
    # rule 1 counts a cut reply under rule 9, not as missing, so 3 of 60 fail and the re-check passes
    rc = pr.build_report({}, recheck_units([pp] * 3 + [("cut", "stopped at the output cap", None)] * 2), {},
                         False)["rule1"]["recheck"]
    assert (rc["status"], rc["settings"]["llama4_scout"]["missing"]) == ("passed", 3)
    # three replies with a field that no decision names stay within 5% of 60, so the setting is decided
    failed = [pp] * 2 + [("partial", "changed missing", ["changed"])] * 3
    rc = pr.build_report({}, recheck_units(failed), {}, False)["rule1"]["recheck"]
    assert (rc["status"], rc["settings"]["llama4_scout"]["undecided"]) == ("decided", 3)


def test_turn2_acceptance_counts_http_400_only():
    name = "glm_flash"
    good = rec(name, "pil001", 1, "control", 0.5)
    e502 = {**rec(name, "pil001", 1, "market", status="error"), "error": {"type": "http", "status": 502,
                                                                         "message": "made-up error"}}
    e400 = rec(name, "pil002", 1, "market", status="error")
    a = pr.turn2_acceptance({("pilot", name): pr.make_unit("pilot", name, Path("."), [good, e502])})[name]
    assert (a["accepted"], a["http_400"], a["errors_only"]) == (True, 0, 1)
    a = pr.turn2_acceptance({("pilot", name): pr.make_unit("pilot", name, Path("."), [good, e400])})[name]
    assert (a["accepted"], a["http_400"], a["errors_only"]) == (False, 1, 1)
    a = pr.turn2_acceptance({("pilot", name): pr.make_unit("pilot", name, Path("."), [e502])})[name]
    assert (a["accepted"], a["http_400"], a["errors_only"]) == (None, 0, 1)


def test_turn2_acceptance_waits_for_a_reply_or_an_http_400():
    # PLAN 10.4: the pilot_wording run is prepared but not sent, so none of its settings is reported as refused
    units = {("pilot", "haiku_off"): wording_unit("pilot", "haiku_off", 0),
             ("pilot_wording", "haiku_off"): wording_unit("pilot_wording", "haiku_off", 0, 60)}
    acc = pr.turn2_acceptance(units)
    assert (acc["haiku_off"]["replies"], acc["haiku_off"]["accepted"]) == (60, True)
    a = acc["pilot_wording/haiku_off"]
    assert (a["requested"], a["replies"], a["http_400"], a["accepted"]) == (60, 0, 0, None)
    rep = pr.build_report({}, units, {}, False)
    assert not any(d.startswith("PLAN 4.3") for d in rep["decisions"])

def test_rule3_freezes_the_largest_chain1_sd_of_a_sprint_setting(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "ITEMS", tmp_path)
    ho = [rec("haiku_off", i, 1, p, v) for i, (e, s) in {"Z1": (60, 40), "Z2": (55, 45), "Z3": (50, 50)}.items()
          for p, v in (("control", 50), ("enthusiast", e), ("skeptic", s))]
    sh = [rec("sonnet_high", i, 1, p, v) for i, (e, s) in {"Z1": (90, 10), "Z2": (50, 50)}.items()
          for p, v in (("control", 50), ("enthusiast", e), ("skeptic", s))]
    units = units_of(("haiku_off", ho), ("sonnet_high", sh))
    cm = pricing.cost_model()
    m = pr.rule3(units, {})["frozen_mde"]
    assert m["setting"] == "haiku_off" and m["sd"] == pytest.approx(0.1, abs=1e-6)
    assert m["mde_800"] == pytest.approx(cm.mde(0.1, 800), abs=1e-6)
    assert m["mde_400"] == pytest.approx(cm.mde(0.1, 400), abs=1e-6)
    assert m["tost_power_800"] == pytest.approx(cm.tost_power(0.03, 0.1, 800), abs=1e-6)
    assert m["tost_power_400"] == pytest.approx(cm.tost_power(0.03, 0.1, 400), abs=1e-6)
    rep = pr.build_report({}, units, {}, False)
    want = (f"rule 3: frozen SD 0.1000 (haiku_off, chain 1); MDE {cm.mde(0.1, 400):.4f} at 400 items under the "
            f"half split of PLAN 6.3 and {cm.mde(0.1, 800):.4f} at 800; TOST power "
            f"{cm.tost_power(0.03, 0.1, 400):.3f} at 400 and {cm.tost_power(0.03, 0.1, 800):.3f} at 800")
    assert want in rep["decisions"]


def test_rule4_counts_hiding_phantoms_misreports_and_turn1_noise():
    recs = [rec("haiku_off", "Y1", 1, "t1", 40), rec("haiku_off", "Y2", 1, "t1", 40),
            rec("haiku_off", "Y1", 2, "t1", 46),
            rec("haiku_off", "Y1", 1, "enthusiast", 45, changed=False, previous_probability=40),
            rec("haiku_off", "Y1", 1, "skeptic", 40, changed=True, previous_probability=40),
            rec("haiku_off", "Y1", 1, "control", 40, changed=False, previous_probability=40),
            rec("haiku_off", "Y2", 1, "market", 70, prepare=True, changed=True, previous_probability=41)]
    r = pr.rule4(units_of(("haiku_off", recs)))
    o = r["settings"]["haiku_off"]["overall"]
    assert (o["pairs"], o["substantive"], o["hide"], o["literal"], o["phantom"], o["misreport"]) == (4, 2, 1, 2, 1, 1)
    assert (o["hide_rate"], o["phantom_rate"], o["misreport_rate"], o["consistency_serving_share"]) == \
        (0.5, 0.5, 0.25, 1.0)
    assert r["flagged"] == ["haiku_off"]
    assert r["settings"]["haiku_off"]["noise_turn1"] == {"n": 1, "mean_abs": 0.06, "share_5_points": 1.0,
                                                         "p90": 0.06}


def test_completeness_and_the_bounds_of_plan_7_10():
    recs = []
    for i in ("X1", "X2", "X3", "X4"):
        recs.append(rec("haiku_medium", i, 1, "t1", 50))
        for arm in ("control", "double_check", "market", "hunch"):
            recs.append(rec("haiku_medium", i, 1, arm, 50, changed=False, previous_probability=50))
        if i == "X1":
            recs.append(rec("haiku_medium", i, 1, "enthusiast", status="missing"))
        else:
            recs.append(rec("haiku_medium", i, 1, "enthusiast", 60, changed=True, previous_probability=50))
        if i == "X2":
            recs.append(rec("haiku_medium", i, 1, "skeptic", status="error"))
        else:
            recs.append(rec("haiku_medium", i, 1, "skeptic", 40, changed=False, previous_probability=50))
    c = pr.completeness(units_of(("haiku_medium", recs)))
    [row] = c["rows"]
    assert row["turn1_ok"] == 4
    assert row["arms"]["enthusiast"] == {"ok": 3, "missing": 1}
    assert row["arms"]["skeptic"] == {"ok": 3, "error": 1}
    assert row["arms"]["control"] == {"ok": 4}
    assert (row["complete_chains"], row["incomplete_triples"], row["incomplete_share"]) == (2, 2, 0.5)
    assert row["bounds_apply"] is True
    assert (row["D_lower"], row["D_upper"]) == (pytest.approx(-0.1), pytest.approx(0.4))
    assert c["flagged"] == ["haiku_medium chain 1"]


def test_mirror_pairs_read_the_flag_in_the_item_file():
    """PLAN 6.8: the report pairs the two items of an event that the item file flags and skips an event with one
    flagged item. The rule that sets the flag is items.mirror_events (tests/test_items.py)."""
    items = {"A1": {"item_id": "A1", "event_id": "e1", "mirror": True},
             "A2": {"item_id": "A2", "event_id": "e1", "mirror": True},
             "B1": {"item_id": "B1", "event_id": "e2", "mirror": True},
             "B2": {"item_id": "B2", "event_id": "e2", "mirror": True},
             "C1": {"item_id": "C1", "event_id": "e3", "mirror": True},
             "D1": {"item_id": "D1", "event_id": "e4", "mirror": False}}
    recs = [rec("haiku_off", i, 1, "t1", p) for i, p in (("A1", 60), ("A2", 45), ("B1", 30), ("B2", 60),
                                                          ("C1", 50))]
    m = pr.mirror_pairs(units_of(("haiku_off", recs)), items)
    assert m["pairs_in_item_file"] == 2
    assert m["settings"]["haiku_off"] == {"n": 2, "mean_abs": 0.075, "signed_mean": -0.025}
