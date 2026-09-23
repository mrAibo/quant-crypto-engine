# Project Gates

Gate outcomes are `PASS`, `FAIL`, `INCONCLUSIVE`, or `BLOCKED`. Missing evidence is never a pass.

## Data Gate — Stage 0

Pass only when captured data is causally usable, auditable, recoverable, and source/timestamp semantics are explicit.

## Frontier Gate — Stage 0.5

Pass only when at least one supported horizon/size region is economically plausible under conservative taker costs and evidence can be collected within the approved budget.

This gate permits predictability testing. It does **not** prove edge.

## Gate 1 — First Economic GO/NO-GO

Pass only when a frozen BTC policy survives untouched chronological confirmation with:

- positive business-net expectancy above the predeclared hurdle;
- dependence-aware uncertainty/power sufficient for the claim;
- realistic fees, funding, executable-price costs, invalid intervals, and latency assumptions;
- no unsupported precision/depth requirement;
- complete trial accounting;
- an acceptable tail-loss/risk profile.

ETH replication is reported separately. ETH failure blocks ETH deployment/generalization, not necessarily a separately valid BTC-only result.

**Production signing/OMS/watchdog deployment is forbidden before Gate 1 passes.**

## Replay / Forward Gate

Requires replay parity and prospective shadow/paper behavior consistent with the frozen strategy and cost model.

## Safety Gate

Requires durable order handling, reconciliation, recovery, independent safety intervention, and chaos/testnet evidence.

## Micro-live Gate

Requires human approval tied to frozen strategy/config/risk hashes and a risk-derived size small enough for bounded actual-money validation.

## Production Gate

Requires positive actual-money expectancy at micro size, acceptable real execution costs, and operational readiness for unattended trading.

## Scale Gate

Capital increases require human approval and evidence that the larger size remains within measured capacity, exit-liquidity, and risk limits. Automatic scale-down is allowed; automatic scale-up is not.
