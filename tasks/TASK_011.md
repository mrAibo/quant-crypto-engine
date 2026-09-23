# TASK-011 — Hyperliquid Trade Normalization from Raw Capture

## Status

`COMPLETE`

## Objective

Normalize Hyperliquid public `trades` raw WebSocket messages into the existing v1 `Trade` event contract while preserving exact raw provenance, exact numerics, native side semantics, and deterministic identity for multiple trades contained in one raw frame.

This task extends semantic parsing only. It does **not** add features, labels, trade-sign inference beyond documented native semantics, funding, reference venues, Parquet, or strategy logic.

## Mandatory first action

Before parser behavior is written, re-verify from current official Hyperliquid sources:

- exact `WsTrade[]` message envelope;
- required `WsTrade` fields;
- native `side` values and whether side is aggressor or resting side;
- `time` unit and documented semantic meaning;
- `tid` uniqueness semantics;
- `hash` meaning;
- ordering semantics of multiple trades in one WebSocket message, if documented;
- whether duplicate/replayed trades can occur after reconnect/snapshot behavior.

Record verified facts in the evidence contract. Undocumented ordering/deduplication guarantees remain `UNKNOWN`.

## Inputs

- QCR1 raw frames from TASK-005/009;
- TASK-004 `EventEnvelope` and `Trade`;
- TASK-010 normalization result/error conventions;
- canonical instrument registry;
- current official Hyperliquid trade schema.

## Expected official fields to verify, not assume

The current documentation observed before task creation shows a shape resembling:

```
WsTrade {
  coin: string
  side: string
  px: string
  sz: string
  hash: string
  time: number
  tid: number
  users: [string, string]
}
```

and states that `tid` alone is not globally unique, while a tuple involving block time, coin, and tid is globally unique. TASK-011 must re-verify this immediately before implementation rather than treating this task text as authority.

## Core parsing rules

1. Parse from original raw bytes, never a re-serialized market object.
2. `channel != "trades"` is `NOT_APPLICABLE`.
3. Target-channel malformed payloads produce structured errors.
4. The `data` payload must be an array.
5. One raw WebSocket frame may yield zero, one, or many normalized `Trade` events.
6. Price and size use exact `Decimal`; binary float input is rejected.
7. Native coin maps strictly through the canonical registry.
8. Preserve native side string.
9. Map aggressor side only from verified Hyperliquid side semantics.
10. Never infer buyer/seller direction from price movement.
11. Preserve transaction hash and verified trade identity fields.
12. Do not silently reorder trades in a message.
13. Additive future fields may be ignored only under an explicit compatibility policy.
14. Every normalized event carries complete raw provenance.

## Multi-event identity

Because one raw frame contains an array of trades, deterministic event identity must include enough stable information to distinguish events within that frame.

The event ID should be derived from immutable inputs such as:

- parse version;
- event type;
- raw segment ID;
- raw offset;
- raw payload SHA-256;
- trade array index;
- verified native trade identity fields.

Repeated replay of the same raw frame must generate identical event IDs. Two distinct elements in one frame must never collide.

## Timestamp policy

Do not inherit TASK-010 timestamp semantics blindly.

Re-verify/measure the `WsTrade.time` unit separately. If the wire unit is established but the semantic meaning is not, convert the unit accurately while retaining `ExchangeTimestampSemantics.UNKNOWN` or the narrowest justified semantic.

## Trade identity / duplicate policy

If official documentation confirms the globally unique trade identity tuple, store a deterministic representation in `trade_id`.

Do not add global deduplication in TASK-011 unless there is a verified, testable key. Parser output may mark a duplicate candidate only when exact duplicate identity evidence is present; replay infrastructure itself must remain deterministic.

## User-address field

The documented `users:[buyer,seller]` field is useful provenance, but the existing v1 `Trade` contract has no buyer/seller-address fields.

TASK-011 must:

- validate the field if it is required by the current schema;
- not expand the v1 event schema merely to carry public addresses unless a concrete downstream requirement is documented;
- record this deliberate information-loss boundary in the artifact;
- preserve all original information through raw provenance.

## Error taxonomy

At minimum distinguish:

