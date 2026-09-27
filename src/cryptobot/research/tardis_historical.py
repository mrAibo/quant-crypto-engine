from __future__ import annotations

import gzip
import hashlib
import json
import os
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import cast
from urllib.request import Request, urlopen

PROTOCOL_VERSION = "stage2-task028-tardis-historical-v1"
EVIDENCE_ROLE = "DEVELOPMENT_ONLY_EXTERNAL_RECEIVE_TIME"
FIRST_DAY = date(2024, 11, 1)
LAST_DAY = date(2026, 6, 1)
HYPERLIQUID_FASTBOOK_CUTOFF = date(2026, 6, 17)
FEE_SCENARIO_BPS_PER_SIDE = "4.5"
TASK025_REGISTRY_SHA256 = "d5024ce6cb16c0d3dcce5b65f3f62f6d577b971d3bda7c8342ab67aaa100b130"
TASK027_PROTOCOL_SHA256 = "1ab9a735f512dd301392ba568b49ebd0f1e80d676f073b3d502bf73d111bc1d3"
_TARDIS_BASE = "https://datasets.tardis.dev/v1"

BOOK5_HEADER = (
    "exchange,symbol,timestamp,local_timestamp,"
    "asks[0].price,asks[0].amount,bids[0].price,bids[0].amount,"
    "asks[1].price,asks[1].amount,bids[1].price,bids[1].amount,"
    "asks[2].price,asks[2].amount,bids[2].price,bids[2].amount,"
    "asks[3].price,asks[3].amount,bids[3].price,bids[3].amount,"
    "asks[4].price,asks[4].amount,bids[4].price,bids[4].amount"
)
TRADES_HEADER = "exchange,symbol,timestamp,local_timestamp,id,side,price,amount"
QUOTES_HEADER = (
    "exchange,symbol,timestamp,local_timestamp,ask_amount,ask_price,bid_price,bid_amount"
)

RetrieveFn = Callable[[str, Path], None]


class TardisHistoricalError(ValueError):
    """Raised when frozen TASK-028 historical evidence is invalid."""


@dataclass(frozen=True, slots=True)
class TardisArchiveSpec:
    exchange: str
    data_type: str
    symbol: str
    day: date
    expected_header: str

    @property
    def url(self) -> str:
        return (
            f"{_TARDIS_BASE}/{self.exchange}/{self.data_type}/"
            f"{self.day:%Y/%m/%d}/{self.symbol}.csv.gz"
        )

    @property
    def relative_path(self) -> Path:
        return Path(self.exchange) / self.data_type / self.day.isoformat() / f"{self.symbol}.csv.gz"

    def as_dict(self) -> dict[str, str]:
        return {
            "exchange": self.exchange,
            "data_type": self.data_type,
            "symbol": self.symbol,
            "day": self.day.isoformat(),
            "url": self.url,
        }


@dataclass(frozen=True, slots=True)
class DownloadedTardisArchive:
    archive_path: Path
    manifest_path: Path
    sha256: str
    size_bytes: int


def frozen_days() -> tuple[date, ...]:
    values: list[date] = []
    current = FIRST_DAY
    while current <= LAST_DAY:
        values.append(current)
        if current.month == 12:
            current = date(current.year + 1, 1, 1)
        else:
            current = date(current.year, current.month + 1, 1)
    return tuple(values)


def frozen_specs() -> tuple[TardisArchiveSpec, ...]:
    result: list[TardisArchiveSpec] = []
    for day in frozen_days():
        result.extend(
            (
                TardisArchiveSpec("hyperliquid", "book_snapshot_5", "BTC", day, BOOK5_HEADER),
                TardisArchiveSpec("hyperliquid", "trades", "BTC", day, TRADES_HEADER),
                TardisArchiveSpec("binance-futures", "quotes", "BTCUSDT", day, QUOTES_HEADER),
                TardisArchiveSpec("binance-futures", "trades", "BTCUSDT", day, TRADES_HEADER),
            )
        )
    return tuple(result)


