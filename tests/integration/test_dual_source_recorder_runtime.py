from __future__ import annotations

import asyncio
import json
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from typing import cast

import pyarrow as pa
import pyarrow.parquet as pq
from websockets.asyncio.server import ServerConnection, serve

from cryptobot.adapters.binance.public import MARKET_STREAMS, PUBLIC_STREAMS
from cryptobot.data.instruments import load_instrument_registry
from cryptobot.data.materialize import materialize_research_dataset
from cryptobot.data.normalization_pipeline import (
    BINANCE_SOURCE_ID,
    FrameOutcome,
    HL_SOURCE_ID,
    build_pipeline_report,
    normalize_frames,
)
from cryptobot.data.rawlog import iter_raw_frames
from cryptobot.runtime.dual_source_recorder import (
    DualSourceExitCode,
    load_dual_source_recorder_config,
    run_dual_source_recorder,
)
from cryptobot.runtime.public_recorder import RuntimeIdentity


type _ReadTableFn = Callable[..., pa.Table]

_READ_TABLE = cast(_ReadTableFn, pq.read_table)


def _hl_market_payloads() -> tuple[dict[str, object], ...]:
    return (
        {
            "channel": "bbo",
            "data": {
                "coin": "BTC",
                "time": 1_790_200_000_000,
                "bbo": [
                    {"px": "100", "sz": "1", "n": 1},
                    {"px": "101", "sz": "2", "n": 1},
                ],
            },
        },
        {
            "channel": "l2Book",
            "data": {
                "coin": "ETH",
                "time": 1_790_200_000_001,
                "levels": [
                    [{"px": "50", "sz": "3", "n": 2}],
                    [{"px": "51", "sz": "4", "n": 1}],
                ],
            },
        },
        {
            "channel": "trades",
            "data": [
                {
                    "coin": "BTC",
                    "side": "B",
                    "px": "100.5",
                    "sz": "0.01",
                    "hash": "0x" + "a" * 64,
                    "time": 1_790_200_000_002,
                    "tid": 123,
                    "users": ["0x" + "1" * 40, "0x" + "2" * 40],
                }
            ],
        },
        {
            "channel": "activeAssetCtx",
            "data": {
                "coin": "ETH",
                "ctx": {
                    "funding": "0.00001",
                    "markPx": "50.2",
                    "oraclePx": "50.0",
                },
            },
        },
    )


def _binance_book(symbol: str) -> dict[str, object]:
    return {
        "stream": f"{symbol.lower()}@bookTicker",
        "data": {
            "e": "bookTicker",
            "u": 11,
            "E": 1_790_200_000_100,
            "T": 1_790_200_000_099,
            "s": symbol,
            "ps": symbol,
            "b": "100.0",
            "B": "1.2",
            "a": "100.1",
            "A": "1.3",
            "st": 1,
        },
    }


def _binance_trade(symbol: str) -> dict[str, object]:
    return {
        "stream": f"{symbol.lower()}@aggTrade",
        "data": {
            "e": "aggTrade",
            "E": 1_790_200_000_200,
            "s": symbol,
            "a": 21,
            "p": "100.05",
            "q": "0.1",
            "nq": "0.1",
            "f": 100,
            "l": 101,
            "T": 1_790_200_000_199,
            "m": False,
            "st": 1,
        },
    }


