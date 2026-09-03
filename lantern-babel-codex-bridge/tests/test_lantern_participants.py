"""Lantern Participant Inspection / Informational Compatibility tests.

Locks in: participant inspection is read-only and never contacts a peer,
never mutates trust/authority/belief/Codex state, and compatibility is
informational only -- it must never be read as, or turned into, an
authorization decision. Every ParticipantView carries
trust_status="unverified" and authority_level="none" unconditionally.
"""

import json
import threading
from datetime import datetime, timezone
from urllib.request import Request, urlopen

import pytest

from lantern.bootstrap_node import create_server
from lantern.compatibility import DEFAULT_CAPABILITIES
from lantern.participants import (
    AUTHORITY_NONE,
    COMPATIBLE,
    INCOMPATIBLE,
    REQUIRES_NEGOTIATION,
    TRUST_UNVERIFIED,
    UNKNOWN,
    find,
    inspect,
    inspect_all,
    next_verification_step,
)
from lantern.rendezvous import EXPIRED, JoinMonitor


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
# inspect() / inspect_all() / find()
# ==================================================

def test_inspect_reports_compatible_when_major_version_and_capability_overlap(tmp_path):
    monitor = JoinMonitor(tmp_path / "joins.jsonl")
    request, _, _ = monitor.submit(_payload())

    view = inspect(request)

    assert view.node_id == "external-test-07"
    assert view.request_id == request.request_id
    assert view.protocol_version == "0.82"
    assert view.capabilities_claimed == {"evidence_exchange": True, "handshake": True}
    assert view.join_status == "awaiting_handshake"
    assert view.compatibility_status == COMPATIBLE
    assert "evidence_exchange" in view.shared_capabilities_if_compatible
    assert view.trust_status == TRUST_UNVERIFIED
    assert view.authority_level == AUTHORITY_NONE


def test_inspect_reports_incompatible_on_major_version_mismatch(tmp_path):
    monitor = JoinMonitor(tmp_path / "joins.jsonl")
    request, _, _ = monitor.submit(_payload(protocol_version="9.0"))

    view = inspect(request)

    assert view.compatibility_status == INCOMPATIBLE
    assert view.shared_capabilities_if_compatible == []
    assert view.trust_status == TRUST_UNVERIFIED
    assert view.authority_level == AUTHORITY_NONE


def test_inspect_reports_requires_negotiation_when_no_capability_overlap(tmp_path):
    monitor = JoinMonitor(tmp_path / "joins.jsonl")
    request, _, _ = monitor.submit(_payload(capabilities={"some_future_thing": True}))

    view = inspect(request)

    assert view.compatibility_status == REQUIRES_NEGOTIATION
    assert view.shared_capabilities_if_compatible == []


def test_inspect_reports_unknown_on_unparseable_protocol_version(tmp_path):
    monitor = JoinMonitor(tmp_path / "joins.jsonl")
    request, _, _ = monitor.submit(_payload(protocol_version="not-a-version"))

    view = inspect(request)

    assert view.compatibility_status == UNKNOWN


def test_inspect_all_includes_expired_by_default(tmp_path):
    monitor = JoinMonitor(tmp_path / "joins.jsonl", ttl_seconds=1)
    old_timestamp = "2000-01-01T00:00:00+00:00"
    monitor.submit(_payload(timestamp=old_timestamp))

    views = inspect_all(monitor)
    assert len(views) == 1
    assert views[0].join_status == EXPIRED


def test_inspect_all_can_exclude_expired(tmp_path):
    monitor = JoinMonitor(tmp_path / "joins.jsonl", ttl_seconds=1)
    monitor.submit(_payload(timestamp="2000-01-01T00:00:00+00:00"))

    views = inspect_all(monitor, include_expired=False)
    assert views == []


def test_find_returns_none_for_unknown_request_id(tmp_path):
    monitor = JoinMonitor(tmp_path / "joins.jsonl")
    assert find(monitor, "does-not-exist") is None


def test_find_returns_matching_participant(tmp_path):
    monitor = JoinMonitor(tmp_path / "joins.jsonl")
    request, _, _ = monitor.submit(_payload())

    view = find(monitor, request.request_id)
    assert view is not None
    assert view.node_id == "external-test-07"


# ==================================================
# next_verification_step() advice, never a connection
# ==================================================

def test_next_step_for_expired_request_asks_for_resubmission(tmp_path):
    monitor = JoinMonitor(tmp_path / "joins.jsonl", ttl_seconds=1)
    request, _, _ = monitor.submit(_payload(timestamp="2000-01-01T00:00:00+00:00"))
    view = inspect(monitor.all_requests()[0])

    step = next_verification_step(view)
    assert "expired" in step.lower()
    assert "resubmit" in step.lower() or "new /join" in step.lower()


