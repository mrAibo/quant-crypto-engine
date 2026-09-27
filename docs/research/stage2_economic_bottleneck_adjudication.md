# Stage 2 Economic Bottleneck Adjudication

## Scope

TASK-026 consumes only completed, already exposed Stage-2 artifacts. It does not
open old confirmation, collect new model/test evidence, or fit another predictive
family.

Decision artifact:

- `artifacts/stage_2/economic_bottleneck_adjudication.json`
- SHA-256
  `4c90657accb99a0caff44336bbca091b887f99cd9caedada01fd15364b77b39b`

Selected primary path:

**PROSPECTIVE_DEVELOPMENT_EVIDENCE_EXPANSION**

The next work package is a fixed 72-hour, public-only DEVELOPMENT collection.

## Repeated taker bottleneck

The registered H1/H2 family failed frozen partial-known-cost economics:

- H1 mean: about `-74.03` quote units;
- H2 mean: about `-71.14` quote units.

The bounded 50-second family also remained negative. Its strongest new DEV_B
candidate by mean, E3, had:

- 77 valid trades;
- mean gross quote PnL `12.7922077922...`;
- mean fee under the 4.5 bps/side scenario `75.9507370130...`;
- mean partial-known-cost PnL `-63.1585292208...`.

The implied taker-fee break-even for that observed mean gross edge is only
`0.7579246407...` bps per side.

## Fee sensitivity

The Hyperliquid fee documentation was rechecked on 2026-09-27. For validator-operated
perpetuals, the published tier-6 taker rate is 2.4 bps and the published Diamond
staking discount is 40%, giving a documented volume+staking context of 1.44 bps/side
before account-specific referral or product modifiers.

This is **not** the project account's observed fee tier. The actual project-account
rate remains UNKNOWN and must not be inferred from the published table.

Even using 1.44 bps/side as sensitivity context, the same E3 mean would remain about
`-11.5120` quote units before latency, own-order impact/slippage, and funding.
Therefore account-cost resolution remains necessary later, but it is deferred rather
than selected as the primary TASK-026 path.

Source: <https://hyperliquid.gitbook.io/hyperliquid-docs/trading/fees>

## Longer-horizon and microstructure evidence

The 300-second family did not rescue taker economics. The strongest new DEV_B
candidate by mean, E300_2, had only 9 valid trades and mean partial-known-cost PnL
of about `-39.90` quote units. The registered logistic fallback selected zero
valid DEV_B trades at both score gates.

TASK-025 then exposed a different bottleneck: insufficient full-feature positive
target support for the frozen eight-feature family:

- 50s: 409 valid targets, 24 positive / 385 nonpositive;
- 300s: 21 valid targets, 6 positive / 15 nonpositive.

This makes further feature expansion inappropriate before more DEVELOPMENT evidence
exists.

## Path adjudication

### Selected: prospective DEVELOPMENT evidence expansion

A fixed-duration public-only campaign directly addresses the observed support
shortfall without assuming lower private-account costs and without adding execution
mechanics.

Frozen planning parameters for the next task:

- duration: 72 hours;
- primary support horizon: 50 seconds;
- role: DEVELOPMENT only;
- stopping rule: fixed duration, no outcome-dependent extension;
- private Hyperliquid account access: not required;
- AWS requester-pays access: not required.

The committed Stage-2 protocol places the first source decision at
`1790212930125341960` and the untouched confirmation boundary at
`1790302269067780894`, a pre-confirmation exposure span of about **24.82 hours**.
Over that span TASK-025 exposed 1,282 rows, 409 valid full-feature targets, and
24 positive targets.

Scaling those **observed wall-time rates** to 72 hours gives planning estimates of
about **3,719 rows**, **1,187 valid targets**, and **70 positive targets**. The
5,184 ideal 50-second intervals over 72 hours are retained only as a cadence ceiling,
not as an observed-row count. These projections are planning estimates only, not
gates or profitability claims.

### Deferred: actual account-cost resolution

The actual project-account fee tier remains UNKNOWN and must be measured before any
real economic deployment. It is not the primary next path because the documented
tier-6 + Diamond volume/staking context used above still does not rescue the best
observed 50s candidate, and fee resolution does not solve the current microstructure
sample-support shortage. Account-specific modifiers are deliberately not assumed.

### Deferred: maker-execution research

Maker research remains a separate future gate. Introducing it now would add
unmeasured fill probability, queue position, adverse selection, cancellation, and
maker-fee/rebate state. No maker assumption is mixed into the completed taker
experiments.

## Preserved boundaries

- old Stage-2 confirmation: **UNOPENED_AND_EXCLUDED**;
- actual project-account fee: **UNKNOWN**;
- latency: **UNKNOWN**;
- realized own-order slippage/impact: **UNKNOWN**;
- funding boundaries: **UNKNOWN**;
- maker economics: **UNKNOWN**;
- live trading, private capture, OMS/signing, and capital deployment: **FORBIDDEN**.
