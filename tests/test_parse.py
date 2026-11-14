"""PLAN 4.8 parser on made-up replies: the parse rules, the statuses, the near-miss codes and the flags."""
import pytest

from pipeline import parse as P

T1 = '{"reasoning": "Works are late.", "probability": 35, "prepare": false}'
T2 = '{"reasoning": "No new facts.", "probability": 35, "prepare": false, "changed": false, "previous_probability": 35}'


def run(text, kind="t1", stop="normal"):
    return P.parse_reply(text, kind, stop)


def test_plain_turn1_reply():
    out = run(T1)
    assert out["status"] == "ok" and out["reason"] is None
    assert out["parsed"] == {"reasoning": "Works are late.", "probability": 35, "prepare": False}
    assert list(out["parsed"]) == ["reasoning", "probability", "prepare"]
    assert out["flags"] == [] and out["near_miss"] == [] and out["reasoning_words"] == 3 and out["core_ok"] is None


@pytest.mark.parametrize("text", ["```json\n" + T1 + "\n```", "```\n" + T1 + "\n```", "  ```JSON " + T1 + "```  "])
def test_one_enclosing_fence_is_stripped(text):
    out = run(text)
    assert out["status"] == "ok" and out["flags"] == ["fenced"]


def test_text_around_the_object_and_a_second_object():
    out = run("Here is my answer: " + T1)
    assert out["status"] == "ok" and out["flags"] == ["text_before_object"]
    out = run(T1 + "\nHope this helps.")
    assert out["status"] == "ok" and out["flags"] == ["text_after_object"]
    out = run(T1 + ' {"probability": 90, "prepare": true}')
    assert out["status"] == "ok" and out["flags"] == ["text_after_object", "second_object"]
    assert out["parsed"]["probability"] == 35   # the first complete object is taken (rule 1)


def test_first_complete_object_inside_an_array():
    out = run("[" + T1 + "]")
    assert out["status"] == "ok" and out["flags"] == ["text_before_object", "text_after_object"]


def test_extra_keys_are_flagged_and_dropped():
    out = run('{"reasoning": "x", "probability": 35, "prepare": true, "confidence": "high"}')
    assert out["status"] == "ok" and out["flags"] == ["extra_keys"]
    assert "confidence" not in out["parsed"]


@pytest.mark.parametrize("p", ["0", "100", "0.0", "100.0", "57.5"])
def test_probability_range_is_inclusive(p):
    assert run('{"probability": %s, "prepare": true}' % p)["status"] == "ok"


@pytest.mark.parametrize("p,reason", [("100.5", "probability out of range"), ("-1", "probability out of range"),
                                      ("true", "probability not a number"), ("null", "probability not a number"),
                                      ('[35]', "probability not a number")])
def test_probability_outside_the_rule(p, reason):
    out = run('{"probability": %s, "prepare": true}' % p)
    assert out["status"] == "missing" and out["reason"] == reason and out["parsed"] is None


@pytest.mark.parametrize("p", ["NaN", "Infinity", "-Infinity"])
def test_nan_and_infinity_never_parse(p):
    out = run('{"probability": %s, "prepare": true}' % p)
    assert out["status"] == "missing" and out["reason"] == "no complete JSON object"


def test_fraction_is_valid_and_flagged():
    out = run('{"probability": 0.35, "prepare": true}')
    assert out["status"] == "ok" and out["near_miss"] == ["probability_fraction"]
    assert run('{"probability": 1, "prepare": true}')["near_miss"] == []


def test_percent_string_is_coded_once():
    out = run('{"probability": "35%", "prepare": true}')
    assert out["status"] == "missing" and out["near_miss"] == ["probability_percent_string"]
    assert out["reason"] == "probability not a number"


def test_bare_percent_sign():
    out = run('{"reasoning": "x", "probability": 35%, "prepare": true}')
    assert out["status"] == "missing" and out["reason"] == "no complete JSON object"
    assert out["near_miss"] == ["percent_sign"]


def test_bare_percent_sign_in_a_broken_object_with_a_nested_object():
    out = run('{"probability": 35 %, "prepare": true, "sources": {"news": 2}}')
    assert out["status"] == "missing" and out["parsed"] is None
    assert out["reason"] == "probability missing; prepare missing"
    assert out["near_miss"] == ["percent_sign"]


def test_number_and_bool_strings():
    out = run('{"probability": "35", "prepare": "yes"}')
    assert out["near_miss"] == ["probability_string", "prepare_string"]
    assert out["reason"] == "probability not a number; prepare not true or false"
    out = run('{"probability": 35, "prepare": 1}')
    assert out["near_miss"] == ["prepare_number"] and out["status"] == "missing"


