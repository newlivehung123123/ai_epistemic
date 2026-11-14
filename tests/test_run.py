"""run.py on made-up replies (--stub): prepare, send, collect, status, cancel, adopt, release and summary, the
spend cap, the lock, partial lines and the failure paths of a batch create (PLAN 5 and 10). Nothing touches the
network: the HTTP transport of every client raises, no key is set, and the stub clients answer for the providers."""
import os
import time

import httpx
import pytest

from pipeline import config, keys, prompts, run, settings
from pipeline.clients import common, stub
from pipeline.util import append_jsonl_many, read_json, read_jsonl, write_json
from test_build import PILOT_COUNTS, make_items

THINKS = {"haiku_medium", "sonnet_high", "qwen_flash", "glm_flash", "gpt_oss_120b"}
PARSE_STATUSES = {"ok", "partial", "missing", "cut", "refusal"}


def clear_env(monkeypatch, *names):
    """Remove variables for one test. setenv comes first, so teardown also removes a value set during the test."""
    for name in names:
        monkeypatch.setenv(name, "x")
        monkeypatch.delenv(name)


@pytest.fixture
def env(tmp_path, monkeypatch):
    items = tmp_path / "items"
    items.mkdir()
    monkeypatch.setattr(config, "ITEMS", items)
    monkeypatch.setattr(config, "RUNS", tmp_path / "runs")
    write_json(items / "pilot_items.json", {"items": make_items("pilot", 50)})
    monkeypatch.setattr(stub, "ERROR_IDS", set())
    monkeypatch.setattr(stub, "BATCH_POLLS_BEFORE_END", 0)
    monkeypatch.setattr(stub, "RESULTS_NULL_POLLS", 0)
    monkeypatch.setattr(stub, "SUBMIT_FAILS", None)
    monkeypatch.setattr(run, "SLEEP", lambda s: None)
    monkeypatch.setattr(keys, "ENV_FILE", tmp_path / "no.env")
    clear_env(monkeypatch, *keys.KEY_NAMES.values())

    def no_network(request):
        raise AssertionError(f"network: {request.method} {request.url}")

    monkeypatch.setattr(common, "TRANSPORT", httpx.MockTransport(no_network))
    return tmp_path


def cli(*args):
    return run.main([str(a) for a in args])


def stub_dir(name="pilot"):
    return config.RUNS / f"{name}-stub"


def requests_of(name, rnd, r="pilot", stubbed=True):
    return read_jsonl(run.requests_path(run.run_dir(r, stubbed), name, rnd))


def results_of(name, r="pilot", stubbed=True):
    return read_jsonl(run.results_path(run.run_dir(r, stubbed), name))


# ------------------------------------------------------------------------------------------------- round trips

def test_full_stub_round_trip(env):
    for step in (("prepare", "--round", 1), ("send", "--round", 1, "--yes"), ("collect",),
                 ("prepare", "--round", 2), ("send", "--round", 2, "--yes"), ("collect",), ("summary",)):
        assert cli(*step, "--run", "pilot", "--stub") == 0, step
    summary = read_json(stub_dir() / "summary.json")["settings"]
    for name, c in PILOT_COUNTS.items():
        r1, r2 = requests_of(name, 1), requests_of(name, 2)
        ns = read_jsonl(run.not_sent_path(stub_dir(), name))
        assert len(r1) == c["t1"] + c["probe"]
        assert len(r2) + len(ns) == c["t2"]
        win, errs = run.winners(results_of(name))
        assert set(win) == {r["custom_id"] for r in r1 + r2} and not errs
        s = summary[name]
        assert (s["results"], s["errors_only"], s["in_flight"]) == (len(r1) + len(r2), 0, 0)
        st = settings.setting(name)
        expected = {"anthropic": "None (None)", "openrouter": f"STUB-{st.get('sync_provider')} (reply)",
                    "hf": "STUB-deepinfra (header)"}[st["api"]]
        assert s["serving_provider"] == {expected: s["results"]}, name
        assert s["with_thinking"] == (s["results"] if name in THINKS else 0), name
    assert set(summary["total"]["status"]) <= PARSE_STATUSES
    assert not (config.RUNS / "pilot").exists()


