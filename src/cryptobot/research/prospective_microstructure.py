from __future__ import annotations

from bisect import bisect_right
from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Protocol, cast

import pyarrow as pa
import pyarrow.parquet as pq

from cryptobot.data.events import QualityFlag
from cryptobot.data.instruments import InstrumentRole
from cryptobot.data.numeric import parse_exact_decimal, serialize_exact_decimal
from cryptobot.research.economic_family import EconomicDevelopmentRow
from cryptobot.research.frontier import bbo_mid
from cryptobot.research.microstructure_family import MicrostructureRow
from cryptobot.research.signal_campaign import load_segment_books
from cryptobot.research.signal_dataset import (
    TopOfBookFeatureObservation,
    build_signal_feature_rows,
)
from cryptobot.research.signal_protocol import (
    MAX_EXECUTION_STEP_NS,
    MAX_FEATURE_AGE_NS,
    REFERENCE_LOOKBACK_NS,
    SignalFeatureRow,
)
from cryptobot.sim import QuoteObservation, build_fixed_horizon_opportunities

type _ReadTableFn = Callable[..., pa.Table]
_READ_TABLE = cast(_ReadTableFn, pq.read_table)

_PRIMARY_INSTRUMENT = "hyperliquid.mainnet.perpetual.btc"
_REFERENCE_INSTRUMENT = "binance_usdm.reference.perpetual.btcusdt"
_ALLOWED_HORIZONS = (50, 300)
_FORBIDDEN_FLAGS = QualityFlag.GAP | QualityFlag.STALE | QualityFlag.SUSPECT | QualityFlag.BACKFILL
_ZERO = Decimal(0)


class ProspectiveMicrostructureError(ValueError):
    """Raised when prospective microstructure evidence is inconsistent."""


@dataclass(frozen=True, slots=True)
class DepthObservation:
    event_id: str
    host_id: str
    boot_id: str
    recv_mono_ns: int
    recv_wall_ns: int
    quality_flags: QualityFlag
    bid_sizes: tuple[Decimal, ...]
    ask_sizes: tuple[Decimal, ...]

    @property
    def domain(self) -> tuple[str, str]:
        return (self.host_id, self.boot_id)


@dataclass(frozen=True, slots=True)
class TradeObservation:
    event_id: str
    host_id: str
    boot_id: str
    recv_mono_ns: int
    recv_wall_ns: int
    quality_flags: QualityFlag
    side: str
    size: Decimal

    @property
    def domain(self) -> tuple[str, str]:
        return (self.host_id, self.boot_id)


class TimedItem(Protocol):
    @property
    def event_id(self) -> str: ...

    @property
    def recv_mono_ns(self) -> int: ...

    @property
    def recv_wall_ns(self) -> int: ...


@dataclass(frozen=True, slots=True)
class TimedSeries[T: TimedItem]:
    items: tuple[T, ...]
    mono_values: tuple[int, ...]


