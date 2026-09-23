from __future__ import annotations

import hashlib
from collections.abc import Callable
from dataclasses import dataclass, replace
from decimal import Decimal
from pathlib import Path
from typing import cast

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from cryptobot.data.events import (
    BBO,
    AvailabilityKind,
    BookLevel,
    EventEnvelope,
    EventType,
    ExchangeTimestampSemantics,
    FundingObservationKind,
    FundingRateObservation,
    L2Snapshot,
    MarkPrice,
    OraclePrice,
    QualityFlag,
    ReferenceBBO,
    ReferenceTrade,
    Trade,
    TradeSide,
)
from cryptobot.data.materialize import (
    DATASET_SCHEMA_VERSION,
    MATERIALIZER_VERSION,
    MaterializationError,
    dataset_schemas,
    materialize_research_dataset,
    read_manifest,
)
type _ReadTableFn = Callable[..., pa.Table]
_READ_TABLE = cast(_ReadTableFn, pq.read_table)

from cryptobot.data.normalization_pipeline import (
    BINANCE_SOURCE_ID,
    HL_SOURCE_ID,
    FrameOutcome,
    FrameResult,
    NormalizedEvent,
    PipelineError,
    PipelineErrorCode,
)


def _sha(offset: int) -> str:
    return hashlib.sha256(f"raw-{offset}".encode()).hexdigest()


def _envelope(
    event_type: EventType,
    event_id: str,
    *,
    source: str,
    host_id: str = "host-a",
    boot_id: str = "boot-a",
    recv_mono_ns: int,
    recv_wall_ns: int,
    raw_offset: int,
    ingest_seq: int,
    instrument_id: str = "hyperliquid.mainnet.perpetual.btc",
    native_symbol: str = "BTC",
    exchange_ts_ns: int | None = 1_790_200_000_000_000_000,
) -> EventEnvelope:
    if exchange_ts_ns is None:
        resolution = None
        semantics = ExchangeTimestampSemantics.UNKNOWN
        quality = QualityFlag.MISSING_EXCHANGE_TIME
    else:
        resolution = 1_000_000
        semantics = ExchangeTimestampSemantics.UNKNOWN
        quality = QualityFlag.NONE
    return EventEnvelope(
        schema_version=1,
        event_id=event_id,
        event_type=event_type,
        source=source,
        instrument_id=instrument_id,
        native_symbol=native_symbol,
        exchange_ts_ns=exchange_ts_ns,
        exchange_ts_resolution_ns=resolution,
        exchange_ts_semantics=semantics,
        recv_wall_ns=recv_wall_ns,
        recv_mono_ns=recv_mono_ns,
        host_id=host_id,
        boot_id=boot_id,
        connection_id=f"{source}-conn",
        ingest_seq=ingest_seq,
        native_sequence=None,
        native_update_id=None,
        raw_segment_id=f"segment-{source}",
        raw_offset=raw_offset,
        raw_sha256=_sha(raw_offset),
        parse_version="test-parser-v1",
        quality_flags=quality,
        availability_kind=AvailabilityKind.LIVE_CAPTURE,
    )


def _frame(
    *,
    source: str,
    mono: int,
    wall: int,
    offset: int,
    seq: int,
    events: tuple[NormalizedEvent, ...] = (),
    outcome: FrameOutcome = FrameOutcome.EVENTS,
    channel: str | None = "test",
    error: PipelineError | None = None,
    host_id: str = "host-a",
    boot_id: str = "boot-a",
) -> FrameResult:
    return FrameResult(
        outcome=outcome,
        source_id=source,
        host_id=host_id,
        boot_id=boot_id,
        recv_wall_ns=wall,
        recv_mono_ns=mono,
        connection_id=f"{source}-conn",
        ingest_seq=seq,
        raw_segment_id=f"segment-{source}",
        raw_offset=offset,
        raw_sha256=_sha(offset),
        parser_name="test-parser-v1",
        channel_or_stream=channel,
        events=events,
        error=error,
    )