def test_pilot_batch_test_round_trip(env, capsys):
    args = ("--run", "pilot_batch_test", "--stub")
    assert cli("prepare", *args, "--round", 1) == 0
    assert cli("send", *args, "--round", 1, "--yes") == 0
    assert cli("collect", *args) == 0
    capsys.readouterr()
    assert cli("prepare", *args, "--round", 2) == 0
    assert "gpt6luna: no round 2 in the pilot_batch_test run; skipped" in capsys.readouterr().out
    assert cli("summary", *args) == 0
    s = read_json(stub_dir("pilot_batch_test") / "summary.json")["settings"]
    assert s["gpt6luna"]["serving_provider"] == {"openai (batch)": 10}
    assert s["deepseek_flash"]["serving_provider"] == {"deepinfra (batch)": 10}


def test_pilot_wording_round_trip(env, capsys):
    """PLAN 10.4: the re-check has no round 1 and builds turn 2 from the chain-1 turn-1 replies of the pilot run."""
    args = ("--run", "pilot_wording", "--stub")
    assert cli("prepare", *args, "--round", 1) == run.ERROR
    assert "reuses the turn-1 replies of the pilot run" in capsys.readouterr().err
    assert cli("prepare", *args, "--round", 2, "--setting", "haiku_off") == run.ERROR
    assert "have no result in the pilot run" in capsys.readouterr().err
    for step in (("prepare", "--round", 1), ("send", "--round", 1, "--yes"), ("collect",)):
        assert cli(*step, "--run", "pilot", "--stub") == 0, step
    for step in (("prepare", "--round", 2), ("send", "--round", 2, "--yes"), ("collect",), ("summary",)):
        assert cli(*step, *args) == 0, step
    s = read_json(stub_dir("pilot_wording") / "summary.json")["settings"]
    wording = {"haiku_off", "haiku_medium", "sonnet_off", *settings.PANEL}
    assert set(s) - {"total"} == wording
    for name in wording:
        r2 = requests_of(name, 2, "pilot_wording")
        ns = read_jsonl(run.not_sent_path(stub_dir("pilot_wording"), name))
        assert len(r2) + len(ns) == 60 and {r["kind"] for r in r2} == {"t2"}
        assert {r["item_id"] for r in r2 + ns} == {f"pil{i:03d}" for i in range(1, 11)}
        assert all(r["messages"][2]["content"].endswith(prompts.REQUEST) for r in r2)
        win, errs = run.winners(results_of(name, "pilot_wording"))
        assert set(win) == {r["custom_id"] for r in r2} and not errs
        assert (s[name]["results"], s[name]["errors_only"], s[name]["in_flight"]) == (len(r2), 0, 0)
    assert not run.requests_path(stub_dir("pilot_wording"), "haiku_off", 1).exists()


def test_a_completed_openrouter_batch_with_results_null_is_polled_again(env, capsys, monkeypatch):
    monkeypatch.setattr(stub, "RESULTS_NULL_POLLS", 1)
    args = ("--run", "pilot_batch_test", "--stub", "--setting", "gpt6luna")
    assert cli("prepare", *args, "--round", 1) == 0
    assert cli("send", *args, "--round", 1, "--yes") == 0
    capsys.readouterr()
    assert cli("collect", *args) == 0
    assert "still running" in capsys.readouterr().out
    assert not run.results_path(stub_dir("pilot_batch_test"), "gpt6luna").exists()
    assert cli("collect", *args) == 0
    win, errs = run.winners(results_of("gpt6luna", r="pilot_batch_test"))
    assert len(win) == 10 and not errs


# -------------------------------------------------------------------------------------------- send guards

def test_send_without_yes_sends_nothing(env, capsys):
    args = ("--run", "pilot", "--stub", "--setting", "mistral_small", "--round", 1)
    assert cli("prepare", *args) == 0
    capsys.readouterr()
    assert cli("send", *args) == run.NO_YES
    assert "not sent: add --yes to send" in capsys.readouterr().out
    assert not run.results_path(stub_dir(), "mistral_small").exists()


