from __future__ import annotations

import json
import re
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any


class InstrumentValidationError(ValueError):
    """Raised when the instrument registry is structurally or semantically invalid."""


class Environment(StrEnum):
    MAINNET = "MAINNET"
    TESTNET = "TESTNET"
    REFERENCE = "REFERENCE"


class ProductType(StrEnum):
    SPOT = "SPOT"
    PERPETUAL = "PERPETUAL"


class InstrumentRole(StrEnum):
    PRIMARY = "PRIMARY"
    REPLICATION = "REPLICATION"
    REFERENCE = "REFERENCE"


_INSTRUMENT_ID_RE = re.compile(r"^[a-z0-9]+(?:[._-][a-z0-9]+)*$")
_ASSET_RE = re.compile(r"^[A-Z0-9][A-Z0-9._-]*$")
_ROOT_FIELDS = frozenset({"schema_version", "instruments"})
_INSTRUMENT_FIELDS = frozenset(
    {
        "instrument_id",
        "venue",
        "environment",
        "native_symbol",
        "base_asset",
        "quote_asset",
        "settlement_asset",
        "margin_asset",
        "product_type",
        "role",
        "price_decimals",
        "size_decimals",
        "native_asset_id",
    }
)


@dataclass(frozen=True, slots=True)
class Instrument:
    instrument_id: str
    venue: str
    environment: Environment
    native_symbol: str
    base_asset: str
    quote_asset: str | None
    settlement_asset: str | None
    margin_asset: str | None
    product_type: ProductType
    role: InstrumentRole
    price_decimals: int | None
    size_decimals: int | None
    native_asset_id: int | None

    @property
    def native_identity(self) -> tuple[str, Environment, ProductType, str]:
        return (self.venue, self.environment, self.product_type, self.native_symbol)


@dataclass(frozen=True, slots=True)
class InstrumentRegistry:
    schema_version: int
    instruments: tuple[Instrument, ...]

    def get(self, instrument_id: str) -> Instrument:
        for instrument in self.instruments:
            if instrument.instrument_id == instrument_id:
                return instrument
        raise InstrumentValidationError(f"unknown instrument_id: {instrument_id}")

    def as_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "instruments": [
                {
                    "instrument_id": instrument.instrument_id,
                    "venue": instrument.venue,
                    "environment": instrument.environment.value,
                    "native_symbol": instrument.native_symbol,
                    "base_asset": instrument.base_asset,
                    "quote_asset": instrument.quote_asset,
                    "settlement_asset": instrument.settlement_asset,
                    "margin_asset": instrument.margin_asset,
                    "product_type": instrument.product_type.value,
                    "role": instrument.role.value,
                    "price_decimals": instrument.price_decimals,
                    "size_decimals": instrument.size_decimals,
                    "native_asset_id": instrument.native_asset_id,
                }
                for instrument in self.instruments
            ],
        }


def load_instrument_registry(path: str | Path) -> InstrumentRegistry:
    raw = _load_json_yaml_object(path, "instrument registry")
    _require_exact_fields(raw, _ROOT_FIELDS, "instrument registry")

    schema_version = raw["schema_version"]
    if not isinstance(schema_version, int) or isinstance(schema_version, bool) or schema_version != 1:
        raise InstrumentValidationError("schema_version must be integer 1")

    raw_instruments = raw["instruments"]
    if not isinstance(raw_instruments, list) or not raw_instruments:
        raise InstrumentValidationError("instruments must be a non-empty array")

    instruments = tuple(
        _parse_instrument(item, index) for index, item in enumerate(raw_instruments)
    )
    _validate_registry_uniqueness(instruments)
    _validate_roles(instruments)
    return InstrumentRegistry(schema_version=schema_version, instruments=instruments)


