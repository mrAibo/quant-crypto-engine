from __future__ import annotations

import bisect
import json
from collections import Counter
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
    dkw_required_sample_count,
    empirical_quantile_nearest_rank,
    empirical_signed_quantile_nearest_rank,
    horizon_grid_125,
    minimum_duration_seconds_for_windows,
    next_horizon_125,
    non_overlapping_window_count,
    required_capture_fraction,
    signed_return_bps,
    top_of_book_round_trip_friction_bps,
)

type _ReadTableFn = Callable[..., pa.Table]

_READ_TABLE = cast(_ReadTableFn, pq.read_table)

_PRIMARY_SOURCE = "hyperliquid-mainnet-public"
_PRIMARY_INSTRUMENT = "hyperliquid.mainnet.perpetual.btc"
_REFERENCE_SOURCE = "binance-usdm-reference-public"
_REFERENCE_INSTRUMENT = "binance_usdm.reference.perpetual.btcusdt"
_NS_PER_SECOND = 1_000_000_000
_QUANTILES: tuple[tuple[str, Decimal], ...] = (
    ("q50", Decimal("0.50")),
    ("q75", Decimal("0.75")),
    ("q90", Decimal("0.90")),
    ("q95", Decimal("0.95")),
)
_SIGNED_QUANTILES: tuple[tuple[str, Decimal], ...] = (
    ("q05", Decimal("0.05")),
    ("q50", Decimal("0.50")),
    ("q95", Decimal("0.95")),
)
_PRIMARY_EXPECTED_TYPES = (
    "BBO",
    "L2_SNAPSHOT",
    "TRADE",
    "FUNDING_RATE_OBSERVATION",
    "MARK_PRICE",
    "ORACLE_PRICE",
)
_REFERENCE_EXPECTED_TYPES = ("REFERENCE_BBO", "REFERENCE_TRADE")
_DKW_CONFIDENCE = Decimal("0.95")
_DKW_MAX_CDF_ERROR = Decimal("0.025")


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
class StreamCadenceAudit:
    event_type: str
    observed_count: int
    usable_count: int
    interarrival_count: int
    q50_ns: int | None
    q90_ns: int | None
    q99_ns: int | None
    largest_gap_ns: int | None

    def as_dict(self) -> dict[str, object]:
        return {
            "event_type": self.event_type,
            "observed_count": self.observed_count,
            "usable_count": self.usable_count,
            "interarrival_count": self.interarrival_count,
            "q50_ns": self.q50_ns,
            "q90_ns": self.q90_ns,
            "q99_ns": self.q99_ns,
            "largest_gap_ns": self.largest_gap_ns,
        }


@dataclass(frozen=True, slots=True)
class FrontierDatasetAudit:
    causal_domain_count: int
    raw_frame_count: int
    observed_duration_ns: int
    observed_wall_duration_ns: int
    frame_counts_by_source_outcome: tuple[tuple[str, str, int], ...]
    frame_counts_by_source_channel: tuple[tuple[str, str | None, int], ...]
    event_counts_by_source_type: tuple[tuple[str, str, int], ...]
    primary_btc_event_counts: tuple[tuple[str, int], ...]
    reference_btc_event_counts: tuple[tuple[str, int], ...]
    primary_bbo_cadence: StreamCadenceAudit
    primary_l2_cadence: StreamCadenceAudit

    def as_dict(self) -> dict[str, object]:
        return {
            "causal_domain_count": self.causal_domain_count,
            "raw_frame_count": self.raw_frame_count,
            "observed_duration_ns": self.observed_duration_ns,
            "observed_wall_duration_ns": self.observed_wall_duration_ns,
            "frame_counts_by_source_outcome": [
                {
                    "source_id": source_id,
                    "outcome": outcome,
                    "count": count,
                }
                for source_id, outcome, count in self.frame_counts_by_source_outcome
            ],
            "frame_counts_by_source_channel": [
                {
                    "source_id": source_id,
                    "channel_or_stream": channel,
                    "count": count,
                }
                for source_id, channel, count in self.frame_counts_by_source_channel
            ],
            "event_counts_by_source_type": [
                {
                    "source_id": source_id,
                    "event_type": event_type,
                    "count": count,
                }
                for source_id, event_type, count in self.event_counts_by_source_type
            ],
            "primary_btc_event_counts": dict(self.primary_btc_event_counts),
            "reference_btc_event_counts": dict(self.reference_btc_event_counts),
            "primary_bbo_cadence": self.primary_bbo_cadence.as_dict(),
            "primary_l2_cadence": self.primary_l2_cadence.as_dict(),
        }


