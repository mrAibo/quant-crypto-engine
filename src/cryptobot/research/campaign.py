from __future__ import annotations

import bisect
import hashlib
import json
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from itertools import pairwise

from cryptobot.data.numeric import (
    NumericValidationError,
    parse_exact_decimal,
    serialize_exact_decimal,
)
from cryptobot.research.frontier import (
    EvidenceClass,
    TradeDirection,
    empirical_quantile_nearest_rank,
    required_capture_fraction,
    signed_return_bps,
    top_of_book_round_trip_friction_bps,
)
from cryptobot.research.frontier_dataset import PrimaryBBOObservation

_NS_PER_SECOND = 1_000_000_000
_TARGET_HORIZON_SECONDS = 50
_REQUIRED_WINDOWS = 2_952
_DKW_CONFIDENCE = Decimal("0.95")
_DKW_MAX_CDF_ERROR = Decimal("0.025")
_REQUIRED_SOURCES = (
    "binance-usdm-reference-public",
    "hyperliquid-mainnet-public",
)
_PRIMARY_INSTRUMENT = "hyperliquid.mainnet.perpetual.btc"


class CampaignValidationError(ValueError):
    """Raised when prospective frontier campaign evidence is invalid."""


class GateDecision(StrEnum):
    PASS_FEASIBILITY = "PASS_FEASIBILITY"
    FAIL_FEASIBILITY_AT_50S = "FAIL_FEASIBILITY_AT_50S"
    INCONCLUSIVE = "INCONCLUSIVE"


class CampaignReadiness(StrEnum):
    COLLECTING = "COLLECTING"
    READY_FOR_FRONTIER_ADJUDICATION = "READY_FOR_FRONTIER_ADJUDICATION"


@dataclass(frozen=True, slots=True)
class CampaignConfig:
    campaign_id: str
    fee_scenario_bps_per_side: Decimal
    target_horizon_seconds: int = _TARGET_HORIZON_SECONDS
    required_non_overlapping_windows: int = _REQUIRED_WINDOWS
    dkw_confidence: Decimal = _DKW_CONFIDENCE
    dkw_maximum_cdf_error: Decimal = _DKW_MAX_CDF_ERROR
    source_ids: tuple[str, ...] = _REQUIRED_SOURCES
    primary_instrument_id: str = _PRIMARY_INSTRUMENT

    def __post_init__(self) -> None:
        if not self.campaign_id.strip():
            raise CampaignValidationError("campaign_id must be non-empty")
        if self.target_horizon_seconds != _TARGET_HORIZON_SECONDS:
            raise CampaignValidationError("target_horizon_seconds must remain pre-registered at 50")
        if self.required_non_overlapping_windows != _REQUIRED_WINDOWS:
            raise CampaignValidationError(
                "required_non_overlapping_windows must remain pre-registered at 2952"
            )
        if self.dkw_confidence != _DKW_CONFIDENCE:
            raise CampaignValidationError("dkw_confidence must remain pre-registered at 0.95")
        if self.dkw_maximum_cdf_error != _DKW_MAX_CDF_ERROR:
            raise CampaignValidationError(
                "dkw_maximum_cdf_error must remain pre-registered at 0.025"
            )
        _require_nonnegative_decimal(
            self.fee_scenario_bps_per_side,
            "fee_scenario_bps_per_side",
        )
        if tuple(sorted(self.source_ids)) != _REQUIRED_SOURCES:
            raise CampaignValidationError("source_ids must match the frozen Stage-0 source set")
        if self.primary_instrument_id != _PRIMARY_INSTRUMENT:
            raise CampaignValidationError("primary_instrument_id must remain frozen to BTC")

    def as_dict(self) -> dict[str, object]:
        return {
            "campaign_id": self.campaign_id,
            "fee_scenario_bps_per_side": serialize_exact_decimal(
                self.fee_scenario_bps_per_side
            ),
            "target_horizon_seconds": self.target_horizon_seconds,
            "required_non_overlapping_windows": self.required_non_overlapping_windows,
            "dkw_confidence": serialize_exact_decimal(self.dkw_confidence),
            "dkw_maximum_cdf_error": serialize_exact_decimal(
                self.dkw_maximum_cdf_error
            ),
            "source_ids": list(self.source_ids),
            "primary_instrument_id": self.primary_instrument_id,
        }


