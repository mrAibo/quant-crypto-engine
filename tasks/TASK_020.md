# TASK-020 — Stage 2 Signal-Existence Dataset and Falsification Protocol

## Status

**NEXT AFTER TASK-019**

## Context

TASK-018 established only 50-second economic plausibility. TASK-019 provides the shared
deterministic simulator/accounting path. The next uncertainty is whether any causal information
available at decision time predicts executable BTC outcomes strongly enough to justify a frozen
policy experiment.

Do not fit a model or tune a strategy before this task freezes the experiment protocol.

## Objective

Build a deterministic, leakage-resistant Stage-2 opportunity/feature dataset and pre-register the
first bounded signal-existence experiments, controls, chronological partitions, metrics, and
stopping rules.

## Binding principles

- BTC is PRIMARY; ETH is REPLICATION and reported separately.
- The target economic horizon remains 50 seconds for the first signal-existence work.
- Every feature must be available at or before the decision cursor.
- No feature may use future Hyperliquid or Binance state, future gap knowledge, or retrospective
  repair.
- Data used to choose feature definitions/thresholds is not untouched confirmation.
- Trial accounting must use the TASK-019 shared simulator and controls.
- Unknown account-specific fees, latency, impact, and funding remain explicit; they are not zero.

## Required work

1. Define the causal feature-row contract and deterministic serialization.
2. Build feature rows from existing normalized Hyperliquid + Binance evidence with explicit
   availability timestamps and host/boot domains.
3. Freeze a small feature set motivated by microstructure/cross-venue mechanics rather than broad
   feature mining.
4. Derive chronological development / selection / untouched-confirmation partitions before
   evaluating candidate-policy economics.
5. Carry no-trade and randomized-direction controls through the exact same rows/simulator.
6. Define dependence-aware uncertainty and the business-net hurdle required for later Gate 1.
7. Pre-register at most a small number of deterministic signal hypotheses before evaluating them.
8. Record all attempted hypotheses/trials, including failures.

## Candidate feature families allowed for pre-registration

Only if causally available and explicitly defined before evaluation:

- Hyperliquid BBO spread and short-horizon mid changes;
- top-of-book or L2 imbalance using observed snapshot depth only;
- Binance reference BBO/mid changes;
- cross-venue mid dislocation / lead-lag state;
- observed public funding/mark/oracle context available at the cursor.

This list is a design boundary, not permission to exhaustively search transformations or windows.

## Required tests

- no future leakage under equal/near-equal timestamps;
- no cross-boot monotonic comparison;
- deterministic feature rows and digest;
- feature availability timestamps no later than decision cursor;
- chronological partition boundaries deterministic and non-overlapping;
- untouched confirmation cannot influence development/selection transforms;
- BTC/ETH separation;
- controls use identical opportunity rows and accounting;
- missing/stale/gapped inputs remain explicit invalid/missing values;
- complete feature/trial provenance.

## Definition of Done

1. A frozen Stage-2 dataset contract exists.
2. Chronological partitions and their derivation are committed before model/policy evaluation.
3. The first bounded deterministic hypotheses and controls are pre-registered.
4. No broad feature/window/hyperparameter search is implemented.
5. Ruff/format/strict mypy/pytest are green on Python 3.12 and 3.13.
6. STATUS.md identifies the first actual falsification run as the next work package.

## Do Not Build

- LightGBM;
- broad feature mining or threshold sweeps;
- Jev/GPT runtime;
- maker simulation;
- OMS/signing/orders;
- private/account capture;
- capital deployment.

Regularized logistic regression remains a later bounded baseline after the deterministic
signal-existence protocol is frozen and exercised.
