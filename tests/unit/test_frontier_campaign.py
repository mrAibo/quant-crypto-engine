from __future__ import annotations

from decimal import Decimal
from itertools import pairwise

import pytest

from cryptobot.research.campaign import (
    CampaignConfig,
    CampaignManifest,
    CampaignReadiness,
    CampaignValidationError,
    GateDecision,
    MovementWindow,
    SegmentData,
    SegmentEvidence,
    adjudicate_windows,
    build_campaign_report,
    build_segment_windows,
)
from cryptobot.research.frontier_dataset import PrimaryBBOObservation


def _sha(char: str) -> str:
    return char * 64


def _config() -> CampaignConfig:
    return CampaignConfig(
        campaign_id="btc-frontier-50s-v1",
        fee_scenario_bps_per_side=Decimal("4.5"),
    )


def _segment(
    segment_id: str,
    *,
    bundle_char: str,
    normalized_char: str,
    wall_start_ns: int,
    wall_end_ns: int,
    bbo_count: int,
    domains: tuple[tuple[str, str], ...] = (("host-a", "boot-a"),),
) -> SegmentEvidence:
    return SegmentEvidence(
        segment_id=segment_id,
        dataset_bundle_sha256=_sha(bundle_char),
        normalized_records_sha256=_sha(normalized_char),
        dataset_schema_version=1,
        materializer_version="parquet-v1",
        raw_frame_count=100,
        normalized_event_count=120,
        source_ids=(
            "binance-usdm-reference-public",
            "hyperliquid-mainnet-public",
        ),
        causal_domains=domains,
        wall_start_ns=wall_start_ns,
        wall_end_ns=wall_end_ns,
        primary_bbo_count=bbo_count,
        primary_l2_count=2,
    )


def _obs(
    index: int,
    *,
    host: str = "host-a",
    boot: str = "boot-a",
    mono_ns: int,
    wall_ns: int,
    bid: str = "100",
    ask: str = "101",
) -> PrimaryBBOObservation:
    return PrimaryBBOObservation(
        event_id=f"event-{index}",
        host_id=host,
        boot_id=boot,
        recv_mono_ns=mono_ns,
        recv_wall_ns=wall_ns,
        bid=Decimal(bid),
        ask=Decimal(ask),
    )


def _window(
    index: int,
    *,
    move: str,
    friction: str | None = "9",
    segment_id: str = "segment-a",
) -> MovementWindow:
    start_mono = index * 50_000_000_000
    end_mono = start_mono + 50_000_000_000
    start_wall = 1_000_000_000_000 + start_mono
    return MovementWindow(
        segment_id=segment_id,
        host_id="host-a",
        boot_id="boot-a",
        start_event_id=f"start-{index}",
        end_event_id=f"end-{index}",
        start_recv_mono_ns=start_mono,
        end_recv_mono_ns=end_mono,
        start_recv_wall_ns=start_wall,
        end_recv_wall_ns=start_wall + 50_000_000_000,
        signed_move_bps=Decimal(move),
        absolute_move_bps=abs(Decimal(move)),
        known_friction_bps=None if friction is None else Decimal(friction),
    )


def test_campaign_config_is_pre_registered_and_deterministic() -> None:
    config = _config()

    assert config.target_horizon_seconds == 50
    assert config.required_non_overlapping_windows == 2952
    assert config.dkw_confidence == Decimal("0.95")
    assert config.dkw_maximum_cdf_error == Decimal("0.025")

    with pytest.raises(CampaignValidationError, match="50"):
        CampaignConfig(
            campaign_id="bad",
            fee_scenario_bps_per_side=Decimal("4.5"),
            target_horizon_seconds=20,
        )


def test_campaign_manifest_serialization_is_deterministic_and_resume_is_immutable() -> None:
    first = _segment(
        "segment-a",
        bundle_char="a",
        normalized_char="b",
        wall_start_ns=100,
        wall_end_ns=200,
        bbo_count=0,
    )
    second = _segment(
        "segment-b",
        bundle_char="c",
        normalized_char="d",
        wall_start_ns=300,
        wall_end_ns=400,
        bbo_count=0,
    )
    base = CampaignManifest(config=_config())
    one = base.add_segment(first)
    two = one.add_segment(second)

    assert base.segments == ()
    assert one.segments == (first,)
    assert two.segments == (first, second)
    assert two.to_json_bytes() == two.to_json_bytes()
    assert len(two.sha256) == 64


