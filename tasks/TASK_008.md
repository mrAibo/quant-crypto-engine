# TASK-008 — Recorder Supervisor and Raw-Writer Integration

## Status

`IN REVIEW — IMPLEMENTED, GITHUB CI PENDING`

## Objective

Compose the validated TASK-007 Hyperliquid public adapter with the TASK-005 raw framed writer and TASK-006 segment lifecycle behind one recorder supervisor.

TASK-008 creates the first end-to-end **raw capture pipeline**:

```
Hyperliquid WS
   ↓
HyperliquidPublicAdapter
   ↓
bounded in-memory queue
   ↓
Recorder supervisor
   ↓
RawLog (.raw.open)
```

It must preserve every received application payload delivered by the adapter, surface overload/failure explicitly, and shut down without falsely claiming un-synced bytes are durable.

This task still does **not** normalize market events or write Parquet.

## Planned files

- `src/cryptobot/data/recorder.py`
- `src/cryptobot/cli.py`
- `tests/unit/test_recorder.py`
- `tests/integration/test_recorder_pipeline.py`
- `tests/fault/test_recorder_supervisor.py`
- `artifacts/stage_0/recorder_smoke.json`

Existing files may receive minimal changes when required:

- `src/cryptobot/adapters/hyperliquid/public.py`
- `src/cryptobot/data/rawlog.py`
- `src/cryptobot/data/manifest.py`
- `src/cryptobot/config.py`

## Binding scope

The supervisor owns:

- source lifecycle;
- bounded queue between network receive and raw persistence;
- mapping `CapturedPublicFrame → RawLog.append(metadata, payload)`;
- segment-open path;
- explicit sync cadence supplied by runtime settings;
- graceful shutdown;
- failure propagation;
- recorder status/metrics snapshots suitable for later reporting;
- safe handoff to TASK-006 sealing at deliberate rollover/shutdown points.

The supervisor does **not** own:

- Hyperliquid protocol parsing beyond TASK-007;
- normalized market events;
- Parquet;
- feature computation;
- trading;
- business-data gap inference;
- production deployment/systemd.

## Runtime settings contract

Introduce a strict immutable recorder-runtime settings type rather than silently converting the intentional `null` values in Stage-0 project config into guessed defaults.

At minimum require:

- `queue_capacity`;
- `sync_every_frames` and/or `sync_interval_seconds`;
- `segment_max_bytes` or an explicit "no automatic rollover in this task" mode;
- reconnect policy values;
- TASK-007 transport values;
- shutdown drain timeout.

Rules:

- all queues are bounded;
- no zero/unlimited sentinel values;
- values must be explicitly supplied by composition/tests;
- TASK-008 does not write guessed numbers back into `config/recorder.yaml`;
- actual deployment values are frozen in TASK-009 after smoke measurement.

## Queue semantics

The queue element must carry the complete `CapturedPublicFrame` or an equivalent immutable capture record.

Required behavior:

1. The adapter capture timestamp occurs before queueing.
2. Writer preserves adapter ordering.
3. No silent drop policy.
4. When queue reaches capacity, producer backpressure is allowed.
5. Queue occupancy/high-water mark is measured.
6. If persistence failure means capture can no longer be trusted, the supervisor stops/reconnects rather than pretending coverage continued.
7. Backpressure/disconnect intervals must be reportable later; TASK-008 may expose status facts without inventing business-message loss counts.

Do **not** add "drop oldest" or "drop market snapshots" optimization in this task.

## Raw-log integration

For every adapter frame:

- use the exact `RawFrameMetadata` emitted by TASK-007;
- append the exact payload bytes;
- retain `RawRef` for accounting/testing if useful;
- do not parse/re-serialize payload before writing;
- sync according to explicit runtime policy;
- after `sync()`, update durable accounting;
- close does not retroactively claim unsynced bytes were durable.

## Segment lifecycle

Initial segment path must use TASK-006 convention:

- open: `segment-<id>.raw.open`;
- final sealed path: `segment-<id>.raw`.

A segment ID must be deterministic/auditable enough to avoid accidental collision. It may include source, UTC start supplied by clock, and a unique connection/session identifier.

For deliberate segment close:

1. stop adding new frames to that segment;
2. `RawLog.sync()`;
3. close;
4. call TASK-006 `seal_segment`;
5. commit manifest;
6. only then open successor segment.

If sealing fails, do not delete/overwrite the bytes and do not continue as if publication succeeded.

Automatic time/size rollover may remain disabled in TASK-008 if implementing it would mix TASK-009 deployment policy into the supervisor. Explicit/manual/test rollover is sufficient for this task.

