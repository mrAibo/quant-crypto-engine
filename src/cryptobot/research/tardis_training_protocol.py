from __future__ import annotations

import hashlib
import json
from pathlib import Path

PROTOCOL_VERSION = "stage2-task029-tardis-training-v1"
PURPOSE = "DEVELOPMENT_ONLY_TARDIS_HISTORICAL_TRAINING"
TASK025_REGISTRY_SHA256 = "d5024ce6cb16c0d3dcce5b65f3f62f6d577b971d3bda7c8342ab67aaa100b130"
TASK028_PROTOCOL_SHA256 = "8d08ffa54eb64a3ecf11b9a73e3eea5d815f60560e7a93ad6796c63d2760b735"
TASK028_CORPUS_SHA256 = "9696dca5f57fe160a8438236f1af82947a1588d2476a882fdf627f4cbd26e5e8"
TASK028_ARCHIVE_SET_SHA256 = "8e545456b34c6d1dabdb4e31fc13a0cb174bb96fef01eb137d9c32fa1dcb37fc"
FEE_SCENARIO_BPS_PER_SIDE = "4.5"
FEATURE_LOOKBACK_US = 5_000_000
MAX_FEATURE_STALENESS_US = 2_000_000
MAX_HISTORICAL_BOOK_STEP_US = 15_000_000

DEV_A_DAYS = (
    "2024-11-01",
    "2024-12-01",
    "2025-01-01",
    "2025-02-01",
    "2025-03-01",
    "2025-04-01",
    "2025-05-01",
    "2025-06-01",
    "2025-07-01",
    "2025-08-01",
    "2025-09-01",
    "2025-10-01",
)
DEV_B_DAYS = (
    "2025-11-01",
    "2025-12-01",
    "2026-01-01",
    "2026-02-01",
    "2026-03-01",
    "2026-04-01",
    "2026-05-01",
    "2026-06-01",
)

FEATURE_NAMES = (
    "abs_hl_bbo_imbalance",
    "h2_aligned_hl_depth_imbalance_top5",
    "h2_aligned_hl_aggressive_trade_flow_5s",
    "h2_aligned_binance_aggressive_trade_flow_5s",
    "h2_aligned_hl_mid_return_5s_bps",
    "h2_aligned_binance_mid_return_5s_bps",
    "h2_aligned_cross_venue_return_gap_5s_bps",
    "hl_spread_bps",
)

HORIZONS = (
    {
        "horizon_seconds": 50,
        "min_dev_a_valid_targets": 300,
        "min_dev_a_positive_targets": 30,
        "min_dev_a_nonpositive_targets": 30,
        "min_dev_b_selected_trades": 50,
        "min_each_dev_b_half_selected_trades": 25,
    },
    {
        "horizon_seconds": 300,
        "min_dev_a_valid_targets": 80,
        "min_dev_a_positive_targets": 30,
        "min_dev_a_nonpositive_targets": 30,
        "min_dev_b_selected_trades": 30,
        "min_each_dev_b_half_selected_trades": 15,
    },
)


class TardisTrainingProtocolError(ValueError):
    """Raised when the frozen TASK-029 protocol is invalid."""


