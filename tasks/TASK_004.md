# TASK-004 — Immutable Event Envelope, Exact Numeric Rules, and Clock Abstraction

## Status

`COMPLETE`

Merged as PR #4 in commit `dbc08c6a6f721b9f7e0f0cc0b5afb2e91c948659`.

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
- `tasks/TASK_005.md`

## Decisions

- Normalized events are immutable.
- Exchange timestamp and resolution remain explicitly nullable/typed.
- No exchange precision or timestamp semantics are invented.
- Local receive wall/monotonic clocks are nanosecond integers.
- Monotonic elapsed-time comparison is limited to one host/boot identity.
- Persisted market numerics use exact `Decimal`; binary floats are rejected.
- No venue parser/network/raw-writer/trading logic was introduced.

## Validation

Final GitHub Actions run `35891870831`:

- lock verification Python 3.12: PASS
- Ruff lint: PASS
- Ruff format: PASS
- strict mypy: PASS
- pytest Python 3.12: PASS
- lock verification Python 3.13: PASS
- pytest Python 3.13: PASS

## Next task

`TASK-005 — Append-only raw framed writer`.
