from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

import pytest

from cryptobot.data.events import (
    BBO,
    AvailabilityKind,
    EventEnvelope,
    EventType,
    ExchangeTimestampSemantics,
    QualityFlag,
    ReferenceBBO,
)
from cryptobot.data.materialize import materialize_research_dataset
from cryptobot.data.normalization_pipeline import FrameOutcome, FrameResult
from cryptobot.research import campaign_dataset as campaign_dataset_module
from cryptobot.research.campaign import CampaignValidationError
from cryptobot.research.campaign_dataset import load_campaign_segment


def _envelope(
    *,
    event_id: str,
    event_type: EventType,
    source: str,
    instrument_id: str,
    native_symbol: str,
    recv_mono_ns: int,
    recv_wall_ns: int,
    raw_offset: int,
    raw_sha: str,
) -> EventEnvelope:
    return EventEnvelope(
        schema_version=1,
        event_id=event_id,
        event_type=event_type,
        source=source,
        instrument_id=instrument_id,
        native_symbol=native_symbol,
        exchange_ts_ns=None,
        exchange_ts_resolution_ns=None,
        exchange_ts_semantics=ExchangeTimestampSemantics.UNKNOWN,
        recv_wall_ns=recv_wall_ns,
        recv_mono_ns=recv_mono_ns,
        host_id="host-a",
        boot_id="boot-a",
        connection_id=f"conn-{source}",
        ingest_seq=raw_offset,
        native_sequence=None,
        native_update_id=None,
        raw_segment_id="raw-segment-a",
        raw_offset=raw_offset,
        raw_sha256=raw_sha,
        parse_version="fixture-v1",
        quality_flags=QualityFlag.MISSING_EXCHANGE_TIME,
        availability_kind=AvailabilityKind.LIVE_CAPTURE,
    )


def _frame(
    *,
    source: str,
    event: BBO | ReferenceBBO,
    recv_mono_ns: int,
    recv_wall_ns: int,
    raw_offset: int,
    raw_sha: str,
    channel: str,
) -> FrameResult:
    return FrameResult(
        outcome=FrameOutcome.EVENTS,
        source_id=source,
        host_id="host-a",
        boot_id="boot-a",
        recv_wall_ns=recv_wall_ns,
        recv_mono_ns=recv_mono_ns,
        connection_id=f"conn-{source}",
        ingest_seq=raw_offset,
        raw_segment_id="raw-segment-a",
        raw_offset=raw_offset,
        raw_sha256=raw_sha,
        parser_name="fixture-v1",
        channel_or_stream=channel,
        events=(event,),
        error=None,
    )


def _materialized_dataset(root: Path) -> Path:
    hl_source = "hyperliquid-mainnet-public"
    bn_source = "binance-usdm-reference-public"
    base_wall = 1_790_000_000_000_000_000

    hl1_sha = "1" * 64
    hl1 = BBO(
        envelope=_envelope(
            event_id="hl-bbo-1",
            event_type=EventType.BBO,
            source=hl_source,
            instrument_id="hyperliquid.mainnet.perpetual.btc",
            native_symbol="BTC",
            recv_mono_ns=1_000_000_000,
            recv_wall_ns=base_wall + 1_000_000_000,
            raw_offset=1,
            raw_sha=hl1_sha,
        ),
        bid_price=Decimal("100"),
        bid_size=Decimal("2"),
        ask_price=Decimal("101"),
        ask_size=Decimal("3"),
    )

    hl2_sha = "2" * 64
    hl2 = BBO(
        envelope=_envelope(
            event_id="hl-bbo-2",
            event_type=EventType.BBO,
            source=hl_source,
            instrument_id="hyperliquid.mainnet.perpetual.btc",
            native_symbol="BTC",
            recv_mono_ns=51_000_000_000,
            recv_wall_ns=base_wall + 51_000_000_000,
            raw_offset=2,
            raw_sha=hl2_sha,
        ),
        bid_price=Decimal("102"),
        bid_size=Decimal("2"),
        ask_price=Decimal("103"),
        ask_size=Decimal("3"),
    )

    bn_sha = "3" * 64
    reference = ReferenceBBO(
        envelope=_envelope(
            event_id="bn-bbo-1",
            event_type=EventType.REFERENCE_BBO,
            source=bn_source,
            instrument_id="binance.usdm.perpetual.btcusdt",
            native_symbol="BTCUSDT",
            recv_mono_ns=2_000_000_000,
            recv_wall_ns=base_wall + 2_000_000_000,
            raw_offset=3,
            raw_sha=bn_sha,
        ),
        bid_price=Decimal("100.1"),
        bid_size=Decimal("1"),
        ask_price=Decimal("100.2"),
        ask_size=Decimal("1"),
        sampling_mode="NATIVE",
    )

    results = (
        _frame(
            source=hl_source,
            event=hl1,
            recv_mono_ns=1_000_000_000,
            recv_wall_ns=base_wall + 1_000_000_000,
            raw_offset=1,
            raw_sha=hl1_sha,
            channel="bbo",
        ),
        _frame(
            source=bn_source,
            event=reference,
            recv_mono_ns=2_000_000_000,
            recv_wall_ns=base_wall + 2_000_000_000,
            raw_offset=3,
            raw_sha=bn_sha,
            channel="btcusdt@bookTicker",
        ),
        _frame(
            source=hl_source,
            event=hl2,
            recv_mono_ns=51_000_000_000,
            recv_wall_ns=base_wall + 51_000_000_000,
            raw_offset=2,
            raw_sha=hl2_sha,
            channel="bbo",
        ),
    )
    materialized = materialize_research_dataset(results, root)
    return materialized.output_dir


