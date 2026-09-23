# TASK-009 — Public Recorder Runtime, systemd Template, and Live Smoke Evidence

## Status

`PENDING`

## Objective

Turn the validated TASK-007 + TASK-008 components into the first runnable **public-data recorder process** and obtain short real-network smoke evidence from Hyperliquid without introducing trading credentials, normalization, strategy logic, or production execution.

This task is the bridge from deterministic offline tests to prospective native market-data capture.

## Core outputs

- executable public-recorder CLI;
- signal-aware graceful shutdown;
- explicit runtime configuration file for the smoke environment;
- systemd unit/template suitable for a Linux host;
- storage/audit command for completed raw capture;
- manual/automatable live-smoke command;
- smoke evidence artifact with observed queue, message, durability, reconnect, and storage facts;
- operational runbook.

## Planned files

- `src/cryptobot/runtime/public_recorder.py`
- `src/cryptobot/runtime/__init__.py`
- `src/cryptobot/cli.py` (minimal extension)
- `config/runtime/public-recorder-smoke.json`
- `deploy/systemd/quant-crypto-recorder.service`
- `docs/runbooks/public_recorder.md`
- `tests/unit/test_public_recorder_runtime.py`
- `tests/integration/test_public_recorder_runtime.py`
- `artifacts/stage_0/live_capture_smoke.json`

Exact names may vary if a smaller structure is cleaner.

## Binding scope

TASK-009 may:

- connect to Hyperliquid public WebSocket only;
- record BTC and ETH public channels already frozen in Stage 0;
- instantiate TASK-007 adapter and TASK-008 supervisor;
- create host/boot/run IDs;
- create storage directories;
- respond to SIGINT/SIGTERM;
- run for an explicit finite smoke duration or until signal;
- audit sealed output after exit;
- report observed recorder metrics;
- provide a systemd unit with no secrets.

TASK-009 must not:

- use private/account WebSocket channels;
- use API keys or signing wallets;
- place/cancel orders;
- normalize market payloads;
- compute strategy features;
- write Parquet;
- infer profitability;
- treat one smoke run as completeness evidence.

## Runtime composition

The runtime must explicitly compose:

```
Recorder runtime config
  -> SystemClock
  -> HyperliquidPublicAdapter
  -> ReconnectPolicy
  -> RecorderSupervisor
  -> RawLog / seal_segment / manifest
```

No hidden globals.

## Runtime configuration

Create a dedicated smoke/runtime config rather than changing the intentional UNKNOWN/null values in the Stage-0 research config silently.

At minimum freeze for the smoke run:

- source ID;
- endpoint;
- BTC/ETH coins;
- l2Book/bbo/trades/activeAssetCtx;
- queue capacity;
- sync-every-frames;
- shutdown drain timeout;
- reconnect base/max/jitter;
- heartbeat idle;
- WebSocket max-message size;
- receive queue high-water;
- open/close timeout;
- storage root;
- manifest path;
- optional finite run duration.

Every chosen value must be labeled:

- `MEASURED`,
- `SAFETY_DEFAULT`,
- `DOCUMENTED_CONSTRAINT`,
- or `EXPERIMENTAL`.

Do not imply that smoke values are final production values.

## Signal and lifecycle behavior

Required:

1. start in explicit STARTING state;
2. validate all config before network access;
3. create clock/run identity;
4. start adapter + supervisor;
5. on SIGINT/SIGTERM call `request_stop()`;
6. allow bounded drain;
7. sync and seal if clean;
8. run storage audit;
9. exit non-zero on failed/timed-out capture;
10. emit one machine-readable final summary.

A second termination signal may force immediate cancellation, but this must be explicit and tested.

## systemd unit

The service must:

- run as a dedicated non-root user placeholder;
- use an explicit working directory;
- use an explicit runtime config path;
- restart only on abnormal failure, not in a tight loop;
- set a bounded restart delay compatible with Hyperliquid documented connection-rate constraints;
- use `KillSignal=SIGTERM`;
- allow enough stop time for configured drain/seal;
- not contain credentials;
- set conservative filesystem protections where compatible with the recorder's data directory;
- write application logs to stdout/stderr/journald;
- document where raw data and manifest live.

Do not over-engineer sandboxing if it prevents raw-data writes; document trade-offs.

## Live smoke

A real smoke run must be deliberately short and public-only.

Target evidence:

- connection established;
- all configured subscription ACKs observed;
- market frames captured;
- heartbeat/reconnect behavior observed if it naturally occurs or tested separately;
- raw segment sealed;
- manifest audit VALID;
- exact frame count;
- bytes written/durable;
- queue high-water mark;
- run duration;
- messages per second overall and by top-level channel;
- connection IDs seen;
- any malformed/unknown frames;
- any reconnect count;
- shutdown outcome;
- host/runtime version metadata.

Do not claim channel completeness from the smoke run.

## Environment limitation handling

The default automated CI remains network-independent.

Live Hyperliquid smoke is **not** a required GitHub Actions test.

If the current execution environment cannot resolve/connect to external Internet:

1. do not weaken the task;
2. finish all offline code/tests/systemd/runbook;
3. generate a self-contained command/prompt for an Internet-enabled harness;
4. require that harness to return:
   - command output;
   - `live_capture_smoke.json`;
   - resulting manifest/audit summary;
   - no code changes outside the explicit smoke task unless needed for a demonstrated bug.

The returned evidence must be committed only after review.

## Tests

### Unit

- runtime-config parser/validation;
- run identity generation;
- host/boot ID derivation/fallback;
- finite-duration validation;
- exit-code mapping;
- signal state transitions;
- final summary serialization;
- no private/trading fields accepted.

### Integration

Using fake TASK-007 WebSocket server:

- runtime composes adapter + supervisor end-to-end;
- finite run exits cleanly;
- SIGTERM-equivalent stop drains and seals;
- output audit is VALID;
- summary counts match replayed raw log;
- nonzero exit on storage failure;
- reconnect/resubscribe reflected in summary.

### systemd/static

Tests or static checks verify:

- no credentials;
- correct ExecStart;
- explicit user/working directory/config;
- restart delay >= TASK-007 connection-rate floor;
- graceful SIGTERM;
- bounded stop timeout.

## Completion artifact

`artifacts/stage_0/live_capture_smoke.json` must contain two sections:

1. `offline_validation`
2. `live_observation`

Until a real smoke succeeds, `live_observation.status` remains `NOT_RUN`, never fabricated.

After a successful real run it records only actually observed facts.

## Definition of Done

1. Public recorder executable exists.
2. Runtime config is strict and explicit.
3. SIGINT/SIGTERM shutdown is bounded and seals clean output.
4. systemd template/runbook exist and contain no secrets.
5. Offline fake-server tests are green.
6. CI remains network-independent.
7. At least one real Hyperliquid public smoke run succeeds in an Internet-enabled environment.
8. Smoke raw storage audits VALID.
9. `live_capture_smoke.json` contains observed metrics, not guesses.
10. No normalization/strategy/trading code introduced.
11. Ruff/format/strict mypy/pytest green on Python 3.12/3.13.
12. `STATUS.md` advances to TASK-010.

## Do Not Build

- private account ingestion;
- wallet/signing support;
- order execution;
- strategy/risk logic;
- normalized L2/BBO/trade models;
- Parquet;
- Prometheus/Grafana;
- Docker/Kubernetes;
- remote orchestration;
- production HA/failover.
