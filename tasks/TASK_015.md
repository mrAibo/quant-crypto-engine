# TASK-015 — Deterministic Parquet Research Dataset

## Status

`PENDING`

## Objective

Materialize TASK-014 frame outcomes and normalized causal records into a deterministic, typed, audit-friendly Parquet research dataset.

The dataset must be a **derived cache of immutable QCR1 evidence**, never a new source of truth. Every materialized event must remain traceable to exactly one raw occurrence and reproducible from the same raw inputs plus pinned code/dependencies.

This task does **not** create features, labels, forward returns, signals, backtests, strategies, deduplication, gap backfill, OMS, or trading.

## Input authority

Inputs are:

- TASK-014 `FrameResult` values;
- TASK-014 `CausalRecord` values;
- existing immutable event envelopes and payloads;
- the TASK-014 deterministic normalization report/digest.

Raw QCR1 remains authoritative. Parquet is replaceable/rebuildable derived state.

## Dependency decision

Use **PyArrow directly**, not pandas.

Reasons:

- explicit Parquet schemas;
- exact nullable integer/string/list handling;
- stable row ordering under our control;
- no DataFrame index semantics;
- smaller conceptual surface for the Data Gate.

The resolved PyArrow version must be pinned by `uv.lock` and recorded in the materialization manifest.

## Dataset topology

Write the same fixed set of files on every successful materialization, including schema-correct empty tables:

- `frames.parquet` — one row per raw frame result, including NOT_APPLICABLE / EMPTY / ERROR;
- `events.parquet` — one row per normalized causal event with common envelope + causal metadata;
- `l2_snapshots.parquet`;
- `l2_levels.parquet` — one row per level with side + level ordinal;
- `bbo.parquet`;
- `trades.parquet`;
- `funding_rates.parquet`;
- `mark_prices.parquet`;
- `oracle_prices.parquet`;
- `reference_bbo.parquet`;
- `reference_trades.parquet`;
- `manifest.json` — schema/writer/version/row-count/hash provenance.

Do not hide control/error frames merely because they have no normalized event.

## Exact numeric policy

Do **not** use binary floats.

For TASK-015, persisted market prices, sizes, and rates are canonical exact fixed-point strings produced by the existing numeric serializer.

Rationale:

- source scales vary;
- v1 intentionally preserves exact decimal value semantics;
- fixed Parquet decimal scale would either over-constrain heterogeneous inputs or silently rescale representation;
- later numeric feature materialization may add explicitly scaled numeric columns once scale requirements are frozen.

Integer IDs/timestamps/counters remain integer columns.

## Common event table

`events.parquet` must contain at minimum:

Pipeline metadata:

- host_id;
- boot_id;
- recv_mono_ns;
- recv_wall_ns;
- source_id;
- raw_segment_id;
- raw_offset;
- event_ordinal.

Envelope metadata:

- event_id;
- event_type;
- instrument_id;
- native_symbol;
- exchange_ts_ns;
- exchange_ts_resolution_ns;
- exchange_ts_semantics;
- connection_id;
- ingest_seq;
- native_sequence;
- native_update_id;
- raw_sha256;
- parse_version;
- quality_flags;
- availability_kind.

The event envelope and pipeline wrapper must agree on shared receive/raw/source/domain fields; mismatch is a hard materialization error.

## Payload tables

Payload tables are keyed by `event_id` and contain only event-specific fields.

### L2

`l2_snapshots.parquet`:

- event_id;
- depth_limit;
- aggregation;
- full_snapshot.

`l2_levels.parquet`:

- event_id;
- side = BID|ASK;
- level_ordinal;
- price_exact;
- size_exact;
- order_count.

Preserve parser order exactly. Do not sort levels by price in TASK-015.

### BBO / reference BBO

Persist exact bid/ask price/size strings with nullable paired sides.

Reference BBO also stores sampling_mode.

### Trades / reference trades

Persist:

- price_exact;
- size_exact;
- native_side;
- aggressor_side;
- trade_id.

Hyperliquid trade additionally stores transaction_hash.

Do not deduplicate repeated stable trade IDs.

### Funding / mark / oracle

Persist exact rate/price strings and existing semantic fields only. Do not invent effective boundaries, mark methods, or oracle IDs.

## Deterministic ordering

Parquet row order is fixed before writing:

- frames: `(host_id, boot_id, recv_mono_ns, recv_wall_ns, source_id, raw_segment_id, raw_offset)`;
- events: `(host_id, boot_id, recv_mono_ns, recv_wall_ns, source_id, raw_segment_id, raw_offset, event_ordinal)`;
- payload tables: follow the corresponding deterministic event order;
- L2 levels: event order, then side order BID before ASK, then original level ordinal.

Ordering across different causal domains is only a deterministic serialization order; it is **not** a causal claim.

