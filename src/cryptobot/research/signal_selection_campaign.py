from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import cast

from cryptobot.data.instruments import InstrumentRole
from cryptobot.research.signal_campaign import (
    build_gate_feature_dataset_before_wall,
)
from cryptobot.research.signal_protocol import SignalFeatureRow
from cryptobot.research.signal_selection import (
    CONFIRMATION_START_WALL_NS,
    EXPECTED_DATASET_SHA256,
    EXPECTED_PROTOCOL_SHA256,
    EXPECTED_SELECTION_ROW_COUNT,
    SELECTION_START_WALL_NS,
    SignalSelectionValidationError,
)

EXPECTED_GATE_REPORT_SHA256 = "d2289bff1d2d3ffddc246456ff6ea9c6a4ae7663e1805d40cc0802e33891a3b2"
PRIMARY_INSTRUMENT_ID = "hyperliquid.mainnet.perpetual.btc"
REFERENCE_INSTRUMENT_ID = "binance_usdm.reference.perpetual.btcusdt"

_ROWS_MARKER = b'"rows":['
_WALL_RE = re.compile(rb'"decision_recv_wall_ns":([0-9]+)')


def load_verified_selection_rows(
    *,
    campaign_root: str | Path,
    gate_report_path: str | Path,
    protocol_path: str | Path,
    frozen_dataset_path: str | Path,
) -> tuple[SignalFeatureRow, ...]:
    _verify_file_sha256(
        Path(protocol_path),
        expected=EXPECTED_PROTOCOL_SHA256,
        label="protocol",
    )
    raw_dataset = _read_bytes(Path(frozen_dataset_path))
    actual_dataset_sha = hashlib.sha256(raw_dataset).hexdigest()
    if actual_dataset_sha != EXPECTED_DATASET_SHA256:
        raise SignalSelectionValidationError(
            "dataset SHA-256 does not match frozen registered value"
        )

    frozen_selection = load_frozen_selection_row_dicts(raw_dataset)

    rebuilt = build_gate_feature_dataset_before_wall(
        campaign_root=campaign_root,
        gate_report_path=gate_report_path,
        expected_gate_report_sha256=EXPECTED_GATE_REPORT_SHA256,
        instrument_id=PRIMARY_INSTRUMENT_ID,
        reference_instrument_id=REFERENCE_INSTRUMENT_ID,
        role=InstrumentRole.PRIMARY,
        decision_end_wall_ns_exclusive=CONFIRMATION_START_WALL_NS,
    )
    selection = tuple(
        row
        for row in rebuilt.rows
        if SELECTION_START_WALL_NS <= row.decision_recv_wall_ns < CONFIRMATION_START_WALL_NS
    )

    if len(selection) != EXPECTED_SELECTION_ROW_COUNT:
        raise SignalSelectionValidationError(
            f"rebuilt selection requires exactly {EXPECTED_SELECTION_ROW_COUNT} rows"
        )
    if len(frozen_selection) != EXPECTED_SELECTION_ROW_COUNT:
        raise SignalSelectionValidationError(
            f"frozen selection requires exactly {EXPECTED_SELECTION_ROW_COUNT} rows"
        )

    for index, (row, frozen) in enumerate(zip(selection, frozen_selection, strict=True)):
        actual = row.as_dict()
        if actual != frozen:
            raise SignalSelectionValidationError(
                f"rebuilt selection row differs from frozen dataset at index {index}"
            )
        exit_wall = row.outcome.exit_recv_wall_ns
        if exit_wall is not None and exit_wall >= CONFIRMATION_START_WALL_NS:
            raise SignalSelectionValidationError("selection row exit crosses confirmation boundary")

    return selection


def load_frozen_selection_row_dicts(
    raw_dataset: bytes,
) -> tuple[dict[str, object], ...]:
    marker_index = raw_dataset.find(_ROWS_MARKER)
    if marker_index < 0:
        raise SignalSelectionValidationError("frozen dataset rows array is missing")
    position = marker_index + len(_ROWS_MARKER)
    output: list[dict[str, object]] = []

    while position < len(raw_dataset):
        position = _skip_delimiters(raw_dataset, position)
        if position >= len(raw_dataset):
            raise SignalSelectionValidationError("frozen dataset rows array is truncated")
        if raw_dataset[position] == ord("]"):
            break
        if raw_dataset[position] != ord("{"):
            raise SignalSelectionValidationError("frozen dataset row must be a JSON object")

        wall = _peek_decision_wall(raw_dataset, position)
        if wall >= CONFIRMATION_START_WALL_NS:
            break

        end = _json_object_end(raw_dataset, position)
        if wall >= SELECTION_START_WALL_NS:
            try:
                parsed = json.loads(raw_dataset[position:end])
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise SignalSelectionValidationError(
                    "pre-confirmation frozen row is invalid JSON"
                ) from exc
            if not isinstance(parsed, dict) or not all(isinstance(key, str) for key in parsed):
                raise SignalSelectionValidationError(
                    "pre-confirmation frozen row must decode to an object"
                )
            output.append(cast(dict[str, object], parsed))
        position = end

    return tuple(output)


def _peek_decision_wall(raw: bytes, row_start: int) -> int:
    prefix = raw[row_start : min(len(raw), row_start + 4096)]
    match = _WALL_RE.search(prefix)
    if match is None:
        raise SignalSelectionValidationError(
            "cannot locate decision_recv_wall_ns before row payload"
        )
    return int(match.group(1))


def _json_object_end(raw: bytes, start: int) -> int:
    depth = 0
    in_string = False
    escaped = False

    for index in range(start, len(raw)):
        value = raw[index]
        if in_string:
            if escaped:
                escaped = False
            elif value == ord("\\"):
                escaped = True
            elif value == ord('"'):
                in_string = False
            continue

        if value == ord('"'):
            in_string = True
        elif value == ord("{"):
            depth += 1
        elif value == ord("}"):
            depth -= 1
            if depth == 0:
                return index + 1
            if depth < 0:
                break

    raise SignalSelectionValidationError("frozen dataset row object is truncated")


def _skip_delimiters(raw: bytes, position: int) -> int:
    while position < len(raw) and raw[position] in b" \t\r\n,":
        position += 1
    return position


def _verify_file_sha256(path: Path, *, expected: str, label: str) -> None:
    actual = hashlib.sha256(_read_bytes(path)).hexdigest()
    if actual != expected:
        raise SignalSelectionValidationError(
            f"{label} SHA-256 does not match frozen registered value"
        )


def _read_bytes(path: Path) -> bytes:
    try:
        return path.read_bytes()
    except OSError as exc:
        raise SignalSelectionValidationError(f"cannot read frozen file: {path}") from exc
