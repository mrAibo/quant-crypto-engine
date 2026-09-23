# Stage 2 — Quantitative Falsification and Gate 1

## Objective

Test a deliberately small registered strategy family and select at most one BTC champion for untouched chronological confirmation.

## Model sequence

1. No-trade/accounting control.
2. Randomized control.
3. Simple deterministic hypotheses using a frozen small feature set.
4. Regularized logistic regression.
5. Optional shallow LightGBM only under a registered residual hypothesis.

## Candidate feature families

- top-level order-book imbalance;
- trade-flow imbalance;
- short/long momentum or reversal hypotheses;
- spread/depth;
- realized volatility;
- external-reference/local displacement.

Feature definitions and horizons must be frozen before confirmation. No feature explosion or unrestricted threshold/hyperparameter search.

## Validation

Chronological pilot/development/confirmation separation, purging/embargo, dependence-aware inference, multiple-testing registry, effective sample-size/power planning, and one protected champion confirmation.

## Exit

Gate 1 `PASS` is required before production execution engineering begins.
