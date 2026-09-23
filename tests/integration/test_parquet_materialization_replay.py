from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pyarrow.parquet as pq
import pytest

from cryptobot.data.instruments import load_instrument_registry
from cryptobot.data.materialize import materialize_research_dataset
from cryptobot.data.normalization_pipeline import (
    BINANCE_SOURCE_ID,
    HL_SOURCE_ID,
    FrameOutcome,
    normalize_frames,
)
from cryptobot.data.rawlog import RawFrameMetadata, RawLog, iter_raw_frames


def _metadata(
    *,
    source: str,
    mono: int,
    wall: int,
    seq: int,
    channel_hint: str,
) -> RawFrameMetadata:
    flags = (
        ("BINANCE_PUBLIC", "LIVE_CAPTURE", "WS_PUBLIC")
        if source == BINANCE_SOURCE_ID
        else ("LIVE_CAPTURE", "WS_PUBLIC")
    )
    return RawFrameMetadata(
        schema_version=1,
        source_id=source,
        recv_wall_ns=wall,
        recv_mono_ns=mono,
        host_id="shared-recorder",
        boot_id="shared-boot",
        connection_id=f"{source}-conn",
        ingest_seq=seq,
        channel_hint=channel_hint,
        capture_flags=flags,
    )


def _hl_bbo() -> bytes:
    return json.dumps(
        {
            "channel": "bbo",
            "data": {
                "coin": "BTC",
                "time": 1_790_196_100_000,
                "bbo": [
                    {"px": "100", "sz": "1", "n": 1},
                    {"px": "101", "sz": "2", "n": 1},
                ],
            },
        },
        separators=(",", ":"),
    ).encode()


def _hl_trade(tid: int) -> bytes:
    return json.dumps(
        {
            "channel": "trades",
            "data": [
                {
                    "coin": "BTC",
                    "side": "B",
                    "px": "100.5000",
                    "sz": "0.0100",
                    "hash": "0x" + "a" * 64,
                    "time": 1_790_196_100_100,
                    "tid": tid,
                    "users": ["0x" + "1" * 40, "0x" + "2" * 40],
                }
            ],
        },
        separators=(",", ":"),
    ).encode()


def _hl_context() -> bytes:
    return json.dumps(
        {
            "channel": "activeAssetCtx",
            "data": {
                "coin": "BTC",
                "ctx": {
                    "funding": "0.0000100",
                    "markPx": "100.2000",
                    "oraclePx": "100.0000",
                },
            },
        },
        separators=(",", ":"),
    ).encode()


def _binance_bbo() -> bytes:
    return json.dumps(
        {
            "stream": "btcusdt@bookTicker",
            "data": {
                "e": "bookTicker",
                "u": 11,
                "E": 1_790_196_100_200,
                "T": 1_790_196_100_199,
                "s": "BTCUSDT",
                "ps": "BTCUSDT",
                "b": "100.00",
                "B": "1.20",
                "a": "100.10",
                "A": "1.30",
                "st": 1,
            },
        },
        separators=(",", ":"),
    ).encode()


def _binance_trade() -> bytes:
    return json.dumps(
        {
            "stream": "btcusdt@aggTrade",
            "data": {
                "e": "aggTrade",
                "E": 1_790_196_100_300,
                "s": "BTCUSDT",
                "a": 21,
                "p": "100.050",
                "q": "0.100",
                "nq": "0.100",
                "f": 100,
                "l": 101,
                "T": 1_790_196_100_299,
                "m": False,
                "st": 1,
            },
        },
        separators=(",", ":"),
    ).encode()


def _write_segment(
    path: Path,
    segment_id: str,
    source: str,
    frames: list[tuple[int, int, str, bytes]],
) -> None:
    log = RawLog.open(path, segment_id)
    for seq, (mono, wall, hint, payload) in enumerate(frames, start=1):
        log.append(
            _metadata(
                source=source,
                mono=mono,
                wall=wall,
                seq=seq,
                channel_hint=hint,
            ),
            payload,
        )
    log.sync()
    log.close()


def _file_hashes(path: Path) -> dict[str, str]:
    return {
        item.name: hashlib.sha256(item.read_bytes()).hexdigest()
        for item in sorted(path.iterdir())
        if item.is_file()
    }


def _read_rows(path: Path, filename: str) -> list[dict[str, object]]:
    return pq.read_table(path / filename, use_threads=False).to_pylist()


