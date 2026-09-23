from __future__ import annotations

import asyncio
import json
import random
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import cast

from websockets.asyncio.client import connect
from websockets.exceptions import ConnectionClosedOK, WebSocketException

from cryptobot.data.clock import Clock
from cryptobot.data.rawlog import RawFrameMetadata


PUBLIC_ENDPOINT = "wss://fstream.binance.com/public/stream"
MARKET_ENDPOINT = "wss://fstream.binance.com/market/stream"
SOURCE_ID = "binance-usdm-reference-public"
REFERENCE_SYMBOLS = ("BTCUSDT", "ETHUSDT")
PUBLIC_STREAMS = ("btcusdt@bookTicker", "ethusdt@bookTicker")
MARKET_STREAMS = ("btcusdt@aggTrade", "ethusdt@aggTrade")

SleepFn = Callable[[float], Awaitable[None]]
RandomFn = Callable[[], float]
ConnectionIdFactory = Callable[[str], str]


class BinanceReferenceError(ValueError):
    """Raised when the Binance reference adapter contract is invalid."""


class BinanceRoute(StrEnum):
    PUBLIC = "PUBLIC"
    MARKET = "MARKET"


class BinanceFrameKind(StrEnum):
    SUBSCRIPTION_ACK = "SUBSCRIPTION_ACK"
    MARKET_DATA = "MARKET_DATA"
    UNKNOWN = "UNKNOWN"
    MALFORMED = "MALFORMED"


@dataclass(frozen=True, slots=True)
class BinanceCapturedFrame:
    metadata: RawFrameMetadata
    payload: bytes
    kind: BinanceFrameKind
    route: BinanceRoute
    stream: str | None
    event_type: str | None
    subscription_ack_id: str | int | None


@dataclass(frozen=True, slots=True)
class BinanceReconnectPolicy:
    base_delay_seconds: float
    max_delay_seconds: float
    jitter_fraction: float

    def __post_init__(self) -> None:
        for field, value in (
            ("base_delay_seconds", self.base_delay_seconds),
            ("max_delay_seconds", self.max_delay_seconds),
        ):
            if isinstance(value, bool) or not isinstance(value, int | float) or value <= 0:
                raise BinanceReferenceError(f"{field} must be a positive number")
        if self.base_delay_seconds > self.max_delay_seconds:
            raise BinanceReferenceError("base_delay_seconds must not exceed max_delay_seconds")
        if (
            isinstance(self.jitter_fraction, bool)
            or not isinstance(self.jitter_fraction, int | float)
            or not 0 <= self.jitter_fraction < 1
        ):
            raise BinanceReferenceError("jitter_fraction must be in [0, 1)")

    def delay_seconds(self, failure_count: int, random_unit: float) -> float:
        if isinstance(failure_count, bool) or not isinstance(failure_count, int):
            raise BinanceReferenceError("failure_count must be an integer")
        if failure_count < 1:
            raise BinanceReferenceError("failure_count must be at least 1")
        if not 0 <= random_unit <= 1:
            raise BinanceReferenceError("random_unit must be in [0, 1]")
        exponent = min(failure_count - 1, 30)
        base = min(self.max_delay_seconds, self.base_delay_seconds * (2**exponent))
        jitter_span = base * self.jitter_fraction
        jitter = (2 * random_unit - 1) * jitter_span
        return float(max(0.1, min(self.max_delay_seconds, base + jitter)))


@dataclass(frozen=True, slots=True)
class BinanceTransportSettings:
    max_message_bytes: int
    receive_queue_high_water: int
    open_timeout_seconds: float
    close_timeout_seconds: float

    def __post_init__(self) -> None:
        for field, value in (
            ("max_message_bytes", self.max_message_bytes),
            ("receive_queue_high_water", self.receive_queue_high_water),
        ):
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise BinanceReferenceError(f"{field} must be a positive integer")
        for field, value in (
            ("open_timeout_seconds", self.open_timeout_seconds),
            ("close_timeout_seconds", self.close_timeout_seconds),
        ):
            if isinstance(value, bool) or not isinstance(value, int | float) or value <= 0:
                raise BinanceReferenceError(f"{field} must be a positive number")


