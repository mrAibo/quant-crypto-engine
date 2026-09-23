from __future__ import annotations

import hashlib
import json
from decimal import Decimal

import pytest

from cryptobot.adapters.hyperliquid.context import (
    PARSE_VERSION,
    ContextNormalizationStatus,
    ContextParseErrorCode,
    normalize_context_frame,
    serialize_normalized_context,
)
from cryptobot.data.events import (
    ExchangeTimestampSemantics,
    FundingObservationKind,
    FundingRateObservation,
    MarkPrice,
    OraclePrice,
    QualityFlag,
)
from cryptobot.data.instruments import InstrumentRegistry, load_instrument_registry
from cryptobot.data.rawlog import RawFrame, RawFrameMetadata, RawRef


def _registry() -> InstrumentRegistry:
    return load_instrument_registry("config/instruments.yaml")


def _raw_frame(payload: bytes, *, offset: int = 0) -> RawFrame:
    sha = hashlib.sha256(payload).hexdigest()
    return RawFrame(
        ref=RawRef(
            segment_id="context-segment",
            offset=offset,
            frame_length=len(payload) + 100,
            payload_length=len(payload),
            payload_sha256=sha,
            frame_checksum="0" * 64,
        ),
        metadata=RawFrameMetadata(
            schema_version=1,
            source_id="hyperliquid-mainnet-public",
            recv_wall_ns=1_790_196_115_086_000_000,
            recv_mono_ns=456_789,
            host_id="host-test",
            boot_id="boot-test",
            connection_id="conn-test",
            ingest_seq=22,
            channel_hint="activeAssetCtx",
            capture_flags=("LIVE_CAPTURE", "WS_PUBLIC"),
        ),
        payload=payload,
    )


def _ctx(
    *,
    coin: str = "BTC",
    funding: object = "0.0000118657",
    mark_px: object = "84384.0",
    oracle_px: object = "84419.0",
) -> bytes:
    return json.dumps(
        {
            "channel": "activeAssetCtx",
            "data": {
                "coin": coin,
                "ctx": {
                    "dayBaseVlm": "123.45",
                    "dayNtlVlm": "10420000.0",
                    "funding": funding,
                    "impactPxs": ["84380.0", "84390.0"],
                    "markPx": mark_px,
                    "midPx": "84383.5",
                    "openInterest": "1000.25",
                    "oraclePx": oracle_px,
                    "premium": "0.0001",
                    "prevDayPx": "83000.0",
                },
            },
        },
        separators=(",", ":"),
    ).encode()


def test_context_normalizes_three_events_with_no_fabricated_exchange_timestamp() -> None:
    frame = _raw_frame(_ctx(), offset=512)

    result = normalize_context_frame(frame, _registry())

    assert result.status is ContextNormalizationStatus.EVENTS
    assert result.error is None
    assert len(result.events) == 3
    funding, mark, oracle = result.events
    assert isinstance(funding, FundingRateObservation)
    assert isinstance(mark, MarkPrice)
    assert isinstance(oracle, OraclePrice)

    assert funding.rate == Decimal("0.0000118657")
    assert funding.rate_period_seconds == 3600
    assert funding.kind is FundingObservationKind.CURRENT
    assert funding.effective_boundary_ns is None
    assert mark.price == Decimal("84384.0")
    assert oracle.price == Decimal("84419.0")

    for event in result.events:
        envelope = event.envelope
        assert envelope.exchange_ts_ns is None
        assert envelope.exchange_ts_resolution_ns is None
        assert envelope.exchange_ts_semantics is ExchangeTimestampSemantics.UNKNOWN
        assert envelope.quality_flags & QualityFlag.MISSING_EXCHANGE_TIME
        assert envelope.recv_wall_ns == frame.metadata.recv_wall_ns
        assert envelope.raw_segment_id == "context-segment"
        assert envelope.raw_offset == 512
        assert envelope.raw_sha256 == frame.ref.payload_sha256
        assert envelope.parse_version == PARSE_VERSION


def test_context_derived_event_ids_are_distinct_and_deterministic() -> None:
    frame = _raw_frame(_ctx())

    first = normalize_context_frame(frame, _registry())
    second = normalize_context_frame(frame, _registry())

    first_ids = [event.envelope.event_id for event in first.events]
    second_ids = [event.envelope.event_id for event in second.events]
    assert len(set(first_ids)) == 3
    assert first_ids == second_ids
    assert serialize_normalized_context(first.events) == serialize_normalized_context(second.events)


def test_eth_context_maps_to_replication_instrument() -> None:
    result = normalize_context_frame(_raw_frame(_ctx(coin="ETH")), _registry())

    assert len(result.events) == 3
    assert all(
        event.envelope.instrument_id == "hyperliquid.mainnet.perpetual.eth"
        for event in result.events
    )


