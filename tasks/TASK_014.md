# TASK-014 — Deterministic Causal Raw-to-Normalized Pipeline

## Status

`VALIDATED — MERGE PENDING`

## Objective

Connect the Stage-0 raw-capture and venue-normalization layers into one deterministic, read-only pipeline.

The pipeline must:

1. consume immutable QCR1 raw frames from the two frozen Stage-0 sources;
2. dispatch each frame to the correct already-validated normalizer;
3. preserve every normalized event, explicit parse error, and explicit non-applicable/control outcome;
4. expose deterministic causal ordering inside one recorder host/boot domain;
5. produce a reproducible normalization report/digest suitable for the Stage-0 Data Gate and later Parquet materialization.

This task does **not** create Parquet files, features, labels, backtests, strategies, deduplication, OMS, or trading.

## Frozen sources

Exactly these source IDs are in scope:

- `hyperliquid-mainnet-public`
- `binance-usdm-reference-public`

Any other source ID is an explicit unsupported-source outcome/error. Do not guess a venue from payload shape.

## Existing parser dispatch

Hyperliquid:

- `l2Book`, `bbo` → TASK-010 `normalize_book_frame`;
- `trades` → TASK-011 `normalize_trade_frame`;
- `activeAssetCtx` → TASK-012 `normalize_context_frame`;
- subscription/control/non-target channels → explicit NOT_APPLICABLE;
- malformed target/raw JSON → explicit normalization error.

Binance reference:

- current combined stream wrapper → TASK-013 `normalize_binance_reference_frame`;
- subscription/control/non-target events → explicit NOT_APPLICABLE;
- malformed target/raw JSON → explicit normalization error.

Do not duplicate venue parsing logic in the pipeline.

## Causal domain and ordering

A causal merge is valid only inside a single recorder clock domain:

`(host_id, boot_id)`.

Rules:

1. Never compare `recv_mono_ns` across different host or boot IDs.
2. Within one causal domain, `recv_mono_ns` is the primary replay-order key because it is monotonic across both venue connections on that recorder process/host boot.
3. `recv_wall_ns` is retained as the UTC availability timestamp used by downstream research and for cross-venue time alignment.
4. If monotonic order and wall-clock order disagree, preserve monotonic replay order and record a clock-order anomaly; do not silently reorder by wall time.
5. Equal receive-monotonic timestamps use a deterministic non-semantic tie-break only:
   `(recv_wall_ns, source_id, raw_segment_id, raw_offset, event_ordinal)`.
6. The tie-break must never be described as evidence that one venue led another.
7. Mixed host/boot domains are not globally sorted. A strict causal merge request over mixed domains must fail explicitly.

This is deliberately conservative. Multi-boot research can later partition by causal domain and use explicit clock/gap evidence; TASK-014 must not invent a total order.

## Frame/event identity and duplicates

- Preserve all raw occurrences.
- Do not deduplicate Hyperliquid reconnect-replayed trades.
- Do not deduplicate Binance reconnect data.
- Parser-provided event IDs remain authoritative.
- If one raw frame yields multiple events, preserve parser order with an explicit `event_ordinal`.
- One normalized event must point to exactly one raw QCR1 occurrence.

## Pipeline result contract

Create a small venue-neutral result layer that can represent, per raw frame:

- `EVENTS`: one or more normalized events;
- `EMPTY`: valid target frame that intentionally yields zero events;
- `NOT_APPLICABLE`: control/non-target message;
- `ERROR`: structured parser/dispatch error.

Each frame result must retain:

- source ID;
- host ID / boot ID;
- receive wall / monotonic timestamps;
- connection ID / ingest sequence;
- raw segment ID / offset / SHA-256;
- dispatch/parser name;
- channel/stream hint when known;
- event count;
- normalized event tuple;
- structured error code/detail without raw-payload dumping.

## Normalized event record

Wrap each emitted domain event with pipeline metadata:

- `causal_domain = (host_id, boot_id)`;
- `recv_mono_ns`;
- `recv_wall_ns`;
- `event_ordinal`;
- deterministic `causal_key`;
- the existing immutable normalized domain event.

Do not mutate the existing event envelope merely to add pipeline ordering metadata.

## Report

A deterministic report must include at minimum:

- total raw frames;
- source counts;
- frame outcome counts;
- normalized event counts by event type;
- parse/dispatch error counts by code;
- NOT_APPLICABLE/control counts;
- causal-domain count;
- clock-order anomaly count;
- duplicate stable trade-ID observations may be counted, but must not be removed;
- first/last receive wall and monotonic timestamps per causal domain;
- deterministic SHA-256 digest of canonical normalized records.

