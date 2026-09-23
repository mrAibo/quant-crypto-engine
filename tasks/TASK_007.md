# TASK-007 — Hyperliquid Raw Public WebSocket Adapter

## Status

`COMPLETE`

Merged as PR #7 in commit `2182268783293bc01b2d1ac5608e3f01de9877f1`.

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
- verified WebSocket evidence/provenance
- pinned `websockets==17.0.1`

## Decisions

- Use mature BSD-3-Clause `websockets`; do not implement RFC6455.
- Receive application frames with `recv(decode=False)`.
- Preserve payload bytes unchanged.
- Parse only top-level channel/subscription acknowledgment routing.
- Preserve unknown/malformed frames instead of silently dropping them.
- Use Hyperliquid application heartbeat, distinct from data-channel freshness.
- Reconnect policy has a two-second minimum to remain within documented new-connection rate constraints.
- No normalization, strategy, order execution, or trading logic was introduced.

## Validation

Final GitHub Actions run `35904060906`:

- uv lock/sync Python 3.12: PASS
- Ruff lint: PASS
- Ruff format: PASS
- strict mypy: PASS
- pytest Python 3.12: PASS — 140 tests
- uv lock Python 3.13: PASS
- pytest Python 3.13: PASS — 140 tests

## Next task

`TASK-008 — Recorder Supervisor and Raw-Writer Integration`.