def test_negative_current_funding_is_valid() -> None:
    result = normalize_context_frame(
        _raw_frame(_ctx(funding="-0.000125")),
        _registry(),
    )

    funding = result.events[0]
    assert isinstance(funding, FundingRateObservation)
    assert funding.rate == Decimal("-0.000125")
    assert funding.kind is FundingObservationKind.CURRENT


def test_additive_future_fields_are_ignored() -> None:
    message = json.loads(_ctx())
    message["futureTop"] = 1
    message["data"]["futureData"] = True
    message["data"]["ctx"]["futureCtx"] = {"opaque": True}

    result = normalize_context_frame(
        _raw_frame(json.dumps(message).encode()),
        _registry(),
    )

    assert result.status is ContextNormalizationStatus.EVENTS
    assert len(result.events) == 3


def test_exact_serialization_preserves_decimal_strings() -> None:
    result = normalize_context_frame(
        _raw_frame(_ctx(funding="1E-8", mark_px="8.43840E+4", oracle_px="84419.00")),
        _registry(),
    )

    decoded = json.loads(serialize_normalized_context(result.events))
    assert decoded[0]["rate"] == "0.00000001"
    assert decoded[1]["price"] == "84384.0"
    assert decoded[2]["price"] == "84419.00"


def test_non_target_channel_is_not_applicable() -> None:
    result = normalize_context_frame(
        _raw_frame(b'{"channel":"trades","data":[]}'),
        _registry(),
    )

    assert result.status is ContextNormalizationStatus.NOT_APPLICABLE
    assert result.channel == "trades"
    assert result.events == ()
    assert result.error is None


@pytest.mark.parametrize(
    ("payload", "code"),
    [
        (b"not-json", ContextParseErrorCode.INVALID_JSON),
        (b"[]", ContextParseErrorCode.INVALID_ENVELOPE),
        (b'{"data":{}}', ContextParseErrorCode.INVALID_ENVELOPE),
        (
            b'{"channel":"activeAssetCtx","data":[]}',
            ContextParseErrorCode.INVALID_CONTEXT_OBJECT,
        ),
        (
            b'{"channel":"activeAssetCtx","data":{"coin":"BTC","ctx":[]}}',
            ContextParseErrorCode.INVALID_CONTEXT_OBJECT,
        ),
        (
            _ctx(coin="SOL"),
            ContextParseErrorCode.UNSUPPORTED_COIN,
        ),
        (
            _ctx(funding=1.0),
            ContextParseErrorCode.INVALID_FUNDING,
        ),
        (
            _ctx(funding="NaN"),
            ContextParseErrorCode.INVALID_FUNDING,
        ),
        (
            _ctx(mark_px="0"),
            ContextParseErrorCode.INVALID_MARK_PRICE,
        ),
        (
            _ctx(mark_px=84384.0),
            ContextParseErrorCode.INVALID_MARK_PRICE,
        ),
        (
            _ctx(oracle_px="-1"),
            ContextParseErrorCode.INVALID_ORACLE_PRICE,
        ),
        (
            _ctx(oracle_px=84419.0),
            ContextParseErrorCode.INVALID_ORACLE_PRICE,
        ),
    ],
)
def test_structured_context_parse_errors(
    payload: bytes,
    code: ContextParseErrorCode,
) -> None:
    result = normalize_context_frame(_raw_frame(payload), _registry())

    assert result.status is ContextNormalizationStatus.ERROR
    assert result.events == ()
    assert result.error is not None
    assert result.error.code is code
    assert result.error.raw_sha256 == hashlib.sha256(payload).hexdigest()
    assert payload not in result.error.detail.encode()


def test_missing_required_context_field_fails_whole_frame() -> None:
    message = json.loads(_ctx())
    del message["data"]["ctx"]["oraclePx"]
    payload = json.dumps(message).encode()

    result = normalize_context_frame(_raw_frame(payload), _registry())

    assert result.status is ContextNormalizationStatus.ERROR
    assert result.events == ()
    assert result.error is not None
    assert result.error.code is ContextParseErrorCode.INVALID_ORACLE_PRICE


def test_raw_sha_mismatch_is_provenance_error() -> None:
    frame = _raw_frame(_ctx())
    bad = RawFrame(
        ref=RawRef(
            segment_id=frame.ref.segment_id,
            offset=frame.ref.offset,
            frame_length=frame.ref.frame_length,
            payload_length=frame.ref.payload_length,
            payload_sha256="f" * 64,
            frame_checksum=frame.ref.frame_checksum,
        ),
        metadata=frame.metadata,
        payload=frame.payload,
    )

    result = normalize_context_frame(bad, _registry())

    assert result.status is ContextNormalizationStatus.ERROR
    assert result.error is not None
    assert result.error.code is ContextParseErrorCode.INVALID_PROVENANCE
