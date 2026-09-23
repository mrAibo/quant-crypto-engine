# TASK-013 — Binance USDⓈ-M Public Reference Feed (BTCUSDT / ETHUSDT)

## Status

`COMPLETE`

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

Current 2026 routing makes one connection incorrect for this stream set. Use exactly two public, unauthenticated connections:

- `wss://fstream.binance.com/public/stream` for `btcusdt@bookTicker` and `ethusdt@bookTicker`;
- `wss://fstream.binance.com/market/stream` for `btcusdt@aggTrade` and `ethusdt@aggTrade`.

The split is a protocol requirement, not an optimization. JSON `SUBSCRIBE` request IDs must be unsigned integers as documented.

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


## Implementation status

Implemented:

- Binance USD-M frozen as the single Stage-0 external reference feed;
- BTCUSDT/ETHUSDT REFERENCE perpetual instruments;
- official 2026 routed-endpoint / connection / bookTicker / aggTrade evidence;
- two public-only WebSocket routes: /public for bookTicker and /market for aggTrade;
- bounded reconnect and deterministic raw capture metadata;
- subscription ACK/control classification;
- deterministic ReferenceBBO and ReferenceTrade normalization;
- exact Decimal values;
- explicit st=1 USD-M boundary;
- documented maker-flag → aggressor-side mapping;
- QCR1 replay and fake-server integration tests;
- successful mainnet public-only live probe run `35919551313`;
- `artifacts/stage_0/binance_reference_probe.json`.

No Binance private/account/execution/depth reconstruction code is present.

## Validation status

GitHub CI: **PASS** — run `35923067510`; 271 tests passed on Python 3.12 and Python 3.13; Ruff, formatter, and strict mypy passed.


## 2026 routing resolution

Current official Binance USDⓈ-M documentation was re-verified before implementation:

- `bookTicker` is mapped to the high-frequency `/public` route;
- `aggTrade` is mapped to the regular `/market` route;
- legacy unrouted connections no longer carry Market-route streams after the 2026 migration;
- Binance recommends splitting connections by traffic class;
- JSON stream subscription `id` is documented as an unsigned integer.

TASK-013 therefore uses two unauthenticated connections and deterministic integer IDs `1301` (PUBLIC) and `1302` (MARKET).


## Final transport verification

After aligning JSON `SUBSCRIBE` IDs with the documented unsigned-integer contract, the final adapter was exercised directly against Binance mainnet in workflow `35922113843`:

- ACK IDs: `1301` / `1302`;
- both `/public` and `/market` routes connected;
- all four frozen BTCUSDT/ETHUSDT streams observed;
- every sampled `st` value was `1`;
- 313 market-data frames observed in approximately 7.3 seconds;
- no credentials used.

The temporary network workflow was removed afterward. Default project CI remains network-independent.


## Validation result

GitHub CI run `35923067510` on head `702e9e9294e20b5d30d9589c67d0049adfcca61a`:

- Ruff: PASS;
- Ruff format: PASS — 70 files;
- strict mypy: PASS — 52 source files;
- pytest Python 3.12: **271 PASS**;
- pytest Python 3.13: **271 PASS**.

Default CI is network-independent. Final live adapter verification was separately completed in public-only workflow `35922113843` and its temporary workflow was removed before this CI run.


## Merge provenance

Merged as PR #13 in commit `d850f2d54d02f47b05bfeab0d881ff76ab3275d7`.

Final PR-head validation run `35923167765` on head `ae9250e12fd5fc82fa6aa04269fe52c72c774f43`:

- Ruff: PASS;
- Ruff format: PASS;
- strict mypy: PASS;
- pytest Python 3.12: **271 PASS**;
- pytest Python 3.13: **271 PASS**.

Public-only final adapter probe: `35922113843`.
