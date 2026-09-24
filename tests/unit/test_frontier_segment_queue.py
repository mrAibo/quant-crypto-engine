from __future__ import annotations

from pathlib import Path

from cryptobot.runtime.frontier_segment import discover_pending_captured_segments


def test_pending_capture_discovery_skips_published_and_started(tmp_path: Path) -> None:
    root = tmp_path / "campaign"
    root.mkdir()

    pending = root / "segment-run-100-a"
    pending.mkdir()
    (pending / "capture-ready.json").write_text("{}\n", encoding="utf-8")

    started = root / "segment-run-200-b"
    started.mkdir()
    (started / "capture-ready.json").write_text("{}\n", encoding="utf-8")
    (started / "processing-started.json").write_text("{}\n", encoding="utf-8")

    published = root / "segment-run-300-c"
    published.mkdir()
    (published / "capture-ready.json").write_text("{}\n", encoding="utf-8")
    (published / "segment-evidence.json").write_text("{}\n", encoding="utf-8")

    legacy = root / "segment-run-050-legacy"
    legacy.mkdir()

    assert discover_pending_captured_segments(root) == (pending,)
