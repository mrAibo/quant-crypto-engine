# TASK-003 — Strict Recorder Configuration and Instrument Registry

## Status

`VALIDATED — MERGE PENDING`

## Objective

Define the configuration and instrument identity contracts that the recorder will consume before any network recorder implementation begins.

## Implemented files

- `config/recorder.yaml`
- `config/instruments.yaml`
- `src/cryptobot/config.py`
- `src/cryptobot/data/instruments.py`
- `src/cryptobot/data/__init__.py`
- `tests/unit/test_config.py`
- `tests/unit/test_instruments.py`
- `artifacts/stage_0/config_report.json`

## Key decisions

- Canonical instrument IDs are derived from venue/environment/product/native symbol.
- BTC Hyperliquid mainnet perpetual is PRIMARY.
- ETH Hyperliquid mainnet perpetual is REPLICATION.
- Reference feed is required but intentionally not selected yet.
- Unverified quote/margin/settlement assets, precision, and native asset IDs remain `null`.
- Queue/rollover/reconnect thresholds remain `null` until evidence or measurements justify values.
- No network/exchange/trading code is present.

## Validation guarantees

- Unknown and missing fields rejected.
- Duplicate source/channel identifiers rejected.
- Unsupported channels rejected.
- Unknown recorder instrument references rejected as recorder-config errors.
- Source venue/environment must match instrument registry.
- Canonical instrument-ID mismatch rejected.
- Exactly one PRIMARY instrument required.
- REFERENCE role/environment consistency enforced.
- Relative paths validated without requiring filesystem existence.
- Parent traversal/absolute paths rejected.
- Stable serialization verified.

## Validation

GitHub Actions run `35890454291`:

- lock verification Python 3.12: **PASS**
- Ruff lint: **PASS**
- Ruff format: **PASS**
- strict mypy: **PASS**
- pytest Python 3.12: **PASS**
- lock verification Python 3.13: **PASS**
- pytest Python 3.13: **PASS**

The suite contains 33 tests total at this stage.

## Definition of Done

1. Strict recorder configuration machine validated. **PASS**
2. Instrument identities protected from accidental aliasing. **PASS**
3. Unknown metadata remains unknown. **PASS**
4. Python 3.12/3.13 tests green. **PASS**
5. Ruff/format/strict-mypy/full pytest green. **PASS**
6. TASK-004 defined before merge. **PASS**

## Next task

`TASK-004 — Immutable event envelope, exact numeric rules, and clock abstraction`.

## Do Not Build

- WebSocket connections.
- Exchange API clients.
- Reference-venue adapter.
- Raw writer.
- Strategy/model/trading code.
