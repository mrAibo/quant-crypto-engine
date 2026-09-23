# TASK-002 — Implement the Evidence Contract

## Status

`PENDING`

## Objective

Create the first machine-readable evidence policy so venue/API facts are never silently promoted from assumption to verified input.

## Planned files

- `config/evidence.yaml`
- `src/cryptobot/evidence/contract.py`
- `docs/evidence_sources.md`
- `tests/unit/test_evidence.py`
- `artifacts/stage_0/evidence_report.json`

## Scope

Define and validate at least:

- stable `fact_id`;
- narrow claim;
- `VERIFIED` / `UNKNOWN` status;
- verification scope;
- primary source/reference;
- retrieval/observation time;
- effective period;
- verification artifact;
- limitations;
- re-verification trigger.

Seed the required fact groups for fees, funding, timestamps, public feed semantics, historical-data availability, credential capabilities, order identity/lookup, safety primitives, and execution unknowns.

## Tests

- `VERIFIED` fact without supporting source/scope is rejected;
- `UNKNOWN` fact may omit a value without inventing one;
- stale/reverification-due facts are flagged;
- unknown fields are rejected;
- duplicate fact IDs are rejected.

## Definition of Done

Evidence report is reproducible and all safety/economic facts required by later stages are either explicitly verified or explicitly unknown.
