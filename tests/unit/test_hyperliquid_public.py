from __future__ import annotations

import json

import pytest

from cryptobot.adapters.hyperliquid.public import (
    FrameKind,
    HyperliquidPublicError,
    PayloadClassification,
    ReconnectPolicy,
    SubscriptionKey,
    TransportSettings,
    classify_public_payload,
    subscription_request,
)


def test_subscription_request_is_deterministic() -> None:
    subscription = SubscriptionKey(channel="l2Book", coin="BTC")

    first = subscription_request(subscription)
    second = subscription_request(subscription)

    assert first == second
    assert json.loads(first) == {
        "method": "subscribe",
        "subscription": {"type": "l2Book", "coin": "BTC"},
    }


@pytest.mark.parametrize("channel", ["l2Book", "bbo", "trades", "activeAssetCtx"])
def test_market_channel_classification(channel: str) -> None:
    result = classify_public_payload(
        json.dumps({"channel": channel, "data": {"opaque": True}}).encode()
    )

    assert result == PayloadClassification(
        kind=FrameKind.MARKET_DATA,
        channel=channel,
        acknowledged_subscription=None,
    )


def test_subscription_ack_classification() -> None:
    payload = json.dumps(
        {
            "channel": "subscriptionResponse",
            "data": {
                "method": "subscribe",
                "subscription": {"type": "trades", "coin": "ETH"},
            },
        }
    ).encode()

    result = classify_public_payload(payload)

    assert result.kind is FrameKind.SUBSCRIPTION_ACK
    assert result.channel == "subscriptionResponse"
    assert result.acknowledged_subscription == SubscriptionKey(
        channel="trades",
        coin="ETH",
    )


def test_subscription_ack_with_unexpected_shape_is_preserved_but_not_accepted() -> None:
    payload = b'{"channel":"subscriptionResponse","data":{"method":"unsubscribe"}}'

    result = classify_public_payload(payload)

    assert result.kind is FrameKind.SUBSCRIPTION_ACK
    assert result.acknowledged_subscription is None


def test_pong_classification() -> None:
    result = classify_public_payload(b'{"channel":"pong"}')

    assert result.kind is FrameKind.HEARTBEAT_PONG
    assert result.channel == "pong"


@pytest.mark.parametrize(
    "payload",
    [
        b"not-json",
        b"[]",
        b'"string"',
    ],
)
def test_malformed_payload_classification(payload: bytes) -> None:
    result = classify_public_payload(payload)

    assert result.kind is FrameKind.MALFORMED
    assert result.channel is None


def test_unknown_channel_is_not_misclassified_as_market_data() -> None:
    result = classify_public_payload(b'{"channel":"futureChannel","data":{}}')

    assert result.kind is FrameKind.UNKNOWN
    assert result.channel == "futureChannel"


def test_message_without_channel_is_unknown() -> None:
    result = classify_public_payload(b'{"data":{}}')

    assert result.kind is FrameKind.UNKNOWN
    assert result.channel is None


def test_subscription_key_rejects_unsupported_channel() -> None:
    with pytest.raises(HyperliquidPublicError, match="unsupported"):
        SubscriptionKey(channel="allMids", coin="BTC")


def test_transport_settings_keep_application_heartbeat_inside_documented_window() -> None:
    settings = TransportSettings(
        heartbeat_idle_seconds=50,
        max_message_bytes=1_048_576,
        receive_queue_high_water=16,
        open_timeout_seconds=10,
        close_timeout_seconds=5,
    )

    assert settings.heartbeat_idle_seconds == 50


@pytest.mark.parametrize("heartbeat", [0, 60, 61])
def test_transport_settings_reject_invalid_heartbeat_window(heartbeat: float) -> None:
    with pytest.raises(HyperliquidPublicError, match="heartbeat_idle_seconds"):
        TransportSettings(
            heartbeat_idle_seconds=heartbeat,
            max_message_bytes=1_048_576,
            receive_queue_high_water=16,
            open_timeout_seconds=10,
            close_timeout_seconds=5,
        )


def test_reconnect_policy_enforces_documented_connection_rate_floor() -> None:
    with pytest.raises(HyperliquidPublicError, match="at least 2 seconds"):
        ReconnectPolicy(
            base_delay_seconds=1.99,
            max_delay_seconds=30,
            jitter_fraction=0,
        )


def test_reconnect_backoff_is_bounded_and_jittered() -> None:
    policy = ReconnectPolicy(
        base_delay_seconds=2,
        max_delay_seconds=10,
        jitter_fraction=0.25,
    )

    assert policy.delay_seconds(1, 0.5) == 2
    assert policy.delay_seconds(2, 0.5) == 4
    assert policy.delay_seconds(3, 0.5) == 8
    assert policy.delay_seconds(4, 0.5) == 10
    assert policy.delay_seconds(20, 1.0) == 10
    assert policy.delay_seconds(1, 0.0) == 2
