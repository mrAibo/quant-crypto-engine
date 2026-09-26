# TASK-018 — Stage 0.5 Prospective Frontier Evidence Campaign

## Status

`IN PROGRESS — TOOLING MERGED; LONG PROSPECTIVE CAMPAIGN PENDING`

## Objective

Collect and adjudicate the first statistically planned prospective Stage-0.5 evidence window without fitting any predictive model.

TASK-017 derived the next evidence requirement:

- target frontier horizon: **50 seconds**;
- required valid non-overlapping windows: **2,952**;
- DKW planning confidence: **0.95**;
- maximum empirical-CDF error: **0.025**;
- mathematical minimum observed duration: **147,600 seconds (~41 hours)**;
- gaps, invalid observations, and serial dependence can only increase the real requirement.

TASK-018 must turn that requirement into a restart-safe campaign rather than one fragile long-running process.

The question is deliberately narrow:

> With sufficient prospective BTC market evidence, does the 50-second absolute-movement distribution leave a plausible economic region above the conservative known taker-friction floor, before any claim of predictability?

A PASS here is **not alpha** and is **not permission to trade**.

## Why a campaign abstraction is required

A single 41+ hour process is an avoidable operational risk.

Evidence collection must support multiple immutable segments while preserving:

- one campaign identity;
- per-segment host/boot/source provenance;
- QCR1 authority;
- deterministic Parquet materialization;
- exact campaign segment ordering;
- duplicate/overlap detection;
- gap visibility;
- cumulative valid-window accounting;
- restart/resume without rewriting prior evidence.

Segments may come from different boots. Cross-boot monotonic timestamps must never be directly compared. Campaign chronology uses receive wall time only for ordering across causal domains, while within-domain causal ordering remains monotonic-time authoritative.

## Inputs

Use only validated components:

- TASK-016 dual-source public recorder;
- TASK-014 causal normalization;
- TASK-015 deterministic Parquet materialization;
- TASK-017 frontier/audit/report primitives;
- Hyperliquid BTC primary market;
- Binance USDⓈ-M BTCUSDT frozen reference;
- TASK-017 evidence-window plan.

ETH remains untouched for replication/generalization.

## Work package A — Campaign manifest

Create a strict immutable campaign contract with:

- campaign ID;
- schema/version;
- frozen market/source set;
- target horizon = 50 s;
- DKW planning parameters;
- required valid non-overlapping windows = 2,952;
- segment list;
- per-segment:
  - dataset bundle SHA-256;
  - normalization report SHA-256;
  - raw frame count;
  - normalized event count;
  - host/boot domains;
  - min/max receive wall time;
  - primary BTC BBO count;
  - primary BTC L2 count;
  - validity/audit result.

Campaign aggregation must reject:

- duplicate dataset bundle digests;
- overlapping receive-wall intervals unless explicitly quarantined;
- wrong source/instrument set;
- wrong schema/materializer version;
- inconsistent target/config parameters;
- missing source digest binding.

No segment may be silently replaced.

## Work package B — Segment runner

Add a read-only/public-only evidence-segment runner that reuses TASK-016.

Each bounded segment must:

1. capture both frozen public sources;
2. seal QCR1;
3. audit storage;
4. normalize through TASK-014;
5. materialize TASK-015 Parquet;
6. run TASK-017 dataset audit/frontier measurements;
7. emit one immutable segment evidence JSON;
8. exit nonzero on any acceptance failure.

No credentials, account endpoints, orders, or private streams.

The segment duration is a runtime parameter. Do not hard-code 41 hours into one run.

## Work package C — Cross-segment frontier aggregation

Aggregate primary BTC BBO observations across accepted segments.

Rules:

- preserve every segment independently;
- never concatenate cross-boot monotonic clocks into one causal timeline;
- only form a 50-second movement window when both endpoints belong to a causally valid interval within the same host/boot domain;
- do not bridge segment gaps;
- do not bridge causal-domain boundaries;
- apply the same TASK-017 gap exclusion rule;
- record candidate / accepted / excluded counts;
- count valid non-overlapping 50-second windows exactly.

The campaign becomes statistically **READY_FOR_FRONTIER_ADJUDICATION** only when valid non-overlapping windows >= 2,952.