def build_protocol() -> dict[str, object]:
    if len(DEV_A_DAYS) != 12 or len(DEV_B_DAYS) != 8:
        raise TardisTrainingProtocolError("historical split must remain 12/8 whole days")
    if set(DEV_A_DAYS) & set(DEV_B_DAYS):
        raise TardisTrainingProtocolError("DEV_A and DEV_B days must be disjoint")
    return {
        "schema_version": 1,
        "protocol_version": PROTOCOL_VERSION,
        "purpose": PURPOSE,
        "frozen_before_historical_outcome_use": True,
        "source": {
            "task025_registry_sha256": TASK025_REGISTRY_SHA256,
            "task028_protocol_sha256": TASK028_PROTOCOL_SHA256,
            "task028_corpus_manifest_sha256": TASK028_CORPUS_SHA256,
            "task028_archive_set_sha256": TASK028_ARCHIVE_SET_SHA256,
        },
        "evidence_role": "DEVELOPMENT_ONLY_EXTERNAL_RECEIVE_TIME",
        "storage_layer": {
            "source_of_truth": "TASK028_IMMUTABLE_RAW_PLUS_MANIFESTS",
            "derived_parquet": {
                "compression": "ZSTD",
                "decimal_type": "DECIMAL(38,18)",
                "timestamp_type": "BIGINT_MICROSECONDS",
                "source_row_number_preserved": True,
                "one_file_per_source_archive": True,
            },
            "query_catalog": {
                "engine": "DuckDB",
                "version": "1.5.5",
                "catalog_contains_source_views_and_metadata_only": True,
            },
            "economic_outcomes_materialized_during_conversion": False,
            "derived_layer_rebuildable": True,
        },
        "time_semantics": {
            "ordering": "TARDIS_LOCAL_TIMESTAMP_THEN_FILE_ROW_ORDER",
            "timestamp_units": "MICROSECONDS_SINCE_UNIX_EPOCH_UTC",
            "causal_domain": "EACH_EXCHANGE_SYMBOL_UTC_DAY_IS_SEPARATE",
            "cross_day_windows": "FORBIDDEN",
            "timestamp_reversal": "HARD_FAIL_SOURCE_DAY",
            "aibo_receive_time_equivalence": False,
        },
        "decision_stream": {
            "source": "HYPERLIQUID_BTC_BOOK_SNAPSHOT_5",
            "entry_rule": "NEXT_UNUSED_BOOK_SNAPSHOT",
            "exit_rule": "FIRST_BOOK_SNAPSHOT_AT_OR_AFTER_ENTRY_PLUS_HORIZON",
            "next_entry_rule": "FIRST_BOOK_SNAPSHOT_AFTER_EXIT_ROW",
            "max_inter_snapshot_gap_us": MAX_HISTORICAL_BOOK_STEP_US,
            "gap_rationale": (
                "EXTERNAL_PRE_FASTBOOK_L2_SNAPSHOT_CADENCE_DIFFERS_FROM_AIBO_BBO; "
                "15S_IS_FROZEN_SOURCE_QUALITY_CEILING_NOT_A_LIVE_LATENCY_ASSUMPTION"
            ),
        },
        "feature_semantics": {
            "feature_names": list(FEATURE_NAMES),
            "lookback_us": FEATURE_LOOKBACK_US,
            "max_anchor_or_current_staleness_us": MAX_FEATURE_STALENESS_US,
            "book_depth": 5,
            "hl_bbo_imbalance": ("(BID_SIZE_0-ASK_SIZE_0)/(BID_SIZE_0+ASK_SIZE_0)_AT_DECISION"),
            "hl_depth_imbalance_top5": (
                "(SUM_BID_SIZE_0_4-SUM_ASK_SIZE_0_4)/(SUM_BID_SIZE_0_4+SUM_ASK_SIZE_0_4)"
            ),
            "trade_window": "(DECISION_MINUS_5S,DECISION]",
            "trade_side": "TARDIS_NORMALIZED_LIQUIDITY_TAKER_SIDE",
            "unknown_trade_side": "FEATURE_MISSING_IF_ANY_UNKNOWN_SIDE_TRADE_IN_WINDOW",
            "no_trades": "FEATURE_MISSING",
            "mid_return_anchor": "LATEST_AT_OR_BEFORE_TARGET_WITH_MAX_2S_STALENESS",
            "cross_venue_gap": "HL_MID_RETURN_5S_BPS_MINUS_BINANCE_MID_RETURN_5S_BPS",
            "missingness": "ANY_MISSING_MODEL_FEATURE_EXCLUDES_ROW_FROM_MODEL_SAMPLE",
        },
        "outcome_semantics": {
            "direction_rule": "SIGN_HYPERLIQUID_TOP_OF_BOOK_IMBALANCE",
            "execution": "HYPERLIQUID_EXECUTABLE_BID_ASK",
            "entry_price": "ASK_FOR_LONG_BID_FOR_SHORT_AT_ENTRY_SNAPSHOT",
            "exit_price": "BID_FOR_LONG_ASK_FOR_SHORT_AT_EXIT_SNAPSHOT",
            "fee_bps_per_side": FEE_SCENARIO_BPS_PER_SIDE,
            "fee_class": "SCENARIO",
            "latency": "UNKNOWN",
            "impact": "UNKNOWN",
            "funding": "UNKNOWN",
            "actual_account_fee": "UNKNOWN",
            "target": "H2_DIRECTIONAL_TRADE_PARTIAL_KNOWN_COST_PNL_GT_ZERO",
        },
        "split": {
            "rule": "WHOLE_UTC_DAYS_CHRONOLOGICAL_60_40",
            "dev_a_days": list(DEV_A_DAYS),
            "dev_b_days": list(DEV_B_DAYS),
            "no_day_may_move_between_partitions": True,
        },
        "model": {
            "type": "L2_LOGISTIC_REGRESSION",
            "solver": "DETERMINISTIC_DECIMAL_NEWTON",
            "feature_standardization": "DEV_A_ONLY",
            "l2_lambda": "1",
            "max_iterations": 80,
            "convergence_tolerance": "1e-24",
            "probability_gate": (
                "DEV_A_EXPECTED_VALUE_BREAKEVEN_FROM_MEAN_POSITIVE_AND_NONPOSITIVE_KNOWN_NET"
            ),
            "hyperparameter_sweep": False,
            "training_partition": "DEV_A_ONLY",
        },
        "horizons": [dict(item) for item in HORIZONS],
        "dev_b_evaluation": {
            "selected_trade_split": (
                "CHRONOLOGICAL_HALF_BY_SELECTED_TRADE_COUNT; EXACT MIDDLE EXTRA TRADE GOES_TO_LATE"
            ),
            "pass_rules": [
                "MIN_SELECTED_TRADE_SUPPORT_MET",
                "MIN_EACH_HALF_SELECTED_TRADE_SUPPORT_MET",
                "MEAN_PARTIAL_KNOWN_COST_PNL_GT_ZERO",
                "CUMULATIVE_PARTIAL_KNOWN_COST_PNL_GT_ZERO",
                "MEDIAN_KNOWN_NET_BPS_GT_ZERO",
                "EARLY_MEAN_PARTIAL_KNOWN_COST_PNL_GT_ZERO",
                "LATE_MEAN_PARTIAL_KNOWN_COST_PNL_GT_ZERO",
            ],
            "family_rule": (
                "AT_MOST_ONE_HORIZON; AMONG PASSING HORIZONS CHOOSE HIGHER "
                "DEV_B_MEAN_KNOWN_NET_BPS; EXACT TIE CHOOSES_SHORTER_HORIZON"
            ),
            "no_threshold_or_hyperparameter_tuning": True,
        },
        "decision": {
            "pass": (
                "FREEZE_ONE_HISTORICAL_DEVELOPMENT_CANDIDATE_FOR_FUTURE_FRESH_PROSPECTIVE_SELECTION"
            ),
            "fail": "STOP_HISTORICAL_MICROSTRUCTURE_DEVELOPMENT",
            "current_task027_may_be_repurposed_as_selection": False,
            "old_confirmation": "UNOPENED_AND_EXCLUDED",
            "fresh_selection_started": False,
            "fresh_confirmation_started": False,
        },
    }


def protocol_bytes() -> bytes:
    return (
        json.dumps(build_protocol(), sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        + "\n"
    ).encode()


def protocol_sha256() -> str:
    return hashlib.sha256(protocol_bytes()).hexdigest()


def write_protocol(path: str | Path) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = protocol_bytes()
    try:
        with target.open("xb") as stream:
            stream.write(payload)
    except FileExistsError:
        if target.read_bytes() != payload:
            raise TardisTrainingProtocolError("existing TASK-029 protocol differs") from None
    return target
