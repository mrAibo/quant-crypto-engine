# Evidence Policy

## Purpose

Prevent unsupported facts, lookahead, silent data gaps, and optimistic execution assumptions from becoming strategy evidence.

## Fact status

Every venue/model/API fact relevant to economics or safety must be one of:

- `VERIFIED`: backed by a retained primary source or controlled observation.
- `UNKNOWN`: not yet established strongly enough for dependent claims.

Later Stage 0 will formalize this in `config/evidence.yaml` with source, retrieval time, effective period, verification scope, artifact, limitations, and re-verification trigger.

## Data rules

- Raw capture is immutable.
- Normalized data must reference raw evidence.
- Exchange timestamp and local receive timestamp are distinct.
- Missing exchange timestamps remain missing; precision is never invented.
- Reconnect/resync restores current usability but does not erase the historical gap.
- Late backfill cannot repair the information set of an earlier trading decision.
- Invalid intervals are explicit and machine-readable.

## Economic accounting rules

Maintain one executable P&L ledger.

- If modeled fills walk bid/ask depth, do not subtract spread again.
- If latency changes the book used for execution, do not add a second generic latency fee.
- Funding is applied only at verified payment boundaries.
- Operating/API costs are reported separately and allocated exactly once.
- Unsupported execution behavior is not silently treated as zero cost.

## Research rules

- Pilot/development/confirmation periods are chronological and explicit.
- Confirmation is protected from exploratory tuning.
- Failed variants remain in the trial registry.
- Overlapping labels and autocorrelation are accounted for.
- Multiple testing must be tracked.
- A failed champion does not authorize testing runners-up on the same holdout.
- Win rate is reported but is not the selection objective.
