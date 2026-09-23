from __future__ import annotations

import asyncio
import json
from pathlib import Path

from websockets.asyncio.server import ServerConnection, serve

from cryptobot.adapters.binance.public import (
    MARKET_STREAMS,
    PUBLIC_STREAMS,
    BinanceFrameKind,
    BinanceReconnectPolicy,
    BinanceReferenceAdapter,
    BinanceRoute,
    BinanceTransportSettings,
    classify_binance_payload,
    subscription_request,
)
from cryptobot.data.clock import SystemClock


def test_frozen_stream_sets_are_exactly_btc_eth_bbo_and_aggtrade() -> None:
    assert PUBLIC_STREAMS == ("btcusdt@bookTicker", "ethusdt@bookTicker")
    assert MARKET_STREAMS == ("btcusdt@aggTrade", "ethusdt@aggTrade")


def test_subscription_request_is_deterministic_and_public_only() -> None:
    raw = subscription_request(PUBLIC_STREAMS, 1301)
    decoded = json.loads(raw)

    assert decoded == {
        "id": 1301,
        "method": "SUBSCRIBE",
        "params": ["btcusdt@bookTicker", "ethusdt@bookTicker"],
    }
    assert "api" not in raw.lower()
    assert "key" not in raw.lower()
    assert "secret" not in raw.lower()


def test_subscription_request_rejects_non_unsigned_integer_id() -> None:
    for invalid in (-1, True, "1301"):
        try:
            subscription_request(PUBLIC_STREAMS, invalid)  # type: ignore[arg-type]
        except Exception as exc:
            assert "unsigned integer" in str(exc)
        else:
            raise AssertionError("invalid request id was accepted")


def test_payload_classifier_handles_ack_market_unknown_and_malformed() -> None:
    ack = classify_binance_payload(b'{"result":null,"id":1301}')
    bbo = classify_binance_payload(
        b'{"stream":"btcusdt@bookTicker","data":{"e":"bookTicker"}}'
    )
    trade = classify_binance_payload(
        b'{"stream":"btcusdt@aggTrade","data":{"e":"aggTrade"}}'
    )
    unknown = classify_binance_payload(
        b'{"stream":"btcusdt@markPrice","data":{"e":"markPriceUpdate"}}'
    )
    malformed = classify_binance_payload(b"not-json")

    assert ack.kind is BinanceFrameKind.SUBSCRIPTION_ACK
    assert ack.subscription_ack_id == 1301
    assert bbo.kind is BinanceFrameKind.MARKET_DATA
    assert bbo.event_type == "bookTicker"
    assert trade.kind is BinanceFrameKind.MARKET_DATA
    assert trade.event_type == "aggTrade"
    assert unknown.kind is BinanceFrameKind.UNKNOWN
    assert malformed.kind is BinanceFrameKind.MALFORMED


def test_reconnect_policy_is_bounded() -> None:
    policy = BinanceReconnectPolicy(
        base_delay_seconds=1.0,
        max_delay_seconds=8.0,
        jitter_fraction=0.0,
    )

    assert policy.delay_seconds(1, 0.5) == 1.0
    assert policy.delay_seconds(2, 0.5) == 2.0
    assert policy.delay_seconds(9, 0.5) == 8.0


def test_two_route_fake_server_captures_ack_and_market_data(tmp_path: Path) -> None:
    async def scenario() -> None:
        requests: list[dict[str, object]] = []

        async def handler(websocket: ServerConnection) -> None:
            raw = await websocket.recv()
            assert isinstance(raw, str)
            request = json.loads(raw)
            requests.append(request)
            request_id = request["id"]
            streams = request["params"]
            await websocket.send(json.dumps({"result": None, "id": request_id}))
            if streams == list(PUBLIC_STREAMS):
                await websocket.send(
                    json.dumps(
                        {
                            "stream": "btcusdt@bookTicker",
                            "data": {
                                "e": "bookTicker",
                                "u": 7,
                                "E": 1790196000000,
                                "T": 1790195999999,
                                "s": "BTCUSDT",
                                "ps": "BTCUSDT",
                                "b": "84000.0",
                                "B": "1.2",
                                "a": "84000.1",
                                "A": "1.3",
                                "st": 1,
                            },
                        }
                    )
                )
            else:
                await websocket.send(
                    json.dumps(
                        {
                            "stream": "btcusdt@aggTrade",
                            "data": {
                                "e": "aggTrade",
                                "E": 1790196000001,
                                "s": "BTCUSDT",
                                "a": 99,
                                "p": "84000.05",
                                "q": "0.10",
                                "nq": "0.10",
                                "f": 101,
                                "l": 102,
                                "T": 1790196000000,
                                "m": False,
                                "st": 1,
                            },
                        }
                    )
                )
            await websocket.wait_closed()

        async with serve(handler, "127.0.0.1", 0) as server:
            port = server.sockets[0].getsockname()[1]
            endpoint = f"ws://127.0.0.1:{port}"
            adapter = BinanceReferenceAdapter(
                clock=SystemClock(host_id="host-test", boot_id="boot-test"),
                transport=BinanceTransportSettings(
                    max_message_bytes=1_000_000,
                    receive_queue_high_water=32,
                    open_timeout_seconds=2,
                    close_timeout_seconds=2,
                ),
                public_endpoint=endpoint,
                market_endpoint=endpoint,
                connection_id_factory=lambda route: f"{route}-conn",
            )
            stream = adapter.session_frames()
            frames = []
            try:
                while len(frames) < 4:
                    frames.append(await asyncio.wait_for(anext(stream), timeout=2))
            finally:
                await stream.aclose()

        assert len(requests) == 2
        assert {tuple(request["params"]) for request in requests} == {
            PUBLIC_STREAMS,
            MARKET_STREAMS,
        }
        assert sum(frame.kind is BinanceFrameKind.SUBSCRIPTION_ACK for frame in frames) == 2
        market = [frame for frame in frames if frame.kind is BinanceFrameKind.MARKET_DATA]
        assert {frame.route for frame in market} == {BinanceRoute.PUBLIC, BinanceRoute.MARKET}
        assert {frame.event_type for frame in market} == {"bookTicker", "aggTrade"}
        assert all(frame.metadata.source_id == "binance-usdm-reference-public" for frame in frames)
        assert all("LIVE_CAPTURE" in frame.metadata.capture_flags for frame in frames)

    asyncio.run(scenario())
