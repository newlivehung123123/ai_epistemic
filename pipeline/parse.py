"""PLAN 4.8 parser. The clients pass only the visible reply text, so thinking text never reaches this module.

Statuses
    ok        the first complete JSON object holds every required field with a valid value
    partial   a turn-2 reply (kinds t2 and t2_nf) whose first complete JSON object holds a valid value for some
              required fields and not for others; parsed holds the valid fields alone, and the reply is missing
              only for the measures that use a failed field (PLAN 4.8 arm-level failure and 7.10, DECIDED by
              Jason Hung on 11 November 2026)
    missing   any other reply, kept with the raw text and the reason
    cut       the reply stopped at the output cap and holds no usable complete object (PLAN 5.5)
    refusal   the stop reason is "refusal" (Anthropic) or "content_filter" (OR and HF), logged as its own
              outcome (PLAN 4.8 stop reasons, PLAN 10.3 rule 10)

failed_fields lists, in the order of REQUIRED, the required fields that a reply does not give to any measure: none
for ok, the failed fields for partial, and every required field for missing, cut and refusal. has() tells whether a
stored reply gives every field that a measure uses. A turn-1 reply and a probe reply are never partial, because a
turn 2 is built only from a turn 1 with every field valid (build.py).

Near misses are logged as codes and never change a status. The tolerance for each code is FROZEN at the freeze
(PLAN 4.8 near misses). A reply that fails to parse is never requested again (PLAN 4.8 no second request).
"""
from __future__ import annotations

import json
import re

KINDS = ("t1", "t2", "t2_nf", "probe")
REQUIRED = {
    "t1": ("probability", "prepare"),
    "t2": ("probability", "prepare", "changed", "previous_probability"),
    "t2_nf": ("probability", "prepare"),
    "probe": ("known", "outcome"),
}
PARTIAL_KINDS = ("t2", "t2_nf")   # PLAN 4.8 arm-level failure and 7.10: the kinds that can be partial
NUMBER_FIELDS = ("probability", "previous_probability")
BOOL_FIELDS = ("prepare", "changed", "known")
OUTCOMES = ("yes", "no", "unknown")

FENCE = re.compile(r"^```[A-Za-z0-9_-]*\s*(.*?)\s*```$", re.S)
NUM = re.compile(r"[+-]?(\d+(\.\d*)?|\.\d+)")
PERCENT_VALUE = re.compile(r'"(probability|previous_probability)"\s*:\s*"?\s*[+-]?\d+(\.\d+)?\s*%')
SINGLE_QUOTED_KEY = re.compile(r"'(reasoning|probability|prepare|changed|previous_probability|known|outcome)'\s*:")
TRAILING_COMMA = re.compile(r",\s*[}\]]")
PYTHON_LITERAL = re.compile(r"""['"]?(prepare|changed|known)['"]?\s*:\s*(True|False|None)\b""")

STOP_KINDS = {
    "anthropic": {"end_turn": "normal", "stop_sequence": "normal", "max_tokens": "cut",
                  "model_context_window_exceeded": "cut", "refusal": "refusal"},
    "openrouter": {"stop": "normal", "length": "cut", "content_filter": "refusal"},
    "hf": {"stop": "normal", "eos": "normal", "length": "cut", "content_filter": "refusal"},
}


def stop_kind(api: str, stop_reason) -> str:
    """normal, cut, refusal or other (tool calls, errors, an absent stop reason)."""
    return STOP_KINDS[api].get(stop_reason, "other")


def _reject_constant(name):
    raise ValueError(f"{name} is not valid JSON")


DECODER = json.JSONDecoder(parse_constant=_reject_constant)   # NaN and Infinity never parse as numbers


def is_number(x) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool)


def strip_fence(text: str) -> tuple[str, bool]:
    """Rule 1: one enclosing code fence is stripped if present."""
    s = text.strip()
    m = FENCE.match(s)
    return (m.group(1), True) if m else (s, False)


def first_object(text: str):
    """Rule 1: the first complete JSON object in the text, with its span, or (None, None)."""
    i = text.find("{")
    while i != -1:
        try:
            obj, end = DECODER.raw_decode(text, i)
        except ValueError:
            i = text.find("{", i + 1)
            continue
        if isinstance(obj, dict):
            return obj, (i, end)
        i = text.find("{", i + 1)
    return None, None


def _check_number(obj, key, reasons, near):
    v = obj[key]
    if isinstance(v, bool) or not is_number(v):
        reasons.append(f"{key} not a number")
        if isinstance(v, str):
            s = v.strip()
            if s.endswith("%") and NUM.fullmatch(s[:-1].strip()):
                near.append(f"{key}_percent_string")
            elif NUM.fullmatch(s):
                near.append(f"{key}_string")
        return
    if not 0 <= v <= 100:
        reasons.append(f"{key} out of range")
        return
    if 0 < v < 1:
        near.append(f"{key}_fraction")   # valid under rule 2, flagged as a possible 0-to-1 answer


def _check_bool(obj, key, reasons, near):
    v = obj[key]
    if not isinstance(v, bool):
        reasons.append(f"{key} not true or false")
        if isinstance(v, str) and v.strip().lower() in ("true", "false", "yes", "no"):
            near.append(f"{key}_string")
        elif v in (0, 1) and not isinstance(v, bool):
            near.append(f"{key}_number")