@dataclass(frozen=True, slots=True)
class SegmentEvidence:
    segment_id: str
    dataset_bundle_sha256: str
    normalized_records_sha256: str
    dataset_schema_version: int
    materializer_version: str
    raw_frame_count: int
    normalized_event_count: int
    source_ids: tuple[str, ...]
    causal_domains: tuple[tuple[str, str], ...]
    wall_start_ns: int
    wall_end_ns: int
    primary_bbo_count: int
    primary_l2_count: int

    def __post_init__(self) -> None:
        if not self.segment_id.strip():
            raise CampaignValidationError("segment_id must be non-empty")
        _require_sha256(self.dataset_bundle_sha256, "dataset_bundle_sha256")
        _require_sha256(self.normalized_records_sha256, "normalized_records_sha256")
        _require_positive_int(self.dataset_schema_version, "dataset_schema_version")
        if not self.materializer_version.strip():
            raise CampaignValidationError("materializer_version must be non-empty")
        _require_nonnegative_int(self.raw_frame_count, "raw_frame_count")
        _require_nonnegative_int(self.normalized_event_count, "normalized_event_count")
        if tuple(sorted(self.source_ids)) != _REQUIRED_SOURCES:
            raise CampaignValidationError("segment source_ids do not match frozen source set")
        if not self.causal_domains:
            raise CampaignValidationError("segment must contain at least one causal domain")
        if len(set(self.causal_domains)) != len(self.causal_domains):
            raise CampaignValidationError("segment causal_domains must be unique")
        for host_id, boot_id in self.causal_domains:
            if not host_id.strip() or not boot_id.strip():
                raise CampaignValidationError("causal-domain host/boot IDs must be non-empty")
        _require_nonnegative_int(self.wall_start_ns, "wall_start_ns")
        _require_nonnegative_int(self.wall_end_ns, "wall_end_ns")
        if self.wall_end_ns <= self.wall_start_ns:
            raise CampaignValidationError("wall_end_ns must be greater than wall_start_ns")
        _require_nonnegative_int(self.primary_bbo_count, "primary_bbo_count")
        _require_nonnegative_int(self.primary_l2_count, "primary_l2_count")

    def as_dict(self) -> dict[str, object]:
        return {
            "segment_id": self.segment_id,
            "dataset_bundle_sha256": self.dataset_bundle_sha256,
            "normalized_records_sha256": self.normalized_records_sha256,
            "dataset_schema_version": self.dataset_schema_version,
            "materializer_version": self.materializer_version,
            "raw_frame_count": self.raw_frame_count,
            "normalized_event_count": self.normalized_event_count,
            "source_ids": list(self.source_ids),
            "causal_domains": [list(domain) for domain in self.causal_domains],
            "wall_start_ns": self.wall_start_ns,
            "wall_end_ns": self.wall_end_ns,
            "primary_bbo_count": self.primary_bbo_count,
            "primary_l2_count": self.primary_l2_count,
        }


@dataclass(frozen=True, slots=True)
class CampaignManifest:
    config: CampaignConfig
    segments: tuple[SegmentEvidence, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.config, CampaignConfig):
            raise CampaignValidationError("config must be CampaignConfig")
        _validate_segments(self.segments)

    def add_segment(self, segment: SegmentEvidence) -> CampaignManifest:
        return CampaignManifest(
            config=self.config,
            segments=tuple(sorted((*self.segments, segment), key=_segment_sort_key)),
        )

    def as_dict(self) -> dict[str, object]:
        return {
            "schema_version": 1,
            "config": self.config.as_dict(),
            "segments": [segment.as_dict() for segment in self.segments],
        }

    def to_json_bytes(self) -> bytes:
        return _canonical_json_bytes(self.as_dict())

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.to_json_bytes()).hexdigest()


@dataclass(frozen=True, slots=True)
class SegmentData:
    evidence: SegmentEvidence
    primary_bbo: tuple[PrimaryBBOObservation, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.evidence, SegmentEvidence):
            raise CampaignValidationError("evidence must be SegmentEvidence")
        if len(self.primary_bbo) != self.evidence.primary_bbo_count:
            raise CampaignValidationError(
                "primary BBO observation count does not match segment evidence"
            )
        allowed_domains = set(self.evidence.causal_domains)
        for item in self.primary_bbo:
            if (item.host_id, item.boot_id) not in allowed_domains:
                raise CampaignValidationError(
                    "primary BBO observation belongs to an undeclared causal domain"
                )
            if not (
                self.evidence.wall_start_ns
                <= item.recv_wall_ns
                <= self.evidence.wall_end_ns
            ):
                raise CampaignValidationError(
                    "primary BBO observation falls outside segment wall interval"
                )


