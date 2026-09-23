# TASK-016 — Stage-0 Data Gate: Dual-Source Causal Recorder Evidence

## Status

`COMPLETE`

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


## Implementation status

Implemented:

- strict frozen dual-source runtime config;
- one shared Clock for Hyperliquid and Binance adapters;
- bounded async source multiplexer;
- one RecorderSupervisor / one mixed-source QCR1 segment;
- per-source frame/kind/connection accounting;
- Hyperliquid 8-ACK accounting;
- Binance 1301/1302 ACK accounting;
- clock-domain and manifest-source validation;
- explicit runtime exit codes;
- source-failure propagation and peer cancellation tests;
- fake-server mixed-source capture → QCR1 → TASK-014 normalization → TASK-015 Parquet integration test;
- initial `artifacts/stage_0/data_gate.json` remains BLOCKED until real-mainnet evidence exists.

## Validation status

Network-independent GitHub CI before smoke: **PASS** — run `35930329166`, 306 tests on Python 3.12 and 3.13; Ruff/format/strict mypy PASS.

Real bounded mainnet dual-source smoke: **PASS** — run `35930416414`.


## Real mainnet Data Gate result

Workflow `35930416414` captured both frozen public sources concurrently without credentials.

Measured evidence:

- recorder: **CLEAN_DURABLE / COMPLETE**;
- storage audit: **VALID**;
- raw frames: **24,106**;
- durable bytes: **14,949,703**;
- Hyperliquid raw frames: **464** (456 market + 8 subscription ACK);
- Binance raw frames: **23,642** (23,640 market + ACK IDs 1301/1302);
- Hyperliquid subscription ACKs: **8/8**;
- causal domains: **1**;
- clock-order anomalies: **0**;
- normalized events: **24,345**;
- normalization errors: **0**;
- Hyperliquid normalized events: **705**;
- Binance normalized events: **23,640**;
- Parquet raw-frame count: **24,106**;
- Parquet normalized-event count: **24,345**;
- Parquet bundle SHA-256: `529d4ce5a252ff4d66f50d35133b91b5f8b7a31f6128f9259aade7bd1657990d`.

All 12 real-smoke acceptance criteria passed.

### Gate decision

**Stage-0 Data Gate: PASS.**

This PASS validates the prospective dual-source evidence pipeline only. It does **not** establish alpha, positive expectancy, live execution quality, or production readiness.

The temporary mainnet workflow is removed before merge and the PR must pass one final network-independent CI run.


## Final validation and merge

Final network-independent CI run `35930608146` after removal of the temporary mainnet workflow:

- Ruff: PASS;
- Ruff format: PASS;
- strict mypy: PASS — 61 source files;
- pytest Python 3.12: **306 PASS**;
- pytest Python 3.13: **306 PASS**.

Merged as PR #16 in commit `ed13f9054b290e04151bc1d9de15eddbe4434b5f`.

Stage-0 Data Gate is **PASS**. The project may proceed to Stage 0.5 economic-frontier research, but no alpha/profitability claim exists yet.