## Parquet writer contract

Freeze writer options in code and manifest.

Initial contract:

- explicit PyArrow schemas;
- deterministic pre-sorted rows;
- fixed row-group size;
- dictionary encoding disabled;
- statistics enabled;
- fixed Parquet format/data-page versions;
- fixed compression codec/level;
- no wall-clock-derived file metadata;
- no random UUIDs;
- no path-dependent metadata.

Binary byte identity is required for repeated writes with the same:

- normalized input;
- project code;
- PyArrow/Arrow implementation version;
- writer options.

Cross-PyArrow-version byte identity is **not** claimed. Semantic round-trip equality and manifest schema version remain the compatibility boundary.

## Atomicity / overwrite policy

1. Materialize into a sibling temporary directory.
2. Verify all files, row counts, hashes, schemas, and manifest.
3. Publish by atomic directory rename when the final destination does not exist.
4. Refuse to overwrite an existing dataset by default.
5. No in-place partial mutation of a published dataset.

A future versioned dataset manager may supersede old derived datasets explicitly; TASK-015 does not implement mutable overwrite.

## Manifest

`manifest.json` records at minimum:

- dataset_schema_version;
- materializer_version;
- source normalization pipeline version;
- source normalization report digest;
- PyArrow version;
- writer options;
- deterministic table list;
- per-table row count;
- per-file SHA-256;
- dataset bundle SHA-256 over canonical sorted file metadata;
- causal-domain count;
- raw frame count;
- normalized event count;
- creation semantics = DERIVED_REBUILDABLE;
- explicit statement that raw QCR1 is authoritative.

The manifest must not contain current wall-clock time, hostname, temp path, or other nondeterministic build metadata.

## Validation / round trip

After writing, read every Parquet file back and verify:

- exact schema;
- exact row count;
- expected deterministic row order;
- no float columns for market numerics;
- event IDs and raw provenance match inputs;
- all normalized events have exactly one payload row, except L2 which has one snapshot row plus zero or more level rows;
- all payload rows reference an existing event_id of the correct event type;
- frame outcome/error visibility is preserved;
- repeated materialization from identical inputs yields identical file SHA-256 values and bundle digest under the pinned stack.

## Planned files

- `src/cryptobot/data/materialize.py`
- `tests/unit/test_materialize.py`
- `tests/integration/test_parquet_materialization_replay.py`
- `artifacts/stage_0/parquet_materialization.json`

Dependency files may also change:

- `pyproject.toml`;
- `uv.lock`.

## Required tests

### Unit

- fixed explicit schemas;
- empty dataset writes all expected files;
- common event/envelope metadata mapping;
- each supported event payload table;
- exact decimal string persistence;
- L2 side/ordinal preservation;
- duplicate stable trade IDs preserved;
- deterministic row sorting;
- mixed causal domains serialized deterministically without claiming global causality;
- envelope/pipeline provenance mismatch rejected;
- unsupported event class rejected;
- existing destination rejected;
- manifest excludes nondeterministic build metadata;
- deterministic manifest/file hashes.

### Integration

Construct two-source QCR1 data, replay through TASK-014, materialize, read back, and prove:

- frame/control/error outcomes survive;
- all event types present in the fixture round-trip correctly;
- raw segment/offset/SHA provenance survives;
- same input produces byte-identical Parquet files and identical manifest bundle digest under the pinned environment;
- no source event is silently omitted;
- reconnect duplicate stable trade IDs remain separate rows;
- a second materialization to an already published destination fails cleanly without modifying it.

## Evidence artifact

`artifacts/stage_0/parquet_materialization.json` records:

- materializer/schema version;
- PyArrow version;
- writer contract;
- exact-numeric storage policy;
- table topology;
- deterministic ordering;
- atomic publish policy;
- round-trip validation;
- CI result;
- limitations.

## Definition of Done

1. PyArrow is locked reproducibly.
2. All fixed Parquet tables use explicit schemas.
3. Full TASK-014 outcomes/events materialize without silent loss.
4. Exact numeric values remain non-float exact strings.
5. Raw/event provenance is round-trippable.
6. Repeated same-stack materialization is byte deterministic.
7. Published dataset creation is atomic and non-overwriting.
8. Integration replay proves source → QCR1 → normalize → Parquet → readback.
9. No features/labels/backtest/strategy/execution code is introduced.
10. Ruff/format/strict mypy/pytest green on Python 3.12 and 3.13.
11. `STATUS.md` advances to the Stage-0 Data Gate / next explicitly defined task.

## Do Not Build

- features;
- labels or forward returns;
- resampling bars;
- backtest/simulator;
- economic frontier calculations;
- deduplication;
- gap backfill;
- live execution/OMS/signing;
- AI/Jev/GPT logic.
