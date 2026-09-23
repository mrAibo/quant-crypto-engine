# TASK-005 — Append-Only Raw Framed Writer

## Status

`COMPLETE`

Merged as PR #5 in commit `544bf8ad0f4c04468035e0af9a4e260f3b39f187`.

## Objective

Implement an append-only framed raw log that preserves exact source bytes with capture metadata and safely recovers an incomplete final frame without hiding corruption.

## Delivered

- `src/cryptobot/data/rawlog.py`
- `tests/unit/test_rawlog.py`
- `tests/fault/test_rawlog_tail.py`
- `artifacts/stage_0/rawlog_report.json`
- `tasks/TASK_006.md`

## Decisions

- QCR1 deterministic binary frame format.
- Payload bytes are preserved unchanged.
- Metadata encoding is canonical JSON.
- Payload and whole-frame SHA-256 recorded.
- `append()` does not claim fsync durability.
- `sync()` flushes + fsyncs and advances durable length.
- INCOMPLETE tail may be explicitly truncated to valid prefix.
- CORRUPT/middle corruption is never auto-truncated.

## Validation

Final GitHub Actions run `35892726690`:

- Ruff lint: PASS
- Ruff format: PASS
- strict mypy: PASS
- pytest Python 3.12: PASS
- pytest Python 3.13: PASS

## Next task

`TASK-006 — Raw segment sealing and manifest recovery`.
