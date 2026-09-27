# TASK-028 — Tardis Historical Microstructure DEVELOPMENT Corpus

## Status

**COMPLETE — 80/80 ARCHIVES VERIFIED AND FROZEN**

## Role

TASK-028 is a parallel, non-gating historical DEVELOPMENT track while TASK-027
continues its fixed 72-hour prospective public capture.

It must not replace, shorten, pause, or reinterpret TASK-027.

## Objective

Build an immutable historical corpus that can reproduce the frozen TASK-025
eight-feature BTC microstructure family without waiting for the prospective campaign
to finish.

No predictive model is fitted in TASK-028.

## Frozen provider and dates

Provider: **Tardis.dev downloadable CSV datasets**.

Use exactly the first UTC day of every month from:

- first day: **2024-11-01**
- last day: **2026-06-01**
- day count: **20**
- nominal historical coverage: **480 hours**

The dates are fixed before bulk outcome inspection.

The end date is deliberately before the **2026-06-17** Tardis Hyperliquid normalized
book cutoff where `book_snapshot_5/25` changes from regular `l2Book` to `fastBook`.

No date may be added, removed, or replaced because of observed strategy outcomes.

## Frozen sources per day

Exactly four archives are eligible:

1. Hyperliquid `BTC` `book_snapshot_5`
2. Hyperliquid `BTC` `trades`
3. Binance USDS-M `BTCUSDT` `quotes`
4. Binance USDS-M `BTCUSDT` `trades`

Total expected archives: **80**.

The primary ordering/alignment field is Tardis `local_timestamp` in microseconds UTC.
Hyperliquid and Binance Futures are recorded by Tardis in the same Tokyo GCP region.
This makes their local timestamps suitable for this DEVELOPMENT cross-venue alignment,
but they remain external receive-time and are not equivalent to Aibo receive-time.

## Evidence role

Every TASK-028 row is:

`DEVELOPMENT_ONLY_EXTERNAL_RECEIVE_TIME`

It is not:

- prospective TASK-027 evidence;
- SELECTION evidence;
- CONFIRMATION evidence;
- live execution evidence.

The old Stage-2 confirmation remains **UNOPENED_AND_EXCLUDED**.

## Frozen research semantics

- TASK-025 eight-feature family unchanged;
- horizons: 50s and 300s only;
- 4.5 bps/side fee remains a SCENARIO;
- actual account fee, latency, own-order impact/slippage, funding boundaries, and
  maker economics remain UNKNOWN;
- gaps/incidents are preserved and reported;
- no outcome-dependent exclusions;
- no new feature, threshold, horizon, or hyperparameter is selected in TASK-028.

## CryptoDataDownload

The user-provided CryptoDataDownload source is useful for auxiliary OHLCV/trade-print
context, regime checks, and independent coarse sanity checks.

It is **not eligible** for TASK-028 eight-feature rows because the free catalog does
not provide the required Hyperliquid top-5 microstructure plus comparable cross-venue
receiver timestamps.

## Storage

Use only:

`/var/lib/quant-crypto-engine/tardis-historical-development`

Never store TASK-028 files under the TASK-018 or TASK-027 campaign roots.

Each archive is published with an immutable manifest containing source URL, local
SHA-256, compressed byte size, frozen protocol SHA, expected schema, and evidence role.

## Definition of Done

1. Frozen protocol artifact is committed before bulk data download.
2. Protocol covers exactly 20 dates / 80 archives.
3. All downloaded gzip files pass decompression/CRC and exact header checks.
4. Every archive has an immutable SHA-bound manifest.
5. A deterministic status report shows complete/missing sources and total bytes.
6. No model is fitted and no outcome-driven corpus changes occur.
7. TASK-027 continues independently.
8. Old confirmation remains unopened/excluded.
9. A later task freezes the historical feature-build/training/evaluation protocol
   before using TASK-028 outcomes for model adjudication.
10. Ruff/format/strict mypy/pytest are green before merge.

## Do Not Build

- new predictive features;
- horizon sweeps;
- unrestricted model tuning;
- LightGBM;
- maker simulation/orders;
- private account ingestion;
- OMS/signing/live trading;
- capital deployment;
- reinterpretation of historical DEVELOPMENT as confirmation.

## Closeout result

TASK-028 completed without consuming strategy/economic outcomes.

Verified corpus:

- 20 frozen first-of-month UTC days;
- 480 nominal historical hours;
- 80/80 archives verified;
- 0 missing archives;
- total compressed bytes: **1,180,336,813**;
- protocol SHA-256:
  `8d08ffa54eb64a3ecf11b9a73e3eea5d815f60560e7a93ad6796c63d2760b735`;
- deterministic corpus artifact:
  `artifacts/stage_2/tardis_historical_corpus_manifest.json`;
- corpus artifact SHA-256:
  `9696dca5f57fe160a8438236f1af82947a1588d2476a882fdf627f4cbd26e5e8`;
- archive-set SHA-256:
  `8e545456b34c6d1dabdb4e31fc13a0cb174bb96fef01eb137d9c32fa1dcb37fc`;
- economic outcomes consumed: **false**;
- model fitted: **false**;
- old confirmation: **UNOPENED_AND_EXCLUDED**;
- TASK-027 replaced or shortened: **false**.

The next bounded work package may construct/train on this historical DEVELOPMENT
corpus only after its feature-build, chronological split, training procedure, and
development evaluation rule are frozen before outcome inspection.
