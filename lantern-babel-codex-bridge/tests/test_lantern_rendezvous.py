"""Lantern Rendezvous / Join Monitor tests.

Locks in: a join request is an announcement, not authorization. It is
recorded in its own Chronicle (separate from the belief/evidence
Chronicle), never enters the EvidenceKernel, never mutates belief, never
grants a capability, and expires rather than sitting pending forever
without being deleted from the audit trail.
"""

import json
import threading
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from lantern.bootstrap_node import create_server
from lantern.compatibility import DEFAULT_CAPABILITIES
from lantern.core import Chronicle, Lantern
from lantern.rendezvous import AWAITING_HANDSHAKE, EXPIRED, JoinMonitor, JoinRequest


def _payload(request_id="req-1", node_id="external-test-07", **overrides):
    base = {
        "request_id": request_id,
        "node_id": node_id,
        "protocol_version": "0.82",
        "capabilities": {"evidence_exchange": True, "handshake": True},
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    base.update(overrides)
    return base


# ==================================================
# JoinMonitor unit behavior
# ==================================================

def test_valid_join_request_is_accepted_and_pending(tmp_path):
    monitor = JoinMonitor(tmp_path / "joins.jsonl")
    request, is_new, notification = monitor.submit(_payload())

    assert isinstance(request, JoinRequest)
    assert is_new is True
    assert request.status == AWAITING_HANDSHAKE
    assert notification is not None
    assert "external-test-07" in notification
    assert request.request_id in notification

    pending = monitor.pending()
    assert len(pending) == 1
    assert pending[0].request_id == request.request_id


def test_malformed_join_request_missing_fields_rejected(tmp_path):
    monitor = JoinMonitor(tmp_path / "joins.jsonl")

    with pytest.raises(ValueError, match="Missing join fields"):
        monitor.submit({"node_id": "x"})


def test_malformed_join_request_bad_capability_types_rejected(tmp_path):
    monitor = JoinMonitor(tmp_path / "joins.jsonl")

    with pytest.raises(ValueError, match="capabilities values must be boolean"):
        monitor.submit(_payload(capabilities={"evidence_exchange": "yes"}))


def test_malformed_join_request_bad_timestamp_rejected(tmp_path):
    monitor = JoinMonitor(tmp_path / "joins.jsonl")

    with pytest.raises(ValueError, match="timestamp"):
        monitor.submit(_payload(timestamp="not-a-timestamp"))


def test_duplicate_request_id_does_not_create_second_pending_entry(tmp_path):
    monitor = JoinMonitor(tmp_path / "joins.jsonl")
    first, first_is_new, _ = monitor.submit(_payload())
    second, second_is_new, notification = monitor.submit(_payload())

    assert first_is_new is True
    assert second_is_new is False
    assert notification is None
    assert first.request_id == second.request_id
    assert len(monitor.pending()) == 1

    events = [record["type"] for record in monitor.chronicle.replay()]
    assert events.count("JOIN_REQUESTED") == 1
    assert events.count("JOIN_DUPLICATE") == 1


def test_expired_request_becomes_expired_not_deleted(tmp_path):
    monitor = JoinMonitor(tmp_path / "joins.jsonl", ttl_seconds=1)
    old_timestamp = (datetime.now(timezone.utc) - timedelta(seconds=10)).isoformat()
    request, _, _ = monitor.submit(_payload(timestamp=old_timestamp))

    assert monitor.pending() == []
    all_requests = monitor.all_requests()
    assert len(all_requests) == 1
    assert all_requests[0].request_id == request.request_id
    assert all_requests[0].status == EXPIRED

    events = [record["type"] for record in monitor.chronicle.replay()]
    assert "JOIN_EXPIRED" in events
    assert "JOIN_REQUESTED" in events


def test_join_monitor_survives_restart_via_chronicle_replay(tmp_path):
    path = tmp_path / "joins.jsonl"
    first = JoinMonitor(path)
    first.submit(_payload())

    second = JoinMonitor(path)
    assert len(second.pending()) == 1
    assert second.pending()[0].node_id == "external-test-07"


def test_join_monitor_chronicle_is_independent_of_belief_chronicle(tmp_path):
    """The rendezvous Chronicle and the belief/evidence Chronicle must be
    two different files, so a join announcement structurally cannot end
    up inside the belief audit trail.
    """
    belief_chronicle = Chronicle(tmp_path / "lantern-b.jsonl")
    monitor = JoinMonitor(tmp_path / "lantern-b.joins.jsonl")
    monitor.submit(_payload())

    assert belief_chronicle.path != monitor.path
    assert list(belief_chronicle.replay()) == []


def test_join_request_never_enters_evidence_kernel(tmp_path):
    """A join announcement must never be observable as an Observation or
    Evidence inside a real Lantern kernel -- JoinMonitor has no reference
    to any Lantern/agent object at all.
    """
    lantern = Lantern()
    before_observations = len(lantern.kernel.observations)
    before_evidence = len(lantern.kernel.evidence)
    before_step = lantern.kernel.step

    monitor = JoinMonitor(tmp_path / "joins.jsonl")
    monitor.submit(_payload())

    assert len(lantern.kernel.observations) == before_observations
    assert len(lantern.kernel.evidence) == before_evidence
    assert lantern.kernel.step == before_step
    assert DEFAULT_CAPABILITIES["codex_update"] is False


def test_notification_text_matches_requested_format(tmp_path):
    monitor = JoinMonitor(tmp_path / "joins.jsonl")
    request, _, notification = monitor.submit(_payload())

    assert "LANTERN JOIN REQUEST" in notification
    assert f"Node: {request.node_id}" in notification
    assert f"Protocol: {request.protocol_version}" in notification
    assert f"Request: {request.request_id}" in notification
    assert "Status: awaiting_handshake" in notification


def test_health_reports_pending_count_without_details(tmp_path):
    monitor = JoinMonitor(tmp_path / "joins.jsonl")
    monitor.submit(_payload())
    monitor.submit(_payload(request_id="req-2", node_id="external-test-08"))

    health = monitor.health()
    assert health["pending"] == 2
    assert health["total"] == 2


def test_verify_persisted_confirms_a_real_write_via_independent_read(tmp_path):
    """submit() returning is only category D-candidate (a write call
    completed); verify_persisted() re-parses the Chronicle file from
    disk -- not self.requests -- so a True result is an independent
    read confirming the earlier write, satisfying Principle 2's
    action -> external result -> independent retrieval -> verification
    chain.
    """
    monitor = JoinMonitor(tmp_path / "joins.jsonl")
    request, is_new, _ = monitor.submit(_payload())

    assert is_new is True
    assert monitor.verify_persisted(request.request_id) is True


def test_verify_persisted_is_false_for_a_request_id_that_was_never_submitted(tmp_path):
    """A request_id that was never actually written must be reported as
    unverified, not assumed persisted just because it looks well-formed.
    """
    monitor = JoinMonitor(tmp_path / "joins.jsonl")
    monitor.submit(_payload())

    assert monitor.verify_persisted("never-submitted-id") is False


def test_verify_persisted_reads_the_file_not_the_in_memory_cache(tmp_path):
    """Even if the in-memory dict were wrong or stale, verify_persisted()
    must still answer from the on-disk Chronicle -- this is what makes
    it an independent retrieval rather than a restatement of the claim
    that was already made in-process.
    """
    path = tmp_path / "joins.jsonl"
    writer = JoinMonitor(path)
    request, _, _ = writer.submit(_payload())

    # A second, separate monitor instance never called submit() itself --
    # its own in-memory self.requests only exists because _rebuild()
    # replayed the file. verify_persisted() re-reads that same file
    # independently of whatever _rebuild() cached.
    reader = JoinMonitor(path)
    assert reader.verify_persisted(request.request_id) is True
    assert reader.verify_persisted("some-other-id-entirely") is False


# ==================================================
# HTTP wiring: POST /join, GET /health
# ==================================================

def _request(base, path, method="GET", payload=None):
    data = None if payload is None else json.dumps(payload).encode()
    req = Request(base + path, data=data, method=method, headers={"Content-Type": "application/json"})
    with urlopen(req, timeout=3) as response:
        return response.status, json.loads(response.read())


@pytest.fixture
def node(tmp_path):
    server = create_server("127.0.0.1", 0, "lantern-b", tmp_path / "b.jsonl")
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    yield base, server
    server.shutdown()
    server.server_close()
    thread.join(timeout=3)


def test_post_join_over_http_is_accepted_and_reported_in_health(node):
    base, server = node

    status, result = _request(base, "/join", "POST", _payload())
    assert status == 200
    assert result["accepted"] is True
    assert result["status"] == AWAITING_HANDSHAKE
    assert result["is_new"] is True
    assert result["persisted"] is True
    assert "not a trust or capability grant" in result["note"].lower()

    status, health = _request(base, "/health")
    assert status == 200
    assert health["rendezvous"]["pending"] == 1
    assert health["rendezvous"]["total"] == 1

    # A join announcement must never touch the belief/evidence kernel.
    assert len(server.node.lantern.kernel.observations) == 0
    assert len(server.node.lantern.kernel.evidence) == 0


def test_post_join_duplicate_over_http_does_not_double_count(node):
    base, server = node

    _request(base, "/join", "POST", _payload())
    status, result = _request(base, "/join", "POST", _payload())

    assert status == 200
    assert result["is_new"] is False

    status, health = _request(base, "/health")
    assert health["rendezvous"]["pending"] == 1


def test_post_join_malformed_over_http_returns_400(node):
    base, server = node

    with pytest.raises(HTTPError) as error:
        _request(base, "/join", "POST", {"node_id": "incomplete"})
    assert error.value.code == 400


def test_join_does_not_bypass_handshake_or_capability_gate(node):
    """Announcing via /join must have zero effect on what /message will
    accept -- the existing handshake and capability negotiation remain
    the only path to actually exchanging anything.

    Category C reason-string update (Phase 4 compatibility migration):
    this scenario sends no session_id, so the secure-default boundary
    now rejects it at the LEGACY_MODE_DISABLED check, before capability
    negotiation is even reached. The invariant under test -- that /join
    grants nothing toward accepting a message -- is not just preserved
    but strengthened: unauthenticated traffic is now rejected earlier
    and unconditionally, regardless of what capabilities it claims.
    """
    base, server = node

    status, join_result = _request(base, "/join", "POST", _payload())
    assert join_result["accepted"] is True

    # No capability was granted by the join alone: sending a message
    # without a verified session is still rejected exactly as before,
    # just at the (now earlier) legacy-mode boundary instead of the
    # capability-negotiation step.
    message = {
        "message_id": "m1",
        "protocol": "0.82",
        "message_type": "OBSERVATION_SHARE",
        "source": "external-test-07",
        "timestamp": "2026-01-01T00:00:00+00:00",
        "payload": {"observation": {"content": "trying to skip the handshake"}},
    }
    status, result = _request(
        base, "/message", "POST",
        {"message": message, "peer_capabilities": {}},
    )
    assert result["accepted"] is False
    assert "LEGACY_MODE_DISABLED" in result["reason"]
    assert len(server.node.lantern.kernel.observations) == 0


def test_join_does_not_weaken_codex_update_protection(node):
    """Category C reason-string update: same rationale as above. No
    session_id is presented, so the secure-default boundary rejects
    this before capability negotiation runs. CODEX_UPDATE protection is
    not weakened by this change -- it is strictly reinforced, since
    CODEX_UPDATE remains rejected even in the unreachable case where
    legacy mode were enabled (see test_bootstrap_transport.py's
    codex_update coverage under the secure path).
    """
    base, server = node
    _request(base, "/join", "POST", _payload(capabilities={"codex_update": True}))

    message = {
        "message_id": "m2",
        "protocol": "0.82",
        "message_type": "CODEX_UPDATE",
        "source": "external-test-07",
        "timestamp": "2026-01-01T00:00:00+00:00",
        "payload": {"concept": "gravity", "confidence": 0.99, "evidence_ids": ["x"]},
    }
    status, result = _request(
        base, "/message", "POST",
        {"message": message, "peer_capabilities": {"codex_update": True}},
    )
    assert result["accepted"] is False
    assert "LEGACY_MODE_DISABLED" in result["reason"]
    assert len(server.node.lantern.kernel.evidence) == 0


def test_join_uses_separate_chronicle_from_belief_chronicle(node, tmp_path):
    base, server = node
    _request(base, "/join", "POST", _payload())

    assert server.node.rendezvous.path != server.node.chronicle.path
    assert list(server.node.chronicle.replay()) == []
    join_events = [record["type"] for record in server.node.rendezvous.chronicle.replay()]
    assert "JOIN_REQUESTED" in join_events
