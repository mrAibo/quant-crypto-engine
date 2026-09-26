# TASK-023 — Stage 2 New Economic Signal Family Design

## Status

**COMPLETE**

## Context

TASK-022 stopped the registered H1/H2 family.

H2 showed directional information on the exposed SELECTION sample but failed the
registered taker partial-known-cost economic filter. H1 was underpowered and also
economically negative.

The old Stage-2 confirmation partition remains unopened and is excluded from this
new family.

## Objective

Design one small, explicitly bounded new signal family whose target is executable
economic value after the frozen taker cost scenario, not directional hit rate alone.

Development may use already exposed/non-holdout evidence and clearly labeled
historical data. Any eventual registered test must use new prospective evidence
collected after the new protocol is frozen.

## Evidence roles

Allowed DEVELOPMENT evidence:

- completed Stage-2 DEVELOPMENT and SELECTION evidence;
- TASK-021/TASK-022 artifacts and diagnostics;
- existing checksum-verified Binance retrospective archives;
- additional historical public data if provenance and semantic limitations are
  explicit;
- a separately labeled development-only prospective sample if primary-market
  history is insufficient.

Forbidden test evidence during development:

- the old untouched Stage-2 CONFIRMATION partition;
- any future sample intended for the new family's SELECTION or CONFIRMATION.

Historical data is never a substitute for new prospective confirmation.

## Required work

1. Define the economic target/label directly from executable bid/ask accounting and
   the frozen taker cost scenario.
2. Quantify which observable decision-time variables can plausibly separate trades
   whose movement is large enough to overcome friction.
3. Keep the candidate family small and predeclare the multiple-testing budget.
4. Decide whether the next family is:
   - a new deterministic economic filter/rule family; or
   - a regularized logistic baseline justified by the development evidence.
5. Do not use LightGBM unless the simpler registered family later fails for a
   documented reason that nonlinear structure could address.
6. Freeze:
   - feature definitions and point-in-time semantics;
   - target and horizon;
   - model/rule form;
   - thresholds;
   - cost model;
   - selection/confirmation power and sample plan;
   - controls;
   - stopping/champion rule.
7. Write a machine-readable new-family protocol before any fresh test evidence is
   evaluated.
8. Define a fresh prospective collection boundary:
   - new SELECTION begins only after protocol freeze;
   - new CONFIRMATION is later and untouched until a champion exists.

## Historical-data rule

Use historical data aggressively for **development efficiency**, but never to claim
confirmation.

If Hyperliquid historical L2/BBO cannot reproduce native receive-time semantics, it
must remain explicitly limited development context. New prospective Hyperliquid +
Binance capture is authoritative for the registered test.

## Definition of Done

1. Old confirmation remains unopened/excluded.
2. New family has a bounded hypothesis/model registry.
3. Economic target is executable and cost-aware.
4. No fresh test data is inspected before protocol freeze.
5. Fresh SELECTION and CONFIRMATION sample requirements are committed.
6. Machine-readable protocol and derivation docs are committed.
7. Ruff/format/strict mypy/pytest are green on Python 3.12 and 3.13.
8. STATUS.md points to the fresh prospective campaign task.

## Do Not Build

- old-confirmation evaluation;
- broad feature sweeps;
- unrestricted hyperparameter search;
- LightGBM by default;
- Jev/GPT runtime;
- maker simulation;
- OMS/signing/orders;
- private/account capture;
- capital deployment.


## Final result — 2026-09-26

TASK-023 is complete for the 50-second new economic family.

Development source:

- 1,282 exposed/non-holdout rows;
- chronological DEV_A/DEV_B = 641/641;
- source SHA-256
  `64f3bcf87b65f62b438f204abe06483b44c1314eb9c82546ca238fba75710bf9`.

Deterministic development result:

- no candidate had positive DEV_B mean/median known-net economics;
- decision: `DEVELOP_REGULARIZED_LOGISTIC_BASELINE`;
- artifact: `artifacts/stage_2/economic_family_development.json`;
- SHA-256: `ae62dff1172ca7666b1119c4c8a0f1ca61757f428c30b66b73a208b34c2a3b67`.

Fixed logistic development result:

- economic probability hurdle:
  `0.670096216343838670184142236545596019441226490180723430160101`;
- DEV_A selected 0 / 547 eligible;
- DEV_B selected 1 / 484 eligible;
- selected DEV_B trade known-net PnL: `-129.9582`;
- decision: `STOP_LOGISTIC_DEVELOPMENT`;
- artifact: `artifacts/stage_2/economic_logistic_development.json`;
- SHA-256: `285775b8febb226414bd838121f99b15b72d5b46edb13383b12398b8c80ccaf8`.

No fresh test evidence is justified for the 50-second family.

Changing horizon is a new development family. Continue with
`tasks/TASK_024.md`.