def build_segment_rows(
    dataset_root: str | Path,
    *,
    segment_id: str,
    horizon_seconds: int,
) -> tuple[tuple[MicrostructureRow, dict[str, object]], ...]:
    if horizon_seconds not in _ALLOWED_HORIZONS:
        raise ProspectiveMicrostructureError("horizon must remain frozen to 50s or 300s")
    root = Path(dataset_root)
    primary_books, reference_books = load_segment_books(
        root,
        primary_instrument_id=_PRIMARY_INSTRUMENT,
        reference_instrument_id=_REFERENCE_INSTRUMENT,
    )
    quotes = tuple(
        QuoteObservation(
            event_id=item.event_id,
            source_id=item.source_id,
            instrument_id=item.instrument_id,
            role=InstrumentRole.PRIMARY,
            host_id=item.host_id,
            boot_id=item.boot_id,
            recv_mono_ns=item.recv_mono_ns,
            recv_wall_ns=item.recv_wall_ns,
            bid_price=item.bid_price,
            ask_price=item.ask_price,
            quality_flags=item.quality_flags,
        )
        for item in primary_books
    )
    opportunities = build_fixed_horizon_opportunities(
        quotes,
        horizon_ns=horizon_seconds * 1_000_000_000,
        max_step_ns=MAX_EXECUTION_STEP_NS,
    )
    signal_rows = build_signal_feature_rows(
        segment_id=segment_id,
        opportunities=opportunities,
        primary_books=primary_books,
        reference_books=reference_books,
        reference_instrument_id=_REFERENCE_INSTRUMENT,
    )
    book_series = _group(primary_books, lambda item: item.causal_domain)
    depth_series = _group(load_depths(root), lambda item: item.domain)
    hl_trade_series = _group(
        load_trades(
            root,
            event_type="TRADE",
            instrument_id=_PRIMARY_INSTRUMENT,
            payload_filename="trades.parquet",
            hyperliquid_native_side=True,
        ),
        lambda item: item.domain,
    )
    ref_trade_series = _group(
        load_trades(
            root,
            event_type="REFERENCE_TRADE",
            instrument_id=_REFERENCE_INSTRUMENT,
            payload_filename="reference_trades.parquet",
            hyperliquid_native_side=False,
        ),
        lambda item: item.domain,
    )
    result: list[tuple[MicrostructureRow, dict[str, object]]] = []
    for signal in signal_rows:
        entry = signal.opportunity.entry_quote
        exit_quote = signal.opportunity.exit_quote
        domain = entry.causal_domain
        hl_return = mid_return_5s(
            book_series.get(domain),
            decision_mono_ns=entry.recv_mono_ns,
            decision_wall_ns=entry.recv_wall_ns,
        )
        depth = depth_imbalance(
            depth_series.get(domain),
            decision_mono_ns=entry.recv_mono_ns,
            decision_wall_ns=entry.recv_wall_ns,
        )
        hl_flow = trade_flow(
            hl_trade_series.get(domain),
            decision_mono_ns=entry.recv_mono_ns,
            decision_wall_ns=entry.recv_wall_ns,
        )
        ref_flow = trade_flow(
            ref_trade_series.get(domain),
            decision_mono_ns=entry.recv_mono_ns,
            decision_wall_ns=entry.recv_wall_ns,
        )
        ref_return = signal.binance_mid_return_5s_bps.value
        cross = None if hl_return is None or ref_return is None else hl_return - ref_return
        invalid = tuple(
            sorted(set(signal.decision_invalid_reasons + signal.outcome.invalid_reasons))
        )
        base = EconomicDevelopmentRow(
            row_id=signal.row_id,
            decision_recv_wall_ns=signal.decision_recv_wall_ns,
            invalid_reasons=invalid,
            entry_bid=entry.bid_price,
            entry_ask=entry.ask_price,
            exit_bid=None if exit_quote is None else exit_quote.bid_price,
            exit_ask=None if exit_quote is None else exit_quote.ask_price,
            hl_spread_bps=signal.hl_spread_bps.value,
            hl_bbo_imbalance=signal.hl_bbo_imbalance.value,
            binance_mid_return_5s_bps=ref_return,
            outcome_invalid_reasons=signal.outcome.invalid_reasons,
        )
        row = MicrostructureRow(
            base=base,
            hl_depth_imbalance_top5=depth,
            hl_aggressive_trade_flow_5s=hl_flow,
            binance_aggressive_trade_flow_5s=ref_flow,
            hl_mid_return_5s_bps=hl_return,
            cross_venue_return_gap_5s_bps=cross,
        )
        result.append((row, row_to_dict(row, signal, horizon_seconds)))
    return tuple(result)