def _fixture_results() -> tuple[FrameResult, ...]:
    l2_env = _envelope(
        EventType.L2_SNAPSHOT,
        "event-l2",
        source=HL_SOURCE_ID,
        recv_mono_ns=100,
        recv_wall_ns=1_100,
        raw_offset=10,
        ingest_seq=1,
    )
    l2 = L2Snapshot(
        envelope=l2_env,
        bids=(
            BookLevel(Decimal("100.10"), Decimal("1.2500"), 2),
            BookLevel(Decimal("99.5"), Decimal("2"), 1),
        ),
        asks=(BookLevel(Decimal("100.20"), Decimal("0.75"), 3),),
        depth_limit=None,
        aggregation=None,
        full_snapshot=True,
    )

    bbo_env = _envelope(
        EventType.BBO,
        "event-bbo",
        source=HL_SOURCE_ID,
        recv_mono_ns=200,
        recv_wall_ns=1_200,
        raw_offset=20,
        ingest_seq=2,
    )
    bbo = BBO(
        envelope=bbo_env,
        bid_price=Decimal("100.10"),
        bid_size=Decimal("1.25"),
        ask_price=Decimal("100.20"),
        ask_size=Decimal("0.75"),
    )

    trade1_env = _envelope(
        EventType.TRADE,
        "event-trade-1",
        source=HL_SOURCE_ID,
        recv_mono_ns=300,
        recv_wall_ns=1_300,
        raw_offset=30,
        ingest_seq=3,
    )
    trade1 = Trade(
        envelope=trade1_env,
        price=Decimal("100.15"),
        size=Decimal("0.0100"),
        native_side="B",
        aggressor_side=TradeSide.UNKNOWN,
        trade_id="stable-trade-7",
        transaction_hash="0x" + "a" * 64,
    )

    trade2_env = _envelope(
        EventType.TRADE,
        "event-trade-2",
        source=HL_SOURCE_ID,
        recv_mono_ns=400,
        recv_wall_ns=1_400,
        raw_offset=40,
        ingest_seq=4,
    )
    trade2 = Trade(
        envelope=trade2_env,
        price=Decimal("100.15"),
        size=Decimal("0.0100"),
        native_side="B",
        aggressor_side=TradeSide.UNKNOWN,
        trade_id="stable-trade-7",
        transaction_hash="0x" + "a" * 64,
    )

    funding = FundingRateObservation(
        envelope=_envelope(
            EventType.FUNDING_RATE_OBSERVATION,
            "event-funding",
            source=HL_SOURCE_ID,
            recv_mono_ns=500,
            recv_wall_ns=1_500,
            raw_offset=50,
            ingest_seq=5,
            exchange_ts_ns=None,
        ),
        rate=Decimal("0.0000118657"),
        rate_period_seconds=3600,
        kind=FundingObservationKind.CURRENT,
        effective_boundary_ns=None,
    )
    mark = MarkPrice(
        envelope=_envelope(
            EventType.MARK_PRICE,
            "event-mark",
            source=HL_SOURCE_ID,
            recv_mono_ns=500,
            recv_wall_ns=1_500,
            raw_offset=50,
            ingest_seq=5,
            exchange_ts_ns=None,
        ),
        price=Decimal("100.1250"),
        method=None,
    )
    oracle = OraclePrice(
        envelope=_envelope(
            EventType.ORACLE_PRICE,
            "event-oracle",
            source=HL_SOURCE_ID,
            recv_mono_ns=500,
            recv_wall_ns=1_500,
            raw_offset=50,
            ingest_seq=5,
            exchange_ts_ns=None,
        ),
        price=Decimal("100.00"),
        oracle_id=None,
    )

    ref_bbo_env = _envelope(
        EventType.REFERENCE_BBO,
        "event-ref-bbo",
        source=BINANCE_SOURCE_ID,
        recv_mono_ns=600,
        recv_wall_ns=1_600,
        raw_offset=60,
        ingest_seq=6,
        instrument_id="binance.reference.perpetual.btcusdt",
        native_symbol="BTCUSDT",
    )
    ref_bbo = ReferenceBBO(
        envelope=ref_bbo_env,
        bid_price=Decimal("100.11"),
        bid_size=Decimal("4.0"),
        ask_price=Decimal("100.12"),
        ask_size=Decimal("5.0"),
        sampling_mode="REALTIME_BOOK_TICKER",
    )

    ref_trade_env = _envelope(
        EventType.REFERENCE_TRADE,
        "event-ref-trade",
        source=BINANCE_SOURCE_ID,
        recv_mono_ns=700,
        recv_wall_ns=1_700,
        raw_offset=70,
        ingest_seq=7,
        instrument_id="binance.reference.perpetual.btcusdt",
        native_symbol="BTCUSDT",
    )
    ref_trade = ReferenceTrade(
        envelope=ref_trade_env,
        price=Decimal("100.115"),
        size=Decimal("0.500"),
        native_side="BUY_TAKER",
        aggressor_side=TradeSide.BUY,
        trade_id="agg-99",
    )

    error_offset = 90
    error = PipelineError(
        code=PipelineErrorCode.PARSER_ERROR,
        parser_name="hyperliquid-trade-v1",
        parser_code="INVALID_TRADE_OBJECT",
        detail="trade element is missing required fields",
        raw_segment_id=f"segment-{HL_SOURCE_ID}",
        raw_offset=error_offset,
        raw_sha256=_sha(error_offset),
    )

    results = (
        _frame(
            source=BINANCE_SOURCE_ID,
            mono=700,
            wall=1_700,
            offset=70,
            seq=7,
            events=(ref_trade,),
            channel="aggTrade",
        ),
        _frame(
            source=HL_SOURCE_ID,
            mono=500,
            wall=1_500,
            offset=50,
            seq=5,
            events=(funding, mark, oracle),
            channel="activeAssetCtx",
        ),
        _frame(
            source=HL_SOURCE_ID,
            mono=100,
            wall=1_100,
            offset=10,
            seq=1,
            events=(l2,),
            channel="l2Book",
        ),
        _frame(
            source=HL_SOURCE_ID,
            mono=300,
            wall=1_300,
            offset=30,
            seq=3,
            events=(trade1,),
            channel="trades",
        ),
        _frame(
            source=BINANCE_SOURCE_ID,
            mono=600,
            wall=1_600,
            offset=60,
            seq=6,
            events=(ref_bbo,),
            channel="bookTicker",
        ),
        _frame(
            source=HL_SOURCE_ID,
            mono=200,
            wall=1_200,
            offset=20,
            seq=2,
            events=(bbo,),
            channel="bbo",
        ),
        _frame(
            source=HL_SOURCE_ID,
            mono=400,
            wall=1_400,
            offset=40,
            seq=4,
            events=(trade2,),
            channel="trades",
        ),
        _frame(
            source=HL_SOURCE_ID,
            mono=800,
            wall=1_800,
            offset=80,
            seq=8,
            outcome=FrameOutcome.NOT_APPLICABLE,
            events=(),
            channel="subscriptionResponse",
        ),
        _frame(
            source=HL_SOURCE_ID,
            mono=900,
            wall=1_900,
            offset=error_offset,
            seq=9,
            outcome=FrameOutcome.ERROR,
            events=(),
            channel="trades",
            error=error,
        ),
        _frame(
            source=HL_SOURCE_ID,
            mono=1_000,
            wall=2_000,
            offset=100,
            seq=10,
            outcome=FrameOutcome.EMPTY,
            events=(),
            channel="trades",
        ),
    )
    return results


