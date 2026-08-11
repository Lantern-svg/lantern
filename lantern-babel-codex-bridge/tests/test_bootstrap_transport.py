"""Real process-boundary tests for the minimal external bootstrap adapter."""

import json
import threading
from dataclasses import asdict
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from lantern import identity as identity_module
from lantern.bootstrap_client import _verify_identity_with_peer
from lantern.bootstrap_node import create_server
from lantern.capability_authorization import AuthorizationPolicy
from lantern.handshake import create_handshake
from lantern.protocol import create_codex_update, create_observation_share


def request(base, path, method="GET", payload=None):
    data = None if payload is None else json.dumps(payload).encode()
    req = Request(base + path, data=data, method=method, headers={"Content-Type": "application/json"})
    with urlopen(req, timeout=3) as response:
        return response.status, json.loads(response.read())


@pytest.fixture
def node(tmp_path):
    # authorization_policy grants lantern-a evidence_exchange up front so
    # tests that migrate to the secure identity -> session -> /message
    # path (Phase 4 compatibility migration) can exercise a real
    # accepted Observation, exactly as an operator would configure a
    # known peer. This does not weaken anything: identity verification
    # and session binding are still required in full below; a grant
    # alone accepts nothing without both.
    server = create_server(
        "127.0.0.1", 0, "lantern-b", tmp_path / "b.jsonl",
        authorization_policy=AuthorizationPolicy.authorize("lantern-a", {"evidence_exchange"}),
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    yield base, server
    server.shutdown()
    server.server_close()
    thread.join(timeout=3)


def handshake_with(base, node_id=None):
    request_message = create_handshake()
    if node_id is not None:
        request_message.node_id = node_id
    _, response = request(base, "/handshake", "POST", asdict(request_message))
    return request_message, response


def _open_verified_session_over_http(base, tmp_path, node_id="lantern-a"):
    """Real HTTP identity verification + session creation against a
    running _Handler-backed server, reusing bootstrap_client's own
    challenge/response wiring verbatim (never reimplemented here)."""
    identity_dir = identity_module.default_identity_dir(tmp_path, node_id)
    local_identity = identity_module.load_or_create(node_id, identity_dir)
    verify_result = _verify_identity_with_peer(base, node_id, local_identity)
    assert verify_result["verified"] is True, verify_result
    _, session = request(base, "/session/open", "POST", {"node_id": node_id})
    assert session["created"] is True, session
    return session["session_id"]


def _establish_session_in_process(server_node, tmp_path, node_id="lantern-a"):
    """Same identity -> session establishment as above, but calling
    LanternNode methods directly in-process (no HTTP thread involved) --
    for tests that exercise persistence/restart behavior rather than the
    network boundary itself."""
    identity_dir = identity_module.default_identity_dir(tmp_path, node_id)
    local_identity = identity_module.load_or_create(node_id, identity_dir)
    challenge_data = server_node.issue_identity_challenge(node_id)
    challenge = identity_module.Challenge(
        nonce=challenge_data["nonce"],
        from_node_id=challenge_data["from_node_id"],
        to_node_id=challenge_data["to_node_id"],
        protocol_version=challenge_data["protocol_version"],
        issued_at=0.0,
        ttl_seconds=challenge_data.get("ttl_seconds", identity_module.DEFAULT_CHALLENGE_TTL_SECONDS),
    )
    binding = json.loads((local_identity.identity_dir / "binding.json").read_text())
    proof = identity_module.respond_to_challenge(challenge, local_identity, binding["signature"])
    proof_data = {
        "nonce": proof.nonce,
        "from_node_id": proof.from_node_id,
        "to_node_id": proof.to_node_id,
        "protocol_version": proof.protocol_version,
        "claimed_node_id": proof.claimed_node_id,
        "public_key": proof.public_key,
        "identity_binding_signature": proof.identity_binding_signature,
        "signature": proof.signature,
        "proof_timestamp": proof.proof_timestamp,
    }
    verify_result = server_node.verify_identity_proof(proof_data)
    assert verify_result["verified"] is True, verify_result
    session = server_node.open_session(node_id)
    assert session["created"] is True, session
    return session["session_id"]


def test_external_process_boundary_handshake_and_observation(node, tmp_path):
    """Category A migration (Phase 4 compatibility migration): this is a
    legitimate node-to-node workflow, so it now goes through real
    identity verification and a session-bound /message call instead of
    self-declared peer_capabilities. It still proves the same external
    boundary properties as before (real HTTP, real handshake, exactly
    one accepted Observation, no Evidence, a verified Chronicle) -- it
    additionally now proves cryptographic identity and session binding,
    which the pre-migration version could not.
    """
    base, server = node
    local_handshake, response = handshake_with(base, node_id="lantern-a")

    assert response["accepted"] is True
    assert response["protocol_version"] == "0.82"
    assert response["shared_capabilities"]["evidence_exchange"] is True
    assert "codex_update" not in response["shared_capabilities"]

    session_id = _open_verified_session_over_http(base, tmp_path)

    message = create_observation_share(
        "lantern-a",
        {"content": "external claim", "source": "operator-a", "reliability": 0.99},
    )
    _, result = request(
        base,
        "/message",
        "POST",
        {"message": asdict(message), "session_id": session_id},
    )

    assert result["accepted"] is True
    assert result["action"] == "accept"
    assert result["source"] == "lantern-a"
    assert result["protocol"] == "0.82"
    observation_id = result["observation_id"]
    assert isinstance(observation_id, str) and observation_id
    assert len(server.node.lantern.kernel.observations) == 1
    assert len(server.node.lantern.kernel.evidence) == 0
    assert server.node.lantern.bus.chronicle.verify() is True


def test_external_boundary_rejects_bad_version_and_capability(node):
    base, server = node
    local_handshake = create_handshake()
    message = create_observation_share("lantern-a", {"content": "blocked"})

    bad_version = asdict(message)
    bad_version["protocol"] = "9.0"
    _, result = request(
        base,
        "/message",
        "POST",
        {"message": bad_version, "peer_capabilities": {"evidence_exchange": True}},
    )
    assert result["accepted"] is False
    assert len(server.node.lantern.kernel.observations) == 0

    _, result = request(
        base,
        "/message",
        "POST",
        {"message": asdict(message), "peer_capabilities": {}},
    )
    assert result["accepted"] is False
    assert len(server.node.lantern.kernel.observations) == 0


def test_external_boundary_rejects_malformed_and_codex_update(node, tmp_path):
    """Category C reason-string update: the malformed-payload assertion
    is unchanged (a structurally invalid message is rejected with HTTP
    400 before any legacy/session check runs, in either mode).

    The CODEX_UPDATE assertion is updated, not just re-pointed at the
    legacy fixture, because this now proves a STRICTLY STRONGER
    guarantee than before the migration: CODEX_UPDATE is rejected by the
    secure /message path even for a fully identity-verified, session-
    bound, evidence_exchange-authorized peer -- not merely because a
    capability flag was withheld. codex_update stays NEVER_AUTHORIZABLE
    regardless of identity, session, or authorization state, which is
    exactly the invariant this test exists to protect.
    """
    base, server = node
    with pytest.raises(HTTPError) as error:
        request(base, "/message", "POST", {"message": {"bad": "shape"}, "peer_capabilities": {}})
    assert error.value.code == 400
    assert len(server.node.lantern.kernel.observations) == 0

    session_id = _open_verified_session_over_http(base, tmp_path)
    codex = create_codex_update("lantern-a", "gravity", 0.99, ["remote-evidence"])
    _, result = request(
        base,
        "/message",
        "POST",
        {"message": asdict(codex), "session_id": session_id},
    )
    assert result["accepted"] is False
    assert "OBSERVATION_SHARE" in result["reason"]
    assert "CODEX_UPDATE" in result["reason"]
    assert len(server.node.lantern.kernel.evidence) == 0


def test_restart_reuses_chronicle_and_snapshot(tmp_path):
    """Category A migration: this test's real purpose is persistence
    (Chronicle + snapshot survive a process restart), not legacy
    ingestion semantics -- it only needs SOME real accepted Observation
    to verify that. Migrated to the secure identity -> session ->
    /message path in-process (no HTTP thread needed, same as before).
    """
    path = tmp_path / "persisted.jsonl"
    first = create_server(
        "127.0.0.1", 0, "lantern-b", path,
        authorization_policy=AuthorizationPolicy.authorize("lantern-a", {"evidence_exchange"}),
    )
    session_id = _establish_session_in_process(first.node, tmp_path)
    message = create_observation_share("lantern-a", {"content": "persist me"})
    result = first.node.receive(asdict(message), {}, session_id=session_id)
    assert result["accepted"] is True
    first.node.lantern.save_snapshot()
    first.server_close()

    second = create_server("127.0.0.1", 0, "lantern-b", path)
    assert len(second.node.lantern.kernel.observations) == 1
    assert second.node.lantern.bus.chronicle.verify() is True
    second.server_close()


def test_join_write_failure_is_reported_as_failure_not_success(node):
    """PRINCIPLE 2: if the durable write (Chronicle.append) fails, the
    HTTP layer must report a clear failure with persisted=False -- never
    a false "accepted" response. This forces the real append() call to
    raise OSError and checks the adapter does not swallow it.
    """
    import datetime as _dt

    base, server = node

    def _boom(self, event):
        raise OSError("simulated disk failure")

    original_append = type(server.node.rendezvous.chronicle).append
    type(server.node.rendezvous.chronicle).append = _boom
    try:
        payload = {
            "request_id": "req-fail-1",
            "node_id": "external-test-fail",
            "protocol_version": "0.82",
            "capabilities": {"evidence_exchange": True},
            "timestamp": _dt.datetime.now(_dt.timezone.utc).isoformat(),
        }
        with pytest.raises(HTTPError) as error:
            request(base, "/join", "POST", payload)
        assert error.value.code == 500
        body = json.loads(error.value.read())
        assert body["persisted"] is False
        assert "durable write failed" in body["error"].lower()
    finally:
        type(server.node.rendezvous.chronicle).append = original_append

    # The failed write must not have left a phantom pending request behind.
    assert "req-fail-1" not in server.node.rendezvous.requests
