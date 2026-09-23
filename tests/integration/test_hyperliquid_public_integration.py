from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

from websockets.asyncio.server import ServerConnection, serve

from cryptobot.adapters.hyperliquid.public import (
    CapturedPublicFrame,
    FrameKind,
    HyperliquidPublicAdapter,
    ReconnectPolicy,
    TransportSettings,
)
from cryptobot.data.clock import ClockSample


@dataclass
class IncrementingClock:
    wall_ns: int = 1_000_000
    mono_ns: int = 2_000_000

    def sample(self) -> ClockSample:
        self.wall_ns += 10
        self.mono_ns += 10
        return ClockSample(
            wall_ns=self.wall_ns,
            mono_ns=self.mono_ns,
            host_id="test-host",
            boot_id="test-boot",
        )


def _transport(heartbeat_idle_seconds: float = 1.0) -> TransportSettings:
    return TransportSettings(
        heartbeat_idle_seconds=heartbeat_idle_seconds,
        max_message_bytes=1_048_576,
        receive_queue_high_water=16,
        open_timeout_seconds=2,
        close_timeout_seconds=2,
    )


async def _collect(stream: AsyncIterator[CapturedPublicFrame]) -> list[CapturedPublicFrame]:
    return [frame async for frame in stream]


def test_session_preserves_exact_payload_and_tracks_subscription_acks() -> None:
    async def scenario() -> None:
        market_payload = '{  "channel":"trades", "data":[{"px":"1.00"}] }'

        async def handler(websocket: ServerConnection) -> None:
            for _ in range(2):
                request_raw = await websocket.recv()
                assert isinstance(request_raw, str)
                request = json.loads(request_raw)
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
            await websocket.send(market_payload)

        async with serve(handler, "127.0.0.1", 0) as server:
            socket = server.sockets[0]
            port = socket.getsockname()[1]
            adapter = HyperliquidPublicAdapter(
                source_id="hl-test",
                coins=("BTC",),
                channels=("trades", "bbo"),
                clock=IncrementingClock(),
                transport=_transport(),
                endpoint=f"ws://127.0.0.1:{port}",
                connection_id_factory=lambda: "conn-1",
            )

            frames = await _collect(adapter.session_frames())

        assert len(frames) == 3
        assert [frame.pending_subscription_count for frame in frames[:2]] == [1, 0]
        assert all(frame.kind is FrameKind.SUBSCRIPTION_ACK for frame in frames[:2])

        market = frames[2]
        assert market.kind is FrameKind.MARKET_DATA
        assert market.channel == "trades"
        assert market.payload == market_payload.encode("utf-8")
        assert market.metadata.connection_id == "conn-1"
        assert market.metadata.ingest_seq == 3
        assert market.metadata.capture_flags == ("LIVE_CAPTURE", "WS_PUBLIC")

    asyncio.run(scenario())


def test_idle_connection_sends_application_ping_and_captures_pong() -> None:
    async def scenario() -> None:
        async def handler(websocket: ServerConnection) -> None:
            request_raw = await websocket.recv()
            assert isinstance(request_raw, str)
            request = json.loads(request_raw)
            await websocket.send(
                json.dumps(
                    {
                        "channel": "subscriptionResponse",
                        "data": {
                            "method": "subscribe",
                            "subscription": request["subscription"],
                        },
                    }
                )
            )
            ping = await websocket.recv()
            assert ping == '{"method":"ping"}'
            await websocket.send('{"channel":"pong"}')

        async with serve(handler, "127.0.0.1", 0) as server:
            port = server.sockets[0].getsockname()[1]
            adapter = HyperliquidPublicAdapter(
                source_id="hl-test",
                coins=("BTC",),
                channels=("bbo",),
                clock=IncrementingClock(),
                transport=_transport(heartbeat_idle_seconds=0.02),
                endpoint=f"ws://127.0.0.1:{port}",
                connection_id_factory=lambda: "conn-heartbeat",
            )

            frames = await _collect(adapter.session_frames())

        assert [frame.kind for frame in frames] == [
            FrameKind.SUBSCRIPTION_ACK,
            FrameKind.HEARTBEAT_PONG,
        ]
        assert frames[-1].payload == b'{"channel":"pong"}'

    asyncio.run(scenario())


def test_reconnect_creates_new_connection_and_resubscribes() -> None:
    async def scenario() -> None:
        sessions = 0
        requests: list[dict[str, Any]] = []
        sleeps: list[float] = []
        connection_ids = iter(("conn-a", "conn-b"))

        async def fake_sleep(delay: float) -> None:
            sleeps.append(delay)

        async def handler(websocket: ServerConnection) -> None:
            nonlocal sessions
            sessions += 1
            request_raw = await websocket.recv()
            assert isinstance(request_raw, str)
            request = json.loads(request_raw)
            requests.append(request)
            await websocket.send(
                json.dumps(
                    {
                        "channel": "subscriptionResponse",
                        "data": {
                            "method": "subscribe",
                            "subscription": request["subscription"],
                        },
                    }
                )
            )
            await websocket.send(
                json.dumps(
                    {
                        "channel": "bbo",
                        "data": {"coin": "BTC", "session": sessions},
                    }
                )
            )

        async with serve(handler, "127.0.0.1", 0) as server:
            port = server.sockets[0].getsockname()[1]
            adapter = HyperliquidPublicAdapter(
                source_id="hl-test",
                coins=("BTC",),
                channels=("bbo",),
                clock=IncrementingClock(),
                transport=_transport(),
                endpoint=f"ws://127.0.0.1:{port}",
                connection_id_factory=lambda: next(connection_ids),
                sleep=fake_sleep,
                random_unit=lambda: 0.5,
            )
            frames = await _collect(
                adapter.frames(
                    ReconnectPolicy(
                        base_delay_seconds=2,
                        max_delay_seconds=8,
                        jitter_fraction=0,
                    ),
                    max_sessions=2,
                )
            )

        assert sessions == 2
        assert len(requests) == 2
        assert requests[0] == requests[1]
        assert sleeps == [2]
        assert [frame.metadata.connection_id for frame in frames] == [
            "conn-a",
            "conn-a",
            "conn-b",
            "conn-b",
        ]
        assert [frame.metadata.ingest_seq for frame in frames] == [1, 2, 1, 2]
        assert sum(frame.kind is FrameKind.MARKET_DATA for frame in frames) == 2

    asyncio.run(scenario())


def test_binary_or_unknown_payload_is_preserved() -> None:
    async def scenario() -> None:
        payload = b"\xff\x00opaque"

        async def handler(websocket: ServerConnection) -> None:
            request_raw = await websocket.recv()
            assert isinstance(request_raw, str)
            request = json.loads(request_raw)
            await websocket.send(
                json.dumps(
                    {
                        "channel": "subscriptionResponse",
                        "data": {
                            "method": "subscribe",
                            "subscription": request["subscription"],
                        },
                    }
                )
            )
            await websocket.send(payload)

        async with serve(handler, "127.0.0.1", 0) as server:
            port = server.sockets[0].getsockname()[1]
            adapter = HyperliquidPublicAdapter(
                source_id="hl-test",
                coins=("BTC",),
                channels=("trades",),
                clock=IncrementingClock(),
                transport=_transport(),
                endpoint=f"ws://127.0.0.1:{port}",
                connection_id_factory=lambda: "conn-binary",
            )
            frames = await _collect(adapter.session_frames())

        assert frames[-1].kind is FrameKind.MALFORMED
        assert frames[-1].payload == payload

    asyncio.run(scenario())
