# TASK-017 — Stage 0.5 Profitability Frontier Measurement Contract

## Status

`IN REVIEW — PRIMITIVES IMPLEMENTED, CI PENDING`

## Objective

Start the first economic-feasibility phase without fitting a predictive model.

Build deterministic, auditable measurement primitives that answer:

> For which BTC perpetual horizons and executable-size regions could market movement plausibly exceed conservative taker friction?

This task measures the **economic frontier**. It does not claim predictability or profitability.

The mandatory distinction is:

1. observed market movement;
2. predictable movement;
3. executable net edge.

TASK-017 covers item 1 and the execution-cost floor needed to bound item 3. Predictability remains unproven.

## Inputs

Use only validated Stage-0 artifacts/contracts:

- QCR1 raw authority;
- TASK-014 causal normalized records;
- TASK-015 deterministic Parquet datasets;
- Hyperliquid BTC primary market;
- Binance USDⓈ-M BTCUSDT reference market;
- verified evidence contract for documented fee/funding facts;
- exact Decimal market values.

ETH is not used to choose the initial frontier. ETH remains an untouched replication/generalization market.

## Binding principles

1. **No model fitting.**
2. **No strategy optimization.**
3. **No trade simulation that invents fills.**
4. **No maker economics.**
5. **No fixed profitability claim from volatility alone.**
6. Actual future project-account fees remain UNKNOWN until measured; documented base taker fees may be used only as an explicitly labeled scenario.
7. Spread, depth impact, fees, funding, latency, and residual slippage must not be double-counted.
8. Unsupported cells remain unsupported; no interpolation across missing depth/time evidence.
9. All computations use exact Decimal where money/prices/sizes enter the calculation.
10. Every report records the source dataset manifest/digests and experiment configuration.

## Work package A — Dataset sufficiency and cadence

Create a deterministic frontier input audit that reports at minimum:

- dataset causal-domain count;
- observed wall/monotonic duration;
- frame/event counts by source/type;
- BTC BBO/L2/trade/context coverage;
- Binance BTC reference BBO/trade coverage;
- inter-arrival distributions for primary BBO and L2 observations;
- largest observed gaps;
- unsupported intervals;
- number of independent/non-overlapping horizon windows available for each candidate horizon.

A short smoke dataset may be used only as a **pipeline pilot**. It must not receive a Frontier Gate PASS.

## Work package B — Candidate horizon grid

Use a finite logarithmic 1-2-5 horizon grid expressed in seconds.

The grid is bounded by observed data rather than an arbitrary trading preference:

- lower bound must not be finer than the primary market-data cadence required by the calculation;
- upper bound must leave enough non-overlapping windows to estimate a movement distribution;
- each cell reports its actual sample count and coverage;
- latency scenarios are explicit scenario inputs, never presented as measured execution latency.

The report must expose why each horizon is included/excluded.

## Work package C — Market movement

For each supported horizon, measure BTC primary-market movement using causal BBO mid observations:

- signed mid return in basis points;
- absolute mid move in basis points;
- robust distribution summaries;
- sample count;
- time coverage;
- missing/gap exclusions.

Future observations are allowed here only because this is a retrospective **movement-label measurement**, not a feature available to a trading decision.

Do not call movement predictability.

## Work package D — Conservative taker friction floor

Implement deterministic friction primitives:

### Fees

Represent fees per side explicitly.

The current documented Hyperliquid base taker schedule may be used as a named scenario from the evidence contract, but the report must state that the actual future project-account tier is not yet measured.

Round-trip fee cost is counted exactly once.

### Spread / top-of-book

Measure executable top-of-book entry/exit friction from Hyperliquid BBO without treating mid price as executable.

### Depth

Provide a deterministic L2 book-walk primitive for hypothetical base size:

- buy consumes asks;
- sell consumes bids;
- return VWAP, filled size/notional, worst price, and unfilled remainder;
- never fill beyond displayed depth;
- never invent queue priority;
- crossed/suspect books are excluded or explicitly flagged.

TASK-017 may expose capacity curves, but it must not choose production capital.