def test_the_spend_cap_stops_a_send(env, capsys):
    args = ("--run", "pilot", "--stub", "--setting", "mistral_small", "--round", 1)
    assert cli("prepare", *args) == 0
    capsys.readouterr()
    assert cli("send", *args, "--yes", "--spend-cap", 0.000001) == run.OVER_CAP
    assert "exceeds --spend-cap" in capsys.readouterr().out
    assert not run.results_path(stub_dir(), "mistral_small").exists()


def test_a_paid_send_needs_a_spend_cap(env, capsys):
    assert cli("send", "--run", "pilot", "--round", 1, "--yes") == run.ERROR
    assert "--spend-cap" in capsys.readouterr().err
    assert not (config.RUNS / "pilot").exists()


def test_a_send_after_a_full_send_has_nothing_to_send(env, capsys):
    args = ("--run", "pilot", "--stub", "--setting", "mistral_small", "--round", 1)
    assert cli("prepare", *args) == 0
    assert cli("send", *args, "--yes") == 0
    capsys.readouterr()
    assert cli("send", *args, "--yes") == 0
    assert "nothing to send" in capsys.readouterr().out
    assert len(results_of("mistral_small")) == 40


@pytest.mark.parametrize("name,route,message", [
    ("haiku_off", "sync", "Message Batches"),
    ("gpt_oss_120b", "batch", "HF has no batch route"),
    ("gemini_flash_lite", "batch", "no OpenRouter batch provider serves google/gemini-3.1-flash-lite"),
])
def test_a_route_the_plan_rules_out_is_refused(env, capsys, name, route, message):
    args = ("--run", "pilot", "--stub", "--setting", name, "--round", 1)
    assert cli("prepare", *args) == 0
    capsys.readouterr()
    assert cli("send", *args, "--route", route, "--yes") == run.ERROR
    assert message in capsys.readouterr().err
    assert not run.results_path(stub_dir(), name).exists()


def test_an_unknown_setting_is_refused(env, capsys):
    assert cli("prepare", "--run", "pilot_batch_test", "--stub", "--round", 1, "--setting", "haiku_off") == run.ERROR
    assert "has no setting haiku_off" in capsys.readouterr().err


# ---------------------------------------------------------------------------------------- errors and retries

def test_retry_failed_sends_errors_again(env, capsys, monkeypatch):
    args = ("--run", "pilot", "--stub", "--setting", "mistral_small", "--round", 1)
    assert cli("prepare", *args) == 0
    every = {r["custom_id"] for r in requests_of("mistral_small", 1)}
    bad = [r["custom_id"] for r in requests_of("mistral_small", 1)[:3]]
    monkeypatch.setattr(stub, "ERROR_IDS", set(bad))
    assert cli("send", *args, "--yes") == 0
    win, errs = run.winners(results_of("mistral_small"))
    assert errs == set(bad) and len(win) == 37
    capsys.readouterr()
    assert cli("send", *args, "--yes") == 0
    assert "nothing to send" in capsys.readouterr().out
    monkeypatch.setattr(stub, "ERROR_IDS", set())
    assert cli("send", *args, "--yes", "--retry-failed") == 0
    win, errs = run.winners(results_of("mistral_small"))
    assert set(win) == every and not errs


def test_an_errored_sync_request_keeps_its_error_and_no_cost(env, monkeypatch):
    args = ("--run", "pilot", "--stub", "--setting", "llama4_scout", "--round", 1)
    assert cli("prepare", *args) == 0
    bad = requests_of("llama4_scout", 1)[0]["custom_id"]
    monkeypatch.setattr(stub, "ERROR_IDS", {bad})
    assert cli("send", *args, "--yes") == 0
    rec = next(r for r in results_of("llama4_scout") if r["custom_id"] == bad)
    assert rec["status"] == "error" and rec["parsed"] is None and rec["cost_usd"] is None
    assert rec["error"]["status"] == 400


def test_winners_keep_the_first_result_that_is_not_an_error():
    recs = [{"custom_id": "a", "status": "error", "n": 1}, {"custom_id": "a", "status": "ok", "n": 2},
            {"custom_id": "b", "status": "error", "n": 3},
            {"custom_id": "c", "status": "ok", "n": 4}, {"custom_id": "c", "status": "error", "n": 5},
            {"custom_id": "c", "status": "missing", "n": 6}, {"custom_id": None, "status": "ok", "n": 7}]
    win, errs = run.winners(recs)
    assert {k: v["n"] for k, v in win.items()} == {"a": 2, "c": 4}
    assert errs == {"b"}


