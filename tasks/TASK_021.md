# TASK-021 — Stage 2 Registered H1/H2 Selection Run

## Status

**READY TO START**

## Context

TASK-020 froze the Stage-2 dataset, partitions, H1/H2 definitions, controls, metrics and stopping rules before candidate performance was evaluated.

The untouched CONFIRMATION partition is reserved for at most one selection champion and must not be opened in this task.

## Objective

Evaluate the two pre-registered deterministic hypotheses exactly once on the frozen BTC SELECTION partition, run the frozen controls on the same opportunities, apply the frozen selection rule, and record either one champion or a family-level selection failure.

## Frozen source

- protocol: `artifacts/stage_2/signal_protocol.json`;
- BTC dataset SHA-256: `3eeb0b405a9db439b7711b453ec9820707068bbfba855bf120124b79aa32b237`;
- SELECTION wall interval begins at `1790292370076995098` and ends before `1790341044387002988`;
- SELECTION rows: **847**;
- H1-ready rows: **783**;
- H2-ready rows: **847**;
- confirmation rows/outcomes are forbidden input.

## Registered trials

1. `S2-SEL-H1-V1` — `S2-H1-BINANCE-REF-5S-SIGN-V1`
2. `S2-SEL-H2-V1` — `S2-H2-HL-BBO-IMBALANCE-SIGN-V1`

Controls:

- no-trade;
- randomized direction with frozen seed `2026092601`.

## Required implementation

1. Load and SHA-verify the frozen protocol and BTC feature dataset.
2. Select only PRIMARY SELECTION rows from the committed wall boundaries.
3. Reject any attempt to load/evaluate CONFIRMATION in the selection runner.
4. Evaluate H1 and H2 exactly once with the frozen sign rules.
5. Compute for each registered trial:
   - total selection rows;
   - feature-ready / abstain / outcome-valid / directional-evaluable counts;
   - correct-direction count and directional accuracy;
   - exact one-sided binomial IID-reference p-value under p=0.50;
   - correctness autocorrelation lags 1..10;
   - frozen positive-autocorrelation design effect;
   - effective sample size;
   - one-sided 97.5% Wilson lower bound using effective sample size;
   - TASK-019 simulation counts and mean partial-known-cost PnL on TRADED opportunities.
6. Run the no-trade and frozen randomized control on the exact same opportunities.
7. Apply the committed selection-pass rule without modification.
8. If both pass, choose the highest dependence-adjusted lower bound; exact tie breaks lexicographically by hypothesis ID.
9. Write an immutable deterministic selection artifact with source/protocol/dataset/trial digests.

## Selection outcomes

Only these outcomes are allowed:

- `SELECTION_CHAMPION_H1`;
- `SELECTION_CHAMPION_H2`;
- `STOP_FAIL_SIGNAL_SELECTION`;
- `INCONCLUSIVE_SELECTION` for missing/corrupt/insufficient required evidence.

A selection failure does not authorize threshold changes, sign reversal, another lookback, H3, or opening confirmation.

## Tests

At minimum:

- confirmation rows cannot be passed to the selection evaluator;
- protocol/dataset SHA mismatch hard-fails;
- exact-binomial calculation deterministic;
- dependence diagnostic deterministic with edge cases;
- effective sample size never exceeds evaluable count;
- Wilson lower-bound calculation deterministic;
- H1/H2 action/evaluable accounting exact;
- TASK-019 accounting uses the same selection opportunities;
- controls use identical opportunity IDs;
- pass/fail and champion tie-break rules exact;
- deterministic selection report bytes and SHA-256;
- no hidden extra trial IDs.

## Definition of Done

1. H1 and H2 each have one immutable SELECTION result.
2. Controls are recorded on identical selection opportunities.
3. The frozen selection rule produces either one champion or a registered stop/failure.
4. CONFIRMATION was not opened.
5. All attempted trials including failures are preserved.
6. Ruff/format/strict mypy/pytest are green on Python 3.12 and 3.13.
7. STATUS.md identifies the next action:
   - champion -> single untouched confirmation task;
   - no champion -> stop registered family and design any new family as a new protocol using new/appropriately reserved evidence;
   - inconclusive -> evidence remediation.

## Do Not Build

- confirmation evaluation in this task;
- logistic regression;
- LightGBM;
- threshold/lookback sweeps;
- H3 or additional feature mining;
- Jev/GPT runtime;
- maker simulation;
- OMS/signing/orders;
- private/account capture;
- capital deployment.