def test_python_literals_and_single_quotes():
    out = run("{'reasoning': 'x', 'probability': 35, 'prepare': True}")
    assert out["status"] == "missing" and out["near_miss"] == ["single_quotes", "python_literal"]
    out = run('{"probability": 35, "prepare": False}')
    assert out["near_miss"] == ["python_literal"]


def test_trailing_comma():
    out = run('{"probability": 35, "prepare": true,}')
    assert out["status"] == "missing" and out["near_miss"] == ["trailing_comma"]
    assert run("I would say 35, maybe 40.")["near_miss"] == []


def test_key_case():
    out = run('{"Probability": 35, "prepare": true}')
    assert out["status"] == "missing" and out["near_miss"] == ["probability_key_case"]
    assert "extra_keys" in out["flags"]


def test_missing_reasoning_still_parses():
    out = run('{"probability": 35, "prepare": true}')
    assert out["status"] == "ok" and out["flags"] == ["reasoning_missing"] and "reasoning" not in out["parsed"]
    out = run('{"reasoning": null, "probability": 35, "prepare": true}')
    assert out["status"] == "ok" and out["flags"] == ["reasoning_missing"]
    out = run('{"reasoning": 5, "probability": 35, "prepare": true}')
    assert out["status"] == "ok" and out["flags"] == ["reasoning_not_string"] and out["reasoning_words"] is None


def test_turn2_fields_and_core_ok():
    out = run(T2, "t2")
    assert out["status"] == "ok" and out["core_ok"] is True and out["failed_fields"] == []
    assert list(out["parsed"]) == ["reasoning", "probability", "prepare", "changed", "previous_probability"]
    # PLAN 4.8 arm-level failure and 7.10, decided on 11 November 2026: a turn-2 reply is missing only for the
    # measures that use a field that failed, so the valid fields are kept and the failed ones are named
    out = run('{"probability": 40, "prepare": false, "changed": true}', "t2")
    assert out["status"] == "partial" and out["reason"] == "previous_probability missing" and out["core_ok"] is True
    assert out["parsed"] == {"probability": 40, "prepare": False, "changed": True}
    assert out["failed_fields"] == ["previous_probability"]
    out = run('{"probability": "40%", "prepare": false, "changed": true, "previous_probability": 35}', "t2")
    assert out["status"] == "partial" and out["core_ok"] is False and out["failed_fields"] == ["probability"]
    assert out["parsed"] == {"prepare": False, "changed": True, "previous_probability": 35}
    assert out["near_miss"] == ["probability_percent_string"]
    out = run('{"probability": 40, "prepare": false, "changed": "no", "previous_probability": 135}', "t2")
    assert out["reason"] == "changed not true or false; previous_probability out of range" and out["core_ok"] is True
    assert out["status"] == "partial" and out["failed_fields"] == ["changed", "previous_probability"]
    assert out["parsed"] == {"probability": 40, "prepare": False}


def test_a_null_previous_probability_is_partial():
    """The llama-4-scout replies of the re-check of 11 November 2026 gave a null previous_probability."""
    text = '{"reasoning": "No new facts.", "probability": 35, "prepare": false, "changed": false, ' \
           '"previous_probability": null}'
    out = run(text, "t2")
    assert out["status"] == "partial" and out["reason"] == "previous_probability not a number"
    assert out["parsed"] == {"reasoning": "No new facts.", "probability": 35, "prepare": False, "changed": False}
    assert out["failed_fields"] == ["previous_probability"] and out["core_ok"] is True
    assert P.has(out, "probability", "prepare", "changed") and not P.has(out, "previous_probability")


def test_partial_turn2_without_the_fields():
    out = run('{"reasoning": "x", "probability": 40, "prepare": "yes"}', "t2_nf")
    assert out["status"] == "partial" and out["failed_fields"] == ["prepare"] and out["core_ok"] is False
    assert out["parsed"] == {"reasoning": "x", "probability": 40} and out["near_miss"] == ["prepare_string"]


def test_a_reply_with_every_field_failed_is_missing():
    out = run('{"reasoning": "x", "probability": "high", "prepare": "yes", "changed": 1}', "t2")
    assert out["status"] == "missing" and out["parsed"] is None
    assert out["failed_fields"] == ["probability", "prepare", "changed", "previous_probability"]
    for text in ("", "no object here"):
        out = run(text, "t2")
        assert out["status"] == "missing" and out["failed_fields"] == list(P.REQUIRED["t2"])
        assert not P.has(out, "probability")


def test_turn1_and_probe_are_never_partial():
    out = run('{"reasoning": "x", "probability": 40, "prepare": "yes"}')
    assert out["status"] == "missing" and out["parsed"] is None and out["failed_fields"] == ["probability", "prepare"]
    out = run('{"known": true, "outcome": "maybe"}', "probe")
    assert out["status"] == "missing" and out["parsed"] is None and out["failed_fields"] == ["known", "outcome"]


