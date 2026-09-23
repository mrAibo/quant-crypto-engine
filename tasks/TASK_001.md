# TASK-001 — Bootstrap Repository and Quality Gate

## Status

`IN PROGRESS` until the committed GitHub Actions workflow is green.

## Objective

Create the reproducible Python project and mandatory quality gates before any trading logic is added.

## Files

- `pyproject.toml`
- `uv.lock`
- `.python-version`
- `.gitignore`
- `.github/workflows/ci.yml`
- `src/cryptobot/__init__.py`
- `tests/unit/test_package.py`
- initial project documentation and `STATUS.md`

## Tests

- clean dependency synchronization from `uv.lock`;
- Ruff lint;
- Ruff formatting check;
- strict mypy;
- pytest on Python 3.12;
- pytest compatibility run on Python 3.13.

## Definition of Done

1. Clean checkout can reproduce the environment from the lock file.
2. Local lint/format/type/test checks pass.
3. GitHub Actions CI is green.
4. No market-data, strategy, exchange, or trading logic has been introduced.
5. `artifacts/stage_0/bootstrap_report.json` records validation status.
6. `STATUS.md` points to `TASK-002` as the exact next task.
