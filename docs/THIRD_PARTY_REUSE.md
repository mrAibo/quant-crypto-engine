# Third-Party Reuse Register

This file records external implementation influence so later reviews can distinguish copied code, adapted implementation patterns, protocol provenance, and original project code.

## Policy

- Prefer mature, licensed implementations for protocol details and low-level mechanics.
- Copy source only when the license permits it and the copied portion is clearly identified.
- Prefer adapting small patterns behind this project's interfaces over importing whole trading systems.
- Never treat a public trading repository as evidence of profitability.
- Record an exact upstream commit/tag whenever a code-level implementation pattern is used.
- If license status is unclear, do not copy code; use only independently reimplemented ideas/protocol facts.

## Current register

| Component | Upstream | Pin | License / status | Reuse type | Copied verbatim? | Notes |
|---|---|---|---|---|---|---|
| Hyperliquid WebSocket protocol semantics | `hyperliquid-dex/hyperliquid-python-sdk` | `2fdb18f9517675ea03695a0962bd19eece9c83f0` | Official Hyperliquid SDK; license must remain verified before any source copying | Protocol/reference implementation review | No | TASK-007 uses endpoint/subscription/channel/heartbeat behavior as protocol evidence. Raw adapter implementation is project-specific. |
| Hyperliquid WebSocket documentation | Hyperliquid GitBook | retrieved 2026-09-23 | Documentation | Protocol provenance | No | Mainnet endpoint, subscribe/ack example, heartbeat behavior, and IP WebSocket limits. |
| Jev architecture patterns | `buberlo/jev-trader` | pin when/if implementation reuse starts | MIT previously verified; reverify before copying | Architecture pattern only so far | No | Model interprets; deterministic code calculates and applies policy/risk. No Jev runtime work before its gate. |
| Hyperliquid/Jev live-bot patterns | `aowang-ai/jev-trade` | pin when/if implementation reuse starts | MIT previously verified; reverify before copying | Pattern review only so far | No | Potential later execution/WS operational reference; no code copied into Stage 0. |
| Research infrastructure patterns | `OpenByteInc/QuantDinger` | pin when/if implementation reuse starts | Apache-2.0 previously verified; reverify before copying | Pattern review only so far | No | Selective infrastructure ideas only; project is not forked from QuantDinger. |
| Jev negative-control research | `cristiancolon/jev-hft` | pin when/if implementation reuse starts | License unclear in prior review | Research evidence/pattern only | No | Never copy source unless license becomes explicit. |

## TASK-007 decision

The Hyperliquid raw public WebSocket adapter is **not** copied from an existing trading bot.

We intentionally reuse:

- official subscription/message semantics;
- official SDK behavior as a reference implementation;
- a mature third-party WebSocket transport library instead of hand-implementing RFC 6455.

We implement ourselves:

- raw-frame preservation into the TASK-005 format;
- capture metadata integration;
- acknowledgment tracking;
- reconnect/backoff state;
- channel routing diagnostics;
- failure semantics and tests;
- integration boundary with later TASK-008 recorder supervision.

