"""Chain-level board verification: forks, duplicate seqs, gaps, re-anchors.

Synthetic chains exercise analyze_chain() directly, plus BoardClient
integration through verify_entry(). No network: entries are plain dicts in
the board's own shape. Signature/hash checks are NOT the subject here (they
are covered elsewhere); these tests pin the chain block's structure, the
known-anomalies classification rules, and the top-level status rule.
"""

from __future__ import annotations

import pytest

from lantern_harness.board.client import (
    CORROBORATED,
    FORK_ACKNOWLEDGED,
    REANCHOR,
    UNEXPLAINED,
    UNKNOWN,
    analyze_chain,
)
from lantern_harness.board.known_anomalies import KNOWN_ANOMALIES, table_hash


def _entry(h, seq, epoch, prev, msg=None, server_ms=None):
    return {"hash": h, "seq": seq, "epoch": epoch, "prev_hash": prev,
            "message_id": msg or f"m{seq}-{h[:4]}", "node_id": "test-node",
            "server_ms": server_ms or (1000 + seq)}


H = [f"{i:02d}" + "ab" * 31 for i in range(20)]  # distinct 64-hex-ish ids


def _linear(n=5):
    entries = []
    prev = "GENESIS"
    for i in range(1, n + 1):
        entries.append(_entry(H[i], i, 1, prev))
        prev = H[i]
    return entries


def test_clean_linear_chain_has_no_anomalies():
    chain = analyze_chain(_linear(5), known_anomalies=[])
    assert chain["head"] == {"entry_hash": H[5], "seq": 5, "epoch": 1,
                             "message_id": chain["head"]["message_id"]}
    assert chain["duplicate_seqs"] == []
    assert chain["seq_gaps"] == []
    assert chain["multi_child_parents"] == []
    assert chain["anomalies"] == []
    assert chain["unexplained_count"] == 0
    assert chain["epochs"] == [{"epoch": 1, "first_seq": 1, "last_seq": 5,
                                "anchor_entry_hash": "GENESIS", "record_count": 5}]


def _forked():
    """seq1..3 linear, then two children of H[3] at seq 4, seq 5 skipped,
    epoch 2 re-anchored at H[3] from seq 6."""
    entries = _linear(3)
    entries.append(_entry(H[4], 4, 1, H[3], msg="child-a", server_ms=2000))
    entries.append(_entry(H[5], 4, 1, H[3], msg="child-b", server_ms=2001))
    entries.append(_entry(H[6], 6, 2, H[3], msg="reanchor", server_ms=3000))
    entries.append(_entry(H[7], 7, 2, H[6], msg="repair-record", server_ms=3001))
    return entries


FORK_TABLE = [
    {"kind": "fork", "parent": H[3], "children": [H[4], H[5]],
     "duplicate_seqs": [4], "skipped_seqs": [5],
     "acknowledged_by": [H[7]]},
    {"kind": "reanchor", "parent": H[3], "child": H[6], "epoch": 2},
]


def test_acknowledged_fork_and_reanchor_classified_not_unexplained():
    chain = analyze_chain(_forked(), known_anomalies=FORK_TABLE)
    assert chain["duplicate_seqs"] == [{"seq": 4, "entry_hashes": [H[4], H[5]]}]
    assert chain["seq_gaps"] == [5]
    assert chain["multi_child_parents"] == [
        {"parent": H[3], "children": [H[4], H[5], H[6]]}]
    kinds = {(a["type"], a["classification"]) for a in chain["anomalies"]}
    assert ("multi_child_parent", FORK_ACKNOWLEDGED) in kinds
    assert ("multi_child_parent", REANCHOR) in kinds
    assert ("duplicate_seq", FORK_ACKNOWLEDGED) in kinds
    assert ("seq_gap", FORK_ACKNOWLEDGED) in kinds
    assert chain["unexplained_count"] == 0
    assert chain["known_anomalies_table_hash"] == table_hash(FORK_TABLE)


def test_fork_without_table_row_is_unexplained():
    chain = analyze_chain(_forked(), known_anomalies=[FORK_TABLE[1]])  # reanchor only
    unexplained = [a for a in chain["anomalies"] if a["classification"] == UNEXPLAINED]
    assert unexplained, "a fork with no validated row must be UNEXPLAINED"
    assert chain["unexplained_count"] >= 1


def test_fork_row_with_missing_acknowledgement_does_not_excuse():
    bad_table = [dict(FORK_TABLE[0], acknowledged_by=["ff" * 32]), FORK_TABLE[1]]
    chain = analyze_chain(_forked(), known_anomalies=bad_table)
    assert chain["unexplained_count"] >= 1, \
        "acknowledging records absent from the chain must not excuse the fork"


def test_reanchor_row_requires_real_epoch_increase():
    entries = _linear(3)
    entries.append(_entry(H[4], 4, 1, H[3], msg="same-epoch-child-a", server_ms=2000))
    entries.append(_entry(H[5], 5, 1, H[3], msg="same-epoch-child-b", server_ms=2001))
    table = [{"kind": "reanchor", "parent": H[3], "child": H[5], "epoch": 1}]
    chain = analyze_chain(entries, known_anomalies=table)
    # child epoch == parent epoch: row must not validate; anomaly stays
    assert chain["unexplained_count"] >= 1