def test_qcr1_to_parquet_is_deterministic_auditable_and_non_deduplicating(
    tmp_path: Path,
) -> None:
    hl_segment = "hl-parquet-segment"
    binance_segment = "binance-parquet-segment"
    hl_path = tmp_path / f"{hl_segment}.raw"
    binance_path = tmp_path / f"{binance_segment}.raw"

    duplicate_trade = _hl_trade(777)
    _write_segment(
        hl_path,
        hl_segment,
        HL_SOURCE_ID,
        [
            (100, 10_100, "bbo", _hl_bbo()),
            (300, 10_300, "trades", duplicate_trade),
            (500, 10_500, "trades", duplicate_trade),
            (700, 10_700, "activeAssetCtx", _hl_context()),
            (
                900,
                10_900,
                "subscriptionResponse",
                b'{"channel":"subscriptionResponse","data":{}}',
            ),
            (
                1_100,
                11_100,
                "trades",
                b'{"channel":"trades","data":[{"coin":"BTC"}]}',
            ),
        ],
    )
    _write_segment(
        binance_path,
        binance_segment,
        BINANCE_SOURCE_ID,
        [
            (200, 10_200, "bookTicker", _binance_bbo()),
            (400, 10_400, "aggTrade", _binance_trade()),
            (800, 10_800, "subscription", b'{"result":null,"id":1301}'),
        ],
    )

    registry = load_instrument_registry("config/instruments.yaml")
    hl_frames = tuple(iter_raw_frames(hl_path, hl_segment))
    binance_frames = tuple(iter_raw_frames(binance_path, binance_segment))
    all_frames = (*hl_frames, *binance_frames)

    first_results = normalize_frames(all_frames, registry)
    reordered_results = normalize_frames(
        (*reversed(binance_frames), *reversed(hl_frames)),
        registry,
    )

    first = materialize_research_dataset(first_results, tmp_path / "dataset-first")
    second = materialize_research_dataset(
        reordered_results,
        tmp_path / "dataset-second",
    )

    assert first.manifest.raw_frame_count == 9
    assert first.manifest.normalized_event_count == 8
    assert first.manifest.causal_domain_count == 1
    assert first.manifest == second.manifest
    assert _file_hashes(first.output_dir) == _file_hashes(second.output_dir)

    frame_rows = _read_rows(first.output_dir, "frames.parquet")
    assert len(frame_rows) == 9
    assert sum(row["outcome"] == FrameOutcome.NOT_APPLICABLE.value for row in frame_rows) == 2
    error_rows = [row for row in frame_rows if row["outcome"] == FrameOutcome.ERROR.value]
    assert len(error_rows) == 1
    assert error_rows[0]["parser_error_code"] == "INVALID_TRADE_OBJECT"

    event_rows = _read_rows(first.output_dir, "events.parquet")
    assert len(event_rows) == 8
    assert [row["recv_mono_ns"] for row in event_rows] == [
        100,
        200,
        300,
        400,
        500,
        700,
        700,
        700,
    ]

    frame_by_raw = {(frame.ref.segment_id, frame.ref.offset): frame for frame in all_frames}
    for row in event_rows:
        raw_key = (row["raw_segment_id"], row["raw_offset"])
        frame = frame_by_raw[raw_key]
        assert row["raw_sha256"] == frame.ref.payload_sha256

    trade_rows = _read_rows(first.output_dir, "trades.parquet")
    assert len(trade_rows) == 2
    assert trade_rows[0]["trade_id"] == trade_rows[1]["trade_id"]
    assert trade_rows[0]["event_id"] != trade_rows[1]["event_id"]
    assert trade_rows[0]["price_exact"] == "100.5000"
    assert trade_rows[0]["size_exact"] == "0.0100"

    reference_trades = _read_rows(first.output_dir, "reference_trades.parquet")
    assert reference_trades[0]["price_exact"] == "100.050"
    assert reference_trades[0]["size_exact"] == "0.100"

    funding = _read_rows(first.output_dir, "funding_rates.parquet")
    assert funding[0]["rate_exact"] == "0.0000100"
    assert funding[0]["kind"] == "CURRENT"

    before = _file_hashes(first.output_dir)
    with pytest.raises(FileExistsError, match="refusing to overwrite"):
        materialize_research_dataset(first_results, first.output_dir)
    assert _file_hashes(first.output_dir) == before
    assert not (tmp_path / ".dataset-first.tmp").exists()