Elapsed wall-clock duration alone is insufficient.

## Work package D — Frontier Gate adjudication

When the campaign is ready, produce a deterministic adjudication artifact.

Required observed outputs:

- primary BBO cadence/gap summaries;
- 50-second signed and absolute move distributions;
- q50/q75/q90/q95/q97.5/q99 absolute movement;
- spread distribution;
- known top-of-book round-trip friction distribution;
- documented-base taker fee scenario clearly labeled SCENARIO;
- known-friction floor distribution;
- required capture fraction by movement quantile;
- valid-window count;
- excluded-window count and reasons;
- campaign calendar span;
- accepted segment count;
- source dataset digests.

Still UNKNOWN / unsupported unless separately measured:

- actual future project-account fee tier;
- submit-to-ACK/fill latency;
- realized own-order slippage/impact;
- boundary-aligned funding cost;
- maker economics;
- predictability.

### Gate semantics

Allowed decisions:

- `PASS_FEASIBILITY`
- `FAIL_FEASIBILITY_AT_50S`
- `INCONCLUSIVE`

`PASS_FEASIBILITY` means only:

> The statistically planned observed 50-second movement distribution contains an economically plausible region relative to the currently known top-of-book + documented-base-taker friction floor, so testing predictability at/around this horizon is not ruled out.

It does **not** mean the move is predictable or tradable.

`FAIL_FEASIBILITY_AT_50S` means only:

> Even before requiring prediction, the planned 50-second observed movement distribution does not clear the pre-registered economic criterion relative to the known friction floor.

It does not automatically kill longer horizons. The next 1-2-5 horizon must be evaluated under a separately derived support requirement.

`INCONCLUSIVE` is mandatory if required evidence or required cost components for the pre-registered test are missing/corrupted.

## Pre-registered 50-second criterion

Use the TASK-017 pilot only to select the next horizon, not to tune the decision threshold.

For the first 50-second adjudication:

- compare **q95 absolute primary-mid movement** to **q50 known friction floor**;
- report the exact ratio `q50_known_friction / q95_abs_move`;
- `PASS_FEASIBILITY` requires q95 absolute movement **strictly greater** than q50 known friction;
- equality is not a pass;
- if q95 does not clear q50 friction, record `FAIL_FEASIBILITY_AT_50S`.

This criterion is deliberately simple and model-free. It is not a trading rule.

Also report q90/q97.5/q99 for context, but do not change the pre-registered decision after observing the evidence.

## Statistical limitations

The DKW planning count assumes independent samples.

Non-overlap removes mechanical overlap but does not prove independence.

Therefore the adjudication must:

- state this limitation prominently;
- report serial-dependence diagnostics that do not alter the pre-registered sample floor;
- never claim a formal iid confidence guarantee if dependence is observed;
- permit a conservative extension of the campaign if dependence diagnostics materially weaken the interpretation.

Do not silently reduce the required window count.

## Required code

Expected modules:

- `src/cryptobot/research/campaign.py`
- optional read-only CLI entry point;
- tests for campaign manifests, overlap detection, cross-domain windowing, cumulative support, and deterministic adjudication;
- `artifacts/stage_05/frontier_campaign_contract.json`.

Reuse TASK-017 primitives rather than duplicating movement/friction math.

## Required tests

At minimum:

- immutable campaign config validation;
- deterministic campaign/segment serialization;
- duplicate segment digest rejection;
- overlapping segment interval rejection/quarantine;
- cross-boot monotonic values never compared;
- no movement window bridges a segment boundary;
- no movement window bridges a causal-domain boundary;
- exact cumulative valid-window counting;
- readiness only at >= 2,952 valid non-overlapping 50-second windows;
- q95 vs q50 pre-registered adjudication;
- equality does not pass;
- missing required friction evidence -> INCONCLUSIVE;
- scenario/observed/unknown classes preserved;
- deterministic aggregate/report digest;
- resume with prior accepted segments does not rewrite them;
- malformed/tampered segment evidence rejected.

## Evidence collection

The project needs at least ~41 hours of valid observed support and likely more.

GitHub-hosted CI must **not** be treated as a reliable single 41-hour recorder.

