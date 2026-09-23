# Architecture Decisions

This file records decisions that should not be casually reopened in later chats or coding sessions.

## ADR-001 — Evidence-first development

**Decision:** Build the evidence recorder/research path before the production bot.

**Reason:** Architecture alone does not create alpha. The project must falsify the economic hypothesis before large production investment.

## ADR-002 — Python 3.12+ layered monolith

**Decision:** Use Python 3.12+ and a layered/modular monolith. Separate watchdog infrastructure is the deliberate later exception.

**Reason:** Optimize for testability, development speed, and shared research/live code before introducing distributed complexity.

## ADR-003 — Hyperliquid is a candidate, not a dogma

**Decision:** Hyperliquid remains the initial execution candidate. BTC is primary; ETH is replication. One external reference feed is included.

**Reason:** Venue suitability and edge must be measured. No claim that Hyperliquid/BTC is inherently easier or profitable.

## ADR-004 — Taker-only first

**Decision:** Initial economic validation uses conservative taker execution. Maker economics are a later live-measurement workstream.

**Reason:** Offline maker fills require queue/adverse-selection assumptions that are easy to overstate.

## ADR-005 — Small model sequence

**Decision:** deterministic rules → regularized logistic regression → optional LightGBM.

**Reason:** Minimize data snooping and overfitting. Complexity must purchase measurable incremental information.

## ADR-006 — Runtime AI scope

**Decision:** GPT is not part of runtime v1. Jev gets at most one initial, separately gated hypothesis: rank/veto bad candidate trades better than deterministic and classical controls.

**Reason:** AI is optional evidence, not a prerequisite or architectural dependency.

## ADR-007 — Autonomy is not self-modification

**Decision:** Approved production versions may trade unattended, reconnect, reconcile, de-risk, halt, and alert. They may not rewrite strategy code, raise hard limits, increase capital, or deploy new models automatically.

## ADR-008 — Production safety principles

**Decision:** Intent-before-send durability, deterministic order identity, no blind retry of ambiguity, reconciliation-before-resume, latched hard halts, and an independent watchdog are mandatory before unattended live operation.

## ADR-009 — Thresholds are derived where possible

**Decision:** Do not hard-code arbitrary 14/30/90-day stages, 2,000-trade gates, or fixed Sharpe deltas when a power/economic derivation is possible.

**Reason:** Calendar duration is an output of evidence rate and required power, not a design preference.

## ADR-010 — No production execution engineering before Gate 1

**Decision:** No production signer/OMS/watchdog deployment until the first economic GO/NO-GO passes. Pure interfaces or simulations may be designed earlier only when they directly support research and do not create a live path.
