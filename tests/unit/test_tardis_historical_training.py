from __future__ import annotations

import json
from decimal import Decimal, localcontext
from pathlib import Path

import duckdb
import pytest

from cryptobot.research import tardis_historical_training as ht
from cryptobot.research import tardis_training_protocol as tp
from cryptobot.research.economic_family import EconomicDevelopmentRow
from cryptobot.research.microstructure_family import (
    FrozenMicrostructureModel,
    MicrostructureRow,
    Standardization,
    feature_vector,
)


def _micro_row(index: int, *, positive: bool = True) -> MicrostructureRow:
    tweak = Decimal(index % 7) / Decimal("1000")
    base = EconomicDevelopmentRow(
        row_id=f"row-{index}",
        decision_recv_wall_ns=1_730_000_000_000_000_000 + index,
        invalid_reasons=(),
        entry_bid=Decimal("99"),
        entry_ask=Decimal("100"),
        exit_bid=Decimal("101") if positive else Decimal("99.9"),
        exit_ask=Decimal("102"),
        hl_spread_bps=Decimal("1") + tweak,
        hl_bbo_imbalance=Decimal("0.2") + tweak,
        binance_mid_return_5s_bps=Decimal("0.3") + tweak,
        outcome_invalid_reasons=(),
    )
    return MicrostructureRow(
        base=base,
        hl_depth_imbalance_top5=Decimal("0.1") + tweak,
        hl_aggressive_trade_flow_5s=Decimal("0.15") + tweak,
        binance_aggressive_trade_flow_5s=Decimal("0.12") + tweak,
        hl_mid_return_5s_bps=Decimal("0.25") + tweak,
        cross_venue_return_gap_5s_bps=Decimal("-0.05") + tweak,
    )


def test_build_opportunities_is_nonoverlapping_and_flags_15s_gap() -> None:
    rows = tuple(range(11))
    timestamps = tuple(index * 10_000_000 for index in range(11))

    opportunities = ht.build_opportunities(
        source_day="2025-01-01",
        source_rows=rows,
        timestamps_us=timestamps,
        horizon_seconds=50,
    )

    assert [(item.entry_row, item.exit_row) for item in opportunities] == [
        (0, 5),
        (6, None),
    ]
    assert opportunities[0].gap_invalid is False

    gapped = ht.build_opportunities(
        source_day="2025-01-01",
        source_rows=(0, 1, 2, 3),
        timestamps_us=(0, 10_000_000, 30_000_001, 50_000_000),
        horizon_seconds=50,
    )
    assert gapped[0].exit_row == 3
    assert gapped[0].gap_invalid is True


def test_trade_flow_is_exact_and_unknown_side_window_is_missing() -> None:
    value = ht._trade_flow(
        current_buy=Decimal("10"),
        current_sell=Decimal("5"),
        current_unknown=0,
        start_buy=Decimal("4"),
        start_sell=Decimal("3"),
        start_unknown=0,
    )
    assert value == Decimal("0.5")

    assert (
        ht._trade_flow(
            current_buy=Decimal("10"),
            current_sell=Decimal("5"),
            current_unknown=1,
            start_buy=Decimal("4"),
            start_sell=Decimal("3"),
            start_unknown=0,
        )
        is None
    )


def test_mid_return_enforces_frozen_two_second_staleness() -> None:
    fresh = ht._mid_return_bps(
        current_ts=10_000_000,
        current_bid=Decimal("101"),
        current_ask=Decimal("102"),
        current_target_us=10_000_000,
        anchor_ts=5_000_000,
        anchor_bid=Decimal("100"),
        anchor_ask=Decimal("101"),
        anchor_target_us=5_000_000,
    )
    assert fresh is not None
    assert fresh > 0

    stale = ht._mid_return_bps(
        current_ts=7_999_999,
        current_bid=Decimal("101"),
        current_ask=Decimal("102"),
        current_target_us=10_000_000,
        anchor_ts=5_000_000,
        anchor_bid=Decimal("100"),
        anchor_ask=Decimal("101"),
        anchor_target_us=5_000_000,
    )
    assert stale is None


