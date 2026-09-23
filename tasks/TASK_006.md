# TASK-006 — Raw Segment Sealing and Manifest Recovery

## Status

`VALIDATED — MERGE PENDING`

## Objective

Add crash-safe segment publication and a durable manifest around the TASK-005 raw frame log.

## Delivered

- `src/cryptobot/data/manifest.py`
- `tests/unit/test_manifest.py`
- `tests/fault/test_manifest_commit.py`
- `artifacts/stage_0/storage_recovery_report.json`

## Publication contract

Segment publication sequence:

1. require CLEAN raw scan;
2. flush/fsync the open segment;
3. derive byte length, SHA-256, frame count, receive-time range, ingest-sequence range and source IDs;
4. atomically rename open → sealed;
5. fsync sealed-file parent directory;
6. canonical manifest temp write;
7. flush/fsync temp manifest;
8. atomic replace temp → canonical manifest;
9. fsync manifest parent directory.

Manifest validity requires both sealed-file content integrity and derived metadata parity.

## Recovery states

- VALID
- MISSING
- MISMATCH
- ORPHAN_COMPLETE
- OPEN_RECOVERABLE
- OPEN_INCOMPLETE_RECOVERABLE
- CORRUPT
- STALE_MANIFEST_TEMP
- MANIFEST_CORRUPT

No orphan/mismatched bytes are silently deleted or accepted.

## Fault injection

Crash boundaries covered:

- before/after segment fsync;
- after segment rename;
- after segment directory fsync;
- before/after manifest temp write;
- after manifest temp fsync;
- after manifest replace;
- after manifest directory fsync.

## Validation

GitHub Actions run `35893691800`:

- Ruff lint: **PASS**
- Ruff format: **PASS**
- strict mypy: **PASS**
- pytest Python 3.12: **PASS**
- pytest Python 3.13: **PASS**
- repository tests: **116 PASS**

## Definition of Done

1. Clean raw segments seal to checksum-addressed immutable artifacts. **PASS**
2. Manifest commit is atomic/durable at Stage 0 scope. **PASS**
3. Supported crash states classify deterministically. **PASS**
4. Orphans/mismatches are never silently deleted or accepted. **PASS**
5. Python 3.12/3.13 tests green. **PASS**
6. Ruff/format/strict-mypy/full pytest green. **PASS**
7. TASK-007 defined before merge. **PASS**

## Next task

`TASK-007 — Hyperliquid raw public WebSocket adapter`.

Before implementing network code, re-verify current Hyperliquid public WebSocket endpoints and subscription schemas against official documentation and update the evidence contract if needed.

## Do Not Build

- normalization
- Parquet
- reference-venue adapter
- strategy/trading code