def test_a_partial_last_line_is_kept_apart_and_skipped(tmp_path, capsys):
    path = tmp_path / "x.jsonl"
    path.write_text('{"custom_id": "a"}\n{"custom_id": "b", "sta', encoding="utf-8")
    append_jsonl_many(path, [{"custom_id": "c"}])
    assert [r["custom_id"] for r in read_jsonl(path)] == ["a", "c"]
    assert "line 2 does not decode" in capsys.readouterr().err


# ---------------------------------------------------------------------------------------------- dry runs

def test_a_batch_dry_run_writes_the_batch_bodies(env, capsys):
    args = ("--run", "pilot_batch_test", "--stub", "--round", 1)
    assert cli("prepare", *args) == 0
    capsys.readouterr()
    assert cli("send", *args, "--dry-run") == 0
    assert "dry run: nothing was sent" in capsys.readouterr().out
    for name, provider in (("gpt6luna", "openai"), ("deepseek_flash", "deepinfra")):
        lines = read_jsonl(stub_dir("pilot_batch_test") / "dryrun" / f"{name}-r1-batch.jsonl")
        assert len(lines) == 1 and lines[0]["chunk"] == 1
        payload = lines[0]["payload"]
        assert list(payload) == ["endpoint", "model", "provider", "completion_window", "requests"]
        assert payload["provider"] == {"only": [provider], "allow_fallbacks": False}
        assert len(payload["requests"]) == 10
        assert not run.results_path(stub_dir("pilot_batch_test"), name).exists()
    assert not (stub_dir("pilot_batch_test") / "stub_store").exists()


def test_a_dry_run_without_stub_reads_no_key_and_sends_nothing(env, capsys):
    args = ("--run", "pilot", "--setting", "mistral_small", "--round", 1)
    assert cli("prepare", *args) == 0
    assert cli("send", *args, "--dry-run") == 0
    lines = read_jsonl(config.RUNS / "pilot" / "dryrun" / "mistral_small-r1-sync.jsonl")
    assert len(lines) == 40
    assert list(lines[0]) == ["custom_id", "body"]
    assert lines[0]["body"]["provider"]["only"] == ["mistral/zdr"]
    assert "dry run: nothing was sent" in capsys.readouterr().out
    assert not run.results_path(config.RUNS / "pilot", "mistral_small").exists()
    assert not (config.RUNS / "pilot" / "stub_store").exists()


# ------------------------------------------------------------------------------------------- open batches

def test_requests_in_open_batches_are_not_sent_twice(env, capsys, monkeypatch):
    monkeypatch.setattr(stub, "BATCH_POLLS_BEFORE_END", 5)
    args = ("--run", "pilot", "--stub", "--setting", "haiku_off")
    assert cli("prepare", *args, "--round", 1) == 0
    assert cli("send", *args, "--round", 1, "--yes") == 0
    capsys.readouterr()
    assert cli("collect", *args) == 0
    assert "still running" in capsys.readouterr().out
    assert cli("send", *args, "--round", 1, "--yes") == 0
    assert "nothing to send" in capsys.readouterr().out
    assert cli("send", *args, "--round", 1, "--yes", "--include-in-flight") == 0
    assert "sent (150 requests" in capsys.readouterr().out
    monkeypatch.setattr(stub, "BATCH_POLLS_BEFORE_END", 0)
    assert cli("collect", *args) == 0
    subs = run.submissions(stub_dir())
    assert len(subs) == 2 and {s["state"] for s in subs.values()} == {"closed"}
    win, errs = run.winners(results_of("haiku_off"))
    assert len(win) == 150 and not errs


def test_collect_wait_polls_until_the_batch_ends(env, capsys, monkeypatch):
    monkeypatch.setattr(stub, "BATCH_POLLS_BEFORE_END", 3)
    sleeps = []
    monkeypatch.setattr(run, "SLEEP", sleeps.append)
    args = ("--run", "pilot", "--stub", "--setting", "sonnet_high")
    assert cli("prepare", *args, "--round", 1) == 0
    assert cli("send", *args, "--round", 1, "--yes") == 0
    assert cli("collect", *args, "--wait", "--max-wait", 10) == 0
    assert sleeps == [run.POLL_S] * 3
    assert len(run.winners(results_of("sonnet_high"))[0]) == 10