### Funding

Public `activeAssetCtx` gives current funding but no native timestamp/boundary in the validated wire contract.

Therefore exact boundary-aligned funding cost is **unsupported** in TASK-017 unless a separately verified source establishes the needed timing.

A clearly labeled conservative scenario may be reported separately, but it must not be silently blended into observed execution cost.

### Latency / residual slippage

No measured submit-to-ACK/fill latency distribution exists yet.

TASK-017 accepts explicit stress scenarios and reports them as **SCENARIO**, not observation. It must not infer live slippage from market-data receive lag.

## Work package E — Frontier metrics

For each supported horizon/cost scenario compute model-free diagnostics such as:

- movement quantiles in bps;
- top-of-book round-trip friction floor in bps;
- documented-fee scenario in bps;
- total known friction floor;
- required gross directional move to break even;
- required capture fraction relative to selected absolute-move quantiles;
- data support/sample count;
- unsupported cost components.

These metrics are feasibility diagnostics only.

A cell cannot be labeled economically supported if a required cost component is silently missing.

## Required code

Expected modules:

- `src/cryptobot/research/frontier.py`
- `src/cryptobot/research/__init__.py`
- tests for exact return/friction/book-walk/horizon/audit behavior;
- `artifacts/stage_05/frontier_contract.json`.

A CLI/report runner may be added if it remains read-only and deterministic.

## Required tests

At minimum:

- exact BBO mid/spread arithmetic;
- signed and absolute bps movement;
- no binary-float market arithmetic;
- deterministic 1-2-5 horizon generation;
- horizon exclusion when coverage is insufficient;
- exact non-overlapping-window counts;
- long/short top-of-book friction;
- L2 buy book walk;
- L2 sell book walk;
- partial fill/unfilled remainder;
- no fill beyond displayed depth;
- invalid/crossed/suspect book handling;
- fee counted once per side;
- required-capture-fraction arithmetic;
- explicit UNKNOWN/unsupported funding timing;
- explicit scenario-vs-observed latency distinction;
- deterministic report serialization;
- source dataset digest binding.

## Pilot run

After code/CI is green, run the frontier pipeline on a bounded prospective dual-source dataset.

The pilot answers only:

- does the Stage-0.5 measurement pipeline work on real data?
- which horizon cells have enough observations to compute pilot diagnostics?
- what additional data duration is required for a defensible Frontier Gate decision?

A pilot **must not** promote the Frontier Gate solely because a short window looks favorable.

## Exit / next task

TASK-017 is complete when:

1. frontier measurement contracts are implemented and tested;
2. real prospective pilot data runs end to end;
3. the report clearly separates OBSERVED / SCENARIO / UNKNOWN inputs;
4. no model/alpha claim is made;
5. the required evidence duration/sample support for the actual Frontier Gate is derived from the chosen horizon grid rather than guessed.

Then define the next Stage-0.5 task for the evidence window and Frontier Gate adjudication.

## Do Not Build

- logistic regression / LightGBM;
- Jev / GPT / LLM runtime;
- broad feature search;
- strategy optimizer;
- maker queue simulator;
- OMS/signing/orders;
- live capital deployment.


## Implementation progress

Implemented first model-free frontier primitives:

- exact BBO mid/spread arithmetic;
- exact signed/absolute bps movement;
- exact per-side/round-trip fee arithmetic;
- direction-specific top-of-book round-trip friction;
- required-capture-fraction diagnostic;
- strict displayed-depth L2 book walking with explicit partial fills;
- crossed/locked/unsorted book rejection;
- deterministic 1-2-5 horizon grid;
- non-overlapping window support accounting;
- nearest-rank empirical quantile without float interpolation;
- OBSERVED / SCENARIO / UNKNOWN evidence classes;
- digest-bound deterministic frontier report contract;
- Stage-0.5 frontier contract artifact;
- 18 unit tests.

Still pending in TASK-017:

- dataset audit/real Parquet reader;
- prospective pilot frontier run;
- derived evidence-window requirement;
- final CI and merge.
