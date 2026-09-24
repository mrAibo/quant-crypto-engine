# Stage-0.5 frontier evidence campaign runbook

## Purpose

TASK-018 collects the prospective evidence required to adjudicate the first **model-free**
50-second profitability frontier.

This runbook does not start trading, fit a model, use a private/account endpoint, or prove
alpha.

The pre-registered campaign contract is:

- primary market: Hyperliquid BTC perpetual;
- reference market: Binance USDⓈ-M BTCUSDT;
- target horizon: 50 seconds;
- required valid non-overlapping windows: 2,952;
- DKW planning confidence: 0.95;
- DKW maximum empirical-CDF error: 0.025;
- mathematical minimum observed support: 147,600 seconds (~41 hours);
- first gate rule: q95 absolute primary-mid movement must be **strictly greater** than q50
  known friction floor.

The 41-hour value is a mathematical minimum, not a wall-clock promise. Gaps and excluded
windows can require additional collection.

## Evidence layout

Use one persistent campaign root, for example:

```text
/var/lib/quant-crypto-engine/frontier-campaign/
  campaign-config.json
  segment-<run-id>/
    raw/
      ...
      manifest.json
    dataset/
      manifest.json
      *.parquet
    recorder-summary.json
    normalization-report.json
    frontier-audit.json
    segment-evidence.json
  campaign-reports/
    <campaign-manifest-sha256>.json
```

A segment directory is accepted by campaign discovery only after
`segment-evidence.json` exists and all bound digests validate.

A failed/interrupted segment may remain on disk without `segment-evidence.json`.
It is reported as incomplete and is **not** included in campaign statistics.

Never edit an accepted segment in place.

## Install the locked environment

From the repository checkout:

```bash
uv sync --locked --all-groups --python 3.12
```

No wallet, API key, private account address, or signing key is required.

## Initialize the campaign exactly once

The current Stage-0.5 fee value is a **documented-base taker SCENARIO**, not a measured
future project-account fee.

Example:

```bash
uv run --python 3.12 python -m cryptobot.cli init-frontier-campaign \
  --campaign-root /var/lib/quant-crypto-engine/frontier-campaign \
  --campaign-id btc-frontier-50s-v1 \
  --fee-scenario-bps-per-side 4.5
```

The command refuses to overwrite `campaign-config.json` and refuses initialization after
segment directories already exist.

## Capture one bounded segment

Use the validated dual-source public config as the network/recorder basis.

The CLI ignores that config's storage paths and run duration for the campaign run. It writes
into a new `segment-<run-id>` directory and uses the explicit
`--duration-seconds` value.

Example one-hour segment:

```bash
uv run --python 3.12 python -m cryptobot.cli run-frontier-segment \
  --config config/runtime/dual-source-smoke.json \
  --campaign-root /var/lib/quant-crypto-engine/frontier-campaign \
  --duration-seconds 3600 \
  --registry config/instruments.yaml
```

Segment duration is an operational choice, not a statistical threshold. Reasonable shorter
segments reduce restart blast radius; longer segments reduce per-segment overhead.

A successful segment performs, in order:

1. dual public-source capture;
2. QCR1 seal and storage audit;
3. causal normalization;
4. rejection if normalization contains target/source errors;
5. deterministic Parquet materialization;
6. manifest/table SHA verification;
7. model-free frontier dataset audit;
8. exclusive publication of `segment-evidence.json`.

The command returns non-zero if an acceptance step fails.

## Rebuild the cumulative campaign report

After any successful segment:

```bash
uv run --python 3.12 python -m cryptobot.cli report-frontier-campaign \
  --campaign-root /var/lib/quant-crypto-engine/frontier-campaign
```

The command:

- reloads the frozen campaign config;
- discovers only `segment-*` directories with published evidence;
- re-hashes each bound evidence file;
- re-hashes all Parquet files against the TASK-015 manifest;
- recomputes the dataset bundle hash;
- rejects duplicate dataset/normalization digests;
- rejects overlapping/touching accepted segment wall intervals;
- never creates a movement window across a segment or host/boot boundary;
- writes a deterministic revision under `campaign-reports/<manifest-sha>.json`.

Important output fields:

- `published_segment_count`;
- `incomplete_segment_directories`;
- `report.total_valid_non_overlapping_windows`;
- `report.adjudication_window_count`;
- `report.readiness`;
- `report.gate_decision`.

Until 2,952 valid non-overlapping 50-second windows exist, readiness stays
`COLLECTING` and the gate decision stays `INCONCLUSIVE`.

## Initial gate interpretation

When the first deterministic 2,952-window sample is available:

- `PASS_FEASIBILITY`: q95 absolute movement > q50 known friction;
- `FAIL_FEASIBILITY_AT_50S`: q95 absolute movement <= q50 known friction;
- `INCONCLUSIVE`: required evidence is missing/corrupt.

This is **not** a strategy result.

Even `PASS_FEASIBILITY` does not establish predictability, realizable slippage, actual
account fees, execution latency, capacity, or positive net expectancy.

The fee remains a SCENARIO and latency/funding-boundary/maker economics remain UNKNOWN
unless separately measured.

## Restart and recovery

After host reboot or network failure:

1. do not delete the old segment directory;
2. run `report-frontier-campaign` to see whether it was fully published;
3. if the directory is listed as incomplete, preserve it for diagnostics;
4. start a **new** segment run;
5. never splice raw files from two runs into one accepted segment.

Cross-boot monotonic timestamps are never compared.

## Recommended split systemd operation

For long prospective collection, prefer decoupled capture and processing so expensive
normalization/Parquet work does not create market-data gaps.

Templates:

- `deploy/systemd/quant-frontier-capture.service`
- `deploy/systemd/quant-frontier-capture.timer`
- `deploy/systemd/quant-frontier-process.service`
- `deploy/systemd/quant-frontier-process.timer`

The legacy combined templates remain available for bounded/manual compatibility:

- `deploy/systemd/quant-frontier-segment.service`
- `deploy/systemd/quant-frontier-segment.timer`

Recommended host layout:

- code: `/opt/quant-crypto-engine`;
- dual-source config: `/etc/quant-crypto-engine/dual-source.json`;
- campaign data: `/var/lib/quant-crypto-engine/frontier-campaign`;
- service user/group: `quantcrypto`.

The split capture template defaults to 900-second segments. Override only the operational
segment size in `/etc/quant-crypto-engine/frontier-campaign.env`:

```text
SEGMENT_SECONDS=900
```

The capture unit writes `capture-ready.json` only after clean durable raw sealing. The
processor considers only capture-ready directories that have neither
`segment-evidence.json` nor `processing-started.json`. It writes the processing marker
before expensive work, so a crashed/OOM processing attempt is preserved and not retried
automatically.

The capture timer starts the next raw segment 10 seconds after the prior capture unit becomes
inactive. A successful capture triggers the lower-priority processor immediately through
`OnSuccess=`; the processor's one-minute timer is a recovery/backlog fallback. Capture can
therefore continue while the previous sealed segment is normalized/materialized.

Install after initializing the campaign:

```bash
sudo systemctl disable --now quant-frontier-segment.timer

sudo install -m 0644 deploy/systemd/quant-frontier-capture.service /etc/systemd/system/
sudo install -m 0644 deploy/systemd/quant-frontier-capture.timer /etc/systemd/system/
sudo install -m 0644 deploy/systemd/quant-frontier-process.service /etc/systemd/system/
sudo install -m 0644 deploy/systemd/quant-frontier-process.timer /etc/systemd/system/

sudo systemctl daemon-reload
sudo systemctl enable --now quant-frontier-capture.timer quant-frontier-process.timer
```

Inspect:

```bash
systemctl status quant-frontier-capture.timer
systemctl status quant-frontier-capture.service
systemctl status quant-frontier-process.timer
systemctl status quant-frontier-process.service
journalctl -u quant-frontier-capture.service -u quant-frontier-process.service -f
```

Build the cumulative report periodically, after published segments or at operational
checkpoints:

```bash
uv run --python 3.12 python -m cryptobot.cli report-frontier-campaign   --campaign-root /var/lib/quant-crypto-engine/frontier-campaign
```

Stop future capture/processing without deleting evidence:

```bash
sudo systemctl disable --now quant-frontier-capture.timer quant-frontier-process.timer
```

Never delete prior accepted or incomplete segment directories during migration.

## Disk and retention

Do not prune accepted raw QCR1 or Parquet data during TASK-018. QCR1 remains authoritative
and Parquet remains rebuildable derived evidence.

Before a long campaign, verify free space and monitor it. If capacity becomes constrained,
stop starting new segments; do not delete accepted evidence to make room.

## Completion

TASK-018 is complete only after:

1. campaign code/tests are green;
2. at least 2,952 valid non-overlapping 50-second windows are present;
3. the deterministic campaign report records the pre-registered gate decision;
4. the result and source digests are committed to the repository evidence artifact;
5. STATUS.md advances to the branch dictated by that decision.

Do not fit logistic regression, LightGBM, Jev, GPT, or any other predictive model before
this gate is adjudicated.