def test_a_cancelled_batch_gives_errors_that_retry_failed_sends_again(env, capsys, monkeypatch):
    monkeypatch.setattr(stub, "BATCH_POLLS_BEFORE_END", 5)
    args = ("--run", "pilot", "--stub", "--setting", "haiku_off")
    assert cli("prepare", *args, "--round", 1) == 0
    assert cli("send", *args, "--round", 1, "--yes") == 0
    lid = next(iter(run.submissions(stub_dir())))
    assert cli("cancel", "--run", "pilot", "--stub", "--local-id", lid) == 0
    assert cli("collect", *args) == 0
    win, errs = run.winners(results_of("haiku_off"))
    assert not win and len(errs) == 150
    assert run.submissions(stub_dir())[lid]["cancel_requested"]
    monkeypatch.setattr(stub, "BATCH_POLLS_BEFORE_END", 0)
    assert cli("send", *args, "--round", 1, "--yes", "--retry-failed") == 0
    assert cli("collect", *args) == 0
    win, errs = run.winners(results_of("haiku_off"))
    assert len(win) == 150 and not errs


def test_only_an_open_anthropic_batch_can_be_cancelled(env, capsys):
    args = ("--run", "pilot_batch_test", "--stub", "--setting", "gpt6luna")
    assert cli("prepare", *args, "--round", 1) == 0
    assert cli("send", *args, "--round", 1, "--yes") == 0
    lid = next(iter(run.submissions(stub_dir("pilot_batch_test"))))
    capsys.readouterr()
    assert cli("cancel", "--run", "pilot_batch_test", "--stub", "--local-id", lid) == run.ERROR
    assert "only an Anthropic batch can be cancelled" in capsys.readouterr().err


# ------------------------------------------------------------------------------- batch creates that fail

def test_a_batch_made_without_a_reply_can_be_adopted(env, capsys, monkeypatch):
    args = ("--run", "pilot", "--stub", "--setting", "haiku_off")
    assert cli("prepare", *args, "--round", 1) == 0
    monkeypatch.setattr(stub, "SUBMIT_FAILS", "uncertain_created")
    capsys.readouterr()
    assert cli("send", *args, "--round", 1, "--yes") == run.SUBMIT_STOPPED
    assert "ended without a reply" in capsys.readouterr().err
    assert cli("send", *args, "--round", 1, "--yes") == 0
    assert "nothing to send" in capsys.readouterr().out
    assert cli("batches", "--run", "pilot", "--stub", "--api", "anthropic") == 0
    assert "tied to no submission" in capsys.readouterr().out
    bid = stub.StubAnthropic(stub_dir() / "stub_store").list_batches()[0]["id"]
    lid = next(k for k, s in run.submissions(stub_dir()).items() if s["state"] == "uncertain")
    assert cli("adopt", "--run", "pilot", "--stub", "--local-id", lid, "--batch-id", bid) == 0
    assert cli("adopt", "--run", "pilot", "--stub", "--local-id", lid, "--batch-id", bid) == run.ERROR
    assert cli("collect", *args) == 0
    win, errs = run.winners(results_of("haiku_off"))
    assert len(win) == 150 and not errs
    assert run.submissions(stub_dir())[lid]["state"] == "closed"


def test_a_lost_batch_create_can_be_released_and_sent_again(env, capsys, monkeypatch):
    args = ("--run", "pilot", "--stub", "--setting", "haiku_off")
    assert cli("prepare", *args, "--round", 1) == 0
    monkeypatch.setattr(stub, "SUBMIT_FAILS", "uncertain_lost")
    assert cli("send", *args, "--round", 1, "--yes") == run.SUBMIT_STOPPED
    capsys.readouterr()
    assert cli("send", *args, "--round", 1, "--yes") == 0
    assert "nothing to send" in capsys.readouterr().out
    lid = next(k for k, s in run.submissions(stub_dir()).items() if s["state"] == "uncertain")
    assert cli("release", "--run", "pilot", "--stub", "--local-id", lid) == 0
    assert "can be sent again" in capsys.readouterr().err
    assert cli("send", *args, "--round", 1, "--yes") == 0
    assert "sent (150 requests" in capsys.readouterr().out


