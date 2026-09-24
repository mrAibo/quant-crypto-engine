from __future__ import annotations

import asyncio
import json
from dataclasses import replace
from decimal import Decimal
from pathlib import Path

from websockets.asyncio.server import ServerConnection, serve

from cryptobot.adapters.binance.public import MARKET_STREAMS, PUBLIC_STREAMS
from cryptobot.research.campaign import CampaignConfig, CampaignReadiness, GateDecision
from cryptobot.research.campaign_storage import (
    initialize_campaign_root,
    publish_campaign_report,
)
from cryptobot.runtime.dual_source_recorder import load_dual_source_recorder_config
from cryptobot.runtime.frontier_segment import (
    capture_frontier_evidence_segment,
    discover_pending_captured_segments,
    process_next_frontier_captured_segment,
)
from cryptobot.runtime.public_recorder import RuntimeIdentity


def _hl_payloads() -> tuple[dict[str, object], ...]:
    return (
        {
            "channel": "bbo",
            "data": {
                "coin": "BTC",
                "time": 1_790_300_000_000,
                "bbo": [
                    {"px": "100", "sz": "1", "n": 1},
                    {"px": "101", "sz": "2", "n": 1},
                ],
            },
        },
        {
            "channel": "l2Book",
            "data": {
                "coin": "BTC",
                "time": 1_790_300_000_001,
                "levels": [
                    [{"px": "100", "sz": "3", "n": 2}],
                    [{"px": "101", "sz": "4", "n": 1}],
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
                    "time": 1_790_300_000_002,
                    "tid": 123,
                    "users": ["0x" + "1" * 40, "0x" + "2" * 40],
                }
            ],
        },
        {
            "channel": "activeAssetCtx",
            "data": {
                "coin": "BTC",
                "ctx": {
                    "funding": "0.00001",
                    "markPx": "100.4",
                    "oraclePx": "100.3",
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
            "E": 1_790_300_000_100,
            "T": 1_790_300_000_099,
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
            "E": 1_790_300_000_200,
            "s": symbol,
            "a": 21,
            "p": "100.05",
            "q": "0.1",
            "nq": "0.1",
            "f": 100,
            "l": 101,
            "T": 1_790_300_000_199,
            "m": False,
            "st": 1,
        },
    }


def test_frontier_segment_runner_publishes_only_after_full_pipeline(
    tmp_path: Path,
) -> None:
    async def scenario() -> None:
        async def hl_handler(websocket: ServerConnection) -> None:
            for _ in range(8):
                raw = await websocket.recv()
                assert isinstance(raw, str)
                request = json.loads(raw)
                assert isinstance(request, dict)
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
            for payload in _hl_payloads():
                await websocket.send(json.dumps(payload, separators=(",", ":")))
            await websocket.wait_closed()

        async def binance_handler(websocket: ServerConnection) -> None:
            raw = await websocket.recv()
            assert isinstance(raw, str)
            request = json.loads(raw)
            assert isinstance(request, dict)
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
            base = load_dual_source_recorder_config("config/runtime/dual-source-smoke.json")
            config = replace(
                base,
                hyperliquid=replace(
                    base.hyperliquid,
                    endpoint=f"ws://127.0.0.1:{hl_port}",
                ),
                binance=replace(
                    base.binance,
                    public_endpoint=f"ws://127.0.0.1:{bn_port}",
                    market_endpoint=f"ws://127.0.0.1:{bn_port}",
                ),
            )

            campaign_root = tmp_path / "campaign"
            initialize_campaign_root(
                campaign_root,
                CampaignConfig(
                    campaign_id="runner-integration-campaign",
                    fee_scenario_bps_per_side=Decimal("4.5"),
                ),
            )
            capture = await capture_frontier_evidence_segment(
                config,
                campaign_root=campaign_root,
                run_duration_seconds=0.15,
                identity=RuntimeIdentity(
                    host_id="host-test",
                    boot_id="boot-test",
                    run_id="segment-test-run",
                ),
            )

        root = Path(capture.segment_root)
        assert capture.run_id == "segment-test-run"
        assert capture.raw_frame_count > 0
        assert (root / "capture-ready.json").is_file()
        assert not (root / "processing-started.json").exists()
        assert not (root / "segment-evidence.json").exists()
        assert discover_pending_captured_segments(campaign_root) == (root,)

        result = process_next_frontier_captured_segment(
            campaign_root,
            fee_scenario_bps_per_side=Decimal("4.5"),
        )
        assert result is not None
        assert discover_pending_captured_segments(campaign_root) == ()
        assert (root / "processing-started.json").is_file()
        assert result.run_id == "segment-test-run"
        assert result.raw_frame_count > 0
        assert result.normalized_event_count > 0
        assert len(result.dataset_bundle_sha256) == 64
        assert len(result.segment_evidence_sha256) == 64
        assert len(result.dataset_manifest_sha256) == 64
        assert (root / "recorder-summary.json").is_file()
        assert (root / "normalization-report.json").is_file()
        assert (root / "frontier-audit.json").is_file()
        assert (root / "segment-evidence.json").is_file()
        assert (root / "dataset" / "manifest.json").is_file()
        assert (root / "raw" / "manifest.json").is_file()

        evidence = json.loads((root / "segment-evidence.json").read_text(encoding="utf-8"))
        assert evidence["acceptance"] == {
            "dataset_bundle_verified": True,
            "normalization_error_count": 0,
            "public_only": True,
            "recorder_exit_code": 0,
            "single_causal_domain": True,
            "table_hashes_verified": True,
        }
        assert evidence["segment"]["segment_id"] == result.segment_id
        assert evidence["segment"]["causal_domains"] == [["host-test", "boot-test"]]

        published = publish_campaign_report(campaign_root)
        assert len(published.discovery.segments) == 1
        assert published.discovery.incomplete_segment_directories == ()
        assert published.report.readiness is CampaignReadiness.COLLECTING
        assert published.report.gate_decision is GateDecision.INCONCLUSIVE
        assert published.report.accepted_segment_count == 1
        assert published.report_path.is_file()

    asyncio.run(scenario())
