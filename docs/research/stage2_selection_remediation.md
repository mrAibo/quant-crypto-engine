# Stage 2 Selection Evidence Remediation

## Decision

TASK-022 closes the registered H1/H2 family with:

**STOP_REGISTERED_H1_H2_FAMILY**

Source TASK-021 selection artifact:

- `artifacts/stage_2/selection_result.json`
- SHA-256 `e3403ef3eb6016040344dd8c17f4174b9190ca1a3aa5f5a59f54e1af7f7fb5a0`

Remediation artifact:

- `artifacts/stage_2/selection_remediation.json`
- SHA-256 `fec7cbb77fe67c672a2319fadee7e6a94f79fef013c16c6033b55fbb07f574d5`

The old confirmation partition remains unopened and excluded.

## Why the family stops

Both registered candidates failed the frozen partial-known-cost economic filter.

H1:

- mean partial-known-cost PnL: `-74.0311082956259426847662141779788838612368024132730015082956`
  quote units per traded opportunity at quantity 1 BTC;
- gap to partial-known-cost breakeven: the exact positive magnitude of that value;
- directional-evaluable support: 644, below the registered 783 floor;
- dependence-adjusted 97.5% lower bound: approximately 49.9821%.

H2:

- mean partial-known-cost PnL: `-71.1355103950103950103950103950103950103950103950103950103950`
  quote units per traded opportunity at quantity 1 BTC;
- gap to partial-known-cost breakeven: the exact positive magnitude of that value;
- directional-evaluable support: 930;
- directional accuracy: approximately 58.3871%;
- dependence-adjusted 97.5% lower bound: approximately 54.8815%.

H2 therefore contains useful directional information in the observed selection sample,
but the registered taker implementation does not convert it into positive
partial-known-cost economics. Directional significance alone is insufficient.

The result is not full business-net economics. Actual project-account fee tier,
latency, own-order impact/slippage and boundary funding remain UNKNOWN.

## H1 attrition

The registered H1 selection path is:

- total SELECTION rows: 1,123;
- feature-ready: 1,059 / 1,123 = approximately 94.30%;
- nonzero/actionable H1 decisions: 744 / 1,059 feature-ready = approximately 70.25%;
- valid executable opportunities after an action: 663 / 744 = approximately 89.11%;
- nonzero directional outcomes after a trade: 644 / 663 = approximately 97.13%;
- final directional-evaluable yield: 644 / 1,123 = approximately 57.35%.

This explains why the pre-selection support buffer was still insufficient for H1.

## Counterfactual unchanged-H1 replication

A replication was calculated for planning transparency but is **not registered**.

For each of the four attrition stages, TASK-022 uses a one-sided Wilson lower bound
with Bonferroni planning alpha `0.025 / 4`. Their product is a conservative
directional-yield estimate of approximately 50.23%.

Using the observed H1 positive-autocorrelation design effect
`1.10181251073305046318539571912885256213592045676003696993203`:

- selection target 783 effective directional rows -> 863 directional rows after
  dependence planning -> **1,719 fresh raw rows** after attrition planning;
- confirmation target 1,225 effective directional rows -> 1,350 directional rows
  after dependence planning -> **2,688 fresh raw rows**;
- total counterfactual fresh support: **4,407 rows**.

This plan is intentionally not registered because H1 also failed the frozen economic
filter. Future dependence can differ, so even the counterfactual plan is a planning
buffer rather than a guarantee.

## Historical versus new data

Historical data remains useful, but only for:

- diagnostics;
- regime/context research;
- feature engineering;
- development and training of a **new** signal family;
- testing data-pipeline code.

Historical evidence must not be presented as fresh confirmation after candidate
performance has already been observed.

For the next registered family:

1. use only explicitly labeled development evidence while designing it;
2. freeze features/model, objective, costs, thresholds, sample sizes and stopping
   rules before the test;
3. collect a **new prospective SELECTION** sample after the freeze;
4. reserve a later **new prospective CONFIRMATION** sample that remains untouched
   until a selection champion exists.

The previous Stage-2 confirmation partition remains unopened and excluded from the
new family.

Available Binance retrospective archives are therefore development context only.
They also cannot replace native Hyperliquid BBO/L2 receive-time evidence.

## Next action

Proceed to `TASK-023 — Stage 2 New Economic Signal Family Design`.

The next family should target executable economic value rather than directional
accuracy alone. Any use of H1/H2 observations in designing that family makes it a
new protocol and therefore requires new prospective selection and confirmation
evidence.
