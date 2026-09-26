from __future__ import annotations

import hashlib
import json
import math
from decimal import Decimal, getcontext
from pathlib import Path

getcontext().prec = 60
CACHE = Path("/var/lib/quant-crypto-engine/stage2/economic-development-300s-v1.json")
REG = Path("/var/lib/quant-crypto-engine/stage2/economic-family-300s-development-registry-v1.json")
OUT = Path("/var/lib/quant-crypto-engine/stage2/economic-logistic-300s-development-results-v1.json")
FEE = Decimal("4.5")
BPS = Decimal(10000)
rows = sorted(
    json.loads(CACHE.read_text())["rows"], key=lambda r: (r["decision_recv_wall_ns"], r["row_id"])
)
split = int(len(rows) * 0.60)
while (
    split < len(rows)
    and split > 0
    and rows[split]["decision_recv_wall_ns"] == rows[split - 1]["decision_recv_wall_ns"]
):
    split += 1
A = rows[:split]
B = rows[split:]


def valid(r):
    return not r["invalid_reasons"] and all(
        r[k] is not None
        for k in (
            "entry_bid",
            "entry_ask",
            "exit_bid",
            "exit_ask",
            "hl_bbo_imbalance",
            "binance_mid_return_5s_bps",
        )
    )


def pnl(r, a):
    eb, ea, xb, xa = [Decimal(r[k]) for k in ("entry_bid", "entry_ask", "exit_bid", "exit_ask")]
    if a == 1:
        entry, exit, g = ea, xb, xb - ea
    else:
        entry, exit, g = eb, xa, eb - xa
    return g - (entry + exit) * FEE / BPS


def feat(r, a):
    im = float(Decimal(r["hl_bbo_imbalance"]))
    br = float(Decimal(r["binance_mid_return_5s_bps"]))
    return [a * im, abs(im), a * br, abs(br)]


train = []
for r in A:
    if not valid(r):
        continue
    for a in (1, -1):
        train.append((feat(r, a), 1.0 if pnl(r, a) > 0 else 0.0))
m = len(train)
k = 4
means = [sum(x[j] for x, y in train) / m for j in range(k)]
stds = []
for j in range(k):
    s = math.sqrt(sum((x[j] - means[j]) ** 2 for x, y in train) / m)
    stds.append(s or 1.0)


def z(x):
    return [(x[j] - means[j]) / stds[j] for j in range(k)]


w = [0.0] * 5
for _ in range(4000):
    g = [0.0] * 5
    for x, y in train:
        zz = z(x)
        eta = w[0] + sum(w[j + 1] * zz[j] for j in range(k))
        pr = 1 / (1 + math.exp(-max(-50, min(50, eta))))
        diff = pr - y
        g[0] += diff
        for j in range(k):
            g[j + 1] += diff * zz[j]
    g[0] /= m
    for j in range(k):
        g[j + 1] = g[j + 1] / m + w[j + 1] / m
    for j in range(5):
        w[j] -= 0.05 * g[j]


def prob(r, a):
    zz = z(feat(r, a))
    eta = w[0] + sum(w[j + 1] * zz[j] for j in range(k))
    return 1 / (1 + math.exp(-max(-50, min(50, eta))))


def score(part):
    o = []
    for r in part:
        if not valid(r):
            continue
        pl, ps = prob(r, 1), prob(r, -1)
        a = 1 if pl >= ps else -1
        o.append((max(pl, ps), a, pnl(r, a)))
    return o


sa, sb = score(A), score(B)


def q(vals, p):
    s = sorted(vals)
    x = (len(s) - 1) * p
    lo = int(x)
    hi = min(len(s) - 1, lo + 1)
    f = x - lo
    return s[lo] * (1 - f) + s[hi] * f


ths = {"LOGIT300_TOP10": q([x[0] for x in sa], 0.90), "LOGIT300_TOP05": q([x[0] for x in sa], 0.95)}


def met(sc, t):
    ch = [x for x in sc if x[0] >= t]
    v = [x[2] for x in ch]
    return {
        "eligible": len(sc),
        "valid_trade_count": len(v),
        "positive_count": sum(x > 0 for x in v),
        "mean_partial_known_cost_pnl": None if not v else str(sum(v, Decimal(0)) / Decimal(len(v))),
        "sum_partial_known_cost_pnl": None if not v else str(sum(v, Decimal(0))),
        "threshold": repr(t),
    }


payload = {
    "schema_version": 1,
    "cache_sha256": hashlib.sha256(CACHE.read_bytes()).hexdigest(),
    "registry_sha256": hashlib.sha256(REG.read_bytes()).hexdigest(),
    "dev_a_action_samples": m,
    "target_prevalence": repr(sum(y for x, y in train) / m),
    "means": [repr(x) for x in means],
    "stds": [repr(x) for x in stds],
    "coefficients": [repr(x) for x in w],
    "gates": {k: {"DEV_A": met(sa, t), "DEV_B": met(sb, t)} for k, t in ths.items()},
}
raw = (json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n").encode()
OUT.write_bytes(raw)
print(
    "SHA", hashlib.sha256(raw).hexdigest(), "train", m, "prev", payload["target_prevalence"], "w", w
)
for k, t in ths.items():
    print(k, "A", met(sa, t), "B", met(sb, t))
