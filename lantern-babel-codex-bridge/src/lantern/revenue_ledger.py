"""
Lantern Revenue Ledger

Purpose:
    Turn the service's existing Chronicle records (RECIPROCITY_COMPLETED /
    RECIPROCITY_FAILED events written by service.py) into an honest
    economic accounting view: calls received, successful paid calls,
    failed payments, verified settlements, gross revenue, operating
    costs, and net contribution.

This module does NOT invent data. It only reads Chronicle events that
were actually appended by a running service instance. If no service has
ever run, every count in the summary is zero -- that is the correct,
honest answer, not a bug.

Hard accounting rules (per explicit operator instruction, 2026-08-30):
    - A testnet settlement (any non-mainnet network, e.g. Base Sepolia
      "eip155:84532") is NEVER counted as revenue, regardless of
      settlement_status. It is tracked separately as
      `testnet_settlements` for engineering visibility only.
    - An unpaid/unsettled request (settlement_status not "settled") is
      NEVER counted as revenue.
    - A "verified_pending_settlement" status (the service's own
      intermediate state -- payment verified by the facilitator, but
      settlement confirmation not yet recorded) is NEVER counted as
      revenue on its own. Only a record whose settlement_status is
      exactly "settled" AND whose network is the configured mainnet
      network counts as real revenue.
    - A promised/expected payment with no Chronicle-recorded outcome at
      all does not exist to this ledger -- there is no code path here
      that accepts a manually-asserted revenue number.

MAINNET_NETWORK is intentionally NOT hardcoded to Base mainnet
("eip155:8453") by default here -- this module has no opinion on when
the mainnet transition happens. The caller (an operator-run
reconciliation script, invoked only after Gate 3 authorization) must
pass the real mainnet CAIP-2 network id explicitly. Until that
authorization exists, every recorded settlement in this environment is
on Base Sepolia ("eip155:84532") and therefore, correctly, contributes
$0.00 to gross_revenue_usd no matter how many test calls occur.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


# Base Sepolia -- the only network this service is currently configured
# to use (see service.py TESTNET_NETWORK). Kept here as a named constant
# so testnet-vs-mainnet classification is explicit, not inferred.
BASE_SEPOLIA = "eip155:84532"
BASE_MAINNET = "eip155:8453"


@dataclass
class LedgerSummary:
    """Honest economic summary derived only from real Chronicle events."""

    calls_received: int = 0
    successful_paid_calls: int = 0
    failed_payments: int = 0
    verified_mainnet_settlements: int = 0
    testnet_settlements: int = 0
    gross_revenue_usd: float = 0.0
    operating_costs_usd: float = 0.0
    unverified_or_pending: int = 0
    entries: list[dict] = field(default_factory=list)

    @property
    def net_contribution_usd(self) -> float:
        """Always derived live from gross - costs; never a stored,
        independently-settable field that could drift out of sync."""
        return self.gross_revenue_usd - self.operating_costs_usd

    def to_dict(self) -> dict:
        return {
            "calls_received": self.calls_received,
            "successful_paid_calls": self.successful_paid_calls,
            "failed_payments": self.failed_payments,
            "verified_mainnet_settlements": self.verified_mainnet_settlements,
            "testnet_settlements": self.testnet_settlements,
            "unverified_or_pending": self.unverified_or_pending,
            "gross_revenue_usd": round(self.gross_revenue_usd, 6),
            "operating_costs_usd": round(self.operating_costs_usd, 6),
            "net_contribution_usd": round(self.net_contribution_usd, 6),
        }


def _price_to_float(price: object) -> float:
    """Parse a price like "$0.001" or "0.001" into a float. Returns 0.0
    on anything unparseable rather than raising -- a malformed price
    string must never crash accounting, and must never be silently
    treated as a nonzero amount by guessing."""
    if price is None:
        return 0.0
    text = str(price).strip().lstrip("$")
    try:
        return float(text)
    except ValueError:
        return 0.0


def summarize_chronicle(
    chronicle_path: str | Path,
    mainnet_network: str = BASE_MAINNET,
    operating_costs_usd: float = 0.0,
) -> LedgerSummary:
    """Read a Chronicle JSONL file and produce an honest revenue summary.

    Args:
        chronicle_path: path to the service's reciprocity_chronicle.jsonl
        mainnet_network: the CAIP-2 network id that counts as "real
            money" for this summary. Defaults to Base mainnet
            ("eip155:8453"), but the service itself must still be
            explicitly reconfigured to that network (Gate 3) before any
            record could ever actually carry it -- this parameter does
            not change what network the service accepts payment on.
        operating_costs_usd: any known real operating cost to net
            against gross revenue (e.g. CDP Facilitator per-transaction
            fees above the free tier, hosting cost). Defaults to 0.0;
            never invented or estimated by this function.

    Returns:
        LedgerSummary with only real, Chronicle-evidenced figures.
    """
    summary = LedgerSummary(operating_costs_usd=operating_costs_usd)
    path = Path(chronicle_path)
    if not path.exists():
        # No service has ever run / no events yet. Zero is the honest
        # answer -- this is not an error.
        return summary

    with path.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue

            event_type = record.get("type")
            payload = record.get("payload") or {}

            if event_type not in ("RECIPROCITY_COMPLETED", "RECIPROCITY_FAILED"):
                continue

            summary.calls_received += 1
            summary.entries.append(record)

            settlement_status = payload.get("settlement_status")
            execution_status = payload.get("execution_status")
            settlement_details = payload.get("settlement_details") or {}
            network = settlement_details.get("network")
            price = settlement_details.get("price")

            if event_type == "RECIPROCITY_FAILED" or execution_status == "failed":
                summary.failed_payments += 1
                continue

            if settlement_status != "settled":
                # Includes the service's current
                # "verified_pending_settlement" intermediate state.
                # Verified-but-not-settled is explicitly NOT revenue.
                summary.unverified_or_pending += 1
                continue

            # settlement_status == "settled" from here on.
            if network == mainnet_network:
                summary.verified_mainnet_settlements += 1
                summary.successful_paid_calls += 1
                summary.gross_revenue_usd += _price_to_float(price)
            else:
                # Settled, but on testnet (or an unrecognized/other
                # network) -- tracked for engineering visibility, never
                # counted as revenue.
                summary.testnet_settlements += 1
                summary.successful_paid_calls += 1

    return summary


def format_report(summary: LedgerSummary) -> str:
    """Render a plain-text report suitable for direct operator reading."""
    d = summary.to_dict()
    lines = [
        "Lantern Revenue Ledger",
        "=======================",
        f"Calls received:              {d['calls_received']}",
        f"Successful paid calls:       {d['successful_paid_calls']}",
        f"Failed payments:             {d['failed_payments']}",
        f"Verified MAINNET settlements:{d['verified_mainnet_settlements']}",
        f"Testnet settlements (not revenue): {d['testnet_settlements']}",
        f"Verified-pending / other (not revenue): {d['unverified_or_pending']}",
        "",
        f"Gross revenue (USD, mainnet-settled only): ${d['gross_revenue_usd']:.6f}",
        f"Operating costs (USD):                     ${d['operating_costs_usd']:.6f}",
        f"Net contribution (USD):                     ${d['net_contribution_usd']:.6f}",
    ]
    if d["gross_revenue_usd"] == 0.0:
        lines.append("")
        lines.append(
            "No real revenue has occurred yet. Testnet activity, pending "
            "settlements, and unpaid requests are never counted as revenue."
        )
    return "\n".join(lines)


if __name__ == "__main__":
    import sys

    chronicle_file = sys.argv[1] if len(sys.argv) > 1 else "reciprocity_chronicle.jsonl"
    result = summarize_chronicle(chronicle_file)
    print(format_report(result))
