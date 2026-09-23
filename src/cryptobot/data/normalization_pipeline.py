from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum
from typing import cast

from cryptobot.adapters.binance.normalize import (
    PARSE_VERSION as BINANCE_PARSE_VERSION,
    BinanceReferenceNormalizationStatus,
    normalize_binance_reference_frame,
    serialize_binance_reference_event,
)
from cryptobot.adapters.hyperliquid.context import (
    PARSE_VERSION as HL_CONTEXT_PARSE_VERSION,
    ContextNormalizationStatus,
    normalize_context_frame,
    serialize_normalized_context,
)
from cryptobot.adapters.hyperliquid.normalize import (
    PARSE_VERSION as HL_BOOK_PARSE_VERSION,
    BookNormalizationStatus,
    normalize_book_frame,
    serialize_normalized_book_event,
)
from cryptobot.adapters.hyperliquid.trades import (
    PARSE_VERSION as HL_TRADE_PARSE_VERSION,
    TradeNormalizationStatus,
    normalize_trade_frame,
    serialize_normalized_trades,
)
from cryptobot.data.events import (
    BBO,
    FundingRateObservation,
    L2Snapshot,
    MarkPrice,
    OraclePrice,
    ReferenceBBO,
    ReferenceTrade,
    Trade,
)
from cryptobot.data.instruments import InstrumentRegistry
from cryptobot.data.rawlog import RawFrame

PIPELINE_VERSION = "causal-normalization-v1"
HL_SOURCE_ID = "hyperliquid-mainnet-public"
BINANCE_SOURCE_ID = "binance-usdm-reference-public"
_HL_DISPATCHER = "hyperliquid-dispatch-v1"


type NormalizedEvent = (
    L2Snapshot
    | BBO
    | Trade
    | FundingRateObservation
    | MarkPrice
    | OraclePrice
    | ReferenceBBO
    | ReferenceTrade
)


class FrameOutcome(StrEnum):
    EVENTS = "EVENTS"
    EMPTY = "EMPTY"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    ERROR = "ERROR"


class PipelineErrorCode(StrEnum):
    INVALID_PROVENANCE = "INVALID_PROVENANCE"
    INVALID_JSON = "INVALID_JSON"
    INVALID_ENVELOPE = "INVALID_ENVELOPE"
    UNSUPPORTED_SOURCE = "UNSUPPORTED_SOURCE"
    PARSER_ERROR = "PARSER_ERROR"


class CausalDomainError(ValueError):
    """Raised when strict causal ordering is requested across clock domains."""


@dataclass(frozen=True, slots=True)
class PipelineError:
    code: PipelineErrorCode
    parser_name: str
    parser_code: str | None
    detail: str
    raw_segment_id: str
    raw_offset: int
    raw_sha256: str


@dataclass(frozen=True, slots=True)
class FrameResult:
    outcome: FrameOutcome
    source_id: str
    host_id: str
    boot_id: str
    recv_wall_ns: int
    recv_mono_ns: int
    connection_id: str
    ingest_seq: int
    raw_segment_id: str
    raw_offset: int
    raw_sha256: str
    parser_name: str
    channel_or_stream: str | None
    events: tuple[NormalizedEvent, ...] = ()
    error: PipelineError | None = None

    def __post_init__(self) -> None:
        if self.outcome is FrameOutcome.EVENTS:
            if not self.events or self.error is not None:
                raise ValueError("EVENTS requires one or more events and no error")
        elif self.outcome is FrameOutcome.ERROR:
            if self.events or self.error is None:
                raise ValueError("ERROR requires one error and no events")
        elif self.events or self.error is not None:
            raise ValueError("EMPTY/NOT_APPLICABLE cannot contain events or an error")

    @property
    def causal_domain(self) -> tuple[str, str]:
        return (self.host_id, self.boot_id)


@dataclass(frozen=True, slots=True)
class CausalRecord:
    host_id: str
    boot_id: str
    recv_mono_ns: int
    recv_wall_ns: int
    source_id: str
    raw_segment_id: str
    raw_offset: int
    event_ordinal: int
    event: NormalizedEvent

    @property
    def causal_domain(self) -> tuple[str, str]:
        return (self.host_id, self.boot_id)

    @property
    def causal_key(self) -> tuple[int, int, str, str, int, int]:
        return (
            self.recv_mono_ns,
            self.recv_wall_ns,
            self.source_id,
            self.raw_segment_id,
            self.raw_offset,
            self.event_ordinal,
        )