- invalid JSON/UTF-8;
- invalid envelope;
- invalid trades-array shape;
- invalid trade object;
- unsupported coin;
- invalid native side;
- invalid timestamp;
- invalid price/size;
- invalid `tid`;
- invalid transaction hash;
- invalid users tuple;
- raw provenance mismatch.

Do not include full raw payloads in routine error text.

## Tests

### Unit

- one valid BTC trade;
- one valid ETH trade;
- multiple trades in one raw frame;
- stable source ordering;
- B/A side mapping from verified semantics;
- exact decimal preservation including exponent-form strings if accepted;
- invalid/unknown side;
- unsupported coin;
- malformed timestamp;
- malformed/negative/non-integral tid;
- malformed users tuple;
- malformed hash;
- additive future fields;
- deterministic event IDs;
- unique event IDs within one multi-trade frame;
- non-target channel NOT_APPLICABLE;
- raw SHA mismatch.

### Replay integration

Write raw frames through QCR1, replay them, normalize, and prove:

- event count matches parsed trade elements;
- raw segment/offset/SHA is preserved for every derived event;
- per-element event IDs are deterministic;
- serialization is deterministic;
- target parse errors are surfaced;
- non-target raw frames are skipped explicitly.

## Evidence artifact

Create `artifacts/stage_0/hyperliquid_trade_normalization.json` with:

- parse version;
- verified trade schema;
- native side semantics;
- timestamp unit/semantic decision;
- native trade identity decision;
- multi-event event-ID construction;
- compatibility/error policy;
- deliberately omitted `users` representation rationale;
- test/replay coverage;
- CI result;
- remaining UNKNOWNs.

## Definition of Done

1. Current official trade schema is re-verified and recorded.
2. Raw `trades` arrays normalize deterministically.
3. Multi-event frames have stable collision-free event IDs.
4. Exact Decimal policy is preserved.
5. Native side semantics are mapped only from verified docs.
6. Complete raw provenance is present in every trade envelope.
7. Malformed target data is never silently dropped.
8. Replay tests prove deterministic output.
9. No funding/reference/feature/strategy code is introduced.
10. Ruff/format/strict mypy/pytest green on Python 3.12 and 3.13.
11. `STATUS.md` advances to TASK-012.

## Do Not Build

- mark/oracle/funding normalization (TASK-012);
- external reference feed (TASK-013);
- Parquet/materialized research tables;
- trade-derived features/labels;
- deduplication service;
- backtest;
- strategy/models;
- OMS/signing/trading.


## Implementation status

Implemented:

- official/current `WsTrade[]` schema re-verification;
- official `tid` identity and `users=[buyer,seller]` evidence;
- native side A/B preservation with normalized aggressor side intentionally UNKNOWN;
- measured Unix-millisecond trade timestamp unit;
- measured reconnect replay/duplicate behavior;
- exact-Decimal multi-event normalizer;
- stable vendor-style `trade_id=(time,coin,tid)`;
- occurrence-specific deterministic `event_id`;
- strict BTC/ETH mapping;
- complete raw provenance;
- structured all-or-nothing target parse errors;
- deterministic serialization;
- QCR1 replay and reconnect-duplicate tests;
- `artifacts/stage_0/hyperliquid_trade_normalization.json`.

No funding/reference/Parquet/feature/model/backtest/execution code is present.

## Validation status

GitHub CI: **PASS** — run `35917274342`; 222 tests passed on Python 3.12 and Python 3.13; Ruff, formatter, and strict mypy passed.


## Validation result

GitHub CI run `35917274342` on head `9f5790cca55b6a24a823e3a3b714fc74f01824bf`:

- Ruff: PASS;
- Ruff format: PASS;
- strict mypy: PASS — 44 source files;
- pytest Python 3.12: **222 PASS**;
- pytest Python 3.13: **222 PASS**.

Default CI remains network-independent. The temporary trade probe workflow was removed before validation.


## Merge provenance

Merged as PR #11 in commit `b5fc231ad0631eb442a3c881ee868dc72106ecfd`.

Validated implementation:

- Ruff: PASS;
- Ruff format: PASS;
- strict mypy: PASS;
- pytest Python 3.12: **222 PASS**;
- pytest Python 3.13: **222 PASS**;
- CI run: `35917274342`.