def _check_outcome(obj, reasons, near):
    v = obj["outcome"]
    if v in OUTCOMES:
        return
    reasons.append("outcome not yes, no or unknown")
    if isinstance(v, str) and v.strip().strip(".").lower() in OUTCOMES:
        near.append("outcome_case_or_punctuation")


def check_fields(obj: dict, kind: str):
    """Validate the required fields of one object. Returns (fields, reasons, near misses, core_ok)."""
    reasons, near = [], []
    for key in REQUIRED[kind]:
        if key not in obj:
            reasons.append(f"{key} missing")
            if any(isinstance(k, str) and k.strip().lower() == key and k != key for k in obj):
                near.append(f"{key}_key_case")
            continue
        if key in NUMBER_FIELDS:
            _check_number(obj, key, reasons, near)
        elif key in BOOL_FIELDS:
            _check_bool(obj, key, reasons, near)
        elif key == "outcome":
            _check_outcome(obj, reasons, near)
    fields = {k: obj[k] for k in REQUIRED[kind] if k in obj}
    core_ok = None
    if kind in ("t2", "t2_nf"):
        bad = {r.split(" ")[0] for r in reasons}
        core_ok = not ({"probability", "prepare"} & bad)
    return fields, reasons, near, core_ok


def has(rec, *fields) -> bool:
    """True when a stored reply gives a valid value for every named field: an ok reply, or a partial reply none of
    whose failed fields is named. A measure counts a turn-2 reply only when has() is true for every field that the
    measure uses (PLAN 4.8 arm-level failure and 7.10)."""
    return (rec is not None and rec.get("status") in ("ok", "partial") and isinstance(rec.get("parsed"), dict)
            and all(f in rec["parsed"] for f in fields))


def parse_reply(text, kind: str, stop: str = "normal") -> dict:
    """Parse one reply. text is the visible reply text only; stop is the result of stop_kind()."""
    if kind not in KINDS:
        raise ValueError(f"unknown kind {kind}")
    out = {"status": None, "reason": None, "parsed": None, "failed_fields": list(REQUIRED[kind]), "core_ok": None,
           "near_miss": [], "flags": [], "reasoning_words": None}
    text = "" if text is None else str(text)
    body, fenced = strip_fence(text)
    if fenced:
        out["flags"].append("fenced")
    obj, span = first_object(body)
    reasons, near, failed = [], [], list(REQUIRED[kind])
    if obj is None:
        reasons.append("empty reply" if not body.strip() else "no complete JSON object")
    else:
        if body[:span[0]].strip():
            out["flags"].append("text_before_object")
        rest = body[span[1]:]
        if rest.strip():
            out["flags"].append("text_after_object")
            if first_object(rest)[0] is not None:
                out["flags"].append("second_object")
        extra = sorted(set(obj) - set(REQUIRED[kind]) - {"reasoning"})
        if extra:
            out["flags"].append("extra_keys")
        fields, r, n, core_ok = check_fields(obj, kind)
        reasons += r
        near += n
        out["core_ok"] = core_ok
        bad = {x.split(" ")[0] for x in r}    # every reason of check_fields starts with its field
        failed = [k for k in REQUIRED[kind] if k in bad]
        fields = {k: v for k, v in fields.items() if k not in bad}
        if kind != "probe":
            if "reasoning" not in obj or obj["reasoning"] is None:
                out["flags"].append("reasoning_missing")
            elif isinstance(obj["reasoning"], str):
                out["reasoning_words"] = len(obj["reasoning"].split())
                fields = {"reasoning": obj["reasoning"], **fields}
            else:
                out["flags"].append("reasoning_not_string")
                fields = {"reasoning": obj["reasoning"], **fields}
        if not failed or (kind in PARTIAL_KINDS and len(failed) < len(REQUIRED[kind])):
            out["parsed"] = fields
    if failed:
        # Text-level formats close to valid. These run on every reply with a failed field, because a broken outer
        # object can leave a nested object as the first complete one, and the field checks then never see the value.
        if PERCENT_VALUE.search(body) and not any(c.endswith("_percent_string") for c in near):
            near.append("percent_sign")
        if SINGLE_QUOTED_KEY.search(body):
            near.append("single_quotes")
        if PYTHON_LITERAL.search(body):
            near.append("python_literal")
        if TRAILING_COMMA.search(body) and "{" in body:
            near.append("trailing_comma")
    out["near_miss"] = near
    usable = out["parsed"] is not None          # every field valid, or a partial turn-2 object
    complete = usable and not failed
    if stop == "refusal":
        out["status"], out["parsed"] = "refusal", None
        reasons.insert(0, "stop reason refusal")
        if complete:
            out["flags"].append("refusal_with_valid_object")
    elif stop == "cut":
        if usable:
            out["status"] = "ok" if complete else "partial"
            out["flags"].append("cut_after_complete_object")
        else:
            out["status"] = "cut"
            reasons.insert(0, "stopped at the output cap")
    else:
        out["status"] = ("ok" if complete else "partial") if usable else "missing"
        if stop == "other":
            out["flags"].append("unusual_stop_reason")
    out["failed_fields"] = [k for k in REQUIRED[kind] if out["parsed"] is None or k not in out["parsed"]]
    out["reason"] = "; ".join(reasons) if reasons and out["status"] != "ok" else None
    return out
