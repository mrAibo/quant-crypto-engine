# Prompt for the next ChatGPT session

Continue **mrAibo/quant-crypto-engine** autonomously from GitHub source of truth.
At session start, verify the latest `main` and prefer it over chat memory.

Current state:

- phase: **Stage 2 — Signal-Existence Dataset and Falsification Protocol**
- current task: **TASK-027 — Stage 2 Prospective Development Evidence Expansion**
- TASK-001 through TASK-026 are complete
- TASK-027 frozen public DEVELOPMENT capture is **RUNNING** on Aibo
- old Stage-2 confirmation: **UNOPENED_AND_EXCLUDED**
- live trading / OMS / signing / capital deployment: **FORBIDDEN**
- no private account/API key/wallet/AWS requester-pays access is required
- no user action is currently required

Read in this order:

1. `HANDOFF.md`
2. `STATUS.md`
3. `tasks/TASK_027.md`
4. `artifacts/stage_2/development_campaign_protocol.json`
5. `artifacts/stage_2/economic_bottleneck_adjudication.json`
6. only then inspect implementation/evidence as needed


Frozen TASK-027 inputs:

- protocol SHA-256:
  `1ab9a735f512dd301392ba568b49ebd0f1e80d676f073b3d502bf73d111bc1d3`
- runtime profile SHA-256:
  `8bf2a31ec634b475f1e3b559663bb35e16950c1c721ab73ddc5812cd6b1f03e1`
- fixed duration: **72 hours**
- ordinary segment duration: **900 seconds**
- horizons: **50s / 300s only**
- TASK-025 eight-feature family unchanged
- evidence role: **DEVELOPMENT_ONLY**

Transport reuses the validated Stage-0 public dual-source recorder as a superset.
Only Hyperliquid BTC L2/BBO/trades and Binance BTCUSDT bookTicker/aggTrade are
TASK-027 eligible. ETH and Hyperliquid activeAssetCtx remain preserved raw but
excluded from TASK-027 features/targets.

Operational checkpoint:

- PR #45 merged as `b3de5b4c15138ccc1df81c9a055d04920cad237c` after green CI run `36312921369`;
- the same merge commit is deployed on Aibo;
- campaign root is `/var/lib/quant-crypto-engine/stage2-development-campaign`;
- capture/process timers are active;
- first attempt is `run-1790505535742461344-86b3a1307196c582cdde`;
- QCR1 raw evidence is growing;
- campaign state is still `PRESTART` until that attempt successfully seals.

Exact next action:

1. verify the first successful capture freezes start and deadline;
2. commit the exact start/deadline checkpoint;
3. keep the fixed 72-hour public DEVELOPMENT collection healthy;
4. after the deadline, publish deterministic coverage/support evidence only.

Do not fit a model, inspect performance to change collection, open old confirmation,
change features/horizons, or introduce private/account/maker/live execution.
