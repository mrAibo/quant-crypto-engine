# Project Status

> **Continuation entry point:** Read this file first in every new chat/session. Then read the referenced current task. Do not reconstruct project state from memory alone when this repository is available.

## Project

- Repository: `mrAibo/quant-crypto-engine`
- Current branch: `task-001-bootstrap` until TASK-001 is merged
- Current phase: **Stage 0 — Evidence Contract and Market-Data Recorder**
- Current work package: **TASK-001 / S0-WP01 — repository bootstrap and quality gate**
- Economic status: **UNPROVEN**
- Live-trading status: **FORBIDDEN**
- Production execution work before Gate 1: **FORBIDDEN**

## Primary objective

Determine, as cheaply and scientifically as possible, whether an automated cryptocurrency strategy can produce reproducible **positive net expectancy after all real costs**. If the evidence survives, evolve the same core architecture toward unattended 24/7 trading.

A win rate above 50% is desirable only as a descriptive characteristic; it is not the objective. Positive net expectancy, risk control, and operational safety are mandatory.

## Settled scope

- Crypto only for now; do not add equities or other asset classes.
- Hyperliquid is the current execution candidate, not an assumption of profitability.
- BTC is primary.
- ETH is replication/generalization and is reported separately.
- One external major-market reference feed will be selected/frozen during Stage 0.
- Python 3.12+.
- Layered/modular monolith through research and initial production.
- Taker-only for the first economic validation.
- Maker economics are a later, separate live-measurement workstream.
- Deterministic rules first, then regularized logistic regression, then LightGBM only if justified.
- GPT has no runtime role in v1.
- Jev is optional. Its only initial hypothesis is whether it ranks/vetoes bad candidate trades better than deterministic and classical controls.
- No autonomous self-modification.
- Human approval remains required for strategy releases, capital increases, hard-risk-limit changes, and reset of a latched halt.

## Settled architecture / safety principles

1. First deliverable is a trustworthy evidence system, not a trading bot.
2. Raw market data is immutable and replayable.
3. Point-in-time availability and missingness are explicit.
4. Core strategy/risk logic contains no exchange/network/filesystem I/O.
5. Research, replay, shadow, paper, and live should reuse the same strategy/risk/ledger contracts.
6. Spread/depth/latency/funding/fees must never be double-counted.
7. No production signer/OMS/watchdog deployment before Gate 1.
8. Later production intent must be durable before transmission.
9. Later ambiguous order writes must never be blindly retransmitted.
10. Reconciled exchange evidence is authoritative for orders/fills/positions/cash.
11. Emergency exit/cancel paths may not depend on Jev, GPT, or any optional model.
12. Production restart begins in recovery, not RUNNING.
13. Automatic scale-down/halt is allowed; automatic scale-up is forbidden.
14. A separate independent watchdog is mandatory before unattended live operation.

## Master stage sequence

1. **Stage 0:** evidence contract + recorder.
2. **Stage 0.5:** economic/profitability frontier.
3. **Stage 1:** minimal shared simulator.
4. **Stage 2:** quant falsification + untouched confirmation.
5. **Gate 1:** first major economic GO/NO-GO.
6. **Stage 3:** replay parity.
7. **Stage 4:** prospective shadow/paper.
8. **Stage 5:** durable OMS/reconciliation/recovery.
9. **Stage 6:** independent watchdog/testnet chaos.
10. **Stage 7:** risk-derived micro-live.
11. **Stage 8:** optional Jev experiment.
12. **Stage 9:** optional maker experiment.
13. **Stage 10:** human-approved scaling/autonomous production.

## Important conclusions from external adversarial reviews

Independent reviews from multiple frontier LLMs converged on the following:

- The biggest risk is building infrastructure before proving executable edge.
- Short-horizon BTC/ETH taker economics are difficult; horizons must be derived from measured movement, costs, latency, and signal decay rather than guessed.
- Cross-venue information may matter; a reference feed is justified as a measured feature source, not an assumed edge.
- Maker backtests are especially vulnerable to queue/adverse-selection optimism; start with taker truth and measure maker fills live later.
- Full Quant/Jev/GPT factorial ablation is unnecessary initially and increases multiple-testing risk.
- A failed pure-quant microstructure hypothesis is not automatically rescued by AI using the same data.
- Testnet proves plumbing/recovery, not profitability.
- Paper/shadow prove prospective behavior/operations, not actual fill economics.
- Micro-live is the first stage that can validate real-money execution economics.
- Unattended autonomy requires reconciliation, durable state, fault drills, and an independent external watchdog—not merely an automatic strategy loop.

