# Project Status

> **Continuation entry point:** Read this file first in every new chat/session, then read the referenced current task. Treat this repository as the source of truth over conversational memory.

## Project

- Repository: `mrAibo/quant-crypto-engine`
- Current branch: `main`
- Current phase: **Stage 0 — Evidence Contract and Market-Data Recorder**
- Current work package: **TASK-010 / S0-WP10 — Hyperliquid L2/BBO normalization from raw capture**
- Completed: **TASK-001, TASK-002, TASK-003, TASK-004, TASK-005, TASK-006, TASK-007, TASK-008, TASK-009**
- Economic status: **UNPROVEN**
- Live trading: **FORBIDDEN**
- Production signer/OMS/watchdog before Gate 1: **FORBIDDEN**

## Primary objective

Determine whether an automated crypto strategy can produce reproducible **positive net expectancy after all real costs**, using the shortest scientifically defensible path. If evidence survives, evolve the same architecture toward unattended 24/7 trading.

Win rate above 50% is descriptive/preferable only; it is not the optimization target.

## Settled scope

- Crypto only for now.
- Hyperliquid is the current execution candidate, not a profitability assumption.
- BTC primary research market.
- ETH replication/generalization market.
- One external major-market reference feed to be selected/frozen during Stage 0.
- Python 3.12+ layered/modular monolith.
- Taker-only first economic validation.
- Maker execution deferred to a separately gated live-measurement experiment.
- Model sequence: deterministic rules → regularized logistic regression → optional LightGBM only if justified.
- GPT has no runtime role in v1.
- Jev receives only one initial bounded veto/ranking hypothesis after the core strategy is validated.
- No autonomous self-modification.
- Human approval required for strategy promotion, capital/risk increases, and latched-halt reset.

## Binding principles

1. The first product is a trustworthy evidence system, not a trading bot.
2. Raw data must be immutable and replayable.
3. Point-in-time availability and missingness are explicit.
4. Core strategy/risk logic contains no network/filesystem/exchange I/O.
5. Research/replay/shadow/paper/live reuse stable strategy/risk/ledger contracts.
6. Costs are counted once; no spread/depth/latency/funding/fee double counting.
7. No production execution stack before Gate 1.
8. Live order intent will be durable before transmission.
9. Ambiguous writes will never be blindly retransmitted.
10. Reconciled exchange evidence is authoritative for orders/fills/positions/cash.
11. Emergency paths do not depend on optional models/AI.
12. Production restarts begin in recovery, never RUNNING.
13. Automatic scale-down/halt is allowed; automatic scale-up is forbidden.
14. An independent watchdog is mandatory before unattended live operation.
15. Unknown facts remain UNKNOWN until specifically verified/measured.

## Stage sequence

Stage 0 → Stage 0.5 → Stage 1 → Stage 2 → **Gate 1** → Replay → Shadow/Paper → OMS/Recovery → Watchdog/Chaos → Micro-live → optional Jev/Maker → controlled scaling.

## Completed work

### TASK-001 — Repository bootstrap

PR #1, merge commit `ed9adb0fe868baeed955302bc3d50deaaa1cb7ca`.

Delivered:

- Python package skeleton.
- committed `uv.lock`.
- Python 3.12 primary and 3.13 compatibility checks.
- Ruff lint/format.
- strict mypy.
- pytest.
- read-only GitHub Actions CI.
- master architecture/evidence/gate/stage documentation.
- `STATUS.md` continuation mechanism.

Artifact: `artifacts/stage_0/bootstrap_report.json`.

### TASK-002 — Evidence contract

PR #2, merge commit `b10034fe26a1af1f48f4c3eaa8d5703abd041d7c`.

Delivered:

- `config/evidence.yaml` using JSON-compatible YAML 1.2.
- strict evidence parser/validator.
- official Hyperliquid provenance notes.
- re-verification rules/reporting.
- 10 evidence-specific unit tests.
- 21 initial facts: **13 VERIFIED / 8 intentionally UNKNOWN**.
- final Ruff/format/strict-mypy/pytest CI green on Python 3.12 and 3.13.

Artifact: `artifacts/stage_0/evidence_report.json`.

Important UNKNOWNs deliberately retained:

- actual future project-account fee rates;
- submit-to-ACK latency distribution;
- IOC partial-fill/rejection distribution;
- realized slippage/own-order impact;
- runtime API-wallet transfer/withdrawal capability boundaries;
- reference-feed selection and timing/completeness semantics;
- completeness of any actual imported historical period.

## Current verified documentation baseline

Checked against official Hyperliquid docs on 2026-09-23 and captured in the evidence contract:

- base perps schedule: 0.045% taker / 0.015% maker;
- first maker rebate tier begins above 0.5% weighted maker volume;
- funding paid hourly; documented payment formula uses oracle price;
- public `l2Book`, `trades`, `bbo`, `activeAssetCtx` channels;
- `WsBook` is documented as a snapshot feed; observed cadence must still be measured;
- `cloid`, ALO/IOC/GTC and `scheduleCancel` documented;
- API-wallet/account identity and per-signer nonce semantics documented;
- official historical archive may be delayed/incomplete and does not replace native receive-time capture.

Human-readable provenance: `docs/evidence_sources.md`.

## Completed — TASK-003

PR #3, merge commit `9dd9145342430ed3a09b1e1e90f2a9d9f02af304`.

Delivered:

