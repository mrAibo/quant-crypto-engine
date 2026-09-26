# TASK-025 — Stage 2 Bounded Microstructure Economic Development

## Status

**READY TO START**

## Context

TASK-023 stopped the bounded 50-second BBO/Binance family.

TASK-024 stopped the bounded 300-second BBO/Binance family.

The observed H2 directional effect was not enough to overcome executable taker
economics. Extending the horizon to 300 seconds increased movement headroom but did
not rescue the registered small family.

The old Stage-2 confirmation partition remains unopened and excluded.

## Objective

Test one small, predeclared microstructure feature family on DEVELOPMENT evidence
only.

The goal is to determine whether causal order-flow/depth state can identify the rare
opportunities whose executable movement is large enough to overcome spread plus the
4.5 bps/side fee scenario.

Do not collect fresh registered test evidence unless this bounded development family
first passes its economic gate.

## Development evidence

Primary path:

- already captured exposed Gate-period Hyperliquid L2 snapshots;
- Hyperliquid trades;
- Hyperliquid BBO;
- Binance reference BBO/trades;
- only timestamps strictly before the old confirmation boundary.

Optional expansion:

- official requester-pays Hyperliquid historical L2 archive;
- development-only;
- record exact S3 URI, retrieval time, object size/hash/schema/coverage;
- never claim archive evidence as prospective receive-time confirmation.

Aibo currently has no AWS CLI/credentials configured. The primary path must proceed
without waiting for S3 access.

## Frozen feature family

Keep the first microstructure family small.

Decision-time causal features:

1. top-5 depth imbalance:
   `(sum_bid_size_5 - sum_ask_size_5) / (sum_bid_size_5 + sum_ask_size_5)`;
2. Hyperliquid aggressive trade-flow imbalance over the prior **5 seconds**:
   signed aggressive volume divided by total aggressive volume;
3. Binance reference aggressive trade-flow imbalance over the prior **5 seconds**;
4. Hyperliquid primary mid return over the prior **5 seconds**;
5. Binance reference mid return over the prior **5 seconds**;
6. cross-venue 5-second return gap:
   primary return minus reference return;
7. current executable spread bps;
8. existing top-of-book imbalance as a benchmark feature.

All source observations must have receive-time availability <= decision cursor.
Missingness is explicit. No retrospective future-gap repair is permitted.

## Economic target

For each candidate action/horizon, evaluate actual executable Hyperliquid bid/ask
entry and exit plus the frozen 4.5 bps/side fee scenario.

Unknown costs remain UNKNOWN:

- latency;
- own-order impact/slippage;
- boundary funding;
- actual project-account fee tier.

Positive partial-known-cost PnL is development evidence only, not full business net.

## Model scope

Exactly one regularized linear baseline first:

- L2 logistic regression;
- target = positive partial-known-cost executable PnL;
- no LightGBM;
- no unrestricted hyperparameter search;
- thresholds/gates derived from DEV_A only and frozen before DEV_B evaluation.

If an interpretable deterministic rule emerges from DEV_A, it may be registered only
if specified before DEV_B outcomes are inspected. Otherwise use the single logistic
baseline.

## Horizons

Do not reopen a broad horizon sweep.

Use only the already developed horizons:

- 50 seconds;
- 300 seconds.

The development protocol must predeclare how the two horizons are treated in the
testing budget before outcome evaluation.

## Development gate

A family is development-eligible for a future fresh test only if DEV_B shows:

1. sufficient valid-trade support predeclared before DEV_B;
2. positive mean partial-known-cost PnL;
3. positive cumulative partial-known-cost PnL;
4. positive median known-net bps or another explicitly frozen downside criterion;
5. chronological stability diagnostics that do not depend on a single short cluster.

If it fails, stop the family. Do not add thresholds/features after DEV_B exposure.

## Definition of Done

1. Old confirmation remains unopened/excluded.
2. Point-in-time microstructure feature builder is deterministic and tested.
3. Feature family and horizon budget are frozen before DEV_B evaluation.
4. DEVELOPMENT artifact records source digests and missingness.
5. Economic evaluation is executable bid/ask + frozen fee scenario.
6. Development decision is committed:
   - FREEZE_MICROSTRUCTURE_FAMILY, or
   - STOP_MICROSTRUCTURE_FAMILY.
7. If frozen, a separate next task defines fresh prospective SELECTION/CONFIRMATION.
8. Ruff/format/strict mypy/pytest are green on Python 3.12 and 3.13.

## Do Not Build

- old-confirmation evaluation;
- broad feature mining;
- new feature additions after DEV_B outcomes;
- LightGBM;
- Jev/GPT runtime;
- maker simulation;
- OMS/signing/orders;
- private/account capture;
- capital deployment.
