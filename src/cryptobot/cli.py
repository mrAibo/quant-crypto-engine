from __future__ import annotations

import argparse
import asyncio
import json
from collections.abc import Sequence
from datetime import date
from decimal import Decimal

from cryptobot.adapters.hyperliquid.public import (
    ReconnectPolicy,
    TransportSettings,
)
from cryptobot.data.recorder import (
    RecorderRuntimeSettings,
    RolloverMode,
)
from cryptobot.research.campaign import CampaignConfig, CampaignValidationError
from cryptobot.research.campaign_storage import (
    initialize_campaign_root,
    load_campaign_config,
    publish_campaign_report,
)
from cryptobot.research.retrospective import (
    GATE_ELIGIBILITY,
    RetrospectiveDataError,
    binance_usdm_daily_aggtrades_spec,
    download_binance_archive,
    write_binance_retrospective_50s_report,
    write_retrospective_plan,
)
from cryptobot.runtime.dual_source_recorder import load_dual_source_recorder_config
from cryptobot.runtime.frontier_segment import (
    FrontierSegmentError,
    capture_frontier_evidence_segment_sync,
    process_next_frontier_captured_segment,
    run_frontier_evidence_segment_sync,
)
from cryptobot.runtime.public_recorder import (
    audit_public_recorder,
    load_public_recorder_config,
    run_public_recorder,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="cryptobot")
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate = subparsers.add_parser(
        "validate-recorder-runtime",
        help="Validate explicit recorder primitive values without network access.",
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

    public_run = subparsers.add_parser(
        "run-public-recorder",
        help="Run the public-only Hyperliquid recorder from a strict JSON config.",
    )
    public_run.add_argument("--config", required=True)

    public_audit = subparsers.add_parser(
        "audit-public-recorder",
        help="Audit raw storage configured for the public recorder without network access.",
    )
    public_audit.add_argument("--config", required=True)

    retrospective_plan = subparsers.add_parser(
        "plan-retrospective-data",
        help="Write a non-gating plan for official Hyperliquid/Binance historical archives.",
    )
    retrospective_plan.add_argument("--start-date", required=True)
    retrospective_plan.add_argument("--end-date", required=True)
    retrospective_plan.add_argument("--output", required=True)

    retrospective_download = subparsers.add_parser(
        "download-binance-retrospective",
        help="Download one checksum-verified Binance USD-M aggTrades archive.",
    )
    retrospective_download.add_argument("--date", required=True)
    retrospective_download.add_argument(
        "--symbol",
        choices=("BTCUSDT", "ETHUSDT"),
        required=True,
    )
    retrospective_download.add_argument("--destination", required=True)

    retrospective_analyze = subparsers.add_parser(
        "analyze-binance-retrospective-50s",
        help="Analyze checksum-verified Binance aggTrades as non-gating 50-second context.",
    )
    retrospective_analyze.add_argument("--source-root", required=True)
    retrospective_analyze.add_argument("--start-date", required=True)
    retrospective_analyze.add_argument("--end-date", required=True)
    retrospective_analyze.add_argument("--output", required=True)

    frontier_init = subparsers.add_parser(
        "init-frontier-campaign",
        help="Create the immutable Stage-0.5 campaign config before any segment capture.",
    )
    frontier_init.add_argument("--campaign-root", required=True)
    frontier_init.add_argument("--campaign-id", required=True)
    frontier_init.add_argument(
        "--fee-scenario-bps-per-side",
        type=Decimal,
        required=True,
    )

    frontier_capture = subparsers.add_parser(
        "capture-frontier-segment",
        help="Capture and seal one public-only Stage-0.5 raw evidence segment.",
    )
    frontier_capture.add_argument("--config", required=True)
    frontier_capture.add_argument("--campaign-root", required=True)
    frontier_capture.add_argument("--duration-seconds", type=float, required=True)

    frontier_process = subparsers.add_parser(
        "process-next-frontier-segment",
        help="Process and publish the oldest capture-ready Stage-0.5 segment.",
    )
    frontier_process.add_argument("--campaign-root", required=True)
    frontier_process.add_argument(
        "--registry",
        default="config/instruments.yaml",
    )

    frontier_segment = subparsers.add_parser(
        "run-frontier-segment",
        help="Capture and publish one bounded public-only Stage-0.5 evidence segment.",
    )
    frontier_segment.add_argument("--config", required=True)
    frontier_segment.add_argument("--campaign-root", required=True)
    frontier_segment.add_argument("--duration-seconds", type=float, required=True)
    frontier_segment.add_argument(
        "--registry",
        default="config/instruments.yaml",
    )

    frontier_report = subparsers.add_parser(
        "report-frontier-campaign",
        help=(
            "Validate all published segments and publish a deterministic campaign report revision."
        ),
    )
    frontier_report.add_argument("--campaign-root", required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.command == "run-public-recorder":
        public_config = load_public_recorder_config(args.config)
        summary = asyncio.run(run_public_recorder(public_config))
        print(summary.to_json())
        return summary.exit_code

    if args.command == "audit-public-recorder":
        public_config = load_public_recorder_config(args.config)
        report = audit_public_recorder(public_config)
        print(json.dumps(report, sort_keys=True, separators=(",", ":")))
        return 0 if bool(report["clean"]) else 3

    if args.command == "plan-retrospective-data":
        try:
            output = write_retrospective_plan(
                args.output,
                date.fromisoformat(args.start_date),
                date.fromisoformat(args.end_date),
            )
        except (RetrospectiveDataError, OSError, ValueError) as exc:
            print(
                json.dumps(
                    {"status": "FAILED", "error": str(exc)},
                    sort_keys=True,
                    separators=(",", ":"),
                )
            )
            return 2
        print(
            json.dumps(
                {
                    "status": "SUCCESS",
                    "plan_path": str(output),
                    "task_018_gate_eligibility": GATE_ELIGIBILITY,
                },
                sort_keys=True,
                separators=(",", ":"),
            )
        )
        return 0

    if args.command == "download-binance-retrospective":
        try:
            spec = binance_usdm_daily_aggtrades_spec(
                date.fromisoformat(args.date),
                args.symbol,
            )
            downloaded = download_binance_archive(spec, args.destination)
        except (RetrospectiveDataError, OSError, ValueError) as exc:
            print(
                json.dumps(
                    {"status": "FAILED", "error": str(exc)},
                    sort_keys=True,
                    separators=(",", ":"),
                )
            )
            return 2
        print(
            json.dumps(
                {
                    "status": "SUCCESS",
                    "archive_path": str(downloaded.archive_path),
                    "manifest_path": str(downloaded.manifest_path),
                    "sha256": downloaded.sha256,
                    "task_018_gate_eligibility": GATE_ELIGIBILITY,
                },
                sort_keys=True,
                separators=(",", ":"),
            )
        )
        return 0

    if args.command == "analyze-binance-retrospective-50s":
        try:
            output = write_binance_retrospective_50s_report(
                args.output,
                args.source_root,
                date.fromisoformat(args.start_date),
                date.fromisoformat(args.end_date),
            )
        except (RetrospectiveDataError, OSError, ValueError) as exc:
            print(
                json.dumps(
                    {"status": "FAILED", "error": str(exc)},
                    sort_keys=True,
                    separators=(",", ":"),
                )
            )
            return 2
        print(
            json.dumps(
                {
                    "status": "SUCCESS",
                    "report_path": str(output),
                    "task_018_gate_eligibility": GATE_ELIGIBILITY,
                },
                sort_keys=True,
                separators=(",", ":"),
            )
        )
        return 0

    if args.command == "init-frontier-campaign":
        try:
            path = initialize_campaign_root(
                args.campaign_root,
                CampaignConfig(
                    campaign_id=args.campaign_id,
                    fee_scenario_bps_per_side=args.fee_scenario_bps_per_side,
                ),
            )
        except (CampaignValidationError, OSError, ValueError) as exc:
            print(
                json.dumps(
                    {"status": "FAILED", "error": str(exc)},
                    sort_keys=True,
                    separators=(",", ":"),
                )
            )
            return 2
        print(
            json.dumps(
                {"status": "SUCCESS", "campaign_config": str(path)},
                sort_keys=True,
                separators=(",", ":"),
            )
        )
        return 0

    if args.command == "capture-frontier-segment":
        dual_source_config = load_dual_source_recorder_config(args.config)
        try:
            load_campaign_config(args.campaign_root)
            capture_result = capture_frontier_evidence_segment_sync(
                dual_source_config,
                campaign_root=args.campaign_root,
                run_duration_seconds=args.duration_seconds,
            )
        except (CampaignValidationError, FrontierSegmentError, OSError, ValueError) as exc:
            print(
                json.dumps(
                    {"status": "FAILED", "error": str(exc)},
                    sort_keys=True,
                    separators=(",", ":"),
                )
            )
            return 2
        print(capture_result.to_json())
        return 0

    if args.command == "process-next-frontier-segment":
        try:
            campaign_config = load_campaign_config(args.campaign_root)
            process_result = process_next_frontier_captured_segment(
                args.campaign_root,
                fee_scenario_bps_per_side=campaign_config.fee_scenario_bps_per_side,
                registry_path=args.registry,
            )
        except (CampaignValidationError, FrontierSegmentError, OSError, ValueError) as exc:
            print(
                json.dumps(
                    {"status": "FAILED", "error": str(exc)},
                    sort_keys=True,
                    separators=(",", ":"),
                )
            )
            return 2
        if process_result is None:
            print(
                json.dumps(
                    {"status": "IDLE", "pending_segment": None},
                    sort_keys=True,
                    separators=(",", ":"),
                )
            )
            return 0
        print(process_result.to_json())
        return 0

    if args.command == "run-frontier-segment":
        dual_source_config = load_dual_source_recorder_config(args.config)
        try:
            campaign_config = load_campaign_config(args.campaign_root)
            segment_result = run_frontier_evidence_segment_sync(
                dual_source_config,
                campaign_root=args.campaign_root,
                run_duration_seconds=args.duration_seconds,
                fee_scenario_bps_per_side=campaign_config.fee_scenario_bps_per_side,
                registry_path=args.registry,
            )
        except (CampaignValidationError, FrontierSegmentError, OSError, ValueError) as exc:
            print(
                json.dumps(
                    {"status": "FAILED", "error": str(exc)},
                    sort_keys=True,
                    separators=(",", ":"),
                )
            )
            return 2
        print(segment_result.to_json())
        return 0

    if args.command == "report-frontier-campaign":
        try:
            published = publish_campaign_report(args.campaign_root)
        except (CampaignValidationError, OSError, ValueError) as exc:
            print(
                json.dumps(
                    {"status": "FAILED", "error": str(exc)},
                    sort_keys=True,
                    separators=(",", ":"),
                )
            )
            return 2
        print(
            json.dumps(
                {
                    "status": "SUCCESS",
                    "report_path": str(published.report_path),
                    "manifest_sha256": published.discovery.manifest.sha256,
                    "published_segment_count": len(published.discovery.segments),
                    "incomplete_segment_directories": list(
                        published.discovery.incomplete_segment_directories
                    ),
                    "report": published.report.as_dict(),
                },
                sort_keys=True,
                separators=(",", ":"),
            )
        )
        return 0

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
