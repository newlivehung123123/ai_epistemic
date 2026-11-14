# Hugging Face Inference Providers as a third payment route (checked 6 November 2026)

Jason Hung holds US$26.91 of Hugging Face credit (billing page, 6 November 2026, usage US$0.00, period shown as ending 1 December).

**Status.** Jason Hung approved the route on 7 November 2026. gpt-oss-120b and llama-4-scout run on Hugging Face through deepinfra as sync requests, and the other six panel models stay on OpenRouter. PLAN.md Section 5.4 governs where this note differs.

## Sources read on 6 November 2026 (copies in raw_sources/huggingface_2026-11-06/)

- Model list with providers, prices per million tokens and listing dates: https://router.huggingface.co/v1/models (126 models)
- Pricing and billing: https://huggingface.co/docs/inference-providers/pricing ("Hugging Face charges you the same rates as the provider, with no additional fees")
- Provider selection: https://huggingface.co/docs/inference-providers/index (automatic selection picks the fastest provider and fails over to other providers; an explicit provider "Forces use of a specific provider"; router suffixes :fastest, :cheapest, :preferred)
- Hub billing FAQ: https://huggingface.co/docs/hub/billing (credits pay for Inference Providers)

## Findings

1. No Anthropic model, no Gemini model and no gpt-6-luna is listed. The credit cannot pay for Haiku 5.5, Sonnet 5.5, gemini-3.1-flash-lite or gpt-6-luna.
2. Four of the eight OpenRouter panel models are listed: openai/gpt-oss-120b, meta-llama/Llama-4-Scout-17B-16E-Instruct, deepseek-ai/DeepSeek-V4.1-Flash (listed 10 September 2026) and zai-org/GLM-5.3-Flash (listed 25 August 2026). mistral-small-2603 and qwen3.7-flash are not listed.
3. The cheapest live provider and its price in US$ per million tokens (input/output) are deepinfra at 0.037/0.17 for gpt-oss-120b, deepinfra at 0.10/0.30 for Llama 4 Scout, deepinfra at 0.20/0.60 for DeepSeek V4.1 Flash, and novita, baseten and deepinfra at 0.15/0.50 for GLM-5.3-Flash (zai-org, the developer, is listed without a price).
4. The Inference Providers pages read describe no batch route. Every request would be a sync request.
5. deepseek-ai/DeepSeek-V4.1-Flash-1017 and MiniMaxAI/MiniMax-M3.1-Flash were listed on 17 October 2026, after the retrospective forecast date, so Rule R excludes them.

## Costs (cost_model.py functions, panel composition of 800 items, 1 chain, 1 re-draw, probe on 400, 20-item pilot, margin 1.3)

| Model | OpenRouter, with pilot | OpenRouter, stake arm | Hugging Face, with pilot | Hugging Face, stake arm |
|---|---|---|---|---|
| gpt-oss-120b | 0.92 | 1.04 | 1.06 | 1.19 |
| llama-4-scout | 1.37 | 1.55 | 1.37 | 1.55 |
| deepseek-v4.1-flash | 0.70 | 0.79 | 2.75 | 3.10 |
| glm-5.3-flash | 1.18 | 1.32 | 4.85 | 5.45 |

Every cell includes the 20-item pilot (sync, probe); the stake-arm columns use the 7-arm pilot. The DeepSeek and GLM Hugging Face cells use the prices in finding 3, which cost_model.py does not hold (recomputed 6 November 2026). The OpenRouter cells use the prices of 6 November 2026. At the provider prices of 7 November 2026 (openrouter_providers_2026-11-07.md), DeepSeek costs 1.54 and GLM 2.43 at OpenRouter with the pilot, and the bullets below use those prices.

- All eight on OpenRouter cost 15.24, or 17.15 with the stake arm (OpenRouter credit 14.06).
- With gpt-oss-120b and llama-4-scout on Hugging Face, OpenRouter needs 12.94 (stake arm 14.56, 0.50 above the credit) and Hugging Face 2.44 (stake arm 2.74). Expected spend without the margin is 9.95 at OpenRouter and 1.87 at Hugging Face, or 11.20 and 2.11 with the stake arm.
- If no OpenRouter batch can name a provider (pilot rule 8) and every batch row moves to sync, OpenRouter needs 14.14 on this route (15.92 with the stake arm), 0.08 above the credit; with all eight on OpenRouter it needs 19.44 (21.88).
- DeepSeek and GLM cost about 1.8 and 2.0 times as much on Hugging Face as on OpenRouter at the prices of 7 November, and stay on OpenRouter.

## Extra freely downloadable models listed before 8 October 2026 (same composition, margin 1.3)

| Model (cheapest provider) | Price in/out | Reasoning 0 | Reasoning 1,000 tokens per request |
|---|---|---|---|
| google/gemma-4-31B-it (novita) | 0.14/0.40 | 1.89 | 5.50 |
| MiniMaxAI/MiniMax-M3 (deepinfra) | 0.28/1.10 | 4.25 | 14.17 |
| Qwen/Qwen3.8-27B (deepinfra) | 0.20/2.50 | 5.75 | 28.31 |
| moonshotai/Kimi-K2.6 (deepinfra) | 0.75/3.50 | 12.26 | 43.84 |
| zai-org/GLM-5.3 (deepinfra) | 0.90/4.00 | 14.40 | 50.49 |
| deepseek-ai/DeepSeek-V4-Pro-0813 (deepinfra) | 1.30/2.60 | 15.77 | 39.22 |

An added model helps RQ3 only if an honesty benchmark score exists for it (MASK coverage is CHECK). Reasoning tokens per request are unknown until the pilot.

## Rules for the route

- Name the provider in every request (no automatic selection, because automatic selection fails over to another provider).
- Log the provider, the model listing date and the price on the request date.
- Plain JSON instruction, the same as every other model; deepinfra lists no structured-output support for gpt-oss-120b or Llama 4 Scout.
- Using the credit amends approved default 2 (the sprint run fits inside US$32.55). Jason Hung approved this on 7 November 2026.
- Whether deepinfra accepts the low reasoning setting for gpt-oss-120b through Hugging Face is checked at the pilot.
