# TASK-006 — Raw Segment Sealing and Manifest Recovery

## Status

`COMPLETE`

Merged as PR #6 in commit `725e79e930534d3396bc399f2c7d4fa73af25bcc`.

## Objective

Add crash-safe segment publication and a durable manifest around the TASK-005 raw frame log.

## Delivered

- `src/cryptobot/data/manifest.py`
- `tests/unit/test_manifest.py`
- `tests/fault/test_manifest_commit.py`
- `artifacts/stage_0/storage_recovery_report.json`
- `tasks/TASK_007.md`

## Decisions

- Segment publication requires a CLEAN raw scan.
- Open segment is fsynced before rename.
- Sealed segment publication uses atomic rename + parent-directory fsync.
- Manifest commit uses canonical temp write + fsync + atomic replace + parent-directory fsync.
- Manifest validity checks file SHA-256, byte length, frame count and derived raw metadata.
- Orphan/missing/mismatched/corrupt states are never silently deleted or accepted.
- Incomplete open tail may use TASK-005 safe truncation; corrupt open segments are blocked.

## Validation

Final GitHub Actions run `35893879796`:

- Ruff lint: PASS
- Ruff format: PASS
- strict mypy: PASS
- pytest Python 3.12: PASS
- pytest Python 3.13: PASS
- repository tests: 116 PASS

## Next task

`TASK-007 — Hyperliquid Raw Public WebSocket Adapter`.

Before implementing network behavior, current official Hyperliquid WebSocket endpoint, subscription messages, message envelopes, keepalive guidance and documented limits must be re-verified.
