from __future__ import annotations

import hashlib
import json
from bisect import bisect_left
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal, localcontext
from itertools import pairwise
from pathlib import Path
from statistics import median
from typing import cast

import duckdb

from cryptobot.data.numeric import serialize_exact_decimal
from cryptobot.research.economic_family import executable_known_net
from cryptobot.research.microstructure_family import (
    FEATURE_NAMES,
    FrozenMicrostructureModel,
    MicrostructureRow,
    expected_value_hurdle,
    feature_vector,
    fit_logistic,
    fit_standardization,
    h2_direction,
)
from cryptobot.research.tardis_training_protocol import (
    DEV_A_DAYS,
    DEV_B_DAYS,
    MAX_FEATURE_STALENESS_US,
    MAX_HISTORICAL_BOOK_STEP_US,
    protocol_sha256,
)

LAKEHOUSE_MANIFEST_SHA256 = "c5032eda1f33421a6d71560e42e0f3e042b1ccd78647e358ea8b0390b4fc0e5f"
PARQUET_SET_SHA256 = "4d451076c74fa706d57b3565a16cc5aa78875664c68fb934ab72c687257a7a2b"
CACHE_VERSION = "stage2-task029-historical-feature-cache-v1"
REPORT_VERSION = "stage2-task029-historical-development-v1"
HORIZONS = (50, 300)
_ZERO = Decimal(0)
_BPS = Decimal(10000)


class TardisHistoricalTrainingError(ValueError):
    """Raised when TASK-029 historical feature/training evidence violates the protocol."""


@dataclass(frozen=True, slots=True)
class OpportunitySpec:
    key: int
    horizon_seconds: int
    source_day: str
    entry_row: int
    exit_row: int | None
    decision_us: int
    anchor_us: int
    gap_invalid: bool


@dataclass(frozen=True, slots=True)
class CachedHistoricalRow:
    source_day: str
    horizon_seconds: int
    row: MicrostructureRow


@dataclass(frozen=True, slots=True)
class FeatureCacheBuildReport:
    protocol_sha256: str
    lakehouse_manifest_sha256: str
    parquet_set_sha256: str
    cache_50s_sha256: str
    cache_300s_sha256: str
    row_count_50s: int
    row_count_300s: int
    day_counts_50s: tuple[tuple[str, int], ...]
    day_counts_300s: tuple[tuple[str, int], ...]

    def as_dict(self) -> dict[str, object]:
        return {
            "schema_version": 1,
            "report_version": "stage2-task029-feature-cache-build-v1",
            "protocol_sha256": self.protocol_sha256,
            "lakehouse_manifest_sha256": self.lakehouse_manifest_sha256,
            "parquet_set_sha256": self.parquet_set_sha256,
            "cache_50s_sha256": self.cache_50s_sha256,
            "cache_300s_sha256": self.cache_300s_sha256,
            "row_count_50s": self.row_count_50s,
            "row_count_300s": self.row_count_300s,
            "day_counts_50s": dict(self.day_counts_50s),
            "day_counts_300s": dict(self.day_counts_300s),
            "economic_summary_computed": False,
            "model_fitted": False,
        }

    def to_json_bytes(self) -> bytes:
        return _json_bytes(self.as_dict())

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.to_json_bytes()).hexdigest()


@dataclass(frozen=True, slots=True)
class HorizonSupport:
    horizon_seconds: int
    feature_complete_count: int
    valid_target_count: int
    positive_target_count: int
    nonpositive_target_count: int
    supported: bool

    def as_dict(self) -> dict[str, object]:
        return {
            "horizon_seconds": self.horizon_seconds,
            "feature_complete_count": self.feature_complete_count,
            "valid_target_count": self.valid_target_count,
            "positive_target_count": self.positive_target_count,
            "nonpositive_target_count": self.nonpositive_target_count,
            "supported": self.supported,
        }


@dataclass(frozen=True, slots=True)
class DevBEvaluation:
    eligible_rows: int
    selected_trades: int
    positive_selected_trades: int
    mean_known_net_quote: Decimal | None
    cumulative_known_net_quote: Decimal
    mean_known_net_bps: Decimal | None
    median_known_net_bps: Decimal | None
    early_selected_trades: int
    late_selected_trades: int
    early_mean_known_net_quote: Decimal | None
    late_mean_known_net_quote: Decimal | None
    passed: bool

    def as_dict(self) -> dict[str, object]:
        return {
            "eligible_rows": self.eligible_rows,
            "selected_trades": self.selected_trades,
            "positive_selected_trades": self.positive_selected_trades,
            "mean_known_net_quote": _optional(self.mean_known_net_quote),
            "cumulative_known_net_quote": serialize_exact_decimal(self.cumulative_known_net_quote),
            "mean_known_net_bps": _optional(self.mean_known_net_bps),
            "median_known_net_bps": _optional(self.median_known_net_bps),
            "early_selected_trades": self.early_selected_trades,
            "late_selected_trades": self.late_selected_trades,
            "early_mean_known_net_quote": _optional(self.early_mean_known_net_quote),
            "late_mean_known_net_quote": _optional(self.late_mean_known_net_quote),
            "passed": self.passed,
        }


@dataclass(frozen=True, slots=True)
class HorizonDevelopmentResult:
    horizon_seconds: int
    cache_sha256: str
    dev_a_row_count: int
    dev_b_row_count: int
    support: HorizonSupport
    model: FrozenMicrostructureModel | None
    dev_b_evaluation: DevBEvaluation | None

    def as_dict(self) -> dict[str, object]:
        model_dict: dict[str, object] | None = None
        if self.model is not None:
            model_dict = self.model.as_dict()
            model_dict["model_id"] = (
                f"S2-T029-TARDIS-H2-MICROSTRUCTURE-L2-LOGISTIC-{self.horizon_seconds}S-V1"
            )
            model_dict["protocol_sha256"] = protocol_sha256()
        return {
            "horizon_seconds": self.horizon_seconds,
            "cache_sha256": self.cache_sha256,
            "dev_a_row_count": self.dev_a_row_count,
            "dev_b_row_count": self.dev_b_row_count,
            "support": self.support.as_dict(),
            "model": model_dict,
            "dev_b_evaluation": (
                None if self.dev_b_evaluation is None else self.dev_b_evaluation.as_dict()
            ),
        }