def test_next_step_for_incompatible_warns_no_safe_step(tmp_path):
    monitor = JoinMonitor(tmp_path / "joins.jsonl")
    request, _, _ = monitor.submit(_payload(protocol_version="9.0"))
    view = inspect(request)

    step = next_verification_step(view)
    assert "no safe verification step" in step.lower()


def test_next_step_for_compatible_with_endpoint_suggests_manual_handshake(tmp_path):
    monitor = JoinMonitor(tmp_path / "joins.jsonl")
    request, _, _ = monitor.submit(_payload(peer_endpoint="http://10.0.0.5:8765"))
    view = inspect(request)

    step = next_verification_step(view)
    assert "10.0.0.5:8765" in step
    assert "automatically" in step.lower()


def test_next_step_for_compatible_without_endpoint_asks_for_address(tmp_path):
    monitor = JoinMonitor(tmp_path / "joins.jsonl")
    request, _, _ = monitor.submit(_payload())
    view = inspect(request)

    step = next_verification_step(view)
    assert "out-of-band" in step.lower()


def test_next_verification_step_never_triggers_network_call(tmp_path, monkeypatch):
    """Guard against a regression that makes this "advice" function
    actually reach out to the network."""
    import urllib.request

    def _boom(*args, **kwargs):
        raise AssertionError("next_verification_step must never open a network connection")

    monkeypatch.setattr(urllib.request, "urlopen", _boom)

    monitor = JoinMonitor(tmp_path / "joins.jsonl")
    request, _, _ = monitor.submit(_payload(peer_endpoint="http://10.0.0.5:8765"))
    view = inspect(request)

    next_verification_step(view)  # must not raise


# ==================================================
# Compatibility is informational only -- never authority
# ==================================================

def test_compatibility_status_never_changes_trust_or_authority(tmp_path):
    monitor = JoinMonitor(tmp_path / "joins.jsonl")
    compatible_request, _, _ = monitor.submit(_payload(request_id="a"))
    incompatible_request, _, _ = monitor.submit(_payload(request_id="b", protocol_version="9.0"))

    compatible_view = inspect(compatible_request)
    incompatible_view = inspect(incompatible_request)

    assert compatible_view.compatibility_status == COMPATIBLE
    assert incompatible_view.compatibility_status == INCOMPATIBLE
    # Trust/authority are identical regardless of compatibility outcome.
    assert compatible_view.trust_status == incompatible_view.trust_status == TRUST_UNVERIFIED
    assert compatible_view.authority_level == incompatible_view.authority_level == AUTHORITY_NONE


def test_claiming_codex_update_capability_does_not_change_authority_or_actual_gate(tmp_path):
    monitor = JoinMonitor(tmp_path / "joins.jsonl")
    request, _, _ = monitor.submit(_payload(capabilities={"codex_update": True}))

    view = inspect(request)
    # codex_update is False locally, so it cannot appear as shared even
    # though claimed -- and even where it might, authority stays "none".
    assert "codex_update" not in view.shared_capabilities_if_compatible
    assert view.authority_level == AUTHORITY_NONE
    assert DEFAULT_CAPABILITIES["codex_update"] is False


# ==================================================
# HTTP wiring: GET /participants, GET /participants/<id>/next-step
# ==================================================

def _get(base, path):
    req = Request(base + path, method="GET")
    with urlopen(req, timeout=3) as response:
        return response.status, json.loads(response.read())


def _post(base, path, payload):
    req = Request(
        base + path,
        data=json.dumps(payload).encode(),
        method="POST",
        headers={"Content-Type": "application/json"},
    )
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


def test_get_participants_lists_claims_after_join(node):
    base, server = node
    _post(base, "/join", _payload())

    status, result = _get(base, "/participants")
    assert status == 200
    assert len(result["participants"]) == 1
    entry = result["participants"][0]
    assert entry["node_id"] == "external-test-07"
    assert entry["trust_status"] == TRUST_UNVERIFIED
    assert entry["authority_level"] == AUTHORITY_NONE
    assert entry["compatibility_status"] == COMPATIBLE

    # Inspection must not touch the belief/evidence kernel.
    assert len(server.node.lantern.kernel.observations) == 0
    assert len(server.node.lantern.kernel.evidence) == 0


def test_get_participants_empty_before_any_join(node):
    base, server = node
    status, result = _get(base, "/participants")
    assert status == 200
    assert result["participants"] == []