def row_to_dict(
    row: MicrostructureRow,
    signal: SignalFeatureRow,
    horizon_seconds: int,
) -> dict[str, object]:
    base = row.base
    opportunity = signal.opportunity
    entry = opportunity.entry_quote
    exit_quote = opportunity.exit_quote
    return {
        "source_segment_id": signal.source_segment_id,
        "horizon_seconds": horizon_seconds,
        "row_id": base.row_id,
        "opportunity_id": opportunity.opportunity_id,
        "decision_recv_mono_ns": entry.recv_mono_ns,
        "decision_recv_wall_ns": base.decision_recv_wall_ns,
        "invalid_reasons": list(base.invalid_reasons),
        "entry_bid": _optional_decimal(base.entry_bid),
        "entry_ask": _optional_decimal(base.entry_ask),
        "exit_bid": _optional_decimal(None if exit_quote is None else exit_quote.bid_price),
        "exit_ask": _optional_decimal(None if exit_quote is None else exit_quote.ask_price),
        "hl_spread_bps": _optional_decimal(base.hl_spread_bps),
        "hl_bbo_imbalance": _optional_decimal(base.hl_bbo_imbalance),
        "binance_mid_return_5s_bps": _optional_decimal(base.binance_mid_return_5s_bps),
        "outcome_invalid_reasons": list(base.outcome_invalid_reasons),
        "hl_depth_imbalance_top5": _optional_decimal(row.hl_depth_imbalance_top5),
        "hl_aggressive_trade_flow_5s": _optional_decimal(row.hl_aggressive_trade_flow_5s),
        "binance_aggressive_trade_flow_5s": _optional_decimal(row.binance_aggressive_trade_flow_5s),
        "hl_mid_return_5s_bps": _optional_decimal(row.hl_mid_return_5s_bps),
        "cross_venue_return_gap_5s_bps": _optional_decimal(row.cross_venue_return_gap_5s_bps),
    }


def load_depths(dataset_root: Path) -> tuple[DepthObservation, ...]:
    metadata = event_metadata(
        dataset_root,
        event_type="L2_SNAPSHOT",
        instrument_id=_PRIMARY_INSTRUMENT,
    )
    table = _READ_TABLE(
        dataset_root / "l2_levels.parquet",
        columns=["event_id", "side", "level_ordinal", "size_exact"],
    )
    levels: dict[str, dict[str, dict[int, Decimal]]] = {}
    for raw in table.to_pylist():
        item = cast(dict[str, object], raw)
        event_id = _required_str(item, "event_id")
        if event_id not in metadata:
            continue
        side = _required_str(item, "side")
        ordinal = _required_int(item, "level_ordinal")
        if side not in {"BID", "ASK"} or not 0 <= ordinal < 5:
            continue
        level_map = levels.setdefault(event_id, {"BID": {}, "ASK": {}})
        level_map[side][ordinal] = _required_decimal(item, "size_exact")

    output: list[DepthObservation] = []
    for event_id, meta in metadata.items():
        level_map = levels.get(event_id, {"BID": {}, "ASK": {}})
        bids = level_map["BID"]
        asks = level_map["ASK"]
        complete = set(bids) == set(range(5)) and set(asks) == set(range(5))
        output.append(
            DepthObservation(
                event_id=event_id,
                host_id=meta[0],
                boot_id=meta[1],
                recv_mono_ns=meta[2],
                recv_wall_ns=meta[3],
                quality_flags=meta[4],
                bid_sizes=tuple(bids[i] for i in range(5)) if complete else (),
                ask_sizes=tuple(asks[i] for i in range(5)) if complete else (),
            )
        )
    return tuple(
        sorted(output, key=lambda item: (item.recv_mono_ns, item.recv_wall_ns, item.event_id))
    )


