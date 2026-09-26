from __future__ import annotations

import hashlib
import json
from pathlib import Path

from cryptobot.data.instruments import InstrumentRole
from cryptobot.research.campaign_dataset import load_campaign_segment, release_unused_arrow_memory
from cryptobot.research.signal_campaign import (
    _discover_segment_roots,
    load_gate_dataset_source,
    load_segment_books,
)
from cryptobot.research.signal_dataset import build_signal_feature_rows
from cryptobot.research.signal_protocol import MAX_EXECUTION_STEP_NS
from cryptobot.research.signal_selection import CONFIRMATION_START_WALL_NS
from cryptobot.research.signal_selection_campaign import EXPECTED_GATE_REPORT_SHA256
from cryptobot.sim import QuoteObservation, build_fixed_horizon_opportunities

CAMPAIGN_ROOT = Path("/var/lib/quant-crypto-engine/frontier-campaign")
GATE_REPORT = (
    CAMPAIGN_ROOT
    / "campaign-reports"
    / "f82ba391ddaeac85ddb4787aec84d3cb85c17794101486c357cbb5bbd41f161c.json"
)
OUT = Path("/var/lib/quant-crypto-engine/stage2/economic-development-300s-v1.json")
HORIZON_NS = 300_000_000_000
instrument = "hyperliquid.mainnet.perpetual.btc"
reference = "binance_usdm.reference.perpetual.btcusdt"

source = load_gate_dataset_source(GATE_REPORT, expected_report_sha256=EXPECTED_GATE_REPORT_SHA256)
roots = _discover_segment_roots(CAMPAIGN_ROOT)
rows = []
used = []
skipped = 0
for sid in source.segment_ids:
    sr = roots[sid]
    ev = json.loads((sr / "segment-evidence.json").read_text())
    if ev["segment"]["wall_start_ns"] >= CONFIRMATION_START_WALL_NS:
        skipped += 1
        continue
    dsroot = sr / "dataset"
    verified = load_campaign_segment(dsroot, segment_id=sid)
    primary, ref = load_segment_books(
        dsroot,
        primary_instrument_id=instrument,
        reference_instrument_id=reference,
        max_recv_wall_ns_exclusive=CONFIRMATION_START_WALL_NS,
    )
    if not primary:
        skipped += 1
        continue
    quotes = tuple(
        QuoteObservation(
            event_id=x.event_id,
            source_id=x.source_id,
            instrument_id=x.instrument_id,
            role=InstrumentRole.PRIMARY,
            host_id=x.host_id,
            boot_id=x.boot_id,
            recv_mono_ns=x.recv_mono_ns,
            recv_wall_ns=x.recv_wall_ns,
            bid_price=x.bid_price,
            ask_price=x.ask_price,
            quality_flags=x.quality_flags,
        )
        for x in primary
    )
    opps = build_fixed_horizon_opportunities(
        quotes, horizon_ns=HORIZON_NS, max_step_ns=MAX_EXECUTION_STEP_NS
    )
    feat = build_signal_feature_rows(
        segment_id=sid,
        opportunities=opps,
        primary_books=primary,
        reference_books=ref,
        reference_instrument_id=reference,
    )
    for row in feat:
        if row.decision_recv_wall_ns >= CONFIRMATION_START_WALL_NS:
            continue
        opp = row.opportunity
        ex = opp.exit_quote
        rows.append(
            {
                "row_id": row.row_id,
                "source_segment_id": sid,
                "decision_recv_wall_ns": row.decision_recv_wall_ns,
                "opportunity_id": opp.opportunity_id,
                "invalid_reasons": list(opp.invalid_reasons()),
                "entry_bid": None
                if opp.entry_quote.bid_price is None
                else str(opp.entry_quote.bid_price),
                "entry_ask": None
                if opp.entry_quote.ask_price is None
                else str(opp.entry_quote.ask_price),
                "exit_bid": None if ex is None or ex.bid_price is None else str(ex.bid_price),
                "exit_ask": None if ex is None or ex.ask_price is None else str(ex.ask_price),
                "exit_recv_wall_ns": None if ex is None else ex.recv_wall_ns,
                "hl_spread_bps": None
                if row.hl_spread_bps.value is None
                else str(row.hl_spread_bps.value),
                "hl_bbo_imbalance": None
                if row.hl_bbo_imbalance.value is None
                else str(row.hl_bbo_imbalance.value),
                "binance_mid_return_5s_bps": None
                if row.binance_mid_return_5s_bps.value is None
                else str(row.binance_mid_return_5s_bps.value),
                "outcome_direction": row.outcome.direction,
                "outcome_signed_mid_return_bps": None
                if row.outcome.signed_mid_return_bps is None
                else str(row.outcome.signed_mid_return_bps),
                "outcome_invalid_reasons": list(row.outcome.invalid_reasons),
            }
        )
    used.append((sid, verified.data.evidence.dataset_bundle_sha256))
    del verified, primary, ref, quotes, opps, feat
    release_unused_arrow_memory()
rows = sorted(rows, key=lambda r: (r["decision_recv_wall_ns"], r["row_id"]))
payload = {
    "schema_version": 1,
    "purpose": "TASK_023_300S_DEVELOPMENT_ONLY",
    "horizon_ns": HORIZON_NS,
    "confirmation_cutoff_wall_ns": CONFIRMATION_START_WALL_NS,
    "source_gate_report_sha256": EXPECTED_GATE_REPORT_SHA256,
    "used_segment_count": len(used),
    "skipped_segment_count": skipped,
    "source_segment_digests": used,
    "row_count": len(rows),
    "rows": rows,
}
raw = (json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n").encode()
OUT.write_bytes(raw)
print(
    json.dumps(
        {
            "sha256": hashlib.sha256(raw).hexdigest(),
            "row_count": len(rows),
            "used_segments": len(used),
            "skipped": skipped,
            "first_wall": rows[0]["decision_recv_wall_ns"] if rows else None,
            "last_wall": rows[-1]["decision_recv_wall_ns"] if rows else None,
        },
        sort_keys=True,
    )
)