def test_mid_return_rejects_future_asof_leakage() -> None:
    with pytest.raises(ht.TardisHistoricalTrainingError, match="leaks future"):
        ht._mid_return_bps(
            current_ts=10_000_001,
            current_bid=Decimal("101"),
            current_ask=Decimal("102"),
            current_target_us=10_000_000,
            anchor_ts=5_000_000,
            anchor_bid=Decimal("100"),
            anchor_ask=Decimal("101"),
            anchor_target_us=5_000_000,
        )


def test_build_cache_row_preserves_frozen_feature_semantics() -> None:
    day_start, _ = ht._day_bounds_us("2025-01-01")
    decision = day_start + 10_000_000
    anchor = decision - 5_000_000
    record: dict[str, object] = {
        "source_day": "2025-01-01",
        "horizon_seconds": 50,
        "entry_row": 10,
        "exit_row": 20,
        "decision_us": decision,
        "anchor_us": anchor,
        "gap_invalid": False,
        "entry_bid": Decimal("100"),
        "entry_ask": Decimal("101"),
        "exit_bid": Decimal("102"),
        "exit_ask": Decimal("103"),
        "bid_amount_0": Decimal("6"),
        "ask_amount_0": Decimal("4"),
        "bid_amount_1": Decimal("5"),
        "ask_amount_1": Decimal("4"),
        "bid_amount_2": Decimal("4"),
        "ask_amount_2": Decimal("4"),
        "bid_amount_3": Decimal("3"),
        "ask_amount_3": Decimal("4"),
        "bid_amount_4": Decimal("2"),
        "ask_amount_4": Decimal("4"),
        "exit_ts": decision + 50_000_000,
        "hl_anchor_ts": anchor,
        "hl_anchor_bid": Decimal("99"),
        "hl_anchor_ask": Decimal("100"),
        "bin_current_ts": decision - 100_000,
        "bin_current_bid": Decimal("201"),
        "bin_current_ask": Decimal("202"),
        "bin_anchor_ts": anchor,
        "bin_anchor_bid": Decimal("200"),
        "bin_anchor_ask": Decimal("201"),
        "hl_cur_buy": Decimal("10"),
        "hl_cur_sell": Decimal("5"),
        "hl_cur_unknown": 0,
        "hl_start_buy": Decimal("4"),
        "hl_start_sell": Decimal("3"),
        "hl_start_unknown": 0,
        "bin_cur_buy": Decimal("20"),
        "bin_cur_sell": Decimal("10"),
        "bin_cur_unknown": 0,
        "bin_start_buy": Decimal("10"),
        "bin_start_sell": Decimal("5"),
        "bin_start_unknown": 0,
    }

    row = ht._build_cache_row(record)

    assert row["invalid_reasons"] == []
    assert row["outcome_invalid_reasons"] == []
    assert Decimal(str(row["hl_bbo_imbalance"])) == Decimal("0.2")
    assert Decimal(str(row["hl_depth_imbalance_top5"])) == Decimal("0")
    assert Decimal(str(row["hl_aggressive_trade_flow_5s"])) == Decimal("0.5")
    with localcontext() as ctx:
        ctx.prec = 60
        expected_binance_flow = Decimal(1) / Decimal(3)
    assert Decimal(str(row["binance_aggressive_trade_flow_5s"])) == expected_binance_flow
    assert row["hl_mid_return_5s_bps"] is not None
    assert row["binance_mid_return_5s_bps"] is not None
    assert row["cross_venue_return_gap_5s_bps"] is not None


def test_build_cache_row_forbids_cross_day_feature_window() -> None:
    day_start, _ = ht._day_bounds_us("2025-01-01")
    record: dict[str, object] = {
        "source_day": "2025-01-01",
        "horizon_seconds": 50,
        "entry_row": 0,
        "exit_row": None,
        "decision_us": day_start + 1_000_000,
        "anchor_us": day_start - 4_000_000,
        "gap_invalid": False,
        "entry_bid": Decimal("100"),
        "entry_ask": Decimal("101"),
        "exit_bid": None,
        "exit_ask": None,
        **{f"bid_amount_{i}": Decimal("1") for i in range(5)},
        **{f"ask_amount_{i}": Decimal("1") for i in range(5)},
    }

    row = ht._build_cache_row(record)

    assert row["hl_mid_return_5s_bps"] is None
    assert row["binance_mid_return_5s_bps"] is None
    assert row["hl_aggressive_trade_flow_5s"] is None
    assert row["binance_aggressive_trade_flow_5s"] is None
    assert row["outcome_invalid_reasons"] == ["HORIZON_EXIT_UNAVAILABLE_WITHIN_UTC_DAY"]


