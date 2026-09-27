# Project Status

> **Continuation entry point:** Read this file first in every new chat/session, then read the referenced current task. Treat this repository as the source of truth over conversational memory.
>
> **Fresh-session shortcut:** read `HANDOFF.md` first for the compact operational handoff, then return here for the authoritative detailed status.

## Project

- Repository: `mrAibo/quant-crypto-engine`
- Current branch: `main`
- Current phase: **Stage 2 — Signal-Existence Dataset and Falsification Protocol**
- Current primary work package: **TASK-027 — Stage 2 Prospective Development Evidence Expansion**
- Parallel bounded work package: **TASK-028 — Tardis Historical Microstructure DEVELOPMENT Corpus**
- Completed: **TASK-001, TASK-002, TASK-003, TASK-004, TASK-005, TASK-006, TASK-007, TASK-008, TASK-009, TASK-010, TASK-011, TASK-012, TASK-013, TASK-014, TASK-015, TASK-016, TASK-017, TASK-018, TASK-019, TASK-020, TASK-021, TASK-022, TASK-023, TASK-024, TASK-025, TASK-026**
- Economic status: **Frontier Gate PASS_FEASIBILITY; bounded 50s, 300s, and microstructure families STOPPED; TASK-026 selected prospective DEVELOPMENT evidence expansion; net edge UNPROVEN**
- Live trading: **FORBIDDEN**
- Production signer/OMS/watchdog before Gate 1: **FORBIDDEN**

## New-session checkpoint — TASK-027 collecting; TASK-028 protocol frozen locally

- latest completed work package: **TASK-026**;
- TASK-027 protocol package: PR #45 merged as
  `b3de5b4c15138ccc1df81c9a055d04920cad237c` after CI run `36312921369` passed;
- deployed Aibo checkout at TASK-027 launch:
  `b3de5b4c15138ccc1df81c9a055d04920cad237c`;
- TASK-027 protocol artifact SHA-256:
  `1ab9a735f512dd301392ba568b49ebd0f1e80d676f073b3d502bf73d111bc1d3`;
- TASK-027 runtime profile SHA-256:
  `8bf2a31ec634b475f1e3b559663bb35e16950c1c721ab73ddc5812cd6b1f03e1`;
- TASK-027 capture state: **COLLECTING**;
- first accepted run ID:
  `run-1790505535742461344-86b3a1307196c582cdde`;
- `started_wall_ns = 1790505535742461344`
  (**2026-09-27 12:38:55.742461 CEST**);
- `deadline_wall_ns = 1790764735742461344`
  (**2026-09-30 12:38:55.742461 CEST**);
- capture/process timers: **ACTIVE**;
- checkpoint: 3 published/bound segments, fourth capture attempt in progress,
  pending processing 0, incomplete processing 0;
- TASK-028 frozen historical protocol SHA-256:
  `8d08ffa54eb64a3ecf11b9a73e3eea5d815f60560e7a93ad6796c63d2760b735`;
- TASK-028 corpus: 20 first-of-month days from 2024-11-01 through 2026-06-01,
  480 nominal hours, 80 Tardis archives;
- TASK-028 evidence role: **DEVELOPMENT_ONLY_EXTERNAL_RECEIVE_TIME**;
- TASK-028 bulk download: **NOT_STARTED — protocol must merge first**;
- TASK-026 decision artifact SHA-256:
  `4c90657accb99a0caff44336bbca091b887f99cd9caedada01fd15364b77b39b`;
- selected primary path: **PROSPECTIVE_DEVELOPMENT_EVIDENCE_EXPANSION**;
- always verify the latest `main` before continuing;
- current work package: **TASK-027 — Stage 2 Prospective Development Evidence Expansion**;
- old confirmation: **UNOPENED_AND_EXCLUDED**;
- no new model/test evidence was consumed during TASK-026;
- no private account, AWS requester-pays, wallet, deposit, or capital access is required now;
- no user action is currently required.

Fresh-session read order:

1. `HANDOFF.md`
2. `STATUS.md`
3. `tasks/TASK_027.md`
4. `tasks/TASK_028.md`
5. `artifacts/stage_2/development_campaign_protocol.json`
6. `artifacts/stage_2/tardis_historical_development_protocol.json`
7. inspect only the implementation/evidence needed for the active bounded tracks

