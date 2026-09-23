from __future__ import annotations

import bisect
import json
from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal
from itertools import pairwise
from pathlib import Path
from typing import cast

import pyarrow as pa
import pyarrow.parquet as pq

from cryptobot.data.events import QualityFlag
from cryptobot.research.frontier import (
    EvidenceClass,
    FrontierValidationError,
    TradeDirection,
    absolute_move_bps,
    empirical_quantile_nearest_rank,
    horizon_grid_125,
    non_overlapping_window_count,
    required_capture_fraction,
    top_of_book_round_trip_friction_bps,
)

type _ReadTableFn = Callable[..., pa.Table]

_READ_TABLE = cast(_ReadTableFn, pq.read_table)

_PRIMARY_SOURCE = "hyperliquid-mainnet-public"
_PRIMARY_INSTRUMENT = "hyperliquid.mainnet.perpetual.btc"
_NS_PER_SECOND = 1_000_000_000
_QUANTILES: tuple[tuple[str, Decimal], ...] = (
    ("q50", Decimal("0.50")),
    ("q75", Decimal("0.75")),
    ("q90", Decimal("0.90")),
    ("q95", Decimal("0.95")),
)


@dataclass(frozen=True, slots=True)
class PrimaryBBOObservation:
    event_id: str
    host_id: str
    boot_id: str
    recv_mono_ns: int
    recv_wall_ns: int
    bid: Decimal
    ask: Decimal

    @property
    def mid(self) -> Decimal:
        return (self.bid + self.ask) / Decimal(2)


@dataclass(frozen=True, slots=True)
class PilotHorizonResult:
    horizon_seconds: int
    non_overlapping_windows: int
    movement_sample_count: int
    movement_quantiles_bps: tuple[tuple[str, Decimal], ...]
    median_known_friction_bps: Decimal
    q90_known_friction_bps: Decimal
    capture_fraction_vs_movement_quantiles: tuple[tuple[str, Decimal], ...]

    def as_dict(self) -> dict[str, object]:
        return {
            "horizon_seconds": self.horizon_seconds,
            "non_overlapping_windows": self.non_overlapping_windows,
            "movement_sample_count": self.movement_sample_count,
            "movement_quantiles_bps": {
                name: _decimal_string(value) for name, value in self.movement_quantiles_bps
            },
            "median_known_friction_bps": _decimal_string(self.median_known_friction_bps),
            "q90_known_friction_bps": _decimal_string(self.q90_known_friction_bps),
            "capture_fraction_vs_movement_quantiles": {
                name: _decimal_string(value)
                for name, value in self.capture_fraction_vs_movement_quantiles
            },
        }


@dataclass(frozen=True, slots=True)
class FrontierPilotReport:
    report_version: str
    status: str
    source_dataset_bundle_sha256: str
    source_normalized_records_sha256: str
    source_id: str
    instrument_id: str
    causal_domain: tuple[str, str] | None
    observation_count: int
    observed_duration_ns: int
    cadence_p99_ns: int | None
    largest_gap_ns: int | None
    spread_quantiles_bps: tuple[tuple[str, Decimal], ...]
    fee_scenario_bps_per_side: Decimal
    fee_evidence_class: EvidenceClass
    latency_evidence_class: EvidenceClass
    funding_boundary_evidence_class: EvidenceClass
    horizon_lower_bound_seconds: int | None
    horizon_upper_bound_seconds: int | None
    horizons: tuple[PilotHorizonResult, ...]
    gate_decision: str
    gate_limitation: str

    def as_dict(self) -> dict[str, object]:
        return {
            "report_version": self.report_version,
            "status": self.status,
            "source_dataset_bundle_sha256": self.source_dataset_bundle_sha256,
            "source_normalized_records_sha256": self.source_normalized_records_sha256,
            "source_id": self.source_id,
            "instrument_id": self.instrument_id,
            "causal_domain": (None if self.causal_domain is None else list(self.causal_domain)),
            "observation_count": self.observation_count,
            "observed_duration_ns": self.observed_duration_ns,
            "cadence_p99_ns": self.cadence_p99_ns,
            "largest_gap_ns": self.largest_gap_ns,
            "spread_quantiles_bps": {
                name: _decimal_string(value) for name, value in self.spread_quantiles_bps
            },
            "fee_scenario_bps_per_side": _decimal_string(self.fee_scenario_bps_per_side),
            "fee_evidence_class": self.fee_evidence_class.value,
            "latency_evidence_class": self.latency_evidence_class.value,
            "funding_boundary_evidence_class": self.funding_boundary_evidence_class.value,
            "horizon_lower_bound_seconds": self.horizon_lower_bound_seconds,
            "horizon_upper_bound_seconds": self.horizon_upper_bound_seconds,
            "horizons": [item.as_dict() for item in self.horizons],
            "gate_decision": self.gate_decision,
            "gate_limitation": self.gate_limitation,
        }

    def to_json_bytes(self) -> bytes:
        return (
            json.dumps(
                self.as_dict(),
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
            )
            + "\n"
        ).encode()


