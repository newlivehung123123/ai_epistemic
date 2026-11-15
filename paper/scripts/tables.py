"""Tables of the paper, written to paper/tables/*.tex.

Reads only the aggregate files data/runs/sprint/analysis_describe.json and data/runs/sprint/analysis_score.json and
the frozen module pipeline/settings.py (labels, model IDs and request parameters). Opens nothing in data/outcomes
and writes no value of a single item.

  python3 -I paper/scripts/tables.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from pipeline import settings as st  # noqa: E402

RUN = ROOT / "data" / "runs" / "sprint"
D = json.loads((RUN / "analysis_describe.json").read_text(encoding="utf-8"))
S = json.loads((RUN / "analysis_score.json").read_text(encoding="utf-8"))
OUT = ROOT / "paper" / "tables"

SET = ["haiku_off", "haiku_medium", "sonnet_off", "gpt6luna", "gemini_flash_lite", "mistral_small",
       "deepseek_flash", "qwen_flash", "glm_flash", "gpt_oss_120b", "llama4_scout"]
LABEL = {s: D["settings"][s]["label"] for s in SET}
ARMS4 = ("control", "double_check", "enthusiast", "skeptic")
POLICIES = ("repeat", "copy", "follow_by_0.01", "follow_by_0.015", "follow_by_0.05", "follow_by_0.1")
POLICY_NAME = {"repeat": "Repeat", "copy": "Copy", "follow_by_0.01": "Follow 0.01", "follow_by_0.015": "Follow 0.015",
               "follow_by_0.05": "Follow 0.05", "follow_by_0.1": "Follow 0.10", "ideal": "Ideal"}
FAIL_CODE = {"H2": "H2", "S above 0": "S", "market-arm Brier gain above 0": "gain"}
TOPICS = ("us_elections", "other_elections", "ai_companies", "other")

# PLAN 5.2 and 5.3: the thinking or reasoning sent, and the developer's default
SENT = {"haiku_off": "Thinking disabled", "haiku_medium": "Not sent (adaptive)",
        "sonnet_off": "Between tools, no tools offered", "gpt6luna": "Effort none", "gemini_flash_lite": "Effort none",
        "mistral_small": "Effort none", "deepseek_flash": "Effort none", "qwen_flash": "Reasoning disabled",
        "glm_flash": "Effort low", "gpt_oss_120b": "Effort low", "llama4_scout": "Not sent"}
DEFAULT = {"haiku_off": "Adaptive, effort medium", "haiku_medium": "Adaptive, effort medium",
           "sonnet_off": "Adaptive, effort high", "gpt6luna": "On (medium)", "gemini_flash_lite": "On (minimal)",
           "mistral_small": "Off", "deepseek_flash": "On (high)", "qwen_flash": "On, no effort levels",
           "glm_flash": "Required (max)", "gpt_oss_120b": "Required (medium)", "llama4_scout": "No reasoning"}


def G(o, path):
    """Strict getter, so a wrong path raises KeyError."""
    for k in path.split("/"):
        o = o[k]
    return o


def d(s):
    return D["settings"][s]


def sc(s):
    return S["settings"][s]["retro"]


def val(x):
    return x["estimate"] if isinstance(x, dict) else x


def num(x, nd=3, lead=False):
    """No leading zero for quantities bounded by 1 (as in the model paper), a math minus sign."""
    x = val(x)
    if x is None:
        return "--"
    r = round(float(x), nd)
    if r == 0:
        r = 0.0
    s = f"{abs(r):.{nd}f}"
    if not lead and s.startswith("0."):
        s = s[1:]
    return f"$-{s}$" if r < 0 else s


def ci(o, nd=3, lead=False, key="ci95"):
    c = o.get(key) if isinstance(o, dict) else None
    if not c or c[0] is None:
        return "--"
    return f"[{num(c[0], nd, lead)}, {num(c[1], nd, lead)}]"


def ec(o, nd=3, lead=False, key="ci95"):
    return f"{num(o, nd, lead)} {ci(o, nd, lead, key)}"


def excl(o):
    c = o.get("ci95") if isinstance(o, dict) else None
    return bool(c and c[0] is not None and (c[0] > 0 or c[1] < 0))


def mark(o, nd=3, lead=False):
    """Point estimate, with a star when the 95 percent interval excludes 0."""
    return num(o, nd, lead) + ("$^{*}$" if excl(o) else "")


def pval(p):
    if p is None:
        return "--"
    return "$<$.001" if p < 0.001 else num(p, 3)


def rank(o):
    def r(x):
        return str(int(x)) if float(x).is_integer() else f"{x:.1f}"
    return f"{r(o['rank'])} [{r(o['rank_ci95'][0])}, {r(o['rank_ci95'][1])}]"


def tt(x):
    return "\\texttt{" + str(x).replace("_", "\\_") + "}"


def closing(cr):
    fails = [FAIL_CODE[f] for f in cr["fails"]]
    if cr.get("not_available"):
        print("  closing rule with conditions not available:", cr["not_available"])
    return "Passes" if not fails else "Fails " + ", ".join(fails)


def _split_outside_math(s):
    parts, cur, math = [], "", False
    for ch in s:
        if ch == "$":
            math = not math
        if ch == " " and not math:
            parts.append(cur); cur = ""
        else:
            cur += ch
    parts.append(cur)
    return [x for x in parts if x]


def stack_head(h, colspec):
    """Put a long header cell on two lines so that wide tables fit the page."""
    if "\\multicolumn" in h or "\\cmidrule" in h or "{" in colspec:
        return h
    aligns = [c for c in colspec if c in "lcr"]
    cells = h.split(" & ")
    if len(aligns) != len(cells):
        return h
    out = []
    for a, cell in zip(aligns, cells):
        words = _split_outside_math(cell)
        visible = len(cell.replace("$", ""))
        if len(words) < 2 or visible <= 9:
            out.append(cell)
            continue
        best = min(range(1, len(words)), key=lambda k: abs(len(" ".join(words[:k])) - len(" ".join(words[k:]))))
        top, bottom = " ".join(words[:best]), " ".join(words[best:])
        out.append(f"\\begin{{tabular}}[b]{{@{{}}{a}@{{}}}}{top}\\\\\\relax {bottom}\\end{{tabular}}")
    return " & ".join(out)


def write(name, head, rows, colspec, caption, label, wide=False, size="\\small", sep="3.5pt", place="t"):
    env = "table*" if wide else "table"
    if wide and place == "h":
        place = "t"
    out = [f"\\begin{{{env}}}[{place}]", "\\centering", size, f"\\setlength{{\\tabcolsep}}{{{sep}}}",
           "\\begin{adjustbox}{max width=\\linewidth}", f"\\begin{{tabular}}{{{colspec}}}", "\\toprule"]
    out += [stack_head(h, colspec) + " \\\\" for h in head]
    out.append("\\midrule")
    for r in rows:
        out.append(r if isinstance(r, str) else " & ".join(r) + " \\\\")
    out += ["\\bottomrule", "\\end{tabular}", "\\end{adjustbox}", f"\\caption{{{caption}}}", f"\\label{{{label}}}", f"\\end{{{env}}}", ""]
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"{name}.tex").write_text("\n".join(out), encoding="utf-8")
    print(f"wrote paper/tables/{name}.tex")


# ---------------------------------------------------------------- main text

def table_turn1():
    rows, short = [], []
    for s in SET:
        a = G(sc(s), "turn_1_accuracy")
        u = G(sc(s), "utility")
        if a["n"] != 359:
            short.append((LABEL[s], a["n"]))
        rows.append([LABEL[s], ec(a["brier"]), num(a["bss_base_rate"], 3, True), num(a["bss_market"], 2, True),
                     num(a["log_loss"], 3, True), num(a["auc"]), num(G(a, "corp/mcb")), num(G(a, "corp/dsc")),
                     num(G(u, "mean_u/model_d1"), 2, True), ec(G(u, "differences/model_d1_minus_own_p1"), 2, True)])
    m = G(S, "market_price_accuracy/retro")
    um = G(sc("haiku_off"), "utility/mean_u")
    rows.append("\\addlinespace")
    rows.append(["Market price at $F$", ec(m["brier"]), num(m["bss_base_rate"], 3, True), "--", num(m["log_loss"], 3, True),
                 num(m["auc"]), num(G(m, "corp/mcb")), num(G(m, "corp/dsc")), num(um["market"], 2, True), "--"])
    unc = val(G(sc("haiku_off"), "turn_1_accuracy/corp/unc"))
    print("  scored items below 359:", short)
    write("tab_turn1",
          ["Setting & Brier [CI] & BSS base & BSS market & Log loss & AUC & MCB & DSC & $U$ & $U-U_{\\mathrm{own}}$ [CI]"],
          rows, "lccccccccc",
          "Turn-1 forecasts on the 359 resolved retro questions. Brier is the mean squared error of the probability, "
          "where 0 is perfect and a constant 0.5 scores 0.25. BSS is the Brier skill score against the base rate of the "
          "outcomes and against the market price at the forecast date $F$. Log loss uses the natural logarithm with "
          "probabilities clipped to [0.01, 0.99]. MCB (miscalibration) and DSC (discrimination) come from the CORP "
          f"decomposition, Brier = MCB $-$ DSC + UNC, with UNC = {unc:.3f} for the 359 resolved retro questions. $U$ is the mean payoff "
          "in US dollars per question of the stated decision to prepare, and $U_{\\mathrm{own}}$ is the payoff of "
          "preparing whenever the model's own probability reaches the cost threshold. Brackets give 95 percent "
          "bootstrap intervals over events. Sonnet 5.5 off has 356 scored questions, deepseek-v4.1-flash and "
          "gpt-oss-120b have 358 and glm-5.3-flash has 355, because the other turn-1 replies of Sonnet 5.5 off, deepseek-v4.1-flash, gpt-oss-120b and glm-5.3-flash were not usable. "
          f"Preparing for every question loses {-val(um['always_prepare']):.2f} dollars per question, and an oracle that "
          f"prepares only for questions that resolve Yes earns {val(um['oracle']):.2f} dollars.",
          "tab:turn1", wide=True, size="\\footnotesize", sep="3pt")


def table_turn2():
    rows, nD = [], []
    for s in SET:
        t = G(d(s), "turn_2")
        Dw = G(t, "without_fields/pooled/D/D")
        hide = G(t, "with_fields/pooled/rates/hide/all_arms")
        nD.append(Dw["n"])
        rows.append([LABEL[s], ec(Dw), num(G(t, "with_fields/pooled/D/D")), f"{num(hide)} ({hide['n']})",
                     num(G(t, "with_fields/pooled/rates/phantom/all_arms")),
                     ec(G(t, "without_fields/pooled/weights/S"), 3, True),
                     ec(G(sc(s), "market_arm_brier_gain/without_fields")),
                     num(G(sc(s), "turn_2_costs/without_fields/caving/mean_accuracy_cost_of_enthusiast_and_skeptic"), 4)])
    print("  D without the fields, items per setting:", min(nD), "to", max(nD))
    write("tab_turn2",
          ["Setting & $D$ without fields [CI] & $D$ with fields & Hide (changes) & Phantom & $S$ [CI] & Gain [CI] & Concession cost"],
          rows, "lccccccc",
          "Turn-2 replies by setting. $D$ is the mean of $p_2$(enthusiast) $-$ $p_2$(sceptic) over items with usable "
          f"control, enthusiast and sceptic replies, on the half of the items sent without the self-report "
          f"fields ({min(nD)} to {max(nD)} items per setting, the retro and prospective sets pooled) and on the half sent with the fields. Hide is "
          "the share of substantive changes (a move of five points or more, or another decision, counted in parentheses) that the model reported "
          "as unchanged, and phantom is the share of unchanged "
          "answers reported as changed, on the half with the fields. $S=w_m-w_h$ is the weight on a market "
          "price minus the weight on the same number offered as the user's own estimate, on items where the number "
          "is at least 10 points from $p_1$. Gain is the Brier score of $p_1$ minus the Brier score after the market "
          "message, and concession cost is the mean Brier cost of the enthusiast and sceptic replies, on the resolved "
          "retro items without the fields. Brackets give 95 percent bootstrap intervals over events.",
          "tab:turn2", wide=True, size="\\footnotesize", sep="3pt")


def table_policies():
    h = d("haiku_off")
    r = sc("haiku_off")
    Dw = G(h, "turn_2/without_fields/pooled/D/D")
    rows = [["Model as tested", num(Dw), num(G(h, "turn_2/without_fields/pooled/weights/S"), 3, True),
             num(G(r, "market_arm_brier_gain/without_fields")), closing(G(r, "closing_rule"))], "\\addlinespace"]
    for p in POLICIES:
        rows.append([POLICY_NAME[p], num(G(h, f"policies/{p}/D")), num(G(h, f"policies/{p}/S"), 3, True),
                     num(G(r, f"policies/{p}/market_arm_brier_gain")), closing(G(r, f"policies/{p}/closing_rule"))])
    ide = G(r, "policies/ideal")
    rows.append(["Ideal", num(ide["D"]), num(ide["S"], 3, True), num(ide["market_arm_brier_gain"]),
                 closing(ide["closing_rule"])])
    rows.append("\\addlinespace")
    stb = D["stubbornness"]
    rows.append(["Never-change instruction", num(G(stb, "D/stubborn")), num(G(stb, "S/stubborn"), 3, True),
                 num(G(S, "stubbornness_brier_gain/retro/stubborn")),
                 closing(G(S, "settings/haiku_off_stub/retro/closing_rule"))])
    bounds = G(d("haiku_off_stub"), "turn_2/without_fields/pooled/D_bounds")
    print("  never-change bounds:", val(bounds["lower"]), val(bounds["upper"]), bounds["complete_triples"], bounds["items_with_turn_1"])
    print("  ideal w_star:", ide["w_star"])
    write("tab_policies", ["Policy & $D$ & $S$ & Gain & Closing rule"], rows, "lcccl",
          "Scripted reply policies applied to the turn-1 answers of Haiku 5.5 off, beside the replies of the model as "
          "tested and with the never-change instruction. Repeat returns $p_1$ in every arm. Copy returns the stated "
          "number in the market and user-estimate arms and $p_1$ elsewhere. Follow $k$ moves $p_1$ up by $k$ in the enthusiast arm "
          "and down by $k$ in the sceptic arm (clipped to [0, 1]) and returns $p_1$ elsewhere. Ideal moves $p_1$ toward "
          f"the market price by $w^*={val(ide['w_star']):.3f}$, the fixed weight with the lowest Brier score on the "
          f"{ide['market_arm_brier_gain']['n']} resolved retro items sent without the fields, in the market arm, and returns "
          "$p_1$ elsewhere. The weight is fitted on the same items as the gain, so the gain of Ideal is the best "
          "any fixed weight can reach on the 183 items. The closing rule needs H2 to hold "
          "(the 90 percent interval of $D$ inside $\\pm 0.03$), the 95 percent interval of $S$ to lie above 0 and the "
          "95 percent interval of the gain to lie above 0. The never-change row uses the 100 retro items sent with the "
          f"instruction. Only {bounds['complete_triples']} of the {bounds['items_with_turn_1']} items without the fields "
          f"have complete replies, so H2 is judged on bounds from ${val(bounds['lower']):.3f}$ to {val(bounds['upper']):.3f}.".replace("$-", "$-"),
          "tab:policies", size="\\small", sep="3pt")


# ---------------------------------------------------------------- appendix

def table_sets():
    ri, pi = D["items"]["retro"], D["items"]["prospective"]
    oc = G(S, "outcome_counts/retro")
    rows = [["Forecast date $F$", "8 October 2026", "12 November 2026"],
            ["Scheduled end dates", "15 October to 8 November", "19 November to 15 December"],
            ["Markets fetched (UTC)", "11 November, 14:30", "12 November, 17:58"],
            ["Items", str(ri["items"]), str(pi["items"])],
            ["Events", str(ri["events"]), str(pi["events"])],
            ["Families", str(ri["families"]), str(pi["families"])],
            ["Items without the self-report fields", str(ri["items_without_the_self_report_fields"]),
             str(pi["items_without_the_self_report_fields"])],
            ["Mirror pairs", str(ri["mirror_pairs"]), str(pi["mirror_pairs"])],
            ["Items resolved at scoring", f"{oc['statuses']['resolved']}", "Opens 16 December 2026"]]
    write("tab_sets", ["& Retro & Prospective"], rows, "lll",
          "The retro and prospective question sets. Each set holds binary Polymarket questions that were open at $F$, priced between "
          "0.05 and 0.95 at $F$ and scheduled to end in the stated window. One election day in one place is one family. Other "
          "events are grouped by 26 written rules, and an event that matches no rule is a family of one. The prospective "
          "events were grouped by hand on 13 November 2026. A mirror pair holds the two candidate markets of one election, "
          "with no other candidate market priced at $F$, whose prices at $F$ sum to at least 0.90, so that the probabilities of the two candidates should sum to nearly 1. The retro "
          f"outcomes were opened on 13 November 2026, and {oc['statuses']['unresolved']} retro items were still "
          "unresolved and are not scored.", "tab:sets", size="\\small", sep="4pt", wide=True)


def table_models():
    rows = []
    for s in SET:
        c = st.SETTINGS[s]
        rec = d(s)["recency"]
        if c["api"] == "anthropic":
            route = "Anthropic, batch"
        elif c["api"] == "openrouter":
            route = "OpenRouter, " + tt(c["sync_provider"])
        else:
            route = "Hugging Face, DeepInfra"
        mid = tt(c["model"]).replace("/", "/\\allowbreak{}").replace(":", ":\\allowbreak{}").replace("-", "-\\allowbreak{}")
        rows.append([LABEL[s], mid, SENT[s], DEFAULT[s], str(c["max_tokens"]), route,
                     rec["release_or_listing_date"], rec["stated_knowledge_cutoff"] or "Not stated"])
    write("tab_models", ["Setting & Model ID & Thinking or reasoning sent & Developer default & Cap & Route & Released & Stated cutoff"],
          rows, "P{0.10}P{0.21}P{0.13}P{0.12}rP{0.13}P{0.08}P{0.08}",
          "Settings as tested on 13 November 2026. The cap is the output limit in tokens, thinking or reasoning "
          "included. OpenRouter requests named one provider and did not allow routing to another provider, and Hugging Face requests named "
          "DeepInfra in the model ID. No request sent a temperature, a tool or a web search. Released gives the release "
          "date or the first listing date. Anthropic requests used SDK 0.85.0, and every reply logged the returned "
          "model ID and the request date.", "tab:models", wide=True, size="\\scriptsize", sep="2.5pt")


def table_replies():
    rows = []
    for s in SET:
        stt = G(d(s), "counts/states")
        t1, t2 = {}, {}
        for chain, kinds in stt.items():
            for kind, states in kinds.items():
                tgt = t1 if kind == "t1" else t2
                for k, n in states.items():
                    tgt[k] = tgt.get(k, 0) + n
        b = G(d(s), "turn_2/without_fields/pooled/D_bounds")
        extra = set(t1) | set(t2)
        extra -= {"ok", "cut", "missing", "partial", "not_sent"}
        if extra:
            print("  other states:", s, extra)
        rows.append([LABEL[s], f"{t1.get('ok', 0)} of {sum(t1.values())}", str(t1.get("cut", 0)), str(t1.get("missing", 0)),
                     f"{t2.get('ok', 0)} of {sum(t2.values())}", str(t2.get("partial", 0)), str(t2.get("not_sent", 0)),
                     str(t2.get("missing", 0) + t2.get("cut", 0)),
                     f"{b['complete_triples']} of {b['items_with_turn_1']}"])
    stb = G(d("haiku_off_stub"), "counts/states")
    t2s = {}
    for kinds in stb.values():
        for kind, states in kinds.items():
            if kind != "t1":
                for k, n in states.items():
                    t2s[k] = t2s.get(k, 0) + n
    print("  never-change turn-2 states:", t2s)
    write("tab_replies", ["& \\multicolumn{3}{c}{Turn 1} & \\multicolumn{4}{c}{Turn 2} & Complete",
                          "Setting & Usable & Cut & Missing & Usable & Partial & Not sent & Missing & triples"],
          rows, "lcccccccc",
          "Replies returned in the sprint run, across every chain and arm. A cut reply reached the output cap "
          "without a usable answer, and a missing reply held no usable JSON object or no valid probability. A partial "
          "turn-2 reply held a valid probability but at least one invalid self-report field, so the reply is usable "
          "for $D$ and the weights and missing for the self-report measures. The 148 partial replies of llama-4-scout "
          "all fall in the half with the fields. Not sent counts turn-2 requests not sent because the turn-1 reply of "
          "the chain was not usable. Complete triples counts items without the fields with usable control, enthusiast "
          "and sceptic replies, of the items with a usable turn-1 reply. No reply was a refusal.",
          "tab:replies", wide=True, size="\\footnotesize", sep="3pt")


def table_scores():
    rb = G(S, "between_settings/retro")
    rows = []
    for s in SET:
        a = G(sc(s), "turn_1_accuracy")
        rows.append([LABEL[s], str(a["n"]), rank(rb["ranking_brier"][s]), num(a["log_loss"], 3, True),
                     num(a["log_loss_clipped_to_0.001"], 3, True), num(a["accuracy_at_one_half"]), ec(a["auc"]),
                     ec(a["bss_base_rate"], 3, True), ec(G(sc(s), "utility/mean_u/model_d1"), 2, True),
                     rank(rb["ranking_mean_u"][s])])
    write("tab_scores", ["Setting & $n$ & Brier rank & Log loss & Log loss 0.001 & Accuracy & AUC [CI] & BSS base [CI] & $U$ [CI] & $U$ rank"],
          rows, "lrcccccccc",
          "Turn-1 scores on the resolved retro questions with ranks. Ranks run from 1 (best) and brackets after a rank "
          "give the 95 percent bootstrap interval of the rank over events. Log loss clips probabilities to [0.01, 0.99] and log "
          "loss 0.001 to [0.001, 0.999]. Accuracy counts a probability above 0.5 as a forecast of Yes. The ranks "
          "describe the resolved retro questions and do not identify a best model.", "tab:scores", wide=True,
          size="\\footnotesize", sep="3pt")


def table_topics():
    n0 = {k: G(sc("haiku_off"), f"topics/{k}/n") for k in TOPICS}
    rows = []
    for s in SET:
        tp = G(sc(s), "topics")
        rows.append([LABEL[s]] + [num(tp[k]["brier"]) for k in TOPICS] + [num(tp[k]["bss_market"], 2, True) for k in TOPICS])
    head = ("Setting & US elections & Other elections & AI companies & Other & US elections & Other elections & "
            "AI companies & Other")
    write("tab_topics", [head], rows, "lcccccccc",
          "Turn-1 Brier score (first four columns) and Brier skill score against the market price (last four columns) "
          f"by topic group, on the resolved retro questions. Haiku 5.5 off has {n0['us_elections']} questions on United "
          f"States elections, {n0['other_elections']} on other elections, {n0['ai_companies']} on AI companies and "
          f"{n0['other']} on other topics. Brier scores are compared only within a set.", "tab:topics", wide=True,
          size="\\footnotesize", sep="3pt")


def table_behaviour():
    rows = []
    for s in SET:
        t = d(s)["turn_1"]
        r, p = t["retro"], t["prospective"]
        rows.append([LABEL[s], num(r["mean_p1"]), num(p["mean_p1"]), num(r["share_prepare"]), num(p["share_prepare"]),
                     num(r["share_within_3_points_of_t"]), num(p["share_within_3_points_of_t"]),
                     num(G(r, "coherence/share_coherent")), num(G(p, "coherence/share_coherent")),
                     num(G(sc(s), "utility/mean_u/own_p1"), 2, True)])
    write("tab_behaviour", ["& \\multicolumn{2}{c}{Mean $p_1$} & \\multicolumn{2}{c}{Prepare} & \\multicolumn{2}{c}{Within 3 points of $t$} & \\multicolumn{2}{c}{Coherent} & $U_{\\mathrm{own}}$",
                            "Setting & Retro & Prosp. & Retro & Prosp. & Retro & Prosp. & Retro & Prosp. & Retro"],
          rows, "lccccccccc",
          "Turn-1 behaviour on all 400 retro and 220 prospective items. Prepare is the share of answers that say to "
          "prepare, and within three points of $t$ is the share of probabilities within 0.03 of the cost threshold. A "
          "decision is coherent when the model prepares exactly when the model's probability reaches the threshold. "
          "$U_{\\mathrm{own}}$ is the mean payoff in dollars of the coherent rule on the resolved retro questions.",
          "tab:behaviour", wide=True, size="\\footnotesize", sep="3pt")


def table_dinference():
    rows = []
    for s in SET:
        x = G(d(s), "turn_2/without_fields/pooled/D")
        Dd = x["D"]
        rows.append([LABEL[s], str(Dd["n"]), ec(Dd, 3, False, "ci90"), num(x["D_up"]), num(x["D_down"]), num(Dd["z"], 1, True),
                     pval(D["holm_h1"][s]["adjusted_p"]), pval(Dd["tost_p"]), num(x["sd_across_items"]), num(x["mde"]),
                     num(x["mde_at_strictest_holm_step"]), num(x["design_effect"], 2, True)])
    write("tab_dinference", ["Setting & $n$ & $D$ [90 CI] & $D_{\\mathrm{up}}$ & $D_{\\mathrm{down}}$ & $z$ & Holm $p$ & TOST $p$ & SD & MDE & MDE Holm & Design effect"],
          rows, "lrcccccccccc",
          "Inference on $D$ on the half without the fields, the retro and prospective sets pooled. Brackets give the 90 percent bootstrap "
          "interval used by the equivalence test. $D_{\\mathrm{up}}=p_2(\\mathrm{enthusiast})-p_2(\\mathrm{control})$ and "
          "$D_{\\mathrm{down}}=p_2(\\mathrm{control})-p_2(\\mathrm{sceptic})$. Holm $p$ is adjusted over the 11 settings "
          "for H1, and TOST $p$ tests $|D|<0.03$ for H2. SD is the standard deviation of the item differences. MDE is "
          "the minimum detectable effect at 80 percent power with the planning design effect of 1.3, at the 0.05 level "
          "and at the strictest Holm step. The design effect is the bootstrap variance of $D$ when events are resampled "
          "divided by the bootstrap variance of $D$ when items are resampled.", "tab:dinference", wide=True, size="\\footnotesize", sep="2.5pt")


def table_drobust():
    rows = []
    for s in SET:
        x = G(d(s), "turn_2/without_fields")
        sub = d(s)["retro_without_subsets"]
        rows.append([LABEL[s], ci(G(x, "pooled/D/D"), 3, False, "ci95_family"), num(G(x, "pooled/D/D_log_odds"), 3, True),
                     num(G(x, "pooled/D/D_complete_chains")), num(G(x, "pooled/D/decision_share_difference")),
                     num(G(x, "retro/D/D")), num(G(x, "prospective/D/D")),
                     num(G(sub, "without_brazil_family/D")), num(G(sub, "without_earlier_pull_events/D"))])
    write("tab_drobust", ["Setting & 95 CI by family & Log-odds & Complete chains & Decision share & Retro & Prospective & Without Brazil & Without earlier pull"],
          rows, "lcccccccc",
          "Robustness of $D$ on the half without the fields. The first column gives the 95 percent interval from "
          "resampling families in place of events. Log-odds computes $D$ on the log-odds scale with probabilities "
          "clipped to [0.01, 0.99]. Complete chains keeps items with usable replies in turn 1 and all six arms. "
          "Decision share is the share of enthusiast replies that say to prepare minus the share of sceptic replies "
          "that say to prepare. Without Brazil and Without earlier pull drop, from the retro set, the Brazilian election family and the events in the "
          "earlier pull of markets (Appendix~\\ref{app:exposure}).", "tab:drobust", wide=True, size="\\footnotesize", sep="3pt")


def table_strata():
    rows = []
    for s in SET:
        a = G(d(s), "strata")
        h = a["distance_of_p1_from_one_half"]["strata"]
        t = a["distance_of_p1_from_t"]["strata"]
        rd = a["redraw_agreement"]["strata"]
        rows.append([LABEL[s]] + [num(h[k]["D"]) for k in ("lower", "middle", "upper")]
                    + [num(t[k]["D"]) for k in ("lower", "middle", "upper")]
                    + [num(rd["redraw_within_5_points"]["D"]), num(rd["redraw_5_points_or_more"]["D"])])
    write("tab_strata", ["& \\multicolumn{3}{c}{Third of $|p_1-0.5|$} & \\multicolumn{3}{c}{Third of $|p_1-t|$} & \\multicolumn{2}{c}{Repeat-request gap}",
                         "Setting & Nearest & Middle & Farthest & Nearest & Middle & Farthest & Below 5 & 5 or more"],
          rows, "lcccccccc",
          "$D$ by stratum on the half without the fields. Thirds are cut at the terciles of each setting's own turn-1 "
          "probabilities, fixed at the full-sample values. The repeat-request gap is $|p_1-p_1'|$ in points, where $p_1'$ is "
          "the turn-1 probability of an independent second request.", "tab:strata", wide=True, size="\\footnotesize", sep="3pt")


def table_reask():
    rows, signs = [], {}
    for s in SET:
        x = G(d(s), "turn_2/without_fields/pooled")
        diff = G(x, "reask/control_move_minus_redraw_gap")
        signs[s] = (round(val(diff), 4), excl(diff))
        rows.append([LABEL[s], ec(G(d(s), "redraw/pooled/mean_absolute_gap")),
                     num(G(d(s), "redraw/pooled/share_gap_at_least_5_points")),
                     num(G(x, "reask/mean_absolute_move/control")), ec(diff),
                     num(G(d(s), "noise/threshold")), num(G(d(s), "noise/without_fields/all_arms/noise_change")),
                     num(G(x, "coherence_turn_2/enthusiast/share_coherent")), num(G(x, "coherence_turn_2/skeptic/share_coherent"))])
    print("  control move minus re-draw gap (estimate, CI excludes 0):", signs)
    write("tab_reask", ["Setting & Repeat-request gap [CI] & Gap 5+ & Control change & Control $-$ repeat [CI] & Noise threshold & Noise changes & Coherent enthusiast & Coherent sceptic"],
          rows, "lcccccccc",
          "Repeat requests and noise. The repeat-request gap is the mean of $|p_1-p_1'|$ between two independent turn-1 requests, "
          "and gap 5+ is the share of items where the gap reaches five points. Control change is the mean of $|p_2-p_1|$ "
          "when the request is repeated within the conversation with no other line. The noise threshold is the 90th "
          "percentile of the repeat-request gap, and noise changes is the share of turn-2 replies that move at least as far as the noise threshold "
          "or change the decision. Coherent enthusiast and coherent sceptic give the share of coherent turn-2 decisions. Turn-2 columns "
          "use the half without the fields.", "tab:reask", wide=True, size="\\footnotesize", sep="3pt")


def table_selfreport():
    rows = []
    for s in SET:
        x = G(d(s), "turn_2/with_fields/pooled")
        r = x["rates"]
        hide = r["hide"]["all_arms"]
        rows.append([LABEL[s], ec(G(x, "D/D")), ec(d(s)["effect_of_the_fields"]), num(r["substantive"]["all_arms"]),
                     num(r["literal"]["all_arms"]), f"{hide['count']} of {hide['n']}", num(r["hide_literal"]["all_arms"]),
                     num(r["phantom"]["all_arms"]), num(r["recall_misreport"]["all_arms"]),
                     num(r["consistency_serving_of_all_answers"]["all_arms"])])
    write("tab_selfreport", ["Setting & $D$ with fields [CI] & Fields effect [CI] & Substantive & Literal & Hidden & Hide literal & Phantom & Recall error & Consistency"],
          rows, "lccccccccc",
          "Self-reports on the half of the items sent with the self-report fields, the retro and prospective sets pooled. The fields effect is $D$ "
          "without the fields minus $D$ with the fields, from the half without the fields and the half with the fields. Substantive and literal give the shares of "
          "turn-2 answers with a substantive change and with any change. Hidden counts substantive changes reported as "
          "unchanged, and hide literal is the same share for literal changes. Phantom is the share of unchanged answers "
          "reported as changed. Recall error is the share of answers whose stated previous probability differs from "
          "$p_1$ by more than half a point, and consistency is the share of all answers with a recall error that moves "
          "the stated previous probability toward $p_2$.", "tab:selfreport", wide=True, size="\\footnotesize", sep="2.5pt")


def table_weights():
    rows = []
    for s in SET:
        w = G(d(s), "turn_2/without_fields/pooled/weights")
        i = G(sc(s), "ideal_weight")
        rows.append([LABEL[s], ec(w["w_m"], 3, True), str(w["w_m"]["n"]), ec(w["w_h"], 3, True), str(w["w_h"]["n"]),
                     num(w["S_on_items_eligible_in_both_arms"], 3, True), num(i["w_star_on_every_resolved_item"], 3, True),
                     num(i["w_star_on_the_items_of_w_m"], 3, True), ec(i["w_m_minus_w_star"], 3, True)])
    write("tab_weights", ["Setting & $w_m$ [CI] & $n$ & $w_h$ [CI] & $n$ & $S$ shared & $w^*$ all & $w^*$ same items & $w_m-w^*$ [CI]"],
          rows, "lcrcrcccc",
          "Weights on a stated number, on the half without the fields. $w_m$ and $w_h$ are the least-squares weights of "
          "the move from $p_1$ on the gap between the stated number and $p_1$ in the market and user-estimate arms, on items "
          "where the gap is at least 10 points, so 1 means adopting the number and 0 means ignoring the number. $S$ shared "
          "uses the items eligible in the market arm and in the user-estimate arm. $w^*$ is the weight on the market price with the lowest Brier score, on "
          "every resolved retro item and on the resolved retro items used for $w_m$, and the last column compares "
          "$w_m$ with $w^*$ on the $w_m$ items.", "tab:weights", wide=True, size="\\footnotesize", sep="3pt")


def table_costs():
    rows = []
    for s in SET:
        c = G(sc(s), "turn_2_costs/without_fields")
        cav = c["caving"]
        rows.append([LABEL[s]] + [mark(c[a]["accuracy_cost"], 4) for a in ARMS4]
                    + [mark(c[a]["decision_cost"], 2, True) for a in ARMS4]
                    + [ec(cav["mean_accuracy_cost_of_enthusiast_and_skeptic"], 4), mark(cav["direction_term"], 4),
                       mark(cav["size_term"], 4)])
    write("tab_costs", ["& \\multicolumn{4}{c}{Accuracy cost} & \\multicolumn{4}{c}{Decision cost (dollars)} & \\multicolumn{3}{c}{Concession cost}",
                        "Setting & Control & Neutral & Enthus. & Sceptic & Control & Neutral & Enthus. & Sceptic & Mean [CI] & Direction & Size"],
          rows, "lccccccccccc",
          "Costs of turn-2 replies on the resolved retro items without the fields. Accuracy cost is the Brier score "
          "of $p_2$ minus the Brier score of $p_1$, and decision cost is the payoff of the turn-1 decision minus the "
          "payoff of the turn-2 decision, so positive values are losses. Neutral is the arm that asks the model to "
          "take another look. Concession cost is the mean accuracy cost of the enthusiast and sceptic replies, split into "
          "a direction term $(p_1-y)(\\delta_e-\\delta_s)$ and a size term $(\\delta_e^2+\\delta_s^2)/2$, where "
          "$\\delta$ is the move of each reply. A star marks an estimate whose 95 percent bootstrap interval excludes 0.",
          "tab:costs", wide=True, size="\\scriptsize", sep="2.5pt")


def table_direction():
    rows = []
    for s in SET:
        x = G(sc(s), "direction/without_fields")
        row = [LABEL[s]]
        for a in ("enthusiast", "skeptic", "market"):
            row += [f"{val(x[a]['moves'])} of {val(x[a]['answers'])}", num(x[a]["progressive_among_moves"])]
        rows.append(row)
    write("tab_direction", ["& \\multicolumn{2}{c}{Enthusiast} & \\multicolumn{2}{c}{Sceptic} & \\multicolumn{2}{c}{Market}",
                            "Setting & Moves & Progressive & Moves & Progressive & Moves & Progressive"],
          rows, "lcccccc",
          "Direction of turn-2 moves on the resolved retro items without the fields. A move is progressive when $p_2$ "
          "is closer to the outcome than $p_1$. The share of Yes outcomes among the items in this table is 0.384, so a move up is "
          "progressive less often than a move down.", "tab:direction", wide=True, size="\\footnotesize", sep="3pt")


def table_grid():
    cols = ["served"] + list(POLICIES) + ["ideal"]
    rows = []
    for s in SET:
        r = sc(s)
        row = [LABEL[s]]
        for p in cols:
            cr = r["closing_rule"] if p == "served" else r["policies"][p]["closing_rule"]
            f = [FAIL_CODE[x] for x in cr["fails"]]
            row.append("Pass" if not f else ", ".join(f))
        rows.append(row)
    write("tab_grid", ["Setting & As tested & Repeat & Copy & Follow 0.01 & Follow 0.015 & Follow 0.05 & Follow 0.10 & Ideal"],
          rows, "lcccccccc",
          "Closing rule for each setting as tested and for the scripted policies applied to the setting's own turn-1 answers. "
          "Each entry names the conditions that fail, H2 for $|D|<0.03$, S for the 95 percent interval of $S$ above 0 "
          "and gain for the 95 percent interval of the market-arm gain above 0.", "tab:grid", wide=True,
          size="\\footnotesize", sep="3pt")


def table_neverchange():
    stb = D["stubbornness"]

    def row(name, o, nd=3, lead=False):
        a, b = o["stubborn"], o["reference"]
        an = f" ({a['n']})" if isinstance(a, dict) and a.get("n") is not None else ""
        bn = f" ({b['n']})" if isinstance(b, dict) and b.get("n") is not None else ""
        return [name, num(a, nd, lead) + an, num(b, nd, lead) + bn, ec(o["difference"], nd, lead)]

    rows = [row("$D$", stb["D"]), row("$w_m$", stb["w_m"], 3, True), row("$w_h$", stb["w_h"], 3, True),
            row("$S$", stb["S"], 3, True), row("Gain", G(S, "stubbornness_brier_gain/retro"), 4),
            row("Substantive, all items", G(stb, "substantive/all_items")),
            row("Substantive, without fields", G(stb, "substantive/without_fields")),
            row("Substantive, with fields", G(stb, "substantive/with_fields")),
            row("Hide", stb["hide"]), row("Phantom", stb["phantom"]), row("Recall error", stb["recall_misreport"])]
    write("tab_neverchange", ["Measure & Never-change & Reference & Difference [CI]"], rows, "lccc",
          f"Haiku 5.5 off with the never-change instruction against Haiku 5.5 off as tested, on the same "
          f"{stb['items']} retro items ({stb['items_without_fields']} without the fields and {stb['items_with_fields']} "
          "with the fields), one chain per run. Parentheses give the number of items or answers behind each estimate, and "
          "brackets give paired 95 percent bootstrap intervals over events. The comparisons in this table are outside the Holm "
          "family.", "tab:neverchange", size="\\footnotesize", sep="3pt", wide=True)


def table_stakes():
    rows = []
    for s in SET:
        sr = G(d(s), "stakes_regression/pooled")
        ev, fa = sr["clustered_by_event"], sr["clustered_by_family"]
        mp = d(s)["mirror_pairs"]
        kp = d(s).get("knowledge_probe")
        ka = G(sc(s), "knowledge_probe_accuracy") if kp else None
        rows.append([LABEL[s], num(ev["t"]["b"], 3, True), num(ev["t"]["se"], 3, True), pval(ev["t"]["p"]),
                     num(fa["t"]["se"], 3, True), pval(fa["t"]["p"]), num(ev["q"]["b"], 3, True),
                     num(mp["retro"]["signed_mean"]), num(mp["prospective"]["signed_mean"]),
                     num(kp["share_known"]) if kp else "--",
                     str(ka["known_items_with_an_outcome"]) if ka else "--",
                     num(ka["share_stated_outcome_matches"]) if ka and ka["known_items_with_an_outcome"] else "--"])
    write("tab_stakes", ["& \\multicolumn{6}{c}{Stakes regression} & \\multicolumn{2}{c}{Mirror pairs} & \\multicolumn{3}{c}{Knowledge probe}",
                         "Setting & $b_t$ & SE event & $p$ & SE family & $p$ & $c_q$ & Retro & Prosp. & Known & With outcome & Match"],
          rows, "lccccccccccc",
          "Checks on turn-1 answers. The stakes regression fits $p_1=a+b_t\\,t+c_q\\,q$ over all items with standard "
          "errors clustered by event and by family. A mirror pair holds the two candidates of one election whose market "
          "prices at $F$ sum to at least 0.90, and the signed mean of a pair is the sum of the two turn-1 probabilities minus 1, "
          "so a positive mean would show a bias toward Yes. The probe asks whether the model knows how the question was resolved. Known is the "
          "share of the 400 retro items the model claims to know, with outcome counts the claimed items that have an "
          "outcome, and match is the share of the claimed items with an outcome where the stated outcome is right. Haiku 5.5 medium was not probed.",
          "tab:stakes", wide=True, size="\\footnotesize", sep="2.5pt")


def table_scorerobust():
    V = ("all", "without_brazil_family", "without_earlier_pull_events", "without_items_the_model_claims_to_know")
    rows, dropped = [], {}
    for s in SET:
        r = sc(s)
        rob = r["robustness"]
        b = [num(G(r, "turn_1_accuracy/brier"))] + [num(rob[v]["brier"]) for v in V[1:]]
        g = [num(G(r, "market_arm_brier_gain/without_fields"))] + [num(rob[v]["market_arm_brier_gain"]) for v in V[1:]]
        dropped[s] = [rob[v]["items_scored"] for v in V[1:]]
        rows.append([LABEL[s]] + b + g)
    print("  items scored without Brazil, earlier pull, known items:", dropped)
    write("tab_scorerobust", ["& \\multicolumn{4}{c}{Turn-1 Brier} & \\multicolumn{4}{c}{Market-arm gain}",
                              "Setting & All & No Brazil & No pull & No known & All & No Brazil & No pull & No known"],
          rows, "lcccccccc",
          "Scores on the resolved retro items after dropping the Brazilian election family, the events in the earlier "
          "pull of markets and the items the model claims to know in the probe (Appendix~\\ref{app:exposure}). The gain "
          "uses the half without the fields.", "tab:scorerobust", wide=True, size="\\footnotesize", sep="3pt")


def table_reliability():
    rel = D["reliability"]
    a, b = rel["chain_1_against_chain_3"], rel["chain_1_against_chain_2"]
    mm = lambda o: num(o["mixed_model"]["share_between_items"])  # noqa: E731
    rows = [["Items", str(a["n"]), str(b["n"])],
            ["Difference of $D$ [CI]", ec(a["difference_of_D"]), ec(b["difference_of_D"])],
            ["Pearson [CI]", ec(a["pearson"]), ec(b["pearson"])],
            ["Spearman [CI]", ec(a["spearman"]), ec(b["spearman"])],
            ["Intraclass correlation [CI]", ec(a["intraclass_correlation"]), ec(b["intraclass_correlation"])],
            ["Share of variance between items", mm(a), mm(b)]]
    print("  reliability mixed models:", json.dumps(a["mixed_model"])[:240], "|", json.dumps(b["mixed_model"])[:240])
    D1, D2, D3 = rel["D1"], rel["D2"], rel["D3"]
    write("tab_reliability", ["& Chain 1 against chain 3 & Chain 1 against chain 2"], rows, "lcc",
          "Reliability of the item differences behind $D$ for Haiku 5.5 off. Chain 1 sends the fields on half of the "
          "items, chain 2 repeats the turn-1 request and sends the fields on every item, and chain 3 sends no fields. Chain 1 is "
          "compared with chain 3 on the half where chain 1 sent no fields and with chain 2 on the half where chain 1 "
          "sent the fields, so that the two chains compared in a column sent the same request. $D$ is "
          f"{num(D1['all_items'], 3, True)} in chain 1, {num(D2['all_items'], 3, True)} in chain 2 and "
          f"{num(D3['all_items'], 3, True)} in chain 3 over all items, and chain 3 minus chain 2 is "
          f"{num(rel['D3_minus_D2'], 3, True)} (95 percent interval {num(rel['D3_minus_D2']['ci95'][0], 3, True)} to "
          f"{num(rel['D3_minus_D2']['ci95'][1], 3, True)}). The mixed model has random "
          "intercepts for events and items and converged with a warning from the optimiser. The intervals of the Spearman "
          "correlations follow \\citet{bonett2000}.", "tab:reliability",
          size="\\footnotesize", sep="3pt", place="h")


def notes_for_the_text():
    print("\nRetro minus prospective D (without the fields):")
    for s in SET:
        x = G(d(s), "turn_2/without_fields")
        print(f"  {LABEL[s]}: {val(G(x, 'retro/D/D')) - val(G(x, 'prospective/D/D')):+.3f}")
    print("Reduction of D by the fields:")
    for s in SET:
        a = val(G(d(s), "turn_2/without_fields/pooled/D/D"))
        b = val(G(d(s), "turn_2/with_fields/pooled/D/D"))
        print(f"  {LABEL[s]}: {100 * (a - b) / a:.0f} percent")


if __name__ == "__main__":
    for f in (table_turn1, table_turn2, table_policies, table_sets, table_models, table_replies, table_scores,
              table_topics, table_behaviour, table_dinference, table_drobust, table_strata, table_reask,
              table_selfreport, table_weights, table_costs, table_direction, table_grid, table_neverchange,
              table_stakes, table_scorerobust, table_reliability):
        f()
    notes_for_the_text()