def build_protocol() -> dict[str, object]:
    days = frozen_days()
    if not days or days[-1] >= HYPERLIQUID_FASTBOOK_CUTOFF:
        raise TardisHistoricalError(
            "frozen corpus must remain before fastBook normalization cutoff"
        )
    return {
        "schema_version": 1,
        "protocol_version": PROTOCOL_VERSION,
        "evidence_role": EVIDENCE_ROLE,
        "purpose": "PARALLEL_HISTORICAL_DEVELOPMENT_ONLY",
        "provider": "TARDIS_DEV",
        "access": "PUBLIC_FIRST_DAY_OF_MONTH_NO_API_KEY",
        "recording_location": {
            "hyperliquid": "GCP_ASIA_NORTHEAST1_TOKYO",
            "binance_futures": "GCP_ASIA_NORTHEAST1_TOKYO",
        },
        "time_semantics": {
            "primary_ordering_field": "local_timestamp",
            "units": "microseconds_since_unix_epoch_utc",
            "cross_venue_local_timestamp_comparison": "ALLOWED_SAME_TARDIS_REGION",
            "not_equivalent_to_aibo_receive_time": True,
        },
        "date_rule": "FIRST_UTC_DAY_OF_EACH_MONTH",
        "first_day": FIRST_DAY.isoformat(),
        "last_day": LAST_DAY.isoformat(),
        "day_count": len(days),
        "coverage_hours": len(days) * 24,
        "days": [value.isoformat() for value in days],
        "hyperliquid_normalized_book_source": "L2BOOK_PRE_FASTBOOK_CUTOFF_ONLY",
        "hyperliquid_fastbook_cutoff": HYPERLIQUID_FASTBOOK_CUTOFF.isoformat(),
        "source_templates": [
            {"exchange": "hyperliquid", "data_type": "book_snapshot_5", "symbol": "BTC"},
            {"exchange": "hyperliquid", "data_type": "trades", "symbol": "BTC"},
            {"exchange": "binance-futures", "data_type": "quotes", "symbol": "BTCUSDT"},
            {"exchange": "binance-futures", "data_type": "trades", "symbol": "BTCUSDT"},
        ],
        "expected_archive_count": len(frozen_specs()),
        "feature_family": "TASK025_EIGHT_FEATURE_MICROSTRUCTURE_V1_UNCHANGED",
        "horizons_seconds": [50, 300],
        "fee_scenario": {
            "bps_per_side": FEE_SCENARIO_BPS_PER_SIDE,
            "evidence_class": "SCENARIO",
        },
        "task025_registry_sha256": TASK025_REGISTRY_SHA256,
        "task027_protocol_sha256": TASK027_PROTOCOL_SHA256,
        "task027_relationship": "PARALLEL_DO_NOT_REPLACE_OR_STOP_PROSPECTIVE_CAPTURE",
        "old_confirmation": "UNOPENED_AND_EXCLUDED",
        "model_fitting_allowed_in_task028": False,
        "outcome_dependent_date_exclusion": False,
        "incident_and_gap_policy": "PRESERVE_AND_REPORT_DO_NOT_DROP_BY_OUTCOME",
        "cryptodatadownload_role": (
            "AUXILIARY_COARSE_CONTEXT_ONLY_NOT_ELIGIBLE_FOR_TASK025_EIGHT_FEATURE_ROWS"
        ),
    }


