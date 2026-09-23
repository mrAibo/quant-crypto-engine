# Stage 0.5 — Profitability / Economic Frontier

## Objective

Determine whether any supported horizon/size region is economically plausible for a conservative taker strategy before fitting models.

## Required distinctions

1. Market movement.
2. Predictable movement.
3. Executable net edge.

Large volatility alone is not evidence of predictability.

## Core work

- derive candidate horizons from measured data cadence and explicit latency scenarios;
- measure movement/volatility distributions;
- walk observed bid/ask depth for executable prices;
- apply fees/funding once;
- run latency and residual-slippage scenarios without double counting;
- measure pilot signal decay only for feasibility;
- quantify uncertainty and unsupported cells;
- compress the horizon grid to a small finite set for Stage 2.

## Exit

- Supported taker region exists → continue.
- Taker branch unsupported but maker might be plausible → conditional maker-research pivot later, not an optimistic offline queue backtest.
- No supported region → stop the branch.