@dataclass(frozen=True, slots=True)
class HistoricalDevelopmentReport:
    feature_build_report_sha256: str
    cache_50s_sha256: str
    cache_300s_sha256: str
    horizon_50s: HorizonDevelopmentResult
    horizon_300s: HorizonDevelopmentResult
    decision: str
    selected_horizon_seconds: int | None

    def as_dict(self) -> dict[str, object]:
        return {
            "schema_version": 1,
            "report_version": REPORT_VERSION,
            "protocol_sha256": protocol_sha256(),
            "lakehouse_manifest_sha256": LAKEHOUSE_MANIFEST_SHA256,
            "parquet_set_sha256": PARQUET_SET_SHA256,
            "evidence_role": "DEVELOPMENT_ONLY_EXTERNAL_RECEIVE_TIME",
            "split": {
                "dev_a_days": list(DEV_A_DAYS),
                "dev_b_days": list(DEV_B_DAYS),
            },
            "feature_build_report_sha256": self.feature_build_report_sha256,
            "cache_50s_sha256": self.cache_50s_sha256,
            "cache_300s_sha256": self.cache_300s_sha256,
            "horizon_50s": self.horizon_50s.as_dict(),
            "horizon_300s": self.horizon_300s.as_dict(),
            "decision": self.decision,
            "selected_horizon_seconds": self.selected_horizon_seconds,
            "current_task027_repurposed_as_selection": False,
            "old_confirmation_status": "UNOPENED_AND_EXCLUDED",
            "fresh_selection_started": False,
            "fresh_confirmation_started": False,
            "cost_scope": {
                "execution": "HYPERLIQUID_EXECUTABLE_BID_ASK",
                "fee_bps_per_side": "4.5",
                "fee_class": "SCENARIO",
                "latency": "UNKNOWN",
                "impact": "UNKNOWN",
                "funding": "UNKNOWN",
                "actual_account_fee": "UNKNOWN",
            },
        }

    def to_json_bytes(self) -> bytes:
        return _json_bytes(self.as_dict())

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.to_json_bytes()).hexdigest()


def verify_lakehouse_manifest(path: str | Path) -> dict[str, object]:
    raw = Path(path).read_bytes()
    if hashlib.sha256(raw).hexdigest() != LAKEHOUSE_MANIFEST_SHA256:
        raise TardisHistoricalTrainingError("TASK-029 lakehouse manifest SHA mismatch")
    payload = json.loads(raw)
    if not isinstance(payload, dict):
        raise TardisHistoricalTrainingError("lakehouse manifest root must be an object")
    obj = cast(dict[str, object], payload)
    if obj.get("parquet_set_sha256") != PARQUET_SET_SHA256:
        raise TardisHistoricalTrainingError("TASK-029 Parquet-set SHA mismatch")
    if obj.get("economic_outcomes_materialized") is not False:
        raise TardisHistoricalTrainingError("lakehouse conversion consumed economic outcomes")
    return obj


def build_opportunities(
    *,
    source_day: str,
    source_rows: tuple[int, ...],
    timestamps_us: tuple[int, ...],
    horizon_seconds: int,
    key_start: int = 0,
) -> tuple[OpportunitySpec, ...]:
    if horizon_seconds not in HORIZONS:
        raise TardisHistoricalTrainingError("unsupported frozen horizon")
    if len(source_rows) != len(timestamps_us):
        raise TardisHistoricalTrainingError("book row/timestamp lengths differ")
    if not source_rows:
        return ()
    for previous, current in pairwise(timestamps_us):
        if current < previous:
            raise TardisHistoricalTrainingError("book local timestamps reverse within source day")

    bad_gap_prefix = [0]
    for previous, current in pairwise(timestamps_us):
        bad_gap_prefix.append(
            bad_gap_prefix[-1] + int(current - previous > MAX_HISTORICAL_BOOK_STEP_US)
        )

    horizon_us = horizon_seconds * 1_000_000
    result: list[OpportunitySpec] = []
    start = 0
    key = key_start
    while start < len(timestamps_us):
        decision_us = timestamps_us[start]
        target_us = decision_us + horizon_us
        exit_index = bisect_left(timestamps_us, target_us, lo=start + 1)
        if exit_index >= len(timestamps_us):
            result.append(
                OpportunitySpec(
                    key=key,
                    horizon_seconds=horizon_seconds,
                    source_day=source_day,
                    entry_row=source_rows[start],
                    exit_row=None,
                    decision_us=decision_us,
                    anchor_us=decision_us - 5_000_000,
                    gap_invalid=False,
                )
            )
            break
        gap_invalid = bad_gap_prefix[exit_index] - bad_gap_prefix[start] > 0
        result.append(
            OpportunitySpec(
                key=key,
                horizon_seconds=horizon_seconds,
                source_day=source_day,
                entry_row=source_rows[start],
                exit_row=source_rows[exit_index],
                decision_us=decision_us,
                anchor_us=decision_us - 5_000_000,
                gap_invalid=gap_invalid,
            )
        )
        key += 1
        start = exit_index + 1
    return tuple(result)


