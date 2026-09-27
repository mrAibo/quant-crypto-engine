# Stage 2 Prospective DEVELOPMENT Campaign

## Purpose

TASK-027 collects a fixed 72-hour public-only DEVELOPMENT dataset. It does not
create SELECTION or CONFIRMATION evidence, fit a model, or authorize trading.

Frozen repository inputs:

- `artifacts/stage_2/development_campaign_protocol.json`
- `config/runtime/stage2-development-public.json`
- TASK-026 decision SHA-256
  `4c90657accb99a0caff44336bbca091b887f99cd9caedada01fd15364b77b39b`
- TASK-025 registry SHA-256
  `d5024ce6cb16c0d3dcce5b65f3f62f6d577b971d3bda7c8342ab67aaa100b130`

Capture must not start until the protocol commit is merged and deployed.


## Transport and eligibility

The network transport deliberately reuses the validated Stage-0 dual-source public
recorder as a superset. Raw capture therefore preserves BTC and ETH plus
`activeAssetCtx` where the Stage-0 adapter requires them.

TASK-027 eligibility is narrower and frozen:

- Hyperliquid BTC: L2, BBO, trades;
- Binance BTCUSDT: bookTicker, aggTrade;
- horizons: 50s and 300s only;
- TASK-025 eight-feature family unchanged.

ETH and `activeAssetCtx` frames remain immutable raw evidence but are not eligible
for TASK-027 features or targets. They may not tune, rescue, or expand the family.

## Campaign root

Use a new root, never the TASK-018 Frontier Gate root:

`/var/lib/quant-crypto-engine/stage2-development-campaign`

Do not copy accepted TASK-018 segments into this root and do not point the new
systemd units at `/var/lib/quant-crypto-engine/frontier-campaign`.


## Initialize after merge

From the deployed repository checkout:

```bash
python -m cryptobot.cli init-development-campaign \
  --campaign-root /var/lib/quant-crypto-engine/stage2-development-campaign \
  --protocol /opt/quant-crypto-engine/artifacts/stage_2/development_campaign_protocol.json \
  --runtime-config /opt/quant-crypto-engine/config/runtime/stage2-development-public.json
```

Initialization copies the exact protocol and runtime config into the campaign root
immutably. Any digest mismatch is a hard failure.

The first failed capture attempt does not start the 72-hour clock. The campaign start
is recovered from the earliest attempt that produced `capture-ready.json`.
The deadline is then fixed at exactly start + 72 hours.


## Start capture and processing

Install the four `quant-development-*` units from `deploy/systemd`, then:

```bash
systemctl daemon-reload
systemctl enable --now quant-development-capture.timer
systemctl enable --now quant-development-process.timer
```

Capture is 900 seconds per ordinary segment. The CLI has no duration argument:
the frozen protocol supplies the duration, and only the final segment may be shortened
to the remaining wall time before the fixed deadline.

Processing is decoupled and lower priority. It reuses the audited normalization and
materialization path, then adds `development-membership.json` binding each published
segment to the TASK-027 protocol and fixed eligible wall interval.


## Operational status

```bash
python -m cryptobot.cli status-development-campaign \
  --campaign-root /var/lib/quant-crypto-engine/stage2-development-campaign
```

The status is operational only. It reports attempts, captured/published segments,
membership bindings, incomplete processing, and start/deadline state. It does not
calculate signal performance, target economics, or a model score.

After the fixed deadline, the capture command writes an immutable
`campaign-complete.json` with `outcome_dependent=false` and performs no new
capture. Disable the capture timer after observing completion. Keep the processing
timer enabled until all already accepted captures are either published or preserved
as explicit failed/incomplete evidence, then disable it.

Do not delete failed attempts, incomplete processing directories, reconnect evidence,
or extra public frames.


## Preserved boundaries

Throughout TASK-027:

- old Stage-2 confirmation remains `UNOPENED_AND_EXCLUDED`;
- 4.5 bps/side remains a fee SCENARIO;
- actual account fees, latency, own-order impact/slippage, funding boundaries, and
  maker economics remain UNKNOWN;
- no model is fitted;
- no threshold, feature, or horizon is added;
- no API key, wallet, deposit, private stream, maker order, OMS, or capital is used.

The next work package must freeze its evaluation protocol before using the new
DEVELOPMENT outcomes for model-family adjudication.
