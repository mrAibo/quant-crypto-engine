from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path, PurePosixPath

import pytest

from cryptobot.runtime.public_recorder import (
    ParameterBasis,
    PublicRecorderConfig,
    RuntimeConfigError,
    RuntimeIdentity,
    derive_runtime_identity,
    load_public_recorder_config,
)


def _repo_config() -> Path:
    return Path("config/runtime/public-recorder-smoke.json")


def test_committed_smoke_config_is_strict_and_fully_labeled() -> None:
    config = load_public_recorder_config(_repo_config())

    assert config.schema_version == 1
    assert config.endpoint == "wss://api.hyperliquid.xyz/ws"
    assert config.coins == ("BTC", "ETH")
    assert set(config.channels) == {"l2Book", "bbo", "trades", "activeAssetCtx"}
    assert len(config.parameter_bases) == 19
    assert set(config.basis_dict().values()) <= {basis.value for basis in ParameterBasis}
    assert config.run_duration_seconds == 30.0
    assert config.seal_on_shutdown is True


def test_config_rejects_unknown_private_or_trading_fields(tmp_path: Path) -> None:
    raw = json.loads(_repo_config().read_text(encoding="utf-8"))
    raw["parameters"]["api_key"] = {
        "value": "must-not-be-accepted",
        "basis": "EXPERIMENTAL",
    }
    path = tmp_path / "bad.json"
    path.write_text(json.dumps(raw), encoding="utf-8")

    with pytest.raises(RuntimeConfigError, match="unknown fields"):
        load_public_recorder_config(path)


def test_config_rejects_missing_basis(tmp_path: Path) -> None:
    raw = json.loads(_repo_config().read_text(encoding="utf-8"))
    raw["parameters"]["queue_capacity"] = {"value": 10}
    path = tmp_path / "bad.json"
    path.write_text(json.dumps(raw), encoding="utf-8")

    with pytest.raises(RuntimeConfigError, match="missing fields"):
        load_public_recorder_config(path)


def test_config_rejects_scope_expansion_to_other_coins() -> None:
    base = load_public_recorder_config(_repo_config())

    with pytest.raises(RuntimeConfigError, match="exactly BTC and ETH"):
        replace(base, coins=("BTC", "ETH", "SOL"))


def test_config_requires_manifest_inside_storage_root() -> None:
    base = load_public_recorder_config(_repo_config())

    with pytest.raises(RuntimeConfigError, match="inside storage_root"):
        replace(base, manifest_path=PurePosixPath("other/manifest.json"))


def test_identity_derivation_is_stable_with_explicit_sources(tmp_path: Path) -> None:
    machine = tmp_path / "machine-id"
    boot = tmp_path / "boot-id"
    machine.write_text("machine-a\n", encoding="utf-8")
    boot.write_text("boot-a\n", encoding="utf-8")

    first = derive_runtime_identity(
        machine_id_path=machine,
        boot_id_path=boot,
        run_entropy="entropy",
        run_wall_ns=123,
    )
    second = derive_runtime_identity(
        machine_id_path=machine,
        boot_id_path=boot,
        run_entropy="entropy",
        run_wall_ns=123,
    )

    assert first == second
    assert first.host_id.startswith("host-")
    assert first.boot_id.startswith("boot-")
    assert first.run_id.startswith("run-123-")


def test_identity_boot_fallback_is_explicit_and_deterministic(tmp_path: Path) -> None:
    identity = derive_runtime_identity(
        machine_id_path=tmp_path / "missing-machine",
        boot_id_path=tmp_path / "missing-boot",
        hostname="host-name",
        fallback_boot_token="boot-fallback",
        run_entropy="entropy",
        run_wall_ns=456,
    )

    assert identity == RuntimeIdentity(
        host_id=identity.host_id,
        boot_id=identity.boot_id,
        run_id=identity.run_id,
    )
    assert identity.host_id.startswith("host-")
    assert identity.boot_id.startswith("boot-")
    assert identity.run_id.startswith("run-456-")


def test_programmatic_config_keeps_validation_after_replace(tmp_path: Path) -> None:
    base = load_public_recorder_config(_repo_config())
    config: PublicRecorderConfig = replace(
        base,
        storage_root=PurePosixPath(tmp_path.as_posix()),
        manifest_path=PurePosixPath((tmp_path / "manifest.json").as_posix()),
        run_duration_seconds=0.1,
    )

    assert config.run_duration_seconds == 0.1
