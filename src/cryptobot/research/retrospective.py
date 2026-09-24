from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from urllib.request import urlretrieve

RETROSPECTIVE_SCHEMA_VERSION = 1
GATE_ELIGIBILITY = "EXCLUDED_FROM_TASK_018_FRONTIER_GATE"
_BINANCE_BASE = "https://data.binance.vision/data/futures/um/daily/aggTrades"
_HYPERLIQUID_BUCKET = "s3://hyperliquid-archive/market_data"
_BINANCE_SYMBOLS = ("BTCUSDT", "ETHUSDT")
_HYPERLIQUID_COINS = ("BTC", "ETH")

type RetrieveFn = Callable[[str, str], object]


class RetrospectiveDataError(ValueError):
    """Raised when retrospective archive evidence is invalid or unsafe."""


@dataclass(frozen=True, slots=True)
class ArchiveSpec:
    provider: str
    dataset: str
    symbol: str
    day: str
    location: str
    checksum_location: str | None
    access: str
    compression: str
    task_018_gate_eligibility: str = GATE_ELIGIBILITY

    def as_dict(self) -> dict[str, object]:
        return {
            "provider": self.provider,
            "dataset": self.dataset,
            "symbol": self.symbol,
            "day": self.day,
            "location": self.location,
            "checksum_location": self.checksum_location,
            "access": self.access,
            "compression": self.compression,
            "task_018_gate_eligibility": self.task_018_gate_eligibility,
        }


@dataclass(frozen=True, slots=True)
class DownloadedArchive:
    archive_path: Path
    checksum_path: Path
    manifest_path: Path
    sha256: str


def binance_usdm_daily_aggtrades_spec(day: date, symbol: str) -> ArchiveSpec:
    normalized = symbol.upper()
    if normalized not in _BINANCE_SYMBOLS:
        raise RetrospectiveDataError("Binance retrospective symbol must be BTCUSDT or ETHUSDT")
    stamp = day.isoformat()
    filename = f"{normalized}-aggTrades-{stamp}.zip"
    location = f"{_BINANCE_BASE}/{normalized}/{filename}"
    return ArchiveSpec(
        provider="BINANCE_DATA_VISION",
        dataset="USD_M_DAILY_AGGTRADES",
        symbol=normalized,
        day=stamp,
        location=location,
        checksum_location=f"{location}.CHECKSUM",
        access="PUBLIC_HTTPS_NO_AUTH",
        compression="ZIP",
    )


def hyperliquid_hourly_l2book_spec(day: date, hour: int, coin: str) -> ArchiveSpec:
    normalized = coin.upper()
    if normalized not in _HYPERLIQUID_COINS:
        raise RetrospectiveDataError("Hyperliquid retrospective coin must be BTC or ETH")
    if hour < 0 or hour > 23:
        raise RetrospectiveDataError("Hyperliquid archive hour must be in 0..23")
    stamp = day.strftime("%Y%m%d")
    return ArchiveSpec(
        provider="HYPERLIQUID_ARCHIVE",
        dataset="HOURLY_L2BOOK",
        symbol=normalized,
        day=day.isoformat(),
        location=f"{_HYPERLIQUID_BUCKET}/{stamp}/{hour}/l2Book/{normalized}.lz4",
        checksum_location=None,
        access="AWS_S3_REQUESTER_PAYS",
        compression="LZ4",
    )


def build_retrospective_plan(start: date, end: date) -> dict[str, object]:
    if end < start:
        raise RetrospectiveDataError("end date must be on or after start date")
    specs: list[ArchiveSpec] = []
    current = start
    while current <= end:
        for symbol in _BINANCE_SYMBOLS:
            specs.append(binance_usdm_daily_aggtrades_spec(current, symbol))
        for hour in range(24):
            for coin in _HYPERLIQUID_COINS:
                specs.append(hyperliquid_hourly_l2book_spec(current, hour, coin))
        current += timedelta(days=1)
    return {
        "schema_version": RETROSPECTIVE_SCHEMA_VERSION,
        "purpose": "AUXILIARY_RETROSPECTIVE_RESEARCH_ONLY",
        "task_018_gate_eligibility": GATE_ELIGIBILITY,
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "sources": [spec.as_dict() for spec in specs],
    }


