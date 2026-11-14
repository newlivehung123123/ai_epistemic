"""Request builder on made-up items: request counts per setting, custom_ids, the message order of each turn,
the stubbornness draw, the routes and the not-sent records (PLAN 4.1 to 4.7, 5.2 and 10)."""
import pytest

from pipeline import build, config, prompts, settings

END = {"pilot": "2026-11-12", "retro": "2026-10-20", "prospective": "2026-11-25"}


def make_items(set_name, n, sub_sizes=(("sub10", 10), ("sub20", 20))):
    """n items as items.finish writes them: nested subsets for the pilot, t by turns, q_pct inside the band."""
    out = []
    for i in range(n):
        it = {"item_id": f"{build_prefix(set_name)}{i + 1:03d}", "set": set_name,
              "question": f"Will event {i + 1} happen by {END[set_name]}?",
              "description": f"This market resolves Yes if event {i + 1} happens.",
              "end_date": END[set_name], "t": config.T_VALUES[i % 5], "q_pct": 5 + (i * 7) % 91}
        if set_name == "pilot":
            it["subsets"] = [name for name, size in sub_sizes if i < size]
        out.append(it)
    return out


def build_prefix(set_name):
    from pipeline.items import PREFIX
    return PREFIX[set_name]


PILOT = {"pilot": make_items("pilot", 50)}
SPRINT = {"retro": make_items("retro", 400), "prospective": make_items("prospective", 400)}


def all_ok(r1):
    return {r["custom_id"]: {"status": "ok", "parsed": {"reasoning": "Because.", "probability": 42,
                                                        "prepare": True}}
            for r in r1 if r["kind"] == "t1"}


def ok_turn1(run, name, items):
    """A parsed reply for every turn-1 request that round 2 of the run needs, in its own run or in turn1_from."""
    return {cid: {"status": "ok", "parsed": {"reasoning": "Because.", "probability": 42, "prepare": True}}
            for cid in build.turn1_ids(run, name, items)}


RUNS_AND_ITEMS = [("pilot", PILOT), ("pilot_batch_test", PILOT), ("pilot_wording", PILOT), ("sprint", SPRINT)]
WORDING_SETTINGS = ("haiku_off", "haiku_medium", "sonnet_off", *settings.PANEL)


PILOT_COUNTS = {
    "haiku_off": {"items": 50, "t1": 100, "t2": 700, "probe": 50, "total": 850},
    "haiku_medium": {"items": 50, "t1": 50, "t2": 300, "probe": 0, "total": 350},
    "sonnet_off": {"items": 20, "t1": 40, "t2": 240, "probe": 20, "total": 300},
    "sonnet_high": {"items": 10, "t1": 10, "t2": 60, "probe": 0, "total": 70},
    **{name: {"items": 20, "t1": 20, "t2": 120, "probe": 20, "total": 160} for name in settings.PANEL},
}
SPRINT_COUNTS = {
    "haiku_off": {"items": 800, "t1": 2400, "t2": 14400, "probe": 400, "total": 17200},
    "haiku_medium": {"items": 800, "t1": 1600, "t2": 4800, "probe": 0, "total": 6400},
    "sonnet_off": {"items": 800, "t1": 1600, "t2": 4800, "probe": 400, "total": 6800},
    **{name: {"items": 800, "t1": 1600, "t2": 4800, "probe": 400, "total": 6800} for name in settings.PANEL},
    "haiku_off_stub": {"items": 100, "t1": 100, "t2": 600, "probe": 0, "total": 700},
}


def test_pilot_counts():
    assert build.expected_counts("pilot", PILOT) == PILOT_COUNTS
    assert sum(c["total"] for c in PILOT_COUNTS.values()) == 2850


def test_pilot_batch_test_counts():
    assert build.expected_counts("pilot_batch_test", PILOT) == {
        name: {"items": 10, "t1": 10, "t2": 0, "probe": 0, "total": 10} for name in ("gpt6luna", "deepseek_flash")}


def test_sprint_counts():
    assert build.expected_counts("sprint", SPRINT) == SPRINT_COUNTS
    assert sum(c["total"] for c in SPRINT_COUNTS.values()) == 85_500


