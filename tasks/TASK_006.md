# TASK-006 — Raw Segment Sealing and Manifest Recovery

## Status

`PENDING`

## Objective

Add crash-safe segment publication and a durable manifest around the TASK-005 raw frame log.

TASK-006 turns an appendable raw segment into an immutable, checksum-addressed sealed artifact and makes restart recovery deterministic across crashes around close, rename, manifest commit, and orphan-file discovery.

It does not add network ingest, normalization, Parquet, retention, or backup.

## Planned files

- `src/cryptobot/data/manifest.py`
- `tests/unit/test_manifest.py`
- `tests/fault/test_manifest_commit.py`
- `artifacts/stage_0/storage_recovery_report.json`

## Segment lifecycle

States:

1. `OPEN`
2. `SEALED_PENDING_MANIFEST`
3. `PUBLISHED`

A sealed segment is immutable. Publication is complete only when both the final file and durable manifest entry agree.

## Naming

Use deterministic IDs and explicit suffixes.

Example:

- open/temp: `segment-<id>.raw.open`
- sealed final: `segment-<id>.raw`

Do not infer state from filename alone; the manifest and file checksum must agree.

## Seal contract

Sealing must:

1. require a CLEAN raw-log scan;
2. sync/close the raw writer before publication;
3. compute whole-file SHA-256 and byte length;
4. atomically rename temp/open path to final path;
5. fsync the parent directory;
6. create a manifest record;
7. durably commit the manifest;
8. never mutate the sealed raw file afterwards.

## Manifest record

At minimum:

- manifest schema version;
- segment ID;
- relative final path;
- byte length;
- SHA-256;
- raw frame version;
- valid frame count;
- min/max receive wall ns if derivable from raw metadata;
- min/max ingest sequence;
- source IDs observed;
- created/sealed timestamps supplied by injected caller/clock value;
- recorder/schema version identifiers if available;
- publication status.

No business/market parsing is allowed.

## Manifest storage

Use a simple deterministic local manifest format suitable for Stage 0.

Recommended:

- one canonical JSON file containing immutable segment records, or
- append-only JSONL plus a deterministic compacted view.

Whichever is chosen must support atomic/durable replacement or append and crash recovery without silently dropping an already published segment.

Do not introduce a database.

## Atomic commit requirements

For file replacement:

- write `.tmp`;
- flush + fsync temp file;
- `os.replace` to canonical manifest path;
- fsync parent directory.

For segment publication:

- final rename must be atomic on the same filesystem;
- parent directory fsync required.

Cross-filesystem moves are forbidden.

## Recovery cases

On startup/recovery, classify:

1. manifest entry + matching sealed file → valid;
2. manifest entry + missing file → CORRUPT/BLOCKED;
3. manifest entry + checksum/length mismatch → CORRUPT;
4. sealed file with no manifest entry → ORPHAN_COMPLETE;
5. `.open` file with CLEAN log → OPEN_RECOVERABLE;
6. `.open` file with INCOMPLETE tail → truncate via TASK-005 helper, then OPEN_RECOVERABLE;
7. `.open` file with CORRUPT middle → CORRUPT/BLOCKED;
8. stale manifest temp file → recover or discard only according to deterministic rules based on canonical manifest validity.

No automatic deletion of unknown/orphaned bytes.

## Public API

Define small, explicit types/functions such as:

- `SegmentManifestRecord`
- `SegmentManifest`
- `seal_segment(...)`
- `load_manifest(...)`
- `commit_manifest(...)`
- `audit_storage(...)`
- `recover_open_segment(...)`

Exact naming may differ, but state/result types must be explicit.

## Tests

### Unit

- manifest canonical serialization;
- deterministic record ordering;
- duplicate segment ID rejection;
- path traversal/absolute path rejection;
- checksum and size verification;
- seal only CLEAN raw log;
- frame count/min/max metadata derivation;
- immutable final file expectation;
- manifest reload equality.

### Fault / crash points

Inject failures:

- before segment fsync;
- after segment fsync, before rename;
- after rename, before directory fsync;
- after rename, before manifest temp write;
- during manifest temp write;
- after manifest temp fsync, before replace;
- after manifest replace, before parent-directory fsync.

After each simulated crash, recovery must reach one deterministic classification without losing or silently replacing bytes.

Also test:

- orphan sealed file;
- missing manifest-referenced file;
- checksum mismatch;
- incomplete open segment recoverable;
- corrupt open segment blocked.

## Completion artifact

`artifacts/stage_0/storage_recovery_report.json` records:

- manifest schema version;
- segment state model;
- atomic commit sequence;
- recovery matrix;
- fault-injection coverage;
- CI status;
- known limitations.

## Definition of Done

1. Clean raw segments seal to immutable checksum-addressed files.
2. Manifest commit is atomic/durable at Stage 0 scope.
3. Restart recovery classifies every supported crash state deterministically.
4. Orphans/mismatches are never silently deleted or accepted.
5. Python 3.12/3.13 tests green.
6. Ruff/format/strict mypy/full pytest green.
7. `STATUS.md` advances to TASK-007.

## Do Not Build

- WebSocket clients.
- normalization.
- Parquet.
- retention/object-storage backup.
- strategy/trading code.