_ENRICH_SQL = """
WITH
hb AS (
    SELECT
        source_row_number, local_timestamp_us,
        ask_price_0, ask_amount_0, bid_price_0, bid_amount_0,
        ask_amount_1, bid_amount_1, ask_amount_2, bid_amount_2,
        ask_amount_3, bid_amount_3, ask_amount_4, bid_amount_4
    FROM hl_book_snapshot_5
    WHERE local_timestamp_us >= ? AND local_timestamp_us < ?
),
hu AS (
    SELECT * EXCLUDE (rn) FROM (
        SELECT
            source_row_number, local_timestamp_us, bid_price_0, ask_price_0,
            row_number() OVER (
                PARTITION BY local_timestamp_us ORDER BY source_row_number DESC
            ) AS rn
        FROM hb
    ) WHERE rn = 1
),
bq AS (
    SELECT * EXCLUDE (rn) FROM (
        SELECT
            source_row_number, local_timestamp_us, bid_price, ask_price,
            row_number() OVER (
                PARTITION BY local_timestamp_us ORDER BY source_row_number DESC
            ) AS rn
        FROM binance_quotes
        WHERE local_timestamp_us >= ? AND local_timestamp_us < ?
    ) WHERE rn = 1
),
ht AS (
    SELECT
        local_timestamp_us,
        sum(CASE WHEN side = 'buy' THEN amount ELSE 0 END) AS buy_amount,
        sum(CASE WHEN side = 'sell' THEN amount ELSE 0 END) AS sell_amount,
        sum(
            CASE WHEN side NOT IN ('buy', 'sell') OR side IS NULL THEN 1 ELSE 0 END
        ) AS unknown_count
    FROM hl_trades
    WHERE local_timestamp_us >= ? AND local_timestamp_us < ?
    GROUP BY local_timestamp_us
),
hc AS (
    SELECT
        local_timestamp_us,
        sum(buy_amount) OVER (
            ORDER BY local_timestamp_us ROWS UNBOUNDED PRECEDING
        ) AS cum_buy,
        sum(sell_amount) OVER (
            ORDER BY local_timestamp_us ROWS UNBOUNDED PRECEDING
        ) AS cum_sell,
        sum(unknown_count) OVER (
            ORDER BY local_timestamp_us ROWS UNBOUNDED PRECEDING
        ) AS cum_unknown
    FROM ht
),
bt AS (
    SELECT
        local_timestamp_us,
        sum(CASE WHEN side = 'buy' THEN amount ELSE 0 END) AS buy_amount,
        sum(CASE WHEN side = 'sell' THEN amount ELSE 0 END) AS sell_amount,
        sum(
            CASE WHEN side NOT IN ('buy', 'sell') OR side IS NULL THEN 1 ELSE 0 END
        ) AS unknown_count
    FROM binance_trades
    WHERE local_timestamp_us >= ? AND local_timestamp_us < ?
    GROUP BY local_timestamp_us
),
bc AS (
    SELECT
        local_timestamp_us,
        sum(buy_amount) OVER (
            ORDER BY local_timestamp_us ROWS UNBOUNDED PRECEDING
        ) AS cum_buy,
        sum(sell_amount) OVER (
            ORDER BY local_timestamp_us ROWS UNBOUNDED PRECEDING
        ) AS cum_sell,
        sum(unknown_count) OVER (
            ORDER BY local_timestamp_us ROWS UNBOUNDED PRECEDING
        ) AS cum_unknown
    FROM bt
)
SELECT
    d.k, d.horizon_seconds, d.source_day, d.entry_row, d.exit_row,
    d.decision_us, d.anchor_us, d.gap_invalid,
    e.bid_price_0 AS entry_bid, e.ask_price_0 AS entry_ask,
    e.bid_amount_0, e.ask_amount_0,
    e.bid_amount_1, e.ask_amount_1,
    e.bid_amount_2, e.ask_amount_2,
    e.bid_amount_3, e.ask_amount_3,
    e.bid_amount_4, e.ask_amount_4,
    x.local_timestamp_us AS exit_ts,
    x.bid_price_0 AS exit_bid, x.ask_price_0 AS exit_ask,
    ha.local_timestamp_us AS hl_anchor_ts,
    ha.bid_price_0 AS hl_anchor_bid, ha.ask_price_0 AS hl_anchor_ask,
    bcur.local_timestamp_us AS bin_current_ts,
    bcur.bid_price AS bin_current_bid, bcur.ask_price AS bin_current_ask,
    banc.local_timestamp_us AS bin_anchor_ts,
    banc.bid_price AS bin_anchor_bid, banc.ask_price AS bin_anchor_ask,
    hcur.cum_buy AS hl_cur_buy, hcur.cum_sell AS hl_cur_sell,
    hcur.cum_unknown AS hl_cur_unknown,
    hstart.cum_buy AS hl_start_buy, hstart.cum_sell AS hl_start_sell,
    hstart.cum_unknown AS hl_start_unknown,
    btradecur.cum_buy AS bin_cur_buy, btradecur.cum_sell AS bin_cur_sell,
    btradecur.cum_unknown AS bin_cur_unknown,
    btradestart.cum_buy AS bin_start_buy, btradestart.cum_sell AS bin_start_sell,
    btradestart.cum_unknown AS bin_start_unknown
FROM decisions d
JOIN hb e ON e.source_row_number = d.entry_row
LEFT JOIN hb x ON x.source_row_number = d.exit_row
ASOF LEFT JOIN hu ha ON d.anchor_us >= ha.local_timestamp_us
ASOF LEFT JOIN bq bcur ON d.decision_us >= bcur.local_timestamp_us
ASOF LEFT JOIN bq banc ON d.anchor_us >= banc.local_timestamp_us
ASOF LEFT JOIN hc hcur ON d.decision_us >= hcur.local_timestamp_us
ASOF LEFT JOIN hc hstart ON d.anchor_us >= hstart.local_timestamp_us
ASOF LEFT JOIN bc btradecur ON d.decision_us >= btradecur.local_timestamp_us
ASOF LEFT JOIN bc btradestart ON d.anchor_us >= btradestart.local_timestamp_us
ORDER BY d.k
"""


