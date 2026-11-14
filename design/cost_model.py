"""Cost and power model for the pilot and the sprint run of 13 November 2026.

Arithmetic only: no API calls, no keys, no network. Token counts are
assumptions until the pilot measures them. Token counting is free on the
Anthropic API, so input counts can be made exact before the sprint run; output and
thinking counts come from the pilot. Run with:
python3 -I cost_model.py
"""
from math import atanh, tanh
from statistics import NormalDist

Z = NormalDist().inv_cdf
PHI = NormalDist().cdf

# Budget (US$): Anthropic and OpenRouter on 31 Oct 2026, Hugging Face credit on
# 6 Nov 2026 (period ends 1 Dec 2026). No account can pay for another.
BUDGET = {"anthropic": 18.49, "openrouter": 14.06, "huggingface": 26.91}

# Tokens per call, counted in the newer Anthropic tokenizer (about 30% more
# tokens than older tokenizers for the same text), so the OpenRouter rows
# overstate their token counts. Replace after the pilot.
SYSTEM = 330      # system prompt, including the answer-format instruction
QUESTION = 380    # title, full resolution text, scheduled end date. Not truncated: across the
                  # 14,237 retro candidate markets the text has a median of 171 words; US
                  # midterm markets use a 418-word template, so at a 25% US share the mean
                  # is about 186 words (measured 1 Nov 2026)
FRAMING = 120     # stated forecast date and the decision stakes
T1_OUT = 165      # turn-1 JSON: reasoning (at most 80 words), probability, prepare
T2_MSG = 70       # turn-2 user message
T2_OUT = 190      # turn-2 JSON adds changed and previous_probability
PROBE_IN = SYSTEM + QUESTION + 60
PROBE_OUT = 40
T1_IN = SYSTEM + QUESTION + FRAMING
# Turn 2 sends back only the visible turn-1 answer. Earlier thinking blocks are
# not sent back (allowed when no tools are used; the pilot confirms each API
# accepts this), so every model sees the same history and earlier thinking is
# never billed as input.
T2_IN = T1_IN + T1_OUT + T2_MSG
MARGIN = 1.3      # allowance for estimate error; errored batch requests are not billed

# Thinking tokens per call by setting (assumption; the pilot measures them).
THINK = {"off": 0, "low": 300, "medium": 700, "high": 1400}

