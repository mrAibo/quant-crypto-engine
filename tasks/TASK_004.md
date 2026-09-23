# TASK-004 — Immutable Event Envelope, Exact Numeric Rules, and Clock Abstraction

## Status

`PENDING`

## Objective

Define the recorder-independent domain contracts for market events, exact numeric persistence, and time/clock handling before any live feed adapter or raw writer is implemented.

This task must make event availability, timestamp meaning, raw provenance, ordering, and monetary precision explicit enough that later recorder/replay code cannot silently invent time or precision.

## Planned files

- `src/cryptobot/data/events.py`
- `src/cryptobot/data/numeric.py`
- `src/cryptobot/data/clock.py`
- `tests/unit/test_events.py`
- `tests/unit/test_numeric.py`
- `tests/unit/test_clock.py`
- `artifacts/stage_0/schema_v1.json`

## Event-envelope contract

Every persisted normalized event must carry, at minimum:

- `schema_version`
- `event_id`
- `event_type`
- `source`
- `instrument_id`
- `native_symbol`
- nullable `exchange_ts_ns`
- nullable/explicit `exchange_ts_resolution_ns`
- `exchange_ts_semantics`
- `recv_wall_ns`
- `recv_mono_ns`
- `host_id`
- `boot_id`
- `connection_id`
- `ingest_seq`
- nullable `native_sequence`
- nullable `native_update_id`
- `raw_segment_id`
- `raw_offset`
- `raw_sha256`
- `parse_version`
- `quality_flags`
- `availability_kind`

No field may imply precision the venue did not publish.

## Event types to define

Define schema types only; do not implement parsing yet:

- `L2Snapshot`
- `BBO`
- `Trade`
- `FundingRateObservation`
- `FundingPayment`
- `MarkPrice`
- `OraclePrice`
- `ReferenceBBO`
- `ReferenceTrade`
- `FeedStatus`
- `Gap`
- `ClockHealth`

A raw payload may later produce multiple normalized events sharing the same raw reference.

## Time model

### Required concepts

- Exchange/native event time: nullable and semantic-tagged.
- Local receive wall clock: UTC nanoseconds.
- Local monotonic receive clock: nanoseconds valid only within the same host/boot.
- Capture order: explicit `ingest_seq`; timestamps are not the journal/order key.
- Exchange/local apparent lag: allowed only when exchange time is present and with clear naming that it is **not** one-way network latency.
- No wall-clock calls inside pure event/domain logic.

### Clock abstraction

Define a small injected clock protocol suitable for later recorder/runtime use:

- wall UTC nanoseconds;
- monotonic nanoseconds;
- paired sample method if useful to reduce skew between reads.

The clock implementation in this task may wrap the standard library only. No NTP/chrony shell integration yet.

## Exact numeric rules

Define reusable helpers/types for exact persisted market numerics:

- decimal-string parsing for price/size/rate/cash values;
- rejection of NaN/Infinity;
- no binary-float input for values persisted as money/size;
- canonical decimal serialization without silent exponent/precision loss;
- optional instrument-scaled integer helpers may be included only if their contract is fully deterministic.

Feature/model floats are a later concern and must remain separate from persisted monetary values.

## Validation requirements

- Event envelope immutable after construction.
- Required identifiers non-empty and structurally validated.
- Nanosecond fields are integers, not floats.
- Nullable exchange time remains nullable.
- Exchange timestamp resolution must not exist without exchange time.
- `recv_wall_ns` and `recv_mono_ns` non-negative.
- `ingest_seq`, `raw_offset` non-negative.
- SHA-256 field strict.
- Quality flags deterministic and serializable.
- Availability kind strict enum.
- Same event serializes deterministically.
- Decimal round trips exactly.
- Float money input rejected.
- Scientific notation accepted only if it round-trips canonically and without loss.
- NaN/Infinity rejected.
- Monotonic durations never compare different boot IDs silently.
- Apparent exchange lag returns unknown when exchange timestamp is absent.
- No network/filesystem access in unit tests.

## Suggested event semantics enums

Define strict enums rather than free text for:

- event type;
- exchange timestamp semantics;
- availability kind;
- feed status;
- quality flags where a bit/enum representation is appropriate.

Do not invent venue-specific sequence guarantees.

## Completion artifact

`artifacts/stage_0/schema_v1.json` must describe:

- schema version;
- event-envelope fields and nullability;
- supported event types;
- timestamp semantics;
- numeric policy;
- serialization policy;
- known limitations;
- validation/CI result.

## Definition of Done

1. Immutable typed event envelope exists.
2. Supported event-domain payload types exist without parser/network code.
3. Exact decimal policy is implemented and tested.
4. Clock abstraction and time invariants are implemented and tested.
5. Tests pass on Python 3.12 and 3.13.
6. Ruff/format/strict mypy/full pytest CI is green.
7. `STATUS.md` advances to TASK-005.

## Do Not Build

- Hyperliquid WebSocket client.
- Reference-venue client.
- Raw framed writer.
- Parquet writer.
- Strategy/features/backtester.
- Exchange execution/OMS.
