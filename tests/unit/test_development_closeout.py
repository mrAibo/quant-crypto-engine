from __future__ import annotations

import json
from pathlib import Path

import pytest

from cryptobot.research import development_campaign as dc
from cryptobot.research.development_closeout import (
    DevelopmentCloseoutError,
    _union_ns,
    closeout_development_campaign,
)
from cryptobot.runtime.public_recorder import RuntimeIdentity

PROTOCOL_PATH = Path("artifacts/stage_2/development_campaign_protocol.json")
RUNTIME_CONFIG_PATH = Path("config/runtime/stage2-development-public.json")
TASK025_REGISTRY = Path("artifacts/stage_2/microstructure_development_registry.json")


def _started_campaign(tmp_path: Path) -> tuple[Path, dc.CampaignStart]:
    root = tmp_path / "campaign"
    dc.initialize_campaign_root(
        root,
        protocol_path=PROTOCOL_PATH,
        runtime_config_path=RUNTIME_CONFIG_PATH,
    )
    protocol = dc.build_protocol()
    identity = RuntimeIdentity(
        host_id="host-test",
        boot_id="boot-test",
        run_id="run-100-test",
    )
    dc.record_capture_attempt(
        root,
        protocol=protocol,
        identity=identity,
        started_wall_ns=100,
    )
    segment = root / f"segment-{identity.run_id}"
    segment.mkdir()
    (segment / "capture-ready.json").write_text("{}\n", encoding="utf-8")
    start = dc.recover_campaign_start(root, protocol=protocol)
    assert start is not None
    return root, start


def test_closeout_is_forbidden_before_fixed_deadline_completion(tmp_path: Path) -> None:
    root, _ = _started_campaign(tmp_path)

    with pytest.raises(DevelopmentCloseoutError, match="forbidden before"):
        closeout_development_campaign(
            root,
            output_root=tmp_path / "output",
            task025_registry_path=TASK025_REGISTRY,
        )

    assert not (tmp_path / "output" / "development-closeout-report.json").exists()


def test_closeout_rejects_tampered_campaign_duration(tmp_path: Path) -> None:
    root, start = _started_campaign(tmp_path)
    path = root / "campaign-start.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["deadline_wall_ns"] = start.deadline_wall_ns - 1
    path.write_text(
        json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(DevelopmentCloseoutError, match="frozen duration"):
        closeout_development_campaign(
            root,
            output_root=tmp_path / "output",
            task025_registry_path=TASK025_REGISTRY,
        )


def test_union_ns_counts_only_unique_published_coverage() -> None:
    assert _union_ns([]) == 0
    assert _union_ns([(10, 20), (15, 30), (40, 50), (50, 55)]) == 35