def load_trades(
    dataset_root: Path,
    *,
    event_type: str,
    instrument_id: str,
    payload_filename: str,
    hyperliquid_native_side: bool,
) -> tuple[TradeObservation, ...]:
    metadata = event_metadata(
        dataset_root,
        event_type=event_type,
        instrument_id=instrument_id,
    )
    table = _READ_TABLE(
        dataset_root / payload_filename,
        columns=["event_id", "size_exact", "native_side", "aggressor_side"],
    )
    output: list[TradeObservation] = []
    for raw in table.to_pylist():
        item = cast(dict[str, object], raw)
        event_id = _required_str(item, "event_id")
        meta = metadata.get(event_id)
        if meta is None:
            continue
        if hyperliquid_native_side:
            native = item.get("native_side")
            side = "BUY" if native == "B" else "SELL" if native == "A" else "UNKNOWN"
        else:
            aggressor = item.get("aggressor_side")
            side = (
                aggressor
                if isinstance(aggressor, str) and aggressor in {"BUY", "SELL"}
                else "UNKNOWN"
            )
        output.append(
            TradeObservation(
                event_id=event_id,
                host_id=meta[0],
                boot_id=meta[1],
                recv_mono_ns=meta[2],
                recv_wall_ns=meta[3],
                quality_flags=meta[4],
                side=side,
                size=_required_decimal(item, "size_exact"),
            )
        )
    return tuple(
        sorted(output, key=lambda item: (item.recv_mono_ns, item.recv_wall_ns, item.event_id))
    )


def event_metadata(
    dataset_root: Path,
    *,
    event_type: str,
    instrument_id: str,
) -> dict[str, tuple[str, str, int, int, QualityFlag]]:
    table = _READ_TABLE(
        dataset_root / "events.parquet",
        columns=[
            "event_id",
            "host_id",
            "boot_id",
            "recv_mono_ns",
            "recv_wall_ns",
            "quality_flags",
        ],
        filters=[
            ("event_type", "=", event_type),
            ("instrument_id", "=", instrument_id),
        ],
    )
    output: dict[str, tuple[str, str, int, int, QualityFlag]] = {}
    for raw in table.to_pylist():
        item = cast(dict[str, object], raw)
        event_id = _required_str(item, "event_id")
        if event_id in output:
            raise ProspectiveMicrostructureError("duplicate event_id in feature metadata")
        output[event_id] = (
            _required_str(item, "host_id"),
            _required_str(item, "boot_id"),
            _required_int(item, "recv_mono_ns"),
            _required_int(item, "recv_wall_ns"),
            QualityFlag(_required_int(item, "quality_flags")),
        )
    return output


def _group[T: TimedItem](
    items: tuple[T, ...],
    domain_of: Callable[[T], tuple[str, str]],
) -> dict[tuple[str, str], TimedSeries[T]]:
    grouped: dict[tuple[str, str], list[T]] = {}
    for item in items:
        grouped.setdefault(domain_of(item), []).append(item)
    result: dict[tuple[str, str], TimedSeries[T]] = {}
    for domain, raw in grouped.items():
        ordered = tuple(
            sorted(
                raw,
                key=lambda item: (item.recv_mono_ns, item.recv_wall_ns, item.event_id),
            )
        )
        result[domain] = TimedSeries(
            items=ordered,
            mono_values=tuple(item.recv_mono_ns for item in ordered),
        )
    return result


def latest[T: TimedItem](
    series: TimedSeries[T] | None,
    *,
    target_mono_ns: int,
    decision_wall_ns: int,
) -> T | None:
    if series is None:
        return None
    index = bisect_right(series.mono_values, target_mono_ns) - 1
    while index >= 0:
        item = series.items[index]
        if item.recv_wall_ns <= decision_wall_ns:
            return item
        index -= 1
    return None


