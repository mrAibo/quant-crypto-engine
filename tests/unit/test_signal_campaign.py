from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from cryptobot.data.instruments import InstrumentRole
from cryptobot.research.signal_campaign import (
    SignalCampaignValidationError,
    build_gate_feature_dataset,
    load_gate_dataset_source,
)


def _gate_report_bytes(*, segment_ids: tuple[str, ...] = ("seg-a", "seg-b")) -> bytes:
    payload = {
        "report_version": "frontier-campaign-v1",
        "campaign_manifest_sha256": "a" * 64,
        "accepted_segment_count": len(segment_ids),
        "adjudication_window_count": 2952,
        "readiness": "READY_FOR_FRONTIER_ADJUDICATION",
        "gate_decision": "PASS_FEASIBILITY",
        "segment_audits": [
            {
                "segment_id": segment_id,
                "candidate_start_count": 17,
                "accepted_window_count": 17,
                "gap_excluded_count": 0,
                "cadence_p99_ns": 1,
                "causal_domain_count": 1,
            }
            for segment_id in segment_ids
        ],
    }
    return (json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n").encode()


def test_gate_dataset_source_is_bound_to_frozen_report_sha_and_sample(tmp_path: Path) -> None:
    raw = _gate_report_bytes()
    report = tmp_path / "gate.json"
    report.write_bytes(raw)
    digest = hashlib.sha256(raw).hexdigest()

    source = load_gate_dataset_source(report, expected_report_sha256=digest)

    assert source.gate_report_sha256 == digest
    assert source.campaign_manifest_sha256 == "a" * 64
    assert source.segment_ids == ("seg-a", "seg-b")

    with pytest.raises(SignalCampaignValidationError, match="SHA-256"):
        load_gate_dataset_source(report, expected_report_sha256="b" * 64)

    changed = json.loads(raw)
    changed["adjudication_window_count"] = 2951
    report.write_text(
        json.dumps(changed, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    changed_raw = report.read_bytes()
    with pytest.raises(SignalCampaignValidationError, match="2952"):
        load_gate_dataset_source(
            report,
            expected_report_sha256=hashlib.sha256(changed_raw).hexdigest(),
        )


def test_feature_dataset_build_fails_if_frozen_gate_segment_is_missing(
    tmp_path: Path,
) -> None:
    raw = _gate_report_bytes(segment_ids=("missing-segment",))
    report = tmp_path / "gate.json"
    report.write_bytes(raw)

    with pytest.raises(SignalCampaignValidationError, match="missing locally"):
        build_gate_feature_dataset(
            campaign_root=tmp_path / "campaign",
            gate_report_path=report,
            expected_gate_report_sha256=hashlib.sha256(raw).hexdigest(),
            instrument_id="hyperliquid.mainnet.perpetual.btc",
            reference_instrument_id="binance_usdm.reference.perpetual.btcusdt",
            role=InstrumentRole.PRIMARY,
        )