def _table(path: Path, name: str) -> list[dict[str, object]]:
    rows = _READ_TABLE(path / name, use_threads=False).to_pylist()
    return cast(list[dict[str, object]], rows)


def _file_hashes(path: Path) -> dict[str, str]:
    return {
        item.name: hashlib.sha256(item.read_bytes()).hexdigest()
        for item in sorted(path.iterdir())
        if item.is_file()
    }


def test_dataset_schemas_are_explicit_fixed_and_float_free() -> None:
    schemas = dataset_schemas()

    assert [name for name, _ in schemas] == [
        "frames.parquet",
        "events.parquet",
        "l2_snapshots.parquet",
        "l2_levels.parquet",
        "bbo.parquet",
        "trades.parquet",
        "funding_rates.parquet",
        "mark_prices.parquet",
        "oracle_prices.parquet",
        "reference_bbo.parquet",
        "reference_trades.parquet",
    ]
    for _, schema in schemas:
        assert all(not pa.types.is_floating(field.type) for field in schema)

    trades = dict(schemas)["trades.parquet"]
    assert trades.field("price_exact").type == pa.string()
    assert trades.field("size_exact").type == pa.string()
    funding = dict(schemas)["funding_rates.parquet"]
    assert funding.field("rate_exact").type == pa.string()


