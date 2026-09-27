# Stage 2 Tardis Historical DEVELOPMENT Corpus

## Purpose

TASK-028 imports a frozen 480-hour historical microstructure corpus in parallel
with the prospective TASK-027 campaign.

It is DEVELOPMENT only. It does not replace prospective evidence and cannot become
SELECTION or CONFIRMATION evidence.

## Frozen protocol

Repository artifact:

`artifacts/stage_2/tardis_historical_development_protocol.json`

Frozen dates are the first UTC day of each month from 2024-11-01 through
2026-06-01 inclusive: 20 days / 480 hours.

The range ends before Tardis changes normalized Hyperliquid order-book snapshots
from regular `l2Book` to `fastBook` on 2026-06-17.

## Per-day archives

- Hyperliquid BTC `book_snapshot_5`
- Hyperliquid BTC `trades`
- Binance USDS-M BTCUSDT `quotes`
- Binance USDS-M BTCUSDT `trades`

Expected total: 80 gzip CSV archives.

`book_snapshot_5` is used for both Hyperliquid BBO and top-5 depth so the same
reconstructed book state supplies the related TASK-025 features.

## Time semantics

Tardis `local_timestamp` is the message-arrival timestamp and is the primary
historical ordering field.

Tardis records both Hyperliquid and Binance Futures from GCP asia-northeast1
(Tokyo), so cross-venue `local_timestamp` alignment is allowed for this external
DEVELOPMENT corpus.

This timestamp is not Aibo receive-time and may not be presented as if the historical
messages passed through our own recorder.

## Storage

Use:

`/var/lib/quant-crypto-engine/tardis-historical-development`

Never use the TASK-018 or TASK-027 campaign roots.

## Download after protocol merge

From the deployed merged checkout:

```bash
python -m cryptobot.cli download-tardis-historical \
  --protocol /opt/quant-crypto-engine/artifacts/stage_2/tardis_historical_development_protocol.json \
  --destination /var/lib/quant-crypto-engine/tardis-historical-development \
  --workers 4
```

The downloader is restart-safe only for verified immutable evidence. Existing files
must match their manifest SHA, size, source URL, and protocol SHA.

Each gzip is fully decompressed to verify gzip CRC and its exact CSV header before
the archive and immutable manifest are accepted.

## Status

```bash
python -m cryptobot.cli status-tardis-historical \
  --destination /var/lib/quant-crypto-engine/tardis-historical-development
```

Completion requires 80/80 verified archives.

## Completion checkpoint

TASK-028 completed with:

- 80/80 verified archives;
- 0 missing archives;
- 1,180,336,813 compressed bytes;
- corpus manifest:
  `artifacts/stage_2/tardis_historical_corpus_manifest.json`;
- corpus manifest SHA-256:
  `9696dca5f57fe160a8438236f1af82947a1588d2476a882fdf627f4cbd26e5e8`;
- archive-set SHA-256:
  `8e545456b34c6d1dabdb4e31fc13a0cb174bb96fef01eb137d9c32fa1dcb37fc`.

The corpus report binds every archive SHA and every local immutable manifest SHA.
It records `economic_outcomes_consumed=false` and `model_fitted=false`.

## Analysis boundary

TASK-028 does not fit a model and does not inspect outcomes to change the corpus.

A later work package must freeze the feature construction, chronological split,
training procedure, and development evaluation rule before using the downloaded
historical outcomes.

CryptoDataDownload can be used later as independent coarse OHLCV/trade-print context,
but not as a substitute for Tardis receiver-timestamped top-5 microstructure.
