# Question sources and candidate models (feasibility check, 31 Oct to 1 Nov 2026)

Scope. Can the study get 400 to 1,000 binary forecasting questions that resolved between about 1 Jun and 10 Nov 2026, after the training cutoffs of the models tested, from public, citable and redistributable sources? Which cheap models fit the budget?

How it was checked. Every count below was computed from API responses or files saved in `raw_sources/`, using the scripts in `scripts/` (see section 5). No paid API requests were made, no API key was used and no .env file was read. Blog posts were not used as a source for any count. Where a page was blocked or unreachable, it is marked as not verified.

Status. This note records the feasibility check of 31 Oct to 1 Nov 2026, made under an earlier design. PLAN.md governs wherever the two differ, in particular the question windows (PLAN Section 3.2), the eligibility rule for models (Rule R, PLAN Section 5.1) and the model panel (PLAN Section 5). Sections 1 and 3.4 below apply the earlier rule of a developer-stated cutoff before 1 Jun 2026.

---

## 1. Verdict

**Yes. 400 to 1,000 suitable questions exist, with three conditions.**

1. **Close the window on 31 Oct, not 10 Nov.** Resolution data in ForecastBench currently runs to 29 Oct 2026, and its files are published with gaps of up to 21 days. Questions resolving 1 to 10 Nov may not be public by 10 Nov.
2. **Only models with a developer-stated cutoff before 1 Jun 2026 qualify.** Three listed models break this:
   - GPT-6.1 terra (cutoff "Jun 01, 2026") falls inside the window.
   - GPT-6 luna ("May 18, 2026") and Grok 4.7 ("May 2026") end only days or weeks before it.
3. **Licences differ by source and decide what the replication package can contain.** See section 2.6.

**Sources and counts in the window.** Each count below was computed from that source's own files or API. The ForecastBench market questions are themselves drawn from Polymarket, Manifold, Metaculus, Kalshi and INFER, so the pools overlap and must not be added together.

| Source | Questions in window (what was counted) | Crowd or market probability at a set date | Licence or terms |
|---|---|---|---|
| ForecastBench market questions | **678** unique, resolved 1 Jun to 29 Oct 2026 (586 without the 92 from Metaculus) | Yes (`freeze_datetime_value`) | CC BY-SA 4.0 (dataset); the third-party question text keeps its own terms |
| ForecastBench dataset questions | 2,385 unique series; 7,186 unique (set, series) items; 11,726 resolved instances | No (the freeze value is the level of the series, not a probability) | CC BY-SA 4.0 |
| Polymarket, direct | **905** distinct non-series events with a resolved Yes/No market of more than US$10k; 7,050 markets before deduplication | Yes (CLOB price history, no key) | **Terms not verified** (site unreachable) |
| Manifold, direct | **1,111** resolved YES/NO binary markets with 20 or more unique traders | Rebuild from bets (not tested) | Academic research permitted; licence is non-commercial; redistribution not granted |
| BTF-3 (FutureSearch) | **1,355** with expected resolution 1 Jun to 1 Jul 2026 | No crowd (the forecast given comes from a proprietary forecasting system) | CC BY-NC 4.0 |
| Metaculus | Not usable | | The token-gated API terms forbid using the data to "train, evaluate" AI without written permission |

**Best single source: ForecastBench** (github.com/forecastingresearch/forecastbench-datasets). The README says "The datasets in this repository are distributed under the CC BY-SA 4.0 license".
- **It is the only source that already carries every field the study needs.** These are the question, background, resolution criteria, open and close dates, a crowd value at a fixed freeze date, and the resolved outcome.
- **The crowd baseline is strong.** On the 335 in-window market questions whose text is in the downloaded sets, the crowd's freeze-date probability scores Brier 0.100.
- **It has three costs:**
  - ShareAlike applies to the whole replication package.
  - The 92 questions sourced from Metaculus fall under Metaculus's ban on AI evaluation.
  - 343 of the 678 need question text from other question sets in the same repository, which were not downloaded.

**Sample size.** The brief cites Bosse (FutureSearch, 2026) as finding that more than 1,000 questions are needed to separate models. With the counts above, the design must therefore state its smallest detectable difference (section 2.7).

---

## 2. Question sources (Part A)

### 2.1 ForecastBench (Forecasting Research Institute)

**Where.**
- Repository: github.com/forecastingresearch/forecastbench-datasets.
- Site: forecastbench.org.
- Saved files: 8 question sets (2025-11-09, 2026-05-10, 2026-06-07, 2026-08-02, 2026-08-16, 2026-10-11, 2026-10-25 llm, and 2026-10-25 human) and all 39 resolution sets, which cover forecast due dates 2024-07-21 to 2026-10-11.

**Licence.**
- README: "The datasets in this repository are distributed under the CC BY-SA 4.0 license".
- forecastbench.org footer: "Content licensed under CC BY-SA 4.0".
- The code is MIT.
- Caveats:
  - (a) ShareAlike: a derived question file must also be CC BY-SA 4.0.
  - (b) The question text of market questions is copied from Polymarket, Manifold, Metaculus, Kalshi and INFER. FRI cannot relicense text it does not own.
  - (c) Metaculus's API terms forbid using the data to evaluate AI models without permission (section 2.5).
  - (d) The FRED DBAA series background carries a Moody's notice.

