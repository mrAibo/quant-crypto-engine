from __future__ import annotations

import argparse
import json
from collections.abc import Sequence

from cryptobot.adapters.hyperliquid.public import (
    ReconnectPolicy,
    TransportSettings,
)
from cryptobot.data.recorder import (
    RecorderRuntimeSettings,
    RolloverMode,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="cryptobot")
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate = subparsers.add_parser(
        "validate-recorder-runtime",
        help="Validate explicit public-recorder runtime values without network access.",
    )
    validate.add_argument("--queue-capacity", type=int, required=True)
    validate.add_argument("--sync-every-frames", type=int, required=True)
    validate.add_argument("--shutdown-drain-timeout-seconds", type=float, required=True)
    validate.add_argument("--seal-on-shutdown", action="store_true")

    validate.add_argument("--reconnect-base-seconds", type=float, required=True)
    validate.add_argument("--reconnect-max-seconds", type=float, required=True)
    validate.add_argument("--reconnect-jitter-fraction", type=float, required=True)

    validate.add_argument("--heartbeat-idle-seconds", type=float, required=True)
    validate.add_argument("--max-message-bytes", type=int, required=True)
    validate.add_argument("--receive-queue-high-water", type=int, required=True)
    validate.add_argument("--open-timeout-seconds", type=float, required=True)
    validate.add_argument("--close-timeout-seconds", type=float, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command != "validate-recorder-runtime":
        raise RuntimeError("unreachable command")

    recorder = RecorderRuntimeSettings(
        queue_capacity=args.queue_capacity,
        sync_every_frames=args.sync_every_frames,
        shutdown_drain_timeout_seconds=args.shutdown_drain_timeout_seconds,
        seal_on_shutdown=args.seal_on_shutdown,
        rollover_mode=RolloverMode.DISABLED,
    )
    reconnect = ReconnectPolicy(
        base_delay_seconds=args.reconnect_base_seconds,
        max_delay_seconds=args.reconnect_max_seconds,
        jitter_fraction=args.reconnect_jitter_fraction,
    )
    transport = TransportSettings(
        heartbeat_idle_seconds=args.heartbeat_idle_seconds,
        max_message_bytes=args.max_message_bytes,
        receive_queue_high_water=args.receive_queue_high_water,
        open_timeout_seconds=args.open_timeout_seconds,
        close_timeout_seconds=args.close_timeout_seconds,
    )

    print(
        json.dumps(
            {
                "recorder": {
                    "queue_capacity": recorder.queue_capacity,
                    "sync_every_frames": recorder.sync_every_frames,
                    "shutdown_drain_timeout_seconds": recorder.shutdown_drain_timeout_seconds,
                    "seal_on_shutdown": recorder.seal_on_shutdown,
                    "rollover_mode": recorder.rollover_mode.value,
                },
                "reconnect": {
                    "base_delay_seconds": reconnect.base_delay_seconds,
                    "max_delay_seconds": reconnect.max_delay_seconds,
                    "jitter_fraction": reconnect.jitter_fraction,
                },
                "transport": {
                    "heartbeat_idle_seconds": transport.heartbeat_idle_seconds,
                    "max_message_bytes": transport.max_message_bytes,
                    "receive_queue_high_water": transport.receive_queue_high_water,
                    "open_timeout_seconds": transport.open_timeout_seconds,
                    "close_timeout_seconds": transport.close_timeout_seconds,
                },
            },
            sort_keys=True,
            separators=(",", ":"),
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
