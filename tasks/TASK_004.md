# TASK-004 — Immutable Event Envelope, Exact Numeric Rules, and Clock Abstraction

## Status

`IN REVIEW — IMPLEMENTED, GITHUB CI PENDING`

## Objective

Define recorder-independent domain contracts for normalized events, exact persisted market numerics, and time/clock handling before any live feed adapter or raw writer exists.

## Implemented files

- `src/cryptobot/data/events.py`
- `src/cryptobot/data/numeric.py`
- `src/cryptobot/data/clock.py`
- `tests/unit/test_events.py`
- `tests/unit/test_numeric.py`
- `tests/unit/test_clock.py`
- `artifacts/stage_0/schema_v1.json`

## Implemented event contract

The immutable envelope includes:

- schema/event/source/instrument identifiers;
- nullable exchange timestamp;
- explicit exchange timestamp resolution;
- timestamp semantics enum;
- local wall and monotonic receive time;
- host/boot/connection identity;
- capture-order sequence;
- nullable native sequence/update IDs;
- raw segment provenance + SHA-256;
- parser version;
- quality bitmask;
- availability kind.

Exchange time may remain absent. If absent, timestamp semantics must be `UNKNOWN`; precision is never invented.

## Implemented event-domain types

- L2 snapshot + book levels
- BBO
- trade
- funding-rate observation
- funding payment
- mark price
- oracle price
- reference BBO
- reference trade
- feed status
- gap
- clock health

No venue parser exists yet.

## Exact numeric policy

- persisted money/price/size/rate values use `Decimal`;
- strings, integers, and `Decimal` can be parsed exactly;
- binary floats and bools are rejected;
- NaN/Infinity rejected;
- deterministic fixed-point string serialization;
- exact scaled-integer conversion helpers.

## Clock policy

- `ClockSample` carries wall ns + monotonic ns + host/boot identity;
- monotonic elapsed-time comparison is forbidden across host/boot boundaries;
- negative apparent exchange lag is allowed because clock offset can exist;
- missing exchange timestamp produces unknown apparent lag;
- `SystemClock` is a standard-library wrapper only;
- no chrony/NTP integration yet.

## Tests added

Tests cover:

- immutability;
- exchange timestamp nullability/precision invariants;
- deterministic serialization;
- strict raw hash;
- payload/event-type consistency;
- BBO null-side behavior;
- no float monetary values;
- exact Decimal round-trips;
- scaled integer round-trips;
- NaN/Infinity rejection;
- clock identity and monotonic comparison;
- apparent exchange lag semantics;
- event-domain smoke coverage.

## Definition of Done

1. Immutable typed event envelope exists. **IMPLEMENTED**
2. Event payload types exist without network/parser code. **IMPLEMENTED**
3. Exact Decimal policy implemented and tested. **IMPLEMENTED**
4. Clock abstraction/time invariants implemented and tested. **IMPLEMENTED**
5. Python 3.12/3.13 tests green. **PENDING CI**
6. Ruff/format/strict mypy/full pytest green. **PENDING CI**
7. TASK-005 defined before merge. **PENDING**

## Do Not Build

- Hyperliquid/reference WebSocket clients.
- Raw framed writer.
- Parquet writer.
- Strategy/features/backtester.
- Exchange execution/OMS.

## Next task after merge

TASK-005 — append-only raw framed writer.