def test_materializes_all_supported_payload_tables_and_audit_frames(tmp_path: Path) -> None:
    result = materialize_research_dataset(_fixture_results(), tmp_path / "dataset")
    out = result.output_dir

    assert result.manifest.dataset_schema_version == DATASET_SCHEMA_VERSION
    assert result.manifest.materializer_version == MATERIALIZER_VERSION
    assert result.manifest.raw_frame_count == 10
    assert result.manifest.normalized_event_count == 9
    assert result.manifest.creation_semantics == "DERIVED_REBUILDABLE"
    assert result.manifest.authority == "QCR1_RAW_IS_AUTHORITATIVE"

    frames = _table(out, "frames.parquet")
    assert len(frames) == 10
    assert [row["recv_mono_ns"] for row in frames] == [
        100,
        200,
        300,
        400,
        500,
        600,
        700,
        800,
        900,
        1000,
    ]
    assert any(row["outcome"] == "NOT_APPLICABLE" for row in frames)
    error_rows = [row for row in frames if row["outcome"] == "ERROR"]
    assert len(error_rows) == 1
    assert error_rows[0]["parser_error_code"] == "INVALID_TRADE_OBJECT"

    events = _table(out, "events.parquet")
    assert len(events) == 9
    assert [row["event_id"] for row in events[:5]] == [
        "event-l2",
        "event-bbo",
        "event-trade-1",
        "event-trade-2",
        "event-funding",
    ]
    assert [row["event_ordinal"] for row in events[4:7]] == [0, 1, 2]

    levels = _table(out, "l2_levels.parquet")
    assert [(row["side"], row["level_ordinal"]) for row in levels] == [
        ("BID", 0),
        ("BID", 1),
        ("ASK", 0),
    ]
    assert levels[0]["price_exact"] == "100.10"
    assert levels[0]["size_exact"] == "1.2500"

    trades = _table(out, "trades.parquet")
    assert len(trades) == 2
    assert trades[0]["trade_id"] == trades[1]["trade_id"] == "stable-trade-7"
    assert trades[0]["price_exact"] == "100.15"
    assert trades[0]["size_exact"] == "0.0100"

    funding = _table(out, "funding_rates.parquet")
    assert funding == [
        {
            "event_id": "event-funding",
            "rate_exact": "0.0000118657",
            "rate_period_seconds": 3600,
            "kind": "CURRENT",
            "effective_boundary_ns": None,
        }
    ]
    assert _table(out, "mark_prices.parquet")[0]["price_exact"] == "100.1250"
    assert _table(out, "oracle_prices.parquet")[0]["price_exact"] == "100.00"
    assert _table(out, "reference_bbo.parquet")[0]["sampling_mode"] == "REALTIME_BOOK_TICKER"
    assert _table(out, "reference_trades.parquet")[0]["aggressor_side"] == "BUY"


def test_empty_dataset_writes_every_schema_correct_table(tmp_path: Path) -> None:
    result = materialize_research_dataset((), tmp_path / "empty")

    assert result.manifest.raw_frame_count == 0
    assert result.manifest.normalized_event_count == 0
    assert result.manifest.causal_domain_count == 0
    assert len(result.manifest.tables) == 11
    for name, schema in dataset_schemas():
        table = _READ_TABLE(result.output_dir / name, use_threads=False)
        assert table.num_rows == 0
        assert table.schema.equals(schema, check_metadata=True)


def test_same_input_is_byte_deterministic_under_pinned_stack(tmp_path: Path) -> None:
    first = materialize_research_dataset(_fixture_results(), tmp_path / "first")
    second = materialize_research_dataset(_fixture_results(), tmp_path / "second")

    assert first.manifest == second.manifest
    assert _file_hashes(first.output_dir) == _file_hashes(second.output_dir)
    assert (first.output_dir / "manifest.json").read_bytes() == (
        second.output_dir / "manifest.json"
    ).read_bytes()


def test_existing_destination_is_rejected_without_modification(tmp_path: Path) -> None:
    destination = tmp_path / "published"
    materialize_research_dataset(_fixture_results(), destination)
    before = _file_hashes(destination)

    with pytest.raises(FileExistsError, match="refusing to overwrite"):
        materialize_research_dataset(_fixture_results(), destination)

    assert _file_hashes(destination) == before
    assert not (tmp_path / ".published.tmp").exists()


def test_frame_event_provenance_mismatch_is_hard_failure_and_cleans_temp(
    tmp_path: Path,
) -> None:
    first = _fixture_results()[2]
    broken = replace(first, raw_offset=999)
    destination = tmp_path / "broken"

    with pytest.raises(MaterializationError, match="raw_offset"):
        materialize_research_dataset((broken,), destination)

    assert not destination.exists()
    assert not (tmp_path / ".broken.tmp").exists()


