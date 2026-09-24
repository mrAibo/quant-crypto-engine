# Auxiliary retrospective market-data archives

## Purpose

This data is for retrospective sanity checks, regime analysis, and later research only.

It is **not eligible** for the TASK-018 prospective Frontier Gate and must never be added to
`/var/lib/quant-crypto-engine/frontier-campaign`.

The machine-readable eligibility label is:

`EXCLUDED_FROM_TASK_018_FRONTIER_GATE`

## Official sources

### Binance USD-M

Binance Data Vision publishes daily/monthly public market archives. This project initially
uses daily `aggTrades` for BTCUSDT and ETHUSDT because they remain publicly downloadable
without an account and each archive has a published `.CHECKSUM`.

Example source path:

`https://data.binance.vision/data/futures/um/daily/aggTrades/BTCUSDT/`

The downloader verifies SHA-256 before publishing the local archive manifest.

Binance historical `aggTrades` are not a substitute for the live reference `bookTicker`
stream used by TASK-018.

### Hyperliquid

The official Hyperliquid archive exposes hourly L2 book snapshots at:

`s3://hyperliquid-archive/market_data/YYYYMMDD/HOUR/l2Book/COIN.lz4`

The official documentation states that this archive is uploaded approximately monthly,
timeliness is not guaranteed, data may be missing, and S3 transfer is Requester Pays.

Therefore the planner records Hyperliquid objects, but downloading them requires an AWS
identity configured for Requester Pays. No exchange account or wallet is required.

## Storage

Recommended root:

`/var/lib/quant-crypto-engine/retrospective`

Do not use the prospective campaign directory.

## Create a deterministic source plan

Example:

```bash
uv run --python 3.12 python -m cryptobot.cli plan-retrospective-data \
  --start-date 2026-09-01 \
  --end-date 2026-09-07 \
  --output /var/lib/quant-crypto-engine/retrospective/plan-2026-09-01_07.json
```

A one-day plan contains:

- Binance BTCUSDT daily aggTrades;
- Binance ETHUSDT daily aggTrades;
- 24 hourly Hyperliquid BTC L2 objects;
- 24 hourly Hyperliquid ETH L2 objects.

Every source entry is explicitly marked as excluded from TASK-018 adjudication.

## Download one Binance archive

Example:

```bash
uv run --python 3.12 python -m cryptobot.cli download-binance-retrospective \
  --date 2026-09-01 \
  --symbol BTCUSDT \
  --destination /var/lib/quant-crypto-engine/retrospective
```

The command downloads the archive and its official checksum, verifies SHA-256, then writes a
manifest last. Existing files are never overwritten.

## Analyze Binance 50-second trade-price movement

After downloading a contiguous BTCUSDT/ETHUSDT daily range, build a deterministic,
checksum-reverified descriptive report:

```bash
uv run --python 3.12 python -m cryptobot.cli analyze-binance-retrospective-50s \
  --source-root /var/lib/quant-crypto-engine/retrospective \
  --start-date 2026-08-01 \
  --end-date 2026-08-07 \
  --output /var/lib/quant-crypto-engine/retrospective/binance-50s-2026-08-01_07.json
```

The analyzer re-hashes every ZIP against its previously published retrospective manifest,
requires the frozen Binance aggTrades CSV schema, and uses exact Decimal arithmetic with
nearest-rank quantiles. Its metric is absolute first-to-last aggTrade price movement within
clock-aligned, non-overlapping 50-second buckets.

This report is descriptive context only. Trade price is not Hyperliquid primary BBO mid, it
does not reproduce local receive-time/gap/host-boot semantics, and it contains no executable
spread/friction evidence. Therefore its quantiles must never be substituted into the
TASK-018 Frontier Gate.

## Hyperliquid Requester Pays

After AWS CLI credentials are configured, planned objects can be copied with the equivalent
of:

```bash
aws s3 cp \
  s3://hyperliquid-archive/market_data/20260901/7/l2Book/BTC.lz4 \
  /var/lib/quant-crypto-engine/retrospective/hyperliquid/l2book/2026-09-01-7-BTC.lz4 \
  --request-payer requester
```

Do not add AWS credentials to the repository, environment examples, manifests, or campaign
evidence.

## Interpretation boundary

Historical archives can help answer questions such as whether observed movement distributions
are unusual across regimes. They cannot replace the preregistered prospective 2,952-window
sample because they do not reproduce the same local receive-time, gap, host/boot, and live-feed
availability semantics.
