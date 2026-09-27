# TASK-029 — Frozen Tardis Historical Feature/Training Protocol

## Status

**FEATURE CACHES FROZEN — DEV_A/DEV_B ECONOMIC EVALUATION NOT YET RUN**

## Context

TASK-028 completed a frozen 480-hour Tardis historical DEVELOPMENT corpus:

- 20 first-of-month UTC days;
- 80/80 archives verified;
- corpus manifest SHA-256:
  `9696dca5f57fe160a8438236f1af82947a1588d2476a882fdf627f4cbd26e5e8`;
- archive-set SHA-256:
  `8e545456b34c6d1dabdb4e31fc13a0cb174bb96fef01eb137d9c32fa1dcb37fc`;
- economic outcomes consumed: **false**.

TASK-027 remains an independent fixed 72-hour prospective DEVELOPMENT campaign.

## Objective

Freeze the historical feature construction, causal alignment, chronological split,
model training, and DEV_B adjudication rules **before** reading TASK-028 economic
outcomes.

After this exact protocol merges, implementation may build, train, and evaluate the
frozen family without modifying the rules based on observed results.

## Frozen protocol artifact

`artifacts/stage_2/tardis_historical_training_protocol.json`

SHA-256:

`75fc97ab0ee68185704a06c81fd9fce06c0b1df5e32871dbac6247133ab53da1`

It binds:

- TASK-025 eight-feature registry SHA;
- TASK-028 protocol SHA;
- TASK-028 corpus manifest SHA;
- TASK-028 archive-set SHA.

## Rebuildable analytical storage

TASK-028 immutable `.csv.gz` archives and their SHA-bound manifests remain the
source of truth.

TASK-029 may build a derived analytical layer only as:

`raw Tardis .csv.gz -> canonical Parquet (ZSTD) -> DuckDB catalog/views`

Frozen storage rules:

- DuckDB version: **1.5.5**;
- price/amount columns: **DECIMAL(38,18)**;
- exchange/local timestamps: **BIGINT microseconds**;
- immutable CSV row order preserved as `source_row_number`;
- one Parquet file per source archive;
- local timestamps must be monotonic by source row and remain within the frozen UTC day;
- the DuckDB file stores query views and metadata, not a second source of truth;
- economic outcomes/labels/PnL are **not materialized during storage conversion**;
- the entire Parquet/DuckDB layer must be reproducible from TASK-028 raw archives.

### Lakehouse completion checkpoint

The merged TASK-029 storage implementation built successfully on Aibo:

- Parquet partitions: **80/80**;
- total analytical rows: **103,817,053**;
- lakehouse manifest:
  `artifacts/stage_2/tardis_lakehouse_manifest.json`;
- lakehouse manifest SHA-256:
  `c5032eda1f33421a6d71560e42e0f3e042b1ccd78647e358ea8b0390b4fc0e5f`;
- Parquet-set SHA-256:
  `4d451076c74fa706d57b3565a16cc5aa78875664c68fb934ab72c687257a7a2b`;
- DuckDB catalog: `/var/lib/quant-crypto-engine/tardis-lakehouse/catalog/historical.duckdb`;
- Hyperliquid top-5 rows: **3,030,252**;
- Hyperliquid trade rows: **7,170,696**;
- Binance quote rows: **25,002,943**;
- Binance trade rows: **68,613,162**;
- storage conversion economic outcomes materialized: **false**;
- model fitted: **false**.

Raw TASK-028 archives remain the source of truth. The lakehouse is rebuildable and
may now be used by the frozen historical feature builder/trainer.

### Feature/training implementation checkpoint

The deterministic implementation is prepared but has **not** been run on the real
historical corpus yet.

It adds:

- `build-tardis-training-features`: builds separate immutable 50s/300s caches from
  the frozen DuckDB catalog using causal `local_timestamp` ASOF semantics;
- a feature-build report that freezes both cache SHA-256 values before economic
  summary/model fitting;
- `evaluate-tardis-historical-development`: requires the exact feature-build
  report SHA, loads only the frozen cache SHA values, fits DEV_A only, and adjudicates
  DEV_B under the pre-registered rules;
- exact Decimal feature/economic arithmetic;
- no threshold/horizon/hyperparameter sweep;
- explicit provenance from TASK-029 protocol -> lakehouse -> feature-build report
  -> cache SHA values -> development report.

The implementation merged with green CI before the real 480-hour feature build.

### Real feature-build checkpoint

The merged implementation completed the real 20-day / 480-hour feature build on Aibo.

Frozen checkpoint:

- feature-build report:
  `artifacts/stage_2/tardis_historical_feature_build_report.json`;
- feature-build report SHA-256:
  `645e247ea9589935f4b7a09cb98559d0df704ebc6c60287863d72303f6e68195`;
- 50s cache rows: **33,965**;
- 50s cache SHA-256:
  `409ef9c60bfcbb048b593fc16f1d34cc84da1f0087ea372b7c4c799d3d030640`;
- 300s cache rows: **5,756**;
- 300s cache SHA-256:
  `49fea618533a359727cfce3d95d2b50ee876c6fa2d75931f4b4e305e3938b3b3`;
- exact 20 frozen UTC days represented in both caches;
- economic summary computed: **false**;
- model fitted: **false**.

The caches contain the pre-registered entry/exit and feature fields required for the
later economic evaluation, but no DEV_A/DEV_B economic summary or fitted model has
yet been produced. The exact feature-build report SHA must merge before evaluation.