Do not recover project state from old chat messages when repository state differs.

## Primary objective

Determine whether an automated crypto strategy can produce reproducible **positive net expectancy after all real costs**, using the shortest scientifically defensible path. If evidence survives, evolve the same architecture toward unattended 24/7 trading.

Win rate above 50% is descriptive/preferable only; it is not the optimization target.

## Settled scope

- Crypto only for now.
- Hyperliquid is the current execution candidate, not a profitability assumption.
- BTC primary research market.
- ETH replication/generalization market.
- One external major-market reference feed to be selected/frozen during Stage 0.
- Python 3.12+ layered/modular monolith.
- Taker-only first economic validation.
- Maker execution deferred to a separately gated live-measurement experiment.
- Model sequence: deterministic rules → regularized logistic regression → optional LightGBM only if justified.
- GPT has no runtime role in v1.
- Jev receives only one initial bounded veto/ranking hypothesis after the core strategy is validated.
- No autonomous self-modification.
- Human approval required for strategy promotion, capital/risk increases, and latched-halt reset.

## Binding principles

1. The first product is a trustworthy evidence system, not a trading bot.
2. Raw data must be immutable and replayable.
3. Point-in-time availability and missingness are explicit.
4. Core strategy/risk logic contains no network/filesystem/exchange I/O.
5. Research/replay/shadow/paper/live reuse stable strategy/risk/ledger contracts.
6. Costs are counted once; no spread/depth/latency/funding/fee double counting.
7. No production execution stack before Gate 1.
8. Live order intent will be durable before transmission.
9. Ambiguous writes will never be blindly retransmitted.
10. Reconciled exchange evidence is authoritative for orders/fills/positions/cash.
11. Emergency paths do not depend on optional models/AI.
12. Production restarts begin in recovery, never RUNNING.
13. Automatic scale-down/halt is allowed; automatic scale-up is forbidden.
14. An independent watchdog is mandatory before unattended live operation.
15. Unknown facts remain UNKNOWN until specifically verified/measured.

## Stage sequence

Stage 0 → Stage 0.5 → Stage 1 → Stage 2 → **Gate 1** → Replay → Shadow/Paper → OMS/Recovery → Watchdog/Chaos → Micro-live → optional Jev/Maker → controlled scaling.

## Completed work

### TASK-001 — Repository bootstrap

PR #1, merge commit `ed9adb0fe868baeed955302bc3d50deaaa1cb7ca`.

Delivered:

- Python package skeleton.
- committed `uv.lock`.
- Python 3.12 primary and 3.13 compatibility checks.
- Ruff lint/format.
- strict mypy.
- pytest.
- read-only GitHub Actions CI.
- master architecture/evidence/gate/stage documentation.
- `STATUS.md` continuation mechanism.

Artifact: `artifacts/stage_0/bootstrap_report.json`.

### TASK-002 — Evidence contract

PR #2, merge commit `b10034fe26a1af1f48f4c3eaa8d5703abd041d7c`.

Delivered:

- `config/evidence.yaml` using JSON-compatible YAML 1.2.
- strict evidence parser/validator.
- official Hyperliquid provenance notes.
- re-verification rules/reporting.
- 10 evidence-specific unit tests.
- 21 initial facts: **13 VERIFIED / 8 intentionally UNKNOWN**.
- final Ruff/format/strict-mypy/pytest CI green on Python 3.12 and 3.13.

Artifact: `artifacts/stage_0/evidence_report.json`.

Important UNKNOWNs deliberately retained:

- actual future project-account fee rates;
- submit-to-ACK latency distribution;
- IOC partial-fill/rejection distribution;
- realized slippage/own-order impact;
- runtime API-wallet transfer/withdrawal capability boundaries;
- reference-feed selection and timing/completeness semantics;
- completeness of any actual imported historical period.

## Current verified documentation baseline

Checked against official Hyperliquid docs on 2026-09-23 and captured in the evidence contract:

- base perps schedule: 0.045% taker / 0.015% maker;
- first maker rebate tier begins above 0.5% weighted maker volume;
- funding paid hourly; documented payment formula uses oracle price;
- public `l2Book`, `trades`, `bbo`, `activeAssetCtx` channels;
- `WsBook` is documented as a snapshot feed; observed cadence must still be measured;
- `cloid`, ALO/IOC/GTC and `scheduleCancel` documented;
- API-wallet/account identity and per-signer nonce semantics documented;
- official historical archive may be delayed/incomplete and does not replace native receive-time capture.

Human-readable provenance: `docs/evidence_sources.md`.

## Completed — TASK-003

PR #3, merge commit `9dd9145342430ed3a09b1e1e90f2a9d9f02af304`.

Delivered:

- strict recorder configuration;
- canonical instrument registry;
- BTC PRIMARY / ETH REPLICATION project roles;
- explicit nulls for unverified metadata;
- required-but-unselected reference feed;
- explicit nulls for unmeasured operational thresholds;
- 33-test repository suite at the TASK-003 gate;
- final green CI run `35890625489`.

Artifact: `artifacts/stage_0/config_report.json`.

## Completed — TASK-004

PR #4, merge commit `dbc08c6a6f721b9f7e0f0cc0b5afb2e91c948659`.

Delivered:

- immutable normalized event envelope;
- 12 event-domain types;
- exact Decimal persistence policy;
- scaled-integer helpers;
- host/boot-safe clock abstraction;
- event/numeric/clock unit tests;
- final green CI run `35891870831`.

Artifact: `artifacts/stage_0/schema_v1.json`.

## Completed — TASK-005

PR #5, merge commit `544bf8ad0f4c04468035e0af9a4e260f3b39f187`.

Delivered:

- deterministic QCR1 raw frame log;
- exact source payload preservation;
- explicit write-vs-fsync durability semantics;
- payload/frame checksums;
- scan/replay helpers;
- safe torn-tail truncation;
- middle-corruption hard failure;
- final green CI run `35892726690`.

Artifact: `artifacts/stage_0/rawlog_report.json`.

## Completed — TASK-006

PR #6, merge commit `725e79e930534d3396bc399f2c7d4fa73af25bcc`.

Delivered:

- crash-safe raw segment sealing;
- checksum/length/frame/derived-metadata manifest integrity;
- atomic manifest publication;
- deterministic storage audit/recovery states;
- fault injection around every commit boundary;
- final green CI run `35893879796`.

Artifact: `artifacts/stage_0/storage_recovery_report.json`.

## Completed — TASK-007

PR #7, merge commit `2182268783293bc01b2d1ac5608e3f01de9877f1`.

Delivered:

- verified Hyperliquid public WebSocket protocol evidence;
- pinned `websockets==17.0.1`;
- exact raw application payload-byte capture;
- subscription/channel/heartbeat classification;
- bounded reconnect behavior;
- fake-server integration tests;
- third-party reuse register;
- final green CI run `35904060906`;
- **140 tests PASS** on Python 3.12 and 3.13.

Artifact: `artifacts/stage_0/hl_capture_probe.json`.

## Completed — TASK-008

PR #8, merge commit `069bddf1f8ef9aed1fc210bb46e690bc564cbb22`.

Delivered:

- bounded async capture queue with backpressure and no silent drops;
- exact TASK-007 frame → TASK-005 raw log persistence;
- fsync-based durable frame/byte accounting;
- deterministic segment IDs;
- TASK-006 seal/manifest handoff;
- graceful stop and bounded drain behavior;
- explicit producer/writer/append/sync/seal/cancellation failure states;
- network-free runtime validation CLI;
- end-to-end, backpressure, and fault tests;
- final green closeout CI run `35910694098`;
- **161 tests PASS** on Python 3.12 and 3.13.

Artifact: `artifacts/stage_0/recorder_smoke.json`.

## Completed — TASK-009

PR #9, merge commit `4470202c8030ab07acbf031d14968ff72bda2969`.

Delivered:

- strict labeled public-recorder runtime config;
- public-only runnable Hyperliquid recorder;
- host/boot/run identity;
- finite-duration and graceful signal stop path;
- storage audit CLI;
- systemd template and runbook;
- **173 tests PASS** on Python 3.12 and 3.13;
- strict mypy/Ruff/format PASS;
- real Hyperliquid public-only smoke run `35912388990`: **559 frames, 8/8 ACKs, 364893 durable bytes, queue HWM 1, CLEAN_DURABLE, audit VALID**;
- final network-independent closeout CI run `35912786539`;
- one-shot network workflow removed before merge.