def test_fake_servers_capture_both_sources_in_one_clock_domain_and_materialize(
    tmp_path: Path,
) -> None:
    async def scenario() -> None:
        hl_requests: list[dict[str, object]] = []
        binance_requests: list[dict[str, object]] = []

        async def hl_handler(websocket: ServerConnection) -> None:
            for _ in range(8):
                raw = await websocket.recv()
                assert isinstance(raw, str)
                request = json.loads(raw)
                assert isinstance(request, dict)
                hl_requests.append(request)
                await websocket.send(
                    json.dumps(
                        {
                            "channel": "subscriptionResponse",
                            "data": {
                                "method": "subscribe",
                                "subscription": request["subscription"],
                            },
                        },
                        separators=(",", ":"),
                    )
                )
            for payload in _hl_market_payloads():
                await websocket.send(json.dumps(payload, separators=(",", ":")))
            await websocket.wait_closed()

        async def binance_handler(websocket: ServerConnection) -> None:
            raw = await websocket.recv()
            assert isinstance(raw, str)
            request = json.loads(raw)
            assert isinstance(request, dict)
            binance_requests.append(request)
            await websocket.send(
                json.dumps(
                    {"result": None, "id": request["id"]},
                    separators=(",", ":"),
                )
            )
            streams = request["params"]
            if streams == list(PUBLIC_STREAMS):
                await websocket.send(json.dumps(_binance_book("BTCUSDT"), separators=(",", ":")))
                await websocket.send(json.dumps(_binance_book("ETHUSDT"), separators=(",", ":")))
            elif streams == list(MARKET_STREAMS):
                await websocket.send(json.dumps(_binance_trade("BTCUSDT"), separators=(",", ":")))
                await websocket.send(json.dumps(_binance_trade("ETHUSDT"), separators=(",", ":")))
            else:
                raise AssertionError("unexpected Binance stream request")
            await websocket.wait_closed()

        async with (
            serve(hl_handler, "127.0.0.1", 0) as hl_server,
            serve(binance_handler, "127.0.0.1", 0) as bn_server,
        ):
            hl_port = hl_server.sockets[0].getsockname()[1]
            bn_port = bn_server.sockets[0].getsockname()[1]
            endpoint_hl = f"ws://127.0.0.1:{hl_port}"
            endpoint_bn = f"ws://127.0.0.1:{bn_port}"

            base = load_dual_source_recorder_config("config/runtime/dual-source-smoke.json")
            root = tmp_path / "capture"
            config = replace(
                base,
                hyperliquid=replace(base.hyperliquid, endpoint=endpoint_hl),
                binance=replace(
                    base.binance,
                    public_endpoint=endpoint_bn,
                    market_endpoint=endpoint_bn,
                ),
                storage_root=root,
                manifest_path=root / "manifest.json",
                run_duration_seconds=0.15,
            )
            summary = await run_dual_source_recorder(
                config,
                identity=RuntimeIdentity(
                    host_id="host-test",
                    boot_id="boot-test",
                    run_id="dual-source-test",
                ),
            )

        assert len(hl_requests) == 8
        assert len(binance_requests) == 2
        assert summary.exit_code == int(DualSourceExitCode.SUCCESS)
        assert summary.status == "SUCCESS"
        assert summary.audit_clean
        assert summary.both_sources_observed
        assert summary.single_expected_clock_domain
        assert summary.clock_domains == (("host-test", "boot-test"),)
        assert summary.all_hyperliquid_acks_observed
        assert summary.expected_hyperliquid_subscription_acks == 8
        assert summary.all_binance_acks_observed
        assert summary.binance_subscription_ack_ids == (1301, 1302)
        assert set(summary.manifest_source_ids) == {HL_SOURCE_ID, BINANCE_SOURCE_ID}
        assert summary.recorder.counters.received_frames == summary.recorder.counters.durable_frames
        assert summary.recorder.final_path is not None
        assert summary.recorder.segment_id is not None

        frames = tuple(
            iter_raw_frames(
                summary.recorder.final_path,
                summary.recorder.segment_id,
            )
        )
        assert len(frames) == summary.recorder.counters.durable_frames
        assert {(frame.metadata.host_id, frame.metadata.boot_id) for frame in frames} == {
            ("host-test", "boot-test")
        }
        assert {frame.metadata.source_id for frame in frames} == {
            HL_SOURCE_ID,
            BINANCE_SOURCE_ID,
        }

        registry = load_instrument_registry("config/instruments.yaml")
        normalized = normalize_frames(frames, registry)
        report = build_pipeline_report(normalized)
        assert report.total_raw_frames == len(frames)
        assert report.causal_domain_count == 1
        assert report.normalized_record_count >= 8
        assert not any(result.outcome is FrameOutcome.ERROR for result in normalized)
        assert any(result.source_id == HL_SOURCE_ID and result.events for result in normalized)
        assert any(result.source_id == BINANCE_SOURCE_ID and result.events for result in normalized)

        materialized = materialize_research_dataset(
            normalized,
            tmp_path / "parquet",
        )
        assert materialized.manifest.raw_frame_count == len(frames)
        assert materialized.manifest.normalized_event_count == report.normalized_record_count
        event_rows = _READ_TABLE(
            materialized.output_dir / "events.parquet",
            use_threads=False,
        )
        assert event_rows.num_rows == report.normalized_record_count

    asyncio.run(scenario())
