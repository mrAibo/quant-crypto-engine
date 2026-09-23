# Stage 1 — Minimal Shared Simulator

## Objective

Build the smallest event-driven simulator that shares the future strategy/risk/ledger contracts and can falsify the frozen strategy family without production exchange code.

## Initial capabilities

- chronological event replay by availability;
- explicit clock supplied by the runner;
- feature → strategy → risk → intent contracts;
- taker IOC depth walk;
- partial fills;
- fees/funding;
- account/PnL ledger;
- latency scenarios;
- one active position per instrument initially;
- deterministic replay/golden tests;
- future-poisoning/no-lookahead tests.

## Forbidden scope

No production signer, durable live OMS, distributed services, maker queue simulator, portfolio optimizer, or multi-venue execution.