def test_support_uses_valid_target_and_30_30_class_minimums() -> None:
    rows = tuple(_micro_row(index, positive=index % 2 == 0) for index in range(300))
    support = ht.summarize_support(rows, horizon_seconds=50)

    assert support.feature_complete_count == 300
    assert support.valid_target_count == 300
    assert support.positive_target_count == 150
    assert support.nonpositive_target_count == 150
    assert support.supported is True


def test_dev_b_pass_requires_selected_support_and_both_halves_positive() -> None:
    model = FrozenMicrostructureModel(
        horizon_seconds=50,
        training_source_sha256="a" * 64,
        feature_complete_count=300,
        training_sample_count=300,
        standardization=Standardization(
            means=tuple(Decimal("0") for _ in range(8)),
            scales=tuple(Decimal("1") for _ in range(8)),
        ),
        coefficients=(Decimal("1"), *tuple(Decimal("0") for _ in range(8))),
        iterations=1,
        economic_probability_hurdle=Decimal("0.5"),
        mean_positive_known_net_quote=Decimal("1"),
        mean_nonpositive_known_net_quote=Decimal("-1"),
    )
    rows = tuple(_micro_row(index, positive=True) for index in range(50))

    evaluation = ht.evaluate_dev_b(model, rows)

    assert evaluation.selected_trades == 50
    assert evaluation.early_selected_trades == 25
    assert evaluation.late_selected_trades == 25
    assert evaluation.mean_known_net_quote is not None
    assert evaluation.mean_known_net_quote > 0
    assert evaluation.passed is True