@dataclass(frozen=True, slots=True)
class MovementWindow:
    segment_id: str
    host_id: str
    boot_id: str
    start_event_id: str
    end_event_id: str
    start_recv_mono_ns: int
    end_recv_mono_ns: int
    start_recv_wall_ns: int
    end_recv_wall_ns: int
    signed_move_bps: Decimal
    absolute_move_bps: Decimal
    known_friction_bps: Decimal | None

    def __post_init__(self) -> None:
        if not all(
            value.strip()
            for value in (
                self.segment_id,
                self.host_id,
                self.boot_id,
                self.start_event_id,
                self.end_event_id,
            )
        ):
            raise CampaignValidationError("movement-window IDs must be non-empty")
        if self.end_recv_mono_ns <= self.start_recv_mono_ns:
            raise CampaignValidationError("movement window must advance monotonic time")
        if self.end_recv_wall_ns < self.start_recv_wall_ns:
            raise CampaignValidationError("movement window wall time must not go backward")
        _require_decimal(self.signed_move_bps, "signed_move_bps")
        _require_nonnegative_decimal(self.absolute_move_bps, "absolute_move_bps")
        if self.known_friction_bps is not None:
            _require_nonnegative_decimal(self.known_friction_bps, "known_friction_bps")

    def as_dict(self) -> dict[str, object]:
        return {
            "segment_id": self.segment_id,
            "host_id": self.host_id,
            "boot_id": self.boot_id,
            "start_event_id": self.start_event_id,
            "end_event_id": self.end_event_id,
            "start_recv_mono_ns": self.start_recv_mono_ns,
            "end_recv_mono_ns": self.end_recv_mono_ns,
            "start_recv_wall_ns": self.start_recv_wall_ns,
            "end_recv_wall_ns": self.end_recv_wall_ns,
            "signed_move_bps": serialize_exact_decimal(self.signed_move_bps),
            "absolute_move_bps": serialize_exact_decimal(self.absolute_move_bps),
            "known_friction_bps": (
                None
                if self.known_friction_bps is None
                else serialize_exact_decimal(self.known_friction_bps)
            ),
        }


@dataclass(frozen=True, slots=True)
class SegmentWindowAudit:
    segment_id: str
    candidate_start_count: int
    accepted_window_count: int
    gap_excluded_count: int
    causal_domain_count: int
    cadence_p99_ns: int | None

    def as_dict(self) -> dict[str, object]:
        return {
            "segment_id": self.segment_id,
            "candidate_start_count": self.candidate_start_count,
            "accepted_window_count": self.accepted_window_count,
            "gap_excluded_count": self.gap_excluded_count,
            "causal_domain_count": self.causal_domain_count,
            "cadence_p99_ns": self.cadence_p99_ns,
        }