**Structure.**
- Each 2026 LLM question set holds 500 questions: 250 market and 250 dataset (`fb_qsets.py`).
- Market questions resolve when the market resolves.
- Dataset questions resolve at fixed horizons. The 2026-08-02 set uses 7, 30, 90 and 180 days and 1, 3, 5 and 10 years; the 2026-10-11 and 2026-10-25 sets use five horizons, 7 days to 1 year.
- Compared with the 2026-08-16 set, the 2026-10-11 set drops Manifold and Wikipedia and adds Kalshi and SerpAPI. INFER is absent from 2026-08-16 on.
- Some market questions carry the background "N/A". For example, the Kalshi question "More tech layoffs in 2026 than in 2025?" has resolution criteria that only point to the Kalshi URL.

**Fields.**
- Question sets: `id, source, question, resolution_criteria, background, market_info_open_datetime, market_info_close_datetime, market_info_resolution_criteria, url, freeze_datetime, freeze_datetime_value, freeze_datetime_value_explanation, source_intro, resolution_dates`.
- Resolution sets: `id, source, direction, resolution_date, resolved_to, resolved`.
- `freeze_datetime_value` is stored as a string.

**Publication.**
- Question sets appear every two weeks.
- Resolution sets are refreshed by roughly nightly commits, with gaps of up to 21 days (`github_commits_all.json`).
- The latest resolution date in the saved files is 29 Oct 2026.
- About 1,246 dataset instances scheduled for 31 Oct to 10 Nov were not yet published on 31 Oct.

**Counts.** These cover resolution dates 1 Jun to 10 Nov 2026, resolved, with an outcome of 0 or 1 (`fb_count.py`). Combination questions are excluded: 79,748 entries across all files are id-list combinations.

| Measure | Count |
|---|---|
| Market questions, unique (source, id) | **678** |
| of which Polymarket | 367 |
| of which Manifold | 126 |
| of which Metaculus | 92 |
| of which Kalshi | 87 |
| of which INFER | 6 |
| Market questions, by month of resolution | Jun 167, Jul 110, Aug 112, Sep 149, Oct 140 |
| Market questions resolved YES | 251 of 678 (Manifold 62/126, Metaculus 27/92, Polymarket 122/367, INFER 1/6, Kalshi 39/87) |
| Inconsistent resolution across sets | 0 |
| Dataset questions, unique series | 2,385 (ACLED 1,177, Yahoo Finance 547, Wikipedia 341, FRED 163, DBnomics 108, SerpAPI 49) |
| Dataset questions, unique (set, series) | 7,186 |
| Dataset questions, resolved instances | 11,726 (ACLED 2,355, Yahoo Finance 2,407, FRED 2,386, Wikipedia 2,305, DBnomics 2,224, SerpAPI 49) |
| All single-question instances by month | Jun 2,843, Jul 2,526, Aug 3,098, Sep 2,438, Oct 2,296 |

- **Question text on hand.** Of the 678 market questions, 335 have their text in the 8 downloaded sets (Polymarket 170, Manifold 80, Metaculus 70, Kalshi 9, INFER 6). The other 343 need the remaining 2026 and earlier question sets from the same repository; these were not downloaded.
- **Crowd baseline on those 335** (`fb_samples.py`). The Brier score of `freeze_datetime_value` against the outcome is **0.1002**. YES share 0.358. The SD of the per-question squared error is 0.168.
- **10 samples** are in `raw_sources/forecastbench/samples_in_window_market.json`. Examples:
  - INFER, JNIM in Bamako: 0.013, resolved 0.
  - Metaculus, Labour leadership election before 2027: 0.95, resolved 1.
  - Polymarket, Lindell in the Minnesota primary: 0.505, resolved 0.
  - Manifold, US government acquires 5% of Boeing: 0.045, resolved 0.

### 2.2 BTF-3 and BTF-2 (FutureSearch, Hugging Face)

**Where.**
- huggingface.co/datasets/BTF-2/BTF-3: created 2026-06-29, last modified 2026-09-20; config `binary`.
- huggingface.co/datasets/BTF-2/BTF-2.
- Counts come from datasets-server `/statistics` and `/rows` (`btf_stats_brief.py`).

**Licence.** `cc-by-nc-4.0` for both. The README says "CC-BY-NC-4.0 (research and academic use; commercial use requires permission)".

