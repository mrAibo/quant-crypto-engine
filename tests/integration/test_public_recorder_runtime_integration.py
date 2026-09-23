from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from dataclasses import replace
from pathlib import Path, PurePosixPath
from typing import cast

from websockets.asyncio.server import ServerConnection, serve

from cryptobot.data.recorder import CaptureFrame
from cryptobot.runtime.public_recorder import (
    PublicRecorderConfig,
    RuntimeExitCode,
    RuntimeIdentity,
    SignalState,
    load_public_recorder_config,
    run_public_recorder,
)


def _base_config() -> PublicRecorderConfig:
    return load_public_recorder_config("config/runtime/public-recorder-smoke.json")


def test_fake_server_runtime_captures_seals_audits_and_summarizes(tmp_path: Path) -> None:
    async def scenario() -> None:
        requests: list[dict[str, object]] = []

        async def handler(websocket: ServerConnection) -> None:
            for _ in range(8):
                raw = await websocket.recv()
                assert isinstance(raw, str)
                request = json.loads(raw)
                assert isinstance(request, dict)
                requests.append(request)
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

            await websocket.send('{"channel":"bbo","data":{"coin":"BTC"}}')
            await websocket.send('{"channel":"trades","data":[{"coin":"BTC","px":"1"}]}')
            await websocket.send('{"channel":"l2Book","data":{"coin":"ETH"}}')
            await websocket.send('{"channel":"activeAssetCtx","data":{"coin":"ETH"}}')
            await websocket.wait_closed()

        async with serve(handler, "127.0.0.1", 0) as server:
            port = server.sockets[0].getsockname()[1]
            root = tmp_path / "capture"
            config = replace(
                _base_config(),
                endpoint=f"ws://127.0.0.1:{port}",
                storage_root=PurePosixPath(root.as_posix()),
                manifest_path=PurePosixPath((root / "manifest.json").as_posix()),
                run_duration_seconds=0.05,
            )
            summary = await run_public_recorder(
                config,
                identity=RuntimeIdentity(
                    host_id="host-test",
                    boot_id="boot-test",
                    run_id="run-test",
                ),
                install_signal_handlers=False,
            )

        assert len(requests) == 8
        assert summary.exit_code == int(RuntimeExitCode.SUCCESS)
        assert summary.status == "SUCCESS"
        assert summary.audit_clean
        assert summary.recorder.counters.durable_frames == summary.observed_frames
        assert summary.observed_frames >= 12
        assert summary.subscription_ack_count == 8
        assert summary.expected_subscription_ack_count == 8
        assert summary.all_subscription_acks_observed
        assert summary.reconnect_count == 0
        counts = dict(summary.channel_counts)
        assert counts["subscriptionResponse"] == 8
        assert counts["bbo"] >= 1
        assert counts["trades"] >= 1
        assert counts["l2Book"] >= 1
        assert counts["activeAssetCtx"] >= 1
        assert Path(summary.recorder.final_path or "").exists()
        assert json.loads(summary.to_json())["audit"]["clean"] is True

    asyncio.run(scenario())


def test_signal_state_requests_graceful_stop_of_running_runtime(tmp_path: Path) -> None:
    async def scenario() -> None:
        from cryptobot.data.clock import SystemClock
        from cryptobot.data.recorder import RecorderSupervisor

        async def source() -> AsyncIterator[CaptureFrame]:
            while True:
                await asyncio.sleep(3600)
                if False:
                    yield cast(CaptureFrame, object())  # pragma: no cover

        base = _base_config()
        root = tmp_path / "signal"
        supervisor = RecorderSupervisor(
            source=source(),
            storage_root=root,
            manifest_path=root / "manifest.json",
            run_id="signal-run",
            settings=base.recorder_settings(),
            clock=SystemClock(host_id="host-test", boot_id="boot-test"),
        )
        task = asyncio.create_task(supervisor.run())
        await asyncio.sleep(0)
        state = SignalState()

        state.handle(supervisor)
        status = await task

        assert state.count == 1
        assert status.state.value == "COMPLETE"
        assert status.shutdown_outcome.value == "CLEAN_UNSEALED"

    asyncio.run(scenario())
