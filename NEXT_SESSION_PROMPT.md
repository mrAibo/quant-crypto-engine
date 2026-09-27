# Prompt for the next ChatGPT session

Continue **mrAibo/quant-crypto-engine** autonomously from GitHub source of truth.
At session start, verify the latest `main` and prefer it over chat memory.

Current state:

- phase: **Stage 2 — Signal-Existence Dataset and Falsification Protocol**
- primary task: **TASK-027 — Stage 2 Prospective Development Evidence Expansion**
- latest completed parallel task: **TASK-028 — Tardis Historical Microstructure DEVELOPMENT Corpus**
- current parallel bounded task: **TASK-029 — Frozen Tardis Historical Feature/Training Protocol**
- TASK-001 through TASK-026 and TASK-028 are complete; TASK-027 remains actively collecting
- TASK-027 frozen public DEVELOPMENT capture is **COLLECTING** on Aibo
- TASK-028 historical corpus is **COMPLETE: 80/80 verified archives, 0 missing**
- old Stage-2 confirmation: **UNOPENED_AND_EXCLUDED**
- live trading / OMS / signing / capital deployment: **FORBIDDEN**
- no private account/API key/wallet/AWS requester-pays access is required
- no user action is currently required

Read in this order:

1. `HANDOFF.md`
2. `STATUS.md`
3. `tasks/TASK_027.md`
4. `tasks/TASK_028.md`
5. `artifacts/stage_2/development_campaign_protocol.json`
6. `artifacts/stage_2/tardis_historical_development_protocol.json`
7. `artifacts/stage_2/tardis_historical_corpus_manifest.json`
8. `tasks/TASK_029.md`
9. `artifacts/stage_2/tardis_historical_training_protocol.json`
10. `artifacts/stage_2/tardis_lakehouse_manifest.json`
11. only then inspect implementation/evidence as needed

Frozen TASK-027 state:

- protocol SHA-256:
  `1ab9a735f512dd301392ba568b49ebd0f1e80d676f073b3d502bf73d111bc1d3`
- fixed start: `1790505535742461344` = **2026-09-27 12:38:55.742461 CEST**
- fixed deadline: `1790764735742461344` = **2026-09-30 12:38:55.742461 CEST**
- capture/process timers are active
- evidence role: **DEVELOPMENT_ONLY**
- do not shorten/extend based on outcomes

Frozen TASK-028 state:

- protocol SHA-256:
  `8d08ffa54eb64a3ecf11b9a73e3eea5d815f60560e7a93ad6796c63d2760b735`
- provider: Tardis.dev free first-of-month CSV datasets
- dates: **2024-11-01 through 2026-06-01**, first day of each month only
- 20 days / 480 hours / **80/80 verified archives**, 0 missing
- per day: Hyperliquid BTC book_snapshot_5 + trades; Binance Futures BTCUSDT quotes + trades
- primary historical ordering field: Tardis `local_timestamp`
- Hyperliquid and Binance Futures Tardis recorders are both in Tokyo
- end before 2026-06-17 Hyperliquid fastBook normalization cutoff
- TASK-025 eight-feature family unchanged
- horizons 50s / 300s only
- evidence role: **DEVELOPMENT_ONLY_EXTERNAL_RECEIVE_TIME**
- total compressed bytes: **1,180,336,813**
- corpus artifact SHA-256:
  `9696dca5f57fe160a8438236f1af82947a1588d2476a882fdf627f4cbd26e5e8`
- archive-set SHA-256:
  `8e545456b34c6d1dabdb4e31fc13a0cb174bb96fef01eb137d9c32fa1dcb37fc`
- economic outcomes consumed: **false**; model fitted: **false**
- CryptoDataDownload is auxiliary coarse context only, not eligible for eight-feature rows

Frozen TASK-029 state:

- training protocol SHA-256:
  `75fc97ab0ee68185704a06c81fd9fce06c0b1df5e32871dbac6247133ab53da1`
- source: exact TASK-028 corpus manifest and archive-set SHA bindings
- split: first 12 whole UTC days DEV_A / last 8 whole UTC days DEV_B
- horizons: 50s / 300s only
- features: exact TASK-025 eight-feature family
- model: deterministic Decimal L2 logistic; DEV_A standardization/training/gate only
- derived storage: Parquet ZSTD + DuckDB 1.5.5; raw TASK-028 remains source of truth
- lakehouse: **80/80 Parquet files, 103,817,053 rows**
- lakehouse manifest SHA-256:
  `c5032eda1f33421a6d71560e42e0f3e042b1ccd78647e358ea8b0390b4fc0e5f`
- Parquet-set SHA-256:
  `4d451076c74fa706d57b3565a16cc5aa78875664c68fb934ab72c687257a7a2b`
- storage conversion materializes no labels/PnL/economic outcomes
- DEV_B: frozen support/economic pass rules only
- current TASK-027 cannot be repurposed as fresh SELECTION
- historical economic outcomes are **not yet consumed**

Exact next actions:

1. merge the TASK-029 lakehouse checkpoint with its immutable manifest;
2. implement and merge the deterministic historical feature builder/trainer under the already-merged frozen TASK-029 protocol;
3. then build/train/evaluate the fixed TASK-028 corpus for 50s/300s only;
4. in parallel keep TASK-027 healthy until its fixed deadline;
5. after TASK-027 deadline publish deterministic prospective coverage/support evidence.

Do not alter the TASK-028 corpus or TASK-029 rules based on outcomes, open old
confirmation, or introduce private/account/maker/live execution.