**BTF-3 binary.**
- **Rows.** 1,471 rows, all resolved: `resolution` is 0 or 1 with no missing values, and the YES share is 0.321.
- **In the window.** `expected_resolution_date` falls on or after 1 Jun 2026 for **1,355**: June 768 (608 of them on 1 Jun) and July 587 (all on 1 Jul). The other 116 fall in May 2026.
- **Information cutoff.** `date_cutoff_end` (the question's information cutoff) runs from 30 Apr to 30 May 2026. Models must therefore have training cutoffs before that date, question by question.
- **Forecast field.** `sota_forecast_probability` runs 0 to 100 and is missing for 89. The README describes it as "the prediction made by a proprietary forecasting system", so it is a model forecast, not a crowd. The README also has a revision history of re-cut questions.
- **Fields.** `question_id, question, resolution_criteria, background, present_date, date_cutoff_start, date_cutoff_end, expected_resolution_date, resolution, resolution_explanation, sota_forecast_probability, sota_summary_rationale`.
- **Other configs.** `numeric` holds 312 questions (the README labels it experimental). `scraped_pages` holds 6,225,647 rows. The README describes them as "question→page edges over 2,507,511 unique URLs" captured at forecast time, with columns `question_id, url, date_scraped`. It says page contents are not distributed, for copyright reasons. Only the URL index is shipped, so a frozen-retrieval condition would need the pages recovered from elsewhere.

**BTF-2.**
- 1,417 rows, YES share 0.273, all resolved by Dec 2025, so all fall **outside the window**.
- Fields as in BTF-3, plus `research_summary`, and without `date_cutoff_start`, `date_cutoff_end` and `expected_resolution_date`.
- It also has a `scraped_pages` config of 15,554,402 rows (483 MB parquet).

### 2.3 Polymarket

**Access.**
- Endpoint: gamma-api.polymarket.com `/events/pagination` with `closed=true` and `end_date_min` and `end_date_max` for one UTC day at a time. No key is needed.
- The API's `totalResults` is exact for a one-day window.
- Three days returned `totalResults` 2 with `hasMore` true (25 Jul, 12 Sep and 26 Sep, tier_one). The full pages for those days hold exactly 2 events each, so they are not capped (`pm_check_days.py`).
- Tag ids: Sports 1, Crypto 21, Esports 64, Recurring 101757.

**Closed events by end-date month.** Each column adds one filter to the column before it.

| Month | All closed events | Without sports, crypto and esports | And event volume of at least US$10k | And without the Recurring tag |
|---|---|---|---|---|
| Jun 2026 | 105,620 | 3,748 | 2,728 | 1,037 |
| Jul 2026 | 115,260 | 3,923 | 2,606 | 843 |
| Aug 2026 | 157,061 | 4,573 | 2,594 | 821 |
| Sep 2026 | 161,154 | 5,465 | 2,524 | 730 |
| Oct 2026 | 160,237 | 6,499 | 2,592 | 719 |
| **Total** | **699,332** | **24,208** | **13,044** | **4,150** |

The first three columns count events only. The markets inside them were not downloaded, so the number of resolved binary markets is not given for those columns.

**Markets inside the 4,150 last-column events** (`pm_count.py`).
- **Raw count.** The 4,150 events contain 51,733 markets, all with two outcomes and nearly all labelled Yes/No.
- **Qualifying.** 7,050 markets have Yes/No outcomes, are resolved (prices 1/0), have market volume above US$10k, and have both closedTime and endDate in the window.
  - By month: Jun 2,171, Jul 1,476, Aug 1,491, Sep 1,116, Oct 796.
  - YES share 0.29.
- **They are still repetitive.** The Recurring tag misses most repeating series. Top series among the 7,050:
  - elon-tweets 717
  - elon-tweets-48h 338
  - box-office-openings 271
  - spy-daily-close-uo 125
  - mrbeast-views-day-1 122
  - elon-tweet-daily 93
- **They are dependent.** 4,671 of the 7,050 are `negRisk` members of multi-outcome groups (candidate or bracket markets in one event). Only 2,163 distinct events are involved.

**Strict count** (`pm_strict.py`).
- **Method.** Drop events that belong to a series (1,222) and events carrying a template tag such as Tweet Markets, Finance Updown, Daily or Weekly (541, of which 505 are also series). Then keep one market per event.
- **Result.** **905 events**: Jun 243, Jul 83, Aug 165, Sep 176, Oct 238.
  - 126 of them are stand-alone binary events with no sibling markets.
  - Mostly elections and politics (690 tagged Politics).
- **Template filter is incomplete.** The excluded tag list missed the labels "Daily-Close" (it listed "Daily Close"), "Hit Price", "Equity Daily Pyth" and "Monthly". None of these is among the 20 most common tags in the strict set, but a few templated events may remain in the 905.
- **Selection bias.** Picking the highest-volume market per event gives a YES share of 0.526. Volume tracks the eventual winner, so the market chosen per event must be fixed by information available before the freeze date (for example volume or price at the freeze date), or chosen at random.

**Fields.**
- Market: `question, description, startDate, endDate, closedTime, closed, umaResolutionStatus, outcomes, outcomePrices, volumeNum, negRisk, clobTokenIds, resolutionSource, createdAt, slug`.
- Event: `title, description, tags, volume, seriesSlug, markets`.
- The description holds the resolution rules; all 7,050 have one of at least 50 characters. `resolutionSource` is non-empty for 4,049 of 7,050.
- closedTime falls after endDate for 2,649 of 7,050, so take the resolution date from closedTime or the UMA resolution, not from endDate.

**Price at a given date.**
- Endpoint: clob.polymarket.com/prices-history, no key.
- For market 524097 (Yes token), `interval=max&fidelity=1440` returned 28 daily points, 27 May to 23 Jun 2026.
- A request with an explicit start and end range returned an empty history in this probe.

**Terms of use: NOT VERIFIED.**
- On 31 Oct, polymarket.com/tos failed twice with plain curl (curl error 35, at the TLS handshake) and timed out once via WebFetch (ETIMEDOUT). The user agent was not spoofed.
- The API docs (llms.txt, gamma-openapi.yaml, market-data overview) contain no data-reuse terms.
- Until the terms are read, ship market ids plus the fetch scripts rather than the question text.

**10 samples.**
- `raw_sources/polymarket/samples_strict_markets.json` (strict set). Examples:
  - "Will Kim Kyung-soo win the 2026 Gyeongsangnam Province Gubernatorial Election?" resolved No.
  - "Trump endorses China's claim to Taiwan by end of summit?" resolved No.
- `samples_tier_one_markets.json` (before the strict filter).

### 2.4 Manifold

**Access.**
- Endpoint: api.manifold.markets `/v0/search-markets` with `filter=resolved&contractType=BINARY`. No key.
- `offset` is capped at 1,000, so markets were paged by `sort=newest` with `beforeTime` (`mf_fetch2.py`).
- A tail check used the resolve-date ordering (`mf_fetch.py`).

**Counts** (`mf_count.py`): resolution YES or NO (N/A and MKT excluded), `closeTime` 1 Jun to 31 Oct 2026.

| Measure | Count |
|---|---|
| With 20 or more unique traders | **1,111** |
| by close month | Jun 304, Jul 267, Aug 194, Sep 202, Oct 144 |
| YES share | 0.481 |
| Currency | All play money (token MANA) |
| With 10 or more unique traders | 2,411 |
| With 30 or more | 606 |
| With 50 or more | 265 |
| With 100 or more | 97 |

**Fields.** `id, question, description` (rich text) and `textDescription`, plus `createdTime, closeTime, resolutionTime, resolution, resolutionProbability, probability, uniqueBettorCount, volume, totalLiquidity, groupSlugs, url, mechanism, token`.
- Resolution criteria are whatever the creator wrote in the description.
- The probability at a set date has to be rebuilt from the bets endpoint, which was not tested here.

**Terms.**
- API docs (docs.manifold.markets/api): "Academic research, personal projects, and non-commercial use are permitted." The same passage bars training AI/ML models for commercial purposes without a data licence, and names data@manifold.markets for commercial licensing.
- Terms page: the licence is granted "solely for your personal, non-commercial use". Redistribution is not explicitly granted.
- Ship ids plus scripts, or ask Manifold.

**10 samples:** `raw_sources/manifold/samples/`.

### 2.5 Metaculus

**Access.** A token is required. Unauthenticated GET requests to `/api/posts/?limit=1`, with and without the resolved-binary filter, and to `/api2/questions/?limit=1` all returned 403. The headers are saved. The site is behind Cloudflare and was not bypassed.

**Terms.**
- The terms-of-use page source in Metaculus's GitHub repo ("Last Modified September 21, 2026") grants a personal, non-commercial licence and bars AI training without permission.
- `openapi.yml`: the data "may not be used to train, evaluate, or otherwise create or develop AI/ML models … without Metaculus's prior written permission".
- The same file lists access tiers: Restricted, Bot Benchmarking (about 250 resolved questions) and Unrestricted.

**Verdict.**
- Not usable without written permission.
- The restriction plausibly also covers the 92 Metaculus-sourced ForecastBench questions (586 remain without them).

### 2.6 What each licence allows in the replication package

| Source | Can ship question text and outcomes? | Effect on the package |
|---|---|---|
| ForecastBench | Yes, under CC BY-SA 4.0 | The derived question file must be CC BY-SA 4.0; credit FRI; exclude Metaculus-sourced items or get permission |
| BTF-3 | Yes, non-commercial (CC BY-NC 4.0) | The package becomes non-commercial; credit FutureSearch |
| Manifold | Not granted | Ship ids plus fetch script |
| Polymarket | Unknown (terms not read) | Ship ids plus fetch script until verified |
| Metaculus | No (written permission needed) | Exclude |

### 2.7 Sample size and smallest detectable difference

The smallest detectable gap in Brier score between two models scored on the same N questions (80% power, two-sided alpha 0.05) is about 2.8 × SD_d / √N. SD_d is the standard deviation of the per-question Brier difference between the two models.
- The only measured spread available is the crowd's own per-question squared error on 335 ForecastBench questions, which has SD 0.168.
- **Assumption, for illustration only.** If SD_d were also 0.168 (two models with that spread whose errors correlate at 0.5), the detectable gap would be:
  - 0.023 at N = 400
  - 0.018 at N = 678
  - 0.015 at N = 1,000
  - 0.010 at N = 2,000
- SD_d must be measured in the pilot and the design must state its own number.

---

## 3. Candidate models (Part B)

### 3.1 Table

**Sources.** Prices and flags come from openrouter.ai/api/v1/models (saved 31 Oct; `or_list.py`) and `/api/v1/models/{id}/endpoints` (`or_endpoints_brief.py`). Prices are US$ per million tokens.

**Column key.**
- "List" is the default OpenRouter listing price.
- "Cheaper route" is the OpenAI or Google `flex` endpoint, the OpenRouter `:batch` variant, or the cheapest endpoint with at least 90% uptime.
- "Reasoning default" uses OpenRouter's `reasoning.default_enabled`, or "mandatory" when `reasoning.mandatory` is true.
- "Cutoff" is quoted from the developer's own documentation (section 3.2). Anything else is "not stated".

| Developer | OpenRouter id | List in/out | Cheaper route | Context | Reasoning default | Off, low or minimal? | Temperature | Cache read (write) | Developer-stated cutoff |
|---|---|---|---|---|---|---|---|---|---|
| OpenAI | openai/gpt-5-nano | 0.05/0.40 | batch 0.025/0.20 | 400k | mandatory (medium) | minimal, low; cannot disable | no | 0.005 | May 31, 2024 |
| OpenAI | openai/gpt-5-mini | 0.25/2.00 | batch 0.125/1.00 | 400k | mandatory (medium) | minimal, low; cannot disable | no | 0.025 | May 31, 2024 |
| OpenAI | openai/gpt-oss-120b | 0.15/0.60 | cheapest endpoint 0.03/0.15 (fp4); batch 0.03/0.136 | 131k | mandatory (medium) | low; cannot disable | yes | 0.075 | Jun 01, 2024 |
| OpenAI | openai/gpt-5.4-nano | 0.20/1.25 | flex or batch 0.10/0.625 | 400k | flag false, effort medium | none, low | no | 0.02 | Aug 31, 2025 |
| OpenAI | openai/gpt-5.4-mini | 0.75/4.50 | flex or batch 0.375/2.25 | 400k | flag false, effort medium | none, low | no | 0.075 | Aug 31, 2025 |
| OpenAI | openai/gpt-5.6-luna | 0.20/1.20 | flex or batch 0.10/0.60 | 1.05M | on (medium) | none, low | no | 0.02 (0.25) | Feb 16, 2026 |
| OpenAI | openai/gpt-5.6-terra | 2.00/12.00 | flex or batch 1.00/6.00 | 1.05M | on (medium) | none, low | no | 0.20 (2.50) | Feb 16, 2026 |
| OpenAI | openai/gpt-6-luna | 0.10/0.50 | flex or batch 0.05/0.25 | 1.05M | on (medium) | none, low | no | 0.01 (0.125) | May 18, 2026 (borderline) |
| OpenAI | openai/gpt-6.1-terra | 1.00/5.00 | batch 0.50/2.50 | 1.05M | on (medium) | none, low | no | 0.05 (1.25) | Jun 01, 2026 (inside window: exclude) |
| OpenAI | openai/gpt-4.1-nano | 0.10/0.40 | batch 0.05/0.20 | 1.05M | no reasoning | n/a | yes | 0.03 | not checked (not in the saved OpenAI models index) |
| OpenAI | openai/gpt-4o-mini | 0.15/0.60 | batch 0.075/0.30 | 128k | no reasoning | n/a | yes | 0.075 | not checked (not in the saved OpenAI models index) |
| Google | google/gemini-2.5-flash-lite | 0.10/0.40 | flex 0.05/0.20 | 1.05M | not reported by OpenRouter | no effort levels listed | yes | 0.01 (0.083) | January 2025 |
| Google | google/gemini-2.5-flash | 0.30/2.50 | flex 0.15/1.25 | 1.05M | not reported | no effort levels listed | yes | 0.03 (0.083) | January 2025 |
| Google | google/gemini-3.1-flash-lite | 0.25/1.50 | flex or batch 0.125/0.75 | 1.05M | on (minimal) | none, minimal, low | yes | 0.025 (0.083) | not stated (see 3.2) |
| Google | google/gemini-3-flash-preview | 0.50/3.00 | flex or batch 0.25/1.50 | 1.05M | not reported (effort medium) | none, minimal, low | yes | 0.05 (0.083) | not stated (see 3.2) |
| Meta | meta-llama/llama-4-scout | 0.10/0.30 | (DeepInfra fp8, 328k ctx) | 1.31M | no reasoning | n/a | yes | none | August 2024 |
| Meta | meta-llama/llama-4-maverick | 0.188/0.652 | (listed price is DigitalOcean's, 128k ctx) | 524k | no reasoning | n/a | yes | 0.05 | August 2024 |
| Mistral | mistralai/mistral-small-3.2-24b-instruct | 0.075/0.20 | (DeepInfra fp8; Mistral EU 0.10/0.30 at 32k ctx) | 256k | no reasoning | n/a | yes | none | 2023-10-01 |
| Mistral | mistralai/mistral-small-2603 (Small 4) | 0.15/0.60 | | 262k | off | high or none | yes | 0.015 | November 1, 2024 |
| DeepSeek | deepseek/deepseek-v4.1-flash | 0.045/0.50 | batch 0.05/0.15; cheapest endpoint 0.014/0.144 (fp4) | 1.05M | on (high) | none, low | yes | 0.006 | not stated |
| DeepSeek | deepseek/deepseek-v4-flash | 0.091/0.182 | StreamLake 0.04/0.08 (fp8) | 1.05M | not reported (high) | none | yes | 0.018 | not stated |
| DeepSeek | deepseek/deepseek-v3.2 | 0.26/0.38 | GMICloud 0.21/0.31 (fp8) | 164k | off | no effort levels listed | yes | 0.13 | not stated |
| Qwen | qwen/qwen3.7-flash | 0.03/0.13 | | 1M | on | no effort levels listed | yes | 0.006 (0.038) | not stated |
| Qwen | qwen/qwen3-235b-a22b-2507 | 0.09/0.55 | | 262k | no reasoning | n/a | yes | none | not stated |
| xAI | x-ai/grok-4.20 | 1.25/2.50 | | 2M | off | no effort levels listed | yes | 0.20 | not stated |
| xAI | x-ai/grok-4.3 | 1.25/2.50 | batch 1.00/2.00 | 1M | on (low) | none, low | yes | 0.20 | not stated |
| xAI | x-ai/grok-4.7 | 2.00/6.00 | | 500k | mandatory (high) | low; cannot disable | yes | 0.50 | May 2026 (borderline) |
| Moonshot | moonshotai/kimi-k2.5 | 0.50/2.50 | AtlasCloud 0.49/2.50 (int4) | 262k | on | no effort levels listed | yes | 0.15 | not stated |
| Moonshot | moonshotai/kimi-k2-0905 | 0.60/2.50 | (Novita only) | 262k | no reasoning | n/a | yes | none | not stated |
| Z.ai | z-ai/glm-5.3-flash | 0.016/0.148 | (batch 0.05/0.18 is dearer than list) | 1.05M | mandatory (max) | low; cannot disable | yes | 0.016 | not stated |
| Z.ai | z-ai/glm-4.7-flash | 0.061/0.40 | (listed price is Cloudflare's, 131k ctx) | 200k | on | no effort levels listed | yes | none | not stated |
| Z.ai | z-ai/glm-4.5-air | 0.13/0.85 | | 131k | not reported | no effort levels listed | yes | 0.025 | not stated |

**Notes.**
- **Temperature.** OpenAI's GPT-5 family and later do not accept temperature on any endpoint, while gpt-oss and every other developer here do.
- **OpenRouter's own `knowledge_cutoff` field** exists for some models but is a third-party value and was not used. It sometimes differs from the developer's statement: Mistral Small 3.2 is listed as 2023-10-31 against the developer's 2023-10-01, and gpt-oss-120b as 2024-06-30 against the developer's Jun 01, 2024. It also gives a date for Qwen3-235B-2507 (2025-06-30), Kimi K2-0905 (2024-12-31), GLM-4.5-Air (2024-12-31) and Grok 4.20 (2025-09-01), where the developer docs checked state none.
- **Anomalous list prices, to check before use:**
  - kimi-k3 at 0.192/15
  - glm-5.2 at 0.006/6.8
  - glm-5.3-flash:batch priced above its sync price

### 3.2 Developer-stated training cutoffs (URL and quoted line)

**OpenAI** (developers.openai.com/api/docs/models/<id>; the line reads "<date> knowledge cutoff"):

| Model | Quoted line |
|---|---|
| gpt-5-nano | "May 31, 2024 knowledge cutoff" |
| gpt-5-mini | "May 31, 2024 knowledge cutoff" |
| gpt-oss-120b | "Jun 01, 2024 knowledge cutoff" (the HF chat template, huggingface.co/openai/gpt-oss-120b, also says "Knowledge cutoff: 2024-06") |
| gpt-5.4-nano, gpt-5.4-mini | "Aug 31, 2025 knowledge cutoff" |
| gpt-5.6-luna, gpt-5.6-terra | "Feb 16, 2026 knowledge cutoff" |
| gpt-6-luna | "May 18, 2026 knowledge cutoff" |
| gpt-6.1-terra | "Jun 01, 2026 knowledge cutoff" |

The models index also shows gpt-6-astra and gpt-6.1-sol at Apr 30, 2026.

**Google.**
- ai.google.dev/gemini-api/docs/models/gemini-2.5-flash-lite and .../gemini-2.5-flash: table row "Knowledge cutoff | January 2025".
- Gemini 3 Flash and Gemini 3.1 Flash-Lite: **not stated**. The checked pages were the ai.google.dev model pages, the Google Cloud pages (docs.cloud.google.com/gemini-enterprise-agent-platform/models/gemini/3-flash and .../3-1-flash-lite), and the DeepMind model cards (storage.googleapis.com/deepmind-media/Model-Cards/Gemini-3-Flash-Model-Card.pdf; deepmind.google/models/model-cards/gemini-3-1-flash-lite/).
- Both cards say the model is based on Gemini 3 Pro. The Gemini 3 Pro card (storage.googleapis.com/deepmind-media/Model-Cards/Gemini-3-Pro-Model-Card.pdf) says "The knowledge cutoff date for Gemini 3 Pro was January 2025." Applying that date to Flash would be an inference, not a statement.

**Meta.** raw.githubusercontent.com/meta-llama/llama-models/main/models/llama4/MODEL_CARD.md: "The pretraining data has a cutoff of August 2024" (Scout and Maverick).

**Mistral.**
- huggingface.co/mistralai/Mistral-Small-3.2-24B-Instruct-2506, SYSTEM_PROMPT.txt: "Your knowledge base was last updated on 2023-10-01."
- huggingface.co/mistralai/Mistral-Small-4-119B-2603, SYSTEM_PROMPT.txt: "Your knowledge base was last updated on Friday, November 1, 2024."
- Both are the developer's own files, but they are system prompts, not model cards.

**xAI.**
- docs.x.ai/developers/models: "The knowledge cut-off date of Grok 4.7 is May 2026."
- Grok 4.3 and Grok 4.20: **not stated** (docs.x.ai/developers/models/grok-4.3 and /grok-4.20).

**Not stated in any document checked:**
- DeepSeek:
  - HF READMEs: DeepSeek-V3.2, V4-Flash, V4.1-Flash
  - api-docs.deepseek.com: quick_start/pricing and news 251201, 260424, 260910
- Qwen: HF Qwen3-235B-A22B-Instruct-2507 README; Alibaba Model Studio models page.
- Moonshot: HF Kimi-K2-Instruct-0905 README, Kimi-K2.5 README and chat template; platform docs (platform.kimi.ai/docs/introduction).
- Z.ai: HF GLM-4.5-Air, GLM-4.7-Flash and GLM-5.3-Flash READMEs; docs.z.ai/guides/llm/glm-4.7.

### 3.3 Prices, batch and caching (corrections)

- **The memory note "OpenRouter has no batch discount" is wrong.**
  - OpenRouter has a Batch API (`openrouter_docs/batch_api_overview.md`) priced at "Typically 50% of the sync per-token price", with results "Within 24 hours on most providers".
  - The model list carries `:batch` variants. For example, gpt-5-nano:batch costs 0.025/0.20 against 0.05/0.40 sync, and gpt-oss-120b:batch 0.03/0.136.
  - OpenAI and Google AI Studio also expose half-price `flex` endpoints.
- **OpenAI cache writes are charged from GPT-5.6 on.** OpenRouter's prompt-caching doc says: "GPT-5.6 and later charge cache writes at 1.25x the price of the original input pricing, even with automatic caching". Earlier models have "no cost" cache writes.
- **Mandatory reasoning raises the real cost.** gpt-5-nano, gpt-5-mini, gpt-oss-120b, Grok 4.7 and GLM-5.3-Flash always produce billed reasoning tokens, so their real output cost is above the list output price. Budget for this from the pilot.

### 3.4 Five cheapest suitable models

**Rule.** "Suitable" means a developer-stated cutoff before 1 Jun 2026. The plan replaced this rule with Rule R (PLAN Section 5.1).

**Ranking.** Models are ranked by the list price of a typical request with 1,500 input and 500 output tokens (cost per 1,000 requests in brackets; reasoning tokens not included).

| Rank | Model | List in/out | Cost per 1,000 requests | Cheaper route | Developer-stated cutoff |
|---|---|---|---|---|---|
| 1 | Mistral Small 3.2 24B | 0.075/0.20 | US$0.21 | none | 2023-10-01 |
| 2 | GPT-5 nano | 0.05/0.40 | US$0.28, plus mandatory reasoning | batch 0.025/0.20 | May 31, 2024 |
| 3 | Llama 4 Scout | 0.10/0.30 | US$0.30 | none | August 2024 |
| 4 | Gemini 2.5 Flash-Lite | 0.10/0.40 | US$0.35 | flex 0.05/0.20 | January 2025 |
| 5 | GPT-6 luna | 0.10/0.50 | US$0.40 | flex or batch 0.05/0.25 | May 18, 2026; only 14 days before the window |

**Next in line**, if GPT-6 luna is dropped:
- gpt-oss-120b, 0.15/0.60 (Jun 01, 2024; cheapest endpoint 0.03/0.15)
- Mistral Small 4 (2603), 0.15/0.60 (November 1, 2024)
- GPT-5.4 nano, 0.20/1.25 (Aug 31, 2025; flex 0.10/0.625)

**Excluded for lack of a stated cutoff.** The cheapest Qwen, DeepSeek, GLM and Kimi models (for example qwen3.7-flash at 0.03/0.13, glm-5.3-flash at 0.016/0.148 and deepseek-v4.1-flash at 0.045/0.50) have no stated cutoff. Without one, no developer document shows that their training data ends before the window, so they are excluded.

**Not checked.** gpt-4.1-nano (0.10/0.40, batch 0.05/0.20) and gpt-4o-mini (0.15/0.60, batch 0.075/0.30) are cheap, take temperature and do not reason. Their developer cutoffs were not checked because neither appears in the saved OpenAI models index. OpenRouter's third-party field gives 2024-06-30 and 2023-10-31.

**Developer spread.** Only four developers (OpenAI, Google, Meta and Mistral) offer a model whose stated cutoff falls safely before the window. xAI's only stated cutoff (Grok 4.7, May 2026) is borderline and costs 2.00/6.00.

**Design confound.** The stated cutoffs run from Oct 2023 to May 2026. Without supplied background or news, models with old cutoffs lack basic facts about mid-2026, such as who is standing in an election. The design must either give every model the same dated background or analyse results by cutoff.

---

## 4. Flags for the design

1. **Window.** End it on 31 Oct 2026. ForecastBench resolutions after 29 Oct are not yet public, and its commit gaps reach 21 days.
2. **Metaculus.** Exclude it as a direct source. Exclude or seek permission for the 92 Metaculus-sourced ForecastBench questions.
3. **Licences.** ForecastBench's ShareAlike and BTF-3's non-commercial term cannot both govern one merged file. Choose one source as the backbone, or ship the BTF-3 part as ids.
4. **Polymarket terms are unread.** Verify them from another network before redistributing any Polymarket text.
5. **Dependence.** Polymarket negRisk siblings, Manifold or Polymarket duplicates of ForecastBench items, and ForecastBench dataset questions (several horizons and several sets per series) are not independent. Count questions at the level of the unique series or event.
6. **Selection.** Pick questions and markets using only information from before the freeze date. Choosing by final volume biases the sample towards YES (0.526 against 0.29).
7. **Cutoffs.**
   - Exclude GPT-6.1 terra (Jun 01, 2026).
   - Treat GPT-6 luna (May 18, 2026) and Grok 4.7 (May 2026) as borderline.
   - For BTF-3, keep only models whose cutoff predates each question's `date_cutoff_end` (30 Apr to 30 May 2026).
8. **Power.** State the smallest detectable Brier difference (section 2.7), given the brief's note that more than 1,000 questions are needed to separate models.

---

## 5. Methods: scripts and raw files

**How to run.** All scripts are in `design/notes/scripts/` and are run as `python3 -I <script> <args>`. Raw responses are treated as untrusted data and parsed as JSON or text only.

| Script | What it does | Raw input or output |
|---|---|---|
| fb_qsets.py | Questions per ForecastBench set, by source and horizon | raw_sources/forecastbench/question_sets/ |
| fb_count.py `<res_dir> 2026-06-01 2026-11-10` | Counts resolved single questions in the window, market and dataset, by source and month | raw_sources/forecastbench/resolution_sets/ (39 files) |
| fb_samples.py `<q_dir> <res_dir> 2026-06-01 2026-11-10 10 <out>` | Joins question and resolution sets; crowd Brier and SD; 10 seeded samples | samples_in_window_market.json |
| btf_stats_brief.py `<stats_json> <cols>` | Summarises HF datasets-server statistics | raw_sources/btf2/dsserver_stats_*.json |
| pm_fetch.py `<out> 2026-06-01 2026-10-31` | Gamma `/events/pagination` per day at four filter tiers; full pages for the last tier | raw_sources/polymarket/daily_counts/ (612 files), tier_one_events/ (159 files), fetch_log.txt, daily_counts_summary.json |
| pm_count.py `<pm_dir> 2026-06-01 2026-10-31 10` | Monthly event counts per tier; market filter; repetition diagnostics | tier_one_market_ids.json, samples_tier_one_markets.json |
| pm_strict.py `<pm_dir> 2026-06-01 2026-10-31 10` | Drops series and template events; one market per event | strict_market_ids.json, samples_strict_markets.json |
| pm_check_days.py | Checks the three days flagged as possibly capped; summarises the saved CLOB price histories | clob_prices_history_524097_*.json |
| mf_fetch.py, mf_fetch2.py, mf_count.py | Manifold paging (resolve-date order, then newest with beforeTime) and counts | raw_sources/manifold/ (pages, qualifying_ids.json with 1,111 ids, samples/) |
| or_list.py `<models_json> <authors>` | OpenRouter list prices and reasoning flags | openrouter_models_2026-10-31.json |
| or_endpoints.py, or_endpoints_brief.py `<dir>` | Per-endpoint prices, temperature support, cache prices and quantisation | raw_sources/openrouter_endpoints/ (26 files) |
| html_ctx.py, pdf_text_min.py | Plain-text context around a pattern in saved HTML or PDF (the PDF tool uses only the standard library, zlib; no command-line PDF tools such as pdftotext, mutool or qpdf are installed) | raw_sources/model_docs/ |
| keys_dump.py | Prints field names only | any saved JSON |

**Other saved evidence.**
- raw_sources/metaculus/: 403 responses with headers, terms-of-use page source, openapi.yml.
- raw_sources/manifold/: docs_manifold_api.html, terms_page.html.
- raw_sources/forecastbench/: README.md, LICENSE, site HTML.
- raw_sources/btf2/: hf_README_*.md.
- raw_sources/openrouter_docs/: batch, caching and reasoning docs.
- raw_sources/polymarket/tos_NOT_VERIFIED.txt.