def test_a_refused_batch_create_leaves_its_requests_free(env, capsys, monkeypatch):
    args = ("--run", "pilot", "--stub", "--setting", "haiku_off")
    assert cli("prepare", *args, "--round", 1) == 0
    monkeypatch.setattr(stub, "SUBMIT_FAILS", "certain")
    capsys.readouterr()
    assert cli("send", *args, "--round", 1, "--yes") == run.SUBMIT_STOPPED
    assert "refused" in capsys.readouterr().err
    assert [s["state"] for s in run.submissions(stub_dir()).values()] == ["failed"]
    assert cli("send", *args, "--round", 1, "--yes") == 0
    assert "sent (150 requests" in capsys.readouterr().out


# -------------------------------------------------------------------------------- prepare, lock and status

def test_round2_after_a_partial_round1_needs_allow_missing(env, capsys):
    args = ("--run", "pilot", "--stub", "--setting", "mistral_small")
    assert cli("prepare", *args, "--round", 1) == 0
    assert [r["kind"] for r in requests_of("mistral_small", 1)[:5]] == ["t1", "probe", "t1", "probe", "t1"]
    assert cli("send", *args, "--round", 1, "--yes", "--limit", 5) == 0
    capsys.readouterr()
    assert cli("prepare", *args, "--round", 2) == run.ERROR
    assert "turn-1 requests have no result" in capsys.readouterr().err
    assert cli("prepare", *args, "--round", 2, "--allow-missing") == 0
    r2 = requests_of("mistral_small", 2)
    ns = read_jsonl(run.not_sent_path(stub_dir(), "mistral_small"))
    assert len(r2) + len(ns) == 120
    assert sum(r["reason"] == "turn 1 has no result" for r in ns) == 102
    assert {r["status"] for r in ns} == {"not_sent"}


def test_prepare_keeps_an_unchanged_file_and_backs_up_a_replaced_one(env, capsys):
    args = ("--run", "pilot", "--stub", "--setting", "mistral_small", "--round", 1)
    assert cli("prepare", *args) == 0
    capsys.readouterr()
    assert cli("prepare", *args) == 0
    assert "already prepared and unchanged" in capsys.readouterr().out
    path = run.requests_path(stub_dir(), "mistral_small", 1)
    with open(path, "a", encoding="utf-8") as fh:
        fh.write('{"x": 1}\n')
    assert cli("prepare", *args) == run.ERROR
    assert "exists with other content" in capsys.readouterr().err
    assert cli("prepare", *args, "--replace") == 0
    assert list(path.parent.glob("mistral_small-r1.jsonl.replaced-*"))
    assert len(read_jsonl(path)) == 40


def test_prepare_without_the_item_file_says_which_stage_to_run(env, capsys):
    (config.ITEMS / "pilot_items.json").unlink()
    assert cli("prepare", "--run", "pilot", "--stub", "--round", 1) == run.ERROR
    assert "fetch_items.py" in capsys.readouterr().err


def test_the_lock_refuses_a_second_command_and_clears_a_stale_one(env, capsys):
    args = ("--run", "pilot", "--stub", "--setting", "mistral_small", "--round", 1)
    lock = stub_dir() / ".lock"
    lock.parent.mkdir(parents=True)
    lock.write_text(str(os.getpid()))
    assert cli("prepare", *args) == run.ERROR
    assert "is held by process" in capsys.readouterr().err
    lock.write_text("")
    old = time.time() - 60
    os.utime(lock, (old, old))
    assert cli("prepare", *args) == 0
    assert not lock.exists()


def test_status_names_the_run_folder_first(env, capsys):
    assert cli("prepare", "--run", "pilot", "--stub", "--setting", "mistral_small", "--round", 1) == 0
    capsys.readouterr()
    assert cli("status", "--run", "pilot", "--stub") == 0
    out = capsys.readouterr().out.splitlines()
    assert out[0] == str(stub_dir())
    row = next(line for line in out if line.startswith("mistral_small"))
    assert row.split()[1:3] == ["40", "0"]
