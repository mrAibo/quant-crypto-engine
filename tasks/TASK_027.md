# TASK-027 — Stage 2 Prospective Development Evidence Expansion

## Status

**IMPLEMENTATION READY — CAPTURE NOT STARTED**

## Context

TASK-026 selected **PROSPECTIVE_DEVELOPMENT_EVIDENCE_EXPANSION** as the single
primary next path.

The purpose is to obtain substantially more causal public microstructure evidence
without changing the predictive family, opening old confirmation, assuming a lower
fee, or introducing maker execution.

## Objective

Collect one immutable, fixed-duration, public-only DEVELOPMENT dataset suitable for
a later separately frozen microstructure evaluation protocol.

This task is evidence collection and support accounting first, not a new model search.

## Frozen collection protocol

- host: Aibo persistent Ubuntu WSL environment;
- duration: **72 hours** from the first accepted campaign capture start;
- duration must not be extended or shortened because of observed market outcomes;
- operational segmentation may reuse the validated immutable QCR1 campaign pipeline;
- primary market: Hyperliquid BTC;
- reference market: Binance USDⓈ-M BTCUSDT;
- public sources only:
  - Hyperliquid L2/BBO/trades;
  - Binance reference BBO/trades;
- native receive-time / host / boot causal boundaries remain explicit;
- gaps, reconnects, duplicates, failed segments, and missingness remain visible.

## Evidence role and boundaries

Every row captured by this campaign is **DEVELOPMENT_ONLY**.

It must not be called SELECTION, CONFIRMATION, validation, or fresh registered test
evidence.

The old Stage-2 confirmation partition remains **UNOPENED_AND_EXCLUDED**.

No existing exposed outcome may be used to alter:

- the 72-hour duration;
- the existing TASK-025 eight-feature definitions;
- the already developed 50s / 300s horizons;
- feature thresholds;
- model hyperparameters;
- collection inclusion/exclusion semantics.

## Support planning

TASK-025 exposed 1,282 50-second development rows with 409 valid full-feature targets,
of which 24 were positive under executable bid/ask plus the 4.5 bps/side fee
scenario.

The committed Stage-2 protocol shows that those 1,282 rows span about 24.82 hours
from the first source decision to the untouched confirmation boundary. Scaling the
**observed wall-time rates**, rather than treating every ideal 50-second interval as
an observed row, gives the following 72-hour planning estimates:

- about 3,719 Stage-2 rows;
- about 1,187 valid full-feature targets;
- about 70 positive targets.

There are 5,184 ideal 50-second intervals in 72 hours, but that number is only a
cadence ceiling and is not used as the projected row count. These are planning
estimates only. They are not minimum acceptance criteria and must not become an
optional-stopping rule.

The frozen 4.5 bps/side fee remains a **SCENARIO**. Actual account fee, latency,
own-order impact/slippage, funding boundaries, and maker economics remain UNKNOWN.

## No private or capital dependency

TASK-027 does not require:

- Hyperliquid account authentication;
- API keys or wallets;
- deposits or capital;
- private/account streams;
- AWS requester-pays credentials;
- maker orders;
- OMS/signing logic.

If the public campaign cannot run safely on Aibo, record the operational blocker
rather than substituting private data or weakening provenance rules.

## Definition of Done

1. A machine-readable frozen campaign protocol is committed before capture begins.
2. The 72-hour public-only campaign is started from that committed protocol.
3. Raw evidence and segment manifests are immutable and audit-valid.
4. Campaign completion is determined by elapsed protocol time, not outcomes.
5. A deterministic DEVELOPMENT dataset/support report records source digests,
   coverage, missingness, valid-feature counts, and target-class support.
6. No predictive model is fitted and no new threshold/horizon is selected in TASK-027.
7. Old confirmation remains unopened/excluded.
8. No fresh registered SELECTION/CONFIRMATION campaign is started.
9. The next task freezes the evaluation protocol before using the new DEVELOPMENT
   outcomes for model-family adjudication.
10. Ruff/format/strict mypy/pytest are green before merge.

## Do Not Build

- new predictive features or horizon sweeps;
- LightGBM or unrestricted tuning;
- Jev/GPT runtime;
- maker simulation or orders;
- private account data ingestion;
- OMS/signing/order execution;
- capital deployment;
- retrospective extension of collection based on observed results.


## Protocol implementation checkpoint

The capture protocol and orchestration are implemented but **capture must not start
until this exact commit has passed CI and merged to main**.

Frozen protocol artifact:

- `artifacts/stage_2/development_campaign_protocol.json`
- SHA-256 `1ab9a735f512dd301392ba568b49ebd0f1e80d676f073b3d502bf73d111bc1d3`

Frozen public transport profile:

- `config/runtime/stage2-development-public.json`
- SHA-256 `8bf2a31ec634b475f1e3b559663bb35e16950c1c721ab73ddc5812cd6b1f03e1`

The network capture intentionally reuses the validated Stage-0 public dual-source
transport as a superset. ETH and Hyperliquid `activeAssetCtx` frames are preserved
raw because the validated adapter captures them, but TASK-027 eligibility is frozen
to Hyperliquid BTC L2/BBO/trades and Binance BTCUSDT bookTicker/aggTrade only.

Campaign root after merge:

`/var/lib/quant-crypto-engine/stage2-development-campaign`

The first failed capture attempt does not start the 72-hour clock. The immutable
campaign start/deadline is derived from the earliest attempt that successfully
publishes `capture-ready.json`. No model is fitted and no outcome statistic is
used by the collection/status code.