def test_campaign_rejects_duplicate_bundle_and_normalized_digest() -> None:
    first = _segment(
        "segment-a",
        bundle_char="a",
        normalized_char="b",
        wall_start_ns=100,
        wall_end_ns=200,
        bbo_count=0,
    )
    duplicate_bundle = _segment(
        "segment-b",
        bundle_char="a",
        normalized_char="c",
        wall_start_ns=300,
        wall_end_ns=400,
        bbo_count=0,
    )
    duplicate_normalized = _segment(
        "segment-c",
        bundle_char="d",
        normalized_char="b",
        wall_start_ns=500,
        wall_end_ns=600,
        bbo_count=0,
    )

    with pytest.raises(CampaignValidationError, match="bundle"):
        CampaignManifest(config=_config(), segments=(first, duplicate_bundle))
    with pytest.raises(CampaignValidationError, match="normalized"):
        CampaignManifest(config=_config(), segments=(first, duplicate_normalized))


def test_campaign_rejects_overlapping_or_ambiguous_touching_intervals() -> None:
    first = _segment(
        "segment-a",
        bundle_char="a",
        normalized_char="b",
        wall_start_ns=100,
        wall_end_ns=200,
        bbo_count=0,
    )
    overlap = _segment(
        "segment-b",
        bundle_char="c",
        normalized_char="d",
        wall_start_ns=199,
        wall_end_ns=300,
        bbo_count=0,
    )
    touching = _segment(
        "segment-c",
        bundle_char="e",
        normalized_char="f",
        wall_start_ns=200,
        wall_end_ns=300,
        bbo_count=0,
    )

    with pytest.raises(CampaignValidationError, match="overlap"):
        CampaignManifest(config=_config(), segments=(first, overlap))
    with pytest.raises(CampaignValidationError, match="overlap"):
        CampaignManifest(config=_config(), segments=(first, touching))


def test_segment_data_rejects_undeclared_causal_domain_and_count_mismatch() -> None:
    evidence = _segment(
        "segment-a",
        bundle_char="a",
        normalized_char="b",
        wall_start_ns=100,
        wall_end_ns=1_000_000_000_000,
        bbo_count=1,
    )
    bad_domain = _obs(
        1,
        host="host-b",
        boot="boot-b",
        mono_ns=1,
        wall_ns=200,
    )

    with pytest.raises(CampaignValidationError, match="undeclared"):
        SegmentData(evidence=evidence, primary_bbo=(bad_domain,))

    with pytest.raises(CampaignValidationError, match="count"):
        SegmentData(evidence=evidence, primary_bbo=())


def test_no_window_bridges_segment_boundary() -> None:
    # Each segment is individually shorter than 50 seconds. Combined wall span is >50s,
    # but campaign aggregation must not invent a cross-segment window.
    first_obs = (
        _obs(1, mono_ns=0, wall_ns=1_000),
        _obs(2, mono_ns=30_000_000_000, wall_ns=30_000_001_000),
    )
    second_obs = (
        _obs(
            3,
            host="host-b",
            boot="boot-b",
            mono_ns=0,
            wall_ns=40_000_001_000,
        ),
        _obs(
            4,
            host="host-b",
            boot="boot-b",
            mono_ns=30_000_000_000,
            wall_ns=70_000_001_000,
        ),
    )
    first = _segment(
        "segment-a",
        bundle_char="a",
        normalized_char="b",
        wall_start_ns=1_000,
        wall_end_ns=30_000_001_001,
        bbo_count=2,
    )
    second = _segment(
        "segment-b",
        bundle_char="c",
        normalized_char="d",
        wall_start_ns=40_000_001_000,
        wall_end_ns=70_000_001_001,
        bbo_count=2,
        domains=(("host-b", "boot-b"),),
    )
    manifest = CampaignManifest(config=_config(), segments=(first, second))
    report = build_campaign_report(
        manifest,
        (
            SegmentData(first, first_obs),
            SegmentData(second, second_obs),
        ),
    )

    assert report.total_valid_non_overlapping_windows == 0
    assert report.readiness is CampaignReadiness.COLLECTING
    assert report.gate_decision is GateDecision.INCONCLUSIVE


def test_no_window_bridges_boot_boundary_within_segment() -> None:
    observations = (
        _obs(1, mono_ns=0, wall_ns=1_000),
        _obs(2, mono_ns=30_000_000_000, wall_ns=30_000_001_000),
        _obs(
            3,
            host="host-a",
            boot="boot-b",
            mono_ns=0,
            wall_ns=40_000_001_000,
        ),
        _obs(
            4,
            host="host-a",
            boot="boot-b",
            mono_ns=30_000_000_000,
            wall_ns=70_000_001_000,
        ),
    )
    evidence = _segment(
        "segment-a",
        bundle_char="a",
        normalized_char="b",
        wall_start_ns=1_000,
        wall_end_ns=70_000_001_001,
        bbo_count=4,
        domains=(("host-a", "boot-a"), ("host-a", "boot-b")),
    )
    windows, audit = build_segment_windows(
        _config(),
        SegmentData(evidence=evidence, primary_bbo=observations),
    )

    assert windows == ()
    assert audit.causal_domain_count == 2


