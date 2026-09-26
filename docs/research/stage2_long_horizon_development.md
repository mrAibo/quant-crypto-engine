# Stage 2 Longer-Horizon Economic Development

## Decision

TASK-024 closes with:

**STOP_300S_FAMILY**

Decision artifact:

- `artifacts/stage_2/economic_300s_decision.json`
- SHA-256
  `b36027ab6436258b4970e974280ee3669813c585d7deb96a29f00079aca12eb6`

The old Stage-2 confirmation partition remained unopened and excluded. No fresh test
evidence was collected.

## Development-only horizon context

Checksum-verified Binance USD-M aggTrade archives from 2026-08-01 through 2026-08-07
were used only to choose a development horizon.

Artifact:

- `artifacts/stage_2/binance_development_horizon_1_2_5m.json`
- SHA-256
  `effefa74fe611bc2e77bc40177cf652193632b1163768a384870a3eb579dc722`

BTC movement context:

- 60s q95: approximately **7.53 bps**;
- 120s q95: approximately **10.19 bps**;
- 300s q95: approximately **15.68 bps**;
- 300s fraction above 9 bps: approximately **17.51%**.

Before Hyperliquid 300s outcomes were evaluated, the development decision selected
300 seconds as the shortest scanned horizon with material reference-price headroom
over the approximately 9 bps fee-only round trip.

Decision artifact:

- `artifacts/stage_2/economic_horizon_development_decision.json`
- SHA-256
  `626f85a08ca187d0c1762cdc7a22c49dfe2301baa97ad9d09c1fdd5acfb164e6`

Binance history is development context only: it is trade-price evidence, not
Hyperliquid executable BBO and not native receive-time evidence.

## Pre-outcome 300s registry

The bounded 300s registry was written before Hyperliquid 300s outcome evaluation.

Artifact:

- `artifacts/stage_2/economic_300s_registry.json`
- SHA-256
  `f0290fc70dda2911afab02f1a92b4f4262ff6ec1883a25fa86cb129fd4d2a7a8`

It contains exactly four deterministic candidates plus one fixed logistic fallback.
No post-outcome threshold changes are allowed.

## Reproducible 300s development cache

Artifact:

- `artifacts/stage_2/economic_300s_development_cache.json`
- SHA-256
  `459e85a618f5026862428eadd34a652fe1bc63d59d19580e3ea38cf0d3d243b4`
- rows: **215**
- horizon: **300 seconds**
- source: verified Gate segment datasets before the old confirmation wall only.

The cache includes source segment digests and executable entry/exit bid/ask evidence.

Reproduction tools live under `tools/research/task024/`.

## Deterministic 300s result

Artifact:

- `artifacts/stage_2/economic_300s_deterministic_results.json`
- SHA-256
  `b7555046b013a6564560095d36c4cd2a7638fc4b5b880e8359acd08919920201`
- DEV_A / DEV_B: **129 / 86 rows**.

No candidate passed.

DEV_B summary:

- unfiltered H2 benchmark:
  - 22 valid trades;
  - mean known-net PnL about **-70.06** quote units;
- E300_1_IMB_STRONG:
  - 14 valid trades;
  - mean about **-62.61**;
- E300_2_IMB_EXTREME:
  - 9 valid trades;
  - mean about **-39.90**;
  - best observed deterministic mean, but still negative and support is below 30;
- E300_3_IMB_STRONG_BIN_ALIGN:
  - 4 valid trades;
  - mean about **-89.17**;
- E300_4_IMB_STRONG_BIN_ALIGN_STRONG:
  - 2 valid trades;
  - mean about **-109.46**.

Therefore the deterministic family failed its predeclared economic/support gate.

## Fixed 300s logistic fallback

The fallback was allowed only because all deterministic candidates failed.

Artifact:

- `artifacts/stage_2/economic_300s_logistic_results.json`
- SHA-256
  `a11358926b8b69f764e3e0a595f913d17baec8f133521efb81f1f9578ce456d0`

DEV_B:

- q95 score gate: **0 valid selected trades**;
- q90 score gate: **0 valid selected trades**.

The fallback therefore also failed.

## Interpretation

A longer 300-second horizon increases raw movement headroom, but the bounded H2 /
Binance family still did not produce positive executable taker economics in
development.

This does **not** show that all 300-second strategies fail. It shows that this
predeclared small family failed and must not be expanded retroactively after seeing
its outcomes.

The next useful development question is microstructure state, not another threshold
sweep.

## Historical Hyperliquid data

Hyperliquid documents requester-pays historical L2 book snapshots in its S3 archive.
That source may be used to expand **development** evidence, subject to explicit
provenance and completeness limitations. It does not replace prospective
receive-time evidence for a registered test.

Aibo currently has no AWS CLI or requester credentials configured, so historical S3
retrieval is optional rather than a blocker.

## Next step

Proceed to TASK-025 — bounded microstructure economic development.

Use already captured exposed L2/trade/reference evidence first. Any future family
that passes development must freeze its protocol before collecting fresh prospective
SELECTION and later untouched CONFIRMATION evidence.