def test_duplicate_event_id_is_rejected_even_when_raw_occurrences_differ(
    tmp_path: Path,
) -> None:
    original = _fixture_results()[3]
    event = cast(Trade, original.events[0])
    env2 = _envelope(
        EventType.TRADE,
        event.envelope.event_id,
        source=HL_SOURCE_ID,
        recv_mono_ns=999,
        recv_wall_ns=1_999,
        raw_offset=999,
        ingest_seq=99,
    )
    duplicate = Trade(
        envelope=env2,
        price=event.price,
        size=event.size,
        native_side=event.native_side,
        aggressor_side=event.aggressor_side,
        trade_id=event.trade_id,
        transaction_hash=event.transaction_hash,
    )
    second = _frame(
        source=HL_SOURCE_ID,
        mono=999,
        wall=1_999,
        offset=999,
        seq=99,
        events=(duplicate,),
        channel="trades",
    )

    with pytest.raises(MaterializationError, match="duplicate normalized event_id"):
        materialize_research_dataset((original, second), tmp_path / "dupe-event")


def test_mixed_causal_domains_are_serialized_deterministically_not_causally(
    tmp_path: Path,
) -> None:
    env_z = _envelope(
        EventType.TRADE,
        "event-z",
        source=HL_SOURCE_ID,
        host_id="host-z",
        boot_id="boot-z",
        recv_mono_ns=1,
        recv_wall_ns=100,
        raw_offset=201,
        ingest_seq=1,
    )
    event_z = Trade(
        envelope=env_z,
        price=Decimal("1"),
        size=Decimal("1"),
        native_side="A",
        aggressor_side=TradeSide.UNKNOWN,
        trade_id="z",
        transaction_hash=None,
    )
    frame_z = _frame(
        source=HL_SOURCE_ID,
        host_id="host-z",
        boot_id="boot-z",
        mono=1,
        wall=100,
        offset=201,
        seq=1,
        events=(event_z,),
    )

    env_a = _envelope(
        EventType.TRADE,
        "event-a",
        source=HL_SOURCE_ID,
        host_id="host-a",
        boot_id="boot-a",
        recv_mono_ns=999,
        recv_wall_ns=999,
        raw_offset=202,
        ingest_seq=2,
    )
    event_a = Trade(
        envelope=env_a,
        price=Decimal("2"),
        size=Decimal("1"),
        native_side="B",
        aggressor_side=TradeSide.UNKNOWN,
        trade_id="a",
        transaction_hash=None,
    )
    frame_a = _frame(
        source=HL_SOURCE_ID,
        host_id="host-a",
        boot_id="boot-a",
        mono=999,
        wall=999,
        offset=202,
        seq=2,
        events=(event_a,),
    )

    materialized = materialize_research_dataset((frame_z, frame_a), tmp_path / "mixed")
    rows = _table(materialized.output_dir, "events.parquet")

    assert materialized.manifest.causal_domain_count == 2
    assert [row["event_id"] for row in rows] == ["event-a", "event-z"]


def test_manifest_contains_no_build_clock_path_or_hostname(tmp_path: Path) -> None:
    result = materialize_research_dataset(_fixture_results(), tmp_path / "dataset")
    manifest_bytes = (result.output_dir / "manifest.json").read_bytes()
    manifest = read_manifest(result.output_dir / "manifest.json")

    rendered = manifest_bytes.decode()
    assert "created_at" not in rendered
    assert "timestamp" not in rendered
    assert "output_dir" not in rendered
    assert str(tmp_path) not in rendered
    assert "hostname" not in rendered
    assert manifest["pyarrow_version"] == pa.__version__


@dataclass(frozen=True, slots=True)
class _UnsupportedEvent:
    envelope: EventEnvelope


def test_unsupported_event_class_is_rejected(tmp_path: Path) -> None:
    envelope = _envelope(
        EventType.TRADE,
        "unsupported-event",
        source=HL_SOURCE_ID,
        recv_mono_ns=1,
        recv_wall_ns=1,
        raw_offset=301,
        ingest_seq=1,
    )
    unsupported = _UnsupportedEvent(envelope)
    frame = _frame(
        source=HL_SOURCE_ID,
        mono=1,
        wall=1,
        offset=301,
        seq=1,
        events=cast(tuple[NormalizedEvent, ...], (unsupported,)),
    )

    with pytest.raises(MaterializationError, match="unsupported normalized event class"):
        materialize_research_dataset((frame,), tmp_path / "unsupported")