@dataclass(frozen=True, slots=True)
class CampaignReport:
    report_version: str
    campaign_manifest_sha256: str
    readiness: CampaignReadiness
    gate_decision: GateDecision
    accepted_segment_count: int
    total_valid_non_overlapping_windows: int
    adjudication_window_count: int
    excluded_window_count: int
    movement_quantiles_bps: tuple[tuple[str, Decimal], ...]
    friction_quantiles_bps: tuple[tuple[str, Decimal], ...]
    q50_friction_over_q95_move: Decimal | None
    adjacent_nonzero_sign_agreement_fraction: Decimal | None
    zero_move_fraction: Decimal | None
    fee_evidence_class: EvidenceClass
    latency_evidence_class: EvidenceClass
    funding_boundary_evidence_class: EvidenceClass
    unsupported_components: tuple[str, ...]
    segment_audits: tuple[SegmentWindowAudit, ...]

    def as_dict(self) -> dict[str, object]:
        return {
            "report_version": self.report_version,
            "campaign_manifest_sha256": self.campaign_manifest_sha256,
            "readiness": self.readiness.value,
            "gate_decision": self.gate_decision.value,
            "accepted_segment_count": self.accepted_segment_count,
            "total_valid_non_overlapping_windows": self.total_valid_non_overlapping_windows,
            "adjudication_window_count": self.adjudication_window_count,
            "excluded_window_count": self.excluded_window_count,
            "movement_quantiles_bps": {
                name: serialize_exact_decimal(value)
                for name, value in self.movement_quantiles_bps
            },
            "friction_quantiles_bps": {
                name: serialize_exact_decimal(value)
                for name, value in self.friction_quantiles_bps
            },
            "q50_friction_over_q95_move": (
                None
                if self.q50_friction_over_q95_move is None
                else serialize_exact_decimal(self.q50_friction_over_q95_move)
            ),
            "adjacent_nonzero_sign_agreement_fraction": (
                None
                if self.adjacent_nonzero_sign_agreement_fraction is None
                else serialize_exact_decimal(
                    self.adjacent_nonzero_sign_agreement_fraction
                )
            ),
            "zero_move_fraction": (
                None
                if self.zero_move_fraction is None
                else serialize_exact_decimal(self.zero_move_fraction)
            ),
            "fee_evidence_class": self.fee_evidence_class.value,
            "latency_evidence_class": self.latency_evidence_class.value,
            "funding_boundary_evidence_class": self.funding_boundary_evidence_class.value,
            "unsupported_components": list(self.unsupported_components),
            "segment_audits": [item.as_dict() for item in self.segment_audits],
        }

    def to_json_bytes(self) -> bytes:
        return _canonical_json_bytes(self.as_dict())

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.to_json_bytes()).hexdigest()


def build_campaign_report(
    manifest: CampaignManifest,
    segment_data: tuple[SegmentData, ...],
) -> CampaignReport:
    data_by_id = {item.evidence.segment_id: item for item in segment_data}
    if len(data_by_id) != len(segment_data):
        raise CampaignValidationError("segment_data contains duplicate segment IDs")
    expected_ids = {item.segment_id for item in manifest.segments}
    if set(data_by_id) != expected_ids:
        raise CampaignValidationError(
            "segment_data must match campaign manifest segments exactly"
        )

    all_windows: list[MovementWindow] = []
    audits: list[SegmentWindowAudit] = []
    for evidence in manifest.segments:
        windows, audit = build_segment_windows(
            manifest.config,
            data_by_id[evidence.segment_id],
        )
        all_windows.extend(windows)
        audits.append(audit)

    ordered_windows = tuple(
        sorted(
            all_windows,
            key=lambda item: (
                item.start_recv_wall_ns,
                item.end_recv_wall_ns,
                item.segment_id,
                item.start_event_id,
            ),
        )
    )
    return adjudicate_windows(
        manifest=manifest,
        windows=ordered_windows,
        segment_audits=tuple(audits),
    )