def build_feature_caches(
    *,
    catalog_path: str | Path,
    lakehouse_manifest_path: str | Path,
    output_root: str | Path,
) -> FeatureCacheBuildReport:
    verify_lakehouse_manifest(lakehouse_manifest_path)
    root = Path(output_root)
    root.mkdir(parents=True, exist_ok=True)
    by_horizon: dict[int, list[dict[str, object]]] = {50: [], 300: []}
    day_counts: dict[int, list[tuple[str, int]]] = {50: [], 300: []}

    connection = duckdb.connect(str(catalog_path), read_only=True)
    connection.execute("SET threads = 1")
    connection.execute("SET preserve_insertion_order = true")
    try:
        for source_day in (*DEV_A_DAYS, *DEV_B_DAYS):
            day_start, day_end = _day_bounds_us(source_day)
            timeline = connection.execute(
                "SELECT source_row_number, local_timestamp_us "
                "FROM hl_book_snapshot_5 "
                "WHERE local_timestamp_us >= ? AND local_timestamp_us < ? "
                "ORDER BY source_row_number",
                [day_start, day_end],
            ).fetchall()
            source_rows = tuple(int(item[0]) for item in timeline)
            timestamps = tuple(int(item[1]) for item in timeline)
            if not timestamps:
                raise TardisHistoricalTrainingError(f"Hyperliquid book day is empty: {source_day}")

            opportunities: list[OpportunitySpec] = []
            key_start = 0
            for horizon in HORIZONS:
                items = build_opportunities(
                    source_day=source_day,
                    source_rows=source_rows,
                    timestamps_us=timestamps,
                    horizon_seconds=horizon,
                    key_start=key_start,
                )
                opportunities.extend(items)
                day_counts[horizon].append((source_day, len(items)))
                key_start += len(items)

            _load_decisions(connection, tuple(opportunities))
            cursor = connection.execute(
                _ENRICH_SQL,
                [
                    day_start,
                    day_end,
                    day_start,
                    day_end,
                    day_start,
                    day_end,
                    day_start,
                    day_end,
                ],
            )
            columns = tuple(item[0] for item in cursor.description)
            enriched = cursor.fetchall()
            if len(enriched) != len(opportunities):
                raise TardisHistoricalTrainingError(
                    f"enriched decision count differs for {source_day}"
                )
            for item in enriched:
                record = dict(zip(columns, item, strict=True))
                row = _build_cache_row(record)
                horizon = cast(int, row["horizon_seconds"])
                by_horizon[horizon].append(row)
            connection.execute("DROP TABLE decisions")
    finally:
        connection.close()

    cache_paths: dict[int, Path] = {}
    cache_shas: dict[int, str] = {}
    for horizon in HORIZONS:
        payload = {
            "schema_version": 1,
            "cache_version": CACHE_VERSION,
            "protocol_sha256": protocol_sha256(),
            "lakehouse_manifest_sha256": LAKEHOUSE_MANIFEST_SHA256,
            "parquet_set_sha256": PARQUET_SET_SHA256,
            "horizon_seconds": horizon,
            "feature_names": list(FEATURE_NAMES),
            "rows": by_horizon[horizon],
        }
        path = root / f"historical-features-{horizon}s.json"
        raw = _json_bytes(payload)
        _write_immutable(path, raw)
        cache_paths[horizon] = path
        cache_shas[horizon] = hashlib.sha256(raw).hexdigest()

    return FeatureCacheBuildReport(
        protocol_sha256=protocol_sha256(),
        lakehouse_manifest_sha256=LAKEHOUSE_MANIFEST_SHA256,
        parquet_set_sha256=PARQUET_SET_SHA256,
        cache_50s_sha256=cache_shas[50],
        cache_300s_sha256=cache_shas[300],
        row_count_50s=len(by_horizon[50]),
        row_count_300s=len(by_horizon[300]),
        day_counts_50s=tuple(day_counts[50]),
        day_counts_300s=tuple(day_counts[300]),
    )


def _load_decisions(
    connection: duckdb.DuckDBPyConnection,
    opportunities: tuple[OpportunitySpec, ...],
) -> None:
    connection.execute(
        "CREATE TEMP TABLE decisions("
        "k BIGINT, horizon_seconds INTEGER, source_day VARCHAR, "
        "entry_row BIGINT, exit_row BIGINT, decision_us BIGINT, "
        "anchor_us BIGINT, gap_invalid BOOLEAN)"
    )
    connection.executemany(
        "INSERT INTO decisions VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        [
            (
                item.key,
                item.horizon_seconds,
                item.source_day,
                item.entry_row,
                item.exit_row,
                item.decision_us,
                item.anchor_us,
                item.gap_invalid,
            )
            for item in opportunities
        ],
    )


