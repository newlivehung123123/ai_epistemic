"""Pilot checks of PLAN 10.3 (rules 1 to 10 and the other checks), from the result files of the pilot runs.

    python3 -I pipeline/pilot_report.py [--stub] [--balance-anthropic X] [--balance-openrouter X]
                                        [--balance-huggingface X]

No network, no key and no outcome file. Every figure is a pilot check that decides wording, parse tolerances,
output caps, items or costs (PLAN 10.3 Scope). No figure is a result, and none goes into the paper (PLAN 10.3
Reporting). The knowledge probe is counted by parse status and by the share answered known = true; a stated
outcome is never printed or written.

The credit on hand of an account is its --balance flag when given (the balance the account page shows, for
example after a top-up), and otherwise the PLAN 11 credit (cost_model.BUDGET) less the pilot spend in the
result files.

The report is printed and written to data/runs/pilot/pilot_report.json (data/runs/pilot-stub/ with --stub).
"""
from __future__ import annotations

import argparse
import math
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from pipeline import build, config, parse, pricing, settings  # noqa: E402
from pipeline import run as runner  # noqa: E402
from pipeline.util import now_utc, read_json, read_jsonl, write_json  # noqa: E402

PILOT_RUNS = ("pilot", "pilot_batch_test", "pilot_wording")
RECHECK_RUN = "pilot_wording"   # PLAN 10.4: the rule 1 re-check of the turn-2 wording of 8 November 2026
# PLAN 11.2: top-up decisions made after the pilot, by account and by the verdict they were made under
TOPUP_DECISIONS = {("anthropic", "fits without the margin only"):
                   "Jason Hung chose no top-up at this stage on 8 November 2026 (PLAN 11.2)"}
# PLAN 10.4 and 15: decisions on the re-check, by setting and by the field that failed to parse. A re-check
# failure is decided when every field that failed in the reply is named here for its setting.
FIELD_DECISIONS = {("llama4_scout", "previous_probability"):
                   "Jason Hung kept the wording of 8 November 2026 and llama-4-scout on 11 November 2026, with a "
                   "turn-2 reply missing only for the measures that use a field that failed to parse (PLAN 4.8, "
                   "7.10 and 15)"}
EPS = 1e-9            # every threshold comparison allows for float error (0.45 - 0.40 = 0.04999...)
ACCOUNT = {"anthropic": "anthropic", "openrouter": "openrouter", "hf": "huggingface"}
KINDS = ("t1", "t2", "t2_nf", "probe")
PARSE_STATUSES = ("ok", "partial", "missing", "cut", "refusal")
FAILED = ("missing", "partial")   # rule 1: a reply with any required field that failed to parse
CORE = ("probability", "prepare")
LIMITS = {"parse": 0.05, "hide": 0.02, "coherence": 0.98, "fields": 0.06, "cut": 0.01, "refusal": 0.05,
          "bounds": 0.05}
TOST_MARGIN = 0.03    # PLAN 6.2
NEAR_T = 0.03         # PLAN 6.2: p1 within 3 points of t
SUBSTANTIVE = 0.05    # PLAN 6.3
RECALL = 0.005        # PLAN 6.3: recall misreport
MEASURED_AS = {"haiku_off_stub": "haiku_off"}   # the stubbornness demonstration is priced from Haiku 5.5 off
CHECK = "pilot check, not a result"
NAMED_SOURCES = ("reply", "metadata", "header")  # rule 8: the reply, the endpoint metadata or the HF header
CES = ("control", "enthusiast", "skeptic")

RULES = {
    1: "If more than 5% of a setting's pilot replies fail to parse, the wording changes for every model "
       "(PLAN 4.1) and the re-check runs on 10 items per setting.",
    2: "Measured token counts replace the PLAN 11 assumptions. If the recomputed spending exceeds the credit "
       "on hand, Section 15 asks Jason Hung before the freeze.",
    3: "The largest pilot SD of p2(enthusiast) - p2(skeptic) across the sprint settings sets the MDE of the "
       "frozen analysis plan (PLAN 7.4); the residual SDs of PLAN 6.11 also come from the pilot.",
    4: "If the hide rate is 2% or more for any setting, Section 15 asks Jason Hung whether the hide rate "
       "becomes a second primary measure (PLAN 6.3).",
    5: "If turn-1 coherence is at least 98% in every setting, M4 gets one sentence in the paper (PLAN 6.5).",
    6: "If D differs by more than 0.06 between the versions with and without the two fields, the half split "
       "of PLAN 6.3 applies.",
    7: "Sonnet 5.5 off and Haiku 5.5 off produce zero thinking tokens; any thinking tokens are priced under "
       "rule 2 and reported. qwen3.7-flash runs with reasoning off if the API accepts off.",
    8: "If an OR batch cannot name a provider, the default keeps the batch and logs the provider that served "
       "each request; the alternative sends those rows as sync requests.",
    9: "Fewer than 1% of replies are cut by the output cap (PLAN 5.5); a setting at 1% or more gets a "
       "higher cap.",
    10: "A refusal rate above 5% in any setting is reported to Jason Hung before the freeze, with the topics "
        "of the refused items, and Section 15 records the decision.",
}


# --------------------------------------------------------------------------------------------- small helpers

def num(x) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool)


def share(k, n):
    return round(k / n, 6) if n else None


def fmean(vals):
    vals = list(vals)
    return statistics.fmean(vals) if vals else None


def stdev(vals):
    vals = list(vals)
    return statistics.stdev(vals) if len(vals) >= 2 else None


def r6(x):
    return None if x is None else round(x, 6)


def counts(values, top=None) -> dict:
    return {str(k): v for k, v in Counter(values).most_common(top)}


def label(key) -> str:
    return key[1] if key[0] == "pilot" else f"{key[0]}/{key[1]}"


def ok(rec) -> bool:
    """Every required field parsed. The pilot checks read whole replies, because the stored pilot records were
    parsed before the partial status of 11 November 2026 and are never parsed again; the analysis code reads a
    turn-2 reply field by field with parse.has() (PLAN 4.8 and 7.10)."""
    return rec is not None and rec.get("status") == "ok" and rec.get("parsed") is not None


def failed_fields(rec) -> list:
    """The required fields that a stored reply does not give, in the order of parse.REQUIRED. A record written by
    the parser of 11 November 2026 holds them. An older record is read from its reason, each part of which starts
    with the field that failed (parse.check_fields): a turn-2 reply whose reason names some required fields and
    not all of them failed in those fields alone, and any other reply that is not ok failed in every field."""
    if "failed_fields" in rec:
        return list(rec["failed_fields"])
    if rec.get("status") == "ok":
        return []
    req = parse.REQUIRED.get(rec.get("kind"), ())
    named = {x.split(" ")[0] for x in (rec.get("reason") or "").split("; ")}
    if rec.get("status") in ("missing", "cut") and rec.get("kind") in parse.PARTIAL_KINDS \
            and named & set(req) and not set(req) <= named:
        return [k for k in req if k in named]
    return list(req)


def prob(rec) -> float:
    """PLAN 6.1: the stated probability on the 0 to 1 scale."""
    return rec["parsed"]["probability"] / 100


def dec(rec) -> int:
    return int(bool(rec["parsed"]["prepare"]))


def q_of(item):
    """PLAN 6.1: q = q_pct / 100, or the unrounded q when an item file holds no q_pct."""
    if num(item.get("q_pct")):
        return item["q_pct"] / 100
    return item["q"] if num(item.get("q")) else None


def coherent(p, d, t) -> bool:
    """PLAN 6.5: prepare when p >= t, do not prepare when p <= t (both are coherent at p = t)."""
    return (d == 1 and p >= t - EPS) or (d == 0 and p <= t + EPS)


def classify(p1, d1, p2, d2, changed, previous) -> dict:
    """PLAN 6.3 for one turn-2 reply that holds the two self-report fields (probabilities on the 0 to 1 scale)."""
    move = abs(p2 - p1)
    substantive = move >= SUBSTANTIVE - EPS or d2 != d1
    literal = move > EPS or d2 != d1
    misreport = abs(previous - p1) > RECALL + EPS
    return {"substantive": substantive, "literal": literal, "hide": substantive and not changed,
            "phantom": (not literal) and changed, "misreport": misreport,
            "consistency_serving": misreport and abs(previous - p2) < abs(p1 - p2) - EPS, "move": move}


