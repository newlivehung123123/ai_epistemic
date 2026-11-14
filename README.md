# Track 1 evaluation pipeline

This folder holds the design, code and data of a Track 1 project of the AI x Epistemics Research Sprint (Apart Research, 13 to 15 November 2026), which is also written up as an ACL 2027 long paper. The design is in `design/PLAN.md`, and every section number below refers to that plan.

## Folders

**Folders of the project.**

| Folder | Contents |
|---|---|
| `design/` | `PLAN.md`, the cost model `cost_model.py`, and the notes and saved sources behind each decision of the plan |
| `pipeline/` | The code. `fetch_items.py` builds the item sets and `run.py` sends the requests and collects the replies |
| `pipeline/clients/` | One client each for Anthropic, OpenRouter and Hugging Face, and the stub that makes up replies |
| `tests/` | Tests on made-up replies, with every HTTP request sent to a mock transport |
| `data/raw/` | Polymarket events and prices as fetched, with only the fields the item rule needs |
| `data/items/` | The item file of each set, the selection log and the decisions made by hand |
| `data/outcomes/` | Fields withheld from the scored sets (outcome prices, resolution status, volumes), written without being displayed |
| `data/runs/` | One folder per run, with request files, results, batch records and price records |
| `data/release/` | The item ID, market ID, condition ID, Yes token and price at the forecast date of each pilot, retro and prospective item, for the public repository |
| `paper/` | The LaTeX source of the paper, the table and figure scripts in `paper/scripts/`, and the Google Docs copy of the paper |

**Reading the table.** Each row names a folder and what the folder holds. Code stays in `pipeline/` and data stays in `data/`. No file in `data/outcomes/` is displayed, and the retro outcome file is opened only at scoring, after the freeze (Section 12.1).

## Set-up

The code runs on Python 3.13 with httpx 0.28.1 and anthropic 0.85.0, and the tests use pytest 8.3.4. The Anthropic client refuses any other SDK version, because Section 5.7 logs the SDK version with each request. Every script runs with `python3 -I`, which keeps the current folder off the import path.

A paid send needs three keys in a file named `.env` in this folder, one per line.

```text
ANTHROPIC_API_KEY=...
OPENROUTER_API_KEY=...
HF_TOKEN=...
```

A key exported in the shell is used in place of the line in `.env`. The code reads a key only when it builds a client for a real request, and never prints a key or writes one to a log or a file (Section 12.2). The Hugging Face token needs inference permission only (Section 5.4). The `.gitignore` of this folder keeps `.env` out of every commit.

## Tests

```bash
python3 -I -m pytest tests -q -p no:cacheprovider
```

The tests cost nothing and need no key. They check the prompt texts word for word against the text blocks of Section 4, the parser, the request counts of each run, the request bodies and error handling of the three clients, the price records read from the listings saved on 6 and 7 November 2026, and every command of `run.py` from prepare to summary on made-up replies.

## Item sets

`pipeline/fetch_items.py` builds each set from free public Polymarket reads, one stage at a time (Section 3.3). No stage needs a key.

```bash
python3 -I pipeline/fetch_items.py pilot fetch
python3 -I pipeline/fetch_items.py pilot price
python3 -I pipeline/fetch_items.py pilot review
python3 -I pipeline/fetch_items.py pilot select
python3 -I pipeline/fetch_items.py pilot trades
```

`fetch` lists the events whose scheduled end date falls in W, `price` reads the hourly Yes price at F of each eligible market, and `review` prints the counts and the decisions to make by hand. Those decisions go in `data/items/pilot_by_hand.json` before `select` writes `data/items/pilot_items.json`. `trades` counts the trades before F of five pilot markets. The retro and prospective sets run the same stages with `retro` or `prospective` in place of `pilot`, and each set excludes the events of the sets selected before it (Section 3.2). No stage prints an outcome, a price after F or a withheld field.