def _build_cache_row(record: dict[str, object]) -> dict[str, object]:
    source_day = _required_string(record, "source_day")
    horizon = _required_int(record, "horizon_seconds")
    decision_us = _required_int(record, "decision_us")
    anchor_us = _required_int(record, "anchor_us")
    entry_row = _required_int(record, "entry_row")
    exit_row = _optional_int(record.get("exit_row"))
    gap_invalid = bool(record["gap_invalid"])
    day_start, _ = _day_bounds_us(source_day)
    feature_window_crosses_day = anchor_us < day_start

    entry_bid = _as_decimal(record.get("entry_bid"))
    entry_ask = _as_decimal(record.get("entry_ask"))
    exit_bid = _as_decimal(record.get("exit_bid"))
    exit_ask = _as_decimal(record.get("exit_ask"))

    decision_reasons = _bbo_invalid_reasons(entry_bid, entry_ask, "ENTRY")
    outcome_reasons: list[str] = []
    if gap_invalid:
        outcome_reasons.append("HISTORICAL_BOOK_GAP_EXCEEDS_15S")
    if exit_row is None:
        outcome_reasons.append("HORIZON_EXIT_UNAVAILABLE_WITHIN_UTC_DAY")
    else:
        outcome_reasons.extend(_bbo_invalid_reasons(exit_bid, exit_ask, "EXIT"))

    bid_amounts = tuple(_as_decimal(record.get(f"bid_amount_{index}")) for index in range(5))
    ask_amounts = tuple(_as_decimal(record.get(f"ask_amount_{index}")) for index in range(5))
    hl_bbo_imbalance = _imbalance(bid_amounts[:1], ask_amounts[:1])
    hl_depth_imbalance = _imbalance(bid_amounts, ask_amounts)
    spread_bps = _spread_bps(entry_bid, entry_ask)

    hl_return: Decimal | None = None
    binance_return: Decimal | None = None
    hl_flow: Decimal | None = None
    binance_flow: Decimal | None = None
    if not feature_window_crosses_day:
        hl_return = _mid_return_bps(
            current_ts=decision_us,
            current_bid=entry_bid,
            current_ask=entry_ask,
            current_target_us=decision_us,
            anchor_ts=_optional_int(record.get("hl_anchor_ts")),
            anchor_bid=_as_decimal(record.get("hl_anchor_bid")),
            anchor_ask=_as_decimal(record.get("hl_anchor_ask")),
            anchor_target_us=anchor_us,
        )
        binance_return = _mid_return_bps(
            current_ts=_optional_int(record.get("bin_current_ts")),
            current_bid=_as_decimal(record.get("bin_current_bid")),
            current_ask=_as_decimal(record.get("bin_current_ask")),
            current_target_us=decision_us,
            anchor_ts=_optional_int(record.get("bin_anchor_ts")),
            anchor_bid=_as_decimal(record.get("bin_anchor_bid")),
            anchor_ask=_as_decimal(record.get("bin_anchor_ask")),
            anchor_target_us=anchor_us,
        )
        hl_flow = _trade_flow(
            current_buy=_as_decimal(record.get("hl_cur_buy")),
            current_sell=_as_decimal(record.get("hl_cur_sell")),
            current_unknown=_optional_int(record.get("hl_cur_unknown")),
            start_buy=_as_decimal(record.get("hl_start_buy")),
            start_sell=_as_decimal(record.get("hl_start_sell")),
            start_unknown=_optional_int(record.get("hl_start_unknown")),
        )
        binance_flow = _trade_flow(
            current_buy=_as_decimal(record.get("bin_cur_buy")),
            current_sell=_as_decimal(record.get("bin_cur_sell")),
            current_unknown=_optional_int(record.get("bin_cur_unknown")),
            start_buy=_as_decimal(record.get("bin_start_buy")),
            start_sell=_as_decimal(record.get("bin_start_sell")),
            start_unknown=_optional_int(record.get("bin_start_unknown")),
        )

    cross_venue = (
        None if hl_return is None or binance_return is None else hl_return - binance_return
    )
    row_id_payload = (f"{protocol_sha256()}|{source_day}|{horizon}|{entry_row}|{exit_row}").encode()
    row_id = f"tardis-hist-row-{hashlib.sha256(row_id_payload).hexdigest()[:24]}"

    return {
        "source_day": source_day,
        "horizon_seconds": horizon,
        "decision_local_timestamp_us": decision_us,
        "entry_source_row_number": entry_row,
        "exit_source_row_number": exit_row,
        "row_id": row_id,
        "decision_recv_wall_ns": decision_us * 1000,
        "invalid_reasons": sorted(set(decision_reasons)),
        "entry_bid": _optional(entry_bid),
        "entry_ask": _optional(entry_ask),
        "exit_bid": _optional(exit_bid),
        "exit_ask": _optional(exit_ask),
        "hl_spread_bps": _optional(spread_bps),
        "hl_bbo_imbalance": _optional(hl_bbo_imbalance),
        "binance_mid_return_5s_bps": _optional(binance_return),
        "outcome_invalid_reasons": sorted(set(outcome_reasons)),
        "hl_depth_imbalance_top5": _optional(hl_depth_imbalance),
        "hl_aggressive_trade_flow_5s": _optional(hl_flow),
        "binance_aggressive_trade_flow_5s": _optional(binance_flow),
        "hl_mid_return_5s_bps": _optional(hl_return),
        "cross_venue_return_gap_5s_bps": _optional(cross_venue),
    }


def _bbo_invalid_reasons(
    bid: Decimal | None,
    ask: Decimal | None,
    prefix: str,
) -> list[str]:
    if bid is None or ask is None:
        return [f"{prefix}_BBO_SIDE_MISSING"]
    if bid <= 0 or ask <= 0:
        return [f"{prefix}_BBO_NONPOSITIVE"]
    if ask <= bid:
        return [f"{prefix}_BBO_CROSSED_OR_LOCKED"]
    return []


def _imbalance(
    bid_amounts: tuple[Decimal | None, ...],
    ask_amounts: tuple[Decimal | None, ...],
) -> Decimal | None:
    if not bid_amounts or len(bid_amounts) != len(ask_amounts):
        return None
    if any(item is None for item in (*bid_amounts, *ask_amounts)):
        return None
    bids = tuple(cast(Decimal, item) for item in bid_amounts)
    asks = tuple(cast(Decimal, item) for item in ask_amounts)
    bid_total = sum(bids, _ZERO)
    ask_total = sum(asks, _ZERO)
    denominator = bid_total + ask_total
    if denominator <= 0:
        return None
    with localcontext() as ctx:
        ctx.prec = 60
        return (bid_total - ask_total) / denominator


def _spread_bps(bid: Decimal | None, ask: Decimal | None) -> Decimal | None:
    mid = _mid(bid, ask)
    if mid is None or bid is None or ask is None:
        return None
    with localcontext() as ctx:
        ctx.prec = 60
        return (ask - bid) / mid * _BPS


def _mid(bid: Decimal | None, ask: Decimal | None) -> Decimal | None:
    if bid is None or ask is None or bid <= 0 or ask <= bid:
        return None
    with localcontext() as ctx:
        ctx.prec = 60
        return (bid + ask) / Decimal(2)


