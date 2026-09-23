from __future__ import annotations

import asyncio
import json
import random
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import cast

from websockets.asyncio.client import ClientConnection, connect
from websockets.exceptions import ConnectionClosedOK, WebSocketException

from cryptobot.data.clock import Clock
from cryptobot.data.rawlog import RawFrameMetadata

MAINNET_WS_URL = "wss://api.hyperliquid.xyz/ws"
SUPPORTED_PUBLIC_CHANNELS = frozenset({"l2Book", "bbo", "trades", "activeAssetCtx"})
APPLICATION_PING = '{"method":"ping"}'
MIN_RECONNECT_DELAY_SECONDS = 2.0

SleepFn = Callable[[float], Awaitable[None]]
RandomFn = Callable[[], float]
ConnectionIdFactory = Callable[[], str]


class HyperliquidPublicError(ValueError):
    """Raised when public WebSocket adapter configuration is invalid."""


class FrameKind(StrEnum):
    SUBSCRIPTION_ACK = "SUBSCRIPTION_ACK"
    MARKET_DATA = "MARKET_DATA"
    HEARTBEAT_PONG = "HEARTBEAT_PONG"
    UNKNOWN = "UNKNOWN"
    MALFORMED = "MALFORMED"


@dataclass(frozen=True, slots=True, order=True)
class SubscriptionKey:
    channel: str
    coin: str

    def __post_init__(self) -> None:
        if self.channel not in SUPPORTED_PUBLIC_CHANNELS:
            raise HyperliquidPublicError(f"unsupported Hyperliquid public channel: {self.channel}")
        if not self.coin or self.coin.strip() != self.coin:
            raise HyperliquidPublicError("coin must be a non-empty trimmed string")


@dataclass(frozen=True, slots=True)
class CapturedPublicFrame:
    metadata: RawFrameMetadata
    payload: bytes
    kind: FrameKind
    channel: str | None
    acknowledged_subscription: SubscriptionKey | None
    pending_subscription_count: int


@dataclass(frozen=True, slots=True)
class ReconnectPolicy:
    base_delay_seconds: float
    max_delay_seconds: float
    jitter_fraction: float

    def __post_init__(self) -> None:
        for field, value in (
            ("base_delay_seconds", self.base_delay_seconds),
            ("max_delay_seconds", self.max_delay_seconds),
        ):
            if isinstance(value, bool) or not isinstance(value, int | float) or value <= 0:
                raise HyperliquidPublicError(f"{field} must be a positive number")
        if self.base_delay_seconds < MIN_RECONNECT_DELAY_SECONDS:
            raise HyperliquidPublicError(
                "base_delay_seconds must be at least 2 seconds to avoid exceeding "
                "the documented 30-new-connections-per-minute IP limit"
            )
        if self.base_delay_seconds > self.max_delay_seconds:
            raise HyperliquidPublicError("base_delay_seconds must not exceed max_delay_seconds")
        if (
            isinstance(self.jitter_fraction, bool)
            or not isinstance(self.jitter_fraction, int | float)
            or not 0 <= self.jitter_fraction < 1
        ):
            raise HyperliquidPublicError("jitter_fraction must be in [0, 1)")

    def delay_seconds(self, failure_count: int, random_unit: float) -> float:
        if isinstance(failure_count, bool) or not isinstance(failure_count, int):
            raise HyperliquidPublicError("failure_count must be an integer")
        if failure_count < 1:
            raise HyperliquidPublicError("failure_count must be at least 1")
        if not 0 <= random_unit <= 1:
            raise HyperliquidPublicError("random_unit must be in [0, 1]")

        exponent = min(failure_count - 1, 30)
        base = min(self.max_delay_seconds, self.base_delay_seconds * (2**exponent))
        jitter_span = base * self.jitter_fraction
        jitter = (2 * random_unit - 1) * jitter_span
        return max(MIN_RECONNECT_DELAY_SECONDS, min(self.max_delay_seconds, base + jitter))


