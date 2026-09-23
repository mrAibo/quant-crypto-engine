# Project Status

> **Continuation entry point:** Read this file first in every new chat/session, then read the referenced current task. Treat this repository as the source of truth over conversational memory.

## Project

- Repository: `mrAibo/quant-crypto-engine`
- Current branch: `task-003-recorder-config`
- Current phase: **Stage 0 — Evidence Contract and Market-Data Recorder**
- Current work package: **TASK-003 / S0-WP03 — Strict recorder configuration and instrument registry (validated; merge pending)**
- Completed: **TASK-001, TASK-002**
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

## Current task

Read **[`tasks/TASK_003.md`](tasks/TASK_003.md)**.

TASK-003 implementation now exists on the feature branch:

- strict recorder configuration parser;
- strict instrument registry;
- canonical instrument IDs;
- Hyperliquid BTC PRIMARY / ETH REPLICATION registry;
- explicit nulls for unverified metadata;
- required-but-unselected reference feed;
- explicit nulls for unmeasured operational thresholds;
- config and registry unit tests;
- `artifacts/stage_0/config_report.json`.

No network or trading code has been added.

### Validation

TASK-003 passed GitHub Actions run `35890454291`:
Ruff, Ruff-format, strict mypy, pytest Python 3.12, and pytest Python 3.13 are all green.

### Exact next action

Run one closeout CI after documentation/artifact changes, then merge PR #3.

After merge, begin **[TASK-004 — immutable event envelope, exact numeric rules, and clock abstraction](tasks/TASK_004.md)**.

Do not implement a Hyperliquid WebSocket client until TASK-004 passes.

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