@dataclass(frozen=True, slots=True)
class PilotHorizonResult:
    horizon_seconds: int
    non_overlapping_windows: int
    candidate_start_count: int
    movement_sample_count: int
    gap_excluded_count: int
    signed_return_quantiles_bps: tuple[tuple[str, Decimal], ...]
    movement_quantiles_bps: tuple[tuple[str, Decimal], ...]
    median_known_friction_bps: Decimal
    q90_known_friction_bps: Decimal
    capture_fraction_vs_movement_quantiles: tuple[tuple[str, Decimal], ...]

    def as_dict(self) -> dict[str, object]:
        return {
            "horizon_seconds": self.horizon_seconds,
            "non_overlapping_windows": self.non_overlapping_windows,
            "candidate_start_count": self.candidate_start_count,
            "movement_sample_count": self.movement_sample_count,
            "gap_excluded_count": self.gap_excluded_count,
            "signed_return_quantiles_bps": {
                name: _decimal_string(value) for name, value in self.signed_return_quantiles_bps
            },
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
class EvidenceWindowPlan:
    confidence: Decimal
    maximum_cdf_error: Decimal
    required_non_overlapping_windows: int
    target_horizon_seconds: int | None
    minimum_observed_duration_seconds: int | None
    target_reason: str
    dependence_limitation: str

    def as_dict(self) -> dict[str, object]:
        return {
            "confidence": _decimal_string(self.confidence),
            "maximum_cdf_error": _decimal_string(self.maximum_cdf_error),
            "required_non_overlapping_windows": self.required_non_overlapping_windows,
            "target_horizon_seconds": self.target_horizon_seconds,
            "minimum_observed_duration_seconds": self.minimum_observed_duration_seconds,
            "target_reason": self.target_reason,
            "dependence_limitation": self.dependence_limitation,
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
    dataset_audit: FrontierDatasetAudit
    movement_q95_meets_median_known_friction: bool
    evidence_window_plan: EvidenceWindowPlan
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
            "dataset_audit": self.dataset_audit.as_dict(),
            "movement_q95_meets_median_known_friction": (
                self.movement_q95_meets_median_known_friction
            ),
            "evidence_window_plan": self.evidence_window_plan.as_dict(),
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
    frame_rows = _load_frame_rows(destination)
    event_rows = _load_event_rows(destination)
    audit = _build_dataset_audit(frame_rows, event_rows)
    observations = _load_primary_bbo(destination, event_rows)

    if len(observations) < 2:
        return _insufficient_report(
            bundle_sha=bundle_sha,
            normalized_sha=normalized_sha,
            observations=observations,
            fee_scenario_bps_per_side=fee_scenario_bps_per_side,
            limitation="fewer than two valid primary BTC BBO observations",
            dataset_audit=audit,
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
            dataset_audit=audit,
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
            report_version="frontier-pilot-v2",
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
            dataset_audit=audit,
            movement_q95_meets_median_known_friction=False,
            evidence_window_plan=_evidence_window_plan((), lower_seconds),
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
        signed_moves, moves, candidate_count, gap_excluded_count = _movement_samples(
            ordered,
            times,
            horizon_ns=horizon_seconds * _NS_PER_SECOND,
            maximum_overshoot_ns=max(cadence_p99_ns, 1),
        )
        if not moves:
            continue
        signed_quantiles = _signed_quantile_summary(signed_moves)
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
                candidate_start_count=candidate_count,
                movement_sample_count=len(moves),
                gap_excluded_count=gap_excluded_count,
                signed_return_quantiles_bps=signed_quantiles,
                movement_quantiles_bps=movement_quantiles,
                median_known_friction_bps=friction_q50,
                q90_known_friction_bps=friction_q90,
                capture_fraction_vs_movement_quantiles=capture_fractions,
            )
        )

    horizons = tuple(horizon_results)
    q95_meets = _q95_meets_friction(horizons)
    return FrontierPilotReport(
        report_version="frontier-pilot-v2",
        status="PILOT_MEASURED" if horizons else "INSUFFICIENT_DATA",
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
        horizons=horizons,
        dataset_audit=audit,
        movement_q95_meets_median_known_friction=q95_meets,
        evidence_window_plan=_evidence_window_plan(horizons, lower_seconds),
        gate_decision="NOT_EVALUATED",
        gate_limitation=(
            "short pilot measures movement and known top-of-book+taker-fee friction only; "
            "predictability, live latency/slippage, exact funding-boundary cost, serial "
            "dependence, and Frontier Gate evidence remain unproven"
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


def _load_frame_rows(dataset_dir: Path) -> tuple[dict[str, object], ...]:
    raw_rows = _READ_TABLE(
        dataset_dir / "frames.parquet",
        columns=[
            "source_id",
            "host_id",
            "boot_id",
            "recv_mono_ns",
            "recv_wall_ns",
            "channel_or_stream",
            "outcome",
        ],
        use_threads=False,
    ).to_pylist()
    return tuple(cast(dict[str, object], row) for row in raw_rows)


def _load_event_rows(dataset_dir: Path) -> tuple[dict[str, object], ...]:
    raw_rows = _READ_TABLE(
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
    return tuple(cast(dict[str, object], row) for row in raw_rows)


def _build_dataset_audit(
    frame_rows: tuple[dict[str, object], ...],
    event_rows: tuple[dict[str, object], ...],
) -> FrontierDatasetAudit:
    domains: set[tuple[str, str]] = set()
    recv_mono_values: list[int] = []
    recv_wall_values: list[int] = []
    frame_outcomes: Counter[tuple[str, str]] = Counter()
    frame_channels: Counter[tuple[str, str | None]] = Counter()
    event_counts: Counter[tuple[str, str]] = Counter()
    primary_counts: Counter[str] = Counter()
    reference_counts: Counter[str] = Counter()

    for row in frame_rows:
        source_id = row.get("source_id")
        host_id = row.get("host_id")
        boot_id = row.get("boot_id")
        recv_mono_ns = row.get("recv_mono_ns")
        recv_wall_ns = row.get("recv_wall_ns")
        channel = row.get("channel_or_stream")
        outcome = row.get("outcome")

        if not all(isinstance(value, str) for value in (source_id, host_id, boot_id, outcome)):
            raise FrontierValidationError("frame audit identity/outcome fields must be strings")
        if channel is not None and not isinstance(channel, str):
            raise FrontierValidationError("frame channel_or_stream must be null or a string")
        if (
            isinstance(recv_mono_ns, bool)
            or not isinstance(recv_mono_ns, int)
            or isinstance(recv_wall_ns, bool)
            or not isinstance(recv_wall_ns, int)
        ):
            raise FrontierValidationError("frame receive timestamps must be integers")

        source = cast(str, source_id)
        domains.add((cast(str, host_id), cast(str, boot_id)))
        recv_mono_values.append(recv_mono_ns)
        recv_wall_values.append(recv_wall_ns)
        frame_outcomes[(source, cast(str, outcome))] += 1
        frame_channels[(source, cast(str | None, channel))] += 1

    for row in event_rows:
        source_id = row.get("source_id")
        event_type = row.get("event_type")
        instrument_id = row.get("instrument_id")
        if not all(isinstance(value, str) for value in (source_id, event_type, instrument_id)):
            raise FrontierValidationError("event audit identity fields must be strings")

        source = cast(str, source_id)
        event = cast(str, event_type)
        instrument = cast(str, instrument_id)
        event_counts[(source, event)] += 1
        if source == _PRIMARY_SOURCE and instrument == _PRIMARY_INSTRUMENT:
            primary_counts[event] += 1
        if source == _REFERENCE_SOURCE and instrument == _REFERENCE_INSTRUMENT:
            reference_counts[event] += 1

    monotonic_duration = (
        0 if not recv_mono_values else max(recv_mono_values) - min(recv_mono_values)
    )
    wall_duration = 0 if not recv_wall_values else max(recv_wall_values) - min(recv_wall_values)

    return FrontierDatasetAudit(
        causal_domain_count=len(domains),
        raw_frame_count=len(frame_rows),
        observed_duration_ns=monotonic_duration,
        observed_wall_duration_ns=wall_duration,
        frame_counts_by_source_outcome=tuple(
            (source, outcome, count) for (source, outcome), count in sorted(frame_outcomes.items())
        ),
        frame_counts_by_source_channel=tuple(
            (source, channel, count)
            for (source, channel), count in sorted(
                frame_channels.items(),
                key=lambda item: (item[0][0], "" if item[0][1] is None else item[0][1]),
            )
        ),
        event_counts_by_source_type=tuple(
            (source, event, count) for (source, event), count in sorted(event_counts.items())
        ),
        primary_btc_event_counts=tuple(
            (event_type, primary_counts[event_type]) for event_type in _PRIMARY_EXPECTED_TYPES
        ),
        reference_btc_event_counts=tuple(
            (event_type, reference_counts[event_type]) for event_type in _REFERENCE_EXPECTED_TYPES
        ),
        primary_bbo_cadence=_stream_cadence_audit(
            event_rows,
            source_id=_PRIMARY_SOURCE,
            instrument_id=_PRIMARY_INSTRUMENT,
            event_type="BBO",
        ),
        primary_l2_cadence=_stream_cadence_audit(
            event_rows,
            source_id=_PRIMARY_SOURCE,
            instrument_id=_PRIMARY_INSTRUMENT,
            event_type="L2_SNAPSHOT",
        ),
    )


def _stream_cadence_audit(
    event_rows: tuple[dict[str, object], ...],
    *,
    source_id: str,
    instrument_id: str,
    event_type: str,
) -> StreamCadenceAudit:
    observed: list[tuple[int, int]] = []
    usable: list[int] = []

    for row in event_rows:
        if row.get("source_id") != source_id:
            continue
        if row.get("instrument_id") != instrument_id:
            continue
        if row.get("event_type") != event_type:
            continue

        recv_mono_ns = row.get("recv_mono_ns")
        quality_flags = row.get("quality_flags")
        if isinstance(recv_mono_ns, bool) or not isinstance(recv_mono_ns, int):
            raise FrontierValidationError("stream recv_mono_ns must be an integer")
        if isinstance(quality_flags, bool) or not isinstance(quality_flags, int):
            raise FrontierValidationError("stream quality_flags must be an integer")
        observed.append((recv_mono_ns, quality_flags))
        if not (quality_flags & int(QualityFlag.SUSPECT)):
            usable.append(recv_mono_ns)

    ordered = sorted(usable)
    deltas = tuple(
        current - previous for previous, current in pairwise(ordered) if current > previous
    )
    return StreamCadenceAudit(
        event_type=event_type,
        observed_count=len(observed),
        usable_count=len(usable),
        interarrival_count=len(deltas),
        q50_ns=(None if not deltas else _nearest_rank_int(deltas, numerator=50, denominator=100)),
        q90_ns=(None if not deltas else _nearest_rank_int(deltas, numerator=90, denominator=100)),
        q99_ns=(None if not deltas else _nearest_rank_int(deltas, numerator=99, denominator=100)),
        largest_gap_ns=(None if not deltas else max(deltas)),
    )


def _load_primary_bbo(
    dataset_dir: Path,
    event_rows: tuple[dict[str, object], ...],
) -> tuple[PrimaryBBOObservation, ...]:
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
    for row in event_rows:
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
) -> tuple[tuple[Decimal, ...], tuple[Decimal, ...], int, int]:
    signed_moves: list[Decimal] = []
    absolute_moves: list[Decimal] = []
    candidate_count = 0
    gap_excluded_count = 0

    for index, start in enumerate(observations):
        target = start.recv_mono_ns + horizon_ns
        if target > times[-1]:
            break
        candidate_count += 1
        end_index = bisect.bisect_left(times, target, lo=index + 1)
        if end_index >= len(observations):
            break
        end = observations[end_index]
        if end.recv_mono_ns - target > maximum_overshoot_ns:
            gap_excluded_count += 1
            continue
        signed = signed_return_bps(start.mid, end.mid)
        signed_moves.append(signed)
        absolute_moves.append(abs(signed))
    return (
        tuple(signed_moves),
        tuple(absolute_moves),
        candidate_count,
        gap_excluded_count,
    )

def _q95_meets_friction(horizons: tuple[PilotHorizonResult, ...]) -> bool:
    for item in horizons:
        q95 = dict(item.movement_quantiles_bps).get("q95")
        if q95 is not None and q95 >= item.median_known_friction_bps:
            return True
    return False


def _evidence_window_plan(
    horizons: tuple[PilotHorizonResult, ...],
    lower_seconds: int | None,
) -> EvidenceWindowPlan:
    required_windows = dkw_required_sample_count(
        confidence=_DKW_CONFIDENCE,
        maximum_cdf_error=_DKW_MAX_CDF_ERROR,
    )

    target_horizon: int | None = None
    reason = "NO_SUPPORTED_PILOT_HORIZON"
    for item in horizons:
        q95 = dict(item.movement_quantiles_bps).get("q95")
        if q95 is not None and q95 >= item.median_known_friction_bps:
            target_horizon = item.horizon_seconds
            reason = "FIRST_PILOT_Q95_AT_OR_ABOVE_MEDIAN_KNOWN_FRICTION"
            break

    if target_horizon is None and horizons:
        target_horizon = next_horizon_125(horizons[-1].horizon_seconds)
        reason = "EXPAND_ONE_125_CELL_BECAUSE_PILOT_Q95_BELOW_MEDIAN_KNOWN_FRICTION"
    elif target_horizon is None and lower_seconds is not None:
        target_horizon = lower_seconds
        reason = "COLLECT_CADENCE_DERIVED_LOWER_HORIZON"

    minimum_duration = (
        None
        if target_horizon is None
        else minimum_duration_seconds_for_windows(
            horizon_seconds=target_horizon,
            required_non_overlapping_windows=required_windows,
        )
    )
    return EvidenceWindowPlan(
        confidence=_DKW_CONFIDENCE,
        maximum_cdf_error=_DKW_MAX_CDF_ERROR,
        required_non_overlapping_windows=required_windows,
        target_horizon_seconds=target_horizon,
        minimum_observed_duration_seconds=minimum_duration,
        target_reason=reason,
        dependence_limitation=(
            "DKW planning count assumes independent samples; non-overlap reduces mechanical "
            "overlap but does not prove independence. Serial dependence or gaps can only "
            "increase the required real evidence window."
        ),
    )


def _signed_quantile_summary(
    values: tuple[Decimal, ...],
) -> tuple[tuple[str, Decimal], ...]:
    if not values:
        return ()
    return tuple(
        (name, empirical_signed_quantile_nearest_rank(values, probability))
        for name, probability in _SIGNED_QUANTILES
    )


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
    dataset_audit: FrontierDatasetAudit,
) -> FrontierPilotReport:
    domains = {(item.host_id, item.boot_id) for item in observations}
    causal_domain = next(iter(domains)) if len(domains) == 1 else None
    return FrontierPilotReport(
        report_version="frontier-pilot-v2",
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
        dataset_audit=dataset_audit,
        movement_q95_meets_median_known_friction=False,
        evidence_window_plan=_evidence_window_plan((), None),
        gate_decision="NOT_EVALUATED",
        gate_limitation=limitation,
    )


def _is_sha256(value: str) -> bool:
    return len(value) == 64 and all(character in "0123456789abcdef" for character in value)


def _decimal_string(value: Decimal) -> str:
    rendered = format(value, "f")
    return "0" if value.is_zero() and rendered.startswith("-") else rendered
