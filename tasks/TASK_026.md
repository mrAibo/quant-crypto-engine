# TASK-026 — Stage 2 Economic Bottleneck Adjudication

## Status

**COMPLETE**

## Context

TASK-021 through TASK-025 repeatedly found signal information but failed to establish
positive taker economics under the frozen 4.5 bps/side fee scenario.

TASK-025 stopped before fitting the full eight-feature microstructure model because
target-class support was insufficient.

## Objective

Choose the next evidence path before any further signal/model expansion.

The project must not continue broad feature mining while the dominant economic
bottleneck remains unresolved.

## Candidate paths to adjudicate

1. **Development evidence expansion**
   - obtain substantially more development-only microstructure evidence;
   - prefer official historical Hyperliquid L2 archive if requester-pays access can
     be configured and provenance is complete;
   - otherwise define one fixed-duration prospective DEVELOPMENT-only campaign;
   - any later validation/test sample must still be separate and fresh.

2. **Actual account-cost resolution**
   - measure/verify the project account's actual Hyperliquid fee tier;
   - keep latency, impact/slippage and funding UNKNOWN until separately measured;
   - do not substitute a hypothetical lower fee for observed account evidence.

3. **Separate maker-execution research gate**
   - only as a separately registered research package;
   - do not mix maker assumptions into the completed taker experiments;
   - no live orders or capital deployment.

## Required decision

Commit exactly one next primary path, with evidence requirements and human/external
dependencies made explicit.

Do not start a new predictive family before this decision is complete.

## Preserved constraints

- old Stage-2 confirmation remains **UNOPENED_AND_EXCLUDED**;
- no LightGBM or broad feature search;
- no Jev/GPT runtime;
- no OMS/signing/orders;
- no private/account capture unless TASK-026 explicitly selects the account-cost
  evidence path and defines the required human authorization;
- no live trading or capital deployment.

## Definition of Done

1. Economic bottleneck is quantified from completed artifacts.
2. One primary next path is selected.
3. Any required user action (AWS requester-pays access, Hyperliquid account access,
   etc.) is stated explicitly only if truly necessary.
4. No new model/test evidence is consumed during adjudication.
5. STATUS.md / HANDOFF.md / NEXT_SESSION_PROMPT.md are updated.
6. Green CI before merge.

## Final result — 2026-09-27

TASK-026 is complete.

Decision artifact:

- `artifacts/stage_2/economic_bottleneck_adjudication.json`
- SHA-256
  `4c90657accb99a0caff44336bbca091b887f99cd9caedada01fd15364b77b39b`
- selected primary path:
  **PROSPECTIVE_DEVELOPMENT_EVIDENCE_EXPANSION**

The best new 50s deterministic DEV_B candidate, E3, requires an implied taker-fee
break-even of about `0.758 bps/side` on its observed mean gross edge.

The rechecked published tier-6 plus Diamond staking schedule context is
`1.44 bps/side`, under which the same E3 mean remains negative before latency,
own-order impact/slippage, and funding. The actual project account fee remains
UNKNOWN.

The 300s family remains negative and under-supported. TASK-025 also has insufficient
positive full-feature target support: 24 positives at 50s and 6 at 300s.

Therefore the next bounded package is `tasks/TASK_027.md`: a fixed 72-hour,
public-only prospective DEVELOPMENT collection with no outcome-dependent extension.

Old confirmation remains **UNOPENED_AND_EXCLUDED**. No new predictive/model/test
evidence was consumed in TASK-026. No private account access, AWS credentials,
wallet, capital, or other user action is required now.
