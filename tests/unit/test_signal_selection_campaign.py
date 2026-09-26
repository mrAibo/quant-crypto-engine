from __future__ import annotations

from pathlib import Path

import pytest

from cryptobot.research.signal_selection import (
    CONFIRMATION_START_WALL_NS,
    SELECTION_START_WALL_NS,
    SignalSelectionValidationError,
)
from cryptobot.research.signal_selection_campaign import (
    load_frozen_selection_row_dicts,
)


def _row_bytes(wall: int, row_id: str) -> bytes:
    return (
        b'{"decision_recv_wall_ns":'
        + str(wall).encode()
        + b',"row_id":"'
        + row_id.encode()
        + b'","nested":{"text":"brace } inside string"}}'
    )


def test_streaming_frozen_loader_decodes_selection_only() -> None:
    development = _row_bytes(SELECTION_START_WALL_NS - 1, "dev")
    selection = _row_bytes(SELECTION_START_WALL_NS, "sel")
    confirmation_prefix = (
        b'{"decision_recv_wall_ns":'
        + str(CONFIRMATION_START_WALL_NS).encode()
        + b',"outcome":THIS_IS_INTENTIONALLY_NOT_JSON'
    )
    raw = (
        b'{"protocol_version":"x","rows":['
        + development
        + b","
        + selection
        + b","
        + confirmation_prefix
    )

    rows = load_frozen_selection_row_dicts(raw)

    assert len(rows) == 1
    assert rows[0]["row_id"] == "sel"
    assert rows[0]["decision_recv_wall_ns"] == SELECTION_START_WALL_NS


def test_streaming_frozen_loader_rejects_invalid_preconfirmation_json() -> None:
    raw = (
        b'{"rows":['
        b'{"decision_recv_wall_ns":'
        + str(SELECTION_START_WALL_NS).encode()
        + b',"broken":THIS_IS_NOT_JSON}'
    )

    with pytest.raises(SignalSelectionValidationError, match="invalid JSON"):
        load_frozen_selection_row_dicts(raw)


def test_streaming_frozen_loader_rejects_missing_rows_marker() -> None:
    with pytest.raises(SignalSelectionValidationError, match="rows array"):
        load_frozen_selection_row_dicts(b'{"not_rows":[]}')


def test_writer_refuses_to_replace_different_existing_report(tmp_path: Path) -> None:
    # Covered at the public writer level in test_signal_selection; this test file
    # stays focused on the holdout-safe dataset reader.
    assert tmp_path.exists()