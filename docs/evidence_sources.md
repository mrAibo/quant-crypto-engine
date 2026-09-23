# Evidence Sources

Checked on **2026-09-23**. This file records the human-readable provenance behind `config/evidence.yaml`.

The machine-readable contract deliberately uses **JSON-compatible YAML** (JSON is a subset of YAML 1.2) so Stage 0 can validate evidence using only the Python standard library. This avoids adding a YAML parser before the data stack actually needs one.

`source_hash` is currently `null` for documented facts because the project has not yet implemented source-snapshot retention. The validator reports those missing hashes as an audit warning. A URL plus retrieval date is sufficient for the initial `DOCUMENTED` status, but all economically or safety-critical facts must be re-verified at their listed trigger before use.

## Hyperliquid fees

Primary source: <https://hyperliquid.gitbook.io/hyperliquid-docs/trading/fees>

Verified on 2026-09-23:

- Base perpetual tier: **0.045% taker / 0.015% maker**.
- Fee tier is driven by rolling 14-day weighted volume and can also be affected by staking/referrals and product-specific rules.
- First maker-rebate tier begins above **0.5% of weighted maker volume**, with the documented maker fee becoming negative.

Important limitation: these are protocol schedule facts, **not the project's actual account fee rates**. Before economic work, the project must query account-specific fee state and record it as observed evidence.

## Hyperliquid funding

Primary source: <https://hyperliquid.gitbook.io/hyperliquid-docs/trading/funding>

Verified on 2026-09-23:

- Funding is paid every hour.
- The 8-hour funding-rate calculation is paid at one eighth of the computed rate each hour.
- Funding payment is documented as `position_size * oracle_price * funding_rate`.
- Oracle price, rather than mark price, is used for the notional conversion in the funding payment formula.

Important limitation: predicted and realized funding must remain distinct in point-in-time research.

## Hyperliquid WebSocket

Primary source: <https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/websocket/subscriptions>

Verified on 2026-09-23:

- Public subscriptions include `l2Book`, `trades`, `bbo`, and `activeAssetCtx`.
- `WsBook` is documented as a **snapshot feed**, pushed on a block when at least about 0.5 seconds have elapsed since the previous push.
- `WsBbo` is documented as updating only if the BBO changes on a block.
- `WsTrade.tid` alone is not globally unique; the docs describe `(block_time, coin, tid)` as the globally unique trade identity.

Important limitation: documentation is not an observed latency/cadence SLA. The recorder must measure actual cadence, staleness, reconnects and gaps rather than hard-coding review-model claims such as “slow book every 5 seconds.”

## Hyperliquid orders

Primary source: <https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/exchange-endpoint>

Verified on 2026-09-23:

- `cloid` is an optional 128-bit hexadecimal client order identifier.
- `ALO` is add-liquidity-only/post-only.
- `IOC` cancels the unfilled remainder instead of resting.
- `GTC` has no special cancellation behavior and can rest until filled/canceled.
- `expiresAfter` exists for applicable signed actions; stale actions consume additional rate-limit budget according to the docs.

Important limitation: `cloid` is a correlation facility, not evidence of exactly-once execution. Ambiguous write handling remains a later OMS/reconciliation problem.

## Hyperliquid scheduleCancel

Primary source: <https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/exchange-endpoint>

Verified on 2026-09-23:

- Scheduled cancel time must be at least five seconds in the future.
- When triggered, all open orders are canceled.
- The documented maximum is 10 triggers per day, reset at 00:00 UTC.

Important limitation: canceling open orders is not the same as flattening positions. This mechanism is supplemental safety only.

## Hyperliquid API wallets

Primary source: <https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/nonces-and-api-wallets>

Verified on 2026-09-23:

- API wallets are also called agent wallets.
- They sign on behalf of a master account or sub-account.
- Account data queries must use the actual account/sub-account address, not the agent address.
- Nonces are tracked per signer.
- The docs recommend separate API wallets for separate trading processes/subaccounts to avoid nonce collisions.
- Reusing a deregistered API-wallet address is discouraged because nonce state may be pruned and previously signed actions may become replayable.

Important limitation: the project has **not** yet established the exact transfer/withdrawal capability boundaries of the runtime credential arrangement it will use. That remains `UNKNOWN` until a dedicated verification step.

## Hyperliquid historical data

Primary source: <https://hyperliquid.gitbook.io/hyperliquid-docs/historical-data>

Verified on 2026-09-23:

- Archive uploads are described as occurring approximately once a month.
- Timely updates are not guaranteed and data may be missing.
- S3 asset data includes L2 book snapshots and asset contexts; not every live data set is supplied there.
- The official page explicitly suggests recording additional historical data sets via the API when needed.

Important limitation: archive availability never removes the need for an explicit data-quality manifest or for native prospective recording where receive-time evidence matters.

## Unknowns intentionally preserved

The following are **not** silently inferred from documentation:

- project-account effective fee rates;
- mainnet submit-to-ACK latency distribution;
- mainnet IOC partial-fill/rejection distribution;
- realized slippage and own-order impact;
- runtime API-wallet withdrawal/transfer capability boundaries;
- external reference venue selection and timestamp/completeness semantics;
- completeness of any historical period actually imported for research.

These remain `UNKNOWN` in `config/evidence.yaml` until their verification trigger is satisfied.