def test_feature_cache_builder_executes_frozen_duckdb_enrichment(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    catalog = tmp_path / "synthetic.duckdb"
    connection = duckdb.connect(str(catalog))
    connection.execute(
        """
        CREATE TABLE hl_book_snapshot_5(
            source_row_number BIGINT,
            local_timestamp_us BIGINT,
            ask_price_0 DECIMAL(38,18),
            ask_amount_0 DECIMAL(38,18),
            bid_price_0 DECIMAL(38,18),
            bid_amount_0 DECIMAL(38,18),
            ask_amount_1 DECIMAL(38,18),
            bid_amount_1 DECIMAL(38,18),
            ask_amount_2 DECIMAL(38,18),
            bid_amount_2 DECIMAL(38,18),
            ask_amount_3 DECIMAL(38,18),
            bid_amount_3 DECIMAL(38,18),
            ask_amount_4 DECIMAL(38,18),
            bid_amount_4 DECIMAL(38,18)
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE binance_quotes(
            source_row_number BIGINT,
            local_timestamp_us BIGINT,
            bid_price DECIMAL(38,18),
            ask_price DECIMAL(38,18)
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE hl_trades(
            local_timestamp_us BIGINT,
            side VARCHAR,
            amount DECIMAL(38,18)
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE binance_trades(
            local_timestamp_us BIGINT,
            side VARCHAR,
            amount DECIMAL(38,18)
        )
        """
    )

    day_start, _ = ht._day_bounds_us("2025-01-01")
    book_rows = []
    for index in range(401):
        timestamp = day_start + index * 1_000_000
        mid = Decimal("100") + Decimal(index) / Decimal("100")
        book_rows.append(
            (
                index,
                timestamp,
                mid + Decimal("0.5"),
                Decimal("4"),
                mid - Decimal("0.5"),
                Decimal("6"),
                Decimal("4"),
                Decimal("5"),
                Decimal("4"),
                Decimal("4"),
                Decimal("4"),
                Decimal("3"),
                Decimal("4"),
                Decimal("2"),
            )
        )
    connection.executemany(
        "INSERT INTO hl_book_snapshot_5 VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        book_rows,
    )

    quote_rows = []
    trade_rows = []
    for index in range(401):
        timestamp = day_start + index * 1_000_000
        mid = Decimal("200") + Decimal(index) / Decimal("1000")
        quote_rows.append((index, timestamp, mid - Decimal("0.05"), mid + Decimal("0.05")))
        side = "buy" if index % 2 == 0 else "sell"
        trade_rows.append((timestamp, side, Decimal("1")))
    connection.executemany("INSERT INTO binance_quotes VALUES (?,?,?,?)", quote_rows)
    connection.executemany("INSERT INTO hl_trades VALUES (?,?,?)", trade_rows)
    connection.executemany("INSERT INTO binance_trades VALUES (?,?,?)", trade_rows)
    connection.close()

    monkeypatch.setattr(ht, "DEV_A_DAYS", ("2025-01-01",))
    monkeypatch.setattr(ht, "DEV_B_DAYS", ())
    monkeypatch.setattr(ht, "verify_lakehouse_manifest", lambda path: {})

    output = tmp_path / "features"
    report = ht.build_feature_caches(
        catalog_path=catalog,
        lakehouse_manifest_path=tmp_path / "ignored.json",
        output_root=output,
    )

    assert report.row_count_50s == 8
    assert report.row_count_300s == 2
    assert report.cache_50s_sha256 != report.cache_300s_sha256
    sha50, rows50 = ht.load_feature_cache(
        output / "historical-features-50s.json",
        horizon_seconds=50,
        expected_sha256=report.cache_50s_sha256,
    )
    assert sha50 == report.cache_50s_sha256
    assert len(rows50) == 8
    assert rows50[-1].row.base.outcome_invalid_reasons == (
        "HORIZON_EXIT_UNAVAILABLE_WITHIN_UTC_DAY",
    )
    assert any(feature_vector(item.row) is not None for item in rows50)


def test_development_report_binds_feature_build_report_sha() -> None:
    support_50 = ht.HorizonSupport(
        horizon_seconds=50,
        feature_complete_count=0,
        valid_target_count=0,
        positive_target_count=0,
        nonpositive_target_count=0,
        supported=False,
    )
    support_300 = ht.HorizonSupport(
        horizon_seconds=300,
        feature_complete_count=0,
        valid_target_count=0,
        positive_target_count=0,
        nonpositive_target_count=0,
        supported=False,
    )
    result_50 = ht.HorizonDevelopmentResult(
        horizon_seconds=50,
        cache_sha256="a" * 64,
        dev_a_row_count=1,
        dev_b_row_count=1,
        support=support_50,
        model=None,
        dev_b_evaluation=None,
    )
    result_300 = ht.HorizonDevelopmentResult(
        horizon_seconds=300,
        cache_sha256="b" * 64,
        dev_a_row_count=1,
        dev_b_row_count=1,
        support=support_300,
        model=None,
        dev_b_evaluation=None,
    )
    report = ht.HistoricalDevelopmentReport(
        feature_build_report_sha256="f" * 64,
        cache_50s_sha256="a" * 64,
        cache_300s_sha256="b" * 64,
        horizon_50s=result_50,
        horizon_300s=result_300,
        decision="STOP_HISTORICAL_MICROSTRUCTURE_DEVELOPMENT",
        selected_horizon_seconds=None,
    )

    payload = report.as_dict()
    assert payload["feature_build_report_sha256"] == "f" * 64
    assert payload["current_task027_repurposed_as_selection"] is False
    assert payload["old_confirmation_status"] == "UNOPENED_AND_EXCLUDED"


def test_feature_build_report_rejects_consumed_economic_summary(tmp_path: Path) -> None:
    report = ht.FeatureCacheBuildReport(
        protocol_sha256=tp.protocol_sha256(),
        lakehouse_manifest_sha256=ht.LAKEHOUSE_MANIFEST_SHA256,
        parquet_set_sha256=ht.PARQUET_SET_SHA256,
        cache_50s_sha256="a" * 64,
        cache_300s_sha256="b" * 64,
        row_count_50s=1,
        row_count_300s=1,
        day_counts_50s=(("2025-01-01", 1),),
        day_counts_300s=(("2025-01-01", 1),),
    )
    payload = report.as_dict()
    payload["economic_summary_computed"] = True
    path = tmp_path / "build-report.json"
    path.write_text(
        json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ht.TardisHistoricalTrainingError, match="economic summary"):
        ht.load_feature_build_report(path)
