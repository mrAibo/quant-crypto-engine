# Public recorder runbook

## Purpose

TASK-009 runs only the Hyperliquid **public** WebSocket recorder. It requires no wallet, API key, signing key, account address, or trading permission.

The first live run is an evidence smoke, not a production-quality data-completeness claim.

## Before running

Use Python 3.12 or 3.13 and install the locked environment:

```bash
uv sync --locked --all-groups --python 3.12
```

Validate the committed smoke config without opening a network connection:

```bash
uv run --python 3.12 python -c "from cryptobot.runtime.public_recorder import load_public_recorder_config; print(load_public_recorder_config('config/runtime/public-recorder-smoke.json'))"
```

The committed smoke config writes below `data/live-smoke/`. Remove or archive a previous smoke directory before repeating the exact same run if its files would collide with a new run.

## Run the finite public smoke

```bash
uv run --python 3.12 python -m cryptobot.cli run-public-recorder --config config/runtime/public-recorder-smoke.json
```

The command prints one final compact JSON summary and exits non-zero when:

- the recorder fails or times out;
- storage audit is not clean;
- zero frames were observed;
- all expected subscription acknowledgments were not observed.

SIGINT and SIGTERM request a graceful bounded drain. The recorder then syncs, closes, seals, commits the manifest, and audits storage.

## Audit an existing smoke

```bash
uv run --python 3.12 python -m cryptobot.cli audit-public-recorder --config config/runtime/public-recorder-smoke.json
```

A clean result means the manifest and sealed raw segment agree. It does **not** prove market-data completeness.

## systemd deployment template

The repository includes `deploy/systemd/quant-crypto-recorder.service`.

Recommended host layout:

- code: `/opt/quant-crypto-engine`;
- config: `/etc/quant-crypto-engine/public-recorder.json`;
- data: `/var/lib/quant-crypto-engine`;
- user/group: `quantcrypto`.

For a service deployment, create a deployment config derived from the smoke config but change:

- `storage_root` to `/var/lib/quant-crypto-engine`;
- `manifest_path` to `/var/lib/quant-crypto-engine/raw-manifest.json`;
- `run_duration_seconds` to `null` for continuous capture.

Keep the basis labels. Do not silently call any value "MEASURED" until measured evidence exists.

Install:

```bash
sudo install -m 0644 deploy/systemd/quant-crypto-recorder.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now quant-crypto-recorder.service
```

Inspect:

```bash
systemctl status quant-crypto-recorder.service
journalctl -u quant-crypto-recorder.service -f
```

Stop:

```bash
sudo systemctl stop quant-crypto-recorder.service
```

The unit uses `Restart=on-failure` and `RestartSec=5s`, above the adapter's two-second minimum reconnect floor. It writes only to `/var/lib/quant-crypto-engine` under `ProtectSystem=strict`.

## Live smoke evidence

The default CI never connects to Hyperliquid.

After an Internet-enabled smoke succeeds, record only observed facts in `artifacts/stage_0/live_capture_smoke.json`:

- command/environment;
- start/end/duration;
- frame count;
- bytes durable;
- queue high-water;
- per-channel counts/rates;
- subscription ACK coverage;
- connection IDs/reconnect count;
- malformed/unknown counts;
- shutdown outcome;
- audit result.

Do not infer missed messages, exchange completeness, latency quality, or strategy profitability from this smoke.