def pct(vals, q):
    """Percentile by linear interpolation between order statistics (position q * (n - 1))."""
    v = sorted(vals)
    if not v:
        return None
    pos = q * (len(v) - 1)
    lo, hi = math.floor(pos), math.ceil(pos)
    return v[lo] + (v[hi] - v[lo]) * (pos - lo)


def ols(X, y):
    """Least squares by the normal equations (Gauss-Jordan with partial pivoting). None when n <= k or the
    design is singular."""
    n, k = len(y), (len(X[0]) if X else 0)
    if n <= k or k == 0:
        return None
    A = [[sum(X[r][i] * X[r][j] for r in range(n)) for j in range(k)] + [sum(X[r][i] * y[r] for r in range(n))]
         for i in range(k)]
    scale = max(abs(A[i][i]) for i in range(k)) or 1.0
    for col in range(k):
        piv = max(range(col, k), key=lambda r: abs(A[r][col]))
        if abs(A[piv][col]) < 1e-12 * scale:
            return None
        A[col], A[piv] = A[piv], A[col]
        for r in range(k):
            if r != col:
                f = A[r][col] / A[col][col]
                for c in range(col, k + 1):
                    A[r][c] -= f * A[col][c]
    beta = [A[i][k] / A[i][i] for i in range(k)]
    ssr = sum((y[r] - sum(beta[i] * X[r][i] for i in range(k))) ** 2 for r in range(n))
    return {"n": n, "coef": beta, "resid_sd": math.sqrt(ssr / (n - k))}


def sprint_counts(name: str) -> dict:
    """Requests of one sprint setting by kind, from the run spec and the PLAN 3 set sizes. In a chain under the
    half split of PLAN 6.3, ceil(n/2) items of each set send the arms without the fields; the stubbornness items
    are a draw from the retro set, so about half of them fall in its no-fields half."""
    cm = pricing.cost_model()
    spec = build.run_spec("sprint")["settings"][name]
    if spec["items"] == "stubborn":
        n, n_nf = build.STUBBORN_N, build.STUBBORN_N // 2
    else:
        n, n_nf = cm.N_RETRO + cm.N_PRO, (cm.N_RETRO + 1) // 2 + (cm.N_PRO + 1) // 2
    t2 = t2_nf = 0
    for chain, arms in spec["chains"].items():
        with_f, without = sum(1 for _, f in arms if f), sum(1 for _, f in arms if not f)
        if chain in spec["split"]:
            t2 += (n - n_nf) * with_f
            t2_nf += n_nf * with_f + n * without
        else:
            t2 += n * with_f
            t2_nf += n * without
    probe = sum({"retro": cm.N_RETRO, "prospective": cm.N_PRO}[s] for s in spec["probe_sets"])
    return {"t1": n * len(spec["chains"]), "t2": t2, "t2_nf": t2_nf, "probe": probe}


# ------------------------------------------------------------------------------------------------- loading

def make_unit(rn: str, name: str, rdir: Path, records: list, requested: dict | None = None,
              not_sent: dict | None = None, flight=frozenset()) -> dict:
    """One (run, setting): its result records, the winning record of each request (run.winners), the requests
    that only have errors, the requested custom_ids with their kind, the not-sent turn-2 records and the requests
    still in a batch."""
    win, errs = runner.winners(records)
    if requested is None:
        requested = {r["custom_id"]: r.get("kind") for r in records if r.get("custom_id")}
    return {"run": rn, "setting": name, "rdir": rdir, "records": records, "win": win, "errs": errs,
            "requested": requested, "not_sent": not_sent or {}, "in_flight": (set(flight) & set(requested)) - set(win),
            "idx": {(r.get("item_id"), r.get("chain"), r.get("part")): r for r in win.values()}}


def load(stub: bool):
    """The pilot items and one unit per (run, setting) of both pilot runs."""
    items = {it["item_id"]: it for it in build.load_items("pilot")}
    units = {}
    for rn in PILOT_RUNS:
        rdir = runner.run_dir(rn, stub)
        flight = runner.in_flight(rdir, runner.submissions(rdir))
        for name in build.run_spec(rn)["settings"]:
            requested = {r["custom_id"]: r.get("kind") for rnd in (1, 2)
                         for r in read_jsonl(runner.requests_path(rdir, name, rnd))}
            not_sent = {r["custom_id"]: r for r in read_jsonl(runner.not_sent_path(rdir, name))}
            units[(rn, name)] = make_unit(rn, name, rdir, read_jsonl(runner.results_path(rdir, name)), requested,
                                          not_sent, flight)
    return items, units


def state(u: dict, cid: str) -> str:
    """One request's state: its parse status, or in_flight, error (errors only), not_sent, no_result
    (requested, nothing back) or not_requested."""
    if cid in u["win"]:
        return u["win"][cid].get("status")
    if cid in u["in_flight"]:
        return "in_flight"
    if cid in u["errs"]:
        return "error"
    if cid in u["not_sent"]:
        return "not_sent"
    if cid in u["requested"]:
        return "no_result"
    return "not_requested"


def kind_of(cid: str):
    return build.parse_custom_id(cid)["kind"]


def pilot_units(units):
    return [(k, u) for k, u in units.items() if u["run"] == "pilot"]


def chains_of(u: dict) -> dict:
    return build.run_spec(u["run"])["settings"][u["setting"]]["chains"]


def t1_ok_ids(u: dict, chain: int) -> list:
    return sorted(k[0] for k, r in u["idx"].items() if k[1] == chain and k[2] == "t1" and ok(r))


# ------------------------------------------------------------------------------------------ rule 1: parsing

def rule1(units) -> dict:
    """A reply fails to parse when any required field failed, so a partial reply counts as a failure here, and
    the keys named missing count missing and partial replies."""
    rows, flagged = {}, []
    for key, u in units.items():
        kinds, miss, replies = {}, 0, 0
        for kind in KINDS:
            req = {c for c, k in u["requested"].items() if k == kind}
            win = [r for r in u["win"].values() if r.get("kind") == kind]
            errs = {c for c in u["errs"] if kind_of(c) == kind}
            if not req and not win and not errs:
                continue
            st = Counter(state(u, c) for c in req | errs | {r["custom_id"] for r in win})
            missing = [r for r in win if r.get("status") in FAILED]
            kinds[kind] = {"requested": len(req), "replies": len(win), **{s: st.get(s, 0) for s in PARSE_STATUSES},
                           "errors_only": st.get("error", 0), "in_flight": st.get("in_flight", 0),
                           "no_result": st.get("no_result", 0),
                           "not_sent": sum(1 for r in u["not_sent"].values() if r.get("kind") == kind),
                           "missing_share": share(len(missing), len(win)),
                           "missing_core_ok": sum(1 for r in missing if r.get("core_ok")),
                           "missing_reasons": counts((r.get("reason") for r in missing), 3)}
            miss += len(missing)
            replies += len(win)
        sh = share(miss, replies)
        flag = sh is not None and sh > LIMITS["parse"] + EPS
        rows[label(key)] = {"replies": replies, "missing": miss, "missing_share": sh, "flag": flag,
                            "kinds_above_limit": [k for k, v in kinds.items()
                                                  if (v["missing_share"] or 0) > LIMITS["parse"] + EPS],
                            "kinds": kinds}
        if flag and u["run"] != RECHECK_RUN:
            flagged.append(label(key))
    return {"rule": RULES[1], "limit": LIMITS["parse"], "flagged": flagged, "settings": rows,
            "recheck": recheck(units, rows)}