def test_segment_window_builder_creates_strict_non_overlapping_windows() -> None:
    observations = tuple(
        _obs(
            index,
            mono_ns=index * 10_000_000_000,
            wall_ns=1_000 + index * 10_000_000_000,
            bid=str(100 + index),
            ask=str(101 + index),
        )
        for index in range(16)
    )
    evidence = _segment(
        "segment-a",
        bundle_char="a",
        normalized_char="b",
        wall_start_ns=1_000,
        wall_end_ns=151_000_000_001,
        bbo_count=len(observations),
    )

    windows, audit = build_segment_windows(
        _config(),
        SegmentData(evidence=evidence, primary_bbo=observations),
    )

    assert len(windows) == 3
    assert audit.accepted_window_count == 3
    assert all(
        later.start_recv_mono_ns >= earlier.end_recv_mono_ns for earlier, later in pairwise(windows)
    )


def test_readiness_starts_only_at_2952_windows_and_uses_first_2952() -> None:
    manifest = CampaignManifest(config=_config())
    below = tuple(_window(index, move="10") for index in range(2951))
    ready = (*below, _window(2951, move="10"))
    extra_adverse = ready + tuple(_window(3000 + index, move="0.1") for index in range(100))

    below_report = adjudicate_windows(manifest=manifest, windows=below)
    ready_report = adjudicate_windows(manifest=manifest, windows=ready)
    extra_report = adjudicate_windows(manifest=manifest, windows=extra_adverse)

    assert below_report.readiness is CampaignReadiness.COLLECTING
    assert below_report.gate_decision is GateDecision.INCONCLUSIVE
    assert ready_report.readiness is CampaignReadiness.READY_FOR_FRONTIER_ADJUDICATION
    assert ready_report.adjudication_window_count == 2952
    assert extra_report.adjudication_window_count == 2952
    assert extra_report.movement_quantiles_bps == ready_report.movement_quantiles_bps


def test_q95_strictly_above_q50_friction_passes() -> None:
    manifest = CampaignManifest(config=_config())
    windows = tuple(
        _window(index, move="12" if index >= 2800 else "10", friction="9") for index in range(2952)
    )

    report = adjudicate_windows(manifest=manifest, windows=windows)

    assert report.gate_decision is GateDecision.PASS_FEASIBILITY
    assert dict(report.movement_quantiles_bps)["q95"] == Decimal("12")
    assert dict(report.friction_quantiles_bps)["q50"] == Decimal("9")
    assert report.q50_friction_over_q95_move == Decimal("0.75")


def test_q95_equal_to_q50_friction_does_not_pass() -> None:
    manifest = CampaignManifest(config=_config())
    windows = tuple(_window(index, move="9", friction="9") for index in range(2952))

    report = adjudicate_windows(manifest=manifest, windows=windows)

    assert report.gate_decision is GateDecision.FAIL_FEASIBILITY_AT_50S
    assert report.q50_friction_over_q95_move == Decimal("1")


def test_missing_required_friction_is_inconclusive() -> None:
    manifest = CampaignManifest(config=_config())
    windows = tuple(
        _window(index, move="12", friction=None if index == 100 else "9") for index in range(2952)
    )

    report = adjudicate_windows(manifest=manifest, windows=windows)

    assert report.readiness is CampaignReadiness.READY_FOR_FRONTIER_ADJUDICATION
    assert report.gate_decision is GateDecision.INCONCLUSIVE
    assert report.q50_friction_over_q95_move is None


def test_report_preserves_scenario_unknown_classes_and_dependence_diagnostics() -> None:
    manifest = CampaignManifest(config=_config())
    windows = tuple(
        _window(index, move="10" if index % 2 == 0 else "-10", friction="9")
        for index in range(2952)
    )

    report = adjudicate_windows(manifest=manifest, windows=windows)

    assert report.fee_evidence_class.value == "SCENARIO"
    assert report.latency_evidence_class.value == "UNKNOWN"
    assert report.funding_boundary_evidence_class.value == "UNKNOWN"
    assert report.adjacent_nonzero_sign_agreement_fraction == Decimal("0")
    assert report.zero_move_fraction == Decimal("0")
    assert "predictability" in report.unsupported_components


def test_report_serialization_and_digest_are_deterministic() -> None:
    manifest = CampaignManifest(config=_config())
    windows = tuple(_window(index, move="10", friction="9") for index in range(10))

    first = adjudicate_windows(manifest=manifest, windows=windows)
    second = adjudicate_windows(manifest=manifest, windows=windows)

    assert first.to_json_bytes() == second.to_json_bytes()
    assert first.sha256 == second.sha256
    assert len(first.sha256) == 64
