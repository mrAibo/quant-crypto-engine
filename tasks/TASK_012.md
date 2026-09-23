# TASK-012 — Hyperliquid activeAssetCtx Funding / Mark / Oracle Normalization

## Status

`PENDING`

## Objective

Normalize Hyperliquid public `activeAssetCtx` raw frames for configured BTC/ETH perpetuals into the existing v1:

- `FundingRateObservation`
- `MarkPrice`
- `OraclePrice`

contracts while preserving exact raw provenance and explicitly representing the absence of a native exchange timestamp when the wire schema does not provide one.

This task remains Stage 0 semantic parsing only. It does **not** add funding-payment account events, reference venues, Parquet, features, labels, backtests, OMS, or trading.

## Mandatory first action

Before parser implementation, re-verify current official Hyperliquid sources for:

- exact `activeAssetCtx` WebSocket envelope;
- exact `PerpsAssetCtx` fields and wire types;
- whether `activeAssetCtx` itself contains any exchange timestamp;
- meaning and units of `funding`;
- funding payment cadence and formula;
- meaning of `markPx` and `oraclePx`;
- nullable/optional fields;
- any documented distinction between current/predicted/realized funding in this feed.

Record verified facts and explicit UNKNOWNs before writing parser behavior.

## Inputs

- TASK-005 QCR1 raw frames;
- TASK-004 v1 normalized event contracts;
- TASK-003 canonical instrument registry;
- TASK-010/011 normalization conventions;
- current official Hyperliquid WebSocket/funding documentation.

## Planned files

- `src/cryptobot/adapters/hyperliquid/context.py`
- `tests/unit/test_hyperliquid_normalize_context.py`
- `tests/integration/test_hyperliquid_context_raw_replay.py`
- `artifacts/stage_0/hyperliquid_context_normalization.json`

A small shared normalization helper may be extracted only if it simplifies repeated raw provenance/error logic without weakening strict typing.

## Binding rules

1. Parse directly from immutable raw payload bytes.
2. `channel != "activeAssetCtx"` returns `NOT_APPLICABLE`.
3. Strictly map only configured Hyperliquid mainnet BTC/ETH perpetuals.
4. Price/rate values use exact `Decimal`; no binary-float persistence.
5. Never invent an exchange timestamp.
6. If the documented message lacks native event time:
   - `exchange_ts_ns = None`;
   - `exchange_ts_resolution_ns = None`;
   - `exchange_ts_semantics = UNKNOWN`;
   - include `QualityFlag.MISSING_EXCHANGE_TIME`.
7. Local receive timestamps remain the causal availability clock.
8. One valid context frame may yield multiple normalized events sharing the same raw reference.
9. Derived event IDs must be deterministic and distinguish funding/mark/oracle event types from the same raw frame.
10. Required context fields remain strict; additive future fields may be ignored under the explicit compatibility policy.
11. Malformed target payloads return structured errors; no silent partial normalization unless the task explicitly defines independent-field salvage and tests it.
12. Do not treat `activeAssetCtx.funding` as an account funding payment. It is a market observation only.
13. Do not create `FundingPayment`; account cash-flow funding belongs to later user/account capture.

## Funding policy

The parser may emit `FundingRateObservation` only after verifying:

- whether the wire `funding` value is current/predicted/realized;
- the rate period represented by the value;
- whether an effective payment boundary can be known from this message alone.

If the feed documents a rate but not the narrow `FundingObservationKind` distinction required by the v1 contract, record the mismatch explicitly and choose the narrowest defensible representation. Do **not** guess merely to fill the contract.

If the existing v1 contract cannot represent the verified semantics without distortion, stop and document the schema conflict instead of coding around it.

## Mark/oracle policy

For each valid configured perp context:

- emit `MarkPrice` from verified `markPx`;
- emit `OraclePrice` from verified `oraclePx`;
- both use exact decimals;
- missing/invalid required price is a structured target parse error;
- no executable-fill meaning is inferred from mark/oracle prices.

## Error taxonomy

At minimum distinguish:

- invalid JSON/UTF-8;
- invalid envelope;
- invalid context object;
- unsupported coin;
- missing/invalid `ctx`;
- invalid funding value;
- invalid mark price;
- invalid oracle price;
- raw provenance mismatch;
- verified-schema semantic conflict.

Do not include full raw payloads in routine errors.

## Required tests

### Unit

- valid BTC context;
- valid ETH context;
- exact mark/oracle/rate decimals;
- absence of exchange timestamp is represented exactly;
- required missing-time quality flag;
- deterministic three-event identity;
- additive future fields;
- unsupported coin;
- malformed context shape;
- missing required field;
- invalid/non-string or invalid numeric values according to verified wire types;
- non-target NOT_APPLICABLE;
- raw SHA mismatch;
- deterministic serialization/repeated normalization.

### Replay integration

Write raw frames through QCR1 and prove:

- shared raw segment/offset/SHA reaches all derived events;
- derived event IDs are distinct by event type and deterministic;
- causal availability remains receive-time based when native time is absent;
- malformed target context is surfaced;
- non-target channels are explicitly skipped.

## Evidence artifact

`artifacts/stage_0/hyperliquid_context_normalization.json` records:

- parse version;
- verified `activeAssetCtx` / `PerpsAssetCtx` schema;
- native timestamp availability decision;
- funding semantics / period / kind decision;
- mark/oracle meaning;
- exact-numeric policy;
- multi-event identity rule;
- error policy;
- test/replay coverage;
- CI result;
- remaining UNKNOWNs.

## Definition of Done

1. Current official context/funding schema re-verified and recorded.
2. Mark/oracle events normalize deterministically.
3. Funding observation is represented only if semantics fit the v1 contract.
4. No exchange timestamp is fabricated.
5. Complete raw provenance is preserved.
6. Strict BTC/ETH mapping remains in force.
7. Malformed target data is never silently dropped.
8. QCR1 replay proves deterministic output.
9. No account funding payment/reference/features/backtest/execution code is introduced.
10. Ruff/format/strict mypy/pytest green on Python 3.12 and 3.13.
11. `STATUS.md` advances to TASK-013.

## Do Not Build

- user/account funding payments;
- Coinbase/reference adapter (TASK-013);
- Parquet/materialized research tables;
- features/labels/models/backtest;
- strategy/OMS/signing/trading.
