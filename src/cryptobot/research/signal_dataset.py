from __future__ import annotations

import hashlib
from bisect import bisect_right
from dataclasses import dataclass
from decimal import Decimal

from cryptobot.data.events import BBO, QualityFlag, ReferenceBBO
from cryptobot.research.frontier import (
    bbo_mid,
    bbo_spread_bps,
    signed_return_bps,
)
from cryptobot.research.signal_protocol import (
    MAX_FEATURE_AGE_NS,
    PROTOCOL_VERSION,
    REFERENCE_LOOKBACK_NS,
    FeatureValue,
    OutcomeLabel,
    SignalFeatureRow,
)
from cryptobot.sim import QuoteObservation, SimulationOpportunity

_FORBIDDEN_FLAGS = QualityFlag.GAP | QualityFlag.STALE | QualityFlag.SUSPECT | QualityFlag.BACKFILL


@dataclass(frozen=True, slots=True)
class TopOfBookFeatureObservation:
    event_id: str
    source_id: str
    instrument_id: str
    host_id: str
    boot_id: str
    recv_mono_ns: int
    recv_wall_ns: int
    bid_price: Decimal | None
    bid_size: Decimal | None
    ask_price: Decimal | None
    ask_size: Decimal | None
    quality_flags: QualityFlag

    @property
    def causal_domain(self) -> tuple[str, str]:
        return (self.host_id, self.boot_id)


@dataclass(frozen=True, slots=True)
class _ReferenceSeries:
    books: tuple[TopOfBookFeatureObservation, ...]
    mono_values: tuple[int, ...]


def observation_from_bbo(event: BBO) -> TopOfBookFeatureObservation:
    envelope = event.envelope
    return TopOfBookFeatureObservation(
        event_id=envelope.event_id,
        source_id=envelope.source,
        instrument_id=envelope.instrument_id,
        host_id=envelope.host_id,
        boot_id=envelope.boot_id,
        recv_mono_ns=envelope.recv_mono_ns,
        recv_wall_ns=envelope.recv_wall_ns,
        bid_price=event.bid_price,
        bid_size=event.bid_size,
        ask_price=event.ask_price,
        ask_size=event.ask_size,
        quality_flags=envelope.quality_flags,
    )


def observation_from_reference_bbo(
    event: ReferenceBBO,
) -> TopOfBookFeatureObservation:
    envelope = event.envelope
    return TopOfBookFeatureObservation(
        event_id=envelope.event_id,
        source_id=envelope.source,
        instrument_id=envelope.instrument_id,
        host_id=envelope.host_id,
        boot_id=envelope.boot_id,
        recv_mono_ns=envelope.recv_mono_ns,
        recv_wall_ns=envelope.recv_wall_ns,
        bid_price=event.bid_price,
        bid_size=event.bid_size,
        ask_price=event.ask_price,
        ask_size=event.ask_size,
        quality_flags=envelope.quality_flags,
    )


def build_signal_feature_rows(
    *,
    segment_id: str,
    opportunities: tuple[SimulationOpportunity, ...],
    primary_books: tuple[TopOfBookFeatureObservation, ...],
    reference_books: tuple[TopOfBookFeatureObservation, ...],
    reference_instrument_id: str,
    reference_lookback_ns: int = REFERENCE_LOOKBACK_NS,
    max_feature_age_ns: int = MAX_FEATURE_AGE_NS,
) -> tuple[SignalFeatureRow, ...]:
    if not segment_id.strip():
        raise ValueError("segment_id must be non-empty")
    if reference_lookback_ns <= 0 or max_feature_age_ns < 0:
        raise ValueError("feature timing parameters are invalid")

    primary_by_event = {item.event_id: item for item in primary_books}
    reference_by_domain = _group_reference_books(
        reference_books,
        reference_instrument_id=reference_instrument_id,
    )

    rows = [
        _build_row(
            segment_id=segment_id,
            opportunity=opportunity,
            primary_book=primary_by_event.get(opportunity.entry_quote.event_id),
            reference_series=reference_by_domain.get(opportunity.entry_quote.causal_domain),
            reference_lookback_ns=reference_lookback_ns,
            max_feature_age_ns=max_feature_age_ns,
        )
        for opportunity in opportunities
    ]
    return tuple(
        sorted(
            rows,
            key=lambda item: (
                item.decision_recv_wall_ns,
                item.decision_recv_mono_ns,
                item.row_id,
            ),
        )
    )