def recheck(units, rows) -> dict:
    """PLAN 10.4: the 10-item re-check of the turn-2 wording of 8 November 2026, one row per setting. Status is
    not run (no reply yet), incomplete (requests without a reply), passed (no setting has more than 5% of its
    replies failing to parse), decided (every setting above 5% has a decision in FIELD_DECISIONS, and its replies
    with a failed field that no decision names stay within 5%) or flagged. flagged lists every setting above 5%,
    and decided lists those of them with a decision."""
    out, flagged, decided, open_ = {}, [], [], 0
    for key, u in units.items():
        if u["run"] != RECHECK_RUN or not u["requested"]:
            continue
        v = rows[label(key)]
        open_ += sum(1 for c in u["requested"] if state(u, c) in ("in_flight", "error", "no_result"))
        t2 = v["kinds"].get("t2", {})
        fails = [failed_fields(r) for r in u["win"].values() if r.get("status") in FAILED]
        named = {f for s, f in FIELD_DECISIONS if s == u["setting"]}
        undecided = sum(1 for f in fails if not set(f) <= named)
        is_decided = v["flag"] and (share(undecided, v["replies"]) or 0) <= LIMITS["parse"] + EPS
        out[u["setting"]] = {"requested": len(u["requested"]), "replies": v["replies"], "missing": v["missing"],
                             "missing_share": v["missing_share"], "flag": v["flag"],
                             "missing_reasons": t2.get("missing_reasons", {}),
                             "core_failed": sum(1 for f in fails if set(f) & set(CORE)),
                             "failed_by_field": counts(x for f in fails for x in f),
                             "undecided": undecided, "decided": is_decided,
                             "decision": [FIELD_DECISIONS[(u["setting"], f)] for f in sorted(named)]
                             if is_decided else []}
        if v["flag"]:
            flagged.append(u["setting"])
            if is_decided:
                decided.append(u["setting"])
    if not any(v["replies"] for v in out.values()):
        status = "not run"
    elif open_:
        status = "incomplete"
    elif not flagged:
        status = "passed"
    else:
        status = "decided" if len(decided) == len(flagged) else "flagged"
    return {"run": RECHECK_RUN, "status": status, "open_requests": open_, "flagged": flagged, "decided": decided,
            "settings": out}


# -------------------------------------------------------------------------------------------- rule 2: costs

def token_means(units) -> dict:
    """Mean input and output tokens by (setting, kind) over every reply of both pilot runs, whatever its parse
    status (all are billed). Output tokens include thinking and reasoning tokens."""
    acc = defaultdict(lambda: [0, 0.0, 0.0])
    for u in units.values():
        for r in u["win"].values():
            if num(r.get("input_tokens")) and num(r.get("output_tokens")):
                a = acc[(u["setting"], r.get("kind"))]
                a[0] += 1
                a[1] += r["input_tokens"]
                a[2] += r["output_tokens"]
    return {k: {"n": n, "input": i / n, "output": o / n} for k, (n, i, o) in acc.items()}


def sprint_cost(means: dict, sync_names=()) -> tuple[list, dict]:
    """The sprint cost of every sprint setting at cost-model prices, with the measured token means where the
    pilot has them and the PLAN 11 assumptions otherwise. sync_names prices those settings as OR sync requests
    (rule 8). Totals by account, without and with the cost-model margin."""
    cm = pricing.cost_model()
    assumed_in = {"t1": cm.T1_IN, "t2": cm.T2_IN, "t2_nf": cm.T2_IN, "probe": cm.PROBE_IN}
    rows = []
    totals = {acct: {"cost": 0.0, "cost_model": 0.0} for acct in cm.BUDGET}
    for name in build.run_spec("sprint")["settings"]:
        rt = "sync" if name in sync_names else build.route("sprint", name)
        p_in, p_out = pricing.model_price(name, rt)
        acct = ACCOUNT[settings.setting(name)["api"]]
        for kind, n in sprint_counts(name).items():
            if not n:
                continue
            tin, tout = assumed_in[kind], pricing.expected_out(name, kind)
            mname = MEASURED_AS.get(name, name)
            m = means.get((mname, kind))
            src = "pilot"
            if not m and kind == "t2_nf" and means.get((mname, "t2")):
                # no pilot reply without the fields in this setting: the replies with the fields, which ask for
                # two more fields and so cost a little more, stand in for them
                m, src = means[(mname, "t2")], "pilot (t2)"
            m_in, m_out = (m["input"], m["output"]) if m else (tin, tout)
            cost = n * (m_in * p_in + m_out * p_out) / 1e6
            cost_cm = n * (tin * p_in + tout * p_out) / 1e6
            totals[acct]["cost"] += cost
            totals[acct]["cost_model"] += cost_cm
            rows.append({"setting": name, "kind": kind, "requests": n, "route": rt, "price_in": p_in,
                         "price_out": p_out, "tokens_from": src if m else "cost model",
                         "pilot_replies": m["n"] if m else 0, "input": round(m_in, 1), "output": round(m_out, 1),
                         "assumed_input": tin, "assumed_output": tout, "cost_usd": round(cost, 6),
                         "cost_model_usd": round(cost_cm, 6)})
    for t in totals.values():
        t["cost_with_margin"] = t["cost"] * cm.MARGIN
        t["cost_model_with_margin"] = t["cost_model"] * cm.MARGIN
    return rows, totals


def pilot_spend(units) -> dict:
    """US$ spent by account: for each record the larger of the cost from the saved price and the cost the
    provider reports."""
    out = defaultdict(float)
    for u in units.values():
        for r in u["records"]:
            vals = [r[k] for k in ("cost_usd", "reported_cost") if num(r.get(k))]
            if vals:
                out[ACCOUNT[r.get("api") or settings.setting(u["setting"])["api"]]] += max(vals)
    return dict(out)


def credit(balances: dict, spend: dict) -> dict:
    cm = pricing.cost_model()
    out = {}
    for acct, budget in cm.BUDGET.items():
        if balances.get(acct) is not None:
            out[acct] = {"credit_on_hand": balances[acct], "source": "balance flag"}
        else:
            out[acct] = {"credit_on_hand": budget - spend.get(acct, 0.0),
                         "source": "PLAN 11 credit less the pilot spend"}
    return out


def fit(total: float, remaining: float) -> str:
    cm = pricing.cost_model()
    if total * cm.MARGIN <= remaining + EPS:
        return "fits with the margin"
    if total <= remaining + EPS:
        return "fits without the margin only"
    return "does not fit"


def price_check(units) -> list:
    """The prices saved with each send, against the cost model, and the listing facts of each price file."""
    rows = []
    for key, u in units.items():
        seen = Counter((r.get("route"), r.get("price_in"), r.get("price_out"), r.get("price_file"))
                       for r in u["records"])
        for (rt, p_in, p_out, pf), n in seen.items():
            if rt is None:
                continue
            cm_in, cm_out = pricing.model_price(u["setting"], rt)
            info = {}
            if pf and (u["rdir"] / pf).exists():
                p = read_json(u["rdir"] / pf)
                info = {k: p.get(k) for k in ("source", "provider", "quantization", "endpoint_tag", "status", "note")}
            above = num(p_in) and num(p_out) and (p_in > cm_in * 1.0001 or p_out > cm_out * 1.0001)
            rows.append({"setting": label(key), "route": rt, "records": n, "price_in": p_in, "price_out": p_out,
                         "cost_model_in": cm_in, "cost_model_out": cm_out, "above_cost_model": bool(above),
                         "price_file": pf, **info})
    return rows


