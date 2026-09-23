from __future__ import annotations

import json
from pathlib import Path

import pytest

from cryptobot.data.instruments import (
    Environment,
    InstrumentRole,
    InstrumentValidationError,
    ProductType,
    canonical_instrument_id,
    load_instrument_registry,
)


def _instrument(**overrides: object) -> dict[str, object]:
    item: dict[str, object] = {
        "instrument_id": "hyperliquid.mainnet.perpetual.btc",
        "venue": "hyperliquid",
        "environment": "MAINNET",
        "native_symbol": "BTC",
        "base_asset": "BTC",
        "quote_asset": None,
        "settlement_asset": None,
        "margin_asset": None,
        "product_type": "PERPETUAL",
        "role": "PRIMARY",
        "price_decimals": None,
        "size_decimals": None,
        "native_asset_id": None,
    }
    item.update(overrides)
    return item


def _write_registry(tmp_path: Path, instruments: list[dict[str, object]]) -> Path:
    path = tmp_path / "instruments.yaml"
    path.write_text(
        json.dumps({"schema_version": 1, "instruments": instruments}),
        encoding="utf-8",
    )
    return path


def test_project_registry_loads_with_expected_roles_and_unknown_metadata() -> None:
    registry = load_instrument_registry(Path("config/instruments.yaml"))

    btc = registry.get("hyperliquid.mainnet.perpetual.btc")
    eth = registry.get("hyperliquid.mainnet.perpetual.eth")

    assert btc.role is InstrumentRole.PRIMARY
    assert btc.base_asset == "BTC"
    assert eth.role is InstrumentRole.REPLICATION
    assert eth.base_asset == "ETH"
    assert btc.quote_asset is None
    assert btc.margin_asset is None
    assert btc.price_decimals is None
    assert btc.native_asset_id is None


def test_canonical_id_is_deterministic_and_symbol_sensitive() -> None:
    btc = canonical_instrument_id(
        venue="hyperliquid",
        environment=Environment.MAINNET,
        product_type=ProductType.PERPETUAL,
        native_symbol="BTC",
    )
    btc_usd = canonical_instrument_id(
        venue="coinbase",
        environment=Environment.REFERENCE,
        product_type=ProductType.SPOT,
        native_symbol="BTC-USD",
    )
    btc_usdc = canonical_instrument_id(
        venue="coinbase",
        environment=Environment.REFERENCE,
        product_type=ProductType.SPOT,
        native_symbol="BTC-USDC",
    )

    assert btc == "hyperliquid.mainnet.perpetual.btc"
    assert btc_usd == "coinbase.reference.spot.btc_usd"
    assert btc_usdc == "coinbase.reference.spot.btc_usdc"
    assert btc_usd != btc_usdc


def test_instrument_id_must_match_canonical_identity(tmp_path: Path) -> None:
    path = _write_registry(
        tmp_path,
        [_instrument(instrument_id="hyperliquid.mainnet.perpetual.wrong")],
    )

    with pytest.raises(InstrumentValidationError, match="instrument_id must be"):
        load_instrument_registry(path)


def test_duplicate_native_identity_is_rejected(tmp_path: Path) -> None:
    first = _instrument()
    second = _instrument(
        instrument_id="hyperliquid.mainnet.perpetual.btc",
        base_asset="WBTC",
        role="REPLICATION",
    )
    path = _write_registry(tmp_path, [first, second])

    with pytest.raises(InstrumentValidationError, match="duplicate instrument_id"):
        load_instrument_registry(path)


def test_duplicate_native_identity_with_different_id_cannot_bypass_validation(
    tmp_path: Path,
) -> None:
    first = _instrument()
    second = _instrument(
        instrument_id="hyperliquid.mainnet.perpetual.btc_alt",
        role="REPLICATION",
    )
    path = _write_registry(tmp_path, [first, second])

    with pytest.raises(InstrumentValidationError, match="instrument_id must be"):
        load_instrument_registry(path)


def test_reference_environment_requires_reference_role(tmp_path: Path) -> None:
    reference = _instrument(
        instrument_id="coinbase.reference.spot.btc_usd",
        venue="coinbase",
        environment="REFERENCE",
        native_symbol="BTC-USD",
        quote_asset="USD",
        product_type="SPOT",
        role="REPLICATION",
    )
    path = _write_registry(tmp_path, [_instrument(), reference])

    with pytest.raises(InstrumentValidationError, match="REFERENCE role"):
        load_instrument_registry(path)


def test_reference_instrument_preserves_quote_asset_identity(tmp_path: Path) -> None:
    reference = _instrument(
        instrument_id="coinbase.reference.spot.btc_usd",
        venue="coinbase",
        environment="REFERENCE",
        native_symbol="BTC-USD",
        quote_asset="USD",
        product_type="SPOT",
        role="REFERENCE",
    )
    path = _write_registry(tmp_path, [_instrument(), reference])

    registry = load_instrument_registry(path)
    result = registry.get("coinbase.reference.spot.btc_usd")

    assert result.quote_asset == "USD"
    assert result.instrument_id != "hyperliquid.mainnet.perpetual.btc"


def test_registry_requires_exactly_one_primary(tmp_path: Path) -> None:
    btc = _instrument(role="REPLICATION")
    eth = _instrument(
        instrument_id="hyperliquid.mainnet.perpetual.eth",
        native_symbol="ETH",
        base_asset="ETH",
        role="REPLICATION",
    )
    path = _write_registry(tmp_path, [btc, eth])

    with pytest.raises(InstrumentValidationError, match="exactly one PRIMARY"):
        load_instrument_registry(path)


def test_invalid_enum_is_rejected(tmp_path: Path) -> None:
    path = _write_registry(tmp_path, [_instrument(product_type="FUTURE")])

    with pytest.raises(InstrumentValidationError, match="product_type must be one of"):
        load_instrument_registry(path)


def test_unknown_field_is_rejected(tmp_path: Path) -> None:
    item = _instrument()
    item["mystery"] = "value"
    path = _write_registry(tmp_path, [item])

    with pytest.raises(InstrumentValidationError, match="unknown fields: mystery"):
        load_instrument_registry(path)


def test_registry_serialization_is_stable() -> None:
    first = load_instrument_registry(Path("config/instruments.yaml")).as_dict()
    second = load_instrument_registry(Path("config/instruments.yaml")).as_dict()

    assert first == second
