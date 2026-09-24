# Session Handoff

> **Purpose:** This file is the short continuation handoff for a fresh ChatGPT session.
> Treat the repository, especially `STATUS.md`, the current task file, and committed evidence artifacts, as the source of truth over conversational memory.

## Repository

- GitHub: `mrAibo/quant-crypto-engine`
- Branch to start from: `main`
- Current phase: **Stage 0.5 — Profitability / Economic Frontier**
- Current task: **TASK-018 — Stage 0.5 Prospective Frontier Evidence Campaign**
- Economic status: **UNPROVEN**
- Live trading: **FORBIDDEN**
- Predictive modeling before Frontier Gate: **FORBIDDEN**

## Read first in a new session

In this order:

1. `HANDOFF.md`
2. `STATUS.md`
3. `tasks/TASK_018.md`
4. `docs/runbooks/frontier_campaign.md`
5. only then inspect implementation/evidence files as needed

Do not reconstruct project state from chat memory when repository state disagrees.

## What is already complete

### Stage 0

TASK-001 through TASK-016 are complete.

The important result is that the evidence/data pipeline is validated end to end:

- immutable QCR1 raw capture;
- crash-safe segment sealing and audit;
- Hyperliquid public BTC/ETH capture;
- exact L2/BBO/trade/funding/mark/oracle normalization;
- reconnect duplicate visibility;
- Binance USDⓈ-M BTCUSDT/ETHUSDT frozen as Stage-0 reference source;
- mixed-source causal normalization;
- deterministic Parquet materialization;
- real dual-source public-mainnet Stage-0 Data Gate: **PASS**.

No economic edge was established by Stage 0.

### TASK-017 — first Stage-0.5 frontier derivation

Complete.

Derived, without fitting a predictive model:

- target horizon: **50 seconds**;
- required valid non-overlapping windows: **2,952**;
- DKW planning confidence: **0.95**;
- maximum empirical-CDF error: **0.025**;
- mathematical minimum observed support: **147,600 seconds ≈ 41 hours**;
- real collection likely must be longer because gaps/exclusions cannot reduce the requirement.

Pre-registered first gate rule:

`q95 absolute primary-mid movement > q50 known friction floor`

Equality is not a pass.

TASK-017 did **not** prove alpha.

## Current TASK-018 state

TASK-018 repository/tooling implementation is already merged.

Important provenance:

- replacement PR #19 merged as commit `0a169e2205252bd07863a31e2653ea834fd8e514`;
- PR #18 was superseded because of a STATUS-only mainline divergence;
- final network-independent CI: `35940389564`;
- **359 tests PASS** on Python 3.12 and 3.13;
- Ruff PASS;
- Ruff format PASS;
- strict mypy PASS on 74 source files.

Real public-only 30-second campaign smoke:

- workflow `35940052539`;
- **10,789** raw frames;
- **10,999** normalized events;
- immutable segment publication PASS;
- incomplete segment directories: 0;
- readiness: `COLLECTING`;
- gate: `INCONCLUSIVE`;
- valid 50-second windows: 0, expected because the smoke run was shorter than the 50-second target horizon.

The temporary network smoke workflow was removed after validation.

## What TASK-018 tooling already does

The merged implementation includes:

- immutable campaign configuration;
- immutable segment evidence;
- deterministic manifests/reports and SHA-256 binding;
- duplicate dataset/normalization digest rejection;
- overlap/touching segment rejection;
- causal-domain validation;
- no 50-second window may cross a segment boundary;
- no window may cross a host/boot causal boundary;
- documented-base taker fee scenario handling;
- deterministic first-2,952-window adjudication sample;
- q95-vs-q50 pre-registered rule;
- missing friction -> `INCONCLUSIVE`;
- adjacent-sign / zero-move dependence diagnostics;
- tamper-checked TASK-015 dataset loading;
- Parquet file SHA verification;
- bounded public dual-source segment runner;
- exclusive segment publication only after all audits pass;
- campaign report versioning keyed by campaign-manifest SHA;
- CLI commands:
  - `init-frontier-campaign`
  - `run-frontier-segment`
  - `report-frontier-campaign`
- systemd service/timer templates;
- persistent-host runbook.

No wallet, API key, private stream, order, signer, or capital logic is required for TASK-018.

## Exact next action

The repository does **not** need more implementation first.

It needs a persistent Linux host/VM with outbound public WebSocket access and enough disk to retain immutable QCR1 + Parquet evidence.