def mid_return_5s(
    series: TimedSeries[TopOfBookFeatureObservation] | None,
    *,
    decision_mono_ns: int,
    decision_wall_ns: int,
) -> Decimal | None:
    current_obj = latest(
        series,
        target_mono_ns=decision_mono_ns,
        decision_wall_ns=decision_wall_ns,
    )
    anchor_target = decision_mono_ns - REFERENCE_LOOKBACK_NS
    if current_obj is None or anchor_target < 0:
        return None
    anchor_obj = latest(
        series,
        target_mono_ns=anchor_target,
        decision_wall_ns=decision_wall_ns,
    )
    if anchor_obj is None:
        return None
    current = current_obj
    anchor = anchor_obj
    if decision_mono_ns - current.recv_mono_ns > MAX_FEATURE_AGE_NS:
        return None
    if anchor_target - anchor.recv_mono_ns > MAX_FEATURE_AGE_NS:
        return None
    current_mid = valid_mid(current)
    anchor_mid = valid_mid(anchor)
    if current_mid is None or anchor_mid is None:
        return None
    return (current_mid / anchor_mid - Decimal(1)) * Decimal(10000)


def valid_mid(book: TopOfBookFeatureObservation) -> Decimal | None:
    if book.quality_flags & _FORBIDDEN_FLAGS:
        return None
    if book.bid_price is None or book.ask_price is None:
        return None
    try:
        return bbo_mid(book.bid_price, book.ask_price)
    except ValueError:
        return None


def depth_imbalance(
    series: TimedSeries[DepthObservation] | None,
    *,
    decision_mono_ns: int,
    decision_wall_ns: int,
) -> Decimal | None:
    item_obj = latest(
        series,
        target_mono_ns=decision_mono_ns,
        decision_wall_ns=decision_wall_ns,
    )
    if item_obj is None:
        return None
    item = item_obj
    if decision_mono_ns - item.recv_mono_ns > MAX_FEATURE_AGE_NS:
        return None
    if item.quality_flags & _FORBIDDEN_FLAGS:
        return None
    if len(item.bid_sizes) != 5 or len(item.ask_sizes) != 5:
        return None
    bids = sum(item.bid_sizes, _ZERO)
    asks = sum(item.ask_sizes, _ZERO)
    total = bids + asks
    if total <= 0:
        return None
    return (bids - asks) / total


def trade_flow(
    series: TimedSeries[TradeObservation] | None,
    *,
    decision_mono_ns: int,
    decision_wall_ns: int,
) -> Decimal | None:
    if series is None:
        return None
    start = decision_mono_ns - REFERENCE_LOOKBACK_NS
    if start < 0:
        return None
    lo = bisect_right(series.mono_values, start)
    hi = bisect_right(series.mono_values, decision_mono_ns)
    selected = tuple(item for item in series.items[lo:hi] if item.recv_wall_ns <= decision_wall_ns)
    if not selected:
        return None
    if any(
        item.quality_flags & _FORBIDDEN_FLAGS or item.side not in {"BUY", "SELL"}
        for item in selected
    ):
        return None
    buys = sum((item.size for item in selected if item.side == "BUY"), _ZERO)
    sells = sum((item.size for item in selected if item.side == "SELL"), _ZERO)
    total = buys + sells
    if total <= 0:
        return None
    return (buys - sells) / total


def _required_str(item: dict[str, object], field: str) -> str:
    value = item.get(field)
    if not isinstance(value, str) or not value:
        raise ProspectiveMicrostructureError(f"{field} must be a non-empty string")
    return value


def _required_int(item: dict[str, object], field: str) -> int:
    value = item.get(field)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ProspectiveMicrostructureError(f"{field} must be an integer")
    return value


def _required_decimal(item: dict[str, object], field: str) -> Decimal:
    value = item.get(field)
    if not isinstance(value, str):
        raise ProspectiveMicrostructureError(f"{field} must be an exact decimal string")
    try:
        return parse_exact_decimal(value)
    except ValueError as exc:
        raise ProspectiveMicrostructureError(f"{field} is not an exact decimal") from exc


def _optional_decimal(value: Decimal | None) -> str | None:
    return None if value is None else serialize_exact_decimal(value)