- strict recorder configuration;
- canonical instrument registry;
- BTC PRIMARY / ETH REPLICATION project roles;
- explicit nulls for unverified metadata;
- required-but-unselected reference feed;
- explicit nulls for unmeasured operational thresholds;
- 33-test repository suite at the TASK-003 gate;
- final green CI run `35890625489`.

Artifact: `artifacts/stage_0/config_report.json`.

## Completed — TASK-004

PR #4, merge commit `dbc08c6a6f721b9f7e0f0cc0b5afb2e91c948659`.

Delivered:

- immutable normalized event envelope;
- 12 event-domain types;
- exact Decimal persistence policy;
- scaled-integer helpers;
- host/boot-safe clock abstraction;
- event/numeric/clock unit tests;
- final green CI run `35891870831`.

Artifact: `artifacts/stage_0/schema_v1.json`.

## Completed — TASK-005

PR #5, merge commit `544bf8ad0f4c04468035e0af9a4e260f3b39f187`.

Delivered:

- deterministic QCR1 raw frame log;
- exact source payload preservation;
- explicit write-vs-fsync durability semantics;
- payload/frame checksums;
- scan/replay helpers;
- safe torn-tail truncation;
- middle-corruption hard failure;
- final green CI run `35892726690`.

Artifact: `artifacts/stage_0/rawlog_report.json`.

## Completed — TASK-006

PR #6, merge commit `725e79e930534d3396bc399f2c7d4fa73af25bcc`.

Delivered:

- crash-safe raw segment sealing;
- checksum/length/frame/derived-metadata manifest integrity;
- atomic manifest publication;
- deterministic storage audit/recovery states;
- fault injection around every commit boundary;
- final green CI run `35893879796`.

Artifact: `artifacts/stage_0/storage_recovery_report.json`.

## Completed — TASK-007

PR #7, merge commit `2182268783293bc01b2d1ac5608e3f01de9877f1`.

Delivered:

- verified Hyperliquid public WebSocket protocol evidence;
- pinned `websockets==17.0.1`;
- exact raw application payload-byte capture;
- subscription/channel/heartbeat classification;
- bounded reconnect behavior;
- fake-server integration tests;
- third-party reuse register;
- final green CI run `35904060906`;
- **140 tests PASS** on Python 3.12 and 3.13.

Artifact: `artifacts/stage_0/hl_capture_probe.json`.

## Completed — TASK-008

PR #8, merge commit `069bddf1f8ef9aed1fc210bb46e690bc564cbb22`.

Delivered:

- bounded async capture queue with backpressure and no silent drops;
- exact TASK-007 frame → TASK-005 raw log persistence;
- fsync-based durable frame/byte accounting;
- deterministic segment IDs;
- TASK-006 seal/manifest handoff;
- graceful stop and bounded drain behavior;
- explicit producer/writer/append/sync/seal/cancellation failure states;
- network-free runtime validation CLI;
- end-to-end, backpressure, and fault tests;
- final green closeout CI run `35910694098`;
- **161 tests PASS** on Python 3.12 and 3.13.

Artifact: `artifacts/stage_0/recorder_smoke.json`.

## Completed — TASK-009

PR #9, merge commit `4470202c8030ab07acbf031d14968ff72bda2969`.

Delivered:

- strict labeled public-recorder runtime config;
- public-only runnable Hyperliquid recorder;
- host/boot/run identity;
- finite-duration and graceful signal stop path;
- storage audit CLI;
- systemd template and runbook;
- **173 tests PASS** on Python 3.12 and 3.13;
- strict mypy/Ruff/format PASS;
- real Hyperliquid public-only smoke run `35912388990`: **559 frames, 8/8 ACKs, 364893 durable bytes, queue HWM 1, CLEAN_DURABLE, audit VALID**;
- final network-independent closeout CI run `35912786539`;
- one-shot network workflow removed before merge.

Artifact: `artifacts/stage_0/live_capture_smoke.json`.

## Current task

Read **[`tasks/TASK_010.md`](tasks/TASK_010.md)**.

Objective: normalize Hyperliquid raw `l2Book` and `bbo` frames into the existing v1 event contracts with exact decimals, strict instrument mapping, deterministic event IDs, complete raw provenance, and structured parse failures.

### Mandatory first action

Re-verify the current official Hyperliquid `l2Book` / `bbo` message schemas, timestamp semantics, level fields, snapshot-vs-delta behavior, and optional aggregation/depth parameters before writing parser behavior. Record verified facts; leave undocumented semantics UNKNOWN.

No trade/funding/reference/feature/strategy code belongs in TASK-010.

## User actions currently required

**None.**

If a future blocker cannot be bypassed safely through available GitHub/CI tooling, provide a complete self-contained task prompt for another harness (for example DeepSeek) rather than weakening tests or quality gates.

## Open decisions intentionally deferred

- Final external reference venue/feed.
- Recorder VM/provider/region.
- Production signing-key topology.
- Operational timeout/staleness/watchdog thresholds.
- Capital amounts/scaling ladder.
- Software license.

## Rules for future sessions

1. Read `STATUS.md` first.
2. Read the current task file.
3. Every coding task requires tests.
4. Require green relevant CI before merge.
5. Update `STATUS.md` after each completed task/gate/material decision.
6. Preserve failed experiments and UNKNOWN facts.
7. Never commit credentials/secrets.
8. Do not skip economic/safety gates.
9. Stop and document architectural conflicts instead of coding around them.
10. Prefer small correct commits over speculative breadth.