def _mid_return_bps(
    *,
    current_ts: int | None,
    current_bid: Decimal | None,
    current_ask: Decimal | None,
    current_target_us: int,
    anchor_ts: int | None,
    anchor_bid: Decimal | None,
    anchor_ask: Decimal | None,
    anchor_target_us: int,
) -> Decimal | None:
    if current_ts is None or anchor_ts is None:
        return None
    if current_ts > current_target_us or anchor_ts > anchor_target_us:
        raise TardisHistoricalTrainingError("ASOF source leaks future local_timestamp")
    if (
        current_target_us - current_ts > MAX_FEATURE_STALENESS_US
        or anchor_target_us - anchor_ts > MAX_FEATURE_STALENESS_US
    ):
        return None
    current_mid = _mid(current_bid, current_ask)
    anchor_mid = _mid(anchor_bid, anchor_ask)
    if current_mid is None or anchor_mid is None:
        return None
    with localcontext() as ctx:
        ctx.prec = 60
        return (current_mid / anchor_mid - Decimal(1)) * _BPS


def _trade_flow(
    *,
    current_buy: Decimal | None,
    current_sell: Decimal | None,
    current_unknown: int | None,
    start_buy: Decimal | None,
    start_sell: Decimal | None,
    start_unknown: int | None,
) -> Decimal | None:
    if current_buy is None or current_sell is None or current_unknown is None:
        return None
    start_buy_value = _ZERO if start_buy is None else start_buy
    start_sell_value = _ZERO if start_sell is None else start_sell
    start_unknown_value = 0 if start_unknown is None else start_unknown
    buy = current_buy - start_buy_value
    sell = current_sell - start_sell_value
    unknown = current_unknown - start_unknown_value
    if buy < 0 or sell < 0 or unknown < 0:
        raise TardisHistoricalTrainingError("trade cumulative values decreased")
    if unknown > 0:
        return None
    denominator = buy + sell
    if denominator <= 0:
        return None
    with localcontext() as ctx:
        ctx.prec = 60
        return (buy - sell) / denominator


def load_feature_cache(
    path: str | Path,
    *,
    horizon_seconds: int,
    expected_sha256: str | None = None,
) -> tuple[str, tuple[CachedHistoricalRow, ...]]:
    raw = Path(path).read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    if expected_sha256 is not None and digest != expected_sha256:
        raise TardisHistoricalTrainingError("historical feature cache SHA mismatch")
    payload = json.loads(raw)
    if not isinstance(payload, dict):
        raise TardisHistoricalTrainingError("historical feature cache root must be object")
    obj = cast(dict[str, object], payload)
    if obj.get("cache_version") != CACHE_VERSION:
        raise TardisHistoricalTrainingError("historical feature cache version mismatch")
    if obj.get("protocol_sha256") != protocol_sha256():
        raise TardisHistoricalTrainingError("historical feature protocol SHA mismatch")
    if obj.get("lakehouse_manifest_sha256") != LAKEHOUSE_MANIFEST_SHA256:
        raise TardisHistoricalTrainingError("historical feature lakehouse SHA mismatch")
    if obj.get("parquet_set_sha256") != PARQUET_SET_SHA256:
        raise TardisHistoricalTrainingError("historical feature Parquet-set SHA mismatch")
    if obj.get("horizon_seconds") != horizon_seconds:
        raise TardisHistoricalTrainingError("historical feature horizon mismatch")
    raw_rows = obj.get("rows")
    if not isinstance(raw_rows, list):
        raise TardisHistoricalTrainingError("historical feature rows must be a list")

    allowed_days = set((*DEV_A_DAYS, *DEV_B_DAYS))
    day_order = {day: index for index, day in enumerate((*DEV_A_DAYS, *DEV_B_DAYS))}
    rows: list[CachedHistoricalRow] = []
    seen_ids: set[str] = set()
    for item in raw_rows:
        if not isinstance(item, dict):
            raise TardisHistoricalTrainingError("historical feature row must be object")
        row_obj = cast(dict[str, object], item)
        source_day = _required_string(row_obj, "source_day")
        if source_day not in allowed_days:
            raise TardisHistoricalTrainingError("historical feature row day is not frozen")
        if _required_int(row_obj, "horizon_seconds") != horizon_seconds:
            raise TardisHistoricalTrainingError("historical row horizon differs from cache")
        micro = MicrostructureRow.from_dict(row_obj)
        if micro.base.row_id in seen_ids:
            raise TardisHistoricalTrainingError("historical feature row_id duplicated")
        seen_ids.add(micro.base.row_id)
        rows.append(
            CachedHistoricalRow(
                source_day=source_day,
                horizon_seconds=horizon_seconds,
                row=micro,
            )
        )
    ordered = tuple(
        sorted(
            rows,
            key=lambda item: (
                day_order[item.source_day],
                item.row.base.decision_recv_wall_ns,
                item.row.base.row_id,
            ),
        )
    )
    return digest, ordered


def partition_historical_rows(
    rows: tuple[CachedHistoricalRow, ...],
) -> tuple[tuple[MicrostructureRow, ...], tuple[MicrostructureRow, ...]]:
    dev_a = tuple(item.row for item in rows if item.source_day in set(DEV_A_DAYS))
    dev_b = tuple(item.row for item in rows if item.source_day in set(DEV_B_DAYS))
    if len(dev_a) + len(dev_b) != len(rows):
        raise TardisHistoricalTrainingError("historical row outside frozen DEV_A/DEV_B split")
    if not dev_a or not dev_b:
        raise TardisHistoricalTrainingError("historical DEV_A/DEV_B partition is empty")
    return dev_a, dev_b


def summarize_support(
    rows: tuple[MicrostructureRow, ...],
    *,
    horizon_seconds: int,
) -> HorizonSupport:
    feature_complete = 0
    valid = 0
    positive = 0
    nonpositive = 0
    for row in rows:
        values = feature_vector(row)
        if values is None:
            continue
        feature_complete += 1
        economics = executable_known_net(row.base, action=h2_direction(row))
        if economics is None:
            continue
        valid += 1
        if economics[2] > 0:
            positive += 1
        else:
            nonpositive += 1
    min_valid = 300 if horizon_seconds == 50 else 80
    supported = valid >= min_valid and positive >= 30 and nonpositive >= 30
    return HorizonSupport(
        horizon_seconds=horizon_seconds,
        feature_complete_count=feature_complete,
        valid_target_count=valid,
        positive_target_count=positive,
        nonpositive_target_count=nonpositive,
        supported=supported,
    )


