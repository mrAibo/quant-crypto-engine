import hashlib
import json
from pathlib import Path

src = Path("/var/lib/quant-crypto-engine/stage2/binance-development-horizon-1-2-5m-v1.json")
out = Path("/var/lib/quant-crypto-engine/stage2/economic-horizon-development-decision-v1.json")
payload = {
    "schema_version": 1,
    "purpose": "TASK_023_DEVELOPMENT_HORIZON_DECISION_BEFORE_HYPERLIQUID_5M_OUTCOME_EVALUATION",
    "source_sha256": hashlib.sha256(src.read_bytes()).hexdigest(),
    "old_confirmation": "EXCLUDED_AND_UNOPENED",
    "candidate_horizons_seconds": [60, 120, 300],
    "chosen_development_horizon_seconds": 300,
    "reason": {
        "BTC_60S_q95_bps": "7.5263853790966772807998935978782165126704585462028",
        "BTC_120S_q95_bps": "10.190371113653068581353649572956346822180364887071",
        "BTC_300S_q95_bps": "15.684576885011661482914006170312546563587627378370",
        "BTC_300S_fraction_above_9bps": "0.17509920634920634920634920634920634920634920634921",
        "note": (
            "300s is the shortest scanned horizon with material historical "
            "reference-price headroom above the approximately 9 bps fee-only "
            "round trip; final executable viability must be tested on "
            "Hyperliquid bid/ask."
        ),
    },
    "limitations": [
        "Binance aggTrade development context only",
        "not Hyperliquid executable BBO",
        "not confirmation evidence",
    ],
}
raw = (json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n").encode()
out.write_bytes(raw)
print(hashlib.sha256(raw).hexdigest())
