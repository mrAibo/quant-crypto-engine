from __future__ import annotations

import json
from collections.abc import Callable
from decimal import Decimal
from pathlib import Path
from typing import cast

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from cryptobot.data.events import QualityFlag
from cryptobot.research.frontier import FrontierValidationError
from cryptobot.research.frontier_dataset import analyze_frontier_pilot_dataset

type _WriteTableFn = Callable[..., None]

_WRITE_TABLE = cast(_WriteTableFn, pq.write_table)


def _write_dataset(
    root: Path,
    *,
    points: list[tuple[int, str, str, str, str, int]],
    bundle_sha: str = "a" * 64,
    normalized_sha: str = "b" * 64,
) -> None:
    root.mkdir()
    (root / "manifest.json").write_text(
        json.dumps(
            {
                "bundle_sha256": bundle_sha,
                "source_normalized_records_sha256": normalized_sha,
            }
        ),
        encoding="utf-8",
    )

    events: list[dict[str, object]] = []
    bbo: list[dict[str, object]] = []
    for index, (mono_ns, bid, ask, host, boot, quality_flags) in enumerate(points):
        event_id = f"event-{index}"
        events.append(
            {
                "event_id": event_id,
                "source_id": "hyperliquid-mainnet-public",
                "instrument_id": "hyperliquid.mainnet.perpetual.btc",
                "event_type": "BBO",
                "host_id": host,
                "boot_id": boot,
                "recv_mono_ns": mono_ns,
                "recv_wall_ns": 1_790_000_000_000_000_000 + mono_ns,
                "quality_flags": quality_flags,
            }
        )
        bbo.append(
            {
                "event_id": event_id,
                "bid_price_exact": bid,
                "ask_price_exact": ask,
            }
        )

    event_schema = pa.schema(
        [
            pa.field("event_id", pa.string(), nullable=False),
            pa.field("source_id", pa.string(), nullable=False),
            pa.field("instrument_id", pa.string(), nullable=False),
            pa.field("event_type", pa.string(), nullable=False),
            pa.field("host_id", pa.string(), nullable=False),
            pa.field("boot_id", pa.string(), nullable=False),
            pa.field("recv_mono_ns", pa.int64(), nullable=False),
            pa.field("recv_wall_ns", pa.int64(), nullable=False),
            pa.field("quality_flags", pa.int64(), nullable=False),
        ]
    )
    bbo_schema = pa.schema(
        [
            pa.field("event_id", pa.string(), nullable=False),
            pa.field("bid_price_exact", pa.string(), nullable=True),
            pa.field("ask_price_exact", pa.string(), nullable=True),
        ]
    )
    _WRITE_TABLE(pa.Table.from_pylist(events, schema=event_schema), root / "events.parquet")
    _WRITE_TABLE(pa.Table.from_pylist(bbo, schema=bbo_schema), root / "bbo.parquet")


def _regular_points(count: int) -> list[tuple[int, str, str, str, str, int]]:
    result: list[tuple[int, str, str, str, str, int]] = []
    for index in range(count):
        mid = Decimal("100") + Decimal(index) / Decimal("10")
        bid = mid - Decimal("0.05")
        ask = mid + Decimal("0.05")
        result.append(
            (
                index * 1_000_000_000,
                format(bid, "f"),
                format(ask, "f"),
                "host-a",
                "boot-a",
                0,
            )
        )
    return result


def test_frontier_pilot_reads_real_parquet_and_derives_horizon_bounds(
    tmp_path: Path,
) -> None:
    dataset = tmp_path / "dataset"
    _write_dataset(dataset, points=_regular_points(21))

    report = analyze_frontier_pilot_dataset(
        dataset,
        fee_scenario_bps_per_side=Decimal("4.5"),
    )

    assert report.status == "PILOT_MEASURED"
    assert report.gate_decision == "NOT_EVALUATED"
    assert report.source_dataset_bundle_sha256 == "a" * 64
    assert report.source_normalized_records_sha256 == "b" * 64
    assert report.causal_domain == ("host-a", "boot-a")
    assert report.observation_count == 21
    assert report.observed_duration_ns == 20_000_000_000
    assert report.cadence_p99_ns == 1_000_000_000
    assert report.largest_gap_ns == 1_000_000_000
    assert report.horizon_lower_bound_seconds == 1
    assert report.horizon_upper_bound_seconds == 10
    assert report.dataset_audit.causal_domain_count == 1
    assert dict(report.dataset_audit.primary_btc_event_counts)["BBO"] == 21
    assert dict(report.dataset_audit.primary_btc_event_counts)["L2_SNAPSHOT"] == 0
    assert report.dataset_audit.primary_bbo_cadence.observed_count == 21
    assert report.dataset_audit.primary_bbo_cadence.q99_ns == 1_000_000_000
    assert [item.horizon_seconds for item in report.horizons] == [1, 2, 5, 10]
    assert all(item.movement_sample_count > 0 for item in report.horizons)
    assert all(item.median_known_friction_bps > 0 for item in report.horizons)
    assert report.to_json_bytes() == report.to_json_bytes()


