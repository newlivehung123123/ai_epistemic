# Four audit papers and what each one means for the design

Read on 31 Oct 2026. Two papers were read in full from arXiv (text copies in audit_papers/). The other two exist only on OpenReview, which shows a "Verify you are human" check that I cannot complete, so for those two I read the abstract on the NeurIPS 2026 virtual page and nothing else.

## 1. Are You Sure You're Sure? Two Confounds in a Sycophancy Benchmark

Gupta, Jindal, Nigam and Sood (IIT Roorkee). arXiv 2609.32867v1; NeurIPS 2026 JUDGe workshop (OpenReview tySSyo3JbS). Read in full.

What they found
- Naming confound. SycEval's preemptive arm names a target answer, while its in-context arms (Simple, Ethos) do not. Naming a target raises the follow rate by 14.1 to 49.5 percentage points. Once naming is held equal, the timing effect reverses on 3 of 5 conditions (free-form, -14.4 points, p = 1.1e-7).
- Instruction-position confound. Moving the answer-format instruction from the pushback turn to the question turn changes the effect in opposite directions across models (Qwen2.5-3B +19.0 points, Qwen3-4B -7.8 points; difference p = 0.0059). For Llama-3.1-8B free-form the change is -5.1 points, and regressive caving falls from 54.7% to 42.8%.
- They use an equivalence test to support a null (Qwen3-4B).
- Their judge agrees with humans at kappa 0.70, against 0.63 pairwise among four annotators on 48 responses.
- Checklist (their Section 6): (a) no compared condition may name a candidate answer that the other does not; (b) instructions sit in the same turn in every condition; (c) report regressive and progressive rates separately.
- Limits: small open models only.

What it means for us
- The primary contrast must compare two arms that both name a direction (the enthusiast arm leans YES, the skeptic arm leans NO), with identical templates apart from the direction word. The neutral re-ask names nothing, so any contrast between neutral and a leaning arm mixes naming with direction. The neutral arm serves only as a re-ask baseline.
- The format instruction sits in the same place in every arm (in the system prompt, repeated identically in every turn).
- Movement toward the resolved outcome and movement away from it are reported separately, never pooled into one "sycophancy" rate.
- Null claims need an equivalence test with a margin fixed in advance.

## 2. Pitfalls in Evaluating Language Model Forecasters

Paleka, Goel, Geiping and Tramèr. arXiv 2506.00723v1; ICLR 2026 poster (OpenReview z85kARAoyD). Read in full.

What they found, and the fixes they propose
- Logical leakage. Selecting questions because they have resolved can leak the answer when the model knows the evaluation date (a question about the Queen reaching 100 cannot have resolved YES by 2025). Halawi et al. contain at least 3.8% such questions and Tao et al. at least 10%. Fix: keep only questions for which every possible resolution could be confirmed at evaluation time.
- Date-restricted retrieval is unreliable. Search engines leak later information through misdated pages and through ranking built on later knowledge.
- Stated cutoffs are a guideline, not a guarantee. A system-prompt hint drew a post-cutoff fact out of GPT-4o. The release date is a strict upper bound for a fixed snapshot; a buffer of a few months after the stated cutoff is prudent.
- Piggybacking. Market forecasts may sit in training data or retrieval results, so comparing an LLM with the crowd can be circular. ForecastBench is affected because it uses crowd forecasts as the gold standard on unresolved questions.
- Correlated questions reward betting. When many questions share a latent event (the 2024 US election), a forecaster that commits to one world can beat an honest one, and the top of a leaderboard can be overestimated. Fixes: report variance, use several disjoint backtest periods.
- Skewed question pools. Polymarket leans to crypto and sports, Manifold to personal questions, markets in general to US topics; ForecastBench's non-market questions follow a few time-series templates.
- Metrics. Calibration can reward the base rate over a more useful forecast; accuracy is not a proper score and should never be primary; Brier scores are not comparable across base rates; label noise means clipping can beat honest reporting under the log score. They recommend at least the Brier score, the log score and calibration.
- Manifold resolved 1,000 to 6,000 questions per month in late 2024, over half with fewer than 12 forecasters; the backtest window between cutoff and today keeps narrowing.