def fit_historical_model(
    rows: tuple[MicrostructureRow, ...],
    *,
    horizon_seconds: int,
    cache_sha256: str,
    support: HorizonSupport,
) -> FrozenMicrostructureModel:
    if not support.supported:
        raise TardisHistoricalTrainingError("cannot fit unsupported historical horizon")
    samples: list[tuple[tuple[Decimal, ...], int, Decimal]] = []
    for row in rows:
        values = feature_vector(row)
        direction = h2_direction(row)
        economics = executable_known_net(row.base, action=direction)
        if values is None or direction == 0 or economics is None:
            continue
        known_net = economics[2]
        samples.append((values, int(known_net > 0), known_net))
    if len(samples) != support.valid_target_count:
        raise TardisHistoricalTrainingError("DEV_A support changed during model preparation")

    raw_x = tuple(item[0] for item in samples)
    targets = tuple(item[1] for item in samples)
    positives = tuple(item[2] for item in samples if item[1] == 1)
    nonpositives = tuple(item[2] for item in samples if item[1] == 0)
    standardization = fit_standardization(raw_x)
    design = tuple((Decimal(1), *standardization.transform(values)) for values in raw_x)
    coefficients, iterations = fit_logistic(design, targets)
    mean_positive = _mean(positives)
    mean_nonpositive = _mean(nonpositives)
    hurdle = expected_value_hurdle(
        mean_positive=mean_positive,
        mean_nonpositive=mean_nonpositive,
    )
    return FrozenMicrostructureModel(
        horizon_seconds=horizon_seconds,
        training_source_sha256=cache_sha256,
        feature_complete_count=support.feature_complete_count,
        training_sample_count=support.valid_target_count,
        standardization=standardization,
        coefficients=coefficients,
        iterations=iterations,
        economic_probability_hurdle=hurdle,
        mean_positive_known_net_quote=mean_positive,
        mean_nonpositive_known_net_quote=mean_nonpositive,
    )


def evaluate_dev_b(
    model: FrozenMicrostructureModel,
    rows: tuple[MicrostructureRow, ...],
) -> DevBEvaluation:
    eligible = 0
    selected: list[tuple[Decimal, Decimal]] = []
    positive = 0
    for row in rows:
        if feature_vector(row) is None:
            continue
        eligible += 1
        action = model.action(row)
        economics = executable_known_net(row.base, action=action)
        if economics is None:
            continue
        net = economics[2]
        net_bps = economics[3]
        selected.append((net, net_bps))
        positive += int(net > 0)

    if not selected:
        return DevBEvaluation(
            eligible_rows=eligible,
            selected_trades=0,
            positive_selected_trades=0,
            mean_known_net_quote=None,
            cumulative_known_net_quote=_ZERO,
            mean_known_net_bps=None,
            median_known_net_bps=None,
            early_selected_trades=0,
            late_selected_trades=0,
            early_mean_known_net_quote=None,
            late_mean_known_net_quote=None,
            passed=False,
        )

    nets = tuple(item[0] for item in selected)
    bps = tuple(item[1] for item in selected)
    split = len(selected) // 2
    early_nets = nets[:split]
    late_nets = nets[split:]
    min_selected = 50 if model.horizon_seconds == 50 else 30
    min_half = 25 if model.horizon_seconds == 50 else 15
    mean_net = _mean(nets)
    cumulative = sum(nets, _ZERO)
    mean_bps = _mean(bps)
    median_bps = median(bps)
    early_mean = None if not early_nets else _mean(early_nets)
    late_mean = None if not late_nets else _mean(late_nets)
    passed = (
        len(selected) >= min_selected
        and len(early_nets) >= min_half
        and len(late_nets) >= min_half
        and mean_net > 0
        and cumulative > 0
        and median_bps > 0
        and early_mean is not None
        and early_mean > 0
        and late_mean is not None
        and late_mean > 0
    )
    return DevBEvaluation(
        eligible_rows=eligible,
        selected_trades=len(selected),
        positive_selected_trades=positive,
        mean_known_net_quote=mean_net,
        cumulative_known_net_quote=cumulative,
        mean_known_net_bps=mean_bps,
        median_known_net_bps=median_bps,
        early_selected_trades=len(early_nets),
        late_selected_trades=len(late_nets),
        early_mean_known_net_quote=early_mean,
        late_mean_known_net_quote=late_mean,
        passed=passed,
    )


def evaluate_horizon(
    cached_rows: tuple[CachedHistoricalRow, ...],
    *,
    horizon_seconds: int,
    cache_sha256: str,
) -> HorizonDevelopmentResult:
    dev_a, dev_b = partition_historical_rows(cached_rows)
    support = summarize_support(dev_a, horizon_seconds=horizon_seconds)
    if not support.supported:
        return HorizonDevelopmentResult(
            horizon_seconds=horizon_seconds,
            cache_sha256=cache_sha256,
            dev_a_row_count=len(dev_a),
            dev_b_row_count=len(dev_b),
            support=support,
            model=None,
            dev_b_evaluation=None,
        )
    model = fit_historical_model(
        dev_a,
        horizon_seconds=horizon_seconds,
        cache_sha256=cache_sha256,
        support=support,
    )
    evaluation = evaluate_dev_b(model, dev_b)
    return HorizonDevelopmentResult(
        horizon_seconds=horizon_seconds,
        cache_sha256=cache_sha256,
        dev_a_row_count=len(dev_a),
        dev_b_row_count=len(dev_b),
        support=support,
        model=model,
        dev_b_evaluation=evaluation,
    )