def test_pilot_wording_counts():
    """PLAN 10.4: turn 2 only, 10 items and six arms for each of the 11 sprint settings that send turn 2."""
    assert build.expected_counts("pilot_wording", PILOT) == {
        name: {"items": 10, "t1": 0, "t2": 60, "probe": 0, "total": 60} for name in WORDING_SETTINGS}
    assert sum(c["total"] for c in build.expected_counts("pilot_wording", PILOT).values()) == 660


@pytest.mark.parametrize("run,items", RUNS_AND_ITEMS)
def test_built_requests_match_the_counts(run, items):
    counts = build.expected_counts(run, items)
    for name in build.run_spec(run)["settings"]:
        r1 = build.round1(run, name, items)
        r2, not_sent = build.round2(run, name, items, ok_turn1(run, name, items))
        c = counts[name]
        assert sum(r["kind"] == "t1" for r in r1) == c["t1"]
        assert sum(r["kind"] == "probe" for r in r1) == c["probe"]
        assert len(r2) == c["t2"] and not_sent == []
        assert {r["round"] for r in r1} <= {1} and {r["round"] for r in r2} <= {2}


@pytest.mark.parametrize("run,items", RUNS_AND_ITEMS)
def test_custom_ids_are_valid_and_unique(run, items):
    ids = build.all_custom_ids(run, items)
    assert len(ids) == len(set(ids))
    assert all(build.CUSTOM_ID.match(i) and len(i) <= 64 for i in ids)
    assert len(ids) == sum(c["total"] for c in build.expected_counts(run, items).values())


def test_custom_id_forms():
    assert build.custom_id("haiku_off", "ret001", 3, "double_check_nf") == "haiku_off-ret001-c3-double_check_nf"
    assert build.custom_id("sonnet_off", "pil007", None, "probe") == "sonnet_off-pil007-probe"
    with pytest.raises(ValueError):
        build.custom_id("haiku off", "ret001", 1, "t1")
    with pytest.raises(ValueError):
        build.custom_id("x" * 60, "ret001", 1, "t1")


RECORD_KEYS = {"run", "setting", "custom_id", "item_id", "set", "chain", "part", "kind", "arm", "fields",
               "stubborn", "round", "max_tokens", "system", "messages"}


def test_turn1_and_probe_records():
    r1 = build.round1("pilot", "haiku_off", PILOT)
    item = PILOT["pilot"][0]
    t1 = [r for r in r1 if r["item_id"] == item["item_id"] and r["kind"] == "t1"]
    assert [r["chain"] for r in t1] == [1, 2]
    for r in t1:
        assert set(r) == RECORD_KEYS
        assert r["system"] == prompts.SYSTEM and r["max_tokens"] == settings.CAP_PLAIN and not r["stubborn"]
        assert r["messages"] == [{"role": "user", "content": prompts.turn1(item, config.SETS["pilot"]["F"])}]
        assert r["messages"][0]["content"].startswith("Today's date is 7 November 2026.\n")
    probe = [r for r in r1 if r["item_id"] == item["item_id"] and r["kind"] == "probe"]
    assert len(probe) == 1 and probe[0]["chain"] is None and probe[0]["custom_id"] == "haiku_off-pil001-probe"
    assert probe[0]["system"] == prompts.PROBE_SYSTEM
    assert probe[0]["messages"] == [{"role": "user", "content": prompts.probe(item)}]


def test_turn2_messages_replay_the_parsed_turn1_object():
    r1 = build.round1("pilot", "sonnet_off", PILOT)
    t1 = {r["custom_id"]: {"status": "ok", "parsed": {"probability": 61, "prepare": False,
                                                      "reasoning": "Works are late.", "extra": 1}}
          for r in r1 if r["kind"] == "t1"}
    r2, _ = build.round2("pilot", "sonnet_off", PILOT, t1)
    item = PILOT["pilot"][3]
    mine = [r for r in r2 if r["item_id"] == item["item_id"] and r["chain"] == 1]
    assert [r["arm"] for r in mine] == list(prompts.ARMS)
    for r in mine:
        assert set(r) == RECORD_KEYS and r["kind"] == "t2" and r["fields"] is True and r["part"] == r["arm"]
        assert r["system"] == prompts.SYSTEM and r["max_tokens"] == settings.CAP_PLAIN
        assert [m["role"] for m in r["messages"]] == ["user", "assistant", "user"]
        assert r["messages"][0]["content"] == prompts.turn1(item, config.SETS["pilot"]["F"])
        assert r["messages"][1]["content"] == '{"reasoning": "Works are late.", "probability": 61, "prepare": false}'
        assert r["messages"][2]["content"] == prompts.turn2(r["arm"], item["q_pct"])
    market = next(r for r in mine if r["arm"] == "market")
    assert f"at {item['q_pct']}%." in market["messages"][2]["content"]