def serialize_retrospective_plan(plan: dict[str, object]) -> bytes:
    return (
        json.dumps(plan, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n"
    ).encode()


def write_retrospective_plan(path: str | Path, start: date, end: date) -> Path:
    destination = Path(path)
    _reject_campaign_destination(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    payload = serialize_retrospective_plan(build_retrospective_plan(start, end))
    _write_new(destination, payload)
    return destination


def download_binance_archive(
    spec: ArchiveSpec,
    destination_root: str | Path,
    *,
    retrieve: RetrieveFn = urlretrieve,
) -> DownloadedArchive:
    if spec.provider != "BINANCE_DATA_VISION" or spec.checksum_location is None:
        raise RetrospectiveDataError("only Binance Data Vision archives can be downloaded here")
    root = Path(destination_root)
    _reject_campaign_destination(root)
    target_dir = root / "binance" / spec.dataset.lower() / spec.symbol / spec.day
    target_dir.mkdir(parents=True, exist_ok=True)

    filename = spec.location.rsplit("/", 1)[-1]
    archive_path = target_dir / filename
    checksum_path = target_dir / f"{filename}.CHECKSUM"
    manifest_path = target_dir / f"{filename}.manifest.json"
    for path in (archive_path, checksum_path, manifest_path):
        if path.exists():
            raise FileExistsError(f"refusing to overwrite retrospective evidence: {path}")

    archive_tmp = archive_path.with_suffix(archive_path.suffix + ".partial")
    checksum_tmp = checksum_path.with_suffix(checksum_path.suffix + ".partial")
    try:
        retrieve(spec.location, str(archive_tmp))
        retrieve(spec.checksum_location, str(checksum_tmp))
        expected = _parse_checksum(checksum_tmp.read_text(encoding="utf-8"))
        actual = _sha256_file(archive_tmp)
        if actual != expected:
            raise RetrospectiveDataError(
                f"Binance archive checksum mismatch: expected={expected} actual={actual}"
            )
        os.rename(archive_tmp, archive_path)
        os.rename(checksum_tmp, checksum_path)
        manifest = {
            "schema_version": RETROSPECTIVE_SCHEMA_VERSION,
            "purpose": "AUXILIARY_RETROSPECTIVE_RESEARCH_ONLY",
            "task_018_gate_eligibility": GATE_ELIGIBILITY,
            "source": spec.as_dict(),
            "archive_sha256": actual,
            "archive_filename": archive_path.name,
            "checksum_filename": checksum_path.name,
        }
        _write_new(manifest_path, serialize_retrospective_plan(manifest))
    except BaseException:
        archive_tmp.unlink(missing_ok=True)
        checksum_tmp.unlink(missing_ok=True)
        raise

    return DownloadedArchive(
        archive_path=archive_path,
        checksum_path=checksum_path,
        manifest_path=manifest_path,
        sha256=actual,
    )


def hyperliquid_requester_pays_commands(
    specs: Iterable[ArchiveSpec],
    destination_root: str | Path,
) -> tuple[tuple[str, ...], ...]:
    root = Path(destination_root)
    _reject_campaign_destination(root)
    commands = []
    for spec in specs:
        if spec.provider != "HYPERLIQUID_ARCHIVE":
            continue
        hour = spec.location.split("/")[-3]
        filename = f"{spec.day}-{hour}-{spec.symbol}.lz4"
        destination = root / "hyperliquid" / "l2book" / filename
        commands.append(
            (
                "aws",
                "s3",
                "cp",
                spec.location,
                str(destination),
                "--request-payer",
                "requester",
            )
        )
    return tuple(commands)


def _parse_checksum(raw: str) -> str:
    token = raw.strip().split(maxsplit=1)[0].lower() if raw.strip() else ""
    if len(token) != 64 or any(char not in "0123456789abcdef" for char in token):
        raise RetrospectiveDataError("checksum file does not start with a SHA-256 digest")
    return token


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _reject_campaign_destination(path: Path) -> None:
    if "frontier-campaign" in path.parts:
        raise RetrospectiveDataError(
            "retrospective data must not be stored inside the TASK-018 campaign root"
        )


def _write_new(path: Path, payload: bytes) -> None:
    try:
        with path.open("xb") as stream:
            stream.write(payload)
            stream.flush()
    except FileExistsError as exc:
        raise FileExistsError(f"refusing to overwrite retrospective evidence: {path}") from exc