def analyze_frontier_pilot_dataset(
    dataset_dir: str | Path,
    *,
    fee_scenario_bps_per_side: Decimal,
) -> FrontierPilotReport:
    destination = Path(dataset_dir)
    bundle_sha, normalized_sha = _load_manifest_binding(destination)
    observations = _load_primary_bbo(destination)

    if len(observations) < 2:
        return _insufficient_report(
            bundle_sha=bundle_sha,
            normalized_sha=normalized_sha,
            observations=observations,
            fee_scenario_bps_per_side=fee_scenario_bps_per_side,
            limitation="fewer than two valid primary BTC BBO observations",
        )

    domains = {(item.host_id, item.boot_id) for item in observations}
    if len(domains) != 1:
        raise FrontierValidationError(
            "frontier pilot requires exactly one primary BBO causal domain"
        )
    causal_domain = next(iter(domains))

    ordered = tuple(
        sorted(
            observations,
            key=lambda item: (item.recv_mono_ns, item.recv_wall_ns, item.event_id),
        )
    )
    deltas = tuple(
        current.recv_mono_ns - previous.recv_mono_ns
        for previous, current in pairwise(ordered)
        if current.recv_mono_ns > previous.recv_mono_ns
    )
    if not deltas:
        return _insufficient_report(
            bundle_sha=bundle_sha,
            normalized_sha=normalized_sha,
            observations=ordered,
            fee_scenario_bps_per_side=fee_scenario_bps_per_side,
            limitation="primary BTC BBO observations have no positive monotonic cadence",
        )

    cadence_p99_ns = _nearest_rank_int(deltas, numerator=99, denominator=100)
    largest_gap_ns = max(deltas)
    duration_ns = ordered[-1].recv_mono_ns - ordered[0].recv_mono_ns

    lower_seconds = max(1, _ceil_div(cadence_p99_ns, _NS_PER_SECOND))
    upper_seconds = duration_ns // (2 * _NS_PER_SECOND)
    spread_values = tuple(_spread_bps(item.bid, item.ask) for item in ordered)
    spread_quantiles = _quantile_summary(spread_values)

    if upper_seconds < lower_seconds:
        return FrontierPilotReport(
            report_version="frontier-pilot-v1",
            status="INSUFFICIENT_DATA",
            source_dataset_bundle_sha256=bundle_sha,
            source_normalized_records_sha256=normalized_sha,
            source_id=_PRIMARY_SOURCE,
            instrument_id=_PRIMARY_INSTRUMENT,
            causal_domain=causal_domain,
            observation_count=len(ordered),
            observed_duration_ns=duration_ns,
            cadence_p99_ns=cadence_p99_ns,
            largest_gap_ns=largest_gap_ns,
            spread_quantiles_bps=spread_quantiles,
            fee_scenario_bps_per_side=fee_scenario_bps_per_side,
            fee_evidence_class=EvidenceClass.SCENARIO,
            latency_evidence_class=EvidenceClass.UNKNOWN,
            funding_boundary_evidence_class=EvidenceClass.UNKNOWN,
            horizon_lower_bound_seconds=lower_seconds,
            horizon_upper_bound_seconds=upper_seconds,
            horizons=(),
            gate_decision="NOT_EVALUATED",
            gate_limitation=(
                "pilot duration is too short for even two non-overlapping windows "
                "at the cadence-derived lower horizon"
            ),
        )

    times = tuple(item.recv_mono_ns for item in ordered)
    known_friction = tuple(
        max(
            top_of_book_round_trip_friction_bps(
                item.bid,
                item.ask,
                fee_bps_per_side=fee_scenario_bps_per_side,
                direction=TradeDirection.LONG,
            ),
            top_of_book_round_trip_friction_bps(
                item.bid,
                item.ask,
                fee_bps_per_side=fee_scenario_bps_per_side,
                direction=TradeDirection.SHORT,
            ),
        )
        for item in ordered
    )
    friction_q50 = empirical_quantile_nearest_rank(known_friction, Decimal("0.50"))
    friction_q90 = empirical_quantile_nearest_rank(known_friction, Decimal("0.90"))

    horizon_results: list[PilotHorizonResult] = []
    for horizon_seconds in horizon_grid_125(lower_seconds, upper_seconds):
        moves = _movement_samples(
            ordered,
            times,
            horizon_ns=horizon_seconds * _NS_PER_SECOND,
            maximum_overshoot_ns=max(cadence_p99_ns, 1),
        )
        if not moves:
            continue
        movement_quantiles = _quantile_summary(moves)
        capture_fractions = tuple(
            (
                name,
                required_capture_fraction(friction_q50, move),
            )
            for name, move in movement_quantiles
            if move > 0
        )
        horizon_results.append(
            PilotHorizonResult(
                horizon_seconds=horizon_seconds,
                non_overlapping_windows=non_overlapping_window_count(
                    duration_ns,
                    horizon_seconds,
                ),
                movement_sample_count=len(moves),
                movement_quantiles_bps=movement_quantiles,
                median_known_friction_bps=friction_q50,
                q90_known_friction_bps=friction_q90,
                capture_fraction_vs_movement_quantiles=capture_fractions,
            )
        )

    return FrontierPilotReport(
        report_version="frontier-pilot-v1",
        status="PILOT_MEASURED" if horizon_results else "INSUFFICIENT_DATA",
        source_dataset_bundle_sha256=bundle_sha,
        source_normalized_records_sha256=normalized_sha,
        source_id=_PRIMARY_SOURCE,
        instrument_id=_PRIMARY_INSTRUMENT,
        causal_domain=causal_domain,
        observation_count=len(ordered),
        observed_duration_ns=duration_ns,
        cadence_p99_ns=cadence_p99_ns,
        largest_gap_ns=largest_gap_ns,
        spread_quantiles_bps=spread_quantiles,
        fee_scenario_bps_per_side=fee_scenario_bps_per_side,
        fee_evidence_class=EvidenceClass.SCENARIO,
        latency_evidence_class=EvidenceClass.UNKNOWN,
        funding_boundary_evidence_class=EvidenceClass.UNKNOWN,
        horizon_lower_bound_seconds=lower_seconds,
        horizon_upper_bound_seconds=upper_seconds,
        horizons=tuple(horizon_results),
        gate_decision="NOT_EVALUATED",
        gate_limitation=(
            "short pilot measures movement and known top-of-book+taker-fee friction only; "
            "predictability, live latency/slippage, exact funding-boundary cost, and "
            "dependence-aware Frontier Gate evidence remain unproven"
        ),
    )


