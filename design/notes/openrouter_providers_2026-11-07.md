# One named provider per panel model (listings read 7 November 2026)

**Sources.** Public endpoint listings saved in raw_sources/openrouter_endpoints_2026-11-07/ (`GET https://openrouter.ai/api/v1/models/{id}/endpoints`, and the `:batch` listing for the two batch models), the OpenRouter models list (raw_sources/openrouter_docs_2026-11-07/models_2026-11-07.json) and the provider-selection and service-tier pages saved beside it. Hugging Face entries come from raw_sources/huggingface_2026-11-06/router_v1_models.json.

**Rule.** Every model runs on one named endpoint with fallbacks switched off, so every reply in a setting comes from the same host. A freely downloadable model runs on a third-party host at the precision its developer serves (fp8), because DeepSeek's own endpoint is not listed on 7 November 2026. Where several endpoints qualify, the cheapest one is used.

**Choice per model.**

| Model | Route | Provider sent | Precision | US$ per million tokens, in/out | Reasoning sent |
|---|---|---|---|---|---|
| openai/gpt-6-luna | OpenRouter batch in the sprint, sync in the pilot | batch `only: ["openai"]`; sync `openai` | not stated (developer) | batch 0.05/0.25; sync 0.10/0.50 | `{"effort": "none"}` |
| google/gemini-3.1-flash-lite | OpenRouter sync | `google-ai-studio` | not stated (developer) | 0.25/1.50 | `{"effort": "none"}` |
| mistralai/mistral-small-2603 | OpenRouter sync | `mistral/zdr` | not stated (developer) | 0.15/0.60 | `{"effort": "none"}` |
| deepseek/deepseek-v4.1-flash | OpenRouter batch in the sprint, sync in the pilot | batch `only: ["deepinfra"]`; sync `deepinfra/fp8` | fp8 | batch 0.112/0.336; sync 0.14/0.42 | `{"effort": "none"}` |
| qwen/qwen3.7-flash | OpenRouter sync | `alibaba` (cheapest of its endpoints) | not stated (developer) | 0.03/0.13 | `{"enabled": false}` |
| z-ai/glm-5.3-flash | OpenRouter sync | `gmicloud/fp8` | fp8 | 0.075/0.25 | `{"effort": "low"}` |
| openai/gpt-oss-120b | Hugging Face sync | `openai/gpt-oss-120b:deepinfra` | not stated | 0.037/0.17 | `reasoning_effort: "low"` |
| meta-llama/Llama-4-Scout-17B-16E-Instruct | Hugging Face sync | `meta-llama/Llama-4-Scout-17B-16E-Instruct:deepinfra` | not stated | 0.10/0.30 | none |

**Reading the table.** "Provider sent" is the value placed in the request. A batch names the base provider at the top level of the batch, because OpenRouter rejects ordering options in batches and a provider object inside one request does not pin the batch. Reasoning settings follow the models list of 7 November 2026. GLM-5.3-Flash marks reasoning as mandatory (efforts max, high and low), so its lowest setting is sent instead of "none". qwen3.7-flash lists no effort levels, so reasoning is switched off with `enabled: false`. The Hugging Face pages read on 6 November do not name a reasoning parameter, so the client sends the OpenAI chat-completions parameter `reasoning_effort`.

**Request objects.**

- Sync request: `"provider": {"only": [slug], "sort": "price", "allow_fallbacks": false, "require_parameters": true}`. Sorting by price matters because a base slug of a freely downloadable model also matches its priority endpoints. No `service_tier` is sent; the reply's `provider` and served `service_tier` are logged.
- Batch: `"provider": {"only": [base], "allow_fallbacks": false}` next to `model` in the batch body. With fallbacks off, the batch fails and does not move to another host if DeepInfra or OpenAI has no capacity; the noon-UTC sync rule of PLAN 5.3 then applies.
- Hugging Face: the provider suffix in the model name, never automatic selection.

**Why the cost increased.** On 31 October the cost model priced DeepSeek V4.1 Flash at 0.05/0.15 (batch) and 0.045/0.50 (sync) and GLM-5.3-Flash at 0.016/0.148. On 7 November DeepInfra fp8 is DeepSeek's only batch endpoint (0.112/0.336), and the GLM listing at 0.016/0.148 is gone. GMICloud fp8 is the cheapest GLM endpoint at fp8 (Z.AI's own fp8 endpoint costs 0.15/0.50; Relace at 0.06/0.20 serves fp4 and was rejected for lower precision).

**Costs.** Computed with cost_model.py at the prices above, the 800-item panel composition, the 20-item pilot and the 1.3 margin.

| Account | 31 Oct prices | 7 Nov prices | Credit |
|---|---|---|---|
| OpenRouter, approved route | 10.84 | 12.94 (expected 9.95 without the margin) | 14.06 |
| OpenRouter, every batch row sent sync | 12.17 | 14.14 (0.08 over) | 14.06 |
| Hugging Face | 2.44 | 2.44 | 26.91 |
| OpenRouter test batch, 10 turn-1 items each for gpt-6-luna and DeepSeek | 0.0019 | 0.0030 | |

**Reading the table.** The approved route still fits. Only the case in which every OpenRouter batch fails and moves to sync exceeds the credit, by 0.08 with the margin; expected spend in that case is about 10.9.

**Pilot checks added.** Zero reasoning tokens for qwen3.7-flash with `enabled: false` (else its lowest setting, as PLAN 10.3 rule 7 says); reasoning tokens for GLM-5.3-Flash at low; whether DeepInfra accepts `reasoning_effort: "low"` for gpt-oss-120b through Hugging Face; the served provider and tier for every sync request.