def protocol_bytes() -> bytes:
    return (
        json.dumps(build_protocol(), sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        + "\n"
    ).encode()


def protocol_sha256() -> str:
    return hashlib.sha256(protocol_bytes()).hexdigest()


def write_protocol(path: str | Path) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    _write_immutable(target, protocol_bytes())
    return target


def load_protocol(path: str | Path) -> dict[str, object]:
    target = Path(path)
    raw = target.read_bytes()
    try:
        value = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise TardisHistoricalError("TASK-028 protocol is not valid JSON") from exc
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise TardisHistoricalError("TASK-028 protocol root must be an object")
    protocol = cast(dict[str, object], value)
    if protocol != build_protocol():
        raise TardisHistoricalError("TASK-028 protocol differs from frozen implementation")
    return protocol


def download_archive(
    spec: TardisArchiveSpec,
    destination_root: str | Path,
    *,
    retrieve: RetrieveFn | None = None,
) -> DownloadedTardisArchive:
    root = Path(destination_root)
    _reject_campaign_destination(root)
    archive_path = root / spec.relative_path
    manifest_path = archive_path.with_suffix(archive_path.suffix + ".manifest.json")

    if archive_path.exists() or manifest_path.exists():
        return _load_existing(spec, archive_path, manifest_path)

    archive_path.parent.mkdir(parents=True, exist_ok=True)
    partial = archive_path.with_suffix(archive_path.suffix + ".partial")
    partial.unlink(missing_ok=True)
    try:
        (retrieve or _retrieve_http)(spec.url, partial)
        _validate_gzip_csv(partial, spec.expected_header)
        sha256 = _sha256_file(partial)
        size_bytes = partial.stat().st_size
        os.rename(partial, archive_path)
        manifest = {
            "schema_version": 1,
            "manifest_version": "stage2-task028-tardis-archive-v1",
            "protocol_sha256": protocol_sha256(),
            "evidence_role": EVIDENCE_ROLE,
            "source": spec.as_dict(),
            "archive_sha256": sha256,
            "archive_size_bytes": size_bytes,
            "gzip_crc_verified": True,
            "expected_csv_header": spec.expected_header,
            "old_confirmation_used": False,
            "task027_replaced": False,
        }
        _write_immutable(manifest_path, _json_bytes(manifest))
    except BaseException:
        partial.unlink(missing_ok=True)
        raise
    return DownloadedTardisArchive(
        archive_path=archive_path,
        manifest_path=manifest_path,
        sha256=sha256,
        size_bytes=size_bytes,
    )


def download_all(
    destination_root: str | Path,
    *,
    workers: int = 4,
) -> dict[str, object]:
    if isinstance(workers, bool) or not isinstance(workers, int) or not 1 <= workers <= 8:
        raise TardisHistoricalError("workers must be an integer in 1..8")
    specs = frozen_specs()
    with ThreadPoolExecutor(max_workers=workers) as pool:
        results = tuple(pool.map(lambda item: download_archive(item, destination_root), specs))
    return {
        "status": "SUCCESS",
        "protocol_sha256": protocol_sha256(),
        "expected_archive_count": len(specs),
        "downloaded_archive_count": len(results),
        "total_compressed_bytes": sum(item.size_bytes for item in results),
        "destination_root": str(Path(destination_root)),
        "evidence_role": EVIDENCE_ROLE,
    }


def historical_status(destination_root: str | Path) -> dict[str, object]:
    root = Path(destination_root)
    _reject_campaign_destination(root)
    verified = 0
    total_bytes = 0
    missing: list[str] = []
    for spec in frozen_specs():
        archive = root / spec.relative_path
        manifest = archive.with_suffix(archive.suffix + ".manifest.json")
        try:
            existing = _load_existing(spec, archive, manifest)
        except FileNotFoundError:
            missing.append(spec.relative_path.as_posix())
            continue
        verified += 1
        total_bytes += existing.size_bytes
    return {
        "schema_version": 1,
        "status_version": "stage2-task028-tardis-status-v1",
        "protocol_sha256": protocol_sha256(),
        "evidence_role": EVIDENCE_ROLE,
        "expected_archive_count": len(frozen_specs()),
        "verified_archive_count": verified,
        "missing_archive_count": len(missing),
        "total_compressed_bytes": total_bytes,
        "complete": verified == len(frozen_specs()),
        "missing_archives": missing,
    }


def build_corpus_manifest(destination_root: str | Path) -> dict[str, object]:
    root = Path(destination_root)
    _reject_campaign_destination(root)
    archives: list[dict[str, object]] = []
    total_bytes = 0
    for spec in frozen_specs():
        archive_path = root / spec.relative_path
        manifest_path = archive_path.with_suffix(archive_path.suffix + ".manifest.json")
        existing = _load_existing(spec, archive_path, manifest_path)
        total_bytes += existing.size_bytes
        archives.append(
            {
                "relative_path": spec.relative_path.as_posix(),
                "manifest_relative_path": manifest_path.relative_to(root).as_posix(),
                "archive_sha256": existing.sha256,
                "manifest_sha256": _sha256_file(manifest_path),
                "archive_size_bytes": existing.size_bytes,
                "source": spec.as_dict(),
            }
        )
    archive_set_bytes = _json_bytes({"archives": archives})
    return {
        "schema_version": 1,
        "report_version": "stage2-task028-tardis-corpus-v1",
        "protocol_sha256": protocol_sha256(),
        "evidence_role": EVIDENCE_ROLE,
        "complete": True,
        "archive_count": len(archives),
        "total_compressed_bytes": total_bytes,
        "archive_set_sha256": hashlib.sha256(archive_set_bytes).hexdigest(),
        "archives": archives,
        "economic_outcomes_consumed": False,
        "model_fitted": False,
        "old_confirmation_status": "UNOPENED_AND_EXCLUDED",
        "task027_replaced": False,
    }


def write_corpus_manifest(
    path: str | Path,
    destination_root: str | Path,
) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    _write_immutable(target, _json_bytes(build_corpus_manifest(destination_root)))
    return target


def _load_existing(
    spec: TardisArchiveSpec,
    archive_path: Path,
    manifest_path: Path,
) -> DownloadedTardisArchive:
    if not archive_path.is_file() or not manifest_path.is_file():
        raise FileNotFoundError(str(archive_path))
    try:
        manifest_value = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise TardisHistoricalError(f"invalid archive manifest: {manifest_path}") from exc
    if not isinstance(manifest_value, dict):
        raise TardisHistoricalError("archive manifest root must be an object")
    if manifest_value.get("protocol_sha256") != protocol_sha256():
        raise TardisHistoricalError("archive manifest protocol SHA mismatch")
    if manifest_value.get("source") != spec.as_dict():
        raise TardisHistoricalError("archive manifest source mismatch")
    expected_sha = manifest_value.get("archive_sha256")
    if not isinstance(expected_sha, str) or len(expected_sha) != 64:
        raise TardisHistoricalError("archive manifest SHA-256 is invalid")
    actual_sha = _sha256_file(archive_path)
    if actual_sha != expected_sha:
        raise TardisHistoricalError(f"archive SHA-256 mismatch: {archive_path}")
    _validate_gzip_csv(archive_path, spec.expected_header)
    size_bytes = archive_path.stat().st_size
    if manifest_value.get("archive_size_bytes") != size_bytes:
        raise TardisHistoricalError("archive manifest size mismatch")
    return DownloadedTardisArchive(archive_path, manifest_path, actual_sha, size_bytes)


def _retrieve_http(url: str, destination: Path) -> None:
    request = Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 quant-crypto-engine-task028",
            "Accept": "text/csv,application/gzip,*/*",
        },
    )
    try:
        with urlopen(request, timeout=120) as response, destination.open("xb") as output:
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                output.write(chunk)
            output.flush()
    except OSError as exc:
        raise TardisHistoricalError(f"cannot download Tardis archive: {url}") from exc


def _validate_gzip_csv(path: Path, expected_header: str) -> None:
    try:
        with gzip.open(path, "rt", encoding="utf-8", newline="") as stream:
            header = stream.readline().rstrip("\r\n")
            if header != expected_header:
                raise TardisHistoricalError(f"unexpected Tardis CSV schema: {path.name}")
            for _ in stream:
                pass
    except (OSError, UnicodeDecodeError, EOFError) as exc:
        raise TardisHistoricalError(f"invalid gzip CSV archive: {path}") from exc


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _reject_campaign_destination(path: Path) -> None:
    forbidden = {"frontier-campaign", "stage2-development-campaign"}
    if any(part in forbidden for part in path.parts):
        raise TardisHistoricalError(
            "TASK-028 historical evidence must not be stored inside prospective campaign roots"
        )


def _write_immutable(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("xb") as stream:
            stream.write(payload)
            stream.flush()
    except FileExistsError:
        if path.read_bytes() != payload:
            raise TardisHistoricalError(f"immutable TASK-028 file differs: {path}") from None


def _json_bytes(value: dict[str, object]) -> bytes:
    return (
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n"
    ).encode()