Preferred operational path:

- run bounded evidence segments on a persistent Linux host/VM;
- preserve QCR1 + Parquet + segment evidence artifacts;
- add accepted segment manifests to the campaign;
- continue until the valid-window requirement is reached.

If no persistent host is available, define a separately reviewed chunked collection mechanism; do not pretend a short CI job satisfies the requirement.

## Definition of Done

1. Campaign/segment contracts implemented and tested.
2. Segment runner can produce restart-safe immutable evidence.
3. Cross-segment aggregation is deterministic and causal-domain safe.
4. >= 2,952 valid non-overlapping 50-second windows are collected.
5. Frontier adjudication is produced from the pre-registered rule.
6. OBSERVED / SCENARIO / UNKNOWN remain distinct.
7. No predictive model is fitted.
8. No live/private/trading endpoint is used.
9. Ruff/format/strict mypy/pytest green on Python 3.12 and 3.13.
10. `STATUS.md` advances according to the gate:
   - PASS_FEASIBILITY -> Stage 1 predictability/signal-existence design;
   - FAIL_FEASIBILITY_AT_50S -> next 1-2-5 horizon evidence plan;
   - INCONCLUSIVE -> evidence-gap remediation.

## Do Not Build

- logistic regression / LightGBM;
- strategy/backtest optimizer;
- Jev/GPT/LLM runtime;
- maker simulation;
- OMS/signing/orders;
- account/private capture;
- capital deployment.


## Implementation progress

Implemented first campaign core:

- immutable pre-registered CampaignConfig;
- immutable SegmentEvidence / CampaignManifest contracts;
- deterministic manifest/report JSON + SHA-256;
- duplicate dataset/normalized digest rejection;
- overlapping/touching segment interval rejection;
- explicit causal-domain membership validation;
- per-domain 50-second non-overlapping window construction;
- no window may cross segment or host/boot boundary;
- start-BBO known-friction calculation using the documented-base taker fee scenario;
- deterministic campaign chronology;
- first-2,952-window adjudication sample to prevent later optional-stopping changes;
- strict pre-registered `q95 move > q50 friction` rule;
- equality is FAIL, missing required friction is INCONCLUSIVE;
- fee remains SCENARIO; latency/funding remain UNKNOWN;
- simple adjacent-sign / zero-move dependence diagnostics;
- unit tests for campaign immutability, overlap/digest protection, boot/segment boundaries, readiness, gate outcomes, and deterministic digests;
- `artifacts/stage_05/frontier_campaign_contract.json`.

Still pending in TASK-018:

- dataset -> immutable segment-evidence loader;
- reusable bounded segment runner over TASK-016/014/015/017;
- operational persistent-host runbook;
- real prospective campaign accumulation to >= 2,952 valid 50-second windows;
- final Frontier Gate adjudication.

No predictive model, private endpoint, order, signer, or capital logic is present.


## Collection tooling progress

Added after the campaign core:

- tamper-checked TASK-015 dataset loader;
- full manifest bundle-hash recomputation;
- SHA-256 verification of every materialized table;
- strict source/domain/wall-interval reconstruction from Parquet;
- bounded public dual-source evidence-segment runner;
- exclusive segment publication only after recorder/audit/normalization/materialization checks;
- immutable per-segment evidence binding recorder summary, normalization report, dataset manifest, and frontier audit;
- campaign initialization with frozen fee scenario;
- automatic discovery of fully published segments only;
- incomplete segment directories are reported but never counted;
- re-verification of all bound segment evidence during discovery;
- versioned deterministic campaign reports keyed by campaign-manifest SHA;
- CLI:
  - `init-frontier-campaign`;
  - `run-frontier-segment`;
  - `report-frontier-campaign`;
- fake-server end-to-end test through capture -> QCR1 -> normalize -> Parquet -> segment evidence -> aggregate report;
- persistent-host runbook;
- systemd one-shot segment service + timer.

The segment runner does not accept fee assumptions independently from the campaign CLI: the CLI loads the frozen campaign fee scenario before each run.

Real 2,952-window collection and final gate adjudication remain pending.


## Operational smoke validation

One-shot public-only workflow `35940052539` validated the complete segment path on real public mainnet data:

