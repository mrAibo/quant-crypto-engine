# Project Status

> **Continuation entry point:** Read this file first in every new chat/session. Then read the referenced current task. Do not reconstruct project state from memory alone when this repository is available.

## Project

- Repository: `mrAibo/quant-crypto-engine`
- Current PR: **#1 — TASK-001: bootstrap repository and quality gate**
- Current phase: **Stage 0 — Evidence Contract and Market-Data Recorder**
- Current work package: **TASK-001 / S0-WP01 — final read-only CI and merge**
- Exact next work package after merge: **TASK-002 — Evidence Contract**
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

Independent reviews from Google, Qwen, GLM, DeepSeek, Claude/Fable and GPT Astra converged on the following:

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

## Resolved disagreements

- **Prediction horizons:** derive in Stage 0.5; do not hard-code them.
- **Evidence duration:** derive from effective sample size, power, regime coverage, evidence rate and budget; no magic 14/30/90-day gates.
- **Maker execution:** no initial queue simulator; live-measure later if justified.
- **GPT:** no runtime v1.
- **Jev:** one bounded veto/ranking hypothesis only; not a directional engine.
- **Unknown orders:** an `unknown` observation is not proof an order never existed without full reconciliation evidence.
- **Market-data cadence:** measure observed cadence/gaps; do not turn an undocumented cadence assumption into architecture.
- **Production key topology:** intentionally deferred until Gate 1. Later design must separate ordinary strategy authorization from independent cleanup authority and prevent split-brain exposure creation.

## TASK-001 implementation status

### Implemented on PR #1

- Reproducible Python package skeleton.
- Python 3.12 primary; Python 3.13 compatibility test.
- `uv` dependency management with committed `uv.lock`.
- Ruff lint + format checks.
- strict mypy.
- pytest.
- GitHub Actions CI.
- `README.md`.
- `docs/MASTER_PLAN.md`.
- `docs/ARCHITECTURE_DECISIONS.md`.
- `docs/EVIDENCE_POLICY.md`.
- `docs/GATES.md`.
- `stages/STAGE_0.md`, `STAGE_05.md`, `STAGE_1.md`, `STAGE_2.md`.
- `tasks/TASK_001.md`, `tasks/TASK_002.md`.
- `artifacts/stage_0/bootstrap_report.json`.
- This `STATUS.md` continuation record.

### Validation already observed

- Local Python 3.13.5: `compileall` PASS.
- Local Python 3.13.5: pytest PASS.
- GitHub Python 3.12: dependency sync PASS.
- GitHub Ruff lint PASS.
- GitHub Ruff format check PASS.
- GitHub strict mypy PASS.
- GitHub pytest 3.12 PASS.
- GitHub pytest 3.13 PASS.
- GitHub generated and committed `uv.lock`.

The local sandbox could not access external DNS, so generating the initial lock and installing missing lint/type tools locally was impossible. This was bypassed transparently through GitHub Actions. No external harness was required.

### Remaining before TASK-001 merge

Run CI once more using:

- committed `uv.lock`;
- pinned uv 0.12.18;
- GitHub token with `contents: read` only;
- no workflow self-commit behavior.

If this passes, merge PR #1 and begin TASK-002.

## Exact next task

After PR #1 merges, perform **[`tasks/TASK_002.md`](tasks/TASK_002.md): Implement the Evidence Contract**.

Do **not** start Hyperliquid recorder code before the evidence-contract schema is reviewed and tested.

## User actions currently required

**None.**

If a future blocker cannot be bypassed safely with the connected GitHub tooling, provide the user a complete self-contained task prompt for another harness (for example DeepSeek) rather than silently lowering test/quality requirements.

## Open decisions — intentionally deferred

- Final external reference venue/feed after Stage 0 fit-for-purpose review.
- VM/provider/region for long-running recorder.
- Production signing-key topology and remote submit-gate design, deferred until Gate 1.
- Exact operational thresholds (staleness, timeouts, disk reserve, watchdog TTL), derived from measured distributions later.
- Capital amounts and scale ladder, derived later from loss budget, depth, slippage, and exit evidence.
- Project software license. Repository is public but no open-source license has been approved; do not copy third-party code merely because it is visible.

## Rules for future coding sessions

1. Read `STATUS.md` first.
2. Read the current task file.
3. Do not skip gates because later infrastructure is interesting.
4. Every coding task requires tests.
5. Run relevant tests before committing.
6. Update `STATUS.md` with every completed task/gate and material architecture decision.
7. Record failed experiments and rejected decisions; do not rewrite history.
8. Never add trading credentials/secrets to Git, logs, examples, or fixtures.
9. If a task reveals an architectural conflict, stop at a safe boundary, document it here, and resolve it before building around it.
10. Prefer a small correct commit over broad speculative implementation.