def build_segment_windows(
    config: CampaignConfig,
    segment: SegmentData,
) -> tuple[tuple[MovementWindow, ...], SegmentWindowAudit]:
    horizon_ns = config.target_horizon_seconds * _NS_PER_SECOND
    windows: list[MovementWindow] = []
    candidate_count = 0
    gap_excluded = 0
    cadence_values: list[int] = []

    by_domain: dict[tuple[str, str], list[PrimaryBBOObservation]] = {}
    for item in segment.primary_bbo:
        by_domain.setdefault((item.host_id, item.boot_id), []).append(item)

    domain_cadence: dict[tuple[str, str], int | None] = {}
    for domain, raw_items in by_domain.items():
        ordered = sorted(
            raw_items,
            key=lambda item: (item.recv_mono_ns, item.recv_wall_ns, item.event_id),
        )
        deltas = tuple(
            current.recv_mono_ns - previous.recv_mono_ns
            for previous, current in pairwise(ordered)
            if current.recv_mono_ns > previous.recv_mono_ns
        )
        p99 = None if not deltas else _nearest_rank_int(deltas, 99, 100)
        domain_cadence[domain] = p99
        if p99 is not None:
            cadence_values.append(p99)

        if len(ordered) < 2 or p99 is None:
            continue
        times = tuple(item.recv_mono_ns for item in ordered)
        index = 0
        while index < len(ordered) - 1:
            start = ordered[index]
            target = start.recv_mono_ns + horizon_ns
            if target > times[-1]:
                break
            candidate_count += 1
            end_index = bisect.bisect_left(times, target, lo=index + 1)
            if end_index >= len(ordered):
                break
            end = ordered[end_index]
            if end.recv_mono_ns - target > max(p99, 1):
                gap_excluded += 1
                index += 1
                continue

            signed = signed_return_bps(start.mid, end.mid)
            friction = max(
                top_of_book_round_trip_friction_bps(
                    start.bid,
                    start.ask,
                    fee_bps_per_side=config.fee_scenario_bps_per_side,
                    direction=TradeDirection.LONG,
                ),
                top_of_book_round_trip_friction_bps(
                    start.bid,
                    start.ask,
                    fee_bps_per_side=config.fee_scenario_bps_per_side,
                    direction=TradeDirection.SHORT,
                ),
            )
            windows.append(
                MovementWindow(
                    segment_id=segment.evidence.segment_id,
                    host_id=domain[0],
                    boot_id=domain[1],
                    start_event_id=start.event_id,
                    end_event_id=end.event_id,
                    start_recv_mono_ns=start.recv_mono_ns,
                    end_recv_mono_ns=end.recv_mono_ns,
                    start_recv_wall_ns=start.recv_wall_ns,
                    end_recv_wall_ns=end.recv_wall_ns,
                    signed_move_bps=signed,
                    absolute_move_bps=abs(signed),
                    known_friction_bps=friction,
                )
            )
            index = end_index

    audit = SegmentWindowAudit(
        segment_id=segment.evidence.segment_id,
        candidate_start_count=candidate_count,
        accepted_window_count=len(windows),
        gap_excluded_count=gap_excluded,
        causal_domain_count=len(by_domain),
        cadence_p99_ns=(
            None
            if not cadence_values
            else _nearest_rank_int(tuple(cadence_values), 99, 100)
        ),
    )
    return tuple(windows), audit


def adjudicate_windows(
    *,
    manifest: CampaignManifest,
    windows: tuple[MovementWindow, ...],
    segment_audits: tuple[SegmentWindowAudit, ...] = (),
) -> CampaignReport:
    required = manifest.config.required_non_overlapping_windows
    readiness = (
        CampaignReadiness.READY_FOR_FRONTIER_ADJUDICATION
        if len(windows) >= required
        else CampaignReadiness.COLLECTING
    )
    sample = windows[:required] if len(windows) >= required else windows
    missing_friction = any(item.known_friction_bps is None for item in sample)

    movement_values = tuple(item.absolute_move_bps for item in sample)
    friction_values = tuple(
        item.known_friction_bps
        for item in sample
        if item.known_friction_bps is not None
    )

    movement_quantiles = _movement_quantiles(movement_values)
    friction_quantiles = _friction_quantiles(friction_values)
    ratio: Decimal | None = None
    decision = GateDecision.INCONCLUSIVE

    if readiness is CampaignReadiness.READY_FOR_FRONTIER_ADJUDICATION and not missing_friction:
        q95 = dict(movement_quantiles).get("q95")
        q50_friction = dict(friction_quantiles).get("q50")
        if q95 is not None and q50_friction is not None and q95 > 0:
            ratio = required_capture_fraction(q50_friction, q95)
            decision = (
                GateDecision.PASS_FEASIBILITY
                if q95 > q50_friction
                else GateDecision.FAIL_FEASIBILITY_AT_50S
            )

    sign_agreement = _adjacent_nonzero_sign_agreement(sample)
    zero_fraction = (
        None
        if not sample
        else Decimal(sum(item.signed_move_bps == 0 for item in sample))
        / Decimal(len(sample))
    )
    unsupported = (
        "actual_project_account_fee_tier",
        "submit_to_ack_and_fill_latency",
        "realized_own_order_slippage_and_impact",
        "boundary_aligned_funding_cost",
        "maker_economics",
        "predictability",
    )

    return CampaignReport(
        report_version="frontier-campaign-v1",
        campaign_manifest_sha256=manifest.sha256,
        readiness=readiness,
        gate_decision=decision,
        accepted_segment_count=len(manifest.segments),
        total_valid_non_overlapping_windows=len(windows),
        adjudication_window_count=len(sample),
        excluded_window_count=sum(item.gap_excluded_count for item in segment_audits),
        movement_quantiles_bps=movement_quantiles,
        friction_quantiles_bps=friction_quantiles,
        q50_friction_over_q95_move=ratio,
        adjacent_nonzero_sign_agreement_fraction=sign_agreement,
        zero_move_fraction=zero_fraction,
        fee_evidence_class=EvidenceClass.SCENARIO,
        latency_evidence_class=EvidenceClass.UNKNOWN,
        funding_boundary_evidence_class=EvidenceClass.UNKNOWN,
        unsupported_components=unsupported,
        segment_audits=segment_audits,
    )


