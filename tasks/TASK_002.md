# TASK-002 — Implement the Evidence Contract

## Status

`IN REVIEW — LOCAL TESTS PASS, GITHUB CI PENDING`

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

`config/evidence.yaml` deliberately uses the JSON-compatible subset of YAML 1.2.

Reason:

- JSON is valid YAML 1.2.
- Python can validate it using the standard library.
- Stage 0 does not need a third-party YAML parser yet.
- This avoids a dependency/lock-file change for a configuration format that does not require YAML-only syntax.

A later migration to a full YAML parser would require an explicit format/schema decision and tests; it must not silently broaden accepted syntax.

## Contract fields

Each fact contains:

- stable `fact_id`;
- subject and narrow claim;
- `VERIFIED` or `UNKNOWN` status;
- verification scope;
- source URL and retrieval time when applicable;
- optional source hash;
- effective period;
- environment;
- verification artifact;
- limitations;
- re-verification triggers and optional due time;
- owner.

## Validation rules

- Unknown top-level/fact fields are rejected.
- Duplicate fact IDs are rejected.
- `VERIFIED` facts require non-`UNVERIFIED` scope, source URL, retrieval timestamp, and verification artifact.
- `UNKNOWN` facts may remain without source/value instead of inventing one.
- Source URLs must use HTTPS.
- Source hashes, when present, must use `sha256:<64 lowercase hex>`.
- Effective ranges must be ordered.
- Reverification due status is reported but is not silently converted into a different fact status.
- Missing source hashes on verified documentation are surfaced in the audit report.

## Seeded evidence

Current contract contains **21 facts**:

- **13 VERIFIED documented facts**, covering current Hyperliquid fees, maker rebate threshold, funding, public WebSocket subscriptions/semantics, order identifiers/TIF, scheduleCancel, API-wallet identity, nonce ownership, and historical archive limitations.
- **8 UNKNOWN facts**, deliberately preserving account-specific fees, live execution latency, IOC behavior, realized slippage, API-wallet withdrawal/transfer scope, external reference-feed selection/timestamp semantics, and actual historical-period completeness.

## Local validation

- `pytest tests/unit/test_evidence.py`: **10 passed**
- `compileall`: **PASS**

Ruff/mypy are not installed in the local sandbox and will be validated by GitHub Actions using the already committed lock file.

## Definition of Done

1. Machine-readable contract is structurally strict. **IMPLEMENTED**
2. `VERIFIED` facts cannot exist without supporting source/scope. **IMPLEMENTED + TESTED**
3. `UNKNOWN` facts remain representable without fabricated values. **IMPLEMENTED + TESTED**
4. Reverification-due facts are reported. **IMPLEMENTED + TESTED**
5. Unknown fields and duplicate IDs are rejected. **IMPLEMENTED + TESTED**
6. Evidence report is reproducible. **IMPLEMENTED**
7. Full repository Ruff/mypy/pytest CI is green. **PENDING**
8. `STATUS.md` advances to TASK-003 only after merge. **PENDING**

## Next task after merge

TASK-003 — strict recorder configuration and instrument registry.

Do not start Hyperliquid recorder implementation before TASK-003 defines the configuration and symbol contracts.
