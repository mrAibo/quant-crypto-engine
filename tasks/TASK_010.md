# TASK-010 — Hyperliquid L2/BBO Normalization from Raw Capture

## Status

`VALIDATED — MERGE PENDING`

## Objective

Normalize only Hyperliquid `l2Book` and `bbo` raw public messages into the existing v1 `EventEnvelope`, `L2Snapshot`, `BookLevel`, and `BBO` contracts while preserving exact raw provenance and point-in-time receive metadata.

This task starts semantic parsing. It does **not** add features, strategy logic, Parquet, trades, funding, or execution.

## Mandatory first action

Before writing parser behavior, re-verify from current official Hyperliquid sources:

- exact `l2Book` message envelope and fields;
- exact `bbo` message envelope and fields;
- price/size/order-count representations;
- timestamp fields and documented semantics;
- whether book messages are snapshots or deltas;
- any documented depth/aggregation parameters and defaults.

Record the verified facts and source URLs in the evidence contract/provenance notes. Anything not documented remains `UNKNOWN`.

## Inputs

- TASK-005 raw QCR1 frames;
- TASK-004 normalized event contracts;
- TASK-003 instrument registry;
- Hyperliquid raw public payloads for BTC/ETH;
- raw frame metadata and `RawRef`.

## Planned files

- `src/cryptobot/adapters/hyperliquid/normalize.py`
- `src/cryptobot/data/normalize.py` if a small venue-neutral result/error contract is useful;
- `tests/unit/test_hyperliquid_normalize_book.py`
- `tests/integration/test_hyperliquid_raw_replay.py`
- `artifacts/stage_0/hyperliquid_book_normalization.json`

Exact names may vary if a smaller layout is cleaner.

## Binding rules

1. Parse from raw bytes, never from re-serialized intermediate JSON.
2. Use exact `Decimal` parsing; no float conversion for price/size.
3. Preserve:
   - source;
   - recv wall/monotonic timestamps;
   - host/boot;
   - connection ID;
   - ingest sequence;
   - raw segment ID;
   - raw offset;
   - raw payload SHA-256.
4. Deterministic `event_id` must be derived from immutable raw provenance + parse version + normalized event identity.
5. Map native `BTC` and `ETH` through the canonical instrument registry; reject unknown instruments rather than guessing.
6. Exchange timestamp semantics must match verified documentation. If semantics cannot be established, use the existing `UNKNOWN` contract/quality flag rather than inventing meaning.
7. A known-channel malformed payload produces an explicit parse error/result, not silent loss.
8. Unknown future fields may be retained/ignored only under an explicit compatibility policy; required fields remain strict.
9. Normalization must be deterministic across repeated replay.
10. No feed-completeness claim is inferred from normalized output.

## L2 requirements

For each valid `l2Book` message:

- produce one `L2Snapshot`;
- preserve bid/ask ordering exactly as required by the verified protocol;
- parse every included level price and size exactly;
- parse order count only if present/documented;
- set `full_snapshot` from verified source semantics;
- set `depth_limit` and `aggregation` only when justified by actual subscription/message configuration;
- reject non-positive price/size through the existing event contract.

Tests must include:

- empty side if protocol permits it;
- one-sided/invalid book cases;
- multiple levels;
- scientific/decimal string forms if accepted by numeric contract;
- invalid numeric values;
- crossed/locked book handling policy (do not silently "fix" source data);
- unexpected level shape.

## BBO requirements

For each valid `bbo` message:

- produce one normalized `BBO`;
- preserve bid and ask independently;
- represent a missing side with paired null price/size only when the protocol actually permits it;
- use exact decimals;
- never synthesize BBO from `l2Book` inside this parser task.

A later research layer may compare native BBO with top-of-book derived from L2, but TASK-010 must keep source products distinct.

## Parse result/error contract

Prefer a small deterministic result contract containing either:

- normalized event; or
- structured error with:
  - code;
  - channel;
  - raw segment/offset/hash;
  - concise detail.

At minimum distinguish:

- invalid JSON/UTF-8;
- wrong top-level channel;
- missing/invalid data object;
- unsupported coin;
- missing/invalid timestamp;
- invalid level/BBO shape;
- invalid exact numeric value.

Do not put full raw payloads into routine error strings.

## Replay tests

Integration tests must write known raw frames through QCR1 and replay them into the normalizer.

Prove:

- exact raw provenance reaches `EventEnvelope`;
- identical raw input yields byte-for-byte-equivalent serialized normalized output;
- different raw offsets/frames produce distinct deterministic event IDs;
- malformed known-channel frames are counted and surfaced;
- non-target channels are explicitly skipped/not-applicable, not treated as parser failures.

## Evidence artifact

`artifacts/stage_0/hyperliquid_book_normalization.json` records:

- parser/parse version;
- verified field semantics;
- timestamp semantics decision;
- snapshot/delta decision;
- numeric policy;
- error taxonomy;
- fixture/replay coverage;
- CI results;
- any intentionally UNKNOWN protocol semantics.

## Definition of Done

1. Current official L2/BBO schema is re-verified and recorded.
2. Raw `l2Book` → `L2Snapshot` works deterministically.
3. Raw `bbo` → `BBO` works deterministically.
4. Exact decimal policy is preserved.
5. Raw provenance is complete in every normalized envelope.
6. Instrument mapping is strict.
7. Malformed known-channel data is never silently discarded.
8. Replay tests prove determinism and provenance.
9. No trade/funding/reference/feature/strategy code is introduced.
10. Ruff/format/strict mypy/pytest green on Python 3.12 and 3.13.
11. `STATUS.md` advances to TASK-011.

## Do Not Build

- trade normalization (TASK-011);
- mark/oracle/funding normalization (TASK-012);
- external reference feed (TASK-013);
- Parquet/materialized research tables;
- features/signals/models;
- backtest;
- trading/OMS/signing.


## Implementation status

Implemented:

- official/current L2/BBO schema re-verification;
- explicit UNKNOWN timestamp semantic plus measured Unix-millisecond wire unit;
- deterministic raw-frame normalizer;
- exact Decimal price/size parsing;
- strict BTC/ETH canonical instrument mapping;
- raw segment/offset/SHA provenance in normalized envelopes;
- deterministic event IDs;
- explicit additive-field compatibility policy;
- structured parse errors and NOT_APPLICABLE results;
- crossed/unsorted source preservation with SUSPECT quality flag;
- canonical normalized serialization;
- QCR1 replay tests;
- `artifacts/stage_0/hyperliquid_book_normalization.json`.

No trade/funding/reference/Parquet/feature/strategy/execution code is present.

## Validation status

GitHub CI: **PASS** — run `35914447469`; 193 tests passed on Python 3.12 and Python 3.13; Ruff, formatter, and strict mypy passed.


## Validation result

GitHub CI run `35914447469` on head `07342619ed5ad90299e8f1e08054534f1ff71912`:

- Ruff: PASS;
- Ruff format: PASS;
- strict mypy: PASS — 41 source files;
- pytest Python 3.12: **193 PASS**;
- pytest Python 3.13: **193 PASS**.

No default-CI network dependency was introduced.