def _load_manifest_binding(dataset_dir: Path) -> tuple[str, str]:
    path = dataset_dir / "manifest.json"
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise FrontierValidationError(f"cannot read dataset manifest: {path}") from exc
    if not isinstance(raw, dict):
        raise FrontierValidationError("dataset manifest root must be an object")
    bundle = raw.get("bundle_sha256")
    normalized = raw.get("source_normalized_records_sha256")
    if not isinstance(bundle, str) or not _is_sha256(bundle):
        raise FrontierValidationError("dataset bundle_sha256 is invalid")
    if not isinstance(normalized, str) or not _is_sha256(normalized):
        raise FrontierValidationError("dataset source_normalized_records_sha256 is invalid")
    return bundle, normalized


def _load_primary_bbo(dataset_dir: Path) -> tuple[PrimaryBBOObservation, ...]:
    events = _READ_TABLE(
        dataset_dir / "events.parquet",
        columns=[
            "event_id",
            "source_id",
            "instrument_id",
            "event_type",
            "host_id",
            "boot_id",
            "recv_mono_ns",
            "recv_wall_ns",
            "quality_flags",
        ],
        use_threads=False,
    ).to_pylist()
    bbo_rows = _READ_TABLE(
        dataset_dir / "bbo.parquet",
        columns=["event_id", "bid_price_exact", "ask_price_exact"],
        use_threads=False,
    ).to_pylist()

    prices: dict[str, tuple[Decimal, Decimal]] = {}
    for raw in bbo_rows:
        row = cast(dict[str, object], raw)
        event_id = row.get("event_id")
        bid = row.get("bid_price_exact")
        ask = row.get("ask_price_exact")
        if not isinstance(event_id, str):
            raise FrontierValidationError("BBO row event_id must be a string")
        if not isinstance(bid, str) or not isinstance(ask, str):
            continue
        bid_value = Decimal(bid)
        ask_value = Decimal(ask)
        if not bid_value.is_finite() or not ask_value.is_finite():
            raise FrontierValidationError("BBO price must be finite")
        if bid_value <= 0 or ask_value <= bid_value:
            continue
        prices[event_id] = (bid_value, ask_value)

    output: list[PrimaryBBOObservation] = []
    for raw in events:
        row = cast(dict[str, object], raw)
        if row.get("source_id") != _PRIMARY_SOURCE:
            continue
        if row.get("instrument_id") != _PRIMARY_INSTRUMENT:
            continue
        if row.get("event_type") != "BBO":
            continue

        quality_flags = row.get("quality_flags")
        if not isinstance(quality_flags, int) or isinstance(quality_flags, bool):
            raise FrontierValidationError("event quality_flags must be an integer")
        if quality_flags & int(QualityFlag.SUSPECT):
            continue

        event_id = row.get("event_id")
        host_id = row.get("host_id")
        boot_id = row.get("boot_id")
        recv_mono_ns = row.get("recv_mono_ns")
        recv_wall_ns = row.get("recv_wall_ns")
        if not all(isinstance(value, str) for value in (event_id, host_id, boot_id)):
            raise FrontierValidationError("BBO event identity fields must be strings")
        if (
            isinstance(recv_mono_ns, bool)
            or not isinstance(recv_mono_ns, int)
            or isinstance(recv_wall_ns, bool)
            or not isinstance(recv_wall_ns, int)
        ):
            raise FrontierValidationError("BBO receive timestamps must be integers")

        pair = prices.get(cast(str, event_id))
        if pair is None:
            continue
        bid, ask = pair
        output.append(
            PrimaryBBOObservation(
                event_id=cast(str, event_id),
                host_id=cast(str, host_id),
                boot_id=cast(str, boot_id),
                recv_mono_ns=recv_mono_ns,
                recv_wall_ns=recv_wall_ns,
                bid=bid,
                ask=ask,
            )
        )
    return tuple(output)


