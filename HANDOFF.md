# Session Handoff

> **Purpose:** This file is the short continuation handoff for a fresh ChatGPT session.
> Treat the repository, especially `STATUS.md`, the current task file, and committed evidence artifacts, as the source of truth over conversational memory.

## Repository

- GitHub: `mrAibo/quant-crypto-engine`
- Branch to start from: `main`
- Current phase: **Stage 2 — Signal-Existence Dataset and Falsification Protocol**
- Current task: **TASK-027 — Stage 2 Prospective Development Evidence Expansion**
- Frontier Gate: **PASS_FEASIBILITY**
- Economic edge / predictability: **UNPROVEN**
- Live trading: **FORBIDDEN**

## Read first in a new session

In this order:

1. `HANDOFF.md`
2. `STATUS.md`
3. `tasks/TASK_027.md`
4. `tasks/TASK_028.md`
5. `artifacts/stage_2/development_campaign_protocol.json`
6. `artifacts/stage_2/tardis_historical_development_protocol.json`
7. `artifacts/stage_2/tardis_historical_corpus_manifest.json`
8. `tasks/TASK_029.md`
9. `artifacts/stage_2/tardis_historical_training_protocol.json`
10. only then inspect implementation/evidence files as needed

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

## TASK-019 — Minimal Shared Simulator

Complete.

Provenance:

- PR #30 merged as `d963dd59c7e2fe9c873bfc61dd029875131dcbef`;
- pre-merge CI `36238838341`: Ruff PASS, Ruff format PASS, strict mypy PASS on **85 source files**, **389 tests PASS** on Python 3.12 and 3.13;
- post-merge CI `36238897281`: same checks PASS, **389 tests PASS** on Python 3.12 and 3.13;
- contract artifact: `artifacts/stage_1/simulator_contract.json`;
- documentation: `docs/research/simulator.md`.

Delivered:

- causal `QuoteObservation`, `DecisionContext`, and `SimulationOpportunity` contracts;
- deterministic policy protocol with explicit `ABSTAIN/LONG/SHORT`;
- no-trade and seed-provenanced SHA-256 randomized-direction controls;
- one shared taker-only executable-side accounting path;
- spread embedded exactly once in executable bid/ask prices;
- separate fee / latency / impact / funding cost components with `OBSERVED/SCENARIO/UNKNOWN` semantics;
- UNKNOWN costs can never be fabricated as zero; traded `business_net_pnl` remains null while required costs are UNKNOWN;
- deterministic INVALID / NO_TRADE / TRADED ledger with exact-Decimal JSON and SHA-256;
- normalized BBO adapter and deterministic fixed-horizon opportunity builder;
- PRIMARY / REPLICATION separation.

No predictive model or strategy edge was established by TASK-019.

## TASK-020 — Stage-2 protocol freeze

Complete.

Provenance:

- PR #32 merged as `b3568644c900d5e561597cd5c01b3c10ece0a720`;
- pre-merge CI `36248421789`: green on Python 3.12/3.13;
- post-merge CI `36248457686`: green on Python 3.12/3.13;
- local final gate: **408 tests PASS**, Ruff/format PASS, strict mypy PASS on **93 source files**;
- machine-readable protocol: `artifacts/stage_2/signal_protocol.json`;
- documentation: `docs/research/stage2_signal_protocol.md`.

Frozen PRIMARY dataset:

- 182 Gate segments;
- **3,259** BTC rows;
- SHA-256 `3eeb0b405a9db439b7711b453ec9820707068bbfba855bf120124b79aa32b237`;
The pre-selection power-buffer amendment was applied before any H1/H2 candidate
performance was calculated. It uses only the published Frontier zero-move fraction
plus frozen DKW error, decision-time feature readiness, and label
availability/timing metadata.

Amended partitions:

- DEVELOPMENT **159** rows;
- SELECTION **1,123** rows — H1 planning-ready **902**, H2 **962**;
- untouched CONFIRMATION **1,977** rows — H1 planning-ready **1,411**, H2 **1,515**;
- selection start wall-ns `1790235572690884130`;
- confirmation start wall-ns `1790302269067780894`;
- selection valid-label overlap into confirmation: **0**.

Registered hypotheses are only H1 5-second Binance reference lead and H2 Hyperliquid BBO size imbalance. No H1/H2 correctness, PnL, or champion performance was used to derive the amended boundaries.

## TASK-021 selection result

Complete.

- artifact: `artifacts/stage_2/selection_result.json`;
- SHA-256: `e3403ef3eb6016040344dd8c17f4174b9190ca1a3aa5f5a59f54e1af7f7fb5a0`;
- decision: **INCONCLUSIVE_SELECTION**;
- champion: **none**;
- confirmation opened: **false**.

H1 had 644 directional-evaluable rows versus 783 required, a 49.9821% dependence-adjusted lower bound, and negative partial-known-cost PnL.

H2 had 930 directional-evaluable rows, 58.3871% directional accuracy and a 54.8815% dependence-adjusted lower bound, but its mean partial-known-cost PnL was negative. It is not promotable on directional evidence alone.