@dataclass(frozen=True, slots=True)
class CausalDomainRange:
    host_id: str
    boot_id: str
    first_recv_wall_ns: int
    last_recv_wall_ns: int
    first_recv_mono_ns: int
    last_recv_mono_ns: int

    def as_dict(self) -> dict[str, object]:
        return {
            "host_id": self.host_id,
            "boot_id": self.boot_id,
            "first_recv_wall_ns": self.first_recv_wall_ns,
            "last_recv_wall_ns": self.last_recv_wall_ns,
            "first_recv_mono_ns": self.first_recv_mono_ns,
            "last_recv_mono_ns": self.last_recv_mono_ns,
        }


@dataclass(frozen=True, slots=True)
class PipelineReport:
    pipeline_version: str
    total_raw_frames: int
    source_counts: tuple[tuple[str, int], ...]
    outcome_counts: tuple[tuple[str, int], ...]
    event_type_counts: tuple[tuple[str, int], ...]
    error_counts: tuple[tuple[str, int], ...]
    causal_domain_count: int
    causal_domain_ranges: tuple[CausalDomainRange, ...]
    clock_order_anomaly_count: int
    duplicate_stable_trade_id_count: int
    normalized_record_count: int
    normalized_records_sha256: str

    def as_dict(self) -> dict[str, object]:
        return {
            "pipeline_version": self.pipeline_version,
            "total_raw_frames": self.total_raw_frames,
            "source_counts": dict(self.source_counts),
            "outcome_counts": dict(self.outcome_counts),
            "event_type_counts": dict(self.event_type_counts),
            "error_counts": dict(self.error_counts),
            "causal_domain_count": self.causal_domain_count,
            "causal_domain_ranges": [item.as_dict() for item in self.causal_domain_ranges],
            "clock_order_anomaly_count": self.clock_order_anomaly_count,
            "duplicate_stable_trade_id_count": self.duplicate_stable_trade_id_count,
            "normalized_record_count": self.normalized_record_count,
            "normalized_records_sha256": self.normalized_records_sha256,
        }


def normalize_frame(frame: RawFrame, registry: InstrumentRegistry) -> FrameResult:
    provenance_error = _validate_provenance(frame)
    if provenance_error is not None:
        return _frame_error(
            frame,
            parser_name=PIPELINE_VERSION,
            channel_or_stream=frame.metadata.channel_hint,
            code=PipelineErrorCode.INVALID_PROVENANCE,
            parser_code=None,
            detail=provenance_error,
        )

    if frame.metadata.source_id == HL_SOURCE_ID:
        return _normalize_hyperliquid(frame, registry)
    if frame.metadata.source_id == BINANCE_SOURCE_ID:
        return _normalize_binance(frame, registry)

    return _frame_error(
        frame,
        parser_name=PIPELINE_VERSION,
        channel_or_stream=frame.metadata.channel_hint,
        code=PipelineErrorCode.UNSUPPORTED_SOURCE,
        parser_code=None,
        detail=f"unsupported Stage-0 source_id: {frame.metadata.source_id}",
    )


def normalize_frames(
    frames: Iterable[RawFrame],
    registry: InstrumentRegistry,
) -> tuple[FrameResult, ...]:
    return tuple(normalize_frame(frame, registry) for frame in frames)


def strict_causal_records(
    results: Iterable[FrameResult],
) -> tuple[CausalRecord, ...]:
    materialized = tuple(results)
    domains = {result.causal_domain for result in materialized}
    if len(domains) > 1:
        rendered = ", ".join(f"{host}/{boot}" for host, boot in sorted(domains))
        raise CausalDomainError(
            "strict causal merge requires one (host_id, boot_id) domain; "
            f"found: {rendered}"
        )
    records = _records_from_results(materialized)
    return tuple(sorted(records, key=lambda record: record.causal_key))