## Resolved disagreements from the reviews

- **Do not hard-code prediction horizons.** Derive them in Stage 0.5.
- **Do not hard-code arbitrary 14/30/90-day evidence windows.** Duration is derived from effective sample size, power, regime coverage, and evidence rate.
- **Do not build a maker queue simulator initially.** Maker is measured live later.
- **Do not place GPT in runtime v1.**
- **Do not make Jev a directional engine.** One bounded veto/ranking hypothesis only.
- **Do not treat an unknown order observation as proof that an order never existed without full reconciliation evidence.**
- **Do not assume documented market-data cadence when it can be measured.** Recorder reports observed cadence and gaps.
- **Production key topology is intentionally not frozen before Gate 1.** A later design must separate ordinary strategy authorization from independent cleanup/watchdog authority and prevent split-brain exposure creation.

## Current implementation status

### Completed / being committed in TASK-001

- Repository created by the user.
- Project/package naming fixed: repository `quant-crypto-engine`, Python package `cryptobot`.
- Python version policy: 3.12 primary, 3.13 compatibility test.
- `uv` chosen for dependency locking/reproducible environments.
- Ruff, strict mypy, and pytest selected as mandatory first-line quality gates.
- GitHub Actions CI defined.
- Initial authoritative docs created:
  - `docs/MASTER_PLAN.md`
  - `docs/ARCHITECTURE_DECISIONS.md`
  - `docs/EVIDENCE_POLICY.md`
  - `docs/GATES.md`
  - `stages/STAGE_0.md`
  - `stages/STAGE_05.md`
  - `stages/STAGE_1.md`
  - `stages/STAGE_2.md`
- `tasks/TASK_001.md` and `tasks/TASK_002.md` created.
- `STATUS.md` established as the cross-chat continuation source of truth.

### Local validation completed

- Python 3.13.5: `compileall` PASS.
- Python 3.13.5: `pytest` PASS (1/1).
- Local sandbox has no external DNS, so Ruff/mypy installation and `uv lock` generation are intentionally delegated to GitHub Actions rather than fabricated.

### Tests required before TASK-001 is marked complete

- GitHub runner generates `uv.lock`.
- Generated lock is committed.
- `uv sync --locked --all-groups` succeeds.
- Ruff lint passes.
- Ruff formatting check passes.
- strict mypy passes.
- pytest passes on Python 3.12 and 3.13.
- GitHub Actions `CI` is green.

## Exact next task

After TASK-001 is green, perform **[`tasks/TASK_002.md`](tasks/TASK_002.md): Implement the Evidence Contract**.

Do **not** start Hyperliquid recorder code before the evidence-contract schema is reviewed and tested.

## User actions currently required

None after repository creation, unless GitHub reports a permissions/Actions configuration problem that cannot be changed through the connected tooling.

Future user actions will be explicitly recorded here before they are requested.

## Open decisions — intentionally deferred

- Final external reference venue/feed after Stage 0 probe/fit-for-purpose review.
- VM/provider/region for long-running recorder, chosen from legal/access/latency/storage considerations rather than assumption.
- Production signing-key topology and remote submit-gate design, deferred until Gate 1.
- Exact operational thresholds (staleness, timeouts, disk reserve, watchdog TTL), derived from measured distributions later.
- Capital amounts and scale ladder, derived from loss budget, depth, slippage, and exit evidence later.
- Project software license. Repository is public but no open-source license has been approved; do not copy third-party code merely because it is visible.

## Rules for future coding sessions

1. Read `STATUS.md` first.
2. Read the current task file.
3. Do not skip gates because later infrastructure is interesting.
4. Every coding task requires tests.
5. Run relevant tests before committing.
6. Update `STATUS.md` in the same commit or immediately after every completed task/gate.
7. Record failed experiments and rejected decisions; do not rewrite history.
8. Do not add trading credentials or secrets to Git, logs, environment examples, or test fixtures.
9. If a task reveals an architectural conflict, stop that task at a safe boundary, document it here, and resolve it before building around the conflict.
10. Prefer a small correct commit over a broad speculative implementation.