The report is evidence, not a claim of feed completeness.

## Planned files

- `src/cryptobot/data/normalization_pipeline.py`
- `tests/unit/test_normalization_pipeline.py`
- `tests/integration/test_causal_normalization_replay.py`
- `artifacts/stage_0/causal_normalization_pipeline.json`

Exact file naming may vary only if a smaller layout is clearer.

## Required tests

### Unit

- Hyperliquid channel dispatch to book/trade/context parser;
- Binance reference dispatch;
- control/non-target → NOT_APPLICABLE;
- unsupported source → explicit ERROR;
- one raw frame → multiple events preserves event ordinal;
- zero-event valid trade batch → EMPTY;
- parser error is surfaced without raw payload in detail;
- event IDs are not rewritten;
- stable trade duplicates are preserved;
- deterministic causal key;
- same-domain monotonic ordering;
- deterministic tie-break for equal monotonic timestamps;
- wall-clock regression produces anomaly but does not reorder monotonic sequence;
- mixed host IDs rejected by strict merge;
- mixed boot IDs rejected by strict merge;
- deterministic report serialization/digest.

### Integration

Write multiple Hyperliquid and Binance frames through QCR1, replay them through the pipeline, and prove:

- both venue sources appear in one same-host/boot causal stream;
- raw provenance survives end to end;
- event ordering is identical across repeated replay;
- multi-event trade/context frames stay adjacent in parser order;
- explicit control frames and malformed frames remain visible in the report;
- reconnect duplicate native trade identity is not silently removed;
- repeated replay produces byte-identical canonical normalized-record serialization and identical report digest.

## Evidence artifact

`artifacts/stage_0/causal_normalization_pipeline.json` records:

- pipeline version;
- frozen source IDs;
- parser dispatch table;
- causal-domain definition;
- ordering/tie-break semantics;
- wall-vs-monotonic policy;
- duplicate policy;
- outcome/error taxonomy;
- report schema/digest policy;
- test/replay coverage;
- CI result;
- intentionally unsupported mixed-domain merge behavior.

## Definition of Done

1. Both frozen Stage-0 sources dispatch through one deterministic pipeline.
2. Existing parser semantics are reused rather than copied.
3. No raw occurrence, parse failure, or control outcome is silently dropped.
4. Same host/boot causal replay is deterministic.
5. Mixed causal domains fail explicitly in strict merge mode.
6. Wall-clock regressions are visible as anomalies.
7. Duplicate stable trade identities remain auditable and are not removed.
8. QCR1 integration replay proves deterministic normalized records and report digest.
9. No Parquet/features/labels/backtest/strategy/execution code is introduced.
10. Ruff/format/strict mypy/pytest green on Python 3.12 and 3.13.
11. `STATUS.md` advances to TASK-015.

## Do Not Build

- Parquet/materialized research tables (TASK-015);
- feature engineering;
- labels/forward returns;
- backtest/simulator;
- deduplication service;
- gap backfill;
- live execution/OMS/signing;
- AI/Jev/GPT logic.


## Implementation status

Implemented:

- venue-neutral `FrameResult`, `PipelineError`, `CausalRecord`, and `PipelineReport` contracts;
- strict frozen-source dispatch with no payload-based venue guessing;
- reuse of TASK-010/011/012/013 normalizers and serializers;
- explicit EVENTS / EMPTY / NOT_APPLICABLE / ERROR outcomes;
- same-host/boot causal merge using receive monotonic time;
- deterministic non-semantic tie-break for equal monotonic timestamps;
- explicit rejection of mixed host/boot strict causal merge;
- wall-clock regression anomaly counting without reordering;
- parser event IDs and all raw occurrences preserved;
- duplicate stable trade identities counted but never removed;
- deterministic normalized-record serialization and SHA-256 digest;
- deterministic report serialization;
- unit coverage for dispatch, ordering, errors, duplicates, domains, and digest;
- two-venue QCR1 integration replay;
- `artifacts/stage_0/causal_normalization_pipeline.json`.

No Parquet/features/labels/backtest/deduplication/execution code is present.

## Validation status

GitHub CI: **PASS** — run `35924328402`; 288 tests passed on Python 3.12 and Python 3.13; Ruff, formatter, and strict mypy passed.


## Validation result

GitHub CI run `35924328402` on head `16e524d08a37db9e08f8e523c8365b094719a55c`:

- Ruff: PASS;
- Ruff format: PASS;
- strict mypy: PASS — 55 source files;
- pytest Python 3.12: **288 PASS**;
- pytest Python 3.13: **288 PASS**.

Default CI remains network-independent.