The retro set was fetched on 11 November 2026 at 14:30 UTC. Its withheld fields are in `data/outcomes/retro_withheld_fields.json.gz` and its deleted paragraphs in `data/outcomes/retro_deleted_paragraphs.json`, and neither file is opened before scoring. The decisions made by hand are in `data/items/retro_by_hand.json`, and the 400 retro items are in `data/items/retro_items.json`. The items were selected again offline at 15:49 UTC the same day under the mirror rule of Section 6.8, with the same 400 items, and every file that `select` replaced is kept beside the new file with `_superseded_20261111T154959` in its name.

## Runs

`pipeline/run.py` sends the requests of a run and collects the replies (Sections 5.2 to 5.7 and 10). The four runs are `pilot`, `pilot_batch_test`, `pilot_wording` (the re-check of the turn-2 wording, Section 10.4) and `sprint`, and each command names the run with `--run`.

**Commands of `run.py`.**

| Command | What the command does | Costs money | Reads a key |
|---|---|---|---|
| `prepare` | Writes the request file of one round. Round 2 also reads the turn-1 results | No | No |
| `send` | Prints the plan and the worst-case cost from the cost model, and sends nothing | No | No |
| `send --yes` | Sends every prepared request that has no result yet, batches first and sync requests after | Yes | Yes |
| `send --dry-run` | Writes the request bodies to `dryrun/` and sends nothing | No | No |
| `collect` | Downloads the results of open batches. With `--wait` it polls once a minute until every batch ends | No | Yes |
| `status` | Counts requests, results, errors and open batches from the files | No | No |
| `cancel` | Cancels an open Anthropic batch | No | Yes |
| `batches` | Lists the provider's recent batches and the submission each batch belongs to | No | Yes |
| `adopt` | Ties a batch to a submission whose create request ended without a reply | No | Yes |
| `release` | Gives up a submission, so that its requests can be sent again | No | No |
| `summary` | Writes statistics per setting to `summary.json` | No | No |

**Reading the table.** A "Yes" under "Costs money" spends credit at Anthropic, OpenRouter or Hugging Face. A "Yes" under "Reads a key" means the command reads `.env` and contacts the provider. Adding `--stub` to any command replaces every reply with a made-up one, touches no network, needs no key and writes to `data/runs/{run}-stub`, so a stub run never mixes with a real run. `--setting NAME`, repeatable, limits a command to some settings.

**Safeguards.** A paid send needs `--spend-cap` in US$, and sends nothing when the worst case of the plan exceeds the cap. The worst case counts one input token per three characters and the full output cap of every request. The plan printed without `--yes` uses the prices of the cost model, and a send with `--yes` uses the provider's listing of that day. Each sync request reserves its worst case before it goes, so the sync requests also end when the cap is reached. A request in an open batch is sent again only with `--include-in-flight`, and a request whose only results are errors is sent again only with `--retry-failed`. When a batch create request ends without a reply, the send stops with exit code 4 and names the next step, which is `batches` to look for the batch, then `adopt` if the provider made the batch or `release` if the provider did not. Commands that write to a run folder take a lock, so two such commands never work on one folder at the same time.

**Files of a run folder.**

| File | Contents |
|---|---|
| `requests/{setting}-r1.jsonl`, `requests/{setting}-r2.jsonl` | The prepared requests of each round |
| `requests/{setting}-r2-not_sent.jsonl` | Turn-2 requests not sent because turn 1 has no parsed reply (Section 4.3) |
| `results/{setting}.jsonl` | One line per result, with the fields of Section 5.7, the raw reply, the parsed fields and the parse status |
| `manifest.jsonl` | Every batch submission, adoption, release, closing and cancel request, in time order |
| `batches/` | The request IDs of each submission and the latest record of each batch from the provider |
| `prices/` | The price record of each setting and route at each send, with the provider's listing of that day |
| `dryrun/` | The request bodies of a dry run |
| `summary.json` | Results, errors, costs, token totals, parse statuses, serving providers and replies with thinking, per setting |

