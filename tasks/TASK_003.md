# TASK-003 — Strict Recorder Configuration and Instrument Registry

## Status

`PENDING`

## Objective

Define the configuration and instrument identity contracts that the recorder will consume before any network recorder implementation begins.

The task must make symbol/venue/product distinctions explicit and reject ambiguous or silently-defaulted configuration.

## Planned files

- `config/recorder.yaml`
- `config/instruments.yaml`
- `src/cryptobot/config.py`
- `src/cryptobot/data/instruments.py`
- `src/cryptobot/data/__init__.py`
- `tests/unit/test_config.py`
- `tests/unit/test_instruments.py`
- `artifacts/stage_0/config_report.json`

## Required configuration domains

### Recorder

Define, but do not yet implement:

- enabled public sources;
- instruments per source;
- requested public channels;
- storage root;
- raw/normalized paths;
- queue limits;
- segment/rollover policy placeholders only where already justified;
- reconnect policy as explicit configuration fields without inventing production thresholds;
- clock-health recording switch;
- data-quality/report output paths.

Any operational threshold not yet supported by evidence must be represented as an explicit unset/derived-later value, not an arbitrary default.

### Instruments

At minimum represent:

- canonical instrument ID;
- venue;
- environment;
- native symbol;
- base asset;
- quote asset;
- settlement/margin asset where relevant;
- product type (spot/perpetual);
- primary/replication/reference role;
- price/size precision when verified, otherwise unknown;
- venue-native identifier/index when verified, otherwise unknown.

BTC/ETH Hyperliquid perps and reference-market mappings must never collapse USD spot and USDC-margined perpetuals into the same instrument identity.

## Validation requirements

- Unknown configuration fields rejected.
- Required fields enforced.
- Duplicate canonical instrument IDs rejected.
- Duplicate venue/native-symbol/product identities rejected.
- Canonical IDs deterministic and stable.
- BTC and ETH primary/replication roles valid.
- Reference instruments explicitly distinct from Hyperliquid execution instruments.
- USD and USDC distinctions retained.
- Unknown precision/index values remain `null`; no fabricated values.
- Config paths normalized but not required to exist during pure unit validation.
- Recorder config cannot request an instrument absent from the registry.
- Recorder config cannot request an unsupported/unregistered channel name.

## Tests

Include positive and negative unit tests for:

- valid project configuration;
- unknown fields;
- missing fields;
- duplicate instrument identities;
- invalid enum values;
- unknown instrument reference;
- duplicate channel request;
- quote/margin distinction;
- nullable unverified metadata;
- stable serialization/report output.

No network calls in unit tests.

## Completion artifact

`artifacts/stage_0/config_report.json` must summarize:

- schema versions;
- configured sources;
- configured instruments;
- unresolved metadata fields;
- validation result;
- test/CI status.

## Definition of Done

1. Strict recorder configuration is machine validated.
2. Instrument identities cannot alias accidentally across venue/product/quote.
3. Unknown metadata remains unknown.
4. Config/registry tests pass under Python 3.12 and 3.13.
5. Ruff/format/strict mypy/full pytest CI is green.
6. `STATUS.md` advances to TASK-004.

## Do Not Build

- WebSocket connections.
- Hyperliquid API client.
- Coinbase or other reference adapter.
- raw writer.
- event schema.
- strategy/model/trading code.
