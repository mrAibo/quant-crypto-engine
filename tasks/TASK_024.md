# TASK-024 — Stage 2 Longer-Horizon Economic Development

## Status

**READY TO START**

## Context

TASK-023 stopped the bounded 50-second economic family.

Changing the horizon after observing those results is a new development family.

## Objective

Determine whether a longer, still bounded horizon provides enough executable movement
headroom to justify a new registered family.

This task is DEVELOPMENT only. It must not open the old confirmation partition or
collect/register fresh test evidence until a longer-horizon protocol passes the
development gate.

## Pre-outcome horizon registry

Use only the already created development-only 1-2-5 minute horizon context:

- candidate horizons: 60s, 120s, 300s;
- Binance historical aggTrade data: 2026-08-01 through 2026-08-07;
- BTC primary context, ETH replication context;
- source is development-only and does not have Hyperliquid receive-time semantics.

The pre-Hyperliquid-outcome decision selected **300 seconds** as the development
horizon because it was the shortest scanned horizon with material movement headroom
over the approximately 9 bps fee-only round trip.

The 300s bounded registry was written before Hyperliquid 300s outcome evaluation.

## Frozen 300s development candidates

Exactly four deterministic candidates:

1. E300_1_IMB_STRONG — sign H2, |imbalance| >= 0.75
2. E300_2_IMB_EXTREME — sign H2, |imbalance| >= 0.95
3. E300_3_IMB_STRONG_BIN_ALIGN — |imbalance| >= 0.75, Binance sign agrees,
   |Binance 5s return| >= 0.5 bps
4. E300_4_IMB_STRONG_BIN_ALIGN_STRONG — |imbalance| >= 0.75, Binance sign agrees,
   |Binance 5s return| >= 1.5 bps

Development split: chronological 60/40.

Deterministic pass requires positive DEV_B mean and cumulative partial-known-cost PnL
with at least 30 valid trades.

If none pass, only the already preregistered 300s L2-logistic fallback may run.

## 300s logistic fallback

Features:

- action × Hyperliquid BBO imbalance;
- |Hyperliquid BBO imbalance|;
- action × Binance 5s return;
- |Binance 5s return|.

Model:

- L2 logistic regression;
- lambda = 1;
- fixed deterministic optimizer;
- DEV_A score gates q90 and q95 only.

Pass requires positive DEV_B mean and cumulative partial-known-cost PnL with at least
30 valid trades.

## Evidence rules

- old Stage-2 confirmation remains unopened/excluded;
- 300s development cache may use only evidence before the old confirmation wall;
- executable economics use bid/ask and 4.5 bps/side fee scenario;
- latency, impact, funding and actual project-account fee remain UNKNOWN;
- no result from this task is confirmatory.

Official Hyperliquid historical L2 archive may be considered for additional development
support only. It is requester-pays, updated approximately monthly, may be incomplete,
and does not replace prospective receive-time evidence.

## Definition of Done

1. Horizon-context provenance and hashes are committed.
2. 300s registry is committed and demonstrably pre-outcome.
3. 300s cache provenance is reproducible.
4. Deterministic candidates are evaluated exactly once.
5. Logistic fallback is used only if deterministic candidates fail.
6. A deterministic DEVELOPMENT decision is committed:
   - FREEZE_300S_FAMILY, or
   - STOP_300S_FAMILY.
7. Old confirmation remains unopened.
8. Ruff/format/strict mypy/pytest are green on Python 3.12 and 3.13.
9. STATUS.md advances to the next work package.

## Do Not Build

- old-confirmation evaluation;
- broad horizon sweep beyond 60/120/300;
- new thresholds after 300s outcomes;
- LightGBM;
- Jev/GPT runtime;
- maker simulation;
- OMS/signing/orders;
- private/account capture;
- capital deployment.