@dataclass(frozen=True, slots=True)
class BinancePayloadClassification:
    kind: BinanceFrameKind
    stream: str | None
    event_type: str | None
    subscription_ack_id: str | int | None


@dataclass(frozen=True, slots=True)
class _RouteFailure:
    route: BinanceRoute
    error: BaseException | None


class BinanceReferenceAdapter:
    """Capture Binance USD-M BBO and aggregate-trade reference streams only."""

    def __init__(
        self,
        *,
        clock: Clock,
        transport: BinanceTransportSettings,
        source_id: str = SOURCE_ID,
        public_endpoint: str = PUBLIC_ENDPOINT,
        market_endpoint: str = MARKET_ENDPOINT,
        connection_id_factory: ConnectionIdFactory | None = None,
        sleep: SleepFn = asyncio.sleep,
        random_unit: RandomFn = random.random,
    ) -> None:
        if not source_id.strip():
            raise BinanceReferenceError("source_id must be non-empty")
        for label, endpoint in (
            ("public_endpoint", public_endpoint),
            ("market_endpoint", market_endpoint),
        ):
            if not endpoint.startswith(("ws://", "wss://")):
                raise BinanceReferenceError(f"{label} must use ws:// or wss://")
        self._clock = clock
        self._transport = transport
        self._source_id = source_id
        self._public_endpoint = public_endpoint
        self._market_endpoint = market_endpoint
        self._connection_id_factory = connection_id_factory or _new_connection_id
        self._sleep = sleep
        self._random_unit = random_unit

    async def session_frames(self) -> AsyncIterator[BinanceCapturedFrame]:
        queue: asyncio.Queue[BinanceCapturedFrame | _RouteFailure] = asyncio.Queue(maxsize=4096)
        tasks = [
            asyncio.create_task(
                self._pump_route(
                    route=BinanceRoute.PUBLIC,
                    endpoint=self._public_endpoint,
                    streams=PUBLIC_STREAMS,
                    subscription_id="task013-public",
                    output=queue,
                )
            ),
            asyncio.create_task(
                self._pump_route(
                    route=BinanceRoute.MARKET,
                    endpoint=self._market_endpoint,
                    streams=MARKET_STREAMS,
                    subscription_id="task013-market",
                    output=queue,
                )
            ),
        ]
        active = len(tasks)
        try:
            while active:
                item = await queue.get()
                if isinstance(item, _RouteFailure):
                    active -= 1
                    if item.error is not None:
                        raise item.error
                    if active:
                        raise ConnectionError(
                            f"Binance {item.route.value} route ended while peer route remained active"
                        )
                    continue
                yield item
        finally:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)

    async def frames(
        self,
        reconnect: BinanceReconnectPolicy,
        *,
        max_sessions: int | None = None,
    ) -> AsyncIterator[BinanceCapturedFrame]:
        if max_sessions is not None and (
            isinstance(max_sessions, bool) or not isinstance(max_sessions, int) or max_sessions <= 0
        ):
            raise BinanceReferenceError("max_sessions must be null or a positive integer")
        sessions = 0
        failures = 0
        while max_sessions is None or sessions < max_sessions:
            sessions += 1
            yielded = False
            try:
                async for frame in self.session_frames():
                    yielded = True
                    yield frame
            except (OSError, ConnectionError, WebSocketException):
                pass
            if yielded:
                failures = 0
            failures += 1
            if max_sessions is not None and sessions >= max_sessions:
                return
            await self._sleep(reconnect.delay_seconds(failures, self._random_unit()))

    async def _pump_route(
        self,
        *,
        route: BinanceRoute,
        endpoint: str,
        streams: tuple[str, ...],
        subscription_id: str,
        output: asyncio.Queue[BinanceCapturedFrame | _RouteFailure],
    ) -> None:
        connection_id = self._connection_id_factory(route.value.lower())
        if not connection_id.strip():
            raise BinanceReferenceError("connection_id_factory returned an empty ID")
        ingest_seq = 0
        error: BaseException | None = None
        try:
            async with connect(
                endpoint,
                ping_interval=None,
                ping_timeout=None,
                compression=None,
                open_timeout=self._transport.open_timeout_seconds,
                close_timeout=self._transport.close_timeout_seconds,
                max_size=self._transport.max_message_bytes,
                max_queue=self._transport.receive_queue_high_water,
            ) as websocket:
                await websocket.send(subscription_request(streams, subscription_id))
                while True:
                    try:
                        message = await websocket.recv(decode=False)
                    except ConnectionClosedOK:
                        break
                    sample = self._clock.sample()
                    payload = _message_to_bytes(message)
                    classification = classify_binance_payload(payload)
                    ingest_seq += 1
                    await output.put(
                        BinanceCapturedFrame(
                            metadata=RawFrameMetadata(
                                schema_version=1,
                                source_id=self._source_id,
                                recv_wall_ns=sample.wall_ns,
                                recv_mono_ns=sample.mono_ns,
                                host_id=sample.host_id,
                                boot_id=sample.boot_id,
                                connection_id=connection_id,
                                ingest_seq=ingest_seq,
                                channel_hint=classification.stream or classification.event_type,
                                capture_flags=("LIVE_CAPTURE", "WS_PUBLIC", f"BINANCE_{route.value}"),
                            ),
                            payload=payload,
                            kind=classification.kind,
                            route=route,
                            stream=classification.stream,
                            event_type=classification.event_type,
                            subscription_ack_id=classification.subscription_ack_id,
                        )
                    )
        except BaseException as exc:
            if isinstance(exc, asyncio.CancelledError):
                raise
            error = exc
        finally:
            await output.put(_RouteFailure(route=route, error=error))