# (input, output) US$ per million tokens at the price actually paid.
# Anthropic rows are Message Batches prices (half the standard price).
# OpenRouter rows are the cheapest route in the OpenRouter model list fetched
# 31 Oct 2026: the :batch variant where one is cheaper (half the sync price for
# the OpenAI models, a different share for others), the sync price otherwise.
# OpenRouter batches cannot be cancelled and most finish within 24 hours, so
# SYNC holds the price paid if a batch sticks and the work moves to sync calls.
# Every OpenRouter model here was listed before 8 Oct 2026, the stated forecast
# date of the resolved set; gpt-6.1-terra (26 Oct) and deepseek-v4.1-flash-1017
# (17 Oct) were listed later and are not eligible.
# Panel prices re-read on 7 Nov 2026 from the OpenRouter endpoint listings, one named
# provider per model (notes/openrouter_providers_2026-11-07.md); only the DeepSeek and
# GLM prices changed.
MODELS = {
    "Haiku 5.5": ((0.05, 0.25), "anthropic"),
    "Sonnet 5.5": ((1.00, 5.00), "anthropic"),
    "Opus 5.5": ((2.00, 10.00), "anthropic"),
    "Fable 5.1": ((5.00, 25.00), "anthropic"),
    "gpt-6-luna": ((0.05, 0.25), "openrouter"),             # OpenAI, listed 22 Sep 2026, batch
    "gpt-5.6-luna": ((0.10, 0.60), "openrouter"),           # OpenAI, 9 Jul 2026, cutoff Feb 2026, batch
    "gpt-oss-120b": ((0.03, 0.136), "openrouter"),          # OpenAI, freely downloadable, cutoff Jun 2024, batch
    "gemini-3.1-flash-lite": ((0.125, 0.75), "openrouter"),  # Google, 7 May 2026, no stated cutoff, batch price
                                                            # (the panel runs it as sync calls, OR_SYNC)
    "gemini-2.5-flash-lite": ((0.10, 0.40), "openrouter"),  # Google, cutoff Jan 2025, sync list price
    "llama-4-scout": ((0.10, 0.30), "openrouter"),          # Meta, freely downloadable, cutoff Aug 2024, sync
    "mistral-small-2603": ((0.15, 0.60), "openrouter"),     # Mistral, 16 Mar 2026, cutoff 1 Nov 2024 in the
                                                            # developer's system-prompt file (not a model card), sync
    "deepseek-v4.1-flash": ((0.112, 0.336), "openrouter"),  # DeepSeek, 10 Sep 2026, no stated cutoff, batch at
                                                            # DeepInfra fp8, its only batch provider on 7 Nov 2026
    "qwen3.7-flash": ((0.03, 0.13), "openrouter"),          # Alibaba, 27 Jul 2026, no stated cutoff, sync only
    "glm-5.3-flash": ((0.075, 0.25), "openrouter"),         # Zhipu, 26 Aug 2026, sync at GMICloud fp8 (7 Nov 2026;
                                                            # the 31 Oct price of 0.016/0.148 is no longer listed)
    "grok-4.3": ((1.00, 2.00), "openrouter"),               # xAI, 30 Apr 2026, no stated cutoff, batch
    "kimi-k2.5": ((0.50, 2.50), "openrouter"),              # Moonshot, 27 Jan 2026, no stated cutoff, sync only
}
SYNC = {"gpt-6-luna": (0.10, 0.50), "gpt-5.6-luna": (0.20, 1.20), "gpt-oss-120b": (0.15, 0.60),
        "gemini-3.1-flash-lite": (0.25, 1.50), "deepseek-v4.1-flash": (0.14, 0.42), "grok-4.3": (1.25, 2.50)}

# Hugging Face Inference Providers, router model list read 6 Nov 2026: the cheapest
# live provider, the same rates as the provider with no added fee, sync calls only
# (no batch route), provider named in every request. DeepSeek V4.1 Flash
# (deepinfra 0.20/0.60) and GLM-5.3-Flash (0.15/0.50) cost about four times more
# than on OpenRouter and stay there.
HF = {"gpt-oss-120b": (0.037, 0.17), "llama-4-scout": (0.10, 0.30)}   # deepinfra, both
HF_MOVE = ("gpt-oss-120b", "llama-4-scout")   # route approved by Jason Hung on 7 Nov 2026

# Reasoning tokens per call for models whose reasoning cannot be switched off,
# at the lowest setting they accept (assumption; billed as output; the pilot
# measures them). qwen3.7-flash and kimi-k2.5 list no effort levels, so whether
# their reasoning can be switched off is unknown until the pilot; both are
# counted as on.
MIN_REASONING = {"gpt-oss-120b": 300, "glm-5.3-flash": 600, "qwen3.7-flash": 600, "kimi-k2.5": 800}

# Recommended OpenRouter panel: one cheap model per developer, plus OpenAI's
# freely downloadable model. Dearer options are priced separately.
OR_PANEL = ["gpt-6-luna", "gpt-oss-120b", "gemini-3.1-flash-lite", "llama-4-scout",
            "mistral-small-2603", "deepseek-v4.1-flash", "qwen3.7-flash", "glm-5.3-flash"]
# Panel models run as sync calls although a batch would be cheaper. Gemini batches go
# through Vertex, which can take up to 96 hours, and the Sentient Futures Gemini
# batches were still stuck after 24 hours on 4 Oct 2026. From 8 Nov 2026 every OpenRouter
# panel request is a sync call (PLAN 5.3): the two pilot test batches of 7 Nov had no reply
# after about 9 hours, and the pilot measured the all-sync sprint at US$6.42 with the margin.
OR_SYNC = {"gemini-3.1-flash-lite", "gpt-6-luna", "deepseek-v4.1-flash"}

