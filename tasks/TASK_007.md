# TASK-007 — Hyperliquid Raw Public WebSocket Adapter

## Status

`VALIDATED — MERGE PENDING`

## Objective

Implement the first live Hyperliquid public WebSocket adapter while preserving source application-message bytes unchanged and inspecting only the minimum protocol envelope required for subscription accounting, channel classification, heartbeat handling, and reconnect behavior.

## Delivered

- `src/cryptobot/adapters/__init__.py`
- `src/cryptobot/adapters/hyperliquid/__init__.py`
- `src/cryptobot/adapters/hyperliquid/public.py`
- `tests/unit/test_hyperliquid_public.py`
- `tests/integration/test_hyperliquid_public_integration.py`
- `artifacts/stage_0/hl_capture_probe.json`
- `docs/THIRD_PARTY_REUSE.md`
- Hyperliquid WebSocket facts in `config/evidence.yaml`
- WebSocket provenance in `docs/evidence_sources.md`
- pinned `websockets==17.0.1` in `pyproject.toml` / `uv.lock`

## Verified protocol baseline

Re-verified from official Hyperliquid documentation and the official Python SDK before implementation:

- mainnet endpoint: `wss://api.hyperliquid.xyz/ws`;
- subscription request uses `method=subscribe` plus a subscription object;
- subscription acknowledgments are delivered on `subscriptionResponse`;
- public channels used here: `l2Book`, `bbo`, `trades`, `activeAssetCtx`;
- application heartbeat request `{"method":"ping"}` and response channel `pong`;
- documented server idle rule: 60 seconds;
- documented IP WebSocket limits include 10 connections and 30 new connections/minute.

The adapter does not treat documentation as evidence of runtime availability, latency, cadence, or completeness. Those remain observed evidence for later recorder tasks.

## Implementation decisions

- Use mature BSD-3-Clause `websockets==17.0.1`; do not implement RFC6455 ourselves.
- Receive application messages with `recv(decode=False)` so payload is captured as bytes.
- Do not normalize inner market/business fields in TASK-007.
- Parse only top-level JSON needed to classify:
  - subscription acknowledgment;
  - supported market channel;
  - heartbeat pong;
  - unknown;
  - malformed.
- Unknown/malformed payloads are preserved rather than silently dropped.
- Every connection receives a distinct connection ID.
- Ingest sequence is monotonic within one connection and resets on reconnect.
- Application heartbeat is distinct from market-channel freshness.
- Reconnect delay has a hard two-second minimum so the adapter cannot exceed the documented 30-new-connections/minute limit by configuration.
- Built-in protocol pings are disabled; Hyperliquid's documented application heartbeat is used.
- Third-party implementation influence is recorded in `docs/THIRD_PARTY_REUSE.md`.

## Validation

GitHub Actions run `35903825794`:

- `uv lock --check` Python 3.12: **PASS**
- `uv sync --locked` Python 3.12: **PASS**
- Ruff lint: **PASS**
- Ruff format: **PASS**
- strict mypy: **PASS** — 27 source files
- pytest Python 3.12: **PASS — 140 tests**
- `uv lock --check` Python 3.13: **PASS**
- pytest Python 3.13: **PASS — 140 tests**

Fake-server coverage includes:

- deterministic subscription requests;
- subscription acknowledgment tracking;
- exact application payload-byte preservation;
- application ping/pong;
- reconnect and resubscribe;
- connection-ID renewal;
- per-connection ingest-sequence reset;
- malformed/binary payload preservation;
- channel classification.

## Definition of Done

1. Protocol facts re-verified before coding. **PASS**
2. Public subscription adapter exists. **PASS**
3. Raw application payload bytes preserved. **PASS**
4. ACK/channel/heartbeat routing is minimal and explicit. **PASS**
5. Reconnect behavior is bounded and tested. **PASS**
6. No normalization/trading/execution code introduced. **PASS**
7. Dependency lock is reproducible. **PASS**
8. Python 3.12/3.13 tests green. **PASS**
9. Ruff/format/strict-mypy/full pytest green. **PASS**
10. TASK-008 defined before merge. **PASS**

## Next task

`TASK-008 — Recorder Supervisor and Raw-Writer Integration`.

## Do Not Build

- normalized event parsing;
- Parquet materialization;
- reference venue;
- trading features/models;
- order execution/OMS.