def _parse_instrument(raw: Any, index: int) -> Instrument:
    if not isinstance(raw, dict):
        raise InstrumentValidationError(f"instruments[{index}] must be an object")
    _require_exact_fields(raw, _INSTRUMENT_FIELDS, f"instruments[{index}]")

    instrument_id = _required_string(raw, "instrument_id", index)
    if not _INSTRUMENT_ID_RE.fullmatch(instrument_id):
        raise InstrumentValidationError(
            f"instruments[{index}].instrument_id must use lowercase alphanumeric segments"
        )

    venue = _required_string(raw, "venue", index)
    if venue != venue.lower():
        raise InstrumentValidationError(f"instruments[{index}].venue must be lowercase")

    native_symbol = _required_string(raw, "native_symbol", index)
    base_asset = _parse_asset(raw["base_asset"], f"instruments[{index}].base_asset")
    quote_asset = _parse_optional_asset(raw["quote_asset"], f"instruments[{index}].quote_asset")
    settlement_asset = _parse_optional_asset(
        raw["settlement_asset"], f"instruments[{index}].settlement_asset"
    )
    margin_asset = _parse_optional_asset(raw["margin_asset"], f"instruments[{index}].margin_asset")

    return Instrument(
        instrument_id=instrument_id,
        venue=venue,
        environment=_parse_enum(
            Environment, raw["environment"], f"instruments[{index}].environment"
        ),
        native_symbol=native_symbol,
        base_asset=base_asset,
        quote_asset=quote_asset,
        settlement_asset=settlement_asset,
        margin_asset=margin_asset,
        product_type=_parse_enum(
            ProductType, raw["product_type"], f"instruments[{index}].product_type"
        ),
        role=_parse_enum(InstrumentRole, raw["role"], f"instruments[{index}].role"),
        price_decimals=_parse_optional_nonnegative_int(
            raw["price_decimals"], f"instruments[{index}].price_decimals"
        ),
        size_decimals=_parse_optional_nonnegative_int(
            raw["size_decimals"], f"instruments[{index}].size_decimals"
        ),
        native_asset_id=_parse_optional_nonnegative_int(
            raw["native_asset_id"], f"instruments[{index}].native_asset_id"
        ),
    )


def _validate_registry_uniqueness(instruments: tuple[Instrument, ...]) -> None:
    ids: set[str] = set()
    native_identities: set[tuple[str, Environment, ProductType, str]] = set()

    for instrument in instruments:
        if instrument.instrument_id in ids:
            raise InstrumentValidationError(
                f"duplicate instrument_id: {instrument.instrument_id}"
            )
        ids.add(instrument.instrument_id)

        if instrument.native_identity in native_identities:
            venue, environment, product_type, native_symbol = instrument.native_identity
            raise InstrumentValidationError(
                "duplicate venue/environment/product/native_symbol identity: "
                f"{venue}/{environment.value}/{product_type.value}/{native_symbol}"
            )
        native_identities.add(instrument.native_identity)


def _validate_roles(instruments: tuple[Instrument, ...]) -> None:
    primaries = [instrument for instrument in instruments if instrument.role is InstrumentRole.PRIMARY]
    if len(primaries) != 1:
        raise InstrumentValidationError("registry must contain exactly one PRIMARY instrument")


def _load_json_yaml_object(path: str | Path, label: str) -> dict[str, Any]:
    source = Path(path)
    try:
        raw = json.loads(source.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise InstrumentValidationError(
            f"{source} must be JSON-compatible YAML: {exc.msg} at line {exc.lineno}"
        ) from exc
    if not isinstance(raw, dict):
        raise InstrumentValidationError(f"{label} root must be an object")
    return raw


def _require_exact_fields(raw: dict[str, Any], expected: frozenset[str], label: str) -> None:
    unknown = set(raw) - expected
    if unknown:
        raise InstrumentValidationError(
            f"{label} has unknown fields: {', '.join(sorted(unknown))}"
        )
    missing = expected - set(raw)
    if missing:
        raise InstrumentValidationError(
            f"{label} is missing fields: {', '.join(sorted(missing))}"
        )


def _required_string(raw: dict[str, Any], field: str, index: int) -> str:
    value = raw[field]
    if not isinstance(value, str) or not value.strip():
        raise InstrumentValidationError(
            f"instruments[{index}].{field} must be a non-empty string"
        )
    return value.strip()


def _parse_asset(value: Any, field: str) -> str:
    if not isinstance(value, str) or not _ASSET_RE.fullmatch(value):
        raise InstrumentValidationError(f"{field} must be an uppercase asset identifier")
    return value


def _parse_optional_asset(value: Any, field: str) -> str | None:
    if value is None:
        return None
    return _parse_asset(value, field)


def _parse_optional_nonnegative_int(value: Any, field: str) -> int | None:
    if value is None:
        return None
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise InstrumentValidationError(f"{field} must be null or a non-negative integer")
    return value


def _parse_enum[EnumT: StrEnum](enum_type: type[EnumT], value: Any, field: str) -> EnumT:
    if not isinstance(value, str):
        raise InstrumentValidationError(f"{field} must be a string")
    try:
        return enum_type(value)
    except ValueError as exc:
        allowed = ", ".join(member.value for member in enum_type)
        raise InstrumentValidationError(f"{field} must be one of: {allowed}") from exc
