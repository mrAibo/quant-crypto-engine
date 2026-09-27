# Prompt for the next ChatGPT session

Continue **mrAibo/quant-crypto-engine** autonomously from GitHub source of truth.
At session start, verify the latest `main` and prefer it over chat memory.

Current state:

- phase: **Stage 2 — Signal-Existence Dataset and Falsification Protocol**
- primary task: **TASK-027 — Stage 2 Prospective Development Evidence Expansion**
- parallel bounded task: **TASK-028 — Tardis Historical Microstructure DEVELOPMENT Corpus**
- TASK-001 through TASK-026 are complete
- TASK-027 frozen public DEVELOPMENT capture is **COLLECTING** on Aibo
- TASK-028 protocol is frozen locally; bulk download must wait for protocol merge
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
7. only then inspect implementation/evidence as needed

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
- 20 days / 480 hours / 80 expected archives
- per day: Hyperliquid BTC book_snapshot_5 + trades; Binance Futures BTCUSDT quotes + trades
- primary historical ordering field: Tardis `local_timestamp`
- Hyperliquid and Binance Futures Tardis recorders are both in Tokyo
- end before 2026-06-17 Hyperliquid fastBook normalization cutoff
- TASK-025 eight-feature family unchanged
- horizons 50s / 300s only
- evidence role: **DEVELOPMENT_ONLY_EXTERNAL_RECEIVE_TIME**
- CryptoDataDownload is auxiliary coarse context only, not eligible for eight-feature rows

Exact next actions:

1. require green CI and merge the exact TASK-028 protocol/downloader implementation;
2. deploy merged `main` to Aibo;
3. download and verify exactly 80 TASK-028 archives into
   `/var/lib/quant-crypto-engine/tardis-historical-development`;
4. commit the immutable download/status checkpoint;
5. freeze a separate feature-build/training/evaluation protocol before consuming
   historical outcomes for model adjudication;
6. in parallel keep TASK-027 healthy until its fixed deadline;
7. after TASK-027 deadline publish deterministic prospective coverage/support evidence.

Do not fit/tune a model inside TASK-028, change dates/features/horizons based on
outcomes, open old confirmation, or introduce private/account/maker/live execution.
