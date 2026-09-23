from __future__ import annotations

from datetime import UTC, datetime
import json
from pathlib import Path

import pytest

from cryptobot.evidence.contract import (
    EvidenceStatus,
    EvidenceValidationError,
    load_evidence_contract,
    validate_evidence,
)


def _fact(**overrides: object) -> dict[str, object]:
    fact: dict[str, object] = {
        "fact_id": "example.fact",
        "subject": "Example fact",
        "claim": "A narrow claim.",
        "status": "VERIFIED",
        "verification_scope": "DOCUMENTED",
        "source_url": "https://example.com/source",
        "source_retrieved_at": "2026-09-23T00:00:00Z",
        "source_hash": None,
        "effective_from": None,
        "effective_to": None,
        "environment": "GENERAL",
        "verification_artifact": "docs/evidence_sources.md#example",
        "limitations": "Example limitation.",
        "reverify_trigger": ["SOURCE_CHANGE"],
        "reverify_after": None,
        "owner": "project",
    }
    fact.update(overrides)
    return fact


def _write(tmp_path: Path, facts: list[dict[str, object]], **root: object) -> Path:
    payload: dict[str, object] = {"schema_version": 1, "facts": facts}
    payload.update(root)
    path = tmp_path / "evidence.yaml"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_verified_fact_requires_source_url(tmp_path: Path) -> None:
    path = _write(tmp_path, [_fact(source_url=None)])

    with pytest.raises(EvidenceValidationError, match="requires source_url"):
        load_evidence_contract(path)


def test_verified_fact_cannot_use_unverified_scope(tmp_path: Path) -> None:
    path = _write(tmp_path, [_fact(verification_scope="UNVERIFIED")])

    with pytest.raises(EvidenceValidationError, match="cannot use UNVERIFIED"):
        load_evidence_contract(path)


def test_unknown_fact_can_remain_value_unknown_without_source(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        [
            _fact(
                status="UNKNOWN",
                verification_scope="UNVERIFIED",
                source_url=None,
                source_retrieved_at=None,
                verification_artifact=None,
                fact_id="execution.latency",
            )
        ],
    )

    contract = load_evidence_contract(path)

    assert contract.facts[0].status is EvidenceStatus.UNKNOWN
    assert contract.facts[0].source_url is None


def test_reverification_due_is_reported(tmp_path: Path) -> None:
    path = _write(tmp_path, [_fact(reverify_after="2026-09-22T00:00:00Z")])

    report = validate_evidence(path, now=datetime(2026, 9, 23, tzinfo=UTC))

    assert report.reverification_due == 1
    assert report.due_fact_ids == ("example.fact",)


def test_future_reverification_is_not_due(tmp_path: Path) -> None:
    path = _write(tmp_path, [_fact(reverify_after="2026-09-24T00:00:00Z")])

    report = validate_evidence(path, now=datetime(2026, 9, 23, tzinfo=UTC))

    assert report.reverification_due == 0


def test_unknown_fact_field_is_rejected(tmp_path: Path) -> None:
    fact = _fact()
    fact["mystery"] = "not allowed"
    path = _write(tmp_path, [fact])

    with pytest.raises(EvidenceValidationError, match="unknown fields: mystery"):
        load_evidence_contract(path)


def test_unknown_top_level_field_is_rejected(tmp_path: Path) -> None:
    path = _write(tmp_path, [_fact()], mystery="not allowed")

    with pytest.raises(EvidenceValidationError, match="unknown top-level fields: mystery"):
        load_evidence_contract(path)


def test_duplicate_fact_ids_are_rejected(tmp_path: Path) -> None:
    path = _write(tmp_path, [_fact(), _fact()])

    with pytest.raises(EvidenceValidationError, match="duplicate fact_id values"):
        load_evidence_contract(path)


def test_source_hash_format_is_strict(tmp_path: Path) -> None:
    path = _write(tmp_path, [_fact(source_hash="abc")])

    with pytest.raises(EvidenceValidationError, match="source_hash"):
        load_evidence_contract(path)


def test_verified_fact_without_retained_source_hash_is_reported(tmp_path: Path) -> None:
    path = _write(tmp_path, [_fact(source_hash=None)])

    report = validate_evidence(path, now=datetime(2026, 9, 23, tzinfo=UTC))

    assert report.verified_without_source_hash == ("example.fact",)