def test_get_participants_reports_identity_status_after_real_verification(node, tmp_path):
    """Regression test: a node_id that has already completed a REAL
    challenge/response identity proof against this process (recorded in
    LanternNode._known_public_keys) must be reported as
    identity_status=CRYPTOGRAPHICALLY_VERIFIED by GET /participants,
    not silently defaulted to UNVERIFIED just because its /join record
    and its /identity/* proof are tracked on separate ledgers.

    Before the fix, /participants always called inspect_all() with no
    known_public_keys argument, so identity_status was UNVERIFIED
    unconditionally regardless of any completed proof -- this pinned
    that specific gap.

    trust_status and authority_level must remain unconditionally
    "unverified"/"none" throughout -- identity_status is a separate,
    third axis and this fix must not touch the other two.
    """
    from lantern import identity as identity_module
    from lantern.bootstrap_client import _verify_identity_with_peer

    base, server = node
    node_id = "external-test-07"

    # A /join claim exists but has NOT been separately verified via
    # /identity/* yet -- confirms the two ledgers really are decoupled.
    _post(base, "/join", _payload(node_id=node_id, request_id="req-unverified"))
    status, result = _get(base, "/participants")
    assert status == 200
    entry = result["participants"][0]
    assert entry["identity_status"] == "UNVERIFIED"

    # Now perform a REAL challenge/response proof for the same node_id,
    # over real HTTP, using the same client wiring bootstrap_client.py
    # itself uses (never reimplemented here).
    identity_dir = identity_module.default_identity_dir(tmp_path, node_id)
    local_identity = identity_module.load_or_create(node_id, identity_dir)
    verify_result = _verify_identity_with_peer(base, node_id, local_identity)
    assert verify_result["verified"] is True, verify_result
    assert node_id in server.node._known_public_keys

    # /participants must now reflect the real proof for this node_id.
    status, result = _get(base, "/participants")
    assert status == 200
    entry = result["participants"][0]
    assert entry["node_id"] == node_id
    assert entry["identity_status"] == "CRYPTOGRAPHICALLY_VERIFIED"

    # identity_status changed; trust_status/authority_level must not.
    assert entry["trust_status"] == TRUST_UNVERIFIED
    assert entry["authority_level"] == AUTHORITY_NONE


def test_get_participants_unrelated_node_id_stays_unverified(node, tmp_path):
    """A real proof for one node_id must not leak identity_status to a
    different node_id's /join claim -- known_public_keys lookup is keyed
    by node_id, never applied blanket."""
    from lantern import identity as identity_module
    from lantern.bootstrap_client import _verify_identity_with_peer

    base, server = node
    verified_node_id = "external-test-07"
    other_node_id = "external-test-08"

    _post(base, "/join", _payload(node_id=other_node_id, request_id="req-other"))

    identity_dir = identity_module.default_identity_dir(tmp_path, verified_node_id)
    local_identity = identity_module.load_or_create(verified_node_id, identity_dir)
    verify_result = _verify_identity_with_peer(base, verified_node_id, local_identity)
    assert verify_result["verified"] is True, verify_result

    status, result = _get(base, "/participants")
    assert status == 200
    entry = result["participants"][0]
    assert entry["node_id"] == other_node_id
    assert entry["identity_status"] == "UNVERIFIED"


def test_get_next_step_for_known_request(node):
    base, server = node
    _post(base, "/join", _payload(peer_endpoint="http://10.0.0.9:8765"))

    status, result = _get(base, f"/participants/req-1/next-step")
    assert status == 200
    assert result["request_id"] == "req-1"
    assert "10.0.0.9:8765" in result["next_step"]
    assert result["participant"]["authority_level"] == AUTHORITY_NONE


def test_get_next_step_for_unknown_request_returns_404(node):
    base, server = node
    with pytest.raises(Exception):
        _get(base, "/participants/does-not-exist/next-step")


def test_participants_endpoint_does_not_bypass_handshake_or_capability_gate(node):
    """Listing/inspecting a participant must have zero effect on what
    /message will actually accept."""
    base, server = node
    _post(base, "/join", _payload(capabilities={"evidence_exchange": True}))
    _get(base, "/participants")
    _get(base, "/participants/req-1/next-step")

    message = {
        "message_id": "m1",
        "protocol": "0.82",
        "message_type": "OBSERVATION_SHARE",
        "source": "external-test-07",
        "timestamp": "2026-01-01T00:00:00+00:00",
        "payload": {"observation": {"content": "trying to ride in on inspection"}},
    }
    status, result = _post(base, "/message", {"message": message, "peer_capabilities": {}})
    assert result["accepted"] is False
    assert len(server.node.lantern.kernel.observations) == 0