def test_self_report_check_runs_on_pilot_chain_1_only():
    r1 = build.round1("pilot", "haiku_off", PILOT)
    r2, _ = build.round2("pilot", "haiku_off", PILOT, all_ok(r1))
    pil = [r for r in r2 if r["item_id"] == "pil001"]
    assert [r["part"] for r in pil if r["chain"] == 1] == list(prompts.ARMS) + ["enthusiast_nf", "skeptic_nf"]
    assert [r["part"] for r in pil if r["chain"] == 2] == list(prompts.ARMS)
    nf = [r for r in pil if r["part"].endswith("_nf")]
    assert all(r["kind"] == "t2_nf" and r["fields"] is False for r in nf)
    assert all(r["messages"][2]["content"].endswith(prompts.REQUEST_NO_FIELDS) for r in nf)
    assert all(not r["messages"][2]["content"].endswith(prompts.REQUEST_NO_FIELDS)
               for r in pil if not r["part"].endswith("_nf"))


def test_sprint_chain_3_of_haiku_off_has_no_fields():
    items = {"retro": SPRINT["retro"][:2], "prospective": SPRINT["prospective"][:2]}
    r1 = build.round1("sprint", "haiku_off", items)
    r2, _ = build.round2("sprint", "haiku_off", items, all_ok(r1))
    c3 = [r for r in r2 if r["item_id"] == "ret001" and r["chain"] == 3]
    assert [r["part"] for r in c3] == [a + "_nf" for a in prompts.ARMS]
    assert all(r["kind"] == "t2_nf" for r in c3)
    assert build.round1("sprint", "haiku_off", items)[0]["custom_id"] == "haiku_off-ret001-c1-t1"


def test_half_split_draws_half_of_each_set_by_seed():
    """PLAN 6.3: ceil(n/2) items of each set, drawn with the run seed under a purpose named after the set."""
    digits = lambda ids: {int(i[3:]) for i in ids}
    retro = build.half_split_ids("retro", SPRINT["retro"])
    pro = build.half_split_ids("prospective", SPRINT["prospective"])
    assert len(retro) == 200 and retro <= {it["item_id"] for it in SPRINT["retro"]}
    assert len(pro) == 200 and digits(pro) != digits(retro)              # one seed purpose per set
    assert retro == build.half_split_ids("retro", list(reversed(SPRINT["retro"])))
    assert len(build.half_split_ids("retro", SPRINT["retro"][:7])) == 4  # an odd set gives the extra item no fields
    assert build.no_fields_ids("sprint", SPRINT) == retro | pro
    assert build.no_fields_ids("pilot", PILOT) == set() and build.no_fields_ids("pilot_wording", PILOT) == set()


def test_sprint_chain_1_follows_the_half_split():
    nf = build.no_fields_ids("sprint", SPRINT)
    for name in build.run_spec("sprint")["settings"]:
        r2, not_sent = build.round2("sprint", name, SPRINT, all_ok(build.round1("sprint", name, SPRINT)))
        c1 = [r for r in r2 if r["chain"] == 1]
        assert not_sent == [] and len(c1) == 6 * len({r["item_id"] for r in c1})
        for r in c1:
            half = r["item_id"] in nf                                     # the same half in every setting
            assert r["fields"] is not half and r["kind"] == ("t2_nf" if half else "t2")
            assert r["part"] == (r["arm"] + "_nf" if half else r["arm"])
            assert r["messages"][2]["content"].endswith(prompts.REQUEST_NO_FIELDS if half else prompts.REQUEST)
    r2, _ = build.round2("sprint", "haiku_off", SPRINT, all_ok(build.round1("sprint", "haiku_off", SPRINT)))
    assert sum(r["chain"] == 1 and not r["fields"] for r in r2) == 6 * 400
    assert all(r["fields"] for r in r2 if r["chain"] == 2)                # chain 2 keeps the fields on every item
    assert not any(r["fields"] for r in r2 if r["chain"] == 3)            # chain 3 drops them on every item


