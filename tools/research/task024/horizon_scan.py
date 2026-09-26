from __future__ import annotations

import csv
import hashlib
import json
from decimal import Decimal, getcontext
from pathlib import Path
from zipfile import ZipFile

getcontext().prec = 50
ROOT = Path("/var/lib/quant-crypto-engine/retrospective/binance/usd_m_daily_aggtrades")
OUT = Path("/var/lib/quant-crypto-engine/stage2/binance-development-horizon-1-2-5m-v1.json")
H = (60_000, 120_000, 300_000)
SYMS = ("BTCUSDT", "ETHUSDT")


def sha(p):
    h = hashlib.sha256()
    with p.open("rb") as f:
        for c in iter(lambda: f.read(1024 * 1024), b""):
            h.update(c)
    return h.hexdigest()


def nr(a, q):
    a = sorted(a)
    rank = (q * len(a) + 999) // 1000
    return a[rank - 1]


def analyze(sym, window):
    vals = []
    for daydir in sorted((ROOT / sym).iterdir()):
        z = next(daydir.glob("*.zip"))
        m = json.loads(next(daydir.glob("*.manifest.json")).read_text())
        assert sha(z) == m["archive_sha256"]
        bucket = None
        first = None
        last = None
        with ZipFile(z) as zz:
            name = zz.namelist()[0]
            with zz.open(name) as s:
                rd = csv.DictReader(line.decode() for line in s)
                for r in rd:
                    ts = int(r["transact_time"])
                    price = Decimal(r["price"])
                    b = ts // window
                    if bucket is None:
                        bucket = b
                        first = price
                        last = price
                    elif b == bucket:
                        last = price
                    else:
                        vals.append(abs(last - first) / first * Decimal(10000))
                        bucket = b
                        first = price
                        last = price
                if bucket is not None:
                    vals.append(abs(last - first) / first * Decimal(10000))
    return {
        "window_ms": window,
        "window_count": len(vals),
        "q50": str(nr(vals, 500)),
        "q75": str(nr(vals, 750)),
        "q90": str(nr(vals, 900)),
        "q95": str(nr(vals, 950)),
        "q97_5": str(nr(vals, 975)),
        "q99": str(nr(vals, 990)),
        "fraction_above_9bps": str(Decimal(sum(v > Decimal(9) for v in vals)) / Decimal(len(vals))),
        "fraction_above_12bps": str(
            Decimal(sum(v > Decimal(12) for v in vals)) / Decimal(len(vals))
        ),
    }


payload = {
    "schema_version": 1,
    "purpose": "TASK_023_DEVELOPMENT_ONLY_HORIZON_CONTEXT",
    "period": {"start": "2026-08-01", "end": "2026-08-07"},
    "horizons_seconds": [60, 120, 300],
    "limitations": [
        "Binance aggTrade price only",
        "not Hyperliquid executable BBO",
        "no receive-time semantics",
        "development only",
    ],
    "symbols": {sym: [analyze(sym, w) for w in H] for sym in SYMS},
}
raw = (json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n").encode()
OUT.write_bytes(raw)
print("SHA", hashlib.sha256(raw).hexdigest())
for s, arr in payload["symbols"].items():
    print(s)
    for x in arr:
        print(x)
