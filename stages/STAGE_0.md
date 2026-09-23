# Stage 0 — Evidence Contract and Market-Data Recorder

## Objective

Create a trustworthy, replayable, timestamped evidence base for BTC/ETH on Hyperliquid plus one external reference feed.

## Scope

Stage 0 includes:

- repository/quality bootstrap;
- evidence contract;
- strict recorder/instrument configuration;
- immutable event schemas and exact numeric rules;
- append-only raw capture;
- Hyperliquid public adapters;
- external reference adapter;
- causal normalization/readback;
- crash-safe Parquet materialization;
- data-quality and latency reports;
- fault injection;
- retention/backup/restore verification;
- final data-gate audit.

## Binding constraints

- No trading credentials are required.
- No strategy optimization.
- No order signing or OMS.
- No Jev/GPT integration.
- No maker queue model.
- Every injected failure must produce either complete recovery or an explicit invalid interval.

## Work-package sequence

`S0-WP01` through `S0-WP20` are represented by the task files under `tasks/` and tracked in `STATUS.md`.

## Exit

Stage 0 ends only with an explicit Data Gate outcome and a frozen pilot manifest usable by Stage 0.5.
