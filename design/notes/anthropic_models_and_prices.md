# Anthropic models, prices and API rules for this study

Downloaded on 31 Oct 2026 from the live Claude Platform documentation. Raw copies sit in `anthropic_docs/` (the file `about-claude_models_whats-new-claude-5-5.md` is a 9-byte 404 page and can be ignored).

Sources
- Models overview: https://platform.claude.com/docs/en/models/overview
- Pricing: https://platform.claude.com/docs/en/about-claude/pricing
- Model deprecations: https://platform.claude.com/docs/en/about-claude/model-deprecations
- API version 2026-10-21 migration: https://platform.claude.com/docs/en/api/migration-2026-10-21
- One overview page per model: https://platform.claude.com/docs/en/models/<model>/overview (fable-5-1, opus-5-5, sonnet-5-5, haiku-5-5, fable-5, opus-5, sonnet-5, opus-4-8, opus-4-7, opus-4-6, opus-4-5, sonnet-4-6, haiku-4-5)

## Models

"Reliable cutoff" is the date through which the model's knowledge is most extensive and reliable. "Training cutoff" is the broader range of training data (definitions from the models overview). Prices are standard per million tokens; the Batch API halves them.

| Model (API ID) | Released | Reliable cutoff | Training cutoff | Input / output | Batch input / output | Thinking | Default effort | Retirement not sooner than |
|---|---|---|---|---|---|---|---|---|
| Fable 5.1 (`claude-fable-5-1`) | 1 Sep 2026 | Jun 2026 | Jun 2026 | $10 / $50 | $5 / $25 | adaptive, always on | high | 1 Sep 2027 |
| Opus 5.5 (`claude-opus-5-5`) | 22 Sep 2026 | Jun 2026 | Jun 2026 | $4 / $20 | $2 / $10 | adaptive, always on, cannot be turned off | medium | 22 Sep 2027 |
| Sonnet 5.5 (`claude-sonnet-5-5`) | 28 Sep 2026 | Jun 2026 | Jun 2026 | $2 / $10 | $1 / $5 | adaptive; lowest setting `between_tools` turns off up-front thinking, works at effort `high` or below | high | 28 Sep 2027 |
| Haiku 5.5 (`claude-haiku-5-5`) | 7 Oct 2026 | Jun 2026 | Jun 2026 | $0.10 / $0.50 (prompts up to 100,000 tokens; $0.50 / $2.50 above) | $0.05 / $0.25 | adaptive, not listed as always on (whether `disabled` is accepted to be confirmed on the thinking page at build time) | medium | 7 Oct 2027 |
| Fable 5 | 9 Jun 2026 | Jan 2026 | Jan 2026 | $10 / $50 | $5 / $25 | always on | high | 9 Jun 2027 |
| Opus 5 | 24 Jul 2026 | May 2026 | May 2026 | $5 / $25 | $2.50 / $12.50 | adaptive | high | 24 Jul 2027 |
| Sonnet 5 | 30 Jun 2026 | Jan 2026 | Jan 2026 | $2 / $10 | $1 / $5 | adaptive | high | 30 Jun 2027 |
| Opus 4.8 | 28 May 2026 | Jan 2026 | Jan 2026 | $5 / $25 | $2.50 / $12.50 | adaptive | high | 28 May 2027 |
| Opus 4.7 | 16 Apr 2026 | Jan 2026 | Jan 2026 | $5 / $25 | $2.50 / $12.50 | adaptive | high | 16 Apr 2027 |
| Opus 4.6 | 5 Feb 2026 | May 2025 | Aug 2025 | $5 / $25 | $2.50 / $12.50 | adaptive (extended deprecated) | high | 5 Feb 2027 |
| Opus 4.5 (`claude-opus-4-5-20251101`) | 24 Nov 2025 | May 2025 | Aug 2025 | $5 / $25 | $2.50 / $12.50 | extended; 200K context | high | 24 Nov 2026 |
| Sonnet 4.6 | 17 Feb 2026 | Aug 2025 | Jan 2026 | $3 / $15 | $1.50 / $7.50 | adaptive (extended deprecated) | high | 17 Feb 2027 |
| Haiku 4.5 (`claude-haiku-4-5-20251001`) | 15 Oct 2025 | Feb 2025 | Jul 2025 | $1 / $5 | $0.50 / $2.50 | extended; 200K context | none | 15 Oct 2026 (date passed, model still active on 31 Oct) |

