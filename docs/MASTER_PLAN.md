# Master Execution Plan

## Objective

Build an evidence-driven path toward an autonomous 24/7 cryptocurrency trading system. The project must be able to conclude **NO-GO** cheaply and credibly if no executable edge survives real costs.

The first deliverable is a trustworthy evidence system, not a trading bot.

## Scope

- Execution candidate: Hyperliquid.
- Primary research market: BTC perpetual.
- Replication/generalization market: ETH perpetual.
- One external major-market reference feed.
- Python 3.12+ layered/modular monolith.
- Deterministic strategy and risk core.
- Taker-only first economic validation.
- GPT removed from runtime v1.
- Jev is optional and separately gated as a trade-quality veto experiment only.
- Maker execution is deferred to a later live-measurement experiment.
- No autonomous self-modification.
- Human approval is required for strategy releases, capital increases, hard risk-limit changes, and reset of a latched halt.

## Critical path

```text
Stage 0   Evidence contract + market-data recorder
   ↓
Stage 0.5 Profitability/economic frontier
   ↓
Stage 1   Minimal shared simulator
   ↓
Stage 2   Quantitative falsification and untouched confirmation
   ↓
GATE 1    First economic GO/NO-GO
   ├─ FAIL → stop/pivot only under documented rules
   └─ PASS
        ↓
Stage 3   Replay parity
Stage 4   Shadow / forward paper evidence
Stage 5   Durable OMS / reconciliation / recovery
Stage 6   Independent watchdog + chaos/testnet
        ↓
Stage 7   Risk-derived micro-live
        ↓
Stage 8   Jev experiment (optional)
Stage 9   Maker experiment (optional)
Stage 10  Human-approved scaling + autonomous production
```

## Binding engineering principles

1. Core domain logic contains no exchange/network/filesystem I/O.
2. Raw market capture is immutable and replayable.
3. Time and data availability are explicit; no hidden wall-clock reads in strategy logic.
4. Economic accounting must not double-count spread, depth impact, latency, funding, or fees.
5. Production order intent is durable before transmission.
6. Ambiguous writes are never blindly retransmitted.
7. Reconciled exchange evidence is authoritative for orders, fills, positions, and cash.
8. Emergency paths never depend on AI or optional models.
9. Production restarts begin in recovery, never directly in RUNNING.
10. The system may automatically reduce risk; it may not automatically increase capital/risk limits.

## Model sequence before Gate 1

Keep the search space deliberately small:

1. No-trade/accounting control.
2. Randomized control.
3. Simple deterministic microstructure/cross-venue hypotheses.
4. Regularized logistic regression on a frozen feature set.
5. LightGBM only if a specific residual nonlinear hypothesis justifies it.

No broad hyperparameter search. No full Quant/Jev/GPT ensemble.

## Evidence ladder

- **Backtest:** historical causal signal under modeled costs.
- **Replay:** event-driven parity and no causal shortcuts.
- **Shadow:** prospective decisions and runtime timing; no actual fills.
- **Paper:** prospective economics under the same fill model; no actual liquidity proof.
- **Testnet:** API mechanics and recovery; not profitability.
- **Micro-live:** actual fills, fees, funding, operational behavior, micro-size economics.
- **Scaled-live:** capacity and impact at the sizes actually traded.

No stage is allowed to claim evidence that belongs to a later stage.

## Project success definition

Success is either:

1. a demonstrably safe, net-profitable autonomous system at measured capacity; or
2. a defensible NO-GO reached before unnecessary production complexity and capital are committed.