def _movement_samples(
    observations: tuple[PrimaryBBOObservation, ...],
    times: tuple[int, ...],
    *,
    horizon_ns: int,
    maximum_overshoot_ns: int,
) -> tuple[Decimal, ...]:
    moves: list[Decimal] = []
    for index, start in enumerate(observations):
        target = start.recv_mono_ns + horizon_ns
        end_index = bisect.bisect_left(times, target, lo=index + 1)
        if end_index >= len(observations):
            break
        end = observations[end_index]
        if end.recv_mono_ns - target > maximum_overshoot_ns:
            continue
        moves.append(absolute_move_bps(start.mid, end.mid))
    return tuple(moves)


def _quantile_summary(values: tuple[Decimal, ...]) -> tuple[tuple[str, Decimal], ...]:
    if not values:
        return ()
    return tuple(
        (name, empirical_quantile_nearest_rank(values, probability))
        for name, probability in _QUANTILES
    )


def _spread_bps(bid: Decimal, ask: Decimal) -> Decimal:
    mid = (bid + ask) / Decimal(2)
    return ((ask - bid) / mid) * Decimal("10000")


def _nearest_rank_int(
    values: tuple[int, ...],
    *,
    numerator: int,
    denominator: int,
) -> int:
    if not values:
        raise FrontierValidationError("integer quantile requires values")
    if numerator <= 0 or denominator <= 0 or numerator > denominator:
        raise FrontierValidationError("invalid integer quantile probability")
    ordered = sorted(values)
    rank = _ceil_div(numerator * len(ordered), denominator)
    return ordered[rank - 1]


def _ceil_div(numerator: int, denominator: int) -> int:
    if denominator <= 0:
        raise FrontierValidationError("ceil-div denominator must be positive")
    return (numerator + denominator - 1) // denominator


def _insufficient_report(
    *,
    bundle_sha: str,
    normalized_sha: str,
    observations: tuple[PrimaryBBOObservation, ...],
    fee_scenario_bps_per_side: Decimal,
    limitation: str,
) -> FrontierPilotReport:
    domains = {(item.host_id, item.boot_id) for item in observations}
    causal_domain = next(iter(domains)) if len(domains) == 1 else None
    return FrontierPilotReport(
        report_version="frontier-pilot-v1",
        status="INSUFFICIENT_DATA",
        source_dataset_bundle_sha256=bundle_sha,
        source_normalized_records_sha256=normalized_sha,
        source_id=_PRIMARY_SOURCE,
        instrument_id=_PRIMARY_INSTRUMENT,
        causal_domain=causal_domain,
        observation_count=len(observations),
        observed_duration_ns=0,
        cadence_p99_ns=None,
        largest_gap_ns=None,
        spread_quantiles_bps=(),
        fee_scenario_bps_per_side=fee_scenario_bps_per_side,
        fee_evidence_class=EvidenceClass.SCENARIO,
        latency_evidence_class=EvidenceClass.UNKNOWN,
        funding_boundary_evidence_class=EvidenceClass.UNKNOWN,
        horizon_lower_bound_seconds=None,
        horizon_upper_bound_seconds=None,
        horizons=(),
        gate_decision="NOT_EVALUATED",
        gate_limitation=limitation,
    )


def _is_sha256(value: str) -> bool:
    return len(value) == 64 and all(character in "0123456789abcdef" for character in value)


def _decimal_string(value: Decimal) -> str:
    rendered = format(value, "f")
    return "0" if value.is_zero() and rendered.startswith("-") else rendered
