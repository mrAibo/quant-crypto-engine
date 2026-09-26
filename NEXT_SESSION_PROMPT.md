# Prompt for the next ChatGPT session

Continue the project **mrAibo/quant-crypto-engine** autonomously from the repository
source of truth.

Authoritative checkpoint:

- branch: `main`
- commit: `755adce9213c62e7dbbbae30a041479fc375e030`
- current phase: Stage 2 — Signal-Existence Dataset and Falsification Protocol
- current task: **TASK-025 — Stage 2 Bounded Microstructure Economic Development**
- TASK-001 through TASK-024 are complete
- PR #38 is merged
- post-merge CI run `36273758772` succeeded
- old Stage-2 confirmation is **UNOPENED_AND_EXCLUDED**
- live trading is **FORBIDDEN**
- no user action is currently required

Start by reading, in this order:

1. `HANDOFF.md`
2. `STATUS.md`
3. `tasks/TASK_025.md`

Then inspect the repository and the connected Aibo host only as needed and continue
TASK-025 without asking me routine clarifying questions.

Key TASK-025 rules:

- use only exposed DEVELOPMENT evidence initially;
- build point-in-time causal features only:
  top-5 depth imbalance, Hyperliquid 5s aggressive trade-flow imbalance, Binance 5s
  aggressive trade-flow imbalance, Hyperliquid 5s return, Binance 5s return,
  cross-venue 5s return gap, spread, and benchmark BBO imbalance;
- source observations must be available at or before the decision cursor;
- missingness must remain explicit;
- horizons are limited to the already developed 50s and 300s budget;
- freeze the feature/model/horizon budget before DEV_B outcomes are inspected;
- economic evaluation must use executable Hyperliquid bid/ask plus the frozen
  4.5 bps/side fee scenario;
- latency, own-order impact/slippage, boundary funding, and actual account fee tier
  remain UNKNOWN;
- do not open the old confirmation partition;
- do not start a fresh registered test campaign unless DEVELOPMENT first passes;
- no broad feature mining, no post-DEV_B feature/threshold additions, no LightGBM,
  no Jev/GPT runtime, no maker simulation, no OMS/signing/orders, no private/account
  capture, and no capital deployment;
- every code change requires tests;
- require green relevant CI before merge;
- update STATUS.md and HANDOFF.md after material decisions;
- preserve failed experiments and negative results.

Use GitHub as the source of truth and the connected Remote Desktop Commander host
`Aibo` for local evidence/implementation work when needed. Do not rely on chat
memory if it conflicts with the repository.

Continue until TASK-025 reaches its deterministic DEVELOPMENT decision
(`FREEZE_MICROSTRUCTURE_FAMILY` or `STOP_MICROSTRUCTURE_FAMILY`) or until a
genuine external blocker/human gate is reached.