ARMS = 6          # control (request line only), double-check, enthusiast, skeptic, market, hunch; a stake arm would make 7
N_RETRO = 400     # resolved items (stated forecast date 8 Oct 2026); realistic yield, cap 500
N_PRO = 400       # prospective items (stated forecast date 12 Nov 2026); realistic yield, cap 500

# Cost-loss thresholds t, one fifth of the items each (seeded), and the new
# threshold t' of the optional stake arm (t = 0.5 goes to 0.2 or 0.8, half each).
T_VALUES = (0.2, 0.35, 0.5, 0.65, 0.8)
T_STAKE = {0.2: (0.8,), 0.35: (0.65,), 0.5: (0.2, 0.8), 0.65: (0.35,), 0.8: (0.2,)}


def price(model, sync=False, hf=False):
    """(input, output) US$ per million tokens; sync=True prices an OpenRouter batch row as
    sync calls; hf=True prices the model on Hugging Face (sync calls only)."""
    if hf:
        return HF[model]
    return SYNC.get(model, MODELS[model][0]) if sync else MODELS[model][0]


def reasoning(model, think):
    """Thinking or reasoning tokens per call: the setting, or the floor the model cannot go below."""
    return max(THINK[think], MIN_REASONING.get(model, 0))


def chain_cost(model, think, arms=ARMS, sync=False, hf=False):
    """US$ for one item: the turn-1 call plus one turn-2 call per arm."""
    p_in, p_out = price(model, sync, hf)
    tokens_in = T1_IN + arms * T2_IN
    tokens_out = T1_OUT + arms * T2_OUT + (1 + arms) * reasoning(model, think)
    return (p_in * tokens_in + p_out * tokens_out) / 1e6


def probe_cost(model, think, sync=False, hf=False):
    p_in, p_out = price(model, sync, hf)
    return (p_in * PROBE_IN + p_out * (PROBE_OUT + reasoning(model, think))) / 1e6


def turn1_cost(model, think, sync=False, hf=False):
    """US$ for one extra turn-1 call (the re-draw that measures run-to-run noise)."""
    p_in, p_out = price(model, sync, hf)
    return (p_in * T1_IN + p_out * (T1_OUT + reasoning(model, think))) / 1e6


def run(model, think, items, chains=1, extra_t1=0, probe_items=0, arms=ARMS, sync=False, hf=False):
    """chains = full chains per item; extra_t1 = extra turn-1 draws per item."""
    cost = items * (chains * chain_cost(model, think, arms, sync, hf)
                    + extra_t1 * turn1_cost(model, think, sync, hf))
    cost += probe_items * probe_cost(model, think, sync, hf)
    return cost * MARGIN


def mde(sd, n, deff=1.3, alpha=0.05, power=0.8):
    """Smallest true mean difference a two-sided test detects with the given power."""
    return (Z(1 - alpha / 2) + Z(power)) * sd * (deff / n) ** 0.5


def tost_power(margin, sd, n, deff=1.3, alpha=0.05):
    """Power to show equivalence within +/- margin when the true difference is zero."""
    se = sd * (deff / n) ** 0.5
    return max(0.0, 2 * PHI(margin / se - Z(1 - alpha)) - 1)


def sd_weighted(pairs):
    """Population SD of (value, weight) pairs whose weights sum to 1."""
    mean = sum(v * w for v, w in pairs)
    return sum(w * (v - mean) ** 2 for v, w in pairs) ** 0.5


def tally(lines):
    """Totals by account. A line is (label, model, cost) or (label, model, cost, account)."""
    totals = {acct: 0.0 for acct in BUDGET}
    for line in lines:
        totals[line[3] if len(line) > 3 else MODELS[line[1]][1]] += line[2]
    return totals


def show(title, lines):
    print(f"\n{title}")
    for line in lines:
        print(f"  {line[0]:<72} US${line[2]:6.2f}")
    totals = tally(lines)
    for acct, spent in totals.items():
        if spent:
            flag = "fits" if spent <= BUDGET[acct] else f"needs a top-up of about US${spent - BUDGET[acct]:.2f}"
            print(f"  total {acct:<11} US${spent:6.2f} of US${BUDGET[acct]:.2f}: {flag}")
    return totals