## Historical causal semantics

Tardis `local_timestamp` is the primary historical availability clock.

- units: microseconds since Unix epoch UTC;
- ordering: `local_timestamp`, then immutable file row order;
- each exchange/symbol/UTC day is a separate causal domain;
- no feature, trade window, entry/exit opportunity, or outcome may cross a UTC day;
- a local-timestamp reversal hard-fails that source/day;
- Tardis receive time is **not** represented as Aibo receive time.

The primary decision stream is Hyperliquid BTC `book_snapshot_5`.

For each horizon:

1. entry = next unused book snapshot;
2. exit = first book snapshot at or after entry + horizon;
3. next entry = first book row after that exit;
4. opportunities are therefore non-overlapping;
5. any inter-snapshot gap greater than **15 seconds** invalidates the opportunity.

The 15-second ceiling is a frozen historical source-quality rule. It is not a live
latency assumption and does not change TASK-027's prospective semantics.

## Frozen features

The TASK-025 eight-feature family remains unchanged:

1. absolute Hyperliquid BBO imbalance;
2. H2-aligned Hyperliquid top-5 depth imbalance;
3. H2-aligned Hyperliquid aggressive trade flow over 5s;
4. H2-aligned Binance aggressive trade flow over 5s;
5. H2-aligned Hyperliquid mid return over 5s;
6. H2-aligned Binance mid return over 5s;
7. H2-aligned cross-venue return gap over 5s;
8. Hyperliquid spread bps.

Feature anchors/current states must be at or before the decision and no more than
**2 seconds stale** where the registry requires an anchor/current lookup.

Trade windows are `(decision - 5s, decision]`. A window containing any Tardis
`unknown` aggressor side is missing rather than silently dropping unknown volume.
A window with no trades is also missing.

## Frozen DEVELOPMENT split

Whole UTC days only:

### DEV_A — first 12 days

2024-11-01 through 2025-10-01, first day of each month.

### DEV_B — last 8 days

2025-11-01 through 2026-06-01, first day of each month.

No day may move between partitions after outcomes are read.

## Frozen model

For each of the two existing horizons, **50s and 300s only**:

- direction: sign of Hyperliquid top-of-book imbalance;
- target: whether the H2-direction executable trade has positive partial-known-cost
  PnL;
- entry/exit: executable Hyperliquid bid/ask;
- fee: frozen **4.5 bps/side SCENARIO**;
- latency, impact/slippage, funding, actual account fee: remain UNKNOWN;
- standardization: DEV_A only;
- model: deterministic Decimal L2 logistic regression;
- L2 lambda: 1;
- max iterations: 80;
- convergence tolerance: 1e-24;
- probability gate: DEV_A expected-value break-even from mean positive/nonpositive
  known-net observations;
- no hyperparameter or probability-threshold sweep.

Minimum DEV_A support:

- 50s: 300 valid targets, >=30 positive, >=30 nonpositive;
- 300s: 80 valid targets, >=30 positive, >=30 nonpositive.

If a horizon lacks support, it is not fitted and cannot pass.

## Frozen DEV_B adjudication

Selected trades are evaluated chronologically. The early/late split is by selected
trade count; if odd, the extra middle trade belongs to the late half.

50s requires:

- >=50 selected DEV_B trades;
- >=25 selected trades in each half.

300s requires:

- >=30 selected DEV_B trades;
- >=15 selected trades in each half.

A horizon passes only if all are true:

- support minima pass;
- DEV_B mean partial-known-cost PnL > 0;
- DEV_B cumulative partial-known-cost PnL > 0;
- DEV_B median known-net bps > 0;
- early-half mean partial-known-cost PnL > 0;
- late-half mean partial-known-cost PnL > 0.

At most one horizon may be frozen. If both pass, choose the higher DEV_B mean
known-net bps; exact tie chooses 50s.

## Decision boundary

If no horizon passes:

`STOP_HISTORICAL_MICROSTRUCTURE_DEVELOPMENT`

If one horizon passes:

`FREEZE_ONE_HISTORICAL_DEVELOPMENT_CANDIDATE_FOR_FUTURE_FRESH_PROSPECTIVE_SELECTION`

TASK-027 may **not** be relabeled or repurposed as fresh SELECTION because its
collection began before any TASK-029 candidate could be frozen.

Old confirmation remains **UNOPENED_AND_EXCLUDED**.

## Definition of Done

1. Protocol artifact is committed and merged before historical outcome use.
2. Source corpus SHA bindings match TASK-028.
3. Feature builder follows frozen local-timestamp/day semantics.
4. 50s and 300s rows are produced deterministically with provenance.
5. DEV_A support is evaluated before fitting.
6. Models, if supported, fit only DEV_A.
7. Probability hurdle derives only from DEV_A.
8. DEV_B is used only for the frozen adjudication above.
9. No new feature/horizon/threshold/hyperparameter is introduced.
10. TASK-027 remains unchanged and continues to its fixed deadline.
11. Old confirmation stays unopened/excluded.
12. Ruff/format/strict mypy/pytest are green before merge.

## Do Not Build

- LightGBM;
- unrestricted feature mining;
- new horizons;
- threshold sweeps;
- outcome-dependent day exclusion;
- private account data;
- maker simulation/orders;
- OMS/signing/live trading;
- capital deployment.
