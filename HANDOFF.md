# Session Handoff

> **Purpose:** This file is the short continuation handoff for a fresh ChatGPT session.
> Treat the repository, especially `STATUS.md`, the current task file, and committed evidence artifacts, as the source of truth over conversational memory.

## Repository

- GitHub: `mrAibo/quant-crypto-engine`
- Branch to start from: `main`
- Current phase: **Stage 1 — Minimal Shared Simulator**
- Current task: **TASK-019 — Stage 1 Minimal Shared Simulator**
- Frontier Gate: **PASS_FEASIBILITY**
- Economic edge / predictability: **UNPROVEN**
- Live trading: **FORBIDDEN**

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

Prospective collection started on **2026-09-24** on the persistent Ubuntu WSL2 host `Aibo`. **Do not initialize a second campaign.**

Current deployed state:

- production checkout: `main` at `272506ad9c6f216ad2a279d6730569deb310a820`;
- host verification after deployment: Python 3.12.3, Ruff PASS, Ruff format PASS, strict mypy PASS on **77 source files**, **371 pytest PASS**;
- campaign root: `/var/lib/quant-crypto-engine/frontier-campaign`;
- campaign ID: `btc-frontier-50s-v1`;
- frozen fee scenario: **4.5 bps/side SCENARIO**;
- operational segment size remains **900 seconds**;
- Windows AC sleep is disabled and the `QuantCryptoEngine-WSLKeepAlive` scheduled task keeps WSL active;
- legacy `quant-frontier-segment.timer` is **inactive**;
- split `quant-frontier-capture.timer` and `quant-frontier-process.timer` are **active and enabled**;
- capture and processing are now decoupled: the next raw capture starts while the previous sealed segment is normalized/materialized;
- the processor is deliberately lower priority (`Nice=10`, `OOMScoreAdjust=250`).

Campaign-report scalability is also deployed:

- PR #27 merged as `272506ad9c6f216ad2a279d6730569deb310a820`;
- pre-merge CI `35994008562`: green after the corrected formatted head;
- post-merge CI `35994069207`: green;
- on a frozen real 22-segment snapshot, legacy vs optimized report JSON was **byte-for-byte identical** with SHA-256 `d5f6ede81be6f019e372f2358a618fbcd3da6cdbf823fb7e06041dd442e10dad`;
- frozen-snapshot benchmark improved from **110.76 s / 3,662,312 KiB RSS** to **35.18 s / 1,194,780 KiB RSS**;
- production report at 23 accepted segments completed in **35.26 s** with **1,240,964 KiB max RSS**, swap 0;
- latest operational check showed about **927 GiB free** and no new kernel OOM events.

The first production split segment completed end to end:

- raw frames: **662,009**;
- normalized events: **667,554**;
- dataset bundle SHA-256: `69d28e7d23fb1a63ff1727bba64f6e3ddaa713334079a2dc820d1b3091bd40f8`;
- dataset manifest SHA-256: `60b14f059d7794d632681fe33fd6648b99f645be59c608bac96153679c3866d4`;
- segment evidence SHA-256: `557267970a93f221bbfbaf1d7a80f8e45b4628e6d6090df532b8f98105b9b58d`;
- processor memory peak: about **1.3 GiB**, swap **0 B**;
- no new OOM was observed;
- the next capture started while processing ran; measured inter-capture receive-time gap is approximately **60 seconds**, materially below the old combined capture/process downtime.

Latest deterministic campaign checkpoint:

- campaign manifest SHA-256: `6abc46b53572ac91c657f92bc8126a293830785aa7f8168d1d413d831fd9a3eb`;
- accepted/published segments: **23**;
- total valid non-overlapping 50-second windows: **375 / 2,952**;
- excluded candidate windows: **15**;
- q50 known friction: about **9.1234 bps**;
- observed q95 absolute primary-mid movement: about **10.6401 bps**;
- readiness: `COLLECTING`;
- gate: `INCONCLUSIVE`.

The changing early q95 values are descriptive only. They are evidence for **not** stopping early or changing the pre-registered rule.

All old failed/incomplete segment directories remain preserved. Do not delete, splice, or rewrite them.

## Final TASK-018 Frontier Gate — 2026-09-26

TASK-018 is complete.

The deterministic prospective campaign report crossed the pre-registered readiness threshold and adjudicated the **first 2,952 valid non-overlapping 50-second windows** exactly as frozen in TASK-017/TASK-018.

Final Gate evidence:

- campaign/report manifest SHA-256: `f82ba391ddaeac85ddb4787aec84d3cb85c17794101486c357cbb5bbd41f161c`;
- campaign report SHA-256: `d2289bff1d2d3ffddc246456ff6ea9c6a4ae7663e1805d40cc0802e33891a3b2`;
- accepted segments in the Gate report: **182**;
- total valid 50-second windows available: **3,076**;
- deterministic adjudication sample: **2,952** windows;
- excluded candidate windows: **521**;
- q95 absolute primary-mid movement: **9.183776917709780722417361000 bps**;
- q50 known friction floor: **9.123151337258348319833680000 bps**;
- movement minus friction margin: **0.060625580451432402583681000 bps**;
- q50 friction / q95 movement: **0.9933986222667796459142534313**;
- readiness: `READY_FOR_FRONTIER_ADJUDICATION`;
- Gate decision: **`PASS_FEASIBILITY`**.

Interpretation is deliberately narrow: the observed 50-second movement distribution contains an economically plausible region relative to the currently known top-of-book + documented-base-taker friction scenario. This does **not** establish predictability, a tradeable signal, positive net expectancy, actual account fees, live slippage/impact, latency, capacity, or funding economics.

Evidence classes remain unchanged:

- fee: `SCENARIO`;
- latency: `UNKNOWN`;
- funding-boundary cost: `UNKNOWN`;
- actual project-account fee tier, own-order slippage/impact, maker economics, and predictability remain unsupported.

Dependence diagnostics are descriptive only: adjacent non-zero sign agreement = `0.5278725824800910125142207053`; zero-move fraction = `0.1063685636856368563685636856`. Non-overlap does not prove IID, so the DKW count remains a planning bound rather than a formal IID guarantee.

The prospective collection timers were disabled after the Gate sample was frozen. Any segment already in flight may finish and remain preserved, but **must not change the frozen first-2,952-window adjudication**.

Committed Gate artifact: `artifacts/stage_05/frontier_gate_50s.json`.

## Auxiliary retrospective checkpoint

Retrospective public archives are now an explicitly separate, non-gating research track.

Merged provenance:

- PR #23 / merge `29674aa94ef418499a6761a379cdf176967970d9`: split capture/processing;
- PR #24 / merge `63aa02d2e8c52cac0c9e49b8832b96fb1c9e3af2`: non-gating retrospective archive planner/downloader;
- PR #25 / merge `60821293fa8fe03a90bda35e1195410821f8bc1d`: deterministic 50-second Binance retrospective analyzer;
- PR #25 pre-merge and post-merge CI: green.

Local retrospective root:

`/var/lib/quant-crypto-engine/retrospective`

For **2026-08-01 through 2026-08-07**:

- deterministic plan: **350 sources**;
- Binance Data Vision: **14/14** BTCUSDT/ETHUSDT daily aggTrades ZIPs downloaded and SHA-256 checked, **14 manifests**, about **128 MiB**;
- Hyperliquid plan: **336** hourly BTC/ETH L2 objects;
- every retrospective source/report is labeled `EXCLUDED_FROM_TASK_018_FRONTIER_GATE`.

Checksum-reverified Binance 50-second trade-price context:

- BTCUSDT: **12,096 windows**, q95 absolute first-to-last trade-price movement ≈ **6.8355 bps**;
- ETHUSDT: **12,096 windows**, q95 ≈ **9.2205 bps**.

These numbers are **not** Hyperliquid primary BBO-mid, do not reproduce live receive-time/gap/host-boot semantics, and must never substitute for the prospective 2,952-window Gate sample.

Hyperliquid historical L2 uses the official S3 Requester Pays archive. It requires an authenticated AWS identity; no suitable AWS/S3 plugin is currently available. This does **not** block TASK-018 prospective collection.

## Exact next action

Start **TASK-019 — Stage 1 Minimal Shared Simulator**.

Read `tasks/TASK_019.md` and implement only the minimal shared causal simulator/accounting foundation required before quantitative falsification:

1. frozen event/time input contract using existing immutable normalized evidence;
2. deterministic strategy/policy interface with no exchange/network/filesystem I/O;
3. no-trade/accounting control;
4. deterministic randomized control with explicit seed provenance;
5. conservative taker execution/accounting primitives that keep unknown latency/funding/account-specific costs explicit rather than fabricating them;
6. deterministic trial ledger and complete trial accounting;
7. tests for causality, cost non-double-counting, replay determinism, and control behavior.

Do not jump to LightGBM, Jev, OMS/signing, private/account endpoints, or live trading. The Frontier Gate permits predictability testing; it does not prove a signal.

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