- duration: 30 seconds;
- raw frames: **10,789**;
- normalized events: **10,999**;
- segment publication: PASS;
- dataset bundle SHA-256: `9d24f826068a89f53b133ca6a8d034fa0680d86d71036936e615455806f1bf72`;
- segment evidence SHA-256: `55341a47b460ddbcc897c665a51b385680dbc9e27491b1b1cbe7e395055a5cd8`;
- campaign manifest SHA-256: `ad5e9a508ae1851057bf4e33029c6ed097054bb599ad043fe795ca11ae0bd1e2`;
- incomplete segment directories: 0;
- readiness: `COLLECTING`;
- gate decision: `INCONCLUSIVE`;
- valid 50-second windows: 0, expected because the smoke duration is shorter than the pre-registered 50-second horizon.

The temporary network workflow was removed immediately after the successful smoke.

TASK-018 is **not complete**: the prospective campaign still requires at least 2,952 valid non-overlapping 50-second windows and therefore persistent-host collection materially longer than the mathematical ~41-hour minimum when gaps/exclusions are included.


## Tooling merge provenance

Collection tooling merged through replacement PR #19 in commit `0a169e2205252bd07863a31e2653ea834fd8e514`.

PR #18 was closed as superseded after a STATUS-only mainline divergence; its TASK-018 implementation was cleanly rebased onto current `main` in PR #19.

Final network-independent CI run `35940389564`:

- Ruff: PASS;
- Ruff format: PASS;
- strict mypy: PASS — 74 source files;
- pytest Python 3.12: **359 PASS**;
- pytest Python 3.13: **359 PASS**.

Operational public-only smoke workflow `35940052539`:

- duration: 30 seconds;
- raw frames: **10,789**;
- normalized events: **10,999**;
- immutable segment publication: PASS;
- incomplete segment directories: 0;
- readiness: `COLLECTING`;
- gate: `INCONCLUSIVE`;
- 50-second valid windows: 0, expected because smoke duration was shorter than the 50-second target horizon.

Remaining TASK-018 work is evidence collection, not repository implementation: accumulate at least **2,952 valid non-overlapping 50-second windows** on a persistent public-only collector, then run deterministic Frontier Gate adjudication.


## Final adjudication — 2026-09-26

**TASK-018 COMPLETE. Frontier Gate: `PASS_FEASIBILITY`.**

The final deterministic prospective report used the frozen first-2,952-window adjudication sample exactly as pre-registered.

- campaign/report manifest SHA-256: `f82ba391ddaeac85ddb4787aec84d3cb85c17794101486c357cbb5bbd41f161c`;
- report SHA-256: `d2289bff1d2d3ffddc246456ff6ea9c6a4ae7663e1805d40cc0802e33891a3b2`;
- accepted segments: **182**;
- total valid non-overlapping 50-second windows: **3,076**;
- adjudication windows: **2,952**;
- excluded candidate windows: **521**;
- q95 absolute primary-mid movement: **9.183776917709780722417361000 bps**;
- q50 known friction floor: **9.123151337258348319833680000 bps**;
- q95 minus q50: **+0.060625580451432402583681000 bps**;
- q50 friction / q95 movement: `0.9933986222667796459142534313`;
- adjacent non-zero sign agreement: `0.5278725824800910125142207053`;
- zero-move fraction: `0.1063685636856368563685636856`;
- readiness: `READY_FOR_FRONTIER_ADJUDICATION`;
- decision: **`PASS_FEASIBILITY`**.

Evidence classes remain: fee = `SCENARIO`; latency = `UNKNOWN`; funding-boundary cost = `UNKNOWN`. Unsupported components remain actual project-account fee tier, submit-to-ACK/fill latency, realized own-order slippage/impact, boundary-aligned funding cost, maker economics, and predictability.

This PASS means only that a 50-second region is economically plausible relative to currently known friction. It is **not** evidence of a predictable or profitable strategy. The DKW planning count assumed IID; the dependence diagnostics do not establish IID.

Committed closeout artifact: `artifacts/stage_05/frontier_gate_50s.json`.

Next work package: `tasks/TASK_019.md` — Stage 1 Minimal Shared Simulator.