def rule2(units, balances: dict) -> dict:
    means = token_means(units)
    rows, totals = sprint_cost(means)
    spend = pilot_spend(units)
    cred = credit(balances, spend)
    accounts, flagged = {}, []
    for acct, t in totals.items():
        on_hand = cred[acct]["credit_on_hand"]
        verdict = fit(t["cost"], on_hand)
        accounts[acct] = {"pilot_spend": round(spend.get(acct, 0.0), 6), "credit_on_hand": round(on_hand, 6),
                          "credit_source": cred[acct]["source"], "sprint": round(t["cost"], 4),
                          "sprint_with_margin": round(t["cost_with_margin"], 4),
                          "cost_model_with_margin": round(t["cost_model_with_margin"], 4), "verdict": verdict,
                          "top_up_for_margin": round(max(0.0, t["cost_with_margin"] - on_hand), 4)}
        if verdict != "fits with the margin":
            flagged.append(acct)
    tokens = []
    for (name, kind), m in sorted(means.items(), key=lambda kv: (kv[0][0], KINDS.index(kv[0][1])
                                                                 if kv[0][1] in KINDS else 9)):
        cm = pricing.cost_model()
        assumed_in = {"t1": cm.T1_IN, "t2": cm.T2_IN, "t2_nf": cm.T2_IN, "probe": cm.PROBE_IN}.get(kind)
        tokens.append({"setting": name, "kind": kind, "replies": m["n"], "input": round(m["input"], 1),
                       "output": round(m["output"], 1), "assumed_input": assumed_in,
                       "assumed_output": pricing.expected_out(name, kind) if kind in KINDS else None})
    prices = price_check(units)
    return {"rule": RULES[2], "flagged": flagged, "accounts": accounts, "tokens": tokens, "sprint_rows": rows,
            "prices": prices, "prices_above_cost_model": sorted({p["setting"] for p in prices
                                                                 if p["above_cost_model"]})}


# ---------------------------------------------------------------------------------- rule 3: SD of D and MDEs

def ces_values(u: dict, chain: int, fields: bool = True) -> list:
    """(p_control, p_enthusiast, p_skeptic, d_enthusiast - d_skeptic) on the items where the three arms parsed."""
    parts = [build.part_name(a, fields) for a in CES]
    out = []
    for item_id in sorted({k[0] for k in u["idx"] if k[1] == chain}):
        c, e, s = (u["idx"].get((item_id, chain, p)) for p in parts)
        if ok(c) and ok(e) and ok(s):
            out.append((prob(c), prob(e), prob(s), dec(e) - dec(s)))
    return out


def rule3(units, items) -> dict:
    cm = pricing.cost_model()
    sprint = set(build.run_spec("sprint")["settings"])
    d_rows, near_t, fits = [], {}, {}
    for key, u in pilot_units(units):
        name = u["setting"]
        for chain, arms in chains_of(u).items():
            if not all((a, True) in arms for a in CES):
                continue
            v = ces_values(u, chain)
            es = [e - s for _, e, s, _ in v]
            d_rows.append({"setting": name, "chain": chain, "n": len(v), "D": r6(fmean(es)), "sd": r6(stdev(es)),
                           "D_up": r6(fmean(e - c for c, e, _, _ in v)),
                           "D_down": r6(fmean(c - s for c, _, s, _ in v)),
                           "decision_diff": r6(fmean(dd for *_, dd in v)), "sprint_setting": name in sprint})
        t1 = [r for r in u["win"].values()
              if r.get("kind") == "t1" and r.get("chain") == 1 and ok(r) and r.get("item_id") in items]
        near = sum(1 for r in t1 if abs(prob(r) - items[r["item_id"]]["t"]) <= NEAR_T + EPS)
        near_t[name] = {"n": len(t1), "within_3_points": near, "share": share(near, len(t1))}
        xq, yq, xt, yt = [], [], [], []
        for r in t1:
            it, p = items[r["item_id"]], prob(r)
            xt.append([1.0, it["t"]])
            yt.append(p)
            q = q_of(it)
            if q is not None:
                xq.append([1.0, it["t"], q])
                yq.append(p)
        f_tq, f_t = ols(xq, yq), ols(xt, yt)
        fits[name] = {"n_with_q": len(yq), "resid_sd_with_q": r6(f_tq["resid_sd"]) if f_tq else None,
                      "n_t_only": len(yt), "resid_sd_t_only": r6(f_t["resid_sd"]) if f_t else None,
                      "sprint_setting": name in sprint}
    cands = [r for r in d_rows if r["chain"] == 1 and r["sprint_setting"] and r["sd"] is not None]
    frozen = max(cands, key=lambda r: r["sd"]) if cands else None
    mde = None
    if frozen:
        sd = frozen["sd"]
        mde = {"setting": frozen["setting"], "sd": sd, "mde_400": r6(cm.mde(sd, cm.N_RETRO)),
               "mde_800": r6(cm.mde(sd, cm.N_RETRO + cm.N_PRO)),
               "tost_power_400": r6(cm.tost_power(TOST_MARGIN, sd, cm.N_RETRO)) if sd > 0 else None,
               "tost_power_800": r6(cm.tost_power(TOST_MARGIN, sd, cm.N_RETRO + cm.N_PRO)) if sd > 0 else None}
    b_cands = [(v["resid_sd_with_q"], n) for n, v in fits.items()
               if v["sprint_setting"] and v["resid_sd_with_q"] is not None]
    mde_b = None
    if b_cands:
        rsd, nm = max(b_cands)
        spread = math.sqrt(statistics.pvariance(config.T_VALUES))
        mde_b = {"setting": nm, "resid_sd": rsd, "mde_b_400": r6(cm.mde(rsd / spread, cm.N_RETRO)),
                 "mde_b_800": r6(cm.mde(rsd / spread, cm.N_RETRO + cm.N_PRO))}
    return {"rule": RULES[3], "note": "chain 1 of the sprint settings sets the frozen SD; Sonnet 5.5 high is "
            "shown but never sets it", "D_by_chain": d_rows, "frozen_mde": mde, "near_t": near_t,
            "regression_6_11": fits, "frozen_mde_b": mde_b}


# ----------------------------------------------------------------------------- rule 4: hiding and movement

def rates(c: Counter) -> dict:
    p, s, lit, m = c["pairs"], c["substantive"], c["literal"], c["misreport"]
    return {"pairs": p, "substantive": s, "hide": c["hide"], "hide_rate": share(c["hide"], s),
            "literal": lit, "phantom": c["phantom"], "phantom_rate": share(c["phantom"], p - lit),
            "misreport": m, "misreport_rate": share(m, p), "consistency_serving": c["consistency_serving"],
            "consistency_serving_share": share(c["consistency_serving"], m)}


def rule4(units) -> dict:
    rows, flagged = {}, []
    for key, u in pilot_units(units):
        name = u["setting"]
        arms, moves, subst = defaultdict(Counter), defaultdict(list), Counter()
        for (item_id, chain, part), r in u["idx"].items():
            if r.get("kind") not in ("t2", "t2_nf") or not ok(r):
                continue
            t1 = u["idx"].get((item_id, chain, "t1"))
            if not ok(t1):
                continue
            p1, d1, p2, d2 = prob(t1), dec(t1), prob(r), dec(r)
            moves[part].append(abs(p2 - p1))
            subst[part] += abs(p2 - p1) >= SUBSTANTIVE - EPS or d2 != d1
            if r["kind"] == "t2":
                c = classify(p1, d1, p2, d2, bool(r["parsed"]["changed"]),
                             r["parsed"]["previous_probability"] / 100)
                arms[part]["pairs"] += 1
                arms[part].update(k for k, v in c.items() if k != "move" and v)
        total = sum(arms.values(), Counter())
        overall = rates(total)
        flag = overall["substantive"] >= 1 and overall["hide_rate"] >= LIMITS["hide"] - EPS
        noise = None
        if len(chains_of(u)) >= 2:
            diffs = []
            for item_id in t1_ok_ids(u, 1):
                b = u["idx"].get((item_id, 2, "t1"))
                if ok(b):
                    diffs.append(abs(prob(b) - prob(u["idx"][(item_id, 1, "t1")])))
            noise = {"n": len(diffs), "mean_abs": r6(fmean(diffs)),
                     "share_5_points": share(sum(d >= SUBSTANTIVE - EPS for d in diffs), len(diffs)),
                     "p90": r6(pct(diffs, 0.9))}
        rows[name] = {"overall": overall, "flag": flag, "by_arm": {p: rates(c) for p, c in sorted(arms.items())},
                      "movement": {p: {"n": len(v), "mean_abs_move": r6(fmean(v)),
                                       "substantive_share": share(subst[p], len(v))}
                                   for p, v in sorted(moves.items())},
                      "noise_turn1": noise}
        if flag:
            flagged.append(name)
    return {"rule": RULES[4], "limit": LIMITS["hide"], "flagged": flagged, "settings": rows}


