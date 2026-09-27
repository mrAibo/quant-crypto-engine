from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from cryptobot.research import development_campaign as dc
from cryptobot.runtime.public_recorder import RuntimeIdentity

PROTOCOL_PATH = Path("artifacts/stage_2/development_campaign_protocol.json")
RUNTIME_CONFIG_PATH = Path("config/runtime/stage2-development-public.json")


def _init(tmp_path: Path) -> Path:
    root = tmp_path / "campaign"
    dc.initialize_campaign_root(
        root,
        protocol_path=PROTOCOL_PATH,
        runtime_config_path=RUNTIME_CONFIG_PATH,
    )
    return root


def _identity(index: int) -> RuntimeIdentity:
    return RuntimeIdentity(
        host_id="host-test",
        boot_id="boot-test",
        run_id=f"run-{index}-test",
    )


def test_protocol_and_runtime_config_are_frozen() -> None:
    raw = PROTOCOL_PATH.read_bytes()
    payload = json.loads(raw)

    assert hashlib.sha256(raw).hexdigest() == (
        "1ab9a735f512dd301392ba568b49ebd0f1e80d676f073b3d502bf73d111bc1d3"
    )
    assert hashlib.sha256(RUNTIME_CONFIG_PATH.read_bytes()).hexdigest() == (
        "8bf2a31ec634b475f1e3b559663bb35e16950c1c721ab73ddc5812cd6b1f03e1"
    )
    assert payload["evidence_role"] == "DEVELOPMENT_ONLY"
    assert payload["duration_seconds"] == 259200
    assert payload["segment_seconds"] == 900
    assert payload["old_confirmation"] == "UNOPENED_AND_EXCLUDED"
    assert payload["model_fitting_allowed"] is False
    assert payload["fresh_registered_test_evidence"] is False
    assert payload["development_eligibility"]["primary_instrument"] == (
        "hyperliquid.mainnet.perpetual.btc"
    )
    assert payload["capture_transport"]["extra_public_frames"] == (
        "PRESERVE_RAW_BUT_EXCLUDE_FROM_TASK027_ELIGIBILITY"
    )


def test_initialize_campaign_root_is_immutable(tmp_path: Path) -> None:
    root = _init(tmp_path)
    first_protocol = (root / "campaign-protocol.json").read_bytes()
    first_runtime = (root / "runtime-config.json").read_bytes()

    _init(tmp_path)

    assert (root / "campaign-protocol.json").read_bytes() == first_protocol
    assert (root / "runtime-config.json").read_bytes() == first_runtime
    (root / "runtime-config.json").write_text("{}\n", encoding="utf-8")
    with pytest.raises(dc.DevelopmentCampaignError, match="differs"):
        _init(tmp_path)


def test_capture_plan_is_fixed_and_final_segment_is_bounded() -> None:
    protocol = dc.build_protocol()
    first = dc.plan_capture(protocol, None, now_wall_ns=100)
    assert first.status == "CAPTURE"
    assert first.duration_seconds == 900.0

    start = dc.CampaignStart(
        protocol_sha256=protocol.sha256,
        first_run_id="run-1-test",
        started_wall_ns=100,
        deadline_wall_ns=100 + dc.DURATION_SECONDS * 1_000_000_000,
    )
    near_deadline = start.deadline_wall_ns - 12_500_000_000
    final = dc.plan_capture(protocol, start, now_wall_ns=near_deadline)
    assert final.status == "CAPTURE"
    assert final.duration_seconds == 12.5

    complete = dc.plan_capture(protocol, start, now_wall_ns=start.deadline_wall_ns)
    assert complete.status == "COMPLETE"
    assert complete.duration_seconds == 0.0


def test_recover_start_uses_earliest_successful_capture_only(tmp_path: Path) -> None:
    root = _init(tmp_path)
    protocol = dc.build_protocol()

    failed = _identity(100)
    accepted = _identity(200)
    dc.record_capture_attempt(root, protocol=protocol, identity=failed, started_wall_ns=100)
    dc.record_capture_attempt(root, protocol=protocol, identity=accepted, started_wall_ns=200)
    accepted_root = root / f"segment-{accepted.run_id}"
    accepted_root.mkdir()
    (accepted_root / "capture-ready.json").write_text("{}\n", encoding="utf-8")

    start = dc.recover_campaign_start(root, protocol=protocol)

    assert start is not None
    assert start.first_run_id == accepted.run_id
    assert start.started_wall_ns == 200
    assert start.deadline_wall_ns == 200 + dc.DURATION_SECONDS * 1_000_000_000


