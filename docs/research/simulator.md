# Stage 1 minimal shared simulator

## Purpose

TASK-019 adds the smallest deterministic simulator/accounting layer needed before signal
falsification. It is not a production trading path and it is not a strategy optimizer.

The Frontier Gate only established that the 50-second BTC movement region can clear the
currently known friction scenario at q95. The simulator must therefore preserve uncertainty
instead of turning that result into an assumed edge.

## Causal policy boundary

Policies receive a `DecisionContext` containing the current executable quote and only history
whose receive timestamps are at or before the decision cursor in the same host/boot causal
domain. Future history and cross-boot monotonic comparisons are rejected.

The policy protocol exposes only deterministic domain inputs and an `ABSTAIN/LONG/SHORT`
decision. It has no network, exchange, filesystem, wall-clock, GPT, or Jev dependency.

## Taker execution and costs

Stage 1 uses executable top-of-book prices:

- LONG: buy at the entry ask, sell at the exit bid;
- SHORT: sell at the entry bid, buy at the exit ask.

The spread is therefore already embedded in the two execution prices. It is not added again as
a separate cost.

Fees, latency, impact/slippage, and funding are separate `CostInput` components. Each is
classified as `OBSERVED`, `SCENARIO`, or `UNKNOWN`. An `UNKNOWN` component must have a null
bps value; the simulator refuses to fabricate zero. For a traded trial with any unknown cost,
`known_net_pnl` is reported but `business_net_pnl` remains null.

The current 4.5 bps/side taker fee can be represented as a SCENARIO. Actual project-account fee
tier, submit-to-fill latency, own-order impact/slippage, and boundary-aligned funding remain
UNKNOWN until separately measured.

## Trial ledger

Every supplied opportunity produces exactly one ledger entry:

- `INVALID` for unusable/missing/stale/gapped evidence;
- `NO_TRADE` for an explicit abstention;
- `TRADED` for LONG/SHORT controls or later frozen policies.

Ledger/report serialization uses exact Decimal strings, deterministic JSON ordering, and
SHA-256.

## Controls

`NoTradePolicy` exercises the exact same opportunity/accounting path while producing no
positions or costs.

`RandomizedDirectionPolicy` uses SHA-256 of the explicit integer seed plus immutable
opportunity/event identity. It is stateless and repeatable; the seed is included in report
provenance.

## Deliberate limits

TASK-019 does not define a predictive feature set, fit logistic regression/LightGBM, simulate
maker queue position, call Jev/GPT, create an OMS, access private/account endpoints, or deploy
capital.

Those are later gated work packages. Stage 1 only creates the shared deterministic substrate
needed to falsify candidate signals without causal or accounting shortcuts.
