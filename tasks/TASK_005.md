# TASK-005 — Append-Only Raw Framed Writer

## Status

`IN REVIEW — IMPLEMENTED, GITHUB CI PENDING`

## Objective

Implement the first durable market-data storage primitive: an append-only framed raw log that preserves the exact bytes received from a source together with capture metadata and can recover safely from an incomplete tail after process death.

This task stores bytes only. It does not parse venue payloads, normalize events, seal manifests, or materialize Parquet.

## Planned files

- `src/cryptobot/data/rawlog.py`
- `tests/unit/test_rawlog.py`
- `tests/fault/test_rawlog_tail.py`
- `artifacts/stage_0/rawlog_report.json`

## Frame format v1

Use a deterministic binary frame with explicit versioning.

Logical layout:

1. 4-byte magic: `QCR1`
2. 4-byte unsigned big-endian metadata length
3. 8-byte unsigned big-endian payload length
4. metadata bytes: canonical UTF-8 JSON
5. payload bytes: **unchanged bytes received from the source**
6. 32-byte SHA-256 checksum over items 1–5

No compression inside a frame. Segment compression/sealing is a later task.

## Required metadata

At minimum:

- frame schema version;
- source ID;
- local receive wall ns;
- local receive monotonic ns;
- host ID;
- boot ID;
- connection ID;
- local ingest sequence;
- optional content type / channel hint;
- capture flags.

Metadata is capture metadata only. Do not parse or copy venue business fields into the raw-frame header.

## API contract

Define:

- `RawFrameMetadata` immutable type.
- `RawRef` immutable return type containing:
  - segment ID;
  - byte offset;
  - total frame length;
  - payload length;
  - payload SHA-256;
  - frame checksum.
- `RawLog.open(path, segment_id, ...)`
- `RawLog.append(metadata, payload) -> RawRef`
- `RawLog.sync()`
- `RawLog.close()`
- reader/scan helper capable of validating frames and identifying the first invalid/incomplete tail offset.

The public API must distinguish **written** from **durable** data. `append()` alone must not falsely claim fsync durability.

## Durability semantics

- Append-only file.
- No in-place mutation of committed frames.
- `sync()` flushes Python buffers and performs `fsync`.
- Caller may define a later batching policy; TASK-005 does not invent a production fsync interval.
- On restart, scan frames in order.
- Valid prefix is preserved.
- Only an incomplete/corrupt **tail frame** may be truncated automatically.
- Corruption inside a previously valid middle section is not silently repaired; raise a corruption error.
- Empty file is valid.
- Unknown frame version/magic fails closed.

## Validation requirements

- Metadata serialized deterministically (sorted keys, stable separators, UTF-8).
- Payload bytes reproduced exactly.
- Empty payload supported.
- Large payload supported.
- Length fields validated before allocation/read.
- SHA-256 verified.
- Corrupt checksum rejected.
- Truncated header, metadata, payload, or checksum identified as incomplete tail.
- Garbage after a valid frame identified.
- Multiple frames scan/replay in append order.
- `RawRef.offset` points to exact frame start.
- `sync()` calls fsync on the underlying file descriptor.
- Writer cannot append after close.
- Writer cannot accept text payload accidentally; payload API is bytes-only.
- No network calls.
- No normalized-event dependency.

## Recovery behavior

Provide an explicit scan result, for example:

- valid frame count;
- valid byte length;
- tail state: CLEAN / INCOMPLETE / CORRUPT;
- first bad offset.

Automatic truncation helper may truncate only when the bad offset begins at the tail after a valid prefix and the failure is classified as incomplete tail.

Do not conflate checksum corruption with an ordinary crash-tail truncation unless the evidence proves only the final frame is affected.

## Tests

### Unit

- one frame round-trip;
- multiple frame ordering;
- deterministic metadata bytes;
- payload exactness;
- empty payload;
- large payload;
- RawRef offsets/lengths;
- checksum failure;
- invalid magic/version;
- append-after-close;
- bytes-only payload;
- fsync invocation.

### Fault/tail

Parameterize truncation at:

- magic;
- length fields;
- metadata;
- payload;
- checksum.

Verify valid-prefix recovery and safe tail classification.

Add a middle-frame corruption test proving it is not silently truncated away.

## Completion artifact

`artifacts/stage_0/rawlog_report.json` records:

- frame version;
- format layout;
- maximum configured/read-safe lengths;
- test matrix;
- CI result;
- known limitations.

## Implementation status

Implemented:

- deterministic QCR1 binary frame format;
- immutable capture metadata and RawRef types;
- append/sync/close semantics with explicit durable_length;
- exact payload SHA-256 and whole-frame checksum;
- scan/replay helpers;
- CLEAN / INCOMPLETE / CORRUPT classification;
- explicit incomplete-tail truncation helper;
- unit and fault tests covering torn tail and middle corruption.

No network/parser/Parquet/trading logic is present.

## Definition of Done

1. Raw bytes can be appended and replayed exactly. **IMPLEMENTED**
2. Frame checksums/lengths detect corruption. **IMPLEMENTED**
3. Torn-tail recovery preserves valid prefix without hiding middle corruption. **IMPLEMENTED**
4. Durability semantics are explicit and tested. **IMPLEMENTED**
5. Python 3.12/3.13 tests green. **PENDING CI**
6. Ruff/format/strict mypy/full pytest green. **PENDING CI**
7. `STATUS.md` advances to TASK-006. **PENDING**

## Do Not Build

- Segment manifest/sealing logic beyond the minimal frame scan/truncate primitive.
- Parquet writer.
- WebSocket clients.
- normalization.
- retention/backup.
- strategy/trading code.
