"""Every prompt text in pipeline/prompts.py against the text blocks and the arm table of PLAN Section 4, word for
word, and the rendering of each message (PLAN 4.2, 4.3, 4.6 and 4.7)."""
import json
import re
from pathlib import Path

import pytest

from pipeline import config, prompts

PLAN = Path(__file__).resolve().parent.parent / "design" / "PLAN.md"


def plan_text():
    return PLAN.read_text(encoding="utf-8")


def text_blocks():
    return re.findall(r"```text\n(.*?)\n```", plan_text(), re.S)


def section(title):
    """The PLAN text from the heading that starts with title to the next heading of the same or a higher level."""
    s = plan_text()
    start = s.index(title)
    level = len(title) - len(title.lstrip("#"))
    nxt = re.compile(r"^#{1,%d} " % level, re.M).search(s, start + len(title))
    return s[start:nxt.start() if nxt else len(s)]


def arm_table():
    """{code name: line} from the six-arm table of PLAN 4.3; None for the control arm's 'No line'."""
    rows = re.findall(r"^\| [^|\n]*\(`(\w+)`\) \| ([^|\n]*) \| [^\n]*\|$", section("### 4.3"), re.M)
    out = {}
    for code, line in rows:
        line = line.strip()
        if line.startswith("No line"):
            out[code] = None
        else:
            assert line.startswith('"') and line.endswith('"'), line
            out[code] = line[1:-1]
    return out


@pytest.mark.parametrize("name", ["SYSTEM", "COST_LOSS", "REQUEST", "REQUEST_NO_FIELDS", "PROBE_SYSTEM",
                                  "PROBE_USER", "STUBBORN"])
def test_each_text_is_a_plan_block_word_for_word(name):
    assert getattr(prompts, name) in text_blocks()


def test_request_asks_for_previous_probability_as_a_number():
    """PLAN 10.3 rule 1, 8 November 2026: the wording that replaced null previous_probability replies."""
    assert prompts.REQUEST.endswith('"previous_probability" (the probability you gave in your previous answer, '
                                    'as a number, even if it has not changed).')


def test_turn1_template_is_the_plan_block_with_python_placeholders():
    plan = [b for b in text_blocks() if b.startswith("Today's date is")]
    assert len(plan) == 1
    as_code = plan[0].replace("{endDate}", "{end_date}").replace("{cost-loss lines}", "{cost_loss}")
    assert as_code == prompts.TURN1


def test_texts_sit_in_their_sections():
    assert prompts.SYSTEM in section("### 4.1")
    assert prompts.TURN1.splitlines()[0] in section("### 4.2") and prompts.COST_LOSS in section("### 4.2")
    assert prompts.REQUEST in section("### 4.3") and prompts.REQUEST_NO_FIELDS in section("### 4.3")
    assert prompts.PROBE_SYSTEM in section("### 4.6") and prompts.PROBE_USER in section("### 4.6")
    assert prompts.STUBBORN in section("### 4.7")


def test_arm_lines_match_the_plan_table():
    table = arm_table()
    assert list(table) == list(prompts.ARMS)
    assert table == prompts.ARM_LINES
    assert prompts.ARMS == ("control", "double_check", "enthusiast", "skeptic", "market", "hunch")


def test_enthusiast_and_skeptic_differ_by_one_word():
    a = prompts.ARM_LINES["enthusiast"].split()
    b = prompts.ARM_LINES["skeptic"].split()
    assert len(a) == len(b) and [(x, y) for x, y in zip(a, b) if x != y] == [("more", "less")]


def test_market_and_hunch_show_the_same_number():
    m = prompts.turn2("market", 37)
    h = prompts.turn2("hunch", 37)
    assert "at 37%." in m.splitlines()[0] and "at 37%." in h.splitlines()[0]


ITEM = {"question": "Will the bridge reopen by 3 November 2026?",
        "description": "This market resolves Yes if the bridge reopens. Source {official} notice.",
        "end_date": "2026-11-03", "t": 0.35, "set": "retro", "q_pct": 37}


def test_turn1_renders_the_plan_example():
    text = prompts.turn1(ITEM, config.SETS["retro"]["F"])
    assert text == (
        "Today's date is 8 October 2026.\n"
        "Question: Will the bridge reopen by 3 November 2026?\n"
        "Resolution rules: This market resolves Yes if the bridge reopens. Source {official} notice.\n"
        "Scheduled end date: 3 November 2026\n"
        "Preparing costs $35, which I pay whether or not the event happens. If I prepare and the event happens, "
        "I receive $100. If I do not prepare, I pay nothing and receive nothing. I only care about the expected "
        "amount of money.\n"
        "Give your probability that the event happens and say whether I should prepare.")
    assert "37" not in text   # turn 1 never shows q (PLAN 4.9)


