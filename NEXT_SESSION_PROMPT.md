# Prompt for the next ChatGPT session

Continue the project **mrAibo/quant-crypto-engine** autonomously from the repository
source of truth.

At session start, verify the latest `main` and prefer it over chat memory.

Current state:

- phase: **Stage 2 — Signal-Existence Dataset and Falsification Protocol**
- current task: **TASK-026 — Stage 2 Economic Bottleneck Adjudication**
- TASK-001 through TASK-025 are complete
- old Stage-2 confirmation: **UNOPENED_AND_EXCLUDED**
- live trading / OMS / signing / capital deployment: **FORBIDDEN**
- no fresh TASK-025 validation or registered test campaign was started
- no user action is currently required

Read in this order:

1. `HANDOFF.md`
2. `STATUS.md`
3. `tasks/TASK_026.md`
4. `artifacts/stage_2/microstructure_decision.json`
5. only then inspect implementation/evidence as needed

Latest completed decision:

- TASK-025: **STOP_MICROSTRUCTURE_FAMILY**
- registry SHA-256:
  `d5024ce6cb16c0d3dcce5b65f3f62f6d577b971d3bda7c8342ab67aaa100b130`
- decision SHA-256:
  `6355dd1295ab156757e091191ee686f6f9e63708a3bb556e03611b25285f7172`
- 50s: 1,282 rows -> 479 full-feature -> 409 valid targets ->
  **24 positive / 385 nonpositive**
- 300s: 215 rows -> 57 full-feature -> 21 valid targets ->
  **6 positive / 15 nonpositive**
- prior six-feature DEV_B exposure means all pre-cutoff microstructure evidence is
  development-only and cannot be reused as independent validation

TASK-026 goal:

Choose exactly one primary next path before any further predictive-family work:

1. expand DEVELOPMENT evidence (historical requester-pays Hyperliquid L2 if
   properly accessible/provenanced, otherwise a fixed prospective development-only
   campaign);
2. resolve actual Hyperliquid account-specific fee evidence;
3. open a separately registered maker-execution research gate.

Do not consume new model/test evidence while adjudicating. Preserve UNKNOWN facts,
negative experiments, old confirmation, and all economic/safety gates.

Every code change requires tests and green CI before merge. Update STATUS.md,
HANDOFF.md, and NEXT_SESSION_PROMPT.md after the material decision.