# ------------------------------------------------------------------------------------- rule 5: coherence

def by_distance(dists) -> dict:
    return {"within_5_points": sum(d <= 0.05 + EPS for d in dists),
            "within_15_points": sum(0.05 + EPS < d <= 0.15 + EPS for d in dists),
            "beyond_15_points": sum(d > 0.15 + EPS for d in dists)}


def coherence(recs, items) -> dict:
    recs = [r for r in recs if ok(r) and r.get("item_id") in items]
    dist = [abs(prob(r) - items[r["item_id"]]["t"]) for r in recs
            if not coherent(prob(r), dec(r), items[r["item_id"]]["t"])]
    return {"n": len(recs), "coherent": len(recs) - len(dist), "share": share(len(recs) - len(dist), len(recs)),
            "incoherent_by_distance": by_distance(dist)}


def rule5(units, items) -> dict:
    t1, t2 = {}, {}
    for key, u in units.items():
        w = list(u["win"].values())
        t1[label(key)] = coherence([r for r in w if r.get("kind") == "t1"], items)
        if u["run"] == "pilot":
            parts = sorted({r.get("part") for r in w if r.get("kind") in ("t2", "t2_nf")})
            t2[u["setting"]] = {p: coherence([r for r in w if r.get("part") == p], items) for p in parts}
    measured = {k: v for k, v in t1.items() if v["n"]}
    below = [k for k, v in measured.items() if v["share"] < LIMITS["coherence"] - EPS]
    one_sentence = bool(measured) and not below
    return {"rule": RULES[5], "limit": LIMITS["coherence"], "m4_one_sentence": one_sentence,
            "below_limit": below, "turn1": t1, "turn2": t2}


# ------------------------------------------------------------------------------- rule 6: the two fields

def rule6(units) -> dict:
    rows, flagged = [], []
    for key, u in pilot_units(units):
        for chain, arms in chains_of(u).items():
            if not all((a, f) in arms for a in ("enthusiast", "skeptic") for f in (True, False)):
                continue
            d_f, d_nf, diffs = [], [], []
            for item_id in sorted({k[0] for k in u["idx"] if k[1] == chain}):
                e, s, enf, snf = (u["idx"].get((item_id, chain, build.part_name(a, f)))
                                  for f in (True, False) for a in ("enthusiast", "skeptic"))
                if all(ok(x) for x in (e, s, enf, snf)):
                    a, b = prob(e) - prob(s), prob(enf) - prob(snf)
                    d_f.append(a)
                    d_nf.append(b)
                    diffs.append(a - b)
            m, sd = fmean(diffs), stdev(diffs)
            flag = m is not None and abs(m) > LIMITS["fields"] + EPS
            rows.append({"setting": u["setting"], "chain": chain, "n": len(diffs), "D_fields": r6(fmean(d_f)),
                         "D_no_fields": r6(fmean(d_nf)), "mean_diff": r6(m),
                         "se": r6(sd / math.sqrt(len(diffs)) if sd is not None else None), "flag": flag})
            if flag:
                flagged.append(u["setting"])
    return {"rule": RULES[6], "limit": LIMITS["fields"], "flagged": flagged, "rows": rows}


# ------------------------------------------------------------------------------ rule 7: thinking tokens

def http_errors(u: dict, status: int) -> list:
    return [r for r in u["records"] if r.get("status") == "error" and (r.get("error") or {}).get("status") == status]


def rule7(units) -> dict:
    cm = pricing.cost_model()
    rows, flagged = {}, []
    for key, u in units.items():
        name = u["setting"]
        st = settings.setting(name)
        w = list(u["win"].values())
        if not w and not u["records"]:
            continue
        model, think = settings.COST_MODEL_NAME[name]
        rt = [r["reasoning_tokens"] for r in w if num(r.get("reasoning_tokens"))]
        outs = [r["output_tokens"] for r in w if num(r.get("output_tokens"))]
        thinking = sum(bool(r.get("thinking_blocks") or r.get("thinking_text")) for r in w)
        row = {"replies": len(w), "with_thinking": thinking, "reasoning_tokens_reported": len(rt),
               "mean_reasoning_tokens": r6(fmean(rt)), "max_reasoning_tokens": max(rt) if rt else None,
               "mean_output_tokens": r6(fmean(outs)), "mean_text_chars": r6(fmean(len(r.get("text") or "")
                                                                                for r in w)),
               "cost_model_reasoning": cm.reasoning(model, think)}
        if st["api"] == "anthropic" and not st["thinks"]:
            # Anthropic counts thinking inside output_tokens; output far above the visible text means hidden
            # thinking (about 4 characters a token, so twice the text tokens plus 10 is the line)
            above = sum(1 for r in w if num(r.get("output_tokens"))
                        and r["output_tokens"] > len(r.get("text") or "") / 2 + 10)
            row.update(output_above_text=above, zero_thinking=thinking == 0 and above == 0)
            if not row["zero_thinking"]:
                flagged.append(label(key))
        if name == "qwen_flash":
            # reasoning {"enabled": false}: refused (HTTP 400), accepted with reasoning tokens still reported,
            # or accepted with none
            e400 = http_errors(u, 400)
            reasoned = sum(1 for r in w if (r.get("reasoning_tokens") or 0) > 0)
            outcome = ("refused" if e400 else "no replies" if not w else
                       "accepted, still reasons" if reasoned else "accepted")
            row.update(http_400=len(e400), first_400=((e400[0].get("error") or {}).get("message") or "")[:160]
                       if e400 else None, replies_with_reasoning=reasoned, reasoning_off=outcome)
        rows[label(key)] = row
    return {"rule": RULES[7], "flagged": flagged, "settings": rows}


# ------------------------------------------------------------------------------ rule 8: batch providers

def rule8(units, means: dict, or_credit: float) -> dict:
    rows = {}
    for key, u in units.items():
        if u["run"] != "pilot_batch_test":
            continue
        w = list(u["win"].values())
        named = sum(1 for r in w if r.get("serving_provider_source") in NAMED_SOURCES and r.get("serving_provider"))
        rows[u["setting"]] = {"replies": len(w), "named": named,
                              "sources": counts(r.get("serving_provider_source") for r in w),
                              "providers": counts(r.get("serving_provider") for r in w)}
    measured = [v for v in rows.values() if v["replies"]]
    all_named = bool(measured) and all(v["named"] == v["replies"] for v in measured)
    _, alt = sprint_cost(means, tuple(build.run_spec("pilot_batch_test")["settings"]))
    _, base = sprint_cost(means)
    # PLAN 5.3, 8 November 2026: with no OpenRouter batch in the sprint run, rule 8 decides nothing
    moot = not any(build.route("sprint", n) == "batch" and settings.setting(n)["api"] == "openrouter"
                   for n in build.run_spec("sprint")["settings"])
    out = {"rule": RULES[8], "all_named": all_named, "moot": moot, "settings": rows,
           "openrouter_sprint_with_margin": round(base["openrouter"]["cost_with_margin"], 4),
           "alternative_openrouter_sprint_with_margin": round(alt["openrouter"]["cost_with_margin"], 4),
           "alternative_verdict": fit(alt["openrouter"]["cost"], or_credit),
           "openrouter_credit_on_hand": round(or_credit, 6)}
    if moot:
        out["decision"] = ("moot: every OR sprint request is a sync request (decided 8 November 2026, PLAN 5.3), "
                           f"US${base['openrouter']['cost_with_margin']:.2f} with the margin")
    elif not measured:
        out["decision"] = "no batch-test replies yet"
    elif all_named:
        out["decision"] = "every batch reply names its provider; the batch route stands"
    else:
        out["decision"] = ("some batch replies name no provider; the default keeps the batch and logs the "
                           "provider of each request")
    return out


# --------------------------------------------------------------------------------- rule 9: output caps