**Reading the table.** The left column gives the path inside `data/runs/{run}`, and the right column what the file records. A result line is never rewritten. A request sent twice has two result lines, and the analysis uses the first result that is not an error.

## Pilot

Jason Hung runs every paid step. The pilot uses the 50 items of `data/items/pilot_items.json` and follows Section 10. Every Anthropic request goes in a batch, every OpenRouter and Hugging Face request is a sync request, and the OpenRouter test batch sends 10 turn-1 requests each to gpt-6-luna and deepseek-v4.1-flash (Section 10.1).

1. Write `.env` as described under Set-up.
2. Prepare round 1, which is free.

```bash
python3 -I pipeline/run.py prepare --run pilot --round 1
```

3. Print the plan and the worst case, which is free.

```bash
python3 -I pipeline/run.py send --run pilot --round 1
```

4. Send round 1, which is paid. The cap of US$4 sits above the worst case that step 3 prints (US$0.68 at the prices of the cost model on 7 November 2026), and the same cap serves round 2 in step 8.

```bash
python3 -I pipeline/run.py send --run pilot --round 1 --yes --spend-cap 4
```

5. Prepare and send the OpenRouter test batch, which is paid at about US$0.003.

```bash
python3 -I pipeline/run.py prepare --run pilot_batch_test --round 1
```

```bash
python3 -I pipeline/run.py send --run pilot_batch_test --round 1 --yes --spend-cap 0.05
```

6. Download the batch results, which is free and reads the key.

```bash
python3 -I pipeline/run.py collect --run pilot --wait
```

```bash
python3 -I pipeline/run.py collect --run pilot_batch_test --wait
```

7. Prepare round 2 and print its plan, which is free.

```bash
python3 -I pipeline/run.py prepare --run pilot --round 2
```

```bash
python3 -I pipeline/run.py send --run pilot --round 2
```

8. Send round 2, which is paid.

```bash
python3 -I pipeline/run.py send --run pilot --round 2 --yes --spend-cap 4
```

9. Download the round-2 batch results, then write the summary, both free.

```bash
python3 -I pipeline/run.py collect --run pilot --wait
```

```bash
python3 -I pipeline/run.py summary --run pilot
```

10. Write the pilot checks of Section 10.3, which is free and needs no key. The report prints each rule with the decision it asks for and writes `data/runs/pilot/pilot_report.json`. Every figure is a pilot check, not a result, and none goes into the paper. Rule 2 compares the sprint cost with the Section 11 credit less the pilot spend. After a top-up, add `--balance-anthropic`, `--balance-openrouter` or `--balance-huggingface` with the balance in US dollars that the account page shows.

```bash
python3 -I pipeline/pilot_report.py
```

11. Send the re-check of the turn-2 wording of 8 November 2026 (Section 10.4). The run `pilot_wording` sends turn 2 only, six arms on 10 pilot items for each of 11 settings, 660 requests in all, and replays the turn-1 replies of the pilot run. Prepare the request files, which is free and was done on 8 November 2026.

```bash
python3 -I pipeline/run.py prepare --run pilot_wording --round 2
```

Print the plan and the worst case, which is free.

```bash
python3 -I pipeline/run.py send --run pilot_wording --round 2
```

Send the run, which is paid. The cap of US$1 sits above the worst case that the plan prints (US$0.60 at the prices of the cost model on 8 November 2026). Anthropic requests go in batches, and OpenRouter and Hugging Face requests are sync requests.

```bash
python3 -I pipeline/run.py send --run pilot_wording --round 2 --yes --spend-cap 1
```

On 11 November 2026 every request of the two HF settings failed to connect, at no cost, and the HF client now connects over IPv4 only (Section 5.4). Send those 120 requests again, which is paid at a worst case of US$0.06. A request whose only results are errors goes again only with `--retry-failed`.

```bash
python3 -I pipeline/run.py send --run pilot_wording --round 2 --setting gpt_oss_120b --setting llama4_scout --retry-failed --yes --spend-cap 1
```