## TASK-022 remediation result

Complete.

- artifact: `artifacts/stage_2/selection_remediation.json`;
- SHA-256: `fec7cbb77fe67c672a2319fadee7e6a94f79fef013c16c6033b55fbb07f574d5`;
- decision: **STOP_REGISTERED_H1_H2_FAMILY**;
- old confirmation: **UNOPENED_AND_EXCLUDED**.

H1 attrition was 1,123 total -> 1,059 feature-ready -> 744 actionable -> 663 traded
-> 644 directional-evaluable. A conservative unchanged-H1 replication would require
1,719 fresh selection rows and 2,688 fresh confirmation rows, but it is not
registered because H1 also failed frozen taker partial-known-cost economics.

Historical data is now explicitly development/diagnostic evidence only.

## TASK-023 development result

Complete.

- deterministic 50s family: no positive DEV_B economic candidate;
- fixed regularized logistic baseline: `STOP_LOGISTIC_DEVELOPMENT`;
- no fresh 50s test campaign is justified;
- old confirmation remains **UNOPENED_AND_EXCLUDED**.

Artifacts:

- `artifacts/stage_2/economic_family_development.json`
  SHA-256 `ae62dff1172ca7666b1119c4c8a0f1ca61757f428c30b66b73a208b34c2a3b67`;
- `artifacts/stage_2/economic_logistic_development.json`
  SHA-256 `285775b8febb226414bd838121f99b15b72d5b46edb13383b12398b8c80ccaf8`.

## TASK-024 result

Complete.

- decision: **STOP_300S_FAMILY**;
- decision artifact:
  `artifacts/stage_2/economic_300s_decision.json`;
- SHA-256:
  `b36027ab6436258b4970e974280ee3669813c585d7deb96a29f00079aca12eb6`;
- old confirmation: **UNOPENED_AND_EXCLUDED**;
- fresh registered test evidence collected: **false**.

The 300s deterministic family remained economically negative and under-supported.
The fixed 300s logistic fallback selected zero valid DEV_B trades.

## TASK-025 result

Complete.

- decision: **STOP_MICROSTRUCTURE_FAMILY**;
- registry SHA-256: `d5024ce6cb16c0d3dcce5b65f3f62f6d577b971d3bda7c8342ab67aaa100b130`;
- decision artifact SHA-256: `6355dd1295ab156757e091191ee686f6f9e63708a3bb556e03611b25285f7172`;
- 50s: 479 full-feature / 409 valid targets / 24 positive / 385 nonpositive;
- 300s: 57 full-feature / 21 valid targets / 6 positive / 15 nonpositive;
- old confirmation: **UNOPENED_AND_EXCLUDED**;
- fresh development validation started: **false**;
- fresh registered test started: **false**.

A prior six-feature DEV_B result predated the full eight-feature registry, so all
pre-cutoff microstructure evidence is treated as exposed development only.

## TASK-026 result

Complete.

- selected path: **PROSPECTIVE_DEVELOPMENT_EVIDENCE_EXPANSION**;
- decision artifact:
  `artifacts/stage_2/economic_bottleneck_adjudication.json`;
- SHA-256:
  `4c90657accb99a0caff44336bbca091b887f99cd9caedada01fd15364b77b39b`;
- E3 50s implied mean break-even taker fee: about **0.758 bps/side**;
- published tier-6 plus Diamond schedule context: **1.44 bps/side**;
- E3 mean at that documented fee context remains negative before UNKNOWN costs;
- old confirmation: **UNOPENED_AND_EXCLUDED**;
- new model/test evidence consumed: **false**;
- user action required now: **none**.

## Exact next action

TASK-027 frozen capture is **COLLECTING** on Aibo and its fixed window is established.
TASK-028 historical DEVELOPMENT corpus is **COMPLETE** and remains separate from TASK-027.

1. keep TASK-027 capture/process timers healthy until the immutable
   **2026-09-30 12:38:55.742461 CEST** deadline;
2. merge the exact TASK-029 training protocol **before** reading TASK-028 economic outcomes;
3. only after that merge, implement/build/train/evaluate the frozen 50s/300s
   historical family on the fixed 12-day DEV_A / 8-day DEV_B split;
4. use TASK-028 only as DEVELOPMENT data under that frozen protocol;
5. after TASK-027 collection, publish its deterministic coverage/support evidence;
6. do not use outcomes to alter duration, dates, features, horizons, thresholds, or rules.

No private account access, AWS requester-pays credentials, wallet, capital, maker
orders, registered SELECTION/CONFIRMATION evidence, or live trading.

## Session checkpoint — TASK-027 collecting; TASK-029 protocol ready before historical outcome use

This checkpoint exists specifically to start a new chat/session without reconstructing
state from conversational history.

- latest completed work package: **TASK-028**;
- TASK-027 protocol SHA-256:
  `1ab9a735f512dd301392ba568b49ebd0f1e80d676f073b3d502bf73d111bc1d3`;