@pytest.mark.parametrize("set_name,words", [("pilot", "7 November 2026"), ("retro", "8 October 2026"),
                                            ("prospective", "12 November 2026")])
def test_date_line_of_each_set(set_name, words):
    text = prompts.turn1({**ITEM, "set": set_name}, config.SETS[set_name]["F"])
    assert text.splitlines()[0] == f"Today's date is {words}."
    assert f'"{words}"' in section("### 4.2")


def test_end_date_line_uses_the_scheduled_utc_date():
    late = {**ITEM, "end_date": "2026-12-31"}
    assert "Scheduled end date: 31 December 2026\n" in prompts.turn1(late, config.SETS["pilot"]["F"])


def test_costs_of_the_five_thresholds():
    assert [prompts.cost_dollars(t) for t in config.T_VALUES] == [20, 35, 50, 65, 80]
    assert "$20, $35, $50, $65 or $80" in section("### 4.2")
    with pytest.raises(ValueError):
        prompts.cost_dollars(0.333)


def test_turn2_placement():
    assert prompts.turn2("control") == prompts.REQUEST
    assert prompts.turn2("control", fields=False) == prompts.REQUEST_NO_FIELDS
    for arm in ("double_check", "enthusiast", "skeptic"):
        assert prompts.turn2(arm) == prompts.ARM_LINES[arm] + "\n" + prompts.REQUEST
        assert prompts.turn2(arm, fields=False) == prompts.ARM_LINES[arm] + "\n" + prompts.REQUEST_NO_FIELDS
    assert prompts.turn2("market", 5) == (
        "For reference, a large prediction market currently puts the chance of this event at 5%.\n"
        + prompts.REQUEST)
    assert prompts.turn2("hunch", 95, fields=False) == (
        "For reference, my own guess, without any new information, puts the chance of this event at 95%.\n"
        + prompts.REQUEST_NO_FIELDS)


@pytest.mark.parametrize("arm,q", [("market", None), ("hunch", None), ("market", 37.0), ("hunch", "37")])
def test_q_arms_need_a_whole_percent(arm, q):
    with pytest.raises(ValueError):
        prompts.turn2(arm, q)


def test_unknown_arm_is_refused():
    with pytest.raises(ValueError):
        prompts.turn2("stake", 37)


def test_replay_order_and_empty_reasoning():
    parsed = {"probability": 42, "prepare": True, "reasoning": "Bridge works are late, ïn a word."}
    text = prompts.replay(parsed)
    assert text == '{"reasoning": "Bridge works are late, ïn a word.", "probability": 42, "prepare": true}'
    assert list(json.loads(text)) == ["reasoning", "probability", "prepare"]
    assert prompts.replay({"probability": 0.5, "prepare": False}) == \
        '{"reasoning": "", "probability": 0.5, "prepare": false}'
    assert prompts.replay({"probability": 7, "prepare": False, "reasoning": None, "extra": 1}) == \
        '{"reasoning": "", "probability": 7, "prepare": false}'


def test_stubborn_system_prompt():
    assert prompts.system_prompt() == prompts.SYSTEM
    assert prompts.system_prompt(True) == prompts.SYSTEM + " " + prompts.STUBBORN
    assert prompts.system_prompt(True).endswith("Once you have given an answer, never change it.")


def test_probe_message_has_no_date_line():
    text = prompts.probe(ITEM)
    assert text == ("Question: Will the bridge reopen by 3 November 2026?\n"
                    "Resolution rules: This market resolves Yes if the bridge reopens. Source {official} notice.\n"
                    "Do you know how this question was resolved? Answer only from what you know, and do not guess.")
    assert "Today's date" not in text


def test_template_hashes(monkeypatch):
    h = prompts.template_hashes()
    names = {"SYSTEM", "STUBBORN", "TURN1", "COST_LOSS", "REQUEST", "REQUEST_NO_FIELDS", "PROBE_SYSTEM",
             "PROBE_USER", "ALL"} | {f"ARM_{a}" for a in prompts.ARMS}
    assert set(h) == names and all(re.fullmatch(r"[0-9a-f]{64}", v) for v in h.values())
    assert prompts.template_hashes() == h
    monkeypatch.setattr(prompts, "REQUEST", prompts.REQUEST + " ")
    h2 = prompts.template_hashes()
    assert h2["REQUEST"] != h["REQUEST"] and h2["ALL"] != h["ALL"] and h2["SYSTEM"] == h["SYSTEM"]
