"""
Tests for lantern.revenue_ledger.

These tests build real, on-disk Chronicle JSONL fixtures (using the
actual Chronicle class, not hand-typed JSON that might drift from the
real format) and verify the ledger's classification rules match the
operator's explicit accounting instructions:

    - Testnet settlements are NEVER counted as revenue.
    - Unpaid/failed requests are NEVER counted as revenue.
    - "verified_pending_settlement" (the service's own intermediate
      state) is NEVER counted as revenue.
    - Only settlement_status == "settled" AND network == mainnet counts.
    - No chronicle file at all -> all zeros, not an error.
"""

import json

import pytest

from lantern.core import Chronicle, KernelEvent
from lantern.revenue_ledger import (
    BASE_MAINNET,
    BASE_SEPOLIA,
    summarize_chronicle,
)


def _append_outcome(chronicle: Chronicle, *, event_type, settlement_status,
                     execution_status, network, price="$0.001", error=None):
    chronicle.append(
        KernelEvent(
            event_type=event_type,
            source="service",
            payload={
                "initiator": "203.0.113.5",
                "provider": "lantern-service",
                "capability": "belief_reconciliation",
                "settlement_type": "monetary",
                "settlement_details": {
                    "price": price,
                    "network": network,
                    "recipient": "0xD062a97d1Bc9D7CE42B2bD1E4BD7f9d3aa4E2683",
                },
                "settlement_status": settlement_status,
                "execution_status": execution_status,
                "result": {"summary": {"agreement": 1}} if execution_status == "executed" else None,
                "transaction_id": None,
                "error": error,
            },
        )
    )


def test_no_chronicle_file_means_all_zero(tmp_path):
    missing = tmp_path / "does_not_exist.jsonl"
    summary = summarize_chronicle(missing)
    d = summary.to_dict()
    assert d["calls_received"] == 0
    assert d["gross_revenue_usd"] == 0.0
    assert d["net_contribution_usd"] == 0.0


def test_testnet_settlement_never_counts_as_revenue(tmp_path):
    path = tmp_path / "chronicle.jsonl"
    chronicle = Chronicle(str(path))
    _append_outcome(
        chronicle,
        event_type="RECIPROCITY_COMPLETED",
        settlement_status="settled",
        execution_status="executed",
        network=BASE_SEPOLIA,
    )
    summary = summarize_chronicle(path)
    assert summary.calls_received == 1
    assert summary.testnet_settlements == 1
    assert summary.verified_mainnet_settlements == 0
    assert summary.gross_revenue_usd == 0.0


def test_verified_pending_settlement_is_not_revenue(tmp_path):
    """The service's own real intermediate state (payment verified by
    the facilitator, but settlement not yet confirmed) must not be
    counted as revenue even on a mainnet network -- 'verified' is not
    'settled'."""
    path = tmp_path / "chronicle.jsonl"
    chronicle = Chronicle(str(path))
    _append_outcome(
        chronicle,
        event_type="RECIPROCITY_COMPLETED",
        settlement_status="verified_pending_settlement",
        execution_status="executed",
        network=BASE_MAINNET,
    )
    summary = summarize_chronicle(path)
    assert summary.gross_revenue_usd == 0.0
    assert summary.verified_mainnet_settlements == 0
    assert summary.unverified_or_pending == 1


def test_failed_payment_never_counts_as_revenue(tmp_path):
    path = tmp_path / "chronicle.jsonl"
    chronicle = Chronicle(str(path))
    _append_outcome(
        chronicle,
        event_type="RECIPROCITY_FAILED",
        settlement_status="verified_pending_settlement",
        execution_status="failed",
        network=BASE_MAINNET,
        error="reconciliation failed: bad input",
    )
    summary = summarize_chronicle(path)
    assert summary.failed_payments == 1
    assert summary.gross_revenue_usd == 0.0
    assert summary.successful_paid_calls == 0


def test_settled_mainnet_payment_is_real_revenue(tmp_path):
    path = tmp_path / "chronicle.jsonl"
    chronicle = Chronicle(str(path))
    _append_outcome(
        chronicle,
        event_type="RECIPROCITY_COMPLETED",
        settlement_status="settled",
        execution_status="executed",
        network=BASE_MAINNET,
        price="$0.05",
    )
    summary = summarize_chronicle(path, mainnet_network=BASE_MAINNET)
    assert summary.verified_mainnet_settlements == 1
    assert summary.gross_revenue_usd == pytest.approx(0.05)
    assert summary.net_contribution_usd == pytest.approx(0.05)


def test_operating_costs_reduce_net_but_not_gross(tmp_path):
    path = tmp_path / "chronicle.jsonl"
    chronicle = Chronicle(str(path))
    _append_outcome(
        chronicle,
        event_type="RECIPROCITY_COMPLETED",
        settlement_status="settled",
        execution_status="executed",
        network=BASE_MAINNET,
        price="$1.00",
    )
    summary = summarize_chronicle(path, mainnet_network=BASE_MAINNET, operating_costs_usd=0.30)
    d = summary.to_dict()
    assert d["gross_revenue_usd"] == pytest.approx(1.00)
    assert d["operating_costs_usd"] == pytest.approx(0.30)
    assert d["net_contribution_usd"] == pytest.approx(0.70)


def test_mixed_ledger_classifies_each_entry_independently(tmp_path):
    """A realistic mixed history: some testnet noise, a failed payment,
    a verified-but-unsettled call, and exactly one real mainnet sale.
    Only the one real sale should count as revenue."""
    path = tmp_path / "chronicle.jsonl"
    chronicle = Chronicle(str(path))

    _append_outcome(chronicle, event_type="RECIPROCITY_COMPLETED",
                     settlement_status="settled", execution_status="executed",
                     network=BASE_SEPOLIA)
    _append_outcome(chronicle, event_type="RECIPROCITY_FAILED",
                     settlement_status="verified_pending_settlement",
                     execution_status="failed", network=BASE_MAINNET,
                     error="handler exception")
    _append_outcome(chronicle, event_type="RECIPROCITY_COMPLETED",
                     settlement_status="verified_pending_settlement",
                     execution_status="executed", network=BASE_MAINNET)
    _append_outcome(chronicle, event_type="RECIPROCITY_COMPLETED",
                     settlement_status="settled", execution_status="executed",
                     network=BASE_MAINNET, price="$0.25")

    summary = summarize_chronicle(path, mainnet_network=BASE_MAINNET)
    d = summary.to_dict()
    assert d["calls_received"] == 4
    assert d["testnet_settlements"] == 1
    assert d["failed_payments"] == 1
    assert d["unverified_or_pending"] == 1
    assert d["verified_mainnet_settlements"] == 1
    assert d["gross_revenue_usd"] == pytest.approx(0.25)


def test_malformed_lines_are_skipped_not_fatal(tmp_path):
    path = tmp_path / "chronicle.jsonl"
    path.write_text("not valid json at all\n\n", encoding="utf-8")
    summary = summarize_chronicle(path)
    assert summary.calls_received == 0


def test_unparseable_price_defaults_to_zero_not_fabricated(tmp_path):
    path = tmp_path / "chronicle.jsonl"
    chronicle = Chronicle(str(path))
    _append_outcome(
        chronicle,
        event_type="RECIPROCITY_COMPLETED",
        settlement_status="settled",
        execution_status="executed",
        network=BASE_MAINNET,
        price="not-a-number",
    )
    summary = summarize_chronicle(path, mainnet_network=BASE_MAINNET)
    assert summary.verified_mainnet_settlements == 1
    assert summary.gross_revenue_usd == 0.0