- TASK-027 runtime profile SHA-256:
  `8bf2a31ec634b475f1e3b559663bb35e16950c1c721ab73ddc5812cd6b1f03e1`;
- protocol package PR #45 merged as
  `b3de5b4c15138ccc1df81c9a055d04920cad237c` after green CI run `36312921369`;
- TASK-027 launch checkout: `b3de5b4c15138ccc1df81c9a055d04920cad237c`;
- TASK-027 capture state: **COLLECTING**;
- first accepted run ID:
  `run-1790505535742461344-86b3a1307196c582cdde`;
- fixed start: `1790505535742461344`
  (**2026-09-27 12:38:55.742461 CEST**);
- fixed deadline: `1790764735742461344`
  (**2026-09-30 12:38:55.742461 CEST**);
- capture/process timers: **ACTIVE**;
- checkpoint: 4 published/bound segments, fifth capture attempt in progress,
  pending/incomplete processing = 0;
- TASK-028 protocol SHA-256:
  `8d08ffa54eb64a3ecf11b9a73e3eea5d815f60560e7a93ad6796c63d2760b735`;
- TASK-028: 20 first-of-month days / 480 hours / 80 Tardis archives,
  **DEVELOPMENT_ONLY_EXTERNAL_RECEIVE_TIME**;
- TASK-028 download/verification: **COMPLETE — 80/80 archives, 0 missing**;
- TASK-028 total compressed bytes: **1,180,336,813**;
- TASK-028 corpus artifact SHA-256:
  `9696dca5f57fe160a8438236f1af82947a1588d2476a882fdf627f4cbd26e5e8`;
- TASK-028 archive-set SHA-256:
  `8e545456b34c6d1dabdb4e31fc13a0cb174bb96fef01eb137d9c32fa1dcb37fc`;
- TASK-028 economic outcomes consumed: **false**; model fitted: **false**;
- TASK-029 protocol SHA-256:
  `75fc97ab0ee68185704a06c81fd9fce06c0b1df5e32871dbac6247133ab53da1`;
- TASK-029 state: **PROTOCOL_READY — historical economic outcomes not yet consumed**;
- TASK-029 split: **12 whole UTC days DEV_A / 8 whole UTC days DEV_B**;
- TASK-029 horizons: **50s / 300s only**; no sweeps;
- TASK-029 derived storage: **Parquet ZSTD + DuckDB 1.5.5**, rebuildable from raw;
- storage conversion materializes economic outcomes: **false**;
- TASK-027 may not be repurposed as future SELECTION;
- TASK-026 artifact SHA-256:
  `4c90657accb99a0caff44336bbca091b887f99cd9caedada01fd15364b77b39b`;
- selected primary path: **PROSPECTIVE_DEVELOPMENT_EVIDENCE_EXPANSION**;
- always verify the latest `main` before continuing;
- primary work package: **TASK-027 — Stage 2 Prospective Development Evidence Expansion**;
- latest completed parallel work package: **TASK-028 — Tardis Historical Microstructure DEVELOPMENT Corpus**;
- current parallel bounded package: **TASK-029 — Frozen Tardis Historical Feature/Training Protocol**;
- old Stage-2 confirmation: **UNOPENED_AND_EXCLUDED**;
- new model/test evidence consumed during TASK-026: **none**;
- fresh registered test evidence after TASK-026: **none**;
- live trading / OMS / signing / private account capture: **FORBIDDEN**;
- user action required now: **none**.

For a fresh session, trust repository state over chat memory. Read
`HANDOFF.md` → `STATUS.md` → `tasks/TASK_027.md` → `tasks/TASK_028.md`, then
continue both bounded tracks without mixing their evidence roles.

## Historical Frontier Gate outcomes

The section below is retained as historical gate context only. It is **not** the current next action; current work is TASK-027.


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

- open or evaluate the old Stage-2 confirmation partition;
- inspect TASK-025 DEV_B outcomes before the feature/model/horizon budget is frozen;
- add new TASK-025 features, thresholds, or horizons after DEV_B exposure;
- perform broad feature mining or an unrestricted hyperparameter search;
- fit LightGBM;
- add Jev or GPT runtime;
- build maker simulation;
- build OMS/signing/orders;
- add account/private capture;
- deploy capital;
- reinterpret historical/development evidence as fresh confirmation;
- delete/rewrite accepted or failed evidence;
- compare cross-boot monotonic timestamps.

The bounded logistic baselines used in TASK-023/TASK-024 and the bounded
microstructure family in TASK-025 are completed experiments. TASK-026 selected the
next evidence path; TASK-027 must collect only the frozen prospective DEVELOPMENT
evidence and must not expand the predictive family.

Preserve failed/incomplete segments and negative experiments for diagnostics.

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

No user action is required for the completed Frontier Gate.

Prospective TASK-018 scheduling is quiesced. Keep `Aibo` available only when continuing Stage 2 implementation/testing; it no longer needs to remain powered solely to accumulate Frontier Gate evidence.

If host access or external behavior later blocks Stage 2 progress and cannot be resolved with available tools, document the blocker without weakening tests or evidence rules.
