"""
Lantern Identity -- Real Two-Node Local Simulation

Per the Phase 2A implementation authorization: prove the identity
proof mechanism over a REAL local network round-trip (two independent
HTTP servers, two independent identity stores, two independent
node_ids) rather than only in-process function calls. Discord is not
involved anywhere in this file. Nothing is exposed beyond
127.0.0.1 -- both servers bind to an ephemeral loopback port.

Proves, over real HTTP:
    - A can verify B (B answers a challenge A issued; A verifies it).
    - B can verify A (symmetric, A answers a challenge B issued).
    - A cannot impersonate B (a forged proof over the wire is rejected).
    - A captured proof cannot be replayed over the wire a second time.
"""

from __future__ import annotations

import json
import threading
from urllib.request import Request, urlopen

import pytest

from lantern.bootstrap_node import create_server


def _post(base, path, payload):
    data = json.dumps(payload).encode()
    req = Request(base + path, data=data, method="POST", headers={"Content-Type": "application/json"})
    with urlopen(req, timeout=3) as response:
        return response.status, json.loads(response.read())


def _get(base, path):
    with urlopen(base + path, timeout=3) as response:
        return response.status, json.loads(response.read())


@pytest.fixture
def two_nodes(tmp_path):
    server_a = create_server("127.0.0.1", 0, "lantern-A", tmp_path / "a" / "a.jsonl")
    server_b = create_server("127.0.0.1", 0, "lantern-B", tmp_path / "b" / "b.jsonl")

    thread_a = threading.Thread(target=server_a.serve_forever, daemon=True)
    thread_b = threading.Thread(target=server_b.serve_forever, daemon=True)
    thread_a.start()
    thread_b.start()

    base_a = f"http://127.0.0.1:{server_a.server_address[1]}"
    base_b = f"http://127.0.0.1:{server_b.server_address[1]}"

    yield base_a, base_b

    server_a.shutdown()
    server_b.shutdown()
    server_a.server_close()
    server_b.server_close()
    thread_a.join(timeout=3)
    thread_b.join(timeout=3)


def test_health_advertises_public_identity_not_private(two_nodes):
    base_a, _ = two_nodes
    status, body = _get(base_a, "/health")
    assert status == 200
    assert "identity_public" in body
    assert body["identity_public"]["node_id"] == "lantern-A"
    assert len(body["identity_public"]["public_key"]) == 64
    blob = json.dumps(body)
    assert "private_key" not in blob
    assert "SigningKey" not in blob


def test_a_can_verify_b_over_real_http(two_nodes):
    base_a, base_b = two_nodes

    _, challenge = _post(base_a, "/identity/challenge", {"requester_node_id": "lantern-B"})
    assert challenge["from_node_id"] == "lantern-A"
    assert challenge["to_node_id"] == "lantern-B"

    _, proof = _post(base_b, "/identity/respond", challenge)
    assert proof["claimed_node_id"] == "lantern-B"

    _, result = _post(base_a, "/identity/verify", proof)
    assert result["verified"] is True
    assert result["identity_status"] == "CRYPTOGRAPHICALLY_VERIFIED"


def test_b_can_verify_a_over_real_http(two_nodes):
    base_a, base_b = two_nodes

    _, challenge = _post(base_b, "/identity/challenge", {"requester_node_id": "lantern-A"})
    _, proof = _post(base_a, "/identity/respond", challenge)
    _, result = _post(base_b, "/identity/verify", proof)

    assert result["verified"] is True
    assert result["identity_status"] == "CRYPTOGRAPHICALLY_VERIFIED"


def test_a_cannot_impersonate_b_over_real_http(two_nodes):
    base_a, base_b = two_nodes

    _, challenge = _post(base_a, "/identity/challenge", {"requester_node_id": "lantern-B"})

    # Ask A's own node to "respond" to a challenge whose to_node_id names
    # B -- A's node refuses, because respond_identity_challenge() only
    # ever signs with its own configured identity, and
    # respond_to_challenge() rejects a challenge addressed to a different
    # node_id than the responder actually is.
    from urllib.error import HTTPError

    try:
        _post(base_a, "/identity/respond", challenge)
        forged_available = True
        status, body = None, None
    except HTTPError as exc:
        forged_available = False
        status = exc.code
        body = json.loads(exc.read())

    assert not forged_available
    assert status == 400
    assert "lantern-B" in body["error"] or "node_id" in body["error"].lower()


def test_captured_proof_cannot_be_replayed_over_real_http(two_nodes):
    base_a, base_b = two_nodes

    _, challenge = _post(base_a, "/identity/challenge", {"requester_node_id": "lantern-B"})
    _, proof = _post(base_b, "/identity/respond", challenge)

    _, first_result = _post(base_a, "/identity/verify", proof)
    assert first_result["verified"] is True

    _, second_result = _post(base_a, "/identity/verify", proof)
    assert second_result["verified"] is False
    assert "replay" in second_result["reason"].lower()


def test_verification_over_http_never_touches_belief_or_evidence(two_nodes):
    """A full challenge/respond/verify cycle over real HTTP must leave
    the Chronicle's belief/evidence step count completely unchanged --
    identity verification is orthogonal to the kernel."""
    base_a, base_b = two_nodes

    before_a = _get(base_a, "/health")[1]["watermark"]
    before_b = _get(base_b, "/health")[1]["watermark"]

    _, challenge = _post(base_a, "/identity/challenge", {"requester_node_id": "lantern-B"})
    _, proof = _post(base_b, "/identity/respond", challenge)
    _post(base_a, "/identity/verify", proof)

    after_a = _get(base_a, "/health")[1]["watermark"]
    after_b = _get(base_b, "/health")[1]["watermark"]

    assert before_a == after_a
    assert before_b == after_b


def test_handshake_still_returns_stable_node_id_over_http(two_nodes):
    """Regression guard, over real HTTP: /handshake responses from the
    same node must always carry that node's real, configured node_id --
    never a fresh uuid4() per call."""
    base_a, base_b = two_nodes
    from dataclasses import asdict

    from lantern.handshake import create_handshake

    request_message = asdict(create_handshake())
    request_message["node_id"] = "lantern-B-as-initiator"

    _, response1 = _post(base_b, "/handshake", request_message)
    _, response2 = _post(base_b, "/handshake", request_message)

    assert response1["node_id"] == "lantern-B"
    assert response2["node_id"] == "lantern-B"
    assert response1["node_id"] == response2["node_id"]