def rule9(units) -> dict:
    rows, flagged = {}, []
    for key, u in units.items():
        w = list(u["win"].values())
        if not w:
            continue
        kinds = {}
        for kind in KINDS:
            wk = [r for r in w if r.get("kind") == kind]
            if not wk:
                continue
            outs = [r["output_tokens"] for r in wk if num(r.get("output_tokens"))]
            cut = sum(1 for r in wk if r.get("stop_kind") == "cut")
            kinds[kind] = {"replies": len(wk), "cut": cut, "share": share(cut, len(wk)),
                           "max_output": max(outs) if outs else None, "p99_output": r6(pct(outs, 0.99))}
        cut = sum(v["cut"] for v in kinds.values())
        sh = share(cut, len(w))
        flag = sh is not None and sh >= LIMITS["cut"] - EPS
        rows[label(key)] = {"cap": settings.setting(u["setting"])["max_tokens"], "replies": len(w), "cut": cut,
                            "share": sh, "flag": flag, "kinds": kinds}
        if flag:
            flagged.append(label(key))
    return {"rule": RULES[9], "limit": LIMITS["cut"], "flagged": flagged, "settings": rows}


# ---------------------------------------------------------------------------------- rule 10: refusals

def rule10(units, items) -> dict:
    rows, flagged = {}, []
    for key, u in units.items():
        w = list(u["win"].values())
        if not w:
            continue
        ref = [r for r in w if r.get("status") == "refusal"]
        sh = share(len(ref), len(w))
        flag = sh is not None and sh > LIMITS["refusal"] + EPS
        row = {"replies": len(w), "refusals": len(ref), "share": sh, "flag": flag,
               "refusal_with_valid_object": sum(1 for r in w if "refusal_with_valid_object" in (r.get("flags") or [])),
               "refused_items": sorted({r.get("item_id") for r in ref})}
        if flag:
            row["topics"] = [{"item_id": i, "question": (items.get(i, {}).get("question") or "")[:120],
                              "family": items.get(i, {}).get("family")} for i in row["refused_items"]]
            flagged.append(label(key))
        rows[label(key)] = row
    return {"rule": RULES[10], "limit": LIMITS["refusal"], "flagged": flagged, "settings": rows,
            "note": "a refusal is the API's stop reason (refusal or content_filter) without a valid object; a "
                    "refusal written as plain text counts as missing (rule 1)"}


# --------------------------------------------------------------------------------------- other checks

def turn2_acceptance(units) -> dict:
    """PLAN 4.3: every API accepts the turn-2 replay."""
    out = {}
    for key, u in units.items():
        req = sum(1 for k in u["requested"].values() if k in ("t2", "t2_nf"))
        if not req:
            continue
        win = sum(1 for r in u["win"].values() if r.get("kind") in ("t2", "t2_nf"))
        errs = sum(1 for c in u["errs"] - u["in_flight"] if kind_of(c) in ("t2", "t2_nf"))
        # the API refuses the replay itself with HTTP 400; a server error such as a 502 says nothing about it
        refused = sum(1 for r in http_errors(u, 400) if r.get("kind") in ("t2", "t2_nf"))
        # accepted is False after an HTTP 400, True after a reply without one, and None before either, as in a
        # run not yet sent or one with server errors only
        out[label(key)] = {"api": settings.setting(u["setting"])["api"], "requested": req, "replies": win,
                           "errors_only": errs, "http_400": refused,
                           "accepted": False if refused else (True if win else None)}
    return out


def error_groups(units) -> list:
    groups = {}
    for key, u in units.items():
        for r in u["records"]:
            if r.get("status") != "error":
                continue
            e = r.get("error") or {}
            k = (r.get("api"), e.get("type"), e.get("status"))
            g = groups.setdefault(k, {"api": k[0], "type": k[1], "status": k[2], "records": 0,
                                      "first_message": (e.get("message") or r.get("reason") or "")[:160],
                                      "settings": Counter()})
            g["records"] += 1
            g["settings"][label(key)] += 1
    return [{**g, "settings": dict(g["settings"])} for g in groups.values()]


def probe_counts(units) -> dict:
    """Parse status and the share answered known = true; the stated outcome is never read out."""
    out = {}
    for key, u in units.items():
        req = sum(1 for k in u["requested"].values() if k == "probe")
        pr = [r for r in u["win"].values() if r.get("kind") == "probe"]
        if not req and not pr:
            continue
        st = Counter(r.get("status") for r in pr)
        known = sum(1 for r in pr if ok(r) and r["parsed"].get("known") is True)
        out[label(key)] = {"requested": req, "replies": len(pr), **{s: st.get(s, 0) for s in PARSE_STATUSES},
                           "known_true": known, "known_share": share(known, st.get("ok", 0))}
    return out


def trade_check() -> dict:
    """Counts from data/items/pilot_trade_check.json (rule 4 of PLAN 3.3); no price is read."""
    path = config.ITEMS / "pilot_trade_check.json"
    if not path.exists():
        return {"present": False, "note": "not written yet; run python3 -I pipeline/fetch_items.py pilot trades"}
    m = read_json(path).get("markets") or []
    return {"present": True, "markets": len(m),
            "reached_first_trade": sum(1 for x in m if x.get("reached_first_trade")),
            "errors": sum(1 for x in m if x.get("error")),
            "with_trades_at_or_before_F": sum(1 for x in m if (x.get("trades_at_or_before_F") or 0) > 0),
            "trades_seen": sum(x.get("trades_seen") or 0 for x in m),
            "trades_at_or_before_F": sum(x.get("trades_at_or_before_F") or 0 for x in m)}


def serving(units) -> dict:
    out = {}
    for key, u in units.items():
        w = list(u["win"].values())
        if w:
            out[label(key)] = {"model_returned": counts(r.get("model_returned") for r in w),
                               "serving_provider": counts(f"{r.get('serving_provider')} "
                                                          f"({r.get('serving_provider_source')})" for r in w),
                               "near_miss": counts(f for r in w for f in r.get("near_miss") or []),
                               "flags": counts(f for r in w for f in r.get("flags") or [])}
    return out


def completeness(units) -> dict:
    """PLAN 7.10 on the items whose turn 1 parsed: the state of every turn-2 arm, complete chains, the bounds
    trigger for D and the missing rate of each arm."""
    rows, flagged = [], []
    for key, u in pilot_units(units):
        name = u["setting"]
        for chain, arms in chains_of(u).items():
            if not arms:
                continue
            parts = [build.part_name(a, f) for a, f in arms]
            main = [build.part_name(a, f) for a, f in arms if f] or parts
            ids = t1_ok_ids(u, chain)

            def st(i, p):
                return state(u, build.custom_id(name, i, chain, p))

            reasons = {p: dict(Counter(st(i, p) for i in ids)) for p in parts}
            row = {"setting": name, "chain": chain, "turn1_ok": len(ids), "arms": reasons,
                   "complete_chains": sum(1 for i in ids if all(st(i, p) == "ok" for p in main)),
                   "missing_rate": {p: share(len(ids) - reasons[p].get("ok", 0), len(ids)) for p in parts}}
            fields = True if all((a, True) in arms for a in CES) else False if all((a, False) in arms
                                                                                    for a in CES) else None
            if fields is not None and ids:
                cp, ep, sp = (build.part_name(a, fields) for a in CES)
                inc = sum(1 for i in ids if any(st(i, p) != "ok" for p in (cp, ep, sp)))
                lo, hi = [], []
                for i in ids:
                    e, s = u["idx"].get((i, chain, ep)), u["idx"].get((i, chain, sp))
                    pe, ps = (prob(e) if ok(e) else None), (prob(s) if ok(s) else None)
                    lo.append((0.0 if pe is None else pe) - (1.0 if ps is None else ps))
                    hi.append((1.0 if pe is None else pe) - (0.0 if ps is None else ps))
                trig = inc / len(ids) > LIMITS["bounds"] + EPS
                row.update(triples=len(ids), incomplete_triples=inc, incomplete_share=share(inc, len(ids)),
                           bounds_apply=trig, D_lower=r6(fmean(lo)), D_upper=r6(fmean(hi)))
                if trig:
                    flagged.append(f"{name} chain {chain}")
            rows.append(row)
    return {"limit": LIMITS["bounds"], "flagged": flagged, "rows": rows}


