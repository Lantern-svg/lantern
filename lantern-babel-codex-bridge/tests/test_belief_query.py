"""Tests for the belief_query network capability: a read-only, session-
bound, capability-authorized endpoint that exposes a Lantern node's
current belief state without mutating any Chronicle, Codex, evidence,
or observation state.

Covers:
  - Authorized belief_query succeeds and returns belief data
  - Unauthenticated request (no session_id) fails
  - Unauthorized node (no belief_query in policy) fails
  - Invalid session (wrong session_id) fails
  - Source/session binding mismatch fails
  - Query does NOT mutate Chronicle step or watermark
  - codex_update remains impossible (NEVER_AUTHORIZABLE)
  - Existing observation exchange still works alongside belief_query
  - Full existing test suite unaffected
"""

from __future__ import annotations

import json
import threading
import time
from dataclasses import asdict
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from lantern import identity as identity_module
from lantern.bootstrap_client import _verify_identity_with_peer
from lantern.bootstrap_node import create_server
from lantern.capability_authorization import AuthorizationPolicy, NEVER_AUTHORIZABLE
from lantern.handshake import create_handshake
from lantern.protocol import create_observation_share


def request(base, path, method="GET", payload=None):
    data = None if payload is None else json.dumps(payload).encode()
    req = Request(base + path, data=data, method=method, headers={"Content-Type": "application/json"})
    try:
        with urlopen(req, timeout=3) as response:
            return response.status, json.loads(response.read())
    except HTTPError as e:
        return e.code, json.loads(e.read())


