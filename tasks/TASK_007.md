# TASK-007 — Hyperliquid Raw Public WebSocket Adapter

## Status

`PENDING`

## Objective

Implement the first live public-data adapter: connect to the current official Hyperliquid public WebSocket, subscribe only to the Stage 0 channels already approved by configuration, timestamp frames at the receive boundary, and hand **unchanged raw payload bytes** plus capture metadata to the TASK-005 raw-log interface.

This task is raw capture only. It must not normalize market events or compute features.

## Mandatory pre-implementation verification

Before writing or changing network behavior:

1. verify the current mainnet WebSocket endpoint from official Hyperliquid documentation;
2. verify current subscription request/ack shapes;
3. verify message envelopes for:
   - `l2Book`
   - `bbo`
   - `trades`
   - `activeAssetCtx`
4. verify ping/pong/keepalive guidance and connection/subscription rate limits if officially documented;
5. update `config/evidence.yaml` and `docs/evidence_sources.md` when current facts differ or new verified facts are needed;
6. preserve anything not documented/observed as UNKNOWN.

Do not use review-model claims as protocol constants.

## Planned files

- `src/cryptobot/adapters/__init__.py`
- `src/cryptobot/adapters/hyperliquid/__init__.py`
- `src/cryptobot/adapters/hyperliquid/public.py`
- `tests/fixtures/hyperliquid/...`
- `tests/unit/test_hyperliquid_public.py`
- `tests/integration/test_hyperliquid_public.py`
- `artifacts/stage_0/hl_capture_probe.json`

If a new runtime dependency is required (for example a WebSocket client library), update `pyproject.toml` and `uv.lock` explicitly and justify it in the task report.

## Adapter contract

Provide a narrow async interface that yields raw capture units containing:

- exact received frame bytes;
- `RawFrameMetadata` compatible capture metadata;
- source ID;
- connection ID;
- local ingest sequence;
- wall/monotonic receive timestamps captured immediately at receive boundary;
- optional channel hint only when it is observable without lossy business parsing.

The adapter must not return normalized `MarketEvent` objects in TASK-007.

## Subscription behavior

- Read enabled source/instrument/channel selection from the strict recorder configuration.
- Reject unsupported channel/instrument combinations before connecting.
- Subscribe deterministically.
- Confirm/document subscription acknowledgments using observed fixtures.
- Record connection lifecycle/status as capture/control information without pretending it is exchange market data.
- New connection = new `connection_id`.
- Local `ingest_seq` must be monotonic within the adapter process/source contract.

## Reconnect behavior

Implement bounded reconnect behavior only after current API limits/semantics are verified.

Requirements:

- exponential or otherwise explicit bounded retry schedule;
- jitter only if configured/justified;
- cancellation-aware shutdown;
- each disconnect/reconnect reason observable;
- no silent message loss claim;
- after reconnect, treat subsequent frames as a new availability interval;
- never synthesize exchange sequence numbers.

If configuration thresholds are still `null`, derive a conservative documented Stage-0 default only if the evidence contract is updated with its basis; otherwise expose the value as a required deployment choice rather than inventing it.

## Backpressure

Network reading must feed a bounded internal handoff.

Rules:

- no silent dropping of raw frames;
- if downstream cannot keep up, the adapter must surface overload/backpressure and allow the connection to fail/reconnect rather than claiming complete capture;
- exact queue sizing is deferred until observed data rate if current config remains null;
- tests must exercise stalled consumer behavior.

## Protocol robustness

- Unknown channel/message shapes are retained as raw bytes and surfaced diagnostically; do not crash simply because business parsing is unknown.
- Invalid transport/text encoding must be classified explicitly.
- Raw payload bytes must remain exactly those received from the WebSocket library representation chosen by the adapter; document any unavoidable text→UTF-8 conversion at library boundary.
- No business-field deduplication here.
- No L2 book reconstruction here.
- No trade-side interpretation here.

## Tests

### Unit with fixtures/fake transport

- deterministic subscription requests;
- expected subscription ACK handling;
- all four configured public channel message envelopes accepted as raw;
- unknown channel retained;
- malformed JSON retained/raw plus diagnostic classification;
- reconnect creates a new connection ID;
- receive timestamps/ingest sequence generated correctly;
- graceful shutdown;
- bounded backoff;
- backpressure/stalled consumer;
- no normalization dependency.

### Opt-in integration

A network-marked integration/smoke test may connect to the public endpoint, but default CI must not require external network access.

It should:

- subscribe to BTC/ETH configured channels;
- collect a small bounded sample;
- record observed message/channel shapes;
- never place orders and never require credentials.

Captured public fixtures used in ordinary tests must be small, redacted where appropriate, and committed only if redistribution is acceptable.

## Completion artifact

`artifacts/stage_0/hl_capture_probe.json` records:

- verified endpoint/document retrieval time;
- configured subscriptions;
- dependency choice;
- fixture/schema observations;
- reconnect/backpressure behavior;
- network smoke-test status if performed;
- CI result;
- remaining UNKNOWNs.

## Definition of Done

1. Public adapter connects/subscribes according to current verified docs.
2. Exact raw frames can be handed to TASK-005 storage with capture metadata.
3. No raw frame is silently dropped by adapter logic.
4. Reconnect/backpressure behavior is explicit/tested.
5. Default CI has no external-network dependency.
6. Python 3.12/3.13 tests green.
7. Ruff/format/strict mypy/full pytest green.
8. `STATUS.md` advances to TASK-008.

## Do Not Build

- event normalization (TASK-010+)
- trade deduplication/business parsing
- reference-venue adapter
- Parquet materialization
- strategy/features/trading
