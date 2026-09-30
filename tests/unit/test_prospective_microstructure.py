from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from cryptobot.data.events import QualityFlag
from cryptobot.research.prospective_microstructure import (
    DepthObservation,
    ProspectiveMicrostructureError,
    TimedSeries,
    TradeObservation,
    build_segment_rows,
    depth_imbalance,
    mid_return_5s,
    trade_flow,
)
from cryptobot.research.signal_dataset import TopOfBookFeatureObservation


def _book(
    event_id: str,
    mono_ns: int,
    wall_ns: int,
    bid: str,
    ask: str,
    *,
    flags: QualityFlag = QualityFlag.NONE,
) -> TopOfBookFeatureObservation:
    return TopOfBookFeatureObservation(
        event_id=event_id,
        source_id="hyperliquid-mainnet-public",
        instrument_id="hyperliquid.mainnet.perpetual.btc",
        host_id="host-a",
        boot_id="boot-a",
        recv_mono_ns=mono_ns,
        recv_wall_ns=wall_ns,
        bid_price=Decimal(bid),
        bid_size=Decimal("1"),
        ask_price=Decimal(ask),
        ask_size=Decimal("1"),
        quality_flags=flags,
    )


def test_build_segment_rows_rejects_unfrozen_horizon(tmp_path: Path) -> None:
    with pytest.raises(ProspectiveMicrostructureError, match="frozen"):
        build_segment_rows(tmp_path, segment_id="segment-a", horizon_seconds=60)


def test_mid_return_uses_latest_causal_books_and_frozen_staleness() -> None:
    anchor = _book("anchor", 5_000_000_000, 5_000_000_000, "99", "101")
    current = _book("current", 10_000_000_000, 10_000_000_000, "109", "111")
    future_wall = _book("future-wall", 10_000_000_000, 11_000_000_000, "199", "201")
    series = TimedSeries(
        items=(anchor, current, future_wall),
        mono_values=(5_000_000_000, 10_000_000_000, 10_000_000_000),
    )

    value = mid_return_5s(
        series,
        decision_mono_ns=10_000_000_000,
        decision_wall_ns=10_000_000_000,
    )

    assert value == Decimal("1000")

    stale = TimedSeries(items=(anchor,), mono_values=(5_000_000_000,))
    assert (
        mid_return_5s(
            stale,
            decision_mono_ns=12_000_000_001,
            decision_wall_ns=12_000_000_001,
        )
        is None
    )


def test_depth_imbalance_requires_exact_top_five_and_quality() -> None:
    good = DepthObservation(
        event_id="depth",
        host_id="host-a",
        boot_id="boot-a",
        recv_mono_ns=10_000_000_000,
        recv_wall_ns=10_000_000_000,
        quality_flags=QualityFlag.NONE,
        bid_sizes=(Decimal("2"),) * 5,
        ask_sizes=(Decimal("1"),) * 5,
    )
    series = TimedSeries(items=(good,), mono_values=(good.recv_mono_ns,))

    assert depth_imbalance(
        series,
        decision_mono_ns=10_000_000_000,
        decision_wall_ns=10_000_000_000,
    ) == Decimal(1) / Decimal(3)

    bad = DepthObservation(
        event_id="bad",
        host_id="host-a",
        boot_id="boot-a",
        recv_mono_ns=10_000_000_000,
        recv_wall_ns=10_000_000_000,
        quality_flags=QualityFlag.GAP,
        bid_sizes=(Decimal("2"),) * 5,
        ask_sizes=(Decimal("1"),) * 5,
    )
    assert (
        depth_imbalance(
            TimedSeries(items=(bad,), mono_values=(bad.recv_mono_ns,)),
            decision_mono_ns=10_000_000_000,
            decision_wall_ns=10_000_000_000,
        )
        is None
    )


def _trade(event_id: str, mono_ns: int, side: str, size: str) -> TradeObservation:
    return TradeObservation(
        event_id=event_id,
        host_id="host-a",
        boot_id="boot-a",
        recv_mono_ns=mono_ns,
        recv_wall_ns=mono_ns,
        quality_flags=QualityFlag.NONE,
        side=side,
        size=Decimal(size),
    )


def test_trade_flow_uses_open_left_closed_right_window_and_unknown_is_missing() -> None:
    at_start = _trade("start", 5_000_000_000, "SELL", "100")
    buy = _trade("buy", 6_000_000_000, "BUY", "3")
    sell = _trade("sell", 10_000_000_000, "SELL", "1")
    series = TimedSeries(
        items=(at_start, buy, sell),
        mono_values=(5_000_000_000, 6_000_000_000, 10_000_000_000),
    )

    assert trade_flow(
        series,
        decision_mono_ns=10_000_000_000,
        decision_wall_ns=10_000_000_000,
    ) == Decimal("0.5")

    unknown = _trade("unknown", 9_000_000_000, "UNKNOWN", "1")
    series_with_unknown = TimedSeries(
        items=(buy, unknown, sell),
        mono_values=(6_000_000_000, 9_000_000_000, 10_000_000_000),
    )
    assert (
        trade_flow(
            series_with_unknown,
            decision_mono_ns=10_000_000_000,
            decision_wall_ns=10_000_000_000,
        )
        is None
    )
