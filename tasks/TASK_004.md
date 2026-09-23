# TASK-004 — Immutable Event Envelope, Exact Numeric Rules, and Clock Abstraction

## Status

`VALIDATED — MERGE PENDING`

## Objective

Define recorder-independent domain contracts for normalized events, exact persisted market numerics, and time/clock handling before any live feed adapter or raw writer exists.

## Delivered

- `src/cryptobot/data/events.py`
- `src/cryptobot/data/numeric.py`
- `src/cryptobot/data/clock.py`
- `tests/unit/test_events.py`
- `tests/unit/test_numeric.py`
- `tests/unit/test_clock.py`
- `artifacts/stage_0/schema_v1.json`

## Contract decisions

- Normalized events are immutable.
- Exchange timestamps are nullable.
- Exchange timestamp resolution is explicit and never invented.
- Local receive wall/monotonic times are nanosecond integers.
- Monotonic elapsed time may be compared only inside the same host/boot identity.
- Apparent exchange-to-local lag is explicitly not claimed as one-way network latency.
- Persisted market monetary/size/rate values use exact `Decimal`.
- Binary float inputs for persisted exact numerics are rejected.
- NaN/Infinity rejected.
- Canonical fixed-point decimal serialization and exact scaled-integer helpers are provided.
- No venue parser/network/writer logic was introduced.

## Supported event-domain types

- L2 snapshot
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

## Validation

GitHub Actions run `35891685346`:

- lock verification Python 3.12: **PASS**
- Ruff lint: **PASS**
- Ruff format: **PASS**
- strict mypy: **PASS**
- pytest Python 3.12: **PASS**
- lock verification Python 3.13: **PASS**
- pytest Python 3.13: **PASS**

## Definition of Done

1. Immutable typed event envelope exists. **PASS**
2. Event payload types exist without parser/network code. **PASS**
3. Exact Decimal policy implemented and tested. **PASS**
4. Clock abstraction/time invariants implemented and tested. **PASS**
5. Python 3.12/3.13 tests green. **PASS**
6. Ruff/format/strict-mypy/full pytest green. **PASS**
7. TASK-005 defined before merge. **PASS**

## Next task

`TASK-005 — Append-only raw framed writer`.

## Do Not Build

- WebSocket clients.
- Parquet materialization.
- strategy/features/backtester.
- exchange execution/OMS.