@dataclass(frozen=True, slots=True)
class TransportSettings:
    heartbeat_idle_seconds: float
    max_message_bytes: int
    receive_queue_high_water: int
    open_timeout_seconds: float
    close_timeout_seconds: float

    def __post_init__(self) -> None:
        if (
            isinstance(self.heartbeat_idle_seconds, bool)
            or not isinstance(self.heartbeat_idle_seconds, int | float)
            or not 0 < self.heartbeat_idle_seconds < 60
        ):
            raise HyperliquidPublicError(
                "heartbeat_idle_seconds must be in (0, 60) per documented server idle rule"
            )
        for field, value in (
            ("max_message_bytes", self.max_message_bytes),
            ("receive_queue_high_water", self.receive_queue_high_water),
        ):
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise HyperliquidPublicError(f"{field} must be a positive integer")
        for field, value in (
            ("open_timeout_seconds", self.open_timeout_seconds),
            ("close_timeout_seconds", self.close_timeout_seconds),
        ):
            if isinstance(value, bool) or not isinstance(value, int | float) or value <= 0:
                raise HyperliquidPublicError(f"{field} must be a positive number")


class HyperliquidPublicAdapter:
    """Capture raw Hyperliquid public WebSocket messages with minimal envelope inspection."""

    def __init__(
        self,
        *,
        source_id: str,
        coins: tuple[str, ...],
        channels: tuple[str, ...],
        clock: Clock,
        transport: TransportSettings,
        endpoint: str = MAINNET_WS_URL,
        connection_id_factory: ConnectionIdFactory | None = None,
        sleep: SleepFn = asyncio.sleep,
        random_unit: RandomFn = random.random,
    ) -> None:
        if not source_id.strip():
            raise HyperliquidPublicError("source_id must be non-empty")
        if not endpoint.startswith(("wss://", "ws://")):
            raise HyperliquidPublicError("endpoint must use ws:// or wss://")
        if not coins:
            raise HyperliquidPublicError("coins must be non-empty")
        if len(set(coins)) != len(coins):
            raise HyperliquidPublicError("coins must not contain duplicates")
        if not channels:
            raise HyperliquidPublicError("channels must be non-empty")
        if len(set(channels)) != len(channels):
            raise HyperliquidPublicError("channels must not contain duplicates")
        unsupported = sorted(set(channels) - SUPPORTED_PUBLIC_CHANNELS)
        if unsupported:
            raise HyperliquidPublicError(
                f"unsupported Hyperliquid public channels: {', '.join(unsupported)}"
            )
        for coin in coins:
            if not coin or coin.strip() != coin:
                raise HyperliquidPublicError(
                    "coins must contain only non-empty trimmed strings"
                )

        self._source_id = source_id
        self._coins = coins
        self._channels = channels
        self._clock = clock
        self._transport = transport
        self._endpoint = endpoint
        self._connection_id_factory = connection_id_factory or _new_connection_id
        self._sleep = sleep
        self._random_unit = random_unit

    @property
    def subscriptions(self) -> tuple[SubscriptionKey, ...]:
        return tuple(
            SubscriptionKey(channel=channel, coin=coin)
            for coin in self._coins
            for channel in self._channels
        )

    async def session_frames(self) -> AsyncIterator[CapturedPublicFrame]:
        connection_id = self._connection_id_factory()
        if not connection_id.strip():
            raise HyperliquidPublicError("connection_id_factory returned an empty ID")

        pending = set(self.subscriptions)
        ingest_seq = 0

        async with connect(
            self._endpoint,
            ping_interval=None,
            ping_timeout=None,
            compression=None,
            open_timeout=self._transport.open_timeout_seconds,
            close_timeout=self._transport.close_timeout_seconds,
            max_size=self._transport.max_message_bytes,
            max_queue=self._transport.receive_queue_high_water,
        ) as websocket:
            await _send_subscriptions(websocket, self.subscriptions)

            while True:
                try:
                    message = await asyncio.wait_for(
                        websocket.recv(decode=False),
                        timeout=self._transport.heartbeat_idle_seconds,
                    )
                except TimeoutError:
                    await websocket.send(APPLICATION_PING)
                    continue
                except ConnectionClosedOK:
                    return

                sample = self._clock.sample()
                payload = _message_to_bytes(message)
                classification = classify_public_payload(payload)
                acknowledged = classification.acknowledged_subscription
                if acknowledged is not None:
                    pending.discard(acknowledged)

                ingest_seq += 1
                yield CapturedPublicFrame(
                    metadata=RawFrameMetadata(
                        schema_version=1,
                        source_id=self._source_id,
                        recv_wall_ns=sample.wall_ns,
                        recv_mono_ns=sample.mono_ns,
                        host_id=sample.host_id,
                        boot_id=sample.boot_id,
                        connection_id=connection_id,
                        ingest_seq=ingest_seq,
                        channel_hint=classification.channel,
                        capture_flags=("LIVE_CAPTURE", "WS_PUBLIC"),
                    ),
                    payload=payload,
                    kind=classification.kind,
                    channel=classification.channel,
                    acknowledged_subscription=acknowledged,
                    pending_subscription_count=len(pending),
                )

    async def frames(
        self,
        reconnect: ReconnectPolicy,
        *,
        max_sessions: int | None = None,
    ) -> AsyncIterator[CapturedPublicFrame]:
        if max_sessions is not None and (
            isinstance(max_sessions, bool)
            or not isinstance(max_sessions, int)
            or max_sessions <= 0
        ):
            raise HyperliquidPublicError("max_sessions must be null or a positive integer")

        sessions = 0
        consecutive_failures = 0
        while max_sessions is None or sessions < max_sessions:
            sessions += 1
            yielded = False
            try:
                async for frame in self.session_frames():
                    yielded = True
                    yield frame
            except (OSError, WebSocketException):
                pass

            if yielded:
                consecutive_failures = 0
            consecutive_failures += 1

            if max_sessions is not None and sessions >= max_sessions:
                return
            delay = reconnect.delay_seconds(
                consecutive_failures,
                self._random_unit(),
            )
            await self._sleep(delay)


