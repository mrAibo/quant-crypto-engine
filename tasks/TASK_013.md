# TASK-013 — Binance USDⓈ-M Public Reference Feed (BTCUSDT / ETHUSDT)

## Status

`PENDING`

## Objective

Add exactly one external public reference venue for Stage 0: Binance USDⓈ-M Futures.

Capture and normalize, for BTCUSDT and ETHUSDT only:

- individual-symbol `bookTicker` as `ReferenceBBO`;
- `aggTrade` as `ReferenceTrade`.

The adapter is reference-data-only. It cannot place orders, use account credentials, or become an execution venue in this task.

## Why Binance USDⓈ-M instead of Coinbase Exchange

The current official Binance USDⓈ-M WebSocket API provides:

- real-time individual-symbol best bid/ask updates;
- aggregate trade updates at approximately 100 ms;
- explicit event and transaction/trade timestamps;
- perpetual instruments that are structurally closer to Hyperliquid perps.

Coinbase Exchange remains a valid public source, but its `ticker` is match-driven/batched and BTC-USD / ETH-USD are spot products. For the initial lead-lag/reference hypothesis, Binance USDⓈ-M is the smaller semantic gap.

This is a single-source decision, not permission to add multiple reference venues.

## Mandatory first action

Before implementation, re-verify current official Binance USDⓈ-M documentation and record:

- current WebSocket base URLs / public paths;
- connection lifetime and ping/pong rules;
- stream subscription method;
- `bookTicker` schema, timestamps, update ID, symbol-type field;
- `aggTrade` schema, event/trade timestamps, aggregate trade ID, price/qty, maker flag;
- stream update cadence;
- any 2026 CM-migration fields or mixed-universe behavior;
- reconnect/resubscribe semantics and whether any replay/backfill is documented;
- public access requirements / whether API credentials are unnecessary.

Unknown guarantees stay UNKNOWN.

## Scope

Reference products:

- `BTCUSDT` USDⓈ-M perpetual → canonical BTC reference instrument;
- `ETHUSDT` USDⓈ-M perpetual → canonical ETH reference instrument.

Streams:

- `btcusdt@bookTicker`
- `ethusdt@bookTicker`
- `btcusdt@aggTrade`
- `ethusdt@aggTrade`

No depth stream, mark-price stream, liquidation stream, REST history, user data, or trading API in TASK-013.

## Architecture

Implement a separate public adapter, parallel to Hyperliquid:

- raw application payload bytes captured before semantic parsing;
- local receive wall/monotonic timestamps assigned at capture boundary;
- bounded reconnect with documented connection-lifetime handling;
- explicit subscription acknowledgments;
- no credentials;
- raw source ID distinct from Hyperliquid;
- normalization from immutable QCR1 raw frames.

Prefer a single combined/public connection for the four streams unless current official behavior or measurement makes a smaller design safer.

## Reference BBO normalization

Map Binance `bookTicker` to v1 `ReferenceBBO`:

- bid/ask price and quantity → exact Decimal;
- sampling mode = `REALTIME_BOOK_TICKER`;
- preserve explicit event timestamp and transaction timestamp only as far as v1 supports without schema distortion;
- use the narrowest justified `ExchangeTimestampSemantics`;
- preserve native update ID when documented;
- validate symbol/type so a COIN-M payload cannot silently enter the USDⓈ-M reference stream.

Do not construct depth or infer executable liquidity beyond BBO.

## Reference trade normalization

Map Binance `aggTrade` to v1 `ReferenceTrade`:

- exact Decimal price and quantity;
- native side representation must be derived only from documented fields;
- normalized aggressor side may be inferred from `m = buyer is market maker` only if the official semantics support the deterministic mapping;
- stable trade ID uses the documented aggregate trade ID plus instrument/source identity as necessary;
- trade timestamp uses the documented trade-time field;
- event timestamp may be retained in raw provenance/evidence if the v1 event contract cannot store both without semantic distortion.

Do not expand the v1 schema unless a concrete required field cannot be represented safely.

## Causal timing

For cross-venue lead-lag research:

- local `recv_wall_ns` on the same recorder host is the primary cross-venue availability axis;
- venue event/trade timestamps are retained for within-venue/event semantics;
- never compare host monotonic clocks across hosts/boots;
- `recv_wall - exchange_time` is apparent lag, not one-way network latency.

## Raw / replay policy

1. Preserve every raw frame occurrence.
2. Never silently deduplicate reconnect deliveries.
3. Deterministic event IDs include immutable raw provenance.
4. Stable native IDs may be used later for explicit duplicate analysis.
5. If Binance does not document replay behavior, keep it UNKNOWN and measure reconnect overlap with a temporary public-only probe.
6. Non-target streams/messages are explicitly NOT_APPLICABLE or control events; never silently disappear.

## Error taxonomy

At minimum distinguish:

- invalid JSON/UTF-8;
- subscription/control message;
- unsupported event type;
- unsupported symbol;
- wrong symbol type / universe;
- invalid event timestamp;
- invalid trade timestamp;
- invalid update/trade ID;
- invalid price/quantity;
- invalid maker flag;
- raw provenance mismatch.

Routine errors must not include full raw payloads.

## Tests

### Unit

- BTC/ETH bookTicker normalization;
- BTC/ETH aggTrade normalization;
- exact decimals;
- BBO event/transaction timestamp decision;
- trade-time semantics;
- aggregate trade identity;
- maker-flag aggressor mapping only if verified;
- symbol/type rejection;
- additive future fields;
- invalid numeric/timestamp/ID/flag;
- deterministic serialization;
- raw SHA provenance;
- non-target/control behavior.

### Integration / fake server

- subscription to exactly four frozen streams;
- ACK correlation;
- multiple stream messages over one connection;
- ping/pong / reconnect behavior;
- forced disconnect/resubscribe;
- bounded backoff;
- no credentials;
- raw bytes → QCR1 → normalized events;
- deterministic replay.

### Live public probe

Use a temporary one-shot GitHub Actions workflow only if needed to verify current network/wire behavior. Remove it before final CI/merge.

Measure, do not assume:

- successful public connection;
- observed schemas/types;
- event rate;
- apparent exchange-to-receive lag;
- reconnect behavior / duplicate overlap;
- mixed UM/CM `st` field behavior after CM migration.

## Evidence artifact

Create `artifacts/stage_0/binance_reference_probe.json` containing:

- frozen reference-source decision;
- official docs/source retrieval;
- endpoint and subscription contract;
- observed live probe, if used;
- normalization mapping;
- timestamp semantics;
- aggressor-side mapping decision;
- reconnect/duplicate policy;
- test coverage;
- CI result;
- remaining UNKNOWNs.

## Definition of Done

1. Binance USDⓈ-M is explicitly frozen as the single Stage-0 reference feed.
2. Current official WebSocket semantics are recorded.
3. BTCUSDT/ETHUSDT bookTicker and aggTrade raw capture works without credentials.
4. ReferenceBBO/ReferenceTrade normalization is deterministic and exact.
5. Cross-venue causal timing policy is preserved.
6. Reconnect/control behavior is tested.
7. QCR1 raw provenance is complete.
8. No execution/account/private Binance code exists.
9. Default CI has no network dependency.
10. Ruff/format/strict mypy/pytest green on Python 3.12 and 3.13.
11. `STATUS.md` advances to TASK-014.

## Do Not Build

- Binance execution;
- Binance account/user streams;
- additional reference venues;
- depth reconstruction;
- liquidation feeds;
- Parquet materialization (TASK-015);
- features/signals/models/backtest.