def _build_row(
    *,
    segment_id: str,
    opportunity: SimulationOpportunity,
    primary_book: TopOfBookFeatureObservation | None,
    reference_series: _ReferenceSeries | None,
    reference_lookback_ns: int,
    max_feature_age_ns: int,
) -> SignalFeatureRow:
    entry = opportunity.entry_quote
    decision_invalid = list(entry.invalid_reasons())
    if entry.quality_flags & QualityFlag.BACKFILL:
        decision_invalid.append("ENTRY_BACKFILL_NOT_DECISION_TIME_EVIDENCE")
    decision_invalid_reasons = tuple(sorted(set(decision_invalid)))

    spread = _spread_feature(entry)
    imbalance = _imbalance_feature(primary_book, entry_event_id=entry.event_id)
    reference_return = _reference_return_feature(
        reference_series,
        decision_recv_mono_ns=entry.recv_mono_ns,
        decision_recv_wall_ns=entry.recv_wall_ns,
        lookback_ns=reference_lookback_ns,
        max_feature_age_ns=max_feature_age_ns,
    )
    outcome = _outcome_label(opportunity)

    row_id_payload = (f"{PROTOCOL_VERSION}|{segment_id}|{opportunity.opportunity_id}").encode()
    row_id = f"signal-row-{hashlib.sha256(row_id_payload).hexdigest()[:24]}"
    return SignalFeatureRow(
        row_id=row_id,
        source_segment_id=segment_id,
        opportunity=opportunity,
        decision_invalid_reasons=decision_invalid_reasons,
        hl_spread_bps=spread,
        hl_bbo_imbalance=imbalance,
        binance_mid_return_5s_bps=reference_return,
        outcome=outcome,
    )


def _spread_feature(entry: QuoteObservation) -> FeatureValue:
    bid = entry.bid_price
    ask = entry.ask_price
    event_id = entry.event_id
    recv_mono_ns = entry.recv_mono_ns
    recv_wall_ns = entry.recv_wall_ns
    quality_flags = entry.quality_flags
    if bid is None or ask is None:
        return FeatureValue(
            None,
            (event_id,),
            recv_mono_ns,
            recv_wall_ns,
            "PRIMARY_BBO_SIDE_MISSING",
        )
    if quality_flags & _FORBIDDEN_FLAGS:
        return FeatureValue(
            None,
            (event_id,),
            recv_mono_ns,
            recv_wall_ns,
            "PRIMARY_BBO_QUALITY_INVALID",
        )
    try:
        value = bbo_spread_bps(bid, ask)
    except ValueError:
        return FeatureValue(
            None,
            (event_id,),
            recv_mono_ns,
            recv_wall_ns,
            "PRIMARY_BBO_CROSSED_OR_LOCKED",
        )
    return FeatureValue(
        value,
        (event_id,),
        recv_mono_ns,
        recv_wall_ns,
    )


def _imbalance_feature(
    book: TopOfBookFeatureObservation | None,
    *,
    entry_event_id: str,
) -> FeatureValue:
    if book is None or book.event_id != entry_event_id:
        return FeatureValue(
            None,
            (),
            None,
            None,
            "PRIMARY_BBO_PAYLOAD_UNAVAILABLE",
        )
    if book.quality_flags & _FORBIDDEN_FLAGS:
        return FeatureValue(
            None,
            (book.event_id,),
            book.recv_mono_ns,
            book.recv_wall_ns,
            "PRIMARY_BBO_QUALITY_INVALID",
        )
    if book.bid_size is None or book.ask_size is None:
        return FeatureValue(
            None,
            (book.event_id,),
            book.recv_mono_ns,
            book.recv_wall_ns,
            "PRIMARY_BBO_SIZE_MISSING",
        )
    denominator = book.bid_size + book.ask_size
    if denominator <= 0:
        return FeatureValue(
            None,
            (book.event_id,),
            book.recv_mono_ns,
            book.recv_wall_ns,
            "PRIMARY_BBO_SIZE_DENOMINATOR_NONPOSITIVE",
        )
    return FeatureValue(
        (book.bid_size - book.ask_size) / denominator,
        (book.event_id,),
        book.recv_mono_ns,
        book.recv_wall_ns,
    )


def _reference_return_feature(
    series: _ReferenceSeries | None,
    *,
    decision_recv_mono_ns: int,
    decision_recv_wall_ns: int,
    lookback_ns: int,
    max_feature_age_ns: int,
) -> FeatureValue:
    if series is None or not series.books:
        return FeatureValue(None, (), None, None, "REFERENCE_BBO_UNAVAILABLE")

    current = _latest_available(
        series,
        target_mono_ns=decision_recv_mono_ns,
        decision_wall_ns=decision_recv_wall_ns,
    )
    if current is None:
        return FeatureValue(None, (), None, None, "REFERENCE_CURRENT_UNAVAILABLE")

    anchor_target = decision_recv_mono_ns - lookback_ns
    if anchor_target < 0:
        return FeatureValue(
            None,
            (current.event_id,),
            current.recv_mono_ns,
            current.recv_wall_ns,
            "REFERENCE_LOOKBACK_BEFORE_DOMAIN_START",
        )
    anchor = _latest_available(
        series,
        target_mono_ns=anchor_target,
        decision_wall_ns=decision_recv_wall_ns,
    )
    if anchor is None:
        return FeatureValue(
            None,
            (current.event_id,),
            current.recv_mono_ns,
            current.recv_wall_ns,
            "REFERENCE_LOOKBACK_UNAVAILABLE",
        )

    if decision_recv_mono_ns - current.recv_mono_ns > max_feature_age_ns:
        return FeatureValue(
            None,
            (current.event_id,),
            current.recv_mono_ns,
            current.recv_wall_ns,
            "REFERENCE_CURRENT_STALE",
        )
    if anchor_target - anchor.recv_mono_ns > max_feature_age_ns:
        return FeatureValue(
            None,
            (anchor.event_id, current.event_id),
            current.recv_mono_ns,
            current.recv_wall_ns,
            "REFERENCE_LOOKBACK_STALE",
        )

    current_mid = _valid_mid(current)
    anchor_mid = _valid_mid(anchor)
    if current_mid is None or anchor_mid is None:
        return FeatureValue(
            None,
            (anchor.event_id, current.event_id),
            current.recv_mono_ns,
            current.recv_wall_ns,
            "REFERENCE_BBO_INVALID",
        )
    return FeatureValue(
        signed_return_bps(anchor_mid, current_mid),
        (anchor.event_id, current.event_id),
        current.recv_mono_ns,
        current.recv_wall_ns,
    )