def test_pilot_wording_replays_pilot_turn1_with_the_new_request():
    assert build.turn1_source("pilot_wording") == "pilot" and build.turn1_source("sprint") == "sprint"
    for name in WORDING_SETTINGS:
        assert build.round1("pilot_wording", name, PILOT) == []
        ids = build.turn1_ids("pilot_wording", name, PILOT)
        assert ids == [f"{name}-pil{i:03d}-c1-t1" for i in range(1, 11)]
        r2, not_sent = build.round2("pilot_wording", name, PILOT, ok_turn1("pilot_wording", name, PILOT))
        assert not_sent == [] and len(r2) == 60 and {r["chain"] for r in r2} == {1}
        assert all(r["fields"] and r["messages"][2]["content"].endswith(prompts.REQUEST) for r in r2)
        assert all(r["run"] == "pilot_wording" for r in r2)
    assert "sonnet_high" not in build.run_spec("pilot_wording")["settings"]


def test_redraw_chains_send_turn1_only():
    for name in ("haiku_medium", "sonnet_off") + settings.PANEL:
        items = {"retro": SPRINT["retro"][:3], "prospective": SPRINT["prospective"][:3]}
        r1 = build.round1("sprint", name, items)
        r2, _ = build.round2("sprint", name, items, all_ok(r1))
        assert sorted({r["chain"] for r in r1 if r["kind"] == "t1"}) == [1, 2]
        assert {r["chain"] for r in r2} == {1}


def test_sprint_probes_cover_retro_items_only():
    for name in settings.PROBE_SETTINGS:
        r1 = build.round1("sprint", name, SPRINT)
        probes = [r for r in r1 if r["kind"] == "probe"]
        assert len(probes) == 400 and {r["set"] for r in probes} == {"retro"}
    for name in ("haiku_medium", "haiku_off_stub"):
        assert not [r for r in build.round1("sprint", name, SPRINT) if r["kind"] == "probe"]


def test_max_tokens_follow_the_settings():
    for name in build.run_spec("pilot")["settings"]:
        r1 = build.round1("pilot", name, PILOT)
        assert {r["max_tokens"] for r in r1} == {settings.setting(name)["max_tokens"]}
    assert settings.setting("haiku_medium")["max_tokens"] == settings.CAP_REASONING
    assert settings.setting("sonnet_high")["max_tokens"] == settings.CAP_REASONING


def test_stubbornness_draw():
    ids = build.stubborn_ids(SPRINT["retro"])
    assert len(ids) == 100 and ids == sorted(ids) and len(set(ids)) == 100
    assert ids == build.stubborn_ids(list(reversed(SPRINT["retro"])))   # order of the file does not matter
    assert set(ids) <= {it["item_id"] for it in SPRINT["retro"]}
    with pytest.raises(ValueError):
        build.stubborn_ids(SPRINT["retro"][:99])


def test_stubborn_requests_carry_the_extra_sentence():
    r1 = build.round1("sprint", "haiku_off_stub", SPRINT)
    assert len(r1) == 100 and {r["set"] for r in r1} == {"retro"}
    assert {r["item_id"] for r in r1} == set(build.stubborn_ids(SPRINT["retro"]))
    r2, _ = build.round2("sprint", "haiku_off_stub", SPRINT, all_ok(r1))
    for r in r1 + r2:
        assert r["stubborn"] is True and r["system"] == prompts.system_prompt(True)
        assert r["custom_id"].startswith("haiku_off_stub-")
    for r in build.round1("sprint", "haiku_off", {"retro": SPRINT["retro"][:2], "prospective": []}):
        assert r["stubborn"] is False


