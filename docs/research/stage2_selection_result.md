# Stage 2 Registered H1/H2 Selection Result

## Frozen result

TASK-021 evaluated the two pre-registered hypotheses exactly once on the amended PRIMARY BTC SELECTION partition.

- protocol SHA-256: 2e2404b93e82ad8ac6ff27b10b5f4d22cd7ac624be69a277c6aed75a3b9c9843
- frozen BTC dataset SHA-256: 3eeb0b405a9db439b7711b453ec9820707068bbfba855bf120124b79aa32b237
- selection rows: **1,123**
- result SHA-256: e3403ef3eb6016040344dd8c17f4174b9190ca1a3aa5f5a59f54e1af7f7fb5a0
- decision: **INCONCLUSIVE_SELECTION**
- champion: **none**
- confirmation opened: **false**

The untouched confirmation partition remains unopened.

## H1 — Binance 5-second reference lead

Trial S2-SEL-H1-V1:

- feature-ready: **1,059**
- directional-evaluable: **644**
- required directional-evaluable floor: **783**
- correct directions: **348**
- directional accuracy: **54.0373%**
- IID-reference one-sided p-value: **0.02219**
- positive-autocorrelation design effect: **1.1018**
- effective sample size: **584**
- dependence-adjusted one-sided 97.5% Wilson lower bound: **49.9821%**
- traded opportunities: **663**
- mean partial-known-cost PnL at quantity 1 BTC: **-74.0311 quote units**

H1 is inconclusive for registered power and also does not satisfy the frozen dependence-adjusted or partial-known-cost economic filters.

## H2 — Hyperliquid BBO imbalance

Trial S2-SEL-H2-V1:

- feature-ready: **1,123**
- directional-evaluable: **930**
- correct directions: **543**
- directional accuracy: **58.3871%**
- IID-reference one-sided p-value: **1.7522e-7**
- positive-autocorrelation design effect: **1.2001**
- effective sample size: **774**
- dependence-adjusted one-sided 97.5% Wilson lower bound: **54.8815%**
- traded opportunities: **962**
- mean partial-known-cost PnL at quantity 1 BTC: **-71.1355 quote units**

H2 clears the frozen directional statistical diagnostics on SELECTION but fails the required partial-known-cost economic filter. It is therefore **not** a champion.

Directional predictability alone is not sufficient when executable bid/ask and the documented-base 4.5 bps-per-side fee scenario erase the economic value.

## Controls

Both controls used the exact same 1,123 opportunity IDs.

- no-trade: 962 no-trade, 161 invalid
- seeded randomized direction: 962 traded, 161 invalid
- opportunity-ID SHA-256: 62261a7c4c5c78825a30eb51f1074514c0c84865535bd36b5ae99b48c21da23e

## Interpretation boundary

No positive net-expectancy claim is supported.

The reported economic filter is only partial-known-cost accounting. Actual project-account fee tier, realized latency, own-order impact/slippage, and boundary-aligned funding remain UNKNOWN. Fully-accounted business-net expectancy is still not evaluable.

Because the formal decision is INCONCLUSIVE_SELECTION, the next action is evidence remediation under a new registered work package. The existing confirmation partition must remain untouched.