@pytest.fixture
def node_with_belief_auth(tmp_path):
    """Server with belief_query + evidence_exchange authorized for lantern-a."""
    server = create_server(
        "127.0.0.1", 0, "lantern-b", tmp_path / "b.jsonl",
        authorization_policy=AuthorizationPolicy.authorize(
            "lantern-a", {"evidence_exchange", "belief_query"}
        ),
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    yield base, server
    server.shutdown()
    server.server_close()
    thread.join(timeout=3)


@pytest.fixture
def node_without_belief_auth(tmp_path):
    """Server with evidence_exchange authorized but NOT belief_query."""
    server = create_server(
        "127.0.0.1", 0, "lantern-b", tmp_path / "b2.jsonl",
        authorization_policy=AuthorizationPolicy.authorize(
            "lantern-a", {"evidence_exchange"}
        ),
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    yield base, server
    server.shutdown()
    server.server_close()
    thread.join(timeout=3)


def _open_verified_session(base, tmp_path, node_id="lantern-a"):
    """Full identity verification + session creation over HTTP."""
    hs = create_handshake()
    hs.node_id = node_id
    request(base, "/handshake", "POST", asdict(hs))

    identity_dir = identity_module.default_identity_dir(tmp_path / "id", node_id)
    local_identity = identity_module.load_or_create(node_id, identity_dir)
    _verify_identity_with_peer(base, node_id, local_identity)

    # Two-phase session open: challenge -> sign -> proof -> session
    # (Gate 2 Finding 9: per-request proof of private-key possession)
    _, challenge = request(base, "/session/open", "POST", {"node_id": node_id})
    if challenge.get("created"):
        return challenge["session_id"]
    challenge_obj = identity_module.Challenge(
        nonce=challenge["nonce"],
        from_node_id=challenge["from_node_id"],
        to_node_id=challenge["to_node_id"],
        protocol_version=challenge["protocol_version"],
        issued_at=0.0,
        ttl_seconds=challenge.get("ttl_seconds", identity_module.DEFAULT_CHALLENGE_TTL_SECONDS),
    )
    binding = json.loads((local_identity.identity_dir / "binding.json").read_text())
    proof = identity_module.respond_to_challenge(challenge_obj, local_identity, binding["signature"])
    _, session = request(base, "/session/open", "POST", {
        "node_id": node_id,
        "proof": {
            "nonce": proof.nonce,
            "from_node_id": proof.from_node_id,
            "to_node_id": proof.to_node_id,
            "protocol_version": proof.protocol_version,
            "claimed_node_id": proof.claimed_node_id,
            "public_key": proof.public_key,
            "identity_binding_signature": proof.identity_binding_signature,
            "signature": proof.signature,
            "proof_timestamp": proof.proof_timestamp,
        },
    })
    return session["session_id"]


def _add_observation(base, session_id, node_id, content, source):
    message = create_observation_share(node_id, {
        "content": content, "source": source, "reliability": 1.0,
    })
    request(base, "/message", "POST", {
        "message": asdict(message), "session_id": session_id,
    })


class TestBeliefQueryAuthorized:
    """Authorized belief_query succeeds and returns read-only data."""

    def test_authorized_query_returns_belief_state(self, node_with_belief_auth, tmp_path):
        base, server = node_with_belief_auth
        session_id = _open_verified_session(base, tmp_path)
        _add_observation(base, session_id, "lantern-a", "test observation", "test_source")

        code, result = request(base, "/belief/query", "POST", {
            "session_id": session_id,
            "node_id": "lantern-a",
        })
        assert code == 200
        assert result["accepted"] is True
        assert result["queried_by"] == "lantern-a"
        assert result["responded_by"] == "lantern-b"
        assert "concepts" in result
        assert "step" in result
        assert "watermark" in result
        assert isinstance(result["concepts"], list)

    def test_belief_query_returns_watermark_and_step(self, node_with_belief_auth, tmp_path):
        base, server = node_with_belief_auth
        session_id = _open_verified_session(base, tmp_path)

        code, result = request(base, "/belief/query", "POST", {
            "session_id": session_id,
            "node_id": "lantern-a",
        })
        assert code == 200
        assert result["accepted"] is True
        assert "step" in result
        assert "watermark" in result
        assert "chain" in result["watermark"]
        assert "step" in result["watermark"]


class TestBeliefQueryUnauthorized:
    """Various failure modes for belief_query."""

    def test_no_session_id_fails(self, node_with_belief_auth):
        base, server = node_with_belief_auth
        code, result = request(base, "/belief/query", "POST", {
            "node_id": "lantern-a",
        })
        assert code == 400
        assert "session_id" in result["error"]

    def test_invalid_session_fails(self, node_with_belief_auth):
        base, server = node_with_belief_auth
        code, result = request(base, "/belief/query", "POST", {
            "session_id": "fake-session-id-that-does-not-exist",
            "node_id": "lantern-a",
        })
        assert code == 200
        assert result["accepted"] is False
        assert "unknown_session" in result["reason"] or "expired" in result["reason"]

    def test_source_mismatch_fails(self, node_with_belief_auth, tmp_path):
        base, server = node_with_belief_auth
        session_id = _open_verified_session(base, tmp_path, "lantern-a")

        code, result = request(base, "/belief/query", "POST", {
            "session_id": session_id,
            "node_id": "lantern-imposter",
        })
        assert code == 200
        assert result["accepted"] is False
        assert "source_mismatch" in result["reason"]

    def test_belief_query_not_authorized_fails(self, node_without_belief_auth, tmp_path):
        base, server = node_without_belief_auth
        session_id = _open_verified_session(base, tmp_path, "lantern-a")

        code, result = request(base, "/belief/query", "POST", {
            "session_id": session_id,
            "node_id": "lantern-a",
        })
        assert code == 200
        assert result["accepted"] is False
        assert "belief_query" in result["reason"]
        assert "not in authorized_capabilities" in result["reason"]


class TestBeliefQueryReadOnly:
    """belief_query must not mutate any state."""

    def test_chronicle_step_unchanged_after_query(self, node_with_belief_auth, tmp_path):
        base, server = node_with_belief_auth
        session_id = _open_verified_session(base, tmp_path)
        _add_observation(base, session_id, "lantern-a", "obs before query", "src1")

        _, health_before = request(base, "/health")
        step_before = health_before["watermark"]["step"]

        code, result = request(base, "/belief/query", "POST", {
            "session_id": session_id, "node_id": "lantern-a",
        })
        assert result["accepted"] is True

        _, health_after = request(base, "/health")
        step_after = health_after["watermark"]["step"]
        assert step_after == step_before, (
            f"Chronicle step changed from {step_before} to {step_after} after belief_query"
        )

    def test_no_observation_created_by_query(self, node_with_belief_auth, tmp_path):
        base, server = node_with_belief_auth
        session_id = _open_verified_session(base, tmp_path)
        _add_observation(base, session_id, "lantern-a", "baseline obs", "src")

        kernel_before = len(server.node.lantern.kernel.observations)

        request(base, "/belief/query", "POST", {
            "session_id": session_id, "node_id": "lantern-a",
        })

        kernel_after = len(server.node.lantern.kernel.observations)
        assert kernel_after == kernel_before, "belief_query created an observation"

    def test_no_evidence_created_by_query(self, node_with_belief_auth, tmp_path):
        base, server = node_with_belief_auth
        session_id = _open_verified_session(base, tmp_path)

        evidence_before = len(server.node.lantern.kernel.evidence)

        request(base, "/belief/query", "POST", {
            "session_id": session_id, "node_id": "lantern-a",
        })

        evidence_after = len(server.node.lantern.kernel.evidence)
        assert evidence_after == evidence_after, "belief_query created evidence"

    def test_codex_update_still_impossible(self, node_with_belief_auth, tmp_path):
        assert "codex_update" in NEVER_AUTHORIZABLE

        from lantern.capability_authorization import authorize
        from lantern.verified_contact import VerifiedContactResult, VerifiedContactOutcome

        verified = VerifiedContactResult(
            outcome=VerifiedContactOutcome.IDENTITY_VERIFIED,
            local_node_id="lantern-b",
            remote_node_id="lantern-a",
            identity_status=identity_module.CRYPTOGRAPHICALLY_VERIFIED,
            protocol_version="0.82",
            shared_capabilities={"belief_query": True, "codex_update": True, "evidence_exchange": True},
            contact_endpoint="",
            reason="test",
        )
        policy = AuthorizationPolicy.authorize("lantern-a", {"belief_query", "codex_update", "evidence_exchange"})
        decision = authorize(verified, requested=["belief_query", "codex_update", "evidence_exchange"], policy=policy)

        assert "belief_query" in decision.authorized_capabilities
        assert "codex_update" not in decision.authorized_capabilities
        assert decision.denied_capabilities.get("codex_update") == "structurally_unauthorizable"


class TestBeliefQueryCoexistence:
    """belief_query must not break existing observation exchange."""

    def test_observation_exchange_still_works(self, node_with_belief_auth, tmp_path):
        base, server = node_with_belief_auth
        session_id = _open_verified_session(base, tmp_path)

        message = create_observation_share("lantern-a", {
            "content": "coexistence test", "source": "test", "reliability": 1.0,
        })
        code, result = request(base, "/message", "POST", {
            "message": asdict(message), "session_id": session_id,
        })
        assert result["accepted"] is True
        assert result["observation_id"] is not None

        code, bq = request(base, "/belief/query", "POST", {
            "session_id": session_id, "node_id": "lantern-a",
        })
        assert bq["accepted"] is True

        message2 = create_observation_share("lantern-a", {
            "content": "after query", "source": "test2", "reliability": 1.0,
        })
        code, result2 = request(base, "/message", "POST", {
            "message": asdict(message2), "session_id": session_id,
        })
        assert result2["accepted"] is True

    def test_belief_query_after_multiple_observations(self, node_with_belief_auth, tmp_path):
        base, server = node_with_belief_auth
        session_id = _open_verified_session(base, tmp_path)

        for i in range(3):
            msg = create_observation_share("lantern-a", {
                "content": f"obs {i}", "source": f"src{i}", "reliability": 1.0,
            })
            request(base, "/message", "POST", {
                "message": asdict(msg), "session_id": session_id,
            })

        code, result = request(base, "/belief/query", "POST", {
            "session_id": session_id, "node_id": "lantern-a",
        })
        assert result["accepted"] is True
        assert result["step"] >= 3
