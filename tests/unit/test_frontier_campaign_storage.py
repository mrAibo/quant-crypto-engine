from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from cryptobot.research.campaign import (
    CampaignConfig,
    CampaignReadiness,
    CampaignValidationError,
    GateDecision,
)
from cryptobot.research.campaign_storage import (
    discover_campaign,
    initialize_campaign_root,
    load_campaign_config,
    publish_campaign_report,
)


def _config() -> CampaignConfig:
    return CampaignConfig(
        campaign_id="storage-test",
        fee_scenario_bps_per_side=Decimal("4.5"),
    )


def test_campaign_config_is_created_once_and_round_trips(tmp_path: Path) -> None:
    root = tmp_path / "campaign"

    path = initialize_campaign_root(root, _config())

    assert path == root / "campaign-config.json"
    assert load_campaign_config(root) == _config()

    with pytest.raises(CampaignValidationError, match="overwrite"):
        initialize_campaign_root(root, _config())


def test_campaign_init_rejects_preexisting_segment_directories(tmp_path: Path) -> None:
    root = tmp_path / "campaign"
    (root / "segment-orphan").mkdir(parents=True)

    with pytest.raises(CampaignValidationError, match="segment directories"):
        initialize_campaign_root(root, _config())


def test_campaign_discovery_tracks_incomplete_segments_without_accepting_them(
    tmp_path: Path,
) -> None:
    root = tmp_path / "campaign"
    initialize_campaign_root(root, _config())
    (root / "segment-partial").mkdir()

    discovery = discover_campaign(root)

    assert discovery.manifest.segments == ()
    assert discovery.segments == ()
    assert discovery.incomplete_segment_directories == ("segment-partial",)


def test_empty_campaign_report_is_revisioned_and_deterministic(tmp_path: Path) -> None:
    root = tmp_path / "campaign"
    initialize_campaign_root(root, _config())

    first = publish_campaign_report(root)
    second = publish_campaign_report(root)

    assert first.report_path == second.report_path
    assert first.report_path.read_bytes() == first.report.to_json_bytes()
    assert first.report.readiness is CampaignReadiness.COLLECTING
    assert first.report.gate_decision is GateDecision.INCONCLUSIVE
    assert first.report.total_valid_non_overlapping_windows == 0
    assert first.report.accepted_segment_count == 0