def evaluate_historical_development(
    *,
    feature_root: str | Path,
    feature_build_report_sha256: str,
    expected_cache_50s_sha256: str,
    expected_cache_300s_sha256: str,
) -> HistoricalDevelopmentReport:
    root = Path(feature_root)
    sha50, rows50 = load_feature_cache(
        root / "historical-features-50s.json",
        horizon_seconds=50,
        expected_sha256=expected_cache_50s_sha256,
    )
    sha300, rows300 = load_feature_cache(
        root / "historical-features-300s.json",
        horizon_seconds=300,
        expected_sha256=expected_cache_300s_sha256,
    )
    result50 = evaluate_horizon(
        rows50,
        horizon_seconds=50,
        cache_sha256=sha50,
    )
    result300 = evaluate_horizon(
        rows300,
        horizon_seconds=300,
        cache_sha256=sha300,
    )
    passing = [
        result
        for result in (result50, result300)
        if result.dev_b_evaluation is not None and result.dev_b_evaluation.passed
    ]
    selected_horizon: int | None = None
    if passing:
        passing.sort(
            key=lambda item: (
                -cast(Decimal, cast(DevBEvaluation, item.dev_b_evaluation).mean_known_net_bps),
                item.horizon_seconds,
            )
        )
        selected_horizon = passing[0].horizon_seconds
    decision = (
        "FREEZE_ONE_HISTORICAL_DEVELOPMENT_CANDIDATE_FOR_FUTURE_FRESH_PROSPECTIVE_SELECTION"
        if selected_horizon is not None
        else "STOP_HISTORICAL_MICROSTRUCTURE_DEVELOPMENT"
    )
    return HistoricalDevelopmentReport(
        feature_build_report_sha256=feature_build_report_sha256,
        cache_50s_sha256=sha50,
        cache_300s_sha256=sha300,
        horizon_50s=result50,
        horizon_300s=result300,
        decision=decision,
        selected_horizon_seconds=selected_horizon,
    )


def write_feature_build_report(
    report: FeatureCacheBuildReport,
    path: str | Path,
) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    _write_immutable(target, report.to_json_bytes())
    return target


def load_feature_build_report(
    path: str | Path,
    *,
    expected_sha256: str | None = None,
) -> tuple[str, str, str]:
    raw = Path(path).read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    if expected_sha256 is not None and digest != expected_sha256:
        raise TardisHistoricalTrainingError("feature-build report SHA mismatch")
    payload = json.loads(raw)
    if not isinstance(payload, dict):
        raise TardisHistoricalTrainingError("feature-build report root must be object")
    obj = cast(dict[str, object], payload)
    if obj.get("report_version") != "stage2-task029-feature-cache-build-v1":
        raise TardisHistoricalTrainingError("feature-build report version mismatch")
    if obj.get("protocol_sha256") != protocol_sha256():
        raise TardisHistoricalTrainingError("feature-build protocol SHA mismatch")
    if obj.get("lakehouse_manifest_sha256") != LAKEHOUSE_MANIFEST_SHA256:
        raise TardisHistoricalTrainingError("feature-build lakehouse SHA mismatch")
    if obj.get("parquet_set_sha256") != PARQUET_SET_SHA256:
        raise TardisHistoricalTrainingError("feature-build Parquet-set SHA mismatch")
    if obj.get("economic_summary_computed") is not False:
        raise TardisHistoricalTrainingError("feature-build report consumed economic summary")
    if obj.get("model_fitted") is not False:
        raise TardisHistoricalTrainingError("feature-build report fitted a model")
    sha50 = obj.get("cache_50s_sha256")
    sha300 = obj.get("cache_300s_sha256")
    if not isinstance(sha50, str) or len(sha50) != 64:
        raise TardisHistoricalTrainingError("feature-build 50s cache SHA invalid")
    if not isinstance(sha300, str) or len(sha300) != 64:
        raise TardisHistoricalTrainingError("feature-build 300s cache SHA invalid")
    return digest, sha50, sha300


def write_development_report(
    report: HistoricalDevelopmentReport,
    path: str | Path,
) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    _write_immutable(target, report.to_json_bytes())
    return target


def _day_bounds_us(day_text: str) -> tuple[int, int]:
    start = datetime.fromisoformat(day_text).replace(tzinfo=UTC)
    end = start + timedelta(days=1)
    return int(start.timestamp()) * 1_000_000, int(end.timestamp()) * 1_000_000


def _required_string(payload: dict[str, object], field: str) -> str:
    value = payload.get(field)
    if not isinstance(value, str) or not value:
        raise TardisHistoricalTrainingError(f"{field} must be a non-empty string")
    return value


def _required_int(payload: dict[str, object], field: str) -> int:
    value = payload.get(field)
    if isinstance(value, bool) or not isinstance(value, int):
        raise TardisHistoricalTrainingError(f"{field} must be an integer")
    return value


def _optional_int(value: object) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise TardisHistoricalTrainingError("expected integer or null")
    return value


def _as_decimal(value: object) -> Decimal | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return value
    if isinstance(value, int) and not isinstance(value, bool):
        return Decimal(value)
    if isinstance(value, str):
        return Decimal(value)
    raise TardisHistoricalTrainingError("expected exact Decimal-compatible value")


def _optional(value: Decimal | None) -> str | None:
    return None if value is None else serialize_exact_decimal(value)


def _mean(values: tuple[Decimal, ...]) -> Decimal:
    if not values:
        raise TardisHistoricalTrainingError("cannot average empty values")
    with localcontext() as ctx:
        ctx.prec = 60
        return sum(values, _ZERO) / Decimal(len(values))


def _json_bytes(value: object) -> bytes:
    return (
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n"
    ).encode()


def _write_immutable(path: Path, payload: bytes) -> None:
    try:
        with path.open("xb") as stream:
            stream.write(payload)
            stream.flush()
    except FileExistsError:
        if path.read_bytes() != payload:
            raise TardisHistoricalTrainingError(
                f"existing immutable TASK-029 file differs: {path}"
            ) from None
