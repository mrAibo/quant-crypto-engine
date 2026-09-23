# TASK-016 — Stage-0 Data Gate: Dual-Source Causal Recorder Evidence

## Status

`PENDING`

## Gate finding that created this task

The Stage-0 Data Gate cannot yet honestly PASS.

Hyperliquid has a runnable public recorder and live smoke evidence. Binance USDⓈ-M has a validated public adapter and normalization evidence. However, the current runnable recorder is Hyperliquid-only, so the project does not yet have prospective evidence that both frozen Stage-0 sources can be captured concurrently under the same recorder `(host_id, boot_id)` clock domain and then replayed end to end.

TASK-016 closes exactly that evidence gap.

## Objective

Create a reusable public-only dual-source runtime that concurrently captures:

- Hyperliquid BTC/ETH `l2Book`, `bbo`, `trades`, `activeAssetCtx`;
- Binance USDⓈ-M BTCUSDT/ETHUSDT `bookTicker` and `aggTrade`;

using one shared `SystemClock(host_id, boot_id)`, one bounded durable QCR1 recorder, and one sealed manifest.

Then run a bounded real-mainnet smoke and prove:

`LIVE SOURCES → QCR1 → storage audit → TASK-014 normalize → TASK-015 Parquet/readback`.

This is a Data Gate evidence task. It does **not** test profitability, signal quality, or feed completeness over long horizons.

## Architecture

Use existing validated components:

- TASK-007 Hyperliquid adapter;
- TASK-013 Binance reference adapter;
- TASK-008 RecorderSupervisor;
- TASK-014 normalization pipeline;
- TASK-015 materializer.

Do not rewrite venue protocol logic.

Both adapters receive the **same Clock instance**.

Merge their async capture streams through one bounded runtime multiplexer. The multiplexer:

- does not reorder by exchange timestamp or wall time;
- forwards frames as they arrive from adapter tasks;
- preserves adapter-assigned receive wall/monotonic timestamps and source IDs;
- propagates unexpected source failures;
- cancels peer source tasks on shutdown/failure;
- never silently drops a frame.

TASK-014 remains responsible for deterministic replay ordering by receive monotonic time.

## Runtime configuration

Add an explicit dual-source smoke config with:

- Hyperliquid endpoint/source/coins/channels;
- Binance public + market endpoints/source;
- common recorder queue/fsync/shutdown settings;
- Hyperliquid reconnect/heartbeat/transport settings;
- Binance reconnect/transport settings;
- storage root + manifest path;
- bounded run duration.

No credentials, account endpoints, orders, or private streams.

## Runtime evidence summary

The dual-source summary must include at minimum:

- host_id / boot_id / run_id;
- recorder durability counters;
- storage audit result;
- frame count by source;
- market/control/malformed/unknown count by source where available;
- Hyperliquid subscription ACK count vs expected 8;
- Binance subscription ACK IDs observed vs expected `1301,1302`;
- connection IDs;
- manifest source IDs;
- whether both required source IDs were observed;
- whether every captured frame shares the configured host/boot clock domain;
- final exit code/reason.

## Real smoke acceptance

A bounded mainnet smoke passes only if:

1. recorder ends CLEAN_DURABLE;
2. storage audit is VALID;
3. sealed manifest contains both frozen source IDs;
4. all captured raw frames share one host/boot domain;
5. both sources produced raw frames;
6. Hyperliquid 8/8 subscription ACKs observed;
7. Binance ACK IDs 1301 and 1302 observed;
8. at least one normalized Hyperliquid market event and one normalized Binance reference event exist;
9. normalization report has one causal domain;
10. no normalization ERROR frames in the captured smoke;
11. Parquet materialization/readback succeeds from that real QCR1 segment;
12. materialized frame count equals raw frame count and normalized event count equals TASK-014 report count.

A short smoke does not prove long-run feed completeness, uptime, latency distribution, or economic usefulness.

## Stage-0 Data Gate decision

Create `artifacts/stage_0/data_gate.json` with one of:

- `PASS`
- `FAIL`
- `INCONCLUSIVE`
- `BLOCKED`

PASS requires both:

- all engineering/evidence prerequisites from TASK-001..015 remain validated;
- the real dual-source smoke acceptance above passes.

The artifact must explicitly list residual UNKNOWNs and state that Data Gate PASS permits Stage 0.5 feasibility/frontier work only; it does not establish alpha.

## Planned files

- `src/cryptobot/runtime/dual_source_recorder.py`
- `config/runtime/dual-source-smoke.json`
- `tests/unit/test_dual_source_recorder.py`
- `tests/integration/test_dual_source_recorder_runtime.py`
- `artifacts/stage_0/data_gate.json`
- optional CLI command for bounded public dual-source recorder/audit if it stays read-only.

A temporary GitHub Actions mainnet smoke workflow is allowed for evidence collection, but it must be removed before merge so normal CI remains network-independent.

## Required tests

- strict config validation;
- exactly frozen source/channel/symbol sets;
- shared clock identity across both adapters;
- bounded async multiplexing with no silent drop;
- peer cancellation on failure/stop;
- source failure propagation;
- one RecorderSupervisor persists mixed-source frames;
- manifest records both source IDs;
- storage audit remains valid;
- fake Hyperliquid + fake Binance routes end-to-end;
- normalization pipeline sees one causal domain;
- Parquet materialization succeeds from the captured mixed-source QCR1 segment;
- summary ACK/source/durability accounting;
- graceful duration stop.

## Definition of Done

1. Reusable dual-source public recorder exists.
2. Both adapters share one clock domain.
3. Fake-server integration proves mixed-source durable capture.
4. Real bounded mainnet smoke satisfies the acceptance criteria.
5. Real smoke raw data normalizes and materializes successfully.
6. `data_gate.json` records a justified Stage-0 Data Gate decision.
7. Temporary network workflow removed.
8. Ruff/format/strict mypy/pytest green on Python 3.12 and 3.13.
9. On PASS, `STATUS.md` advances to Stage 0.5 profitability/economic-frontier design.

## Do Not Build

- signals/features/labels;
- backtest/simulator;
- execution/OMS/signing;
- account/private data capture;
- maker logic;
- Jev/GPT/LLM runtime;
- profitability claims.
