from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any


class EvidenceValidationError(ValueError):
    """Raised when the evidence contract is structurally or semantically invalid."""


class EvidenceStatus(StrEnum):
    VERIFIED = "VERIFIED"
    UNKNOWN = "UNKNOWN"


class VerificationScope(StrEnum):
    UNVERIFIED = "UNVERIFIED"
    DOCUMENTED = "DOCUMENTED"
    OBSERVED_PUBLIC = "OBSERVED_PUBLIC"
    OBSERVED_TESTNET = "OBSERVED_TESTNET"
    OBSERVED_MAINNET = "OBSERVED_MAINNET"


class EvidenceEnvironment(StrEnum):
    GENERAL = "GENERAL"
    MAINNET = "MAINNET"
    TESTNET = "TESTNET"
    REFERENCE = "REFERENCE"


_FACT_ID_RE = re.compile(r"^[a-z0-9]+(?:[._-][a-z0-9]+)*$")
_SHA256_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_ALLOWED_TOP_LEVEL_FIELDS = frozenset({"schema_version", "facts"})
_REQUIRED_FACT_FIELDS = frozenset(
    {
        "fact_id",
        "subject",
        "claim",
        "status",
        "verification_scope",
        "source_url",
        "source_retrieved_at",
        "source_hash",
        "effective_from",
        "effective_to",
        "environment",
        "verification_artifact",
        "limitations",
        "reverify_trigger",
        "reverify_after",
        "owner",
    }
)


@dataclass(frozen=True, slots=True)
class EvidenceFact:
    fact_id: str
    subject: str
    claim: str
    status: EvidenceStatus
    verification_scope: VerificationScope
    source_url: str | None
    source_retrieved_at: datetime | None
    source_hash: str | None
    effective_from: datetime | None
    effective_to: datetime | None
    environment: EvidenceEnvironment
    verification_artifact: str | None
    limitations: str
    reverify_trigger: tuple[str, ...]
    reverify_after: datetime | None
    owner: str

    def is_reverification_due(self, now: datetime) -> bool:
        current = _require_aware_datetime(now, "now")
        if self.reverify_after is not None and current >= self.reverify_after:
            return True
        return self.effective_to is not None and current > self.effective_to


@dataclass(frozen=True, slots=True)
class EvidenceContract:
    schema_version: int
    facts: tuple[EvidenceFact, ...]


@dataclass(frozen=True, slots=True)
class EvidenceReport:
    schema_version: int
    total_facts: int
    verified_facts: int
    unknown_facts: int
    reverification_due: int
    due_fact_ids: tuple[str, ...]
    verified_without_source_hash: tuple[str, ...]

    def as_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "total_facts": self.total_facts,
            "verified_facts": self.verified_facts,
            "unknown_facts": self.unknown_facts,
            "reverification_due": self.reverification_due,
            "due_fact_ids": list(self.due_fact_ids),
            "verified_without_source_hash": list(self.verified_without_source_hash),
        }