That resend returned all 60 replies of llama-4-scout and 53 replies of gpt-oss-120b, and 7 requests of gpt-oss-120b ended in HF errors (HTTP 503 and 429). Send those 7 requests again, which is paid at a worst case of US$0.0049.

```bash
python3 -I pipeline/run.py send --run pilot_wording --round 2 --setting gpt_oss_120b --retry-failed --yes --spend-cap 1
```

That second resend, on 11 November 2026, returned all 7 replies at US$0.0003, so all 60 replies of gpt-oss-120b parsed.

Download the Anthropic batch results, which is free and reads the key.

```bash
python3 -I pipeline/run.py collect --run pilot_wording --wait
```

Write the pilot checks again, which is free and needs no key. Rule 1 prints the status of the re-check (passed, decided, flagged or incomplete), and rule 2 subtracts the spend of the re-check from the credit on hand.

```bash
python3 -I pipeline/pilot_report.py
```

`status` shows the progress of a run at any point without the network.

```bash
python3 -I pipeline/run.py status --run pilot
```

## Sprint run

The sprint run of 13 November 2026 uses the retro and prospective sets with `--run sprint` and follows the steps of the pilot after the freeze (Section 12.1). Anthropic requests go in batches, and every OpenRouter and Hugging Face request is a sync request (Section 5.3, decided 8 November 2026).

Round 1 and round 2 of the sprint run were sent on 13 November 2026 between 05:46 and 09:05 UTC, in 67,182 requests that cost US$14.57 in all. The describe stage of the analysis needs no key and opens no file in `data/outcomes/`.

```bash
python3 -I pipeline/analysis.py describe --run sprint
```

The retro outcomes were opened on 13 November 2026, one day before the date in PLAN Section 12.1, and the departure is logged in PLAN Section 16. `pipeline/score_departure.py` checks the README hashes of the two retro outcome files and of `analysis.py` before any outcome file is opened, runs the score stage of `analysis.py` with the retro opening date moved to 13 November 2026, and writes the real opening time to `data/runs/sprint/departure_retro_opening.json`.

```bash
python3 -I pipeline/score_departure.py
```

The prospective outcomes are opened from 16 December 2026. The table and figure scripts read only the aggregate files `data/runs/sprint/analysis_describe.json` and `data/runs/sprint/analysis_score.json`, and write `paper/tables/` and `paper/figures/`.

```bash
python3 -I paper/scripts/tables.py
python3 -I paper/scripts/figures.py
```

The paper compiles with tectonic in `paper/`. `paper/scripts/build_docx.py` then writes the Google Docs copy `paper/paper_for_google_docs.docx` from `paper/paper.tex`, the table files and the numbers in `paper/paper.aux`, with pandoc 2.12 and citeproc, and keeps intermediate files in `paper/docx_build/` unless another folder is given.

```bash
cd paper && tectonic -X compile --keep-intermediates paper.tex && cd ..
python3 -I paper/scripts/build_docx.py
```

## Public release

The public repository at https://github.com/newlivehung123123/ai_epistemic holds the plan, the code, the tests, the replies and parsed fields of every run, the price and batch records, the aggregate results and the paper, following PLAN Section 12.3. Polymarket's terms of use had not been read when the public repository was made (PLAN Section 3.6), so the public repository leaves out the files built from Polymarket text, namely `data/raw/`, `data/items/`, the request files in `data/runs/*/requests/` and the saved Polymarket data in `design/notes/`. `data/release/` holds the item ID, market ID, condition ID, Yes token and price at the forecast date of every pilot, retro and prospective item in place of the item files, and `pipeline/fetch_items.py` is the script that built the item files from the Polymarket API. The outcome files in `data/outcomes/` are left out of the public repository, and the prospective outcomes and scores will be released with the ARR paper. Copies of third-party papers and web pages saved in `design/notes/` and `reading/` are left out of the public repository as well.

