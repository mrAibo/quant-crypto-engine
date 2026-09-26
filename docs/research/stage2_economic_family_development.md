# Stage 2 Economic Family Development — 50s

## Scope

TASK-023 used only already exposed/non-holdout evidence. The old Stage-2 confirmation
partition remained unopened and excluded.

Development source:

- 1,282 causal BTC rows before the old confirmation boundary;
- source cache SHA-256:
  `64f3bcf87b65f62b438f204abe06483b44c1314eb9c82546ca238fba75710bf9`;
- chronological DEV_A / DEV_B split: 641 / 641 rows;
- executable economics: Hyperliquid bid/ask plus frozen 4.5 bps/side fee scenario;
- latency, own-order impact/slippage, funding, and actual account fee tier remain UNKNOWN.

## Deterministic development family

The bounded registry contained exactly five candidates:

- E0 H2 baseline;
- E1 strong H2 imbalance;
- E2 H2 + Binance sign agreement;
- E3 H2 + sign agreement + strong Binance 5s move;
- E4 sign agreement + strong imbalance + tight spread.

Thresholds were derived only from DEV_A feature distributions.

No candidate had positive DEV_B mean or median known-net economics.

Best DEV_B mean among the new deterministic candidates was E3:

- 77 valid trades;
- mean partial-known-cost PnL:
  `-63.158529220779220779220779220779220779220779220779` quote units;
- median known-net: approximately `-6.99 bps`.

Deterministic development decision:

**DEVELOP_REGULARIZED_LOGISTIC_BASELINE**

Artifact:

- `artifacts/stage_2/economic_family_development.json`
- SHA-256
  `ae62dff1172ca7666b1119c4c8a0f1ca61757f428c30b66b73a208b34c2a3b67`

## Fixed regularized logistic baseline

One pure-Python L2 logistic baseline was fixed before its result.

Target:

- whether the H2-directional trade has positive partial-known-cost PnL after executable
  bid/ask and 4.5 bps/side fee.

Features:

1. absolute Hyperliquid BBO imbalance;
2. Binance 5s return aligned to the H2 direction;
3. absolute Binance 5s return;
4. Hyperliquid spread.

Model:

- L2 logistic regression;
- lambda = 1;
- deterministic Decimal Newton solver;
- no hyperparameter sweep.

Trade probability hurdle:

- derived once from DEV_A mean positive and mean nonpositive economics;
- no threshold sweep;
- hurdle =
  `0.670096216343838670184142236545596019441226490180723430160101`.

Result:

- DEV_A eligible: 547;
- DEV_A selected: 0;
- DEV_B eligible: 484;
- DEV_B selected: 1;
- that DEV_B trade had known-net PnL `-129.9582` quote units.

Decision:

**STOP_LOGISTIC_DEVELOPMENT**

Artifact:

- `artifacts/stage_2/economic_logistic_development.json`
- SHA-256
  `285775b8febb226414bd838121f99b15b72d5b46edb13383b12398b8c80ccaf8`

## Interpretation

The observed 50-second H2 directional information does not become executable positive
taker economics using the bounded BBO/Binance/spread family.

No fresh registered test evidence should be collected for this 50-second family.

## Next step

TASK-024 treats a longer horizon as a new development family. Any eventual registered
test still requires fresh prospective Hyperliquid + Binance evidence.