def test_partial_reply_cut_or_refused():
    text = '{"probability": 40, "prepare": false, "changed": true, "previous_probability": null} and then'
    out = run(text, "t2", stop="cut")
    assert out["status"] == "partial" and "cut_after_complete_object" in out["flags"]
    assert out["reason"] == "previous_probability not a number" and out["failed_fields"] == ["previous_probability"]
    out = run(text, "t2", stop="refusal")
    assert out["status"] == "refusal" and out["parsed"] is None
    assert "refusal_with_valid_object" not in out["flags"]
    assert out["failed_fields"] == list(P.REQUIRED["t2"])
    out = run(T2, "t2", stop="refusal")
    assert "refusal_with_valid_object" in out["flags"] and out["failed_fields"] == list(P.REQUIRED["t2"])


def test_has_reads_stored_records():
    assert not P.has(None, "probability")
    assert P.has({"status": "ok", "parsed": {"probability": 40, "prepare": True}}, "probability", "prepare")
    assert P.has({"status": "partial", "parsed": {"probability": 40}}, "probability")
    assert not P.has({"status": "partial", "parsed": {"probability": 40}}, "probability", "prepare")
    for status in ("missing", "cut", "refusal", "error"):
        assert not P.has({"status": status, "parsed": {"probability": 40}}, "probability")
    assert not P.has({"status": "ok", "parsed": None}, "probability")


def test_turn2_without_the_fields():
    out = run('{"reasoning": "x", "probability": 40, "prepare": false}', "t2_nf")
    assert out["status"] == "ok" and out["core_ok"] is True and out["flags"] == []
    out = run(T2, "t2_nf")
    assert out["status"] == "ok" and out["flags"] == ["extra_keys"]


def test_probe_replies():
    out = run('{"known": true, "outcome": "yes"}', "probe")
    assert out["status"] == "ok" and out["parsed"] == {"known": True, "outcome": "yes"} and out["flags"] == []
    out = run('{"known": false, "outcome": "Unknown."}', "probe")
    assert out["status"] == "missing" and out["near_miss"] == ["outcome_case_or_punctuation"]
    out = run('{"known": "false", "outcome": "maybe"}', "probe")
    assert out["reason"] == "known not true or false; outcome not yes, no or unknown"
    assert out["near_miss"] == ["known_string"]


def test_empty_reply():
    for text in ("", "   ", None):
        out = run(text)
        assert out["status"] == "missing" and out["reason"] == "empty reply"


def test_refusal_is_its_own_outcome():
    out = run(T1, stop="refusal")
    assert out["status"] == "refusal" and out["parsed"] is None and out["reason"] == "stop reason refusal"
    assert "refusal_with_valid_object" in out["flags"]
    out = run("I can't help with that.", stop="refusal")
    assert out["status"] == "refusal" and out["reason"] == "stop reason refusal; no complete JSON object"
    assert "refusal_with_valid_object" not in out["flags"]


def test_cut_at_the_output_cap():
    out = run(T1 + " And more text that ran", stop="cut")
    assert out["status"] == "ok" and "cut_after_complete_object" in out["flags"] and out["reason"] is None
    out = run('{"reasoning": "The bridge works are', stop="cut")
    assert out["status"] == "cut" and out["parsed"] is None
    assert out["reason"] == "stopped at the output cap; no complete JSON object"


def test_unusual_stop_reason_keeps_the_status():
    out = run(T1, stop="other")
    assert out["status"] == "ok" and out["flags"] == ["unusual_stop_reason"]
    assert run("", stop="other")["status"] == "missing"


def test_unknown_kind():
    with pytest.raises(ValueError):
        run(T1, "t3")


@pytest.mark.parametrize("api,reason,kind", [
    ("anthropic", "end_turn", "normal"), ("anthropic", "stop_sequence", "normal"),
    ("anthropic", "max_tokens", "cut"), ("anthropic", "model_context_window_exceeded", "cut"),
    ("anthropic", "refusal", "refusal"), ("anthropic", "tool_use", "other"), ("anthropic", "pause_turn", "other"),
    ("anthropic", None, "other"),
    ("openrouter", "stop", "normal"), ("openrouter", "length", "cut"), ("openrouter", "content_filter", "refusal"),
    ("openrouter", "tool_calls", "other"), ("openrouter", None, "other"),
    ("hf", "stop", "normal"), ("hf", "eos", "normal"), ("hf", "length", "cut"), ("hf", "content_filter", "refusal"),
])
def test_stop_kinds(api, reason, kind):
    assert P.stop_kind(api, reason) == kind


def test_near_misses_never_change_a_status():
    ok = run('{"probability": 0.5, "prepare": true}')
    assert ok["near_miss"] and ok["status"] == "ok"
