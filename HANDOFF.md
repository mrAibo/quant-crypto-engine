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

## Persistent-host campaign checkpoint

Prospective collection started on **2026-09-24** on a persistent Ubuntu WSL2 host. **Do not initialize a second campaign.**

- deployed collector checkout: `main` at `f01b1fac2c81ccf59d0d05d13ba44dace5367f5f`;
- host CI-equivalent verification: Python 3.12.3, pinned `uv 0.12.18`, Ruff PASS, Ruff format PASS, strict mypy PASS, **359 pytest PASS**;
- campaign root: `/var/lib/quant-crypto-engine/frontier-campaign`;
- campaign ID: `btc-frontier-50s-v1`;
- frozen fee scenario: **4.5 bps/side SCENARIO**;
- first persistent-host acceptance segment: 70 seconds, **69,837** raw frames, **70,281** normalized events;
- acceptance-segment dataset bundle SHA-256: `50e910e5ffd108e58cd02503125059b059609ce53d734ea078652d15bf609274`;
- acceptance-segment evidence SHA-256: `3eb1abf0d91431909fcf3be1b6a5927253d287ca3e7e899c2b82f22510d514a8`;
- checkpoint campaign-manifest SHA-256: `b03185793f345a61a98871381641e5ead41a42930ccf0d5f22ad486bbdaf1dfe`;
- checkpoint valid 50-second windows: **1**;
- readiness: `COLLECTING`;
- gate: `INCONCLUSIVE`;
- one setup-time systemd segment was interrupted by the WSL lifecycle before keep-alive was added; that incomplete segment is deliberately preserved and is not counted;
- two later one-hour segments were killed during post-capture processing by WSL memory exhaustion and remain preserved as incomplete evidence;
- kernel OOM evidence showed the processing Python process reaching about **12.82 GiB** and **13.88 GiB** anonymous RSS on the two failures, while WSL exposed about **14.48 GiB RAM + 4 GiB swap**;
- this is an operational segment-size problem, not a change to the pre-registered 50-second experiment;
- on **2026-09-24 06:29 CEST**, the host override was changed from `SEGMENT_SECONDS=3600` to `SEGMENT_SECONDS=900`;
- the first 900-second validation segment completed successfully at **06:47:24 CEST** with **364,956 raw frames** and **369,682 normalized events**;
- that segment published dataset bundle SHA-256 `667235899f6c93028698dd6be0a71f58c3e4f9315b014e139a76ac76fc791da3` and segment evidence SHA-256 `a27018446274ba65a4aebfd58a2b66d4c7e2a33a2274813eca839347e0b84e74`;
- its systemd cgroup memory peak was **97.5 MiB** and no new OOM event occurred;
- checkpoint campaign-manifest SHA-256 is `fc52b483305339510ec3a97e3992f9885ee31affdf4210e7cfcd41a0d4322c1c`;
- accepted segments: **2**; total valid non-overlapping 50-second windows: **18** (**17** from the first successful 900-second segment plus the original acceptance window); excluded windows: **6**;
- readiness remains `COLLECTING`; gate remains `INCONCLUSIVE`;
- a subsequent 900-second segment started automatically at **06:53:07 CEST** and remains incomplete until immutable publication;
- Windows AC sleep is disabled; a Windows logon scheduled keep-alive holds WSL open and auto-restarts it on failure;
- the systemd timer remains enabled and collection is active.

No wallet, API key, account endpoint, order, signer, or capital is involved.

## Exact next action

Continue the **existing initialized campaign**; do not reinitialize it and do not delete incomplete segments.

On a fresh session:

1. connect to the existing collector host through the authorized remote-computer connector;
2. verify `quant-frontier-segment.service` / `quant-frontier-segment.timer`, `SEGMENT_SECONDS=900`, memory, and free disk;
3. inspect the cumulative report after accepted segments and confirm new 900-second segments continue publishing without OOM;
4. continue bounded 15-minute segments while this host remains memory-constrained, until `report.total_valid_non_overlapping_windows >= 2952`;
5. do not stop merely because 41 wall-clock hours passed;
6. when statistically ready, run the deterministic pre-registered Frontier Gate adjudication;
7. commit the final evidence result and advance `STATUS.md` according to the gate outcome.

No repository implementation work is currently required before that evidence threshold.

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

No command or repository action is required from the user while collection remains healthy.

Physical requirement: keep the collector machine powered and connected to AC power. Windows AC sleep is disabled for the campaign; battery sleep remains unchanged.

If host access or external network behavior later blocks progress and cannot be resolved with available tools, document the blocker without weakening tests or evidence rules.