def test_table_hash_is_stable_and_order_insensitive_to_formatting():
    assert table_hash(FORK_TABLE) == table_hash(list(FORK_TABLE))
    assert table_hash(FORK_TABLE) != table_hash(FORK_TABLE[:1])
    assert len(table_hash()) == 64
    assert table_hash() == table_hash(KNOWN_ANOMALIES)


def test_live_table_names_only_onchain_shape_rows():
    kinds = {r["kind"] for r in KNOWN_ANOMALIES}
    assert kinds <= {"fork", "reanchor"}
    for r in KNOWN_ANOMALIES:
        for key in ("parent",):
            assert len(r[key]) == 64
        if r["kind"] == "fork":
            assert r["children"] and r["acknowledged_by"]
            for h in r["children"] + r["acknowledged_by"]:
                assert len(h) == 64


class _FakeTransportBoard:
    """BoardClient with the HTTP transport stubbed to serve fixed entries.
    action=verify (board self-attestation) is stubbed separately via
    `verify_response`; None means the board's analyze() is unreachable."""

    def __init__(self, entries, verify_response=None):
        from lantern_harness.board.client import BoardClient, BoardClientError
        self.client = BoardClient(endpoint="https://example.invalid/board",
                                  board="test-board")
        self.client._list_entries = lambda: [dict(e) for e in entries]

        def fake_call(payload):
            if payload.get("action") == "verify" and verify_response is not None:
                return dict(verify_response)
            raise BoardClientError("transport stubbed out in tests")

        self.client._call = fake_call


def test_verify_entry_whole_board_reports_chain_and_downgrades():
    fake = _FakeTransportBoard(_forked())
    # entries carry no signature material -> per-entry UNKNOWN/OBSERVED paths;
    # what this test pins is the chain block and the status downgrade.
    result = fake.client.verify_entry(known_anomalies=[])  # empty allowlist
    assert "chain" in result and "head" in result
    assert result["head"]["seq"] == 7 and result["head"]["epoch"] == 2
    assert result["chain"]["unexplained_count"] >= 1
    assert result["status"] not in (CORROBORATED,), \
        "unexplained anomalies must keep top-level status below CORROBORATED"
    assert result["per_entry_status"] is not None

    acknowledged = fake.client.verify_entry(known_anomalies=FORK_TABLE)
    assert acknowledged["chain"]["unexplained_count"] == 0
    # with a clean allowlist the top-level equals the per-entry status
    assert acknowledged["status"] == acknowledged["per_entry_status"]


def test_single_entry_verify_pins_head():
    fake = _FakeTransportBoard(_linear(4))
    result = fake.client.verify_entry(H[2])
    assert result["head"]["entry_hash"] == H[4]
    assert result["source"] == "https://example.invalid/board"
    assert result["retrieved_at_ms"] > 0


def test_board_analysis_unreachable_degrades_to_blocked_block():
    fake = _FakeTransportBoard(_linear(3))
    result = fake.client.verify_entry(known_anomalies=[])
    assert result["board_analysis"]["status"] == "BLOCKED"
    # independent verification still ran
    assert result["checked"] == 3 and result["head"] is not None


def _board_verify_response(latest_valid, first_break=None):
    return {"ok": True, "total": 5,
            "epochs": [
                {"epoch": 1, "posts": 3, "valid": True, "first_break": None,
                 "head": H[3], "anchor_valid": True},
                {"epoch": 2, "posts": 2, "valid": latest_valid,
                 "first_break": first_break, "head": H[5], "anchor_valid": True}],
            "authoritative_epoch": 2, "authoritative_head": H[5],
            "canonical_epoch": 1 if not latest_valid else 2,
            "canonical_head": H[3] if not latest_valid else H[5]}


def test_authoritative_unresolved_adopted_when_latest_epoch_forked():
    forked = _board_verify_response(
        latest_valid=False,
        first_break={"type": "fork", "at_parent": "p1",
                     "children": [{"post_id": "a"}, {"post_id": "b"}]})
    fake = _FakeTransportBoard(_linear(3), verify_response=forked)
    result = fake.client.verify_entry(known_anomalies=[])
    ba = result["board_analysis"]
    assert ba["authoritative_state"] == "AUTHORITATIVE_UNRESOLVED"
    assert ba["authoritative_head"] is None, \
        "never a head from an ambiguous lineage"
    assert ba["fork"]["type"] == "fork"
    assert ba["canonical_epoch"] == 1 and ba["canonical_head"] == H[3]
    # the verify result itself refuses to emit a single head
    assert result["head"] is None
    assert result["authoritative_state"] == "AUTHORITATIVE_UNRESOLVED"
    assert result["status"] not in (CORROBORATED,)


def test_authoritative_ok_when_latest_epoch_valid():
    fake = _FakeTransportBoard(_linear(3),
                               verify_response=_board_verify_response(latest_valid=True))
    result = fake.client.verify_entry(known_anomalies=[])
    ba = result["board_analysis"]
    assert ba["authoritative_state"] == "AUTHORITATIVE_OK"
    assert ba["authoritative_head"] == H[5]
    assert result["head"] is not None


def test_non_fork_break_keeps_existing_reporting():
    tampered = _board_verify_response(
        latest_valid=False, first_break={"type": "tamper", "post_id": "x"})
    fake = _FakeTransportBoard(_linear(3), verify_response=tampered)
    ba = fake.client.verify_entry(known_anomalies=[])["board_analysis"]
    assert ba["authoritative_state"] == "AUTHORITATIVE_OK"
    assert ba["authoritative_head"] == H[5]