## Freeze hashes

The SHA-256 hashes of the plan, `cost_model.py`, the pipeline and analysis code, the retro and prospective item files and the prompt templates are recorded here before the sprint run of 13 November 2026 (Section 12.1). The two retro outcome files were hashed on 11 November 2026, and the other hashes were recorded at the freeze of 13 November 2026, with the time each file was last written. The offline re-selection of 11 November 2026 at 15:49 UTC wrote the deleted-paragraphs file again with the same paragraphs and a new creation time, so its hash changed from `1de2b031a4a82e3ef5f0bef93587087f66a7ee87160743e73e64e681fe1a40c5` (written at 15:03 UTC), and the copy of 15:03 UTC is kept as `data/outcomes/retro_deleted_paragraphs_superseded_20261111T154959.json`. The prompt templates are the texts in `pipeline/prompts.py`, whose hash is in the table, and `prompts.template_hashes()` writes the hash of each text into every run log. Jason Hung accepted the prospective grouping and the other 19 rows of PLAN Section 15 with the PROPOSED label on 13 November 2026. Only the plan changed after that acceptance, so the plan row gives the hash of the accepted plan, and the plan hashed at 05:36 UTC, before the acceptance, had the hash `fd0f965c120f2f0dd25f0ddf261fa55060ff14c886fab85940d2938bcb7958a3`. After the freeze the plan changed once, by the row of Section 16 dated 13 November 2026 that logs the opening of the retro outcomes one day before the frozen date, so `design/PLAN.md` no longer has the plan hash in the table. The frozen plan is kept unchanged as `design/PLAN_frozen_20261113.md`, whose SHA-256 is the plan hash in the table. `pipeline/score_departure.py`, written for that departure after the freeze, is not in the table and changes no hashed file.