def pilot_lines(arms=ARMS, hf_models=()):
    """Pilot requests. arms=ARMS + 1 adds the stake arm; models in hf_models run on Hugging Face.
    The knowledge probe runs on the pilot items of every setting that runs it in the sprint."""
    lines = [
        ("Haiku 5.5, 50 items, thinking off, 2 chains, probe", "Haiku 5.5",
         run("Haiku 5.5", "off", 50, 2, 0, 50, arms=arms)),
        ("Haiku 5.5, 50 items, thinking at default (medium)", "Haiku 5.5",
         run("Haiku 5.5", "medium", 50, arms=arms)),
        ("Sonnet 5.5, 20 items, thinking off (between_tools), 2 chains, probe", "Sonnet 5.5",
         run("Sonnet 5.5", "off", 20, 2, 0, 20, arms=arms)),
        ("Sonnet 5.5, 10 items, thinking at default (high)", "Sonnet 5.5",
         run("Sonnet 5.5", "high", 10, arms=arms)),
        # Self-report check: enthusiast and skeptic re-sent without the two self-report
        # fields, reusing the chain-1 turn-1 answers (two extra turn-2 calls per item).
        ("Self-report check: Haiku 5.5, 50 items, 2 arms without the two fields", "Haiku 5.5",
         run("Haiku 5.5", "off", 50, arms=2) - run("Haiku 5.5", "off", 50, arms=0)),
    ]
    for m in OR_PANEL:
        hf = m in hf_models
        line = (f"{m}, 20 items, 1 chain, probe, {'Hugging Face' if hf else 'sync'}", m,
                run(m, "off", 20, 1, 0, 20, arms=arms, sync=True, hf=hf))
        lines.append(line + ("huggingface",) if hf else line)
    return lines