Artifact: `artifacts/stage_0/live_capture_smoke.json`.

## Completed — TASK-010

PR #10, merge commit `a99b3667714a74bc38d5422b3214ee460034a6fd`.

Delivered:

- official/current Hyperliquid L2/BBO schema evidence;
- measured Unix-millisecond wire timestamp unit with semantic intentionally UNKNOWN;
- exact-Decimal L2Snapshot/BBO normalization;
- deterministic event IDs and serialization;
- complete raw QCR1 provenance;
- strict canonical BTC/ETH mapping;
- structured parse errors and NOT_APPLICABLE handling;
- crossed/unsorted source preservation with SUSPECT quality flags;
- QCR1 replay determinism;
- **193 tests PASS** on Python 3.12 and 3.13;
- Ruff/format/strict mypy PASS.

## Completed — TASK-011

PR #11, merge commit `b5fc231ad0631eb442a3c881ee868dc72106ecfd`.

Delivered:

- official/current Hyperliquid public trade schema evidence;
- measured Unix-millisecond wire timestamp unit;
- measured reconnect recent-trade replay: initial 30-trade batches and duplicate stable identities across connections;
- exact-Decimal 0..N Trade normalization;
- native A/B side preservation with aggressor semantics intentionally UNKNOWN;
- stable `trade_id=(time,coin,tid)`;
- occurrence-specific deterministic event IDs;
- complete raw QCR1 provenance;
- structured all-or-nothing errors;
- QCR1 replay/reconnect duplicate auditability;
- **222 tests PASS** on Python 3.12 and 3.13;
- Ruff/format/strict mypy PASS.

## Completed — TASK-012

PR #12, merge commit `9a6e4c801464b1a56036ae6f50c6fab9e7c1c966`.

Delivered:

- official/current activeAssetCtx/funding/mark/oracle evidence;
- live wire probe confirming string-valued context and no native timestamp;
- additive `FundingObservationKind.CURRENT` semantic correction;
- exact-Decimal funding/mark/oracle normalization;
- no fabricated exchange timestamp;
- complete raw provenance / QCR1 replay;
- **246 tests PASS** on Python 3.12 and 3.13;
- Ruff/format/strict mypy PASS.

## Completed — TASK-013

PR #13, merge commit `d850f2d54d02f47b05bfeab0d881ff76ab3275d7`.

Delivered:

- Stage-0 external reference source frozen as Binance USDⓈ-M BTCUSDT/ETHUSDT;
- current 2026 `/public` bookTicker + `/market` aggTrade routing;
- documented unsigned-integer SUBSCRIBE IDs;
- two unauthenticated public connections;
- exact raw capture + local availability timestamps;
- deterministic ReferenceBBO/ReferenceTrade normalization;
- `st=1` USD-M guard;
- QCR1 replay and fake-server coverage;
- final live adapter probe `35922113843`;
- final PR-head CI `35923167765`;
- **271 tests PASS** on Python 3.12 and 3.13;
- Ruff/format/strict mypy PASS.

## Completed — TASK-014

PR #14, merge commit `e6a4d2d2af6a14adbb23687e41183932731d6f4e`.

Delivered:

- one frozen-source raw-to-normalized dispatcher for Hyperliquid + Binance reference;
- explicit EVENTS / EMPTY / NOT_APPLICABLE / ERROR outcomes;
- same-host/boot monotonic causal replay;
- deterministic equal-timestamp tie-break;
- mixed-domain strict rejection;
- clock-order anomaly visibility;
- duplicate stable trade-ID counting without deduplication;
- deterministic canonical causal-record/report digests;
- two-venue QCR1 end-to-end replay;
- **288 tests PASS** on Python 3.12 and 3.13;
- Ruff/format/strict mypy PASS.

## Completed — TASK-015

PR #15, merge commit `03de66b0d5610de74fd24e8989c839e8067d93fc`.

Delivered:

- PyArrow 24.0.0 locked;
- explicit deterministic Parquet research schemas;
- exact string market numerics;
- full frame/control/error visibility;
- event/raw provenance checks;
- deterministic file/schema/report/bundle hashes;
- atomic non-overwriting publication;
- QCR1 → normalize → Parquet/readback evidence;
- **299 tests PASS** on Python 3.12 and 3.13;
- final PR-head CI `35927498144` PASS.

## Completed — TASK-016 / Stage-0 Data Gate

PR #16, merge commit `ed13f9054b290e04151bc1d9de15eddbe4434b5f`.

Real dual-source public mainnet evidence:

- workflow `35930416414`: **PASS**;
- **24,106** raw frames / **14,949,703** durable bytes;
- Hyperliquid: **464** raw frames, **8/8** ACKs;
- Binance: **23,642** raw frames, ACK IDs **1301/1302**;
- one host/boot causal domain;
- **24,345** normalized events;
- **0** normalization errors;
- deterministic Parquet counts reconciled exactly;
- final network-independent CI `35930608146`: **306 PASS** on Python 3.12 and 3.13; Ruff/format/strict mypy PASS.

**Stage-0 Data Gate: PASS.**

This validates the data/evidence pipeline only. Economic edge remains UNPROVEN.

## Completed — TASK-017

PR #17, merge commit `e59b390ff0a15180b1454819c8ea14c93bc56261`.

Delivered:

- deterministic model-free frontier math/audit/reporting;
- exact BBO/spread/movement/friction and L2 depth primitives;
- prospective real-data pilot;
- no model/alpha claim;
- derived target horizon: **50 seconds**;
- required valid non-overlapping windows: **2,952**;
- mathematical minimum observed support: **147,600 s ≈ 41 h**;
- final PR-head CI `35937250139`: **337 tests PASS** on Python 3.12 and 3.13; Ruff/format/strict mypy PASS.

Frontier Gate remains **NOT_EVALUATED**.

### Final TASK-018 Frontier Gate — PASS_FEASIBILITY

On **2026-09-26**, the deterministic campaign report reached the pre-registered adjudication floor and froze the first **2,952** valid non-overlapping 50-second windows.

Authoritative Gate checkpoint:

- campaign/report manifest SHA-256: `f82ba391ddaeac85ddb4787aec84d3cb85c17794101486c357cbb5bbd41f161c`;
- report SHA-256: `d2289bff1d2d3ffddc246456ff6ea9c6a4ae7663e1805d40cc0802e33891a3b2`;
- accepted segments: **182**;
- total valid windows available: **3,076**;
- adjudication windows: **2,952**;
- excluded candidate windows: **521**;
- q95 movement: **9.183776917709780722417361000 bps**;
- q50 known friction: **9.123151337258348319833680000 bps**;
- margin: **+0.060625580451432402583681000 bps**;
- q50 friction / q95 movement: `0.9933986222667796459142534313`;
- readiness: `READY_FOR_FRONTIER_ADJUDICATION`;
- decision: **`PASS_FEASIBILITY`**;
- adjacent non-zero sign agreement: `0.5278725824800910125142207053`;
- zero-move fraction: `0.1063685636856368563685636856`.

The pass is narrow: it establishes only economic plausibility of the 50-second movement region versus the currently known friction scenario. It does **not** establish predictability, positive expectancy, real account fees, own-order impact/slippage, submit-to-fill latency, capacity, maker economics, or funding-boundary cost.

Fee remains `SCENARIO`; latency and funding-boundary evidence remain `UNKNOWN`. The DKW planning count assumed IID; non-overlap reduces mechanical overlap but does not establish independence.

TASK-018 prospective scheduling was stopped after the Gate sample was frozen. Accepted and incomplete evidence remains immutable and preserved.

Artifact: `artifacts/stage_05/frontier_gate_50s.json`.

### Auxiliary retrospective research checkpoint

This track remains physically and semantically separate from the frozen TASK-018 adjudication, but can provide non-gating research context for later stages.

Merged provenance:

- PR #23: split prospective capture/processing;
- PR #24: non-gating retrospective archive planner/downloader;
- PR #25: deterministic checksum-reverified Binance 50-second retrospective analyzer.

Retrospective root: `/var/lib/quant-crypto-engine/retrospective`.

For **2026-08-01..2026-08-07**:

- deterministic source plan: **350** entries;
- Binance Data Vision: **14/14** BTCUSDT/ETHUSDT daily aggTrades archives verified, **14 manifests**, about **128 MiB**;
- Hyperliquid: **336** planned hourly BTC/ETH L2 objects remain unavailable locally because the official Requester Pays archive requires an authenticated AWS identity;
- all retrospective artifacts remain labeled `EXCLUDED_FROM_TASK_018_FRONTIER_GATE`.

Deterministic Binance trade-price context:

- BTCUSDT: **12,096 50-second windows**, q95 ≈ **6.8355 bps**;
- ETHUSDT: **12,096 50-second windows**, q95 ≈ **9.2205 bps**.

These retrospective trade-price statistics are not Hyperliquid BBO-mid evidence and were not substituted into the prospective Gate.

### Completed — TASK-019 / Stage-1 simulator foundation

PR #30 merged as `d963dd59c7e2fe9c873bfc61dd029875131dcbef`.

Delivered:

- causal quote/opportunity/policy contracts;
- no-trade and deterministic seeded randomized-direction controls;
- one shared taker executable-price accounting path;
- exact separation of fee, latency, impact and funding components;
- spread embedded in executable prices and not double-counted;
- UNKNOWN costs remain null rather than fabricated as zero;
- deterministic complete trial ledger/report + SHA-256;
- normalized BBO adapter and fixed-horizon opportunity builder;
- BTC PRIMARY / ETH REPLICATION separation;
- `artifacts/stage_1/simulator_contract.json`;
- `docs/research/simulator.md`.

Validation:

- pre-merge CI `36238838341`: Ruff/format/strict-mypy PASS, **389 tests PASS** on Python 3.12 and 3.13;
- post-merge CI `36238897281`: Ruff/format/strict-mypy PASS, **389 tests PASS** on Python 3.12 and 3.13.

TASK-019 establishes simulator/accounting infrastructure only. Predictability and positive net expectancy remain **UNPROVEN**.

## Completed — TASK-020 / Stage-2 protocol freeze

PR #32 merged as `b3568644c900d5e561597cd5c01b3c10ece0a720`.

Delivered:

- deterministic causal Stage-2 feature-row contract;
- verified Gate-source dataset builder;
- H1 `S2-H1-BINANCE-REF-5S-SIGN-V1`;
- H2 `S2-H2-HL-BBO-IMBALANCE-SIGN-V1`;
- fixed 50-second label horizon, 5-second H1 lookback and 2-second staleness limits;
- outcome-independent chronological DEVELOPMENT / SELECTION / untouched CONFIRMATION boundaries;
- no-trade and seed-provenanced randomized controls;
- frozen trial registry and champion-only confirmation rule;
- dependence-aware diagnostics and explicit no-optional-stopping rule;
- business-net boundary remains NOT_EVALUABLE while real account/execution costs are UNKNOWN;
- `artifacts/stage_2/signal_protocol.json`;
- `docs/research/stage2_signal_protocol.md`.

Frozen PRIMARY dataset:

- **3,259** BTC rows from **182** frozen Gate segments;
- dataset SHA-256: `3eeb0b405a9db439b7711b453ec9820707068bbfba855bf120124b79aa32b237`;
- DEVELOPMENT: **1,110** rows;
- SELECTION: **847** rows — H1-ready **783**, H2-ready **847**;
- untouched CONFIRMATION: **1,302** rows — H1-ready **1,225**, H2-ready **1,302**.

Validation:

- local full suite: **408 PASS** on Python 3.12.3;
- Ruff/format PASS;
- strict mypy PASS on **93 source files**;
- pre-merge CI `36248421789`: green;
- post-merge CI `36248457686`: green.

No H1/H2 candidate outcome was used to choose the frozen protocol or partitions.

### Pre-selection power-buffer amendment

Before TASK-021 candidate evaluation, a planning mismatch was corrected: the original
783/1,225 floors are directional-evaluable counts, but the original partitions were
sized only to feature-ready counts. Zero-direction labels are excluded from the
directional denominator.

Using only the already published Frontier zero-move fraction, frozen DKW error,
decision-time feature readiness, and label availability/timing metadata:

- conservative nonzero-label lower fraction: `0.8686314363143631436314363144`;
- buffered SELECTION support floor: **902**;
- buffered CONFIRMATION support floor: **1,411**;
- amended SELECTION start: `1790235572690884130`;
- amended CONFIRMATION start: `1790302269067780894`;
- DEVELOPMENT: **159 rows**;
- SELECTION: **1,123 rows**, H1 planning-ready **902**, H2 **962**;
- untouched CONFIRMATION: **1,977 rows**, H1 planning-ready **1,411**, H2 **1,515**;
- valid SELECTION labels crossing confirmation start: **0**.

No H1/H2 correctness, PnL, champion result, or confirmation candidate performance was
inspected. H1/H2 definitions and stopping rules are unchanged.

## Completed — TASK-021 / Registered H1/H2 selection

Frozen artifact: `artifacts/stage_2/selection_result.json`.

- report SHA-256: `e3403ef3eb6016040344dd8c17f4174b9190ca1a3aa5f5a59f54e1af7f7fb5a0`;
- selection rows: **1,123**;
- decision: **INCONCLUSIVE_SELECTION**;
- champion: **none**;
- confirmation opened: **false**.

H1 `S2-SEL-H1-V1`:

- directional-evaluable **644 < 783 required**;
- accuracy **54.0373%**;
- IID-reference p ≈ **0.02219**;
- dependence-adjusted lower bound ≈ **49.9821%**;
- mean partial-known-cost PnL ≈ **-74.0311** quote units at 1 BTC;
- failed support, dependence-adjusted, and economic filters.

H2 `S2-SEL-H2-V1`:

- directional-evaluable **930**;
- accuracy **58.3871%**;
- IID-reference p ≈ **1.7522e-7**;
- dependence-adjusted lower bound ≈ **54.8815%**;
- mean partial-known-cost PnL ≈ **-71.1355** quote units at 1 BTC;
- passed directional diagnostics but failed the required economic filter.

No confirmation outcome was opened. No registered feature, sign, threshold, or lookback was changed after the result.

## Completed — TASK-022 / Selection evidence remediation

Frozen artifact: `artifacts/stage_2/selection_remediation.json`.

- report SHA-256: `fec7cbb77fe67c672a2319fadee7e6a94f79fef013c16c6033b55fbb07f574d5`;
- decision: **STOP_REGISTERED_H1_H2_FAMILY**;
- old confirmation: **UNOPENED_AND_EXCLUDED**;
- historical data role: **development/diagnostics only, not confirmatory**.

H1 support attrition was decomposed as 1,123 total -> 1,059 feature-ready ->
744 nonzero/actionable -> 663 traded valid executable -> 644
directional-evaluable. Final directional-evaluable yield was about **57.35%**.

A conservative unchanged-H1 replication was calculated for transparency but **not
registered**:

- selection: **1,719 fresh rows**;
- confirmation: **2,688 fresh rows**;
- total: **4,407 fresh rows**.

The replication is not justified under the registered taker economics because H1
also failed the frozen partial-known-cost economic filter. H2 remains unpromoted
despite strong directional diagnostics because it failed the same economic filter.

## Completed — TASK-023 / 50-second economic family development

Artifacts:

- `artifacts/stage_2/economic_family_development.json`
  - SHA-256 `ae62dff1172ca7666b1119c4c8a0f1ca61757f428c30b66b73a208b34c2a3b67`
  - decision: **DEVELOP_REGULARIZED_LOGISTIC_BASELINE**
- `artifacts/stage_2/economic_logistic_development.json`
  - SHA-256 `285775b8febb226414bd838121f99b15b72d5b46edb13383b12398b8c80ccaf8`
  - decision: **STOP_LOGISTIC_DEVELOPMENT**

No bounded 50-second deterministic candidate produced positive DEV_B known-net
economics. The fixed L2 logistic baseline selected only one DEV_B trade, which was
negative. No fresh test evidence is justified for this 50-second family.

The old confirmation partition remains unopened/excluded.

## Completed — TASK-024 / longer-horizon development

Frozen decision artifact:

- `artifacts/stage_2/economic_300s_decision.json`
- SHA-256 `b36027ab6436258b4970e974280ee3669813c585d7deb96a29f00079aca12eb6`
- decision: **STOP_300S_FAMILY**