| File | Written (UTC) | SHA-256 |
|---|---|---|
| `data/outcomes/retro_withheld_fields.json.gz` | 11 November 2026 14:30 | `25802e403166756fec32c1003fab33ceb486fdb9d417cab16ce23569db36d93f` |
| `data/outcomes/retro_deleted_paragraphs.json` | 11 November 2026 15:49 | `2a94671ffe4cb0143eeccda0e93ac41e6dcf2e8ec3f065a9b11dd0861197f4f7` |
| `design/PLAN.md` | 13 November 2026 05:42 | `e147618c517c430bbeef8dbb3b53c59fa68e9ff3d1ee0cb56473c09e0959e34e` |
| `design/cost_model.py` | 8 November 2026 01:40 | `54c5cbb88334a7c0e34786658a28525e7aa298602006a11f02e8806f92e3e96e` |
| `pipeline/__init__.py` | 7 November 2026 00:14 | `c0cdbe12dff8733273d63641bf92bb5acdbbe21e897018cfd33e4368a62e7e20` |
| `pipeline/analysis.py` | 13 November 2026 01:25 | `adde4e798def8cccbd1e41ecb1f4ed69520655db88899ee471e434fe3b6548b3` |
| `pipeline/build.py` | 8 November 2026 01:29 | `b11644c86cb7aefcec1a4dabc1413b0a8a88f7c144d264ef56e81604f71a7055` |
| `pipeline/config.py` | 11 November 2026 15:45 | `d4924560f8cb3debc66025a700a6013351e95f93c30a95f70ea94073c983d1a5` |
| `pipeline/families.py` | 11 November 2026 14:47 | `b87886a99975494f0542a605542da4e4b08fe092a86730d33dcc24b5216d676c` |
| `pipeline/fetch_items.py` | 11 November 2026 15:46 | `9d9b2fe996aa9760548d7143c15e092fef303c78ca3ae01ce76749ef61557e68` |
| `pipeline/items.py` | 11 November 2026 15:46 | `0fb1a638e25aeb967f067ffa35ce4e58a04219ac0a2be831a4327b3f3b200b45` |
| `pipeline/keys.py` | 7 November 2026 05:59 | `232be2c12015d40d7ece5e31ba41f086dde146bc0a6dd259f544feb1dabf4bf5` |
| `pipeline/parse.py` | 11 November 2026 15:34 | `4d4467581c7113bed901648bd212f95b03528a4e3f6f32e86fa48ee7bc6be560` |
| `pipeline/pilot_report.py` | 11 November 2026 15:49 | `29f478330712fe170146e1f3e66b7527f240d9152310a6cc79cfc7aec551a3b1` |
| `pipeline/polymarket.py` | 7 November 2026 15:12 | `d0cde98d4979296bdce17839c2ab9e3517560bf4c2901dcba4807882bb8c4fc1` |
| `pipeline/pricing.py` | 7 November 2026 09:04 | `64d6d3a73ededefed3f6a0cb48d65f0a47b60029faeff00fb69da898792e123e` |
| `pipeline/prompts.py` | 8 November 2026 01:24 | `b02ff7b9810f7704c4f6a6eaa4bd5622d03ce0c4cc1423613aa607d3128f3128` |
| `pipeline/run.py` | 8 November 2026 01:31 | `33a979a8a34506e88b8f45973b51172e1e34bd590906ef4ed298e8f374024556` |
| `pipeline/settings.py` | 8 November 2026 01:24 | `d7d7528353f30f4bf9e669f594b59d01a0a022cf84a28400dcbf7d7a74b83f2f` |
| `pipeline/util.py` | 7 November 2026 05:03 | `400dcee0266b09a4a61213a084871183e6fc11d124bb786600c300f6c95ae04f` |
| `pipeline/clients/__init__.py` | 7 November 2026 05:59 | `0209c94b55b2e20a7d8b4a1002a795f43ba51472708719ad3ec1b52cf8e2aeef` |
| `pipeline/clients/anthropic_client.py` | 7 November 2026 08:47 | `6247cb6044dc42f4cf790255b722c7a74b61541443951a8b4bc020f599fa9e4d` |
| `pipeline/clients/common.py` | 11 November 2026 14:05 | `45075e23f3f0412bcc280f3f22625af9cf4e5b90ef98ba327294bc16282af9de` |
| `pipeline/clients/hf_client.py` | 11 November 2026 14:05 | `98ab991d05d872bc60985020974ad92af96b7a30283792a09a98dddc747f3e88` |
| `pipeline/clients/openrouter_client.py` | 7 November 2026 08:47 | `d9f7f406b0f6f5312022a6460fd45ec80b7924cc778b3b2e645858e620d3fbc0` |
| `pipeline/clients/stub.py` | 7 November 2026 08:47 | `e7e6a79a0a54b6631130306fa5763dc92cf81d3bd6e7fe199c47b34ec651fc5e` |
| Prompt templates, `prompts.template_hashes()["ALL"]` | 8 November 2026 01:24 | `c51ad3b3cf6c9d0250b99e6e0b2881c0afbbce9f78e730afe2d01d126be43a2b` |
| `data/items/retro_items.json` | 11 November 2026 15:49 | `8c6b7800292cf1095db9412465ef930c2e4a938eb670d6f99659dffe5e70093b` |
| `data/items/retro_by_hand.json` | 11 November 2026 15:03 | `fa816a0dcf74ffecd2cc0b1fe8369c0c8831d661dfe23946946b78d25caea4d9` |
| `data/items/prospective_items.json` | 13 November 2026 01:36 | `463c0ab7cb06930529454b5f26c11c86ad96981908d8f7b87a33133257d87f0d` |
| `data/items/prospective_by_hand.json` | 13 November 2026 01:36 | `f3ade002f5c466ada2d829023ce0e2a767c54cc4a331b551985f5ce3dd0f4288` |
| `data/outcomes/prospective_deleted_paragraphs.json` | 13 November 2026 01:36 | `5c4ca9e57d35aa7018c1c008f2a1f689753410fbf8bd488df3f93f199d48fce8` |