if __name__ == "__main__":
    n = N_RETRO + N_PRO
    print(f"Tokens per call: turn 1 in {T1_IN}, out {T1_OUT} + thinking; "
          f"turn 2 in {T2_IN}, out {T2_OUT} + thinking; margin x{MARGIN}; {ARMS} turn-2 arms")
    print(f"Cost of one item chain (turn 1 plus {ARMS} arms), before the margin:")
    for m in MODELS:
        row = ", ".join(f"{k} US${chain_cost(m, k):.4f}" for k in THINK)
        print(f"  {m:<32} {row}")

    print("Cost per 100 items, one chain plus one extra turn-1 draw, with the margin:")
    for m in MODELS:
        print(f"  {m:<32} thinking off (or lowest) US${run(m, 'off', 100, 1, 1):.2f}")
    for m in HF:
        print(f"  {m + ' (Hugging Face)':<32} thinking off (or lowest) US${run(m, 'off', 100, 1, 1, hf=True):.2f}")

    pilot = show("Pilot (before 13 Nov, marked preexisting): items from a disjoint window; gpt-oss-120b and "
                 "llama-4-scout on Hugging Face (route approved 7 Nov 2026)", pilot_lines(hf_models=HF_MOVE))
    pilot_stake = tally(pilot_lines(ARMS + 1, HF_MOVE))
    pilot_or = tally(pilot_lines())
    pilot_or_stake = tally(pilot_lines(ARMS + 1))
    print(f"  pilot with the stake arm ({ARMS + 1} arms): anthropic US${pilot_stake['anthropic']:.2f}, "
          f"openrouter US${pilot_stake['openrouter']:.2f}, huggingface US${pilot_stake['huggingface']:.2f}")
    print(f"  for comparison, all eight panel models on OpenRouter: openrouter US${pilot_or['openrouter']:.2f}; "
          f"with the stake arm US${pilot_or_stake['openrouter']:.2f}")
    opus_pilot = ("Opus 5.5, 10 items, effort low (only with option B)", "Opus 5.5", run("Opus 5.5", "low", 10))

    base = [
        ("Haiku 5.5, thinking off, 3 chains per item, knowledge probe", "Haiku 5.5",
         run("Haiku 5.5", "off", n, 3, 0, N_RETRO)),
        ("Haiku 5.5, thinking medium (default), 1 chain + turn-1 re-draw", "Haiku 5.5",
         run("Haiku 5.5", "medium", n, 1, 1)),
        ("Sonnet 5.5, thinking off, 1 chain + turn-1 re-draw, probe", "Sonnet 5.5",
         run("Sonnet 5.5", "off", n, 1, 1, N_RETRO)),
        ("Stubbornness demonstration: Haiku 5.5, 100 items", "Haiku 5.5", run("Haiku 5.5", "off", 100)),
    ]
    a = show(f"Option A: {n} items ({N_RETRO} resolved + {N_PRO} prospective), Anthropic", base)
    opus = [opus_pilot, ("Opus 5.5, effort low, 300 items, 1 chain", "Opus 5.5", run("Opus 5.5", "low", 300))]
    b = show("Option B: option A plus an Opus 5.5 subset", base + opus)
    show("For comparison only: Sonnet 5.5 at its default thinking (high)", [
        ("Sonnet 5.5, thinking high, 1 chain + turn-1 re-draw", "Sonnet 5.5", run("Sonnet 5.5", "high", n, 1, 1)),
    ])
    stake = show(f"Option A with the optional stake arm ({ARMS + 1} arms)", [
        ("Haiku 5.5, thinking off, 3 chains per item, knowledge probe", "Haiku 5.5",
         run("Haiku 5.5", "off", n, 3, 0, N_RETRO, arms=ARMS + 1)),
        ("Haiku 5.5, thinking medium (default), 1 chain + turn-1 re-draw", "Haiku 5.5",
         run("Haiku 5.5", "medium", n, 1, 1, arms=ARMS + 1)),
        ("Sonnet 5.5, thinking off, 1 chain + turn-1 re-draw, probe", "Sonnet 5.5",
         run("Sonnet 5.5", "off", n, 1, 1, N_RETRO, arms=ARMS + 1)),
        base[3],
    ])
    print("\nLevers, each on its own in place of the Sonnet 5.5 line of option A:")
    for label, cost in (("Sonnet 5.5 without its turn-1 re-draw", run("Sonnet 5.5", "off", n, 1, 0, N_RETRO)),
                        ("Sonnet 5.5 on the resolved set only", run("Sonnet 5.5", "off", N_RETRO, 1, 1, N_RETRO))):
        spent = a["anthropic"] - base[2][2] + cost + pilot["anthropic"]
        flag = "fits" if spent <= BUDGET["anthropic"] else f"top-up about US${spent - BUDGET['anthropic']:.2f}"
        print(f"  {label:<72} US${cost:6.2f}; option A with the pilot US${spent:.2f} ({flag})")

    def panel_lines(arms=ARMS, hf_models=()):
        lines = []
        for m in OR_PANEL:
            if m in hf_models:
                lines.append((f"{m} (Hugging Face)", m, run(m, "off", n, 1, 1, N_RETRO, arms=arms, hf=True),
                              "huggingface"))
            else:
                lines.append((m, m, run(m, "off", n, 1, 1, N_RETRO, arms=arms, sync=m in OR_SYNC)))
        return lines

    hf_split = show(f"Panel of {len(OR_PANEL)} models on the approved route (7 Nov 2026): gpt-oss-120b and "
                    f"llama-4-scout on Hugging Face, the other six on OpenRouter; {n} items, 1 chain + turn-1 "
                    "re-draw + probe, cheapest route, Gemini as sync calls", panel_lines(hf_models=HF_MOVE))
    hf_split_stake = show(f"Same route with the stake arm ({ARMS + 1} arms)", panel_lines(ARMS + 1, HF_MOVE))
    show("Same route if every OpenRouter batch moves to sync calls", [
        (f"{m} (Hugging Face)", m, run(m, "off", n, 1, 1, N_RETRO, hf=True), "huggingface") if m in HF_MOVE
        else (m, m, run(m, "off", n, 1, 1, N_RETRO, sync=True)) for m in OR_PANEL])
    panel = show(f"For comparison, all {len(OR_PANEL)} panel models on OpenRouter, cheapest route, "
                 "Gemini as sync calls", panel_lines())
    show("Same comparison with Gemini on batch", [(m, m, run(m, "off", n, 1, 1, N_RETRO)) for m in OR_PANEL])
    panel_stake = show(f"Same comparison with the stake arm ({ARMS + 1} arms), Gemini as sync calls",
                       panel_lines(ARMS + 1))
    show(f"Same comparison with the stake arm ({ARMS + 1} arms), Gemini on batch", [
        (m, m, run(m, "off", n, 1, 1, N_RETRO, arms=ARMS + 1)) for m in OR_PANEL])
    show("Same comparison if every batch moves to sync calls", [
        (m, m, run(m, "off", n, 1, 1, N_RETRO, sync=True)) for m in OR_PANEL])
    show("Dearer OpenRouter options, each priced on its own (cheapest route)", [
        (m, m, run(m, "off", n, 1, 1, N_RETRO)) for m in ("grok-4.3", "kimi-k2.5", "gpt-5.6-luna",
                                                           "gemini-2.5-flash-lite")])

    print("\nTotals with the pilot added (expected cost is the total without the x1.3 margin):")
    for name, acct, t, p in (
            ("option A", "anthropic", a, pilot),
            ("option B", "anthropic", b, pilot),
            ("option A with the stake arm", "anthropic", stake, pilot_stake),
            ("panel on the approved route, OpenRouter part", "openrouter", hf_split, pilot),
            ("panel on the approved route, Hugging Face part", "huggingface", hf_split, pilot),
            ("same with the stake arm, OpenRouter part", "openrouter", hf_split_stake, pilot_stake),
            ("same with the stake arm, Hugging Face part", "huggingface", hf_split_stake, pilot_stake),
            ("for comparison, all eight on OpenRouter", "openrouter", panel, pilot_or),
            ("for comparison, all eight on OpenRouter with the stake arm", "openrouter", panel_stake,
             pilot_or_stake)):
        spent = t[acct] + p[acct]
        flag = "fits" if spent <= BUDGET[acct] else f"top-up about US${spent - BUDGET[acct]:.2f}"
        print(f"  {name}: {acct} US${spent:.2f} of US${BUDGET[acct]:.2f} ({flag}); "
              f"expected US${spent / MARGIN:.2f}")

    print("\nContingencies, not in the totals above:")
    test = {m: run(m, "off", 10, arms=0) for m in ("gpt-6-luna", "deepseek-v4.1-flash", "gpt-oss-120b")}
    print(f"  OpenRouter test batch for rule 8 (turn 1 only, 10 items per batch model, batch prices): "
          f"US${sum(test.values()) - test['gpt-oss-120b']:.4f} on the approved route (gpt-6-luna and "
          f"deepseek-v4.1-flash); US${sum(test.values()):.4f} with all eight on OpenRouter")
    def turn2_only(model, think, items, sync=False, hf=False):
        """US$ for the turn-2 requests of one chain, reusing turn-1 replies already paid for (PLAN 10.4)."""
        return items * (chain_cost(model, think, ARMS, sync, hf) - turn1_cost(model, think, sync, hf)) * MARGIN
    recheck = [("Haiku 5.5 off", "Haiku 5.5", turn2_only("Haiku 5.5", "off", 10)),
               ("Haiku 5.5 medium", "Haiku 5.5", turn2_only("Haiku 5.5", "medium", 10)),
               ("Sonnet 5.5 off", "Sonnet 5.5", turn2_only("Sonnet 5.5", "off", 10))]
    recheck += [(m, m, turn2_only(m, "off", 10, hf=True), "huggingface") if m in HF_MOVE
                else (m, m, turn2_only(m, "off", 10, sync=True)) for m in OR_PANEL]
    rc = tally(recheck)
    print(f"  Recheck of the turn-2 wording (rule 1, run pilot_wording of PLAN 10.4), the six arms on 10 pilot "
          f"items per setting, reusing the chain-1 turn-1 replies of the pilot, approved route with every "
          f"OpenRouter request sync: anthropic US${rc['anthropic']:.2f}, openrouter US${rc['openrouter']:.2f}, "
          f"huggingface US${rc['huggingface']:.2f}")
    for arms, p_hf, p_or in ((ARMS, pilot, pilot_or), (ARMS + 1, pilot_stake, pilot_or_stake)):
        for label, hf_models, p in (("approved route", HF_MOVE, p_hf), ("all eight on OpenRouter", (), p_or)):
            lines = [(m, m, run(m, "off", n, 1, 1, N_RETRO, arms=arms, hf=True), "huggingface")
                     if m in hf_models else (m, m, run(m, "off", n, 1, 1, N_RETRO, arms=arms, sync=True))
                     for m in OR_PANEL]
            spent = tally(lines)["openrouter"] + p["openrouter"]
            flag = "fits" if spent <= BUDGET["openrouter"] else f"top-up about US${spent - BUDGET['openrouter']:.2f}"
            print(f"  Every OpenRouter batch row as sync (rule 8 alternative, or every batch late), {arms} arms, "
                  f"{label}, with the pilot: openrouter US${spent:.2f} ({flag})")

    print("\nPower for the primary contrast (enthusiast minus skeptic, per model),"
          " cluster design effect 1.3:")
    for sd in (0.10, 0.15, 0.20):
        for items in (300, 400, 800):
            print(f"  SD {sd:.2f}, {items:>4} items: smallest detectable difference "
                  f"{mde(sd, items):.3f}; power to show equivalence within 0.03 "
                  f"{tost_power(0.03, sd, items):.2f}")
    print("\nPaired Brier difference between two forecasters on resolved items:")
    for sd in (0.08, 0.12):
        for items in (300, 400, 800):
            print(f"  SD of the per-item difference {sd:.2f}, {items} items: "
                  f"smallest detectable difference {mde(sd, items):.3f}")

    print("\nHolm correction over the settings tested (strictest two-sided threshold):")
    for k in (11, 12):
        z = Z(1 - 0.05 / (2 * k))
        print(f"  {k} settings: z {z:.3f}; the smallest detectable differences above grow by a factor of "
              f"{(z + Z(0.8)) / (Z(0.975) + Z(0.8)):.3f}")

    sd_t = sd_weighted([(t, 1 / len(T_VALUES)) for t in T_VALUES])
    sd_dt = sd_weighted([(tp - t, 1 / len(T_VALUES) / len(T_STAKE[t])) for t in T_VALUES for tp in T_STAKE[t]])
    print(f"\nStake slopes, cluster design effect 1.3 (SD of t {sd_t:.4f}; SD of t' - t {sd_dt:.4f}):")
    for resid, note in ((0.12, "with q in the regression (PILOT)"), (0.30, "without q")):
        for items in (400, 800):
            se = resid / sd_t * (1.3 / items) ** 0.5
            slope = mde(resid / sd_t, items)
            print(f"  turn-1 probability on t, residual SD {resid:.2f} {note}, {items} items: SE {se:.4f}; "
                  f"smallest detectable slope {slope:.3f} ({slope * 0.6 * 100:.1f} points from t 0.2 to 0.8)")
    for items in (400, 800):
        se = 0.10 / sd_dt * (1.3 / items) ** 0.5
        print(f"  stake-arm change on t' - t, SD of the change 0.10 (PILOT), {items} items: SE {se:.4f}; "
              f"smallest detectable slope {mde(0.10 / sd_dt, items):.3f}")

    print("\nRQ3: 95% interval for a Spearman correlation of 0.6 across models "
          "(Fisher z with the Bonett and Wright standard error):")
    for k in (10, 11, 14, 16):
        z, se = atanh(0.6), ((1 + 0.6 ** 2 / 2) / (k - 3)) ** 0.5
        print(f"  {k} models: {tanh(z - Z(0.975) * se):.2f} to {tanh(z + Z(0.975) * se):.2f}")
