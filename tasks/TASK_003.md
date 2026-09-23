# TASK-003 — Strict Recorder Configuration and Instrument Registry

## Status

`COMPLETE`

Merged as PR #3 in commit `9dd9145342430ed3a09b1e1e90f2a9d9f02af304`.

## Objective

Define strict recorder configuration and instrument identity contracts before any network recorder implementation.

## Delivered

- `config/recorder.yaml`
- `config/instruments.yaml`
- `src/cryptobot/config.py`
- `src/cryptobot/data/instruments.py`
- `src/cryptobot/data/__init__.py`
- `tests/unit/test_config.py`
- `tests/unit/test_instruments.py`
- `artifacts/stage_0/config_report.json`
- `tasks/TASK_004.md`

## Decisions

- Canonical instrument identity = venue + environment + product + native symbol.
- BTC Hyperliquid mainnet perpetual = PRIMARY.
- ETH Hyperliquid mainnet perpetual = REPLICATION.
- Reference feed is required but remains unselected.
- Unverified quote/margin/settlement assets, precision, and native IDs remain `null`.
- Queue/rollover/reconnect thresholds remain `null` until evidence justifies them.
- No network or trading code was introduced.

## Validation

Final GitHub Actions run `35890625489`:

- lock verification Python 3.12: PASS
- Ruff lint: PASS
- Ruff format: PASS
- strict mypy: PASS
- pytest Python 3.12: PASS
- lock verification Python 3.13: PASS
- pytest Python 3.13: PASS

## Next task

`TASK-004 — Immutable event envelope, exact numeric rules, and clock abstraction`.
