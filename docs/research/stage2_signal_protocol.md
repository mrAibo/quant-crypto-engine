# Stage 2 Signal-Existence Protocol

## Purpose

This protocol freezes the first bounded signal-existence experiment **before**
candidate H1/H2 results are evaluated.

The Frontier Gate established only that 50-second movement can exceed the current
known-friction scenario. It did not establish predictability.

## Frozen source

The PRIMARY dataset is regenerated deterministically from the final TASK-018 Gate
report and its 182 verified segment datasets.

- Gate report SHA-256:
  `d2289bff1d2d3ffddc246456ff6ea9c6a4ae7663e1805d40cc0802e33891a3b2`
- campaign manifest SHA-256:
  `f82ba391ddaeac85ddb4787aec84d3cb85c17794101486c357cbb5bbd41f161c`
- BTC feature dataset rows: **3,259**
- BTC feature dataset SHA-256:
  `3eeb0b405a9db439b7711b453ec9820707068bbfba855bf120124b79aa32b237`

The full generated dataset remains on the evidence host and is reproducible from the
immutable source evidence. The repository commits the contract and hashes rather
than a multi-megabyte result file.

## Hypotheses

Only two deterministic hypotheses are registered.

### H1 — Binance 5-second reference lead

At decision time, use the sign of the Binance USD-M BTCUSDT BBO-mid change over a
fixed five-second lookback.

Current and anchor observations must both be causally available, in the same
host/boot domain, and no more than two seconds stale relative to their target
timestamps.

- positive -> LONG
- negative -> SHORT
- zero or missing -> ABSTAIN

No alternate lookback or threshold may be tried under this protocol.

### H2 — Hyperliquid BBO imbalance

At the exact decision BBO:

`(bid_size - ask_size) / (bid_size + ask_size)`

- positive -> LONG
- negative -> SHORT
- zero or missing -> ABSTAIN

No threshold sweep is permitted.

Hyperliquid spread is retained as context/provenance but is not a third registered
hypothesis.

## Label and horizon

The label is the signed Hyperliquid PRIMARY mid return over the frozen 50-second
horizon.

Future interval validity belongs only to the outcome side. Future gap knowledge is
never exposed to the decision feature view.

Zero-direction labels remain in complete opportunity accounting but are excluded
from the Bernoulli directional-accuracy denominator.

## Chronological partitions

Partition boundaries are derived from PRIMARY decision-time feature availability
only. Outcome values are not consulted.

- DEVELOPMENT: 1,110 rows
- SELECTION: 847 rows
  - H1-ready: 783
  - H2-ready: 847
- CONFIRMATION: 1,302 rows
  - H1-ready: 1,225
  - H2-ready: 1,302

Selection begins at wall-ns `1790292370076995098`.
Untouched confirmation begins at wall-ns `1790341044387002988`.

Equal wall timestamps stay in the later partition.

ETH REPLICATION uses these same BTC-derived wall boundaries. ETH results may not
choose, tune, reverse, or rescue the BTC champion.

## Power planning

The family contains exactly two hypotheses.

- family alpha: 0.05
- Bonferroni alpha per hypothesis: 0.025
- planning power: 0.80
- null directional accuracy: 0.50
- selection planning alternative: 0.55 -> minimum 783 evaluable rows
- confirmation planning alternative: 0.54 -> minimum 1,225 evaluable rows

These are planning assumptions, not optimized targets. Win rate remains descriptive,
not the project objective.

## Selection and stopping

Selection evaluates H1 and H2 exactly once on the SELECTION partition.

A selection-pass candidate requires:

1. the frozen minimum evaluable support;
2. one-sided exact-binomial IID-reference p <= 0.025;
3. a dependence-adjusted directional lower bound above 0.50;
4. positive mean TASK-019 partial-known-cost PnL on TRADED opportunities.

Dependence is reported using chronological correctness autocorrelation at lags 1..10
and a conservative effective-sample diagnostic. This does not create a formal IID
guarantee.

If both hypotheses pass, the one with the higher dependence-adjusted lower bound is
the champion. An exact tie is resolved lexicographically by hypothesis ID.

Only the champion may be opened on untouched CONFIRMATION. If it fails, the runner-up
may **not** be tried on the same holdout.

No peeking-based optional stopping, threshold changes, sign reversals, additional
lookbacks, or extra hypotheses are allowed after registered results are observed.

## Controls

No-trade and seeded randomized-direction controls use the exact same frozen
opportunity rows and TASK-019 accounting path.

Random control seed: `2026092601`.

Controls are diagnostics; they are not alternate hypotheses that expand the search
family.

## Economic boundary

The positive partial-known-cost PnL requirement is necessary but not sufficient for
business viability.

Fully accounted business-net expectancy remains **NOT EVALUABLE** because actual
project-account fees, realized latency, own-order impact/slippage, and
boundary-aligned funding remain unsupported or UNKNOWN.

A later Gate 1 requires those costs to be measured and a dependence-aware lower
uncertainty bound on fully-accounted net expectancy to remain above zero on locked
confirmation evidence.

## Forbidden before this protocol is exercised

- logistic regression;
- LightGBM;
- threshold/lookback sweeps;
- broad feature mining;
- Jev/GPT runtime;
- maker simulation;
- OMS/signing/orders;
- private/account capture;
- capital deployment.