def test_not_sent_records():
    items = {"pilot": PILOT["pilot"]}
    r1 = build.round1("pilot", "haiku_medium", items)
    results = all_ok(r1)
    results["haiku_medium-pil002-c1-t1"] = {"status": "missing", "parsed": None, "reason": "empty reply"}
    results["haiku_medium-pil003-c1-t1"] = {"status": "refusal", "parsed": None}
    results["haiku_medium-pil004-c1-t1"] = {"status": "cut", "parsed": None}
    del results["haiku_medium-pil005-c1-t1"]
    r2, not_sent = build.round2("pilot", "haiku_medium", items, results)
    assert len(r2) == 46 * 6 and len(not_sent) == 4 * 6
    reasons = {r["item_id"]: r["reason"] for r in not_sent}
    assert reasons == {"pil002": "turn 1 status missing", "pil003": "turn 1 status refusal",
                       "pil004": "turn 1 status cut", "pil005": "turn 1 has no result"}
    assert all(r["status"] == "not_sent" and r["round"] == 2 and "messages" not in r for r in not_sent)


def test_routes():
    # PLAN 5.3, 8 November 2026: every OpenRouter sprint request is a sync request
    assert build.route("pilot", "gpt6luna") == "sync" and build.route("sprint", "gpt6luna") == "sync"
    assert build.route("pilot", "deepseek_flash") == "sync" and build.route("sprint", "deepseek_flash") == "sync"
    assert all(build.route("sprint", n) == "sync" for n in build.run_spec("sprint")["settings"]
               if settings.setting(n)["api"] == "openrouter")
    assert build.route("pilot_batch_test", "gpt6luna") == "batch"
    assert build.route("pilot_batch_test", "deepseek_flash") == "batch"
    for run in ("pilot", "sprint"):
        for name in build.run_spec(run)["settings"]:
            api = settings.setting(name)["api"]
            r = build.route(run, name)
            assert r == {"anthropic": "batch", "hf": "sync"}.get(api, r)
    assert build.route("sprint", "gemini_flash_lite") == "sync"
    with pytest.raises(KeyError):
        build.route("sprint", "sonnet_high")
    with pytest.raises(KeyError):
        build.route("pilot", "haiku_off_stub")
    with pytest.raises(KeyError):
        build.run_spec("sprint2")


def test_route_rules_refuse_a_wrong_route(monkeypatch):
    monkeypatch.setitem(settings.SETTINGS, "haiku_off", {**settings.SETTINGS["haiku_off"],
                                                         "route": {"pilot": "sync", "sprint": "batch"}})
    with pytest.raises(ValueError):
        build.route("pilot", "haiku_off")
    monkeypatch.setitem(settings.SETTINGS, "llama4_scout", {**settings.SETTINGS["llama4_scout"],
                                                            "route": {"pilot": "batch", "sprint": "sync"}})
    with pytest.raises(ValueError):
        build.route("pilot", "llama4_scout")
    monkeypatch.setitem(settings.SETTINGS, "glm_flash", {**settings.SETTINGS["glm_flash"],
                                                         "route": {"pilot": None, "sprint": "sync"}})
    with pytest.raises(ValueError):
        build.route("pilot", "glm_flash")


def test_wrong_subset_size_is_refused():
    short = {"pilot": make_items("pilot", 50, (("sub10", 9), ("sub20", 20)))}
    with pytest.raises(ValueError):
        build.select_items("pilot", "sonnet_high", short)
    assert len(build.select_items("pilot", "sonnet_off", short)) == 20
    sub10 = build.select_items("pilot", "sonnet_high", PILOT)
    assert [it["item_id"] for it in sub10] == [f"pil{i:03d}" for i in range(1, 11)]


@pytest.mark.parametrize("run,items", RUNS_AND_ITEMS)
def test_parse_custom_id_round_trip(run, items):
    for cid in build.all_custom_ids(run, items):
        info = build.parse_custom_id(cid)
        assert build.custom_id(info["setting"], info["item_id"], info["chain"], info["part"]) == cid


@pytest.mark.parametrize("cid", ["has space", "x" * 65, "haiku_off-pil001", "haiku_off-pil001-x1-t1",
                                 "haiku_off-pil001-c1-bogus"])
def test_parse_custom_id_refuses_other_ids(cid):
    with pytest.raises(ValueError):
        build.parse_custom_id(cid)
