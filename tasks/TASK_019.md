# TASK-019 — Stage 1 Minimal Shared Simulator

## Status

**READY TO START**

## Context

TASK-018 / Frontier Gate completed with `PASS_FEASIBILITY` on 2026-09-26.

That result permits predictability testing but does not prove a signal or positive expectancy. Stage 1 therefore builds the smallest deterministic simulator/accounting foundation that later hypotheses can share without introducing causal shortcuts or production execution complexity.

## Objective

Implement a minimal shared event-driven simulator that can evaluate frozen causal policies on immutable normalized evidence with complete trial accounting and explicit cost semantics.

Stage 1 is infrastructure for falsification, not a strategy-search engine.

## Binding inputs

- BTC remains the PRIMARY market.
- ETH remains REPLICATION/generalization and is reported separately.
- Hyperliquid remains the execution candidate.
- Binance USDⓈ-M remains the external reference source.
- Existing normalized event and causal-time contracts remain authoritative.
- The 50-second Frontier Gate result is context only; it is not a trading rule.
- Actual project-account fees, submit-to-fill latency, own-order impact/slippage, and boundary-aligned funding remain UNKNOWN until separately measured.

## Required simulator contracts

1. **Causal clock/event cursor**
   - decisions can use only information available at or before the decision cursor;
   - no future timestamps, future book state, or retrospective repair may leak into policy input;
   - cross-host/boot monotonic timestamps are never compared.

2. **Policy interface**
   - deterministic input/output contract;
   - no network, exchange, filesystem, wall-clock, GPT, or Jev calls inside policy logic;
   - explicit abstain/no-trade action.

3. **Execution/accounting model**
   - taker-only first;
   - executable-side top-of-book accounting;
   - fees, spread/executable price, funding, latency and impact are represented once and never double-counted;
   - UNKNOWN cost components remain explicit scenario/unknown dimensions rather than silently assumed zero.

4. **Trial ledger**
   - every decision opportunity counted, including no-trade/reject/invalid intervals;
   - entry/exit reason, timestamps, prices, costs and PnL components auditable;
   - deterministic serialization and digest.

5. **Controls**
   - no-trade/accounting control;
   - deterministic randomized-direction control with explicit seed provenance;
   - controls use the same event/cost/ledger path as later candidate policies.

## Required tests

At minimum:

- decision-time causality and no future leakage;
- deterministic replay for identical evidence/config/seed;
- policy core has no I/O dependency;
- no-trade control produces zero positions/trades and correct accounting;
- randomized control is seed-deterministic;
- taker entry/exit uses the correct executable side;
- fee/spread/funding/latency/impact components cannot be double-counted;
- UNKNOWN cost inputs are preserved as UNKNOWN or scenario, never fabricated;
- invalid/missing/stale intervals are represented explicitly;
- complete trial/opportunity accounting;
- ledger/report serialization and SHA-256 determinism;
- BTC primary and ETH replication remain separable.

## Deliverables

- minimal simulator module(s) under `src/cryptobot/sim/` or an equally narrow domain package;
- deterministic ledger/report contracts;
- no-trade and randomized controls;
- tests covering the contracts above;
- Stage-1 simulator contract artifact;
- concise documentation of supported and intentionally unsupported economics.

## Definition of Done

1. One shared deterministic simulator path can replay immutable evidence causally.
2. No-trade and randomized controls run through the exact same accounting path.
3. Complete opportunity/trial accounting is auditable and deterministic.
4. Cost components are separated and not double-counted.
5. UNKNOWN real-world costs remain explicit.
6. No broad model/feature/hyperparameter search is introduced.
7. Ruff, format, strict mypy and pytest are green on Python 3.12 and 3.13.
8. `STATUS.md` is updated with the Stage-1 simulator result and next falsification task.

## Do Not Build

- LightGBM;
- broad hyperparameter optimization;
- Jev/GPT runtime;
- maker execution simulation;
- OMS/signing/orders;
- private/account capture;
- capital deployment;
- autonomous strategy mutation.

Regularized logistic regression is part of the later bounded model sequence, not this simulator-foundation task.
