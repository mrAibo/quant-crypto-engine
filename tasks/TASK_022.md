# TASK-022 — Stage 2 Selection Evidence Remediation

## Status

**COMPLETE**

## Context

TASK-021 produced the immutable registered decision INCONCLUSIVE_SELECTION.

The result does not authorize opening the existing confirmation partition.

H2 had sufficient directional support and strong directional diagnostics but failed the frozen partial-known-cost economic filter. H1 had only 644 directional-evaluable rows against the required 783 and also failed the dependence-adjusted and economic filters on the observed selection sample.

## Objective

Adjudicate the evidence-remediation path without reusing or peeking at the untouched confirmation partition and without retroactively changing the completed H1/H2 selection trials.

The task must decide, from the frozen TASK-021 result and non-holdout evidence, whether there is a defensible fresh-evidence experiment worth collecting. If not, stop this registered family.

## Binding rules

1. Preserve TASK-021 exactly; no rerun, threshold change, sign reversal, alternate H1 lookback, or H3 under the same trial family.
2. Do not open the existing confirmation partition.
3. H2 remains a registered selection failure under taker partial-known-cost economics; do not promote it on directional accuracy alone.
4. Any continuation of H1 must be a **new registered trial on fresh evidence**, not optional continuation of the completed selection sample.
5. A new trial must power for:
   - feature availability;
   - nonzero/actionable H1 feature rate;
   - valid/nonzero outcome rate;
   - dependence/effective-sample loss.
6. Any fresh selection evidence must be chronologically separate from its own future confirmation evidence.
7. Existing UNKNOWN real-world costs remain UNKNOWN and cannot be zeroed.
8. No model fitting or broad feature search in this task.

## Required work

1. Explain the H1 support attrition from 1,059 feature-ready to 663 traded and 644 directional-evaluable rows without changing H1.
2. Derive a conservative fresh-evidence sample requirement if an unchanged H1 replication is still scientifically/economically justified.
3. Quantify the selection economic gap using the frozen partial-known-cost result, without treating it as full business-net economics.
4. Decide one of:
   - REGISTER_FRESH_H1_REPLICATION;
   - STOP_REGISTERED_H1_H2_FAMILY;
   - INCONCLUSIVE_REMEDIATION if required non-holdout evidence is missing.
5. If fresh H1 replication is registered:
   - define its sample/power plan before collecting;
   - define a new chronological fresh selection and fresh confirmation scheme;
   - preserve the old confirmation partition unopened and excluded.
6. Commit a machine-readable remediation artifact and all derivations/tests.

## Definition of Done

1. TASK-021 remains immutable.
2. Old confirmation remains unopened.
3. H2 is not promoted.
4. Any H1 continuation is a new registered trial with a fresh-evidence plan.
5. The remediation decision and derivation are deterministic and source-backed.
6. Ruff/format/strict mypy/pytest are green on Python 3.12 and 3.13.
7. STATUS.md identifies either the fresh evidence campaign or the registered-family stop.

## Do Not Build

- confirmation evaluation;
- logistic regression;
- LightGBM;
- alternate H1 lookbacks;
- threshold sweeps;
- H3;
- Jev/GPT runtime;
- maker simulation;
- OMS/signing/orders;
- private/account capture;
- capital deployment.


## Final result — 2026-09-26

TASK-022 is complete.

Machine-readable remediation artifact:

- `artifacts/stage_2/selection_remediation.json`
- SHA-256 `fec7cbb77fe67c672a2319fadee7e6a94f79fef013c16c6033b55fbb07f574d5`
- decision: `STOP_REGISTERED_H1_H2_FAMILY`
- old confirmation: `UNOPENED_AND_EXCLUDED`

H1 attrition:

- 1,123 total rows
- 1,059 feature-ready
- 744 nonzero/actionable decisions
- 663 traded valid executable opportunities
- 644 directional-evaluable outcomes
- 57.35% final directional-evaluable yield

Counterfactual unchanged-H1 fresh support, not registered:

- 1,719 selection rows
- 2,688 confirmation rows
- 4,407 total rows

The replication is not registered because H1 also failed the frozen
partial-known-cost economic filter. H2 remains unpromoted because it also failed that
economic filter despite strong directional diagnostics.

Historical data is approved only for diagnostics/development of a new family.
Registered selection and confirmation for any new family must use fresh prospective
evidence collected after its protocol freeze.

Next work package: `tasks/TASK_023.md`.