The 60/120/300s development context selected 300 seconds before Hyperliquid 300s
outcomes were evaluated. The frozen 300s deterministic family failed its economic /
support gate and the preregistered logistic fallback selected zero valid DEV_B trades
at both frozen score gates.

Old confirmation remains **UNOPENED_AND_EXCLUDED**. No fresh registered test evidence
was collected.

## Completed — TASK-026 / economic bottleneck adjudication

Frozen artifact:

- `artifacts/stage_2/economic_bottleneck_adjudication.json`;
- SHA-256 `4c90657accb99a0caff44336bbca091b887f99cd9caedada01fd15364b77b39b`;
- selected path: **PROSPECTIVE_DEVELOPMENT_EVIDENCE_EXPANSION**.

The strongest new 50s DEV_B candidate, E3, implied a taker-fee break-even of only
about **0.758 bps/side** on its observed mean gross edge. The rechecked published
tier-6 plus Diamond staking schedule context is **1.44 bps/side**, under which that
same mean remains negative before UNKNOWN latency, own-order impact/slippage, and
funding. Actual project-account fees remain UNKNOWN.

The 300s family remains negative/under-supported, while TASK-025 exposed only
24 positive full-feature targets at 50s and 6 at 300s. TASK-026 therefore selected
a fixed **72-hour public-only prospective DEVELOPMENT** collection. No new model/test
evidence was consumed and old confirmation remains **UNOPENED_AND_EXCLUDED**.

## TASK-027 protocol freeze checkpoint

Implementation is prepared, but the 72-hour campaign has **not started**. Capture is
forbidden until the protocol commit passes CI and is merged/deployed from `main`.

Frozen inputs:

- protocol: `artifacts/stage_2/development_campaign_protocol.json`,
  SHA-256 `1ab9a735f512dd301392ba568b49ebd0f1e80d676f073b3d502bf73d111bc1d3`;
- public transport profile: `config/runtime/stage2-development-public.json`,
  SHA-256 `8bf2a31ec634b475f1e3b559663bb35e16950c1c721ab73ddc5812cd6b1f03e1`;
- campaign root after merge:
  `/var/lib/quant-crypto-engine/stage2-development-campaign`.

The validated Stage-0 public recorder is reused as a transport superset. ETH and
Hyperliquid `activeAssetCtx` remain preserved raw but are explicitly excluded from
TASK-027 feature/target eligibility. Only Hyperliquid BTC L2/BBO/trades and Binance
BTCUSDT bookTicker/aggTrade are eligible.

## Current task

Read **[`tasks/TASK_027.md`](tasks/TASK_027.md)**.

TASK-027 freezes and runs one fixed-duration public-only DEVELOPMENT evidence
expansion on Aibo. It does not fit a new predictive model, open old confirmation,
use private/account data, or collect registered SELECTION/CONFIRMATION evidence.

## User actions currently required

No user action is required now.

TASK-018 scheduling remains quiesced. TASK-027 will use Aibo for a separately frozen
72-hour public DEVELOPMENT campaign only after its committed protocol is deployed.
The host is currently available; no credential, wallet, deposit, AWS, or account
action is required from the user.

If a future blocker cannot be bypassed safely through available tooling, document the blocker rather than weakening tests, evidence rules, or quality gates.

## Open decisions intentionally deferred

- Reference venue/feed frozen for Stage 0: **Binance USDⓈ-M BTCUSDT/ETHUSDT public bookTicker + aggTrade**.
- TASK-018 collection host is currently local Ubuntu WSL2; any future cloud/production VM/provider/region remains deferred.
- Production signing-key topology.
- Operational timeout/staleness/watchdog thresholds.
- Capital amounts/scaling ladder.
- Software license.

## Rules for future sessions

1. Read `STATUS.md` first.
2. Read the current task file.
3. Every coding task requires tests.
4. Require green relevant CI before merge.
5. Update `STATUS.md` after each completed task/gate/material decision.
6. Preserve failed experiments and UNKNOWN facts.
7. Never commit credentials/secrets.
8. Do not skip economic/safety gates.
9. Stop and document architectural conflicts instead of coding around them.
10. Prefer small correct commits over speculative breadth.
