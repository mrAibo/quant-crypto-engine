import hashlib
import json
from pathlib import Path

out = Path("/var/lib/quant-crypto-engine/stage2/economic-family-300s-development-registry-v1.json")
payload = {
    "schema_version": 1,
    "purpose": "TASK_023_300S_BOUNDED_DEVELOPMENT_REGISTRY",
    "created_before_hyperliquid_300s_outcome_evaluation": True,
    "evidence_role": "DEVELOPMENT_ONLY",
    "old_confirmation": "EXCLUDED_AND_UNOPENED",
    "horizon_seconds": 300,
    "horizon_decision_sha256": "626f85a08ca187d0c1762cdc7a22c49dfe2301baa97ad9d09c1fdd5acfb164e6",
    "execution": "TAKER_EXECUTABLE_BID_ASK",
    "fee_scenario_bps_per_side": "4.5",
    "unknown_costs": ["latency", "impact", "funding", "actual_project_account_fee_tier"],
    "development_split": {"method": "CHRONOLOGICAL_60_40"},
    "deterministic_candidates": [
        {
            "id": "E300_1_IMB_STRONG",
            "action": "SIGN_HL_BBO_IMBALANCE",
            "min_abs_imbalance": "0.75",
            "min_abs_binance_5s_bps": None,
            "require_binance_sign_alignment": False,
        },
        {
            "id": "E300_2_IMB_EXTREME",
            "action": "SIGN_HL_BBO_IMBALANCE",
            "min_abs_imbalance": "0.95",
            "min_abs_binance_5s_bps": None,
            "require_binance_sign_alignment": False,
        },
        {
            "id": "E300_3_IMB_STRONG_BIN_ALIGN",
            "action": "SIGN_HL_BBO_IMBALANCE",
            "min_abs_imbalance": "0.75",
            "min_abs_binance_5s_bps": "0.5",
            "require_binance_sign_alignment": True,
        },
        {
            "id": "E300_4_IMB_STRONG_BIN_ALIGN_STRONG",
            "action": "SIGN_HL_BBO_IMBALANCE",
            "min_abs_imbalance": "0.75",
            "min_abs_binance_5s_bps": "1.5",
            "require_binance_sign_alignment": True,
        },
    ],
    "deterministic_pass_rule": (
        "Eligible only if DEV_B mean and cumulative partial-known-cost PnL are "
        "positive and DEV_B valid-trade support >=30."
    ),
    "fallback_logistic": {
        "allowed_only_if_no_deterministic_candidate_passes": True,
        "features": [
            "action_times_hl_bbo_imbalance",
            "abs_hl_bbo_imbalance",
            "action_times_binance_mid_return_5s_bps",
            "abs_binance_mid_return_5s_bps",
        ],
        "model": "L2_LOGISTIC_LAMBDA_1",
        "objective": "MEAN_LOGLOSS_PLUS_LAMBDA_OVER_2N_TIMES_NONINTERCEPT_L2",
        "optimizer": "DETERMINISTIC_BATCH_GRADIENT_DESCENT_4000_ITERS_LR_0.05",
        "gates": ["DEV_A_MAX_SCORE_Q90", "DEV_A_MAX_SCORE_Q95"],
        "pass_rule": (
            "DEV_B mean and cumulative partial-known-cost PnL positive with >=30 valid trades."
        ),
    },
}
raw = (json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n").encode()
out.write_bytes(raw)
print(hashlib.sha256(raw).hexdigest())