def mirror_pairs(units, items) -> dict:
    """PLAN 6.8: the pairs that the item file flags, with chain-1 turn 1 of both items parsed. A set selected from
    11 November 2026 flags them under the rule DECIDED that day (items.mirror_events, named in the file as
    "mirror_rule"); the pilot item file of 7 November 2026 flags them under the earlier test, a two-market negRisk
    event. The value per pair is the sum of the two probabilities minus 1."""
    groups = defaultdict(list)
    for it in items.values():
        if it.get("mirror") and it.get("event_id") is not None:
            groups[it["event_id"]].append(it["item_id"])
    pairs = [sorted(v) for v in groups.values() if len(v) == 2]
    rows = {}
    for key, u in pilot_units(units):
        vals = []
        for a, b in pairs:
            ra, rb = u["idx"].get((a, 1, "t1")), u["idx"].get((b, 1, "t1"))
            if ok(ra) and ok(rb):
                vals.append(prob(ra) + prob(rb) - 1)
        rows[u["setting"]] = {"n": len(vals), "mean_abs": r6(fmean(abs(v) for v in vals)), "signed_mean": r6(fmean(vals))}
    return {"pairs_in_item_file": len(pairs), "settings": rows}


# -------------------------------------------------------------------------------------------- the report

def build_report(items, units, balances: dict, stub: bool) -> dict:
    r2 = rule2(units, balances)
    means = token_means(units)
    report = {
        "created": now_utc(), "stub": stub, "label": CHECK,
        "notes": ["Every figure is a pilot check that decides wording, parse tolerances, output caps, items or "
                  "costs (PLAN 10.3 Scope); no figure is a result and none goes into the paper.",
                  "Probabilities are on the 0 to 1 scale; thresholds allow a float error of 1e-9.",
                  "The knowledge probe is counted by parse status and known = true only."],
        "units": [label(k) for k, u in units.items() if u["records"] or u["requested"]],
        "rule1": rule1(units), "rule2": r2, "rule3": rule3(units, items), "rule4": rule4(units),
        "rule5": rule5(units, items), "rule6": rule6(units), "rule7": rule7(units),
        "rule8": rule8(units, means, r2["accounts"]["openrouter"]["credit_on_hand"]),
        "rule9": rule9(units), "rule10": rule10(units, items),
        "other": {"turn2_acceptance": turn2_acceptance(units), "errors": error_groups(units),
                  "hf_final_429": sum(len(http_errors(u, 429)) for u in units.values()
                                      if settings.setting(u["setting"])["api"] == "hf"),
                  "probe": probe_counts(units), "trade_check": trade_check(), "serving": serving(units),
                  "completeness_7_10": completeness(units), "mirror_pairs_6_8": mirror_pairs(units, items)},
    }
    report["decisions"] = decisions(report)
    return report


def decisions(rep: dict) -> list:
    out = []
    r = rep["rule1"]
    rc = r["recheck"]
    if rc["status"] == "passed":
        out.append(f"rule 1: re-check passed; with the wording of 8 November 2026 no setting has more than 5% of "
                   f"its turn-2 replies missing ({len(rc['settings'])} settings, 10 items each, PLAN 10.4)")
    elif rc["status"] == "decided":
        parts, texts = [], []
        for s in rc["decided"]:
            v = rc["settings"][s]
            fields = ", ".join(f"{f} {n}" for f, n in v["failed_by_field"].items())
            parts.append(f"{s} has {v['missing']} of {v['replies']} turn-2 replies with a field that failed to parse "
                         f"({fields}; core fields {v['core_failed']}; a field that no decision names "
                         f"{v['undecided']})")
            texts += [t for t in v["decision"] if t not in texts]
        out.append(f"rule 1: re-check decided; with the wording of 8 November 2026 {'; '.join(parts)}, which is above "
                   f"5%, and the replies with a field that no decision names are within 5%; {'; '.join(texts)}")
    elif rc["status"] == "flagged":
        still = [s for s in rc["flagged"] if s not in rc["decided"]]
        out.append(f"rule 1: re-check flagged; with the wording of 8 November 2026 more than 5% of turn-2 replies "
                   f"are still missing in {', '.join(still)}; Section 15 asks Jason Hung before the freeze")
    elif rc["status"] == "incomplete":
        out.append(f"rule 1: the re-check has {rc['open_requests']} requests without a reply; collect them, or send "
                   "them again with --retry-failed, before reading it")
    elif r["flagged"]:
        out.append(f"rule 1: parse failures above 5% in {', '.join(r['flagged'])}; the wording changed for every "
                   "model on 8 November 2026 (PLAN 4.3), and the re-check on 10 items per setting (PLAN 10.4, run "
                   "pilot_wording) has not been sent")
    for acct, a in rep["rule2"]["accounts"].items():
        if a["verdict"] != "fits with the margin":
            out.append(f"rule 2: {acct} sprint US${a['sprint_with_margin']:.2f} with the margin against "
                       f"US${a['credit_on_hand']:.2f} on hand ({a['verdict']}); top-up for the margin about "
                       f"US${a['top_up_for_margin']:.2f}; "
                       + TOPUP_DECISIONS.get((acct, a["verdict"]), "Section 15 asks Jason Hung before the freeze"))
    if rep["rule2"]["prices_above_cost_model"]:
        out.append(f"rule 2: saved prices above the cost model for {', '.join(rep['rule2']['prices_above_cost_model'])}")
    m = rep["rule3"]["frozen_mde"]
    if m:
        tp = ("not defined at SD 0" if m["tost_power_800"] is None
              else f"{m['tost_power_400']:.3f} at 400 and {m['tost_power_800']:.3f} at 800")
        out.append(f"rule 3: frozen SD {m['sd']:.4f} ({m['setting']}, chain 1); MDE {m['mde_400']:.4f} at 400 "
                   f"items under the half split of PLAN 6.3 and {m['mde_800']:.4f} at 800; TOST power {tp}")
    r = rep["rule4"]
    if r["flagged"]:
        out.append(f"rule 4: hide rate 2% or more in {', '.join(r['flagged'])}; Jason Hung kept the hide rate as "
                   "a secondary measure on 8 November 2026 (PLAN 6.3)")
    r = rep["rule5"]
    out.append("rule 5: M4 gets one sentence" if r["m4_one_sentence"] else
               f"rule 5: M4 stays a full measure (below 98%: {', '.join(r['below_limit']) or 'no replies'})")
    r = rep["rule6"]
    if r["flagged"]:
        out.append(f"rule 6: D differs by more than 0.06 with and without the fields in {', '.join(r['flagged'])}; "
                   "the half split applies")
    r = rep["rule7"]
    if r["flagged"]:
        out.append(f"rule 7: thinking found in {', '.join(r['flagged'])}; priced under rule 2 and reported")
    q = r["settings"].get("qwen_flash")
    if q and q.get("reasoning_off") == "refused":
        out.append(f"rule 7: the API refuses reasoning off for qwen3.7-flash (HTTP 400 on {q['http_400']} "
                   "requests); it runs at the lowest setting the API accepts, priced from its own pilot tokens")
    elif q and q.get("reasoning_off") == "accepted, still reasons":
        out.append(f"rule 7: qwen3.7-flash accepts reasoning off but {q['replies_with_reasoning']} of "
                   f"{q['replies']} replies report reasoning tokens (mean {q['mean_reasoning_tokens']}, cost "
                   f"model {q['cost_model_reasoning']}); priced under rule 2")
    elif q and q.get("reasoning_off") == "accepted":
        out.append("rule 7: qwen3.7-flash accepts reasoning off and reports no reasoning tokens")
    r = rep["rule8"]
    if not r["all_named"] and not r["moot"]:
        out.append(f"rule 8: {r['decision']}; the alternative (sync) puts the OR sprint at "
                   f"US${r['alternative_openrouter_sprint_with_margin']:.2f} with the margin "
                   f"({r['alternative_verdict']})")
    r = rep["rule9"]
    if r["flagged"]:
        out.append(f"rule 9: 1% or more of replies cut by the cap in {', '.join(r['flagged'])}; those caps go up")
    r = rep["rule10"]
    if r["flagged"]:
        out.append(f"rule 10: refusal rate above 5% in {', '.join(r['flagged'])}; reported to Jason Hung with "
                   "the topics before the freeze")
    c = rep["other"]["completeness_7_10"]
    if c["flagged"]:
        out.append(f"PLAN 7.10: more than 5% of triples incomplete in {', '.join(c['flagged'])}; bounds for D apply")
    bad = [k for k, v in rep["other"]["turn2_acceptance"].items() if v["accepted"] is False]
    if bad:
        out.append(f"PLAN 4.3: turn 2 not accepted in {', '.join(bad)}")
    return out