def build_pipeline_report(results: Iterable[FrameResult]) -> PipelineReport:
    materialized = tuple(results)
    records = _records_from_results(materialized)
    canonical_records = tuple(
        sorted(
            records,
            key=lambda record: (
                record.host_id,
                record.boot_id,
                record.causal_key,
            ),
        )
    )
    serialized_records = serialize_causal_records(canonical_records)

    source_counts = Counter(result.source_id for result in materialized)
    outcome_counts = Counter(result.outcome.value for result in materialized)
    event_type_counts = Counter(
        event.envelope.event_type.value
        for result in materialized
        for event in result.events
    )
    error_counts = Counter(
        _error_count_key(result.error)
        for result in materialized
        if result.error is not None
    )

    grouped: dict[tuple[str, str], list[FrameResult]] = defaultdict(list)
    for result in materialized:
        grouped[result.causal_domain].append(result)

    ranges = tuple(
        _domain_range(domain, group)
        for domain, group in sorted(grouped.items())
    )
    anomaly_count = sum(_clock_order_anomalies(group) for group in grouped.values())

    return PipelineReport(
        pipeline_version=PIPELINE_VERSION,
        total_raw_frames=len(materialized),
        source_counts=tuple(sorted(source_counts.items())),
        outcome_counts=tuple(sorted(outcome_counts.items())),
        event_type_counts=tuple(sorted(event_type_counts.items())),
        error_counts=tuple(sorted(error_counts.items())),
        causal_domain_count=len(grouped),
        causal_domain_ranges=ranges,
        clock_order_anomaly_count=anomaly_count,
        duplicate_stable_trade_id_count=_duplicate_trade_ids(records),
        normalized_record_count=len(records),
        normalized_records_sha256=hashlib.sha256(serialized_records).hexdigest(),
    )


def serialize_causal_records(records: Iterable[CausalRecord]) -> bytes:
    payload = []
    for record in records:
        payload.append(
            {
                "host_id": record.host_id,
                "boot_id": record.boot_id,
                "recv_mono_ns": record.recv_mono_ns,
                "recv_wall_ns": record.recv_wall_ns,
                "source_id": record.source_id,
                "raw_segment_id": record.raw_segment_id,
                "raw_offset": record.raw_offset,
                "event_ordinal": record.event_ordinal,
                "causal_key": list(record.causal_key),
                "event_json": _serialize_event(record.event).decode(),
            }
        )
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode()


