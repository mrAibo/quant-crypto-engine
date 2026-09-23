# TASK-003 — Strict Recorder Configuration and Instrument Registry

## Status

`IN REVIEW — IMPLEMENTED, GITHUB CI PENDING`

## Objective

Define the configuration and instrument identity contracts that the recorder will consume before any network recorder implementation begins.

The task makes symbol/venue/product distinctions explicit and rejects ambiguous or silently-defaulted configuration.

## Implemented files

- `config/recorder.yaml`
- `config/instruments.yaml`
- `src/cryptobot/config.py`
- `src/cryptobot/data/instruments.py`
- `src/cryptobot/data/__init__.py`
- `tests/unit/test_config.py`
- `tests/unit/test_instruments.py`
- `artifacts/stage_0/config_report.json`

## Key design decisions

### Canonical instrument identity

Canonical IDs are derived from:

- venue;
- environment;
- product type;
- venue-native symbol.

Example:

`hyperliquid.mainnet.perpetual.btc`

This identity intentionally does **not** depend on quote/margin/settlement metadata that is still unverified. Later metadata enrichment therefore does not silently rename the instrument.

### Unknown metadata stays unknown

For the current Hyperliquid BTC/ETH registry, the following remain `null` until separately verified:

- quote asset;
- settlement asset;
- margin asset;
- price decimals;
- size decimals;
- venue-native asset ID.

No review-model assumption is promoted into configuration merely because it is plausible.

### Reference feed remains unresolved

Project scope still requires one external major-market reference feed, but TASK-003 does not choose one.

`reference_feed.required = true`

`reference_feed.selected_source_id = null`

The actual reference source will be selected only after its access, timestamp, completeness, and cadence semantics are verified.

### Operational thresholds remain unresolved

Queue limits, rollover limits, reconnect delays, and jitter values remain explicit `null` values. They must be derived from evidence/measurement rather than invented here.

## Validation guarantees

- Unknown fields rejected.
- Required fields enforced.
- Duplicate source IDs rejected.
- Duplicate channels rejected.
- Unsupported channels rejected.
- Recorder sources may reference only registered instruments.
- Source venue/environment must match the referenced instrument.
- Instrument IDs must match their canonical identity.
- Exactly one PRIMARY instrument is required.
- REFERENCE role and REFERENCE environment must match exactly.
- USD/USDC/USDT-style reference symbols remain distinct through native-symbol identity and quote metadata.
- Unknown precision/asset IDs remain representable as `null`.
- Config paths may be relative and need not exist during unit validation.
- Parent traversal/absolute config paths are rejected.
- Serialization is deterministic.

## Current project configuration

- Hyperliquid mainnet BTC perpetual: PRIMARY.
- Hyperliquid mainnet ETH perpetual: REPLICATION.
- Hyperliquid public channels requested:
  - `l2Book`
  - `bbo`
  - `trades`
  - `activeAssetCtx`
- Reference feed: required but not yet selected.
- No network code exists.

## Tests added

`tests/unit/test_instruments.py` covers:

- current project registry;
- deterministic canonical IDs;
- instrument-ID mismatch;
- duplicate/alias prevention;
- reference-role/environment rules;
- quote-asset distinction;
- exactly one PRIMARY;
- invalid enum;
- unknown fields;
- stable serialization.

`tests/unit/test_config.py` covers:

- current project recorder config;
- unknown/missing fields;
- unknown instrument references;
- duplicate and unsupported channels;
- source/instrument environment mismatch;
- invalid selected reference source;
- path traversal;
- explicit unresolved operational thresholds;
- stable serialization.

## Definition of Done

1. Strict recorder configuration is machine validated. **IMPLEMENTED**
2. Instrument identities cannot alias accidentally across venue/product/native symbol. **IMPLEMENTED**
3. Unknown metadata remains unknown. **IMPLEMENTED**
4. Config/registry tests pass on Python 3.12 and 3.13. **PENDING CI**
5. Ruff/format/strict mypy/full pytest CI is green. **PENDING CI**
6. `STATUS.md` advances to TASK-004 only after merge. **PENDING**

## Do Not Build

- WebSocket connections.
- Hyperliquid API client.
- Reference-venue adapter.
- Raw writer.
- Event schema.
- Strategy/model/trading code.

## Next task after merge

TASK-004 — immutable market-event envelope, exact numeric rules, and clock abstraction.