def load_evidence_contract(path: str | Path) -> EvidenceContract:
    """Load and validate JSON-compatible YAML using only the Python standard library.

    JSON is a subset of YAML 1.2. Stage 0 deliberately keeps evidence.yaml inside that
    subset so the evidence validator has no third-party parser dependency.
    """

    source_path = Path(path)
    try:
        raw = json.loads(source_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise EvidenceValidationError(
            f"{source_path} must be JSON-compatible YAML: {exc.msg} at line {exc.lineno}"
        ) from exc

    if not isinstance(raw, dict):
        raise EvidenceValidationError("evidence contract root must be an object")

    unknown_top_level = set(raw) - _ALLOWED_TOP_LEVEL_FIELDS
    if unknown_top_level:
        raise EvidenceValidationError(
            f"unknown top-level fields: {', '.join(sorted(unknown_top_level))}"
        )

    missing_top_level = _ALLOWED_TOP_LEVEL_FIELDS - set(raw)
    if missing_top_level:
        raise EvidenceValidationError(
            f"missing top-level fields: {', '.join(sorted(missing_top_level))}"
        )

    schema_version = raw["schema_version"]
    if (
        not isinstance(schema_version, int)
        or isinstance(schema_version, bool)
        or schema_version != 1
    ):
        raise EvidenceValidationError("schema_version must be integer 1")

    raw_facts = raw["facts"]
    if not isinstance(raw_facts, list):
        raise EvidenceValidationError("facts must be an array")

    facts = tuple(_parse_fact(item, index) for index, item in enumerate(raw_facts))
    fact_ids = [fact.fact_id for fact in facts]
    duplicates = sorted({fact_id for fact_id in fact_ids if fact_ids.count(fact_id) > 1})
    if duplicates:
        raise EvidenceValidationError(f"duplicate fact_id values: {', '.join(duplicates)}")

    return EvidenceContract(schema_version=schema_version, facts=facts)


def validate_evidence(path: str | Path, *, now: datetime | None = None) -> EvidenceReport:
    contract = load_evidence_contract(path)
    current = now or datetime.now(UTC)
    current = _require_aware_datetime(current, "now")

    due_fact_ids = tuple(
        fact.fact_id for fact in contract.facts if fact.is_reverification_due(current)
    )
    missing_hashes = tuple(
        fact.fact_id
        for fact in contract.facts
        if fact.status is EvidenceStatus.VERIFIED and fact.source_hash is None
    )

    return EvidenceReport(
        schema_version=contract.schema_version,
        total_facts=len(contract.facts),
        verified_facts=sum(f.status is EvidenceStatus.VERIFIED for f in contract.facts),
        unknown_facts=sum(f.status is EvidenceStatus.UNKNOWN for f in contract.facts),
        reverification_due=len(due_fact_ids),
        due_fact_ids=due_fact_ids,
        verified_without_source_hash=missing_hashes,
    )


def _parse_fact(raw: Any, index: int) -> EvidenceFact:
    if not isinstance(raw, dict):
        raise EvidenceValidationError(f"facts[{index}] must be an object")

    unknown_fields = set(raw) - _REQUIRED_FACT_FIELDS
    if unknown_fields:
        raise EvidenceValidationError(
            f"facts[{index}] has unknown fields: {', '.join(sorted(unknown_fields))}"
        )

    missing_fields = _REQUIRED_FACT_FIELDS - set(raw)
    if missing_fields:
        raise EvidenceValidationError(
            f"facts[{index}] is missing fields: {', '.join(sorted(missing_fields))}"
        )

    fact_id = _required_string(raw, "fact_id", index)
    if not _FACT_ID_RE.fullmatch(fact_id):
        raise EvidenceValidationError(
            f"facts[{index}].fact_id must use lowercase alphanumeric dot/dash/underscore segments"
        )

    subject = _required_string(raw, "subject", index)
    claim = _required_string(raw, "claim", index)
    limitations = _required_string(raw, "limitations", index)
    owner = _required_string(raw, "owner", index)

    status = _parse_enum(EvidenceStatus, raw["status"], f"facts[{index}].status")
    scope = _parse_enum(
        VerificationScope,
        raw["verification_scope"],
        f"facts[{index}].verification_scope",
    )
    environment = _parse_enum(
        EvidenceEnvironment,
        raw["environment"],
        f"facts[{index}].environment",
    )

    source_url = _optional_string(raw["source_url"], f"facts[{index}].source_url")
    source_retrieved_at = _parse_optional_datetime(
        raw["source_retrieved_at"], f"facts[{index}].source_retrieved_at"
    )
    source_hash = _optional_string(raw["source_hash"], f"facts[{index}].source_hash")
    effective_from = _parse_optional_datetime(
        raw["effective_from"], f"facts[{index}].effective_from"
    )
    effective_to = _parse_optional_datetime(raw["effective_to"], f"facts[{index}].effective_to")
    verification_artifact = _optional_string(
        raw["verification_artifact"], f"facts[{index}].verification_artifact"
    )
    reverify_after = _parse_optional_datetime(
        raw["reverify_after"], f"facts[{index}].reverify_after"
    )

    raw_triggers = raw["reverify_trigger"]
    if not isinstance(raw_triggers, list) or not raw_triggers:
        raise EvidenceValidationError(f"facts[{index}].reverify_trigger must be a non-empty array")
    triggers: list[str] = []
    for trigger_index, trigger in enumerate(raw_triggers):
        if not isinstance(trigger, str) or not trigger.strip():
            raise EvidenceValidationError(
                f"facts[{index}].reverify_trigger[{trigger_index}] must be a non-empty string"
            )
        triggers.append(trigger.strip())
    if len(set(triggers)) != len(triggers):
        raise EvidenceValidationError(f"facts[{index}].reverify_trigger contains duplicates")

    if source_url is not None and not source_url.startswith("https://"):
        raise EvidenceValidationError(f"facts[{index}].source_url must use https://")
    if source_hash is not None and not _SHA256_RE.fullmatch(source_hash):
        raise EvidenceValidationError(
            f"facts[{index}].source_hash must be null or sha256:<64 lowercase hex chars>"
        )
    if effective_from is not None and effective_to is not None and effective_from > effective_to:
        raise EvidenceValidationError(
            f"facts[{index}] effective_from must not be after effective_to"
        )

    if status is EvidenceStatus.VERIFIED:
        if scope is VerificationScope.UNVERIFIED:
            raise EvidenceValidationError(
                f"facts[{index}] VERIFIED fact cannot use UNVERIFIED scope"
            )
        if source_url is None:
            raise EvidenceValidationError(f"facts[{index}] VERIFIED fact requires source_url")
        if source_retrieved_at is None:
            raise EvidenceValidationError(
                f"facts[{index}] VERIFIED fact requires source_retrieved_at"
            )
        if verification_artifact is None:
            raise EvidenceValidationError(
                f"facts[{index}] VERIFIED fact requires verification_artifact"
            )

    return EvidenceFact(
        fact_id=fact_id,
        subject=subject,
        claim=claim,
        status=status,
        verification_scope=scope,
        source_url=source_url,
        source_retrieved_at=source_retrieved_at,
        source_hash=source_hash,
        effective_from=effective_from,
        effective_to=effective_to,
        environment=environment,
        verification_artifact=verification_artifact,
        limitations=limitations,
        reverify_trigger=tuple(triggers),
        reverify_after=reverify_after,
        owner=owner,
    )


def _required_string(raw: Mapping[str, Any], field: str, index: int) -> str:
    value = raw[field]
    if not isinstance(value, str) or not value.strip():
        raise EvidenceValidationError(f"facts[{index}].{field} must be a non-empty string")
    return value.strip()


def _optional_string(value: Any, field: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise EvidenceValidationError(f"{field} must be null or a non-empty string")
    return value.strip()


def _parse_enum[EnumT: StrEnum](enum_type: type[EnumT], value: Any, field: str) -> EnumT:
    if not isinstance(value, str):
        raise EvidenceValidationError(f"{field} must be a string")
    try:
        return enum_type(value)
    except ValueError as exc:
        allowed = ", ".join(member.value for member in enum_type)
        raise EvidenceValidationError(f"{field} must be one of: {allowed}") from exc


def _parse_optional_datetime(value: Any, field: str) -> datetime | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise EvidenceValidationError(f"{field} must be null or an ISO-8601 string")
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise EvidenceValidationError(f"{field} is not valid ISO-8601") from exc
    if parsed.tzinfo is None:
        raise EvidenceValidationError(f"{field} must include an explicit timezone")
    return parsed.astimezone(UTC)


def _require_aware_datetime(value: datetime, field: str) -> datetime:
    if value.tzinfo is None:
        raise EvidenceValidationError(f"{field} must be timezone-aware")
    return value.astimezone(UTC)
