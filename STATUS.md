# Project Status

> **Continuation entry point:** Read this file first in every new chat/session. Then read the referenced current task.

## Project

- Repository: `mrAibo/quant-crypto-engine`
- Current branch: `task-002-evidence-contract`
- Current phase: **Stage 0 — Evidence Contract and Market-Data Recorder**
- Current work package: **TASK-002 / S0-WP02 — Evidence Contract (validated; merge pending)**
- Previous work package: **TASK-001 COMPLETE**
- Economic status: **UNPROVEN**
- Live-trading status: **FORBIDDEN**
- Production execution work before Gate 1: **FORBIDDEN**

## Primary objective

Determine, as cheaply and scientifically as possible, whether an automated cryptocurrency strategy can produce reproducible **positive net expectancy after all real costs**. If the evidence survives, evolve the same core architecture toward unattended 24/7 trading.

A win rate above 50% is descriptive only, not the optimization objective.

## Settled scope

- Crypto only for now.
- Hyperliquid is the current execution candidate, not an assumption of profitability.
- BTC primary; ETH replication/generalization.
- One external reference feed will be selected/frozen during Stage 0.
- Python 3.12+ layered/modular monolith.
- Taker-only first economic validation.
- Maker execution is a later live-measurement branch.
- Deterministic rules → regularized logistic regression → optional LightGBM.
- GPT has no runtime role in v1.
- Jev gets only one initial bounded veto/ranking hypothesis.
- No autonomous self-modification.
- Human approval is required for strategy releases, capital increases, hard-risk changes, and reset of a latched halt.

## Binding project principles

1. First deliverable is a trustworthy evidence system, not a trading bot.
2. Raw market data must be immutable and replayable.
3. Point-in-time availability and missingness are explicit.
4. Core strategy/risk logic contains no exchange/network/filesystem I/O.
5. Research/replay/shadow/paper/live reuse stable strategy/risk/ledger contracts.
6. Costs are accounted once; no double-counting of spread/depth/latency/funding/fees.
7. No production signer/OMS/watchdog deployment before Gate 1.
8. Later live order intent is durable before transmission.
9. Ambiguous writes are never blindly retransmitted.
10. Reconciled exchange evidence is authoritative for orders/fills/positions/cash.
11. Emergency paths do not depend on optional AI/models.
12. Production restart begins in recovery.
13. Automatic scale-down is allowed; automatic scale-up is forbidden.
14. Independent watchdog required before unattended live operation.

## Stage sequence

Stage 0 → Stage 0.5 → Stage 1 → Stage 2 → **Gate 1** → Replay → Shadow/Paper → OMS/Recovery → Watchdog/Chaos → Micro-live → optional Jev/Maker → controlled scaling.

## Completed

### TASK-001 — repository bootstrap

Merged PR #1.

Validated:

- committed `uv.lock`;
- Python 3.12 and 3.13 compatibility;
- Ruff lint/format;
- strict mypy;
- pytest;
- read-only GitHub Actions CI.

See `artifacts/stage_0/bootstrap_report.json`.

## Current TASK-002 implementation

Implemented:

- strict evidence data model and validator;
- JSON-compatible YAML 1.2 configuration with zero new parser dependency;
- human-readable source/provenance notes;
- evidence audit report;
- 10 unit tests;
- 21 initial facts:
  - 13 VERIFIED documented facts;
  - 8 intentionally UNKNOWN facts.

Important preserved UNKNOWNs include:

- actual future project-account fee rates;
- mainnet submit-to-ACK latency;
- IOC partial-fill/rejection distributions;
- realized slippage/own-order impact;
- API-wallet transfer/withdrawal capability boundaries;
- external reference-feed selection and timestamp/completeness guarantees;
- actual completeness of any imported historical period.

This is intentional: the project must not turn review-model assumptions or generic documentation into observed production facts.

### Validation

- TASK-002 unit tests: **10/10 PASS**
- compileall: **PASS**
- GitHub Ruff lint: **PASS**
- GitHub Ruff format: **PASS**
- GitHub strict mypy: **PASS**
- GitHub pytest Python 3.12: **PASS**
- GitHub pytest Python 3.13: **PASS**
- Green CI run: `35879128871`

## Current verified documentation baseline

Checked against official Hyperliquid documentation on 2026-09-23:

- base perps fee schedule 0.045% taker / 0.015% maker;
- first maker rebate tier above 0.5% weighted maker volume;
- funding paid hourly with documented oracle-price-based payment formula;
- public `l2Book`, `trades`, `bbo`, `activeAssetCtx` subscriptions;
- `WsBook` documented as snapshot feed, but actual cadence must still be measured;
- `cloid`, ALO/IOC/GTC, `scheduleCancel` documented;
- API wallets sign for an account but account queries use the actual account/subaccount address;
- nonces are per signer;
- historical archive may be delayed/missing and cannot replace native receive-time capture.

Human-readable provenance is in `docs/evidence_sources.md`.

## Exact next action

Merge PR #2 after the closeout commit receives green CI.

After merge, current work package becomes:

**[TASK-003 — strict recorder configuration and instrument registry](tasks/TASK_003.md).**

Recorder network code must not start before TASK-003 is complete.

## User actions currently required

**None.**

If a blocker cannot be bypassed safely with the connected tooling, provide a complete self-contained prompt for another harness (e.g. DeepSeek) instead of lowering the quality/test bar.

## Open decisions intentionally deferred

- external reference venue/feed;
- recorder VM/provider/region;
- production signing-key topology;
- operational threshold values;
- capital amounts/scaling ladder;
- software license.

## Rules for future sessions

1. Read `STATUS.md` first.
2. Read the current task file.
3. Every coding task needs tests.
4. Run relevant tests before merge.
5. Update `STATUS.md` on material progress/decisions.
6. Preserve failed experiments and UNKNOWN facts.
7. Never commit secrets or credentials.
8. Do not skip economic/safety gates.
9. Stop and document architectural conflicts before coding around them.
10. Prefer small correct commits over speculative breadth.