def _latest_available(
    series: _ReferenceSeries,
    *,
    target_mono_ns: int,
    decision_wall_ns: int,
) -> TopOfBookFeatureObservation | None:
    index = bisect_right(series.mono_values, target_mono_ns) - 1
    while index >= 0:
        candidate = series.books[index]
        if candidate.recv_wall_ns <= decision_wall_ns:
            return candidate
        index -= 1
    return None


def _valid_mid(
    book: TopOfBookFeatureObservation,
) -> Decimal | None:
    if book.quality_flags & _FORBIDDEN_FLAGS:
        return None
    if book.bid_price is None or book.ask_price is None:
        return None
    try:
        return bbo_mid(book.bid_price, book.ask_price)
    except ValueError:
        return None


def _outcome_label(opportunity: SimulationOpportunity) -> OutcomeLabel:
    reasons = list(opportunity.invalid_reasons())
    entry = opportunity.entry_quote
    exit_quote = opportunity.exit_quote
    if entry.quality_flags & QualityFlag.BACKFILL:
        reasons.append("ENTRY_BACKFILL")
    if exit_quote is not None and exit_quote.quality_flags & QualityFlag.BACKFILL:
        reasons.append("EXIT_BACKFILL")
    reasons = sorted(set(reasons))

    if reasons or exit_quote is None:
        return OutcomeLabel(
            signed_mid_return_bps=None,
            direction=None,
            exit_event_id=None if exit_quote is None else exit_quote.event_id,
            exit_recv_mono_ns=None if exit_quote is None else exit_quote.recv_mono_ns,
            exit_recv_wall_ns=None if exit_quote is None else exit_quote.recv_wall_ns,
            invalid_reasons=tuple(reasons or ["OUTCOME_UNAVAILABLE"]),
        )

    if (
        entry.bid_price is None
        or entry.ask_price is None
        or exit_quote.bid_price is None
        or exit_quote.ask_price is None
    ):
        return OutcomeLabel(
            None,
            None,
            exit_quote.event_id,
            exit_quote.recv_mono_ns,
            exit_quote.recv_wall_ns,
            ("OUTCOME_BBO_SIDE_MISSING",),
        )
    try:
        start_mid = bbo_mid(entry.bid_price, entry.ask_price)
        end_mid = bbo_mid(exit_quote.bid_price, exit_quote.ask_price)
    except ValueError:
        return OutcomeLabel(
            None,
            None,
            exit_quote.event_id,
            exit_quote.recv_mono_ns,
            exit_quote.recv_wall_ns,
            ("OUTCOME_BBO_INVALID",),
        )
    value = signed_return_bps(start_mid, end_mid)
    direction = 1 if value > 0 else -1 if value < 0 else 0
    return OutcomeLabel(
        value,
        direction,
        exit_quote.event_id,
        exit_quote.recv_mono_ns,
        exit_quote.recv_wall_ns,
        (),
    )


def _group_reference_books(
    books: tuple[TopOfBookFeatureObservation, ...],
    *,
    reference_instrument_id: str,
) -> dict[tuple[str, str], _ReferenceSeries]:
    grouped: dict[tuple[str, str], list[TopOfBookFeatureObservation]] = {}
    for book in books:
        if book.instrument_id != reference_instrument_id:
            continue
        grouped.setdefault(book.causal_domain, []).append(book)

    output: dict[tuple[str, str], _ReferenceSeries] = {}
    for domain, items in grouped.items():
        ordered = tuple(
            sorted(
                items,
                key=lambda item: (
                    item.recv_mono_ns,
                    item.recv_wall_ns,
                    item.event_id,
                ),
            )
        )
        output[domain] = _ReferenceSeries(
            books=ordered,
            mono_values=tuple(item.recv_mono_ns for item in ordered),
        )
    return output