Excluded
- Mythos 5.1 and Mythos 5: "limited availability" on the pricing page.
- Sonnet 4.5 (`claude-sonnet-4-5-20250929`): deprecated 30 Sep 2026, retires 30 Nov 2026.
- Anthropic gives at least 60 days' notice before retiring a publicly released model.

## Price rules

- Batch: 50% off input and output.
- Cache write: 1.25x base input for a 5-minute lifetime, 2x for a 1-hour lifetime.
- Cache read: 0.1x base input in general, 0.05x on Opus 5.5 and Sonnet 5.5, 0.025x on Fable 5.1. Sonnet 5.5 cache read is therefore $0.10 per million tokens (an earlier note said $0.20; $0.10 is correct).
- Cache prices for the three 5.5 models, per million tokens: Opus 5.5 read $0.20, 5-minute write $5, 1-hour write $8; Sonnet 5.5 read $0.10, $2.50, $4; Haiku 5.5 read $0.01, $0.125, $0.20.
- Batch and cache discounts stack.
- Minimum cacheable prefix: 512 tokens on Opus 5.5, Opus 5, Fable 5 and 5.1, Sonnet 5.5 and Haiku 5.5; 1,024 on Opus 4.8, Sonnet 5 and Sonnet 4.6; 2,048 on Opus 4.7; 4,096 on Opus 4.6, Opus 4.5 and Haiku 4.5. A shorter prefix marked for caching silently caches nothing (`cache_creation_input_tokens` is 0). At most 4 cache breakpoints per request.
- Tokeniser. Claude 4.7 and later models use a newer tokeniser that "produces approximately 30% more tokens for the same text" (pricing page). Sonnet 4.6 and earlier use the previous tokeniser. Token counts are therefore not comparable across the two groups.

## API rules that bind the design

- Sampling. Under `anthropic-version: 2026-10-21`, `temperature`, `top_p` and `top_k` return a 400 error on every model, including inside Batch requests. Under `2023-06-01` they are accepted only where a model allows them, and Claude 4.7 and later accept only the defaults. Every Anthropic model is therefore run at its default sampling, and noise is measured by repeated draws, not by setting temperature.
- SDK. The Python SDK sends `2026-10-21` from version 2.0.0. The SDK installed in `/opt/anaconda3` is `anthropic` 0.85.0, which sends `2023-06-01`. The study pins one SDK version in a project virtual environment, chosen and checked against the SDK docs at build time.
- No prefill on Claude 4.6 and later. Answers are returned through structured outputs (a JSON schema), not by prefilling the reply. The plan departs from this and gives every model one plain JSON instruction (PLAN Sections 4.1 and 8.5).
- Refusals. A response can end with `stop_reason: "refusal"`. Fallbacks to another model stay off, and refusals are logged and reported as their own outcome.
- Thinking in two-turn dialogues. On the 5.5 models, thinking blocks from turn 1 are passed back unchanged in turn 2 (append-only); a block edited or dropped breaks the check that ties it to its conversation. The plan does not replay thinking, and the pilot checks that the API accepts a previous message without thinking (PLAN Section 4.3).
- Model identity. Current models have no dated snapshot IDs. Every request logs the alias sent, the `model` field returned, the request timestamp, the `anthropic-version` and the SDK version.
- Batches. Up to 100,000 requests or 256 MB per batch. Most finish within 1 hour, the maximum is 24 hours, results are kept for 29 days, and expired requests must be resubmitted.

## What this means for the item window

- Fable 5.1, Opus 5.5, Sonnet 5.5 and Haiku 5.5 all have a June 2026 cutoff and were released between 1 Sep and 7 Oct 2026.
- A model with no tools cannot know anything that happened after its release, so an outcome decided after 7 Oct 2026 is strictly clean for all four. A three-month buffer after the June cutoff (the prudent rule in Paleka et al.) gives 30 Sep 2026, which the release dates already pass.
- Up to the sprint, the strictly clean retrospective window is therefore about 8 Oct to 12 Nov 2026, roughly five weeks of resolved questions.
- Older models give a longer clean window (Opus 4.6, released 5 Feb 2026 with an August 2025 training cutoff, gives about nine months), but their retirement dates fall close to the ACL review period (Opus 4.6 and Sonnet 4.6 not sooner than February 2027; Opus 4.5 not sooner than 24 Nov 2026).
