# TASK-002 — Implement the Evidence Contract

## Status

`COMPLETE`

Merged as PR #2 in commit `b10034fe26a1af1f48f4c3eaa8d5703abd041d7c`.

## Objective

Create the first machine-readable evidence policy so venue/API facts are never silently promoted from assumption to verified input.

## Implemented files

- `config/evidence.yaml`
- `src/cryptobot/evidence/contract.py`
- `src/cryptobot/evidence/__init__.py`
- `docs/evidence_sources.md`
- `tests/unit/test_evidence.py`
- `artifacts/stage_0/evidence_report.json`

## Design decision

`config/evidence.yaml` uses the JSON-compatible subset of YAML 1.2. This keeps Stage 0 dependency-free for configuration parsing while retaining a future-compatible YAML file extension.

## Evidence baseline

The initial contract contains **21 facts**:

- **13 VERIFIED documented facts**
- **8 intentionally UNKNOWN facts**

UNKNOWNs deliberately include account-specific fees, live latency, IOC fill behavior, realized slippage, credential capability boundaries, external reference-feed semantics, and actual historical-period completeness.

## Validation

- Local TASK-002 unit tests: **10/10 PASS**
- local compileall: **PASS**
- GitHub lock verification: **PASS**
- Ruff lint: **PASS**
- Ruff format: **PASS**
- strict mypy: **PASS**
- pytest Python 3.12: **PASS**
- pytest Python 3.13: **PASS**
- final green CI run: `35879318573`

## Definition of Done

All TASK-002 completion criteria passed.

## Next task

`TASK-003 — Strict recorder configuration and instrument registry`.