def subscription_request(streams: tuple[str, ...], request_id: str) -> str:
    if not streams:
        raise BinanceReferenceError("streams must be non-empty")
    if not request_id.strip():
        raise BinanceReferenceError("request_id must be non-empty")
    return json.dumps(
        {"method": "SUBSCRIBE", "params": list(streams), "id": request_id},
        separators=(",", ":"),
        sort_keys=True,
    )


def classify_binance_payload(payload: bytes) -> BinancePayloadClassification:
    try:
        decoded = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError):
        return BinancePayloadClassification(
            BinanceFrameKind.MALFORMED, None, None, None
        )
    if not isinstance(decoded, dict) or not all(isinstance(k, str) for k in decoded):
        return BinancePayloadClassification(
            BinanceFrameKind.MALFORMED, None, None, None
        )
    obj = cast(dict[str, object], decoded)

    if "result" in obj and "id" in obj:
        ack_id = obj.get("id")
        if isinstance(ack_id, bool) or not isinstance(ack_id, str | int):
            return BinancePayloadClassification(
                BinanceFrameKind.UNKNOWN, None, None, None
            )
        return BinancePayloadClassification(
            BinanceFrameKind.SUBSCRIPTION_ACK, None, None, ack_id
        )

    stream = obj.get("stream")
    data = obj.get("data")
    if not isinstance(stream, str) or not isinstance(data, dict):
        return BinancePayloadClassification(
            BinanceFrameKind.UNKNOWN, None, None, None
        )
    data_obj = cast(dict[str, object], data)
    event_type = data_obj.get("e")
    if not isinstance(event_type, str):
        return BinancePayloadClassification(
            BinanceFrameKind.UNKNOWN, stream, None, None
        )
    if event_type not in {"bookTicker", "aggTrade"}:
        return BinancePayloadClassification(
            BinanceFrameKind.UNKNOWN, stream, event_type, None
        )
    return BinancePayloadClassification(
        BinanceFrameKind.MARKET_DATA, stream, event_type, None
    )


def _message_to_bytes(message: str | bytes) -> bytes:
    return message if isinstance(message, bytes) else message.encode()


def _new_connection_id(route: str) -> str:
    return f"{route}-{uuid.uuid4().hex}"