@dataclass(frozen=True, slots=True)
class PayloadClassification:
    kind: FrameKind
    channel: str | None
    acknowledged_subscription: SubscriptionKey | None


def classify_public_payload(payload: bytes) -> PayloadClassification:
    try:
        decoded = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError):
        return PayloadClassification(
            kind=FrameKind.MALFORMED,
            channel=None,
            acknowledged_subscription=None,
        )
    if not isinstance(decoded, dict):
        return PayloadClassification(
            kind=FrameKind.MALFORMED,
            channel=None,
            acknowledged_subscription=None,
        )

    obj = cast(dict[str, object], decoded)
    channel = obj.get("channel")
    if not isinstance(channel, str):
        return PayloadClassification(
            kind=FrameKind.UNKNOWN,
            channel=None,
            acknowledged_subscription=None,
        )

    if channel == "pong":
        return PayloadClassification(
            kind=FrameKind.HEARTBEAT_PONG,
            channel=channel,
            acknowledged_subscription=None,
        )

    if channel == "subscriptionResponse":
        return PayloadClassification(
            kind=FrameKind.SUBSCRIPTION_ACK,
            channel=channel,
            acknowledged_subscription=_parse_subscription_ack(obj),
        )

    if channel in SUPPORTED_PUBLIC_CHANNELS:
        return PayloadClassification(
            kind=FrameKind.MARKET_DATA,
            channel=channel,
            acknowledged_subscription=None,
        )

    return PayloadClassification(
        kind=FrameKind.UNKNOWN,
        channel=channel,
        acknowledged_subscription=None,
    )


def subscription_request(subscription: SubscriptionKey) -> str:
    return json.dumps(
        {
            "method": "subscribe",
            "subscription": {
                "type": subscription.channel,
                "coin": subscription.coin,
            },
        },
        sort_keys=True,
        separators=(",", ":"),
    )


async def _send_subscriptions(
    websocket: ClientConnection,
    subscriptions: tuple[SubscriptionKey, ...],
) -> None:
    for subscription in subscriptions:
        await websocket.send(subscription_request(subscription))


def _parse_subscription_ack(
    message: dict[str, object],
) -> SubscriptionKey | None:
    data = message.get("data")
    if not isinstance(data, dict):
        return None
    data_obj = cast(dict[str, object], data)
    if data_obj.get("method") != "subscribe":
        return None

    subscription = data_obj.get("subscription")
    if not isinstance(subscription, dict):
        return None
    subscription_obj = cast(dict[str, object], subscription)
    channel = subscription_obj.get("type")
    coin = subscription_obj.get("coin")
    if not isinstance(channel, str) or not isinstance(coin, str):
        return None
    if channel not in SUPPORTED_PUBLIC_CHANNELS:
        return None
    try:
        return SubscriptionKey(channel=channel, coin=coin)
    except HyperliquidPublicError:
        return None


def _message_to_bytes(message: str | bytes) -> bytes:
    if isinstance(message, bytes):
        return message
    return message.encode("utf-8")


def _new_connection_id() -> str:
    return uuid.uuid4().hex