def test_campaign_segment_loader_accepts_valid_materialized_dataset(
    tmp_path: Path,
) -> None:
    dataset = _materialized_dataset(tmp_path / "dataset")

    loaded = load_campaign_segment(dataset, segment_id="segment-001")

    evidence = loaded.data.evidence
    assert evidence.segment_id == "segment-001"
    assert evidence.raw_frame_count == 3
    assert evidence.normalized_event_count == 3
    assert evidence.source_ids == (
        "binance-usdm-reference-public",
        "hyperliquid-mainnet-public",
    )
    assert evidence.causal_domains == (("host-a", "boot-a"),)
    assert evidence.primary_bbo_count == 2
    assert evidence.primary_l2_count == 0
    assert len(loaded.data.primary_bbo) == 2
    assert loaded.data.primary_bbo[0].bid == Decimal("100")
    assert loaded.data.primary_bbo[1].ask == Decimal("103")
    assert len(loaded.manifest_sha256) == 64


def test_campaign_segment_loader_rejects_tampered_parquet(
    tmp_path: Path,
) -> None:
    dataset = _materialized_dataset(tmp_path / "dataset")
    path = dataset / "bbo.parquet"
    path.write_bytes(path.read_bytes() + b"tamper")

    with pytest.raises(CampaignValidationError, match="hash mismatch"):
        load_campaign_segment(dataset, segment_id="segment-001")


def test_campaign_segment_loader_rejects_tampered_bundle_digest(
    tmp_path: Path,
) -> None:
    dataset = _materialized_dataset(tmp_path / "dataset")
    manifest_path = dataset / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["bundle_sha256"] = "f" * 64
    manifest_path.write_text(
        json.dumps(manifest, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(CampaignValidationError, match="bundle_sha256"):
        load_campaign_segment(dataset, segment_id="segment-001")


def test_campaign_segment_loader_filters_large_event_scans(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dataset = _materialized_dataset(tmp_path / "dataset")
    original = campaign_dataset_module._READ_TABLE
    event_calls: list[tuple[object, object]] = []

    def guarded_read_table(path: str | Path, **kwargs: object) -> object:
        if Path(path).name == "events.parquet":
            event_calls.append((kwargs.get("columns"), kwargs.get("filters")))
        return original(path, **kwargs)

    monkeypatch.setattr(campaign_dataset_module, "_READ_TABLE", guarded_read_table)

    loaded = load_campaign_segment(dataset, segment_id="segment-001")

    assert loaded.data.evidence.normalized_event_count == 3
    materializing_calls = [(columns, filters) for columns, filters in event_calls if columns != []]
    assert materializing_calls
    assert all(filters is not None for _, filters in materializing_calls)