What it means for us
- Item rule: a question enters if it was open on the stated forecast date and its scheduled close date falls inside the window, whatever its outcome. Questions that resolved after the forecast date but before their scheduled close are kept, because dropping them removes mostly YES outcomes (corrected 1 Nov 2026; see prospective_check/NOTES.md). The prompt states the forecast date, never the evaluation date.
- No web access and no tools, so date-restricted retrieval cannot leak.
- Leakage window per model: the outcome must be decided after the model's release date, or at least several months after its stated cutoff. A knowledge probe (asking whether the model knows the outcome) and a date-split comparison check for leaks.
- The market price is never shown to the model. It serves only as an outside baseline, and the analysis notes whether the market existed before the model's cutoff.
- Uncertainty is computed with a bootstrap that resamples clusters of related questions (same event or market group), not single questions.
- A topic filter fixed in advance drops personal, sports-betting and crypto-price questions, and results are reported by topic.
- Scores: Brier and log (with the clipping rule stated and a sensitivity check), a Brier skill score against the base rate and the market, calibration and discrimination reported separately, accuracy only as a sanity check. Resolutions are spot-checked, and disputed or annulled markets are dropped.

## 3. What Does Fifty Days Stabilize? A Commit-Level Audit of ForecastBench

Daniel Alami (Harvard Business School). NeurIPS 2026 workshop "Can We Trust AI Evaluation? Robustness, Causality, and Risk in Modern AI Assessment", poster (OpenReview Ta2wQdVTzP). Abstract only, from neurips.cc/virtual/2026/178285.

What it reports
- ForecastBench waits 50 days before listing a new model. Across 13 releases, the day-50 ordering agrees well with the final ordering (median Kendall tau-b 0.824), yet the winner changes in 6 of 13 releases, three day-50 winners end outside the final top five, and the largest Brier regret is 0.0201.
- In a common 40-day follow-up across 15 releases, five day-50 winners change by day 90.
- A replay on 1,055 dated LiveCodeBench problems finds five changed winners across 13 states.
- It proposes a minimal reporting protocol in which every result is linked to a commit, a model cohort, a question set and a state record.

What it means for us
- A stable ordering does not mean a stable winner. We make no "best model" claim unless a bootstrap interval for the rank separates it, and the primary claims are within-model contrasts, not rankings.
- Every reported number is tied to a git commit, the frozen question set (with a hash), the exact model snapshot list and the date of the outcome data.

## 4. Reproducing ELEPHANT: Judge-Dependence and Model Deprecation in an LLM Sycophancy Benchmark

Kristina Sakayeva and Ana Trisovic. NeurIPS 2026 workshop "Can We Trust AI Evaluation?", poster (OpenReview PANMPBrDdC; an AI4MetaScience record SyMgQqWoMr also exists). Abstract from neurips.cc/virtual/2026/178298; repository README read.

What it reports
- A full reproduction one year on. The aggregate findings hold, but some model rankings change.
- Changing the LLM judge shifts the mean sycophancy rate by -0.16 to +0.23, depending on dataset and dimension.
- Within a year, five of the eleven evaluated models and one robustness-check judge were retired or no longer reachable through the original provider. The authors name this the "LLM behavior reproduction window".
- Their repository logs model snapshots, generation settings, seeds, token usage and judge settings, and releases cached outputs and per-example scores. Its robustness dimensions are judge identity, prompt version, temperature, maximum tokens and quantisation.

What it means for us
- Core measures are read from the model's own JSON (probability, decision, the yes/no "did you change" answer), so no judge is needed. Any judge used later must be checked against Jason Hung's labels and against a second judge.
- Record the model ID sent and the model field returned, the OpenRouter provider that served each request, every generation setting, the seed where supported, token counts, timestamps, and for Anthropic requests the `anthropic-version` and SDK version. Current Anthropic models have no dated snapshot IDs (see anthropic_models_and_prices.md), so the alias plus the request date is the record; use a dated ID wherever a provider offers one.
- Release raw outputs and per-item scores, so that every number can be recomputed after the models are retired.