On that host:

### 1. Checkout current main and install locked environment

```bash
git clone https://github.com/mrAibo/quant-crypto-engine.git
cd quant-crypto-engine
git checkout main
git pull --ff-only

uv sync --locked --all-groups --python 3.12
```

### 2. Initialize the campaign exactly once

```bash
uv run --python 3.12 python -m cryptobot.cli init-frontier-campaign \
  --campaign-root /var/lib/quant-crypto-engine/frontier-campaign \
  --campaign-id btc-frontier-50s-v1 \
  --fee-scenario-bps-per-side 4.5
```

This 4.5 bps value is a documented-base **SCENARIO**, not a measured future account fee.

### 3. Run bounded immutable collection segments

Example one-hour segment:

```bash
uv run --python 3.12 python -m cryptobot.cli run-frontier-segment \
  --config config/runtime/dual-source-smoke.json \
  --campaign-root /var/lib/quant-crypto-engine/frontier-campaign \
  --duration-seconds 3600 \
  --registry config/instruments.yaml
```

Recommended operational path: use the supplied systemd service/timer from `docs/runbooks/frontier_campaign.md`.

### 4. Rebuild cumulative report after accepted segments

```bash
uv run --python 3.12 python -m cryptobot.cli report-frontier-campaign \
  --campaign-root /var/lib/quant-crypto-engine/frontier-campaign
```

Watch:

- `published_segment_count`;
- `incomplete_segment_directories`;
- `report.total_valid_non_overlapping_windows`;
- `report.adjudication_window_count`;
- `report.readiness`;
- `report.gate_decision`.

Do not stop merely because 41 wall-clock hours passed. The requirement is **>= 2,952 valid non-overlapping 50-second windows**.

## Frontier Gate outcomes

Only three decisions are allowed:

### PASS_FEASIBILITY

Means only:

The observed 50-second movement distribution contains an economically plausible region relative to currently known top-of-book + documented-base-taker friction.

It does **not** establish predictability, live slippage, actual account fees, latency, capacity, or positive net expectancy.

Next step: design Stage 1 predictability/signal-existence experiment.

### FAIL_FEASIBILITY_AT_50S

Means only:

The planned 50-second observed movement distribution fails the pre-registered movement-vs-friction criterion.

Do not jump directly to AI or a new strategy.

Next step: separately derive/evaluate the next 1-2-5 horizon with its own evidence requirement.

### INCONCLUSIVE

Means required evidence is missing/corrupt/insufficient.

Next step: evidence-gap remediation.

## Important constraints

Do **not**:

- fit logistic regression yet;
- fit LightGBM yet;
- add Jev or GPT runtime;
- optimize a strategy;
- build maker simulation;
- build OMS/signing/orders;
- add account/private capture;
- deploy capital;
- weaken the 2,952-window requirement;
- change the q95-vs-q50 criterion after seeing data;
- delete/rewrite accepted evidence segments;
- compare cross-boot monotonic timestamps.

Preserve failed/incomplete segments for diagnostics.

## Settled architecture decisions

- Python 3.12+ layered/modular monolith.
- Deterministic numeric core.
- Raw data immutable and replayable.
- Research/replay/shadow/paper/live should reuse stable strategy/risk/ledger contracts later.
- Taker-only first economic validation.
- Maker execution is a separately gated later experiment.
- GPT has no runtime role in v1.
- Jev gets at most one bounded veto/ranking hypothesis after a viable core signal exists.
- No autonomous self-modification.
- Scale-down/halt may be automatic; scale-up remains human-approved.
- Exchange/reconciled evidence will be authoritative for future order/position state.
- Independent watchdog mandatory before unattended production.
- Win rate >50% is not the optimization target; positive net expectancy after all costs is.

## User action currently required

**Provide or choose the persistent Linux host/VM.**

Once the host exists, the next session should help with:

1. host sizing/selection if not yet chosen;
2. installation/deployment;
3. campaign initialization;
4. systemd timer setup;
5. first one-hour segment verification;
6. cumulative report inspection;
7. monitoring until >= 2,952 valid windows;
8. final deterministic Frontier Gate adjudication;
9. commit the final evidence result and advance `STATUS.md`.

If host access or external network behavior blocks progress and cannot be resolved with available tools, write a complete self-contained task prompt for another harness instead of weakening tests or evidence rules.