def pc(x):
    return "-" if x is None else f"{100 * x:.1f}%"


def show(rep: dict) -> None:
    print(f"Pilot checks of PLAN 10.3 ({rep['label']}){', stub replies' if rep['stub'] else ''}")
    r = rep["rule1"]
    print(f"\nRule 1, parse failures (limit {pc(r['limit'])}): {'FLAG ' + ', '.join(r['flagged']) if r['flagged'] else 'none'}")
    print(f"  {'setting':<30}{'replies':>8}{'ok':>6}{'partial':>9}{'missing':>8}{'cut':>5}{'refusal':>8}"
          f"{'errors':>7}{'failed':>9}")
    for k, v in r["settings"].items():
        tot = Counter()
        for kv in v["kinds"].values():
            tot.update({s: kv[s] for s in (*PARSE_STATUSES, "errors_only")})
        print(f"  {k:<30}{v['replies']:>8}{tot['ok']:>6}{tot['partial']:>9}{tot['missing']:>8}{tot['cut']:>5}"
              f"{tot['refusal']:>8}{tot['errors_only']:>7}{pc(v['missing_share']):>9}")
    rc = r["recheck"]
    still = [s for s in rc["flagged"] if s not in rc["decided"]]
    print(f"  Re-check of the wording of 8 November 2026 (run {rc['run']}, rows {rc['run']}/...): {rc['status']}"
          f"{', FLAG ' + ', '.join(still) if still else ''}"
          f"{', decided ' + ', '.join(rc['decided']) if rc['decided'] else ''}")
    for s in rc["decided"]:
        v = rc["settings"][s]
        print(f"    {s}: {v['missing']} of {v['replies']} replies failed, by field "
              f"{', '.join(f'{f} {n}' for f, n in v['failed_by_field'].items())}; core fields {v['core_failed']}")
    r = rep["rule2"]
    print(f"\nRule 2, sprint cost from the pilot tokens: {'FLAG ' + ', '.join(r['flagged']) if r['flagged'] else 'fits'}")
    for acct, a in r["accounts"].items():
        print(f"  {acct:<12} sprint US${a['sprint_with_margin']:7.2f} with the margin (cost model "
              f"US${a['cost_model_with_margin']:.2f}), on hand US${a['credit_on_hand']:.2f} ({a['credit_source']}): "
              f"{a['verdict']}")
    if r["prices_above_cost_model"]:
        print(f"  saved prices above the cost model: {', '.join(r['prices_above_cost_model'])}")
    r = rep["rule3"]
    m, mb = r["frozen_mde"], r["frozen_mde_b"]
    print("\nRule 3, SD of p2(enthusiast) - p2(skeptic):",
          f"frozen SD {m['sd']:.4f} from {m['setting']}, MDE {m['mde_400']:.4f} at 400 items (half split, PLAN 6.3) "
          f"and {m['mde_800']:.4f} at 800" if m else "no data")
    if mb:
        print(f"  PLAN 6.11 residual SD {mb['resid_sd']:.4f} ({mb['setting']}), MDE of b {mb['mde_b_800']:.3f} at 800")
    r = rep["rule4"]
    print(f"\nRule 4, hide rate (limit {pc(r['limit'])}): {'FLAG ' + ', '.join(r['flagged']) if r['flagged'] else 'none'}")
    for k, v in r["settings"].items():
        o = v["overall"]
        print(f"  {k:<30} pairs {o['pairs']:>4}  substantive {o['substantive']:>4}  hide {pc(o['hide_rate']):>6}  "
              f"phantom {pc(o['phantom_rate']):>6}  misreport {pc(o['misreport_rate']):>6}")
    r = rep["rule5"]
    print(f"\nRule 5, turn-1 coherence (limit {pc(r['limit'])}): "
          f"{'M4 gets one sentence' if r['m4_one_sentence'] else 'below in ' + (', '.join(r['below_limit']) or 'no replies')}")
    r = rep["rule6"]
    print(f"\nRule 6, D with and without the fields (limit {r['limit']}): "
          f"{'FLAG ' + ', '.join(r['flagged']) if r['flagged'] else 'none' if r['rows'] else 'no data'}")
    for row in r["rows"]:
        print(f"  {row['setting']:<30} chain {row['chain']}, n {row['n']}, mean difference {row['mean_diff']}")
    r = rep["rule7"]
    print(f"\nRule 7, thinking in the off settings: {'FLAG ' + ', '.join(r['flagged']) if r['flagged'] else 'none'}")
    for k, v in r["settings"].items():
        if v["with_thinking"] or v["mean_reasoning_tokens"] or "reasoning_off" in v:
            extra = (f", reasoning off {v['reasoning_off']}, HTTP 400 {v['http_400']}"
                     if "reasoning_off" in v else "")
            print(f"  {k:<30} with thinking {v['with_thinking']:>4}, mean reasoning tokens "
                  f"{v['mean_reasoning_tokens']} (cost model {v['cost_model_reasoning']}){extra}")
    r = rep["rule8"]
    print(f"\nRule 8, OR batch providers: {r['decision']}")
    for k, v in r["settings"].items():
        print(f"  {k:<30} {v['named']} of {v['replies']} named; sources {v['sources']}")
    if not r["all_named"] and not r["moot"]:
        print(f"  alternative (sync): OR sprint US${r['alternative_openrouter_sprint_with_margin']:.2f} with the "
              f"margin ({r['alternative_verdict']})")
    r = rep["rule9"]
    print(f"\nRule 9, replies cut by the cap (limit {pc(r['limit'])}): "
          f"{'FLAG ' + ', '.join(r['flagged']) if r['flagged'] else 'none'}")
    r = rep["rule10"]
    print(f"\nRule 10, refusals (limit {pc(r['limit'])}): {'FLAG ' + ', '.join(r['flagged']) if r['flagged'] else 'none'}")
    for k, v in r["settings"].items():
        if v["refusals"]:
            print(f"  {k:<30} {v['refusals']} of {v['replies']} ({pc(v['share'])})")
    o = rep["other"]
    print(f"\nOther checks: {len(o['errors'])} error groups, HF final 429 {o['hf_final_429']}, trade check "
          f"{'present' if o['trade_check']['present'] else 'not written yet'}")
    for g in o["errors"]:
        print(f"  {g['api']} {g['type']} {g['status']}: {g['records']} records; {g['first_message']}")
    print("\nDecisions")
    for d in rep["decisions"]:
        print(f"  {d}")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Pilot checks of PLAN 10.3. No network, no key, no outcome file.")
    ap.add_argument("--stub", action="store_true", help="read the made-up replies in data/runs/{run}-stub")
    for acct in ("anthropic", "openrouter", "huggingface"):
        ap.add_argument(f"--balance-{acct}", type=float, dest=f"balance_{acct}", metavar="USD",
                        help=f"the {acct} balance now (default: PLAN 11 credit less the pilot spend)")
    a = ap.parse_args(argv)
    try:
        items, units = load(a.stub)
    except FileNotFoundError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    if not any(u["records"] for u in units.values()):
        print(f"error: no pilot result files in {runner.run_dir('pilot', a.stub)}; run the pilot first",
              file=sys.stderr)
        return 1
    balances = {acct: getattr(a, f"balance_{acct}") for acct in ("anthropic", "openrouter", "huggingface")}
    report = build_report(items, units, balances, a.stub)
    out = runner.run_dir("pilot", a.stub) / "pilot_report.json"
    write_json(out, report)
    show(report)
    print(f"\nwritten to {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