def _validate_segments(segments: tuple[SegmentEvidence, ...]) -> None:
    ids: set[str] = set()
    bundles: set[str] = set()
    normalized: set[str] = set()
    sorted_segments = sorted(segments, key=_segment_sort_key)

    for segment in sorted_segments:
        if segment.segment_id in ids:
            raise CampaignValidationError(f"duplicate segment_id: {segment.segment_id}")
        if segment.dataset_bundle_sha256 in bundles:
            raise CampaignValidationError("duplicate dataset bundle digest")
        if segment.normalized_records_sha256 in normalized:
            raise CampaignValidationError("duplicate normalized-records digest")
        ids.add(segment.segment_id)
        bundles.add(segment.dataset_bundle_sha256)
        normalized.add(segment.normalized_records_sha256)

    for previous, current in pairwise(sorted_segments):
        if current.wall_start_ns <= previous.wall_end_ns:
            raise CampaignValidationError(
                "campaign segment wall intervals overlap or touch; quarantine ambiguous boundary"
            )


def _segment_sort_key(segment: SegmentEvidence) -> tuple[int, int, str]:
    return (segment.wall_start_ns, segment.wall_end_ns, segment.segment_id)


def _movement_quantiles(
    values: tuple[Decimal, ...],
) -> tuple[tuple[str, Decimal], ...]:
    if not values:
        return ()
    probabilities = (
        ("q50", Decimal("0.50")),
        ("q75", Decimal("0.75")),
        ("q90", Decimal("0.90")),
        ("q95", Decimal("0.95")),
        ("q97_5", Decimal("0.975")),
        ("q99", Decimal("0.99")),
    )
    return tuple(
        (name, empirical_quantile_nearest_rank(values, probability))
        for name, probability in probabilities
    )


def _friction_quantiles(
    values: tuple[Decimal, ...],
) -> tuple[tuple[str, Decimal], ...]:
    if not values:
        return ()
    return tuple(
        (
            name,
            empirical_quantile_nearest_rank(values, probability),
        )
        for name, probability in (
            ("q50", Decimal("0.50")),
            ("q90", Decimal("0.90")),
            ("q95", Decimal("0.95")),
        )
    )


def _adjacent_nonzero_sign_agreement(
    windows: tuple[MovementWindow, ...],
) -> Decimal | None:
    signs = [
        Decimal(1) if item.signed_move_bps > 0 else Decimal(-1)
        for item in windows
        if item.signed_move_bps != 0
    ]
    if len(signs) < 2:
        return None
    agreements = sum(current == previous for previous, current in pairwise(signs))
    return Decimal(agreements) / Decimal(len(signs) - 1)


def _nearest_rank_int(values: tuple[int, ...], numerator: int, denominator: int) -> int:
    if not values:
        raise CampaignValidationError("integer quantile requires values")
    ordered = sorted(values)
    rank = (numerator * len(ordered) + denominator - 1) // denominator
    return ordered[rank - 1]


def _canonical_json_bytes(value: dict[str, object]) -> bytes:
    return (
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )
        + "\n"
    ).encode()


def _require_sha256(value: str, field: str) -> None:
    if len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
        raise CampaignValidationError(f"{field} must be 64 lowercase hex characters")


def _require_decimal(value: Decimal, field: str) -> None:
    if not isinstance(value, Decimal):
        raise CampaignValidationError(f"{field} must be Decimal")
    try:
        parse_exact_decimal(value)
    except NumericValidationError as exc:
        raise CampaignValidationError(str(exc)) from exc


def _require_nonnegative_decimal(value: Decimal, field: str) -> None:
    _require_decimal(value, field)
    if value < 0:
        raise CampaignValidationError(f"{field} must be non-negative")


def _require_positive_int(value: int, field: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise CampaignValidationError(f"{field} must be a positive integer")


def _require_nonnegative_int(value: int, field: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise CampaignValidationError(f"{field} must be a non-negative integer")
