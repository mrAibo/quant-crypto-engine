from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass, replace
from pathlib import Path

import pytest

from cryptobot.data.rawlog import RawFrameMetadata
from cryptobot.runtime.dual_source_recorder import (
    BINANCE_SOURCE_ID,
    HYPERLIQUID_SOURCE_ID,
    DualSourceConfigError,
    load_dual_source_recorder_config,
    merge_capture_sources,
)


@dataclass(frozen=True, slots=True)
class _Frame:
    metadata: RawFrameMetadata
    payload: bytes


def _frame(source: str, seq: int) -> _Frame:
    return _Frame(
        metadata=RawFrameMetadata(
            schema_version=1,
            source_id=source,
            recv_wall_ns=1_000 + seq,
            recv_mono_ns=100 + seq,
            host_id="host",
            boot_id="boot",
            connection_id=f"{source}-conn",
            ingest_seq=seq,
            channel_hint="test",
            capture_flags=("LIVE_CAPTURE", "WS_PUBLIC"),
        ),
        payload=f"{source}-{seq}".encode(),
    )


def test_dual_source_smoke_config_is_strict_and_frozen() -> None:
    config = load_dual_source_recorder_config("config/runtime/dual-source-smoke.json")

    assert config.schema_version == 1
    assert config.hyperliquid.source_id == HYPERLIQUID_SOURCE_ID
    assert config.hyperliquid.coins == ("BTC", "ETH")
    assert config.hyperliquid.channels == (
        "l2Book",
        "bbo",
        "trades",
        "activeAssetCtx",
    )
    assert config.binance.source_id == BINANCE_SOURCE_ID
    assert config.recorder.seal_on_shutdown
    assert config.run_duration_seconds == 30.0


def test_dual_source_config_rejects_wrong_frozen_source(tmp_path: Path) -> None:
    source = Path("config/runtime/dual-source-smoke.json")
    raw = source.read_text(encoding="utf-8").replace(
        HYPERLIQUID_SOURCE_ID,
        "wrong-source",
        1,
    )
    path = tmp_path / "bad.json"
    path.write_text(raw, encoding="utf-8")

    with pytest.raises(DualSourceConfigError, match="source_id"):
        load_dual_source_recorder_config(path)


def test_dual_source_config_rejects_manifest_outside_storage() -> None:
    config = load_dual_source_recorder_config("config/runtime/dual-source-smoke.json")

    with pytest.raises(DualSourceConfigError, match="inside storage_root"):
        replace(config, manifest_path=Path("elsewhere/manifest.json"))


def test_multiplexer_preserves_every_frame_from_finite_sources() -> None:
    async def scenario() -> None:
        async def source(name: str, count: int) -> AsyncIterator[_Frame]:
            for seq in range(1, count + 1):
                await asyncio.sleep(0)
                yield _frame(name, seq)

        merged = merge_capture_sources(
            (
                source(HYPERLIQUID_SOURCE_ID, 3),
                source(BINANCE_SOURCE_ID, 2),
            ),
            queue_capacity=1,
        )
        observed = [frame async for frame in merged]

        assert len(observed) == 5
        assert {frame.payload for frame in observed} == {
            f"{HYPERLIQUID_SOURCE_ID}-1".encode(),
            f"{HYPERLIQUID_SOURCE_ID}-2".encode(),
            f"{HYPERLIQUID_SOURCE_ID}-3".encode(),
            f"{BINANCE_SOURCE_ID}-1".encode(),
            f"{BINANCE_SOURCE_ID}-2".encode(),
        }

    asyncio.run(scenario())


def test_multiplexer_propagates_source_failure_and_cancels_peer() -> None:
    async def scenario() -> None:
        peer_cancelled = asyncio.Event()

        async def peer() -> AsyncIterator[_Frame]:
            try:
                yield _frame(HYPERLIQUID_SOURCE_ID, 1)
                while True:
                    await asyncio.sleep(3600)
            finally:
                peer_cancelled.set()

        async def failing() -> AsyncIterator[_Frame]:
            yield _frame(BINANCE_SOURCE_ID, 1)
            raise RuntimeError("source exploded")

        stream = merge_capture_sources(
            (peer(), failing()),
            queue_capacity=2,
        )
        seen = 0
        with pytest.raises(RuntimeError, match="source exploded"):
            async for _ in stream:
                seen += 1

        assert seen >= 1
        assert peer_cancelled.is_set()

    asyncio.run(scenario())


def test_multiplexer_rejects_invalid_capacity() -> None:
    async def scenario() -> None:
        async def empty() -> AsyncIterator[_Frame]:
            if False:
                yield _frame(HYPERLIQUID_SOURCE_ID, 1)

        stream = merge_capture_sources((empty(),), queue_capacity=0)
        with pytest.raises(DualSourceConfigError, match="positive integer"):
            await anext(stream)

    asyncio.run(scenario())
