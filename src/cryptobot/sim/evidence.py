from __future__ import annotations

import hashlib

from cryptobot.data.events import BBO
from cryptobot.data.instruments import InstrumentRole
from cryptobot.sim.contracts import (
    QuoteObservation,
    SimulationOpportunity,
    SimulationValidationError,
)


def quote_from_bbo(event: BBO, *, role: InstrumentRole) -> QuoteObservation:
    envelope = event.envelope
    return QuoteObservation(
        event_id=envelope.event_id,
        source_id=envelope.source,
        instrument_id=envelope.instrument_id,
        role=role,
        host_id=envelope.host_id,
        boot_id=envelope.boot_id,
        recv_mono_ns=envelope.recv_mono_ns,
        recv_wall_ns=envelope.recv_wall_ns,
        bid_price=event.bid_price,
        ask_price=event.ask_price,
        quality_flags=envelope.quality_flags,
    )


def build_fixed_horizon_opportunities(
    quotes: tuple[QuoteObservation, ...],
    *,
    horizon_ns: int,
    max_step_ns: int | None = None,
) -> tuple[SimulationOpportunity, ...]:
    if isinstance(horizon_ns, bool) or not isinstance(horizon_ns, int) or horizon_ns <= 0:
        raise SimulationValidationError("horizon_ns must be a positive integer")
    if max_step_ns is not None and (
        isinstance(max_step_ns, bool) or not isinstance(max_step_ns, int) or max_step_ns <= 0
    ):
        raise SimulationValidationError("max_step_ns must be null or a positive integer")
    if not quotes:
        return ()

    ordered = tuple(
        sorted(
            quotes,
            key=lambda item: (item.recv_mono_ns, item.recv_wall_ns, item.event_id),
        )
    )
    _validate_single_execution_stream(ordered)

    opportunities: list[SimulationOpportunity] = []
    start_index = 0
    while start_index < len(ordered):
        entry = ordered[start_index]
        target = entry.recv_mono_ns + horizon_ns
        exit_index = _first_at_or_after(ordered, start_index + 1, target)
        if exit_index is None:
            opportunities.append(
                SimulationOpportunity(
                    opportunity_id=_opportunity_id(entry.event_id, None, horizon_ns),
                    entry_quote=entry,
                    exit_quote=None,
                    interval_invalid_reasons=("HORIZON_EXIT_UNAVAILABLE",),
                )
            )
            break

        exit_quote = ordered[exit_index]
        interval_reasons = _interval_reasons(
            ordered,
            start_index=start_index,
            exit_index=exit_index,
            max_step_ns=max_step_ns,
        )
        opportunities.append(
            SimulationOpportunity(
                opportunity_id=_opportunity_id(
                    entry.event_id,
                    exit_quote.event_id,
                    horizon_ns,
                ),
                entry_quote=entry,
                exit_quote=exit_quote,
                interval_invalid_reasons=interval_reasons,
            )
        )
        start_index = exit_index + 1

    return tuple(opportunities)


def _validate_single_execution_stream(
    quotes: tuple[QuoteObservation, ...],
) -> None:
    first = quotes[0]
    stream = (
        first.source_id,
        first.instrument_id,
        first.role,
        first.causal_domain,
    )
    previous_mono = -1
    for quote in quotes:
        current = (
            quote.source_id,
            quote.instrument_id,
            quote.role,
            quote.causal_domain,
        )
        if current != stream:
            raise SimulationValidationError(
                "fixed-horizon builder requires one source/instrument/role/causal domain"
            )
        if quote.recv_mono_ns < previous_mono:
            raise SimulationValidationError("execution quotes are not monotonic")
        previous_mono = quote.recv_mono_ns


def _first_at_or_after(
    quotes: tuple[QuoteObservation, ...],
    start_index: int,
    target_mono_ns: int,
) -> int | None:
    for index in range(start_index, len(quotes)):
        if quotes[index].recv_mono_ns >= target_mono_ns:
            return index
    return None


def _interval_reasons(
    quotes: tuple[QuoteObservation, ...],
    *,
    start_index: int,
    exit_index: int,
    max_step_ns: int | None,
) -> tuple[str, ...]:
    if max_step_ns is None:
        return ()
    for previous, current in zip(
        quotes[start_index:exit_index],
        quotes[start_index + 1 : exit_index + 1],
        strict=True,
    ):
        if current.recv_mono_ns - previous.recv_mono_ns > max_step_ns:
            return ("GAP_EXCEEDS_MAX_STEP_NS",)
    return ()


def _opportunity_id(
    entry_event_id: str,
    exit_event_id: str | None,
    horizon_ns: int,
) -> str:
    payload = f"{entry_event_id}|{exit_event_id}|{horizon_ns}".encode()
    return f"opp-{hashlib.sha256(payload).hexdigest()[:24]}"