## Graceful shutdown

On requested shutdown:

1. stop starting new sessions/reconnects;
2. allow already captured frames to drain up to configured timeout;
3. sync raw log;
4. close;
5. seal segment if clean and policy requests seal-on-shutdown;
6. expose whether shutdown was:
   - CLEAN_DURABLE;
   - CLEAN_UNSEALED;
   - TIMED_OUT;
   - FAILED.

Never discard queued frames silently.

## Failure semantics

Define explicit supervisor failure/status types for at least:

- adapter/network termination;
- producer task failure;
- writer task failure;
- raw-log append failure;
- fsync failure;
- queue drain timeout;
- sealing/manifest failure;
- cancellation during shutdown.

A writer/storage error is fatal to trusted capture. Network reconnect is adapter-owned and not automatically a storage error.

## Public API

Keep the surface small, for example:

- `RecorderRuntimeSettings`;
- `RecorderStatus`;
- `RecorderCounters`;
- `RecorderSupervisor.run()`;
- `RecorderSupervisor.request_stop()`;
- `RecorderSupervisor.snapshot()`.

Exact naming may differ.

The supervisor should accept ports/dependencies (frame source, raw-log/segment factory, clock/sleep where required) so tests can run without live Internet.

## CLI scope

`src/cryptobot/cli.py` may expose a minimal command needed for later deployment, but must remain safe:

- `python -m cryptobot.cli ...` or a project script;
- no secrets;
- no trading credentials;
- no implicit mainnet execution beyond public feed capture;
- required runtime settings explicit;
- dry configuration validation possible without network.

Do not build a general CLI framework.

## Tests

### Unit

- runtime-settings validation;
- queue/counter state transitions;
- graceful stop state;
- segment-ID/path safety;
- exact capture metadata/payload mapping;
- status snapshot immutability;
- writer failure classification.

### Integration

Use a fake async frame source or TASK-007 fake server:

- frames traverse source → bounded queue → RawLog;
- replay raw frames and prove payload bytes/metadata equal source frames;
- ordering preserved;
- sync boundaries reflected in durable accounting;
- deliberate clean shutdown seals a valid segment and manifest;
- restart/audit sees sealed output as VALID.

### Backpressure

With a deliberately blocked writer:

- producer eventually blocks on bounded queue;
- queue never exceeds configured capacity;
- no frames disappear;
- high-water mark is recorded;
- release writer and prove all accepted frames persist in order.

### Fault

Inject:

- append exception;
- sync exception;
- seal exception;
- writer task cancellation;
- stop while queue non-empty;
- drain timeout.

Each must end in a deterministic status and leave bytes/audit state truthful.

## Completion artifact

`artifacts/stage_0/recorder_smoke.json` records:

- supervisor contract/version;
- queue semantics;
- runtime settings used in tests;
- durability policy;
- segment lifecycle;
- shutdown states;
- fault matrix;
- test counts;
- CI status;
- known limitations.

## Definition of Done

1. TASK-007 frames flow end-to-end into TASK-005 raw storage.
2. Payload bytes and capture metadata round-trip exactly.
3. Queue is bounded and never silently drops.
4. Durable accounting only advances after sync.
5. Clean close can publish a TASK-006 valid sealed segment.
6. Storage failures fail capture honestly.
7. Backpressure and shutdown are covered by tests.
8. No normalization/Parquet/trading code is introduced.
9. Python 3.12/3.13 tests green.
10. Ruff/format/strict mypy/full pytest green.
11. `STATUS.md` advances to TASK-009.

## Do Not Build

- production VM/systemd deployment (TASK-009);
- Hyperliquid normalized L2/BBO parsing (TASK-010);
- trade normalization (TASK-011);
- funding/mark/oracle normalization (TASK-012);
- external reference adapter (TASK-013);
- Parquet;
- strategy/features/backtest;
- OMS/signing/trading.


## Implementation status

Implemented:

- bounded async recorder supervisor;
- explicit immutable runtime settings;
- network-source-independent capture-frame protocol;
- exact metadata/payload mapping into QCR1;
- explicit sync/durable accounting;
- deterministic safe segment IDs;
- clean seal/manifest handoff;
- graceful stop and bounded drain;
- producer/writer/storage failure classification;
- network-free runtime validation CLI;
- end-to-end, backpressure, and fault tests;
- `artifacts/stage_0/recorder_smoke.json`.

No normalization, Parquet, reference venue, strategy, execution, or trading code is present.

## Validation status

GitHub CI: **PENDING**.