def serialize_pipeline_report(report: PipelineReport) -> bytes:
    return json.dumps(
        report.as_dict(),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode()


def _normalize_hyperliquid(
    frame: RawFrame,
    registry: InstrumentRegistry,
) -> FrameResult:
    try:
        decoded = json.loads(frame.payload)
    except (UnicodeDecodeError, json.JSONDecodeError):
        return _frame_error(
            frame,
            parser_name=_HL_DISPATCHER,
            channel_or_stream=frame.metadata.channel_hint,
            code=PipelineErrorCode.INVALID_JSON,
            parser_code=None,
            detail="payload is not valid UTF-8 JSON",
        )
    if not isinstance(decoded, dict) or not all(isinstance(key, str) for key in decoded):
        return _frame_error(
            frame,
            parser_name=_HL_DISPATCHER,
            channel_or_stream=frame.metadata.channel_hint,
            code=PipelineErrorCode.INVALID_ENVELOPE,
            parser_code=None,
            detail="top-level Hyperliquid message must be a string-keyed object",
        )
    message = cast(dict[str, object], decoded)
    channel = message.get("channel")
    if not isinstance(channel, str):
        return _frame_error(
            frame,
            parser_name=_HL_DISPATCHER,
            channel_or_stream=frame.metadata.channel_hint,
            code=PipelineErrorCode.INVALID_ENVELOPE,
            parser_code=None,
            detail="top-level Hyperliquid channel must be a string",
        )

    if channel in {"l2Book", "bbo"}:
        result = normalize_book_frame(frame, registry)
        if result.status is BookNormalizationStatus.EVENT:
            assert result.event is not None
            return _frame_events(frame, HL_BOOK_PARSE_VERSION, channel, (result.event,))
        if result.status is BookNormalizationStatus.ERROR:
            assert result.error is not None
            return _parser_error(
                frame,
                HL_BOOK_PARSE_VERSION,
                channel,
                result.error.code.value,
                result.error.detail,
            )
        return _frame_not_applicable(frame, HL_BOOK_PARSE_VERSION, channel)

    if channel == "trades":
        result = normalize_trade_frame(frame, registry)
        if result.status is TradeNormalizationStatus.EVENTS:
            if result.events:
                return _frame_events(frame, HL_TRADE_PARSE_VERSION, channel, result.events)
            return _frame_empty(frame, HL_TRADE_PARSE_VERSION, channel)
        if result.status is TradeNormalizationStatus.ERROR:
            assert result.error is not None
            return _parser_error(
                frame,
                HL_TRADE_PARSE_VERSION,
                channel,
                result.error.code.value,
                result.error.detail,
            )
        return _frame_not_applicable(frame, HL_TRADE_PARSE_VERSION, channel)

    if channel == "activeAssetCtx":
        result = normalize_context_frame(frame, registry)
        if result.status is ContextNormalizationStatus.EVENTS:
            if result.events:
                return _frame_events(frame, HL_CONTEXT_PARSE_VERSION, channel, result.events)
            return _frame_empty(frame, HL_CONTEXT_PARSE_VERSION, channel)
        if result.status is ContextNormalizationStatus.ERROR:
            assert result.error is not None
            return _parser_error(
                frame,
                HL_CONTEXT_PARSE_VERSION,
                channel,
                result.error.code.value,
                result.error.detail,
            )
        return _frame_not_applicable(frame, HL_CONTEXT_PARSE_VERSION, channel)

    return _frame_not_applicable(frame, _HL_DISPATCHER, channel)


def _normalize_binance(
    frame: RawFrame,
    registry: InstrumentRegistry,
) -> FrameResult:
    result = normalize_binance_reference_frame(frame, registry)
    if result.status is BinanceReferenceNormalizationStatus.EVENT:
        assert result.event is not None
        return _frame_events(
            frame,
            BINANCE_PARSE_VERSION,
            result.stream,
            (result.event,),
        )
    if result.status is BinanceReferenceNormalizationStatus.ERROR:
        assert result.error is not None
        return _parser_error(
            frame,
            BINANCE_PARSE_VERSION,
            result.stream,
            result.error.code.value,
            result.error.detail,
        )
    return _frame_not_applicable(frame, BINANCE_PARSE_VERSION, result.stream)


def _frame_events(
    frame: RawFrame,
    parser_name: str,
    channel_or_stream: str | None,
    events: tuple[NormalizedEvent, ...],
) -> FrameResult:
    return _frame_result(
        frame,
        FrameOutcome.EVENTS,
        parser_name,
        channel_or_stream,
        events,
        None,
    )


def _frame_empty(
    frame: RawFrame,
    parser_name: str,
    channel_or_stream: str | None,
) -> FrameResult:
    return _frame_result(
        frame,
        FrameOutcome.EMPTY,
        parser_name,
        channel_or_stream,
        (),
        None,
    )


def _frame_not_applicable(
    frame: RawFrame,
    parser_name: str,
    channel_or_stream: str | None,
) -> FrameResult:
    return _frame_result(
        frame,
        FrameOutcome.NOT_APPLICABLE,
        parser_name,
        channel_or_stream,
        (),
        None,
    )


def _parser_error(
    frame: RawFrame,
    parser_name: str,
    channel_or_stream: str | None,
    parser_code: str,
    detail: str,
) -> FrameResult:
    return _frame_error(
        frame,
        parser_name=parser_name,
        channel_or_stream=channel_or_stream,
        code=PipelineErrorCode.PARSER_ERROR,
        parser_code=parser_code,
        detail=detail,
    )


def _frame_error(
    frame: RawFrame,
    *,
    parser_name: str,
    channel_or_stream: str | None,
    code: PipelineErrorCode,
    parser_code: str | None,
    detail: str,
) -> FrameResult:
    error = PipelineError(
        code=code,
        parser_name=parser_name,
        parser_code=parser_code,
        detail=detail,
        raw_segment_id=frame.ref.segment_id,
        raw_offset=frame.ref.offset,
        raw_sha256=frame.ref.payload_sha256,
    )
    return _frame_result(
        frame,
        FrameOutcome.ERROR,
        parser_name,
        channel_or_stream,
        (),
        error,
    )


def _frame_result(
    frame: RawFrame,
    outcome: FrameOutcome,
    parser_name: str,
    channel_or_stream: str | None,
    events: tuple[NormalizedEvent, ...],
    error: PipelineError | None,
) -> FrameResult:
    return FrameResult(
        outcome=outcome,
        source_id=frame.metadata.source_id,
        host_id=frame.metadata.host_id,
        boot_id=frame.metadata.boot_id,
        recv_wall_ns=frame.metadata.recv_wall_ns,
        recv_mono_ns=frame.metadata.recv_mono_ns,
        connection_id=frame.metadata.connection_id,
        ingest_seq=frame.metadata.ingest_seq,
        raw_segment_id=frame.ref.segment_id,
        raw_offset=frame.ref.offset,
        raw_sha256=frame.ref.payload_sha256,
        parser_name=parser_name,
        channel_or_stream=channel_or_stream,
        events=events,
        error=error,
    )


def _records_from_results(
    results: Iterable[FrameResult],
) -> tuple[CausalRecord, ...]:
    records: list[CausalRecord] = []
    for result in results:
        for ordinal, event in enumerate(result.events):
            records.append(
                CausalRecord(
                    host_id=result.host_id,
                    boot_id=result.boot_id,
                    recv_mono_ns=result.recv_mono_ns,
                    recv_wall_ns=result.recv_wall_ns,
                    source_id=result.source_id,
                    raw_segment_id=result.raw_segment_id,
                    raw_offset=result.raw_offset,
                    event_ordinal=ordinal,
                    event=event,
                )
            )
    return tuple(records)


def _domain_range(
    domain: tuple[str, str],
    results: list[FrameResult],
) -> CausalDomainRange:
    ordered = sorted(
        results,
        key=lambda result: (
            result.recv_mono_ns,
            result.recv_wall_ns,
            result.source_id,
            result.raw_segment_id,
            result.raw_offset,
        ),
    )
    first = ordered[0]
    last = ordered[-1]
    return CausalDomainRange(
        host_id=domain[0],
        boot_id=domain[1],
        first_recv_wall_ns=first.recv_wall_ns,
        last_recv_wall_ns=last.recv_wall_ns,
        first_recv_mono_ns=first.recv_mono_ns,
        last_recv_mono_ns=last.recv_mono_ns,
    )


def _clock_order_anomalies(results: list[FrameResult]) -> int:
    ordered = sorted(
        results,
        key=lambda result: (
            result.recv_mono_ns,
            result.recv_wall_ns,
            result.source_id,
            result.raw_segment_id,
            result.raw_offset,
        ),
    )
    anomalies = 0
    for previous, current in zip(ordered, ordered[1:], strict=False):
        if (
            current.recv_mono_ns > previous.recv_mono_ns
            and current.recv_wall_ns < previous.recv_wall_ns
        ):
            anomalies += 1
    return anomalies


def _duplicate_trade_ids(records: tuple[CausalRecord, ...]) -> int:
    counts: Counter[tuple[str, str, str]] = Counter()
    for record in records:
        event = record.event
        if isinstance(event, Trade | ReferenceTrade) and event.trade_id is not None:
            counts[
                (
                    record.source_id,
                    event.envelope.event_type.value,
                    event.trade_id,
                )
            ] += 1
    return sum(max(0, count - 1) for count in counts.values())


def _serialize_event(event: NormalizedEvent) -> bytes:
    if isinstance(event, L2Snapshot | BBO):
        return serialize_normalized_book_event(event)
    if isinstance(event, Trade):
        return serialize_normalized_trades((event,))
    if isinstance(event, FundingRateObservation | MarkPrice | OraclePrice):
        return serialize_normalized_context((event,))
    return serialize_binance_reference_event(event)


def _validate_provenance(frame: RawFrame) -> str | None:
    if not frame.ref.segment_id.strip():
        return "raw segment_id must be non-empty"
    if frame.ref.offset < 0:
        return "raw offset must be non-negative"
    actual_sha = hashlib.sha256(frame.payload).hexdigest()
    if actual_sha != frame.ref.payload_sha256:
        return "raw payload SHA-256 does not match payload bytes"
    return None


def _error_count_key(error: PipelineError) -> str:
    if error.code is not PipelineErrorCode.PARSER_ERROR:
        return error.code.value
    assert error.parser_code is not None
    return f"{error.code.value}:{error.parser_name}:{error.parser_code}"