def test_capture_cycle_starts_only_after_successful_capture(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = _init(tmp_path)
    identity = _identity(300)
    times = iter((1_000, 901_000_000_000))

    def fake_capture(
        config: object,
        *,
        campaign_root: str | Path,
        run_duration_seconds: float,
        identity: RuntimeIdentity,
    ) -> SimpleNamespace:
        del config
        assert run_duration_seconds == 900.0
        segment_root = Path(campaign_root) / f"segment-{identity.run_id}"
        segment_root.mkdir()
        (segment_root / "capture-ready.json").write_text("{}\n", encoding="utf-8")
        return SimpleNamespace(
            run_id=identity.run_id,
            segment_root=str(segment_root),
        )

    monkeypatch.setattr(dc, "capture_frontier_evidence_segment_sync", fake_capture)
    result = dc.capture_development_segment_sync(
        root,
        clock_ns=lambda: next(times),
        identity=identity,
    )

    start = dc.load_campaign_start(root)
    assert result.status == "CAPTURE_READY"
    assert start is not None
    assert start.first_run_id == identity.run_id
    assert start.started_wall_ns == 1_000
    assert start.deadline_wall_ns == 1_000 + dc.DURATION_SECONDS * 1_000_000_000


def test_membership_binds_processed_segment_to_fixed_window(tmp_path: Path) -> None:
    root = _init(tmp_path)
    protocol = dc.build_protocol()
    identity = _identity(400)
    dc.record_capture_attempt(root, protocol=protocol, identity=identity, started_wall_ns=100)
    segment_root = root / f"segment-{identity.run_id}"
    segment_root.mkdir()
    evidence = {
        "run_id": identity.run_id,
        "segment": {"segment_id": "raw-segment-400"},
    }
    (segment_root / "segment-evidence.json").write_text(
        json.dumps(evidence, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    start = dc.CampaignStart(
        protocol_sha256=protocol.sha256,
        first_run_id=identity.run_id,
        started_wall_ns=100,
        deadline_wall_ns=1_000,
    )

    membership_path, membership_sha = dc.bind_development_membership(
        segment_root,
        protocol=protocol,
        start=start,
    )
    membership = json.loads(membership_path.read_text(encoding="utf-8"))

    assert hashlib.sha256(membership_path.read_bytes()).hexdigest() == membership_sha
    assert membership["evidence_role"] == "DEVELOPMENT_ONLY"
    assert membership["eligible_decision_wall_ns"] == {
        "start_inclusive": 100,
        "end_exclusive": 1_000,
    }
    assert membership["old_confirmation_used"] is False


def test_membership_rejects_capture_started_at_deadline(tmp_path: Path) -> None:
    root = _init(tmp_path)
    protocol = dc.build_protocol()
    identity = _identity(500)
    dc.record_capture_attempt(root, protocol=protocol, identity=identity, started_wall_ns=1_000)
    segment_root = root / f"segment-{identity.run_id}"
    segment_root.mkdir()
    (segment_root / "segment-evidence.json").write_text(
        '{"run_id":"run-500-test","segment":{"segment_id":"raw-segment-500"}}\n',
        encoding="utf-8",
    )
    start = dc.CampaignStart(protocol.sha256, "run-1-test", 100, 1_000)

    with pytest.raises(dc.DevelopmentCampaignError, match="outside campaign window"):
        dc.bind_development_membership(segment_root, protocol=protocol, start=start)


def test_process_cycle_recovers_unbound_published_segment(tmp_path: Path) -> None:
    root = _init(tmp_path)
    protocol = dc.build_protocol()
    identity = _identity(600)
    dc.record_capture_attempt(root, protocol=protocol, identity=identity, started_wall_ns=100)
    segment_root = root / f"segment-{identity.run_id}"
    segment_root.mkdir()
    (segment_root / "capture-ready.json").write_text("{}\n", encoding="utf-8")
    (segment_root / "segment-evidence.json").write_text(
        '{"run_id":"run-600-test","segment":{"segment_id":"raw-segment-600"}}\n',
        encoding="utf-8",
    )
    assert dc.recover_campaign_start(root, protocol=protocol) is not None

    result = dc.process_development_segment_sync(root)

    assert result.status == "BOUND_RECOVERED"
    assert result.run_id == identity.run_id
    assert result.segment_id == "raw-segment-600"
    assert result.development_membership_sha256 is not None
    assert (segment_root / "development-membership.json").is_file()


def test_status_is_operational_only(tmp_path: Path) -> None:
    root = _init(tmp_path)
    status = dc.development_campaign_status(root)

    assert status["campaign_state"] == "PRESTART"
    assert status["capture_attempt_count"] == 0
    assert status["published_segment_count"] == 0
    assert status["old_confirmation_status"] == "UNOPENED_AND_EXCLUDED"
    assert status["model_fitted"] is False
    assert status["fresh_registered_test_evidence"] is False


def test_protocol_constructor_rejects_frozen_parameter_changes() -> None:
    with pytest.raises(dc.DevelopmentCampaignError, match="72 hours"):
        dc.DevelopmentCampaignProtocol(duration_seconds=1)
    with pytest.raises(dc.DevelopmentCampaignError, match="900 seconds"):
        dc.DevelopmentCampaignProtocol(segment_seconds=1)


def test_campaign_complete_cannot_be_published_early(tmp_path: Path) -> None:
    root = _init(tmp_path)
    protocol = dc.build_protocol()
    start = dc.CampaignStart(protocol.sha256, "run-1-test", 100, 1_000)

    with pytest.raises(dc.DevelopmentCampaignError, match="before the fixed deadline"):
        dc.publish_campaign_complete(
            root,
            protocol=protocol,
            start=start,
            observed_wall_ns=999,
        )
    assert not (root / "campaign-complete.json").exists()
