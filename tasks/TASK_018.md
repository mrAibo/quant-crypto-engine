# TASK-018 — Stage 0.5 Prospective Frontier Evidence Campaign

## Status

`PENDING`

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
