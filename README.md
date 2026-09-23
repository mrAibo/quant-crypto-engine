# quant-crypto-engine

Evidence-driven research and engineering project for an autonomous cryptocurrency trading system.

## Current scope

- Python 3.12+
- Hyperliquid as the current execution candidate
- BTC as the primary research market
- ETH as a replication/generalization market
- one external reference feed
- deterministic quant/risk core
- taker-only first economic validation
- no GPT runtime in v1
- Jev only as an optional, separately gated veto experiment
- autonomous 24/7 operation is a later production goal, not the first deliverable

## Development principle

The first product is a trustworthy evidence system, not a trading bot.

Work proceeds stage by stage. Each work package must include code, tests, and an explicit completion artifact. Production execution components are not built until the first economic GO/NO-GO gate passes.

Start with [`STATUS.md`](STATUS.md) for the current state, completed work, test status, open decisions, and exact next task.
