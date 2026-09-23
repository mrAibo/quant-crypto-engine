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

## Hyperliquid WebSocket transport

Primary sources:

- <https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/websocket>
- <https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/websocket/timeouts-and-heartbeats>

Re-verified on 2026-09-23 for TASK-007:

- Mainnet endpoint: `wss://api.hyperliquid.xyz/ws`.
- Subscription requests use `{"method":"subscribe","subscription":{...}}`.
- The official connection example acknowledges a subscription on `channel: "subscriptionResponse"` and echoes the subscription in `data`.
- The server may close a connection when it has sent no message to the client for 60 seconds.
- Application heartbeat request: `{"method":"ping"}`.
- Heartbeat response: `{"channel":"pong"}`.
- The official Python SDK currently sends its application-level ping every 50 seconds; this is an SDK implementation choice, not a protocol SLA.

Important limitation: heartbeat proves the connection answers; it does **not** prove a market-data channel is fresh. Channel freshness and gaps remain separately observed recorder evidence.

## Hyperliquid WebSocket message envelopes

Official source pinned to the verified SDK commit:

<https://github.com/hyperliquid-dex/hyperliquid-python-sdk/blob/2fdb18f9517675ea03695a0962bd19eece9c83f0/hyperliquid/utils/types.py>

Re-verified on 2026-09-23:

- `l2Book` message envelope: `channel = "l2Book"`, with book data under `data`.
- `bbo` message envelope: `channel = "bbo"`, with BBO data under `data`.
- `trades` message envelope: `channel = "trades"`, with a list of trades under `data`.
- `activeAssetCtx` message envelope: `channel = "activeAssetCtx"`, with coin/context data under `data`.
- The SDK also models `pong` as a top-level channel.

TASK-007 intentionally does **not** promote the SDK's inner business-field typing into the raw-capture contract. It inspects only the minimum top-level routing/ack fields required for safe operation and persists the received frame bytes unchanged.

## Hyperliquid WebSocket limits

Primary source: <https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/rate-limits-and-user-limits>

Re-verified on 2026-09-23:

- maximum 10 WebSocket connections per IP;
- maximum 30 new WebSocket connections per minute;
- maximum 1000 WebSocket subscriptions;
- maximum 2000 messages sent to Hyperliquid per minute across WebSocket connections;
- maximum 100 simultaneous inflight WebSocket post messages.

TASK-007 uses public subscriptions and no WebSocket post requests. Reconnect behavior must remain comfortably below the documented connection-rate ceiling.

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


## Hyperliquid L2/BBO normalization

Primary official source:

- <https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/websocket/subscriptions>
- <https://hyperliquid.gitbook.io/Hyperliquid-docs/for-developers/api/info-endpoint>

Official SDK reference implementation pinned at:

- <https://github.com/hyperliquid-dex/hyperliquid-python-sdk/tree/2fdb18f9517675ea03695a0962bd19eece9c83f0>

Re-verified on 2026-09-23 before TASK-010 parser implementation:

- `WsBook = { coin: string; levels: [Array<WsLevel>, Array<WsLevel>]; time: number }`.
- The documentation calls `WsBook` an order-book **snapshot** feed; it is not documented as a delta stream.
- `WsLevel = { px: string; sz: string; n: number }`, with `n` documented as number of orders.
- `WsBbo = { coin: string; time: number; bbo: [WsLevel | null, WsLevel | null] }`.
- BBO updates are documented as being sent only when the BBO changes on a block.
- `l2Book` documents optional `nSigFigs` and `mantissa`; the info API documents `nSigFigs` 2/3/4/5 or null/full precision, and `mantissa` 1/2/5 only with `nSigFigs=5`.
- The current project subscription supplies neither aggregation option, so TASK-010 records aggregation/depth metadata as null rather than inferring it.
- The official Python SDK master remains commit `2fdb18f9517675ea03695a0962bd19eece9c83f0` as checked for TASK-010 and routes `l2Book` / `bbo` by the message data coin.

Timestamp caution:

The reviewed official WebSocket schema defines `time: number` for both book and BBO, but does not explicitly label that field's semantic meaning as publication time, block time, or event time. TASK-010 therefore preserves this uncertainty and must not claim `BOOK_PUBLICATION_TIME` solely from the field name. Any unit conversion or semantic promotion requires separate documented or measured evidence.

Measured unit probe:

- One-shot public-only GitHub Actions run: <https://github.com/mrAibo/quant-crypto-engine/actions/runs/35913361944>
- BTC `bbo.data.time = 1790193801866`; local receive wall milliseconds `1790193802192`; difference 326 ms.
- BTC `l2Book.data.time = 1790193801460`; local receive wall milliseconds `1790193802127`; difference 667 ms.
- Both values were JSON integers.

Decision: TASK-010 may convert the observed wire `time` as Unix epoch milliseconds to nanoseconds with 1 ms resolution, while retaining `ExchangeTimestampSemantics.UNKNOWN`. The measurement does not justify relabeling the timestamp as block or publication time.



## Hyperliquid trade normalization

Primary official source:

- <https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/websocket/subscriptions>

Official Python SDK reference:

- <https://github.com/hyperliquid-dex/hyperliquid-python-sdk/tree/2fdb18f9517675ea03695a0962bd19eece9c83f0>

Re-verified on 2026-09-23 before TASK-011 implementation:

- `trades` subscribes by coin and returns `WsTrade[]`.
- Official `WsTrade` fields: `coin`, `side`, `px`, `sz`, `hash`, `time`, `tid`, `users`.
- `px` and `sz` are strings.
- `tid` is documented as a 50-bit hash of `(buyer_oid, seller_oid)`.
- The docs recommend `(block_time, coin, tid)` as a globally unique trade identifier.
- `users` is documented as `[buyer, seller]`.
- The reviewed official trade schema does **not** define `side` as aggressor direction. TASK-011 therefore preserves `native_side` and sets normalized `aggressor_side=UNKNOWN`.
- Public-trade reconnect replay/duplicate guarantees and array sequencing guarantees are not documented in the reviewed source and remain UNKNOWN.
- The official Python SDK master was still commit `2fdb18f9517675ea03695a0962bd19eece9c83f0` at re-verification time.

The v1 normalized `Trade` contract does not contain buyer/seller address fields. TASK-011 validates the documented two-element `users` array but deliberately does not expand the event schema solely to persist public addresses; raw provenance retains the complete original payload.

Measured mainnet trade probe:

- One-shot public-only GitHub Actions run: <https://github.com/mrAibo/quant-crypto-engine/actions/runs/35916459823>
- Each of two independent BTC subscriptions produced an initial batch of 30 trades.
- Session 1 initial batch spanned approximately 10.7 s of source timestamps; session 2 approximately 15.2 s.
- The following observed batches were close to receive time (about 289–390 ms in that sample).
- Session 1 and session 2 each contained 32 sampled native identities; **28 identities overlapped after reconnect**.
- Observed `time` values were JSON integers on Unix epoch millisecond scale.
- Observed `tid` values fit the documented 50-bit bound.
- Observed messages contained exactly the documented eight trade keys and a two-element users list in this sample.

Decision:

TASK-011 preserves **every raw occurrence** and does not silently deduplicate reconnect replay. The normalized stable `trade_id` uses the vendor-recommended tuple material `(time, coin, tid)`; the capture-derived `event_id` additionally includes raw segment/offset/index, so duplicate deliveries remain separately auditable. Exact replay-window size and completeness remain UNKNOWN.