def test_frontier_pilot_excludes_suspect_bbo_rows(tmp_path: Path) -> None:
    points = _regular_points(4)
    mono, bid, ask, host, boot, _ = points[1]
    points[1] = (
        mono,
        bid,
        ask,
        host,
        boot,
        int(QualityFlag.SUSPECT),
    )
    dataset = tmp_path / "dataset"
    _write_dataset(dataset, points=points)

    report = analyze_frontier_pilot_dataset(
        dataset,
        fee_scenario_bps_per_side=Decimal("4.5"),
    )

    assert report.observation_count == 3


def test_frontier_pilot_reports_insufficient_data_instead_of_inventing_horizon(
    tmp_path: Path,
) -> None:
    dataset = tmp_path / "dataset"
    _write_dataset(dataset, points=_regular_points(1))

    report = analyze_frontier_pilot_dataset(
        dataset,
        fee_scenario_bps_per_side=Decimal("4.5"),
    )

    assert report.status == "INSUFFICIENT_DATA"
    assert report.gate_decision == "NOT_EVALUATED"
    assert report.horizons == ()
    assert report.horizon_lower_bound_seconds is None


def test_frontier_pilot_rejects_multiple_causal_domains(tmp_path: Path) -> None:
    points = _regular_points(3)
    mono, bid, ask, _, _, flags = points[-1]
    points[-1] = (mono, bid, ask, "host-b", "boot-b", flags)
    dataset = tmp_path / "dataset"
    _write_dataset(dataset, points=points)

    with pytest.raises(FrontierValidationError, match=r"exactly one.*causal domain"):
        analyze_frontier_pilot_dataset(
            dataset,
            fee_scenario_bps_per_side=Decimal("4.5"),
        )


def test_frontier_pilot_rejects_invalid_manifest_binding(tmp_path: Path) -> None:
    dataset = tmp_path / "dataset"
    _write_dataset(
        dataset,
        points=_regular_points(3),
        bundle_sha="invalid",
    )

    with pytest.raises(FrontierValidationError, match="bundle_sha256"):
        analyze_frontier_pilot_dataset(
            dataset,
            fee_scenario_bps_per_side=Decimal("4.5"),
        )


def test_frontier_pilot_derives_next_125_evidence_window_when_cost_not_reached(
    tmp_path: Path,
) -> None:
    dataset = tmp_path / "flat-dataset"
    points: list[tuple[int, str, str, str, str, int]] = []
    for index in range(61):
        points.append(
            (
                index * 1_000_000_000,
                "99.95",
                "100.05",
                "host-a",
                "boot-a",
                0,
            )
        )
    _write_dataset(dataset, points=points)

    report = analyze_frontier_pilot_dataset(
        dataset,
        fee_scenario_bps_per_side=Decimal("4.5"),
    )

    assert report.status == "PILOT_MEASURED"
    assert not report.movement_q95_meets_median_known_friction
    assert [item.horizon_seconds for item in report.horizons] == [1, 2, 5, 10, 20]
    assert all(item.gap_excluded_count == 0 for item in report.horizons)
    assert report.evidence_window_plan.required_non_overlapping_windows == 2952
    assert report.evidence_window_plan.target_horizon_seconds == 50
    assert report.evidence_window_plan.minimum_observed_duration_seconds == 147600
    assert (
        report.evidence_window_plan.target_reason
        == "EXPAND_ONE_125_CELL_BECAUSE_PILOT_Q95_BELOW_MEDIAN_KNOWN_FRICTION"
    )
