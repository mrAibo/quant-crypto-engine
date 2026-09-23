# TASK-002 — Implement the Evidence Contract

## Status

`VALIDATED — MERGE PENDING`

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

`config/evidence.yaml` uses the JSON-compatible subset of YAML 1.2. JSON is valid YAML 1.2 and can be parsed with the Python standard library, so Stage 0 does not add a parser dependency merely for configuration syntax.

## Contract guarantees

- Unknown top-level and fact fields are rejected.
- Duplicate fact IDs are rejected.
- `VERIFIED` requires a non-`UNVERIFIED` scope, source URL, retrieval timestamp, and verification artifact.
- `UNKNOWN` may remain without a source/value rather than inventing one.
- HTTPS source URLs are required when present.
- Source hashes, when present, use `sha256:<64 lowercase hex>`.
- Effective date ranges are validated.
- Re-verification triggers are explicit and non-empty.
- Re-verification due state is reported.
- Missing retained source hashes for documented facts are surfaced as audit warnings.

## Seeded evidence

The initial contract contains **21 facts**:

- **13 VERIFIED documented facts** covering current Hyperliquid fee schedule, maker rebate threshold, funding, public WebSocket semantics, order identifiers/TIF, scheduleCancel, API-wallet identity, nonce ownership, and historical archive limitations.
- **8 intentionally UNKNOWN facts** covering project-account fees, live latency, IOC behavior, realized slippage, credential transfer/withdrawal scope, reference-feed selection/timestamp semantics, and historical-period completeness.

## Validation

Local:
- TASK-002 unit tests: **10/10 PASS**
- compileall: **PASS**

GitHub Actions:
- committed lock verification: **PASS**
- dependency sync: **PASS**
- Ruff lint: **PASS**
- Ruff format: **PASS**
- strict mypy: **PASS**
- pytest Python 3.12: **PASS**
- pytest Python 3.13: **PASS**

CI run: `35879128871`.

## Definition of Done

1. Strict machine-readable contract exists. **PASS**
2. Unsupported facts can remain explicitly unknown. **PASS**
3. Verified facts require provenance. **PASS**
4. Re-verification is represented and tested. **PASS**
5. Duplicate IDs and unknown fields fail validation. **PASS**
6. Human-readable provenance exists. **PASS**
7. Full repository CI is green. **PASS**
8. Next task is defined before merge. **PASS**

## Next task

`TASK-003 — Strict recorder configuration and instrument registry`.
