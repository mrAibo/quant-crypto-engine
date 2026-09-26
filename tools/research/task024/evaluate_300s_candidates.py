from __future__ import annotations

import hashlib
import json
from decimal import Decimal, getcontext
from pathlib import Path

getcontext().prec = 60
CACHE = Path("/var/lib/quant-crypto-engine/stage2/economic-development-300s-v1.json")
REG = Path("/var/lib/quant-crypto-engine/stage2/economic-family-300s-development-registry-v1.json")
OUT = Path("/var/lib/quant-crypto-engine/stage2/economic-family-300s-development-results-v1.json")
FEE = Decimal("4.5")
BPS = Decimal(10000)
rows = sorted(
    json.loads(CACHE.read_text())["rows"], key=lambda r: (r["decision_recv_wall_ns"], r["row_id"])
)
reg = json.loads(REG.read_text())
split = int(len(rows) * Decimal("0.60"))
while (
    split < len(rows)
    and split > 0
    and rows[split]["decision_recv_wall_ns"] == rows[split - 1]["decision_recv_wall_ns"]
):
    split += 1
parts = {"DEV_A": rows[:split], "DEV_B": rows[split:], "ALL_EXPOSED": rows}


def s(x):
    return 1 if x > 0 else -1 if x < 0 else 0


def action(r, c):
    if r["hl_bbo_imbalance"] is None:
        return 0
    imb = Decimal(r["hl_bbo_imbalance"])
    if abs(imb) < Decimal(c["min_abs_imbalance"]):
        return 0
    bmin = c["min_abs_binance_5s_bps"]
    if bmin is not None or c["require_binance_sign_alignment"]:
        if r["binance_mid_return_5s_bps"] is None:
            return 0
        b = Decimal(r["binance_mid_return_5s_bps"])
        if bmin is not None and abs(b) < Decimal(bmin):
            return 0
        if c["require_binance_sign_alignment"] and (s(b) == 0 or s(b) != s(imb)):
            return 0
    return s(imb)


def net(r, a):
    if a == 0 or r["invalid_reasons"]:
        return None
    ks = ("entry_bid", "entry_ask", "exit_bid", "exit_ask")
    if any(r[k] is None for k in ks):
        return None
    eb, ea, xb, xa = [Decimal(r[k]) for k in ks]
    if a > 0:
        entry, exit, gross = ea, xb, xb - ea
    else:
        entry, exit, gross = eb, xa, eb - xa
    return gross - (entry + exit) * FEE / BPS


def med(v):
    if not v:
        return None
    q = sorted(v)
    n = len(q)
    return q[n // 2] if n % 2 else (q[n // 2 - 1] + q[n // 2]) / 2


def metric(part, c):
    selected = valid = pos = 0
    vals = []
    for r in part:
        a = action(r, c)
        if not a:
            continue
        selected += 1
        x = net(r, a)
        if x is None:
            continue
        valid += 1
        vals.append(x)
        pos += int(x > 0)
    return {
        "rows": len(part),
        "selected_count": selected,
        "valid_trade_count": valid,
        "positive_count": pos,
        "positive_rate": None if not valid else str(Decimal(pos) / Decimal(valid)),
        "mean_partial_known_cost_pnl": None
        if not vals
        else str(sum(vals, Decimal(0)) / Decimal(valid)),
        "median_partial_known_cost_pnl": None if not vals else str(med(vals)),
        "sum_partial_known_cost_pnl": None if not vals else str(sum(vals, Decimal(0))),
    }


benchmark = {
    "id": "BENCHMARK_H2_UNFILTERED_300S",
    "action": "SIGN_HL_BBO_IMBALANCE",
    "min_abs_imbalance": "0",
    "min_abs_binance_5s_bps": None,
    "require_binance_sign_alignment": False,
}
cands = [benchmark] + reg["deterministic_candidates"]
res = [{"candidate": c, "partitions": {n: metric(p, c) for n, p in parts.items()}} for c in cands]
payload = {
    "schema_version": 1,
    "cache_sha256": hashlib.sha256(CACHE.read_bytes()).hexdigest(),
    "registry_sha256": hashlib.sha256(REG.read_bytes()).hexdigest(),
    "split_index": split,
    "dev_a_rows": len(parts["DEV_A"]),
    "dev_b_rows": len(parts["DEV_B"]),
    "results": res,
}
raw = (json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n").encode()
OUT.write_bytes(raw)
print("SHA", hashlib.sha256(raw).hexdigest(), "split", len(parts["DEV_A"]), len(parts["DEV_B"]))
for x in res:
    print("\n", x["candidate"]["id"])
    print("A", x["partitions"]["DEV_A"])
    print("B", x["partitions"]["DEV_B"])
