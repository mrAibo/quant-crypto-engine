# TASK-005 — Append-Only Raw Framed Writer

## Status

`VALIDATED — MERGE PENDING`

## Objective

Implement the first durable market-data storage primitive: an append-only framed raw log that preserves exact source bytes together with capture metadata and can recover safely from an incomplete tail after process death.

## Delivered

- `src/cryptobot/data/rawlog.py`
- `tests/unit/test_rawlog.py`
- `tests/fault/test_rawlog_tail.py`
- `artifacts/stage_0/rawlog_report.json`

## Frame format

`QCR1`:

1. 4-byte magic
2. 4-byte unsigned big-endian metadata length
3. 8-byte unsigned big-endian payload length
4. canonical UTF-8 JSON metadata
5. unchanged source payload bytes
6. 32-byte SHA-256 checksum over all preceding frame bytes

## Durability / recovery semantics

- `append()` writes but does not claim fsync durability.
- `sync()` flushes and fsyncs, then advances `durable_length`.
- CLEAN existing logs may be reopened for append.
- INCOMPLETE final frame may be explicitly truncated to the valid prefix.
- CORRUPT frames are never auto-truncated.
- middle-frame corruption is preserved as a hard error.
- raw payload is bytes-only.

## Validation

GitHub Actions run `35892543470`:

- Ruff lint: **PASS**
- Ruff format: **PASS**
- strict mypy: **PASS**
- pytest Python 3.12: **PASS**
- pytest Python 3.13: **PASS**

The test matrix includes round-trip, exact offsets, deterministic metadata, empty/large payloads, checksum/magic corruption, fsync, append-after-close, bytes-only payloads, torn-tail truncation across frame regions, middle-frame corruption, and garbage after a valid frame.

## Definition of Done

1. Raw bytes append/replay exactly. **PASS**
2. Length/checksum corruption detected. **PASS**
3. Torn-tail recovery preserves valid prefix without hiding middle corruption. **PASS**
4. Durability semantics explicit/tested. **PASS**
5. Python 3.12/3.13 tests green. **PASS**
6. Ruff/format/strict-mypy/full pytest green. **PASS**
7. TASK-006 defined before merge. **PASS**

## Next task

`TASK-006 — Raw segment sealing and manifest recovery`.

## Do Not Build

- Parquet writer
- WebSocket clients
- normalization
- retention/backup
- strategy/trading code
