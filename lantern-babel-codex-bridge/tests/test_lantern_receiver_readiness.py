"""Tests for receiver_readiness: proving the JOIN_REQUESTED ->
COMPATIBILITY -> IDENTITY -> AUTHORIZATION -> BOUNDED HANDSHAKE ->
VERIFIED PEER sequence works end to end using only existing Lantern
components, and that every honest boundary is preserved:

    - a bare JOIN_REQUESTED never implies contact was attempted
    - a policy-denied endpoint is never contacted
    - a successful GET is never treated as identity verification
    - identity verification never implies authorization
    - authorization defaults to nothing unless a policy explicitly grants it
    - Compass never asserts "allowed" without a real CapabilityDecision
"""

from __future__ import annotations

import http.server
import json
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

import pytest

from lantern import identity as identity_module
from lantern.capability_authorization import AuthorizationPolicy
from lantern.compatibility import DEFAULT_CAPABILITIES
from lantern.contact_ledger import ContactLedger
from lantern.handshake import HandshakeRequest, evaluate_handshake
from lantern.network_contact_policy import NetworkContactPolicy
from lantern.network_contact_transport import NetworkContactTransport
from lantern.orchestration import create_default_registry
from lantern.receiver_readiness import (
    evaluate_join_request,
    orient_from_evaluation,
    to_contact_attempt,
)
from lantern.rendezvous import JoinMonitor
from lantern.verified_contact import IDENTITY_RESPOND_PATH, HANDSHAKE_PATH


@dataclass
class _NodeState:
    node_id: str
    identity: identity_module.NodeIdentity
    capabilities: dict


class _Handler(http.server.BaseHTTPRequestHandler):
    state: _NodeState | None = None
    record: dict | None = None

    def log_message(self, *_args):
        pass

    def _read_json(self):
        length = int(self.headers.get("Content-Length", "0"))
        return json.loads(self.rfile.read(length).decode("utf-8"))

    def _write_json(self, status: int, payload: dict):
        body = json.dumps(payload, sort_keys=True).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        self._write_json(200, {"ok": True})

    def do_POST(self):
        body = self._read_json()
        self.record["paths"].append(self.path)
        if self.path == HANDSHAKE_PATH:
            req = HandshakeRequest(**body)
            resp = evaluate_handshake(
                req, supported_capabilities=self.state.capabilities, responder_node_id=self.state.node_id
            )
            self._write_json(200, {
                "node_id": resp.node_id,
                "accepted": resp.accepted,
                "protocol_version": resp.protocol_version,
                "shared_capabilities": resp.shared_capabilities,
                "reason": resp.reason,
                "timestamp": resp.timestamp,
            })
            return
        if self.path == IDENTITY_RESPOND_PATH:
            challenge = identity_module.Challenge(
                nonce=body["nonce"],
                from_node_id=body["from_node_id"],
                to_node_id=body["to_node_id"],
                protocol_version=body["protocol_version"],
                issued_at=time.monotonic(),
                ttl_seconds=body.get("ttl_seconds", identity_module.DEFAULT_CHALLENGE_TTL_SECONDS),
            )
            binding = json.loads((self.state.identity.identity_dir / "binding.json").read_text())
            proof = identity_module.respond_to_challenge(challenge, self.state.identity, binding["signature"])
            self._write_json(200, {
                "nonce": proof.nonce,
                "from_node_id": proof.from_node_id,
                "to_node_id": proof.to_node_id,
                "protocol_version": proof.protocol_version,
                "claimed_node_id": proof.claimed_node_id,
                "public_key": proof.public_key,
                "identity_binding_signature": proof.identity_binding_signature,
                "signature": proof.signature,
                "proof_timestamp": proof.proof_timestamp,
            })
            return
        self._write_json(404, {"error": "not found"})


@contextmanager
def _remote_server(state: _NodeState):
    record = {"paths": []}
    handler = type("Handler", (_Handler,), {"state": state, "record": record})
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server.server_address, record
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def _make_identity(tmp_path: Path, node_id: str) -> identity_module.NodeIdentity:
    return identity_module.load_or_create(node_id, tmp_path / node_id)


def _submit_join(monitor: JoinMonitor, *, node_id: str, peer_endpoint: str | None):
    from datetime import datetime, timezone

    request, created, _ = monitor.submit({
        "request_id": f"req-{node_id}",
        "node_id": node_id,
        "protocol_version": "0.82",
        "capabilities": {"identity_proof": True},
        "timestamp": datetime.now(timezone.utc).isoformat(),
        **({"peer_endpoint": peer_endpoint} if peer_endpoint else {}),
    })
    assert created
    return request


def test_join_requested_without_attempt_contact_only_runs_compatibility(tmp_path: Path):
    """Default behavior (attempt_contact=False) mirrors joins_cli.py
    exactly: compatibility + advisory text only, contacts nobody.
    """
    monitor = JoinMonitor(tmp_path / "joins.jsonl")
    request = _submit_join(monitor, node_id="claimed-node", peer_endpoint="http://127.0.0.1:9/x")
    local = _make_identity(tmp_path, "local-node")

    evaluation = evaluate_join_request(
        request, local_node_id=local.node_id, local_identity=local, attempt_contact=False
    )

    assert evaluation.contacted is False
    assert evaluation.verified_contact is None
    assert evaluation.capability_decision is None
    assert evaluation.participant_view.compatibility_status in ("compatible", "requires_negotiation", "unknown", "incompatible")
    assert evaluation.next_step_advice  # advisory text, never a connection

    attempt = to_contact_attempt(evaluation)
    assert attempt.state == "CONTACT_PATH_FOUND"
    assert attempt.contact_type == "UNKNOWN"


def test_policy_denied_endpoint_is_never_contacted(tmp_path: Path):
    """A JoinRequest claiming a private/loopback-style endpoint must be
    refused by NetworkContactPolicy before any socket is opened -- even
    with attempt_contact=True.
    """
    monitor = JoinMonitor(tmp_path / "joins.jsonl")
    # Loopback is denied by the default (non-testing) policy.
    request = _submit_join(monitor, node_id="claimed-node", peer_endpoint="http://127.0.0.1:9999/")
    local = _make_identity(tmp_path, "local-node")

    evaluation = evaluate_join_request(
        request,
        local_node_id=local.node_id,
        local_identity=local,
        attempt_contact=True,
        # deliberately NOT allow_loopback_for_testing, to prove the deny path
        policy=NetworkContactPolicy(),
    )

    assert evaluation.contacted is False
    assert evaluation.verified_contact is None
    attempt = to_contact_attempt(evaluation)
    assert attempt.state == "CONTACT_PATH_FOUND"


def test_full_sequence_reaches_verified_peer_with_a_real_local_endpoint(tmp_path: Path):
    """The real end-to-end proof: JOIN_REQUESTED -> COMPATIBILITY ->
    IDENTITY -> AUTHORIZATION -> BOUNDED HANDSHAKE -> VERIFIED PEER,
    against a real local HTTP server implementing the actual wire
    handshake/identity protocol (same test harness pattern as
    test_lantern_verified_contact.py).
    """
    local = _make_identity(tmp_path, "local-node")
    remote = _make_identity(tmp_path, "remote-node")
    state = _NodeState(
        node_id=remote.node_id,
        identity=remote,
        capabilities={**DEFAULT_CAPABILITIES, "identity_proof": True},
    )

    with _remote_server(state) as ((host, port), record):
        endpoint = f"http://{host}:{port}"
        monitor = JoinMonitor(tmp_path / "joins.jsonl")
        request = _submit_join(monitor, node_id=remote.node_id, peer_endpoint=endpoint)

        policy = NetworkContactPolicy(allow_loopback_for_testing=True, allowed_ports=frozenset(range(1, 65536)))
        transport = NetworkContactTransport(policy=policy, allow_loopback_for_testing=True)

        # AUTHORIZATION stage: operator explicitly grants one capability
        # by name. "evidence_exchange" is negotiated at handshake time via
        # compatibility.DEFAULT_CAPABILITIES (True by default on both
        # sides), unlike "identity_proof" itself -- which the handshake
        # negotiates as an add-on capability but which capability_
        # authorization.authorize()'s OWN local_capabilities default
        # (plain DEFAULT_CAPABILITIES, identity_proof=False) would refuse
        # as NOT_LOCALLY_SUPPORTED. That is authorize()'s existing,
        # correct, conservative behavior -- this test authorizes a
        # capability that really is locally supported by default, rather
        # than working around that boundary. Omitting authorization_policy
        # entirely would authorize nothing (proven in a separate test
        # below).
        auth_policy = AuthorizationPolicy.authorize(remote.node_id, {"evidence_exchange"})

        evaluation = evaluate_join_request(
            request,
            local_node_id=local.node_id,
            local_identity=local,
            attempt_contact=True,
            policy=policy,
            transport=transport,
            authorization_policy=auth_policy,
            requested_capabilities=["evidence_exchange"],
        )

    # --- IDENTITY stage ---
    assert evaluation.contacted is True
    assert evaluation.verified_contact is not None
    assert evaluation.is_verified_peer is True
    assert evaluation.verified_contact.remote_node_id == remote.node_id
    assert evaluation.verified_contact.identity_status == identity_module.CRYPTOGRAPHICALLY_VERIFIED

    # --- BOUNDED HANDSHAKE: exactly the fixed 2-request budget, no more ---
    assert record["paths"] == [HANDSHAKE_PATH, IDENTITY_RESPOND_PATH]

    # --- AUTHORIZATION stage: explicit grant, not inferred from identity ---
    assert evaluation.capability_decision is not None
    assert evaluation.capability_decision.is_authorized("evidence_exchange")
    # codex_update must never be authorizable regardless of any of this.
    assert not evaluation.capability_decision.is_authorized("codex_update")

    # --- Translate to the existing contact ledger vocabulary ---
    attempt = to_contact_attempt(evaluation)
    assert attempt.state == "IDENTITY_VERIFIED"
    assert attempt.contact_type == "REAL_INDEPENDENT_PEER"
    assert attempt.is_evidence_backed

    ledger = ContactLedger()
    # ContactLedger enforces that an evidence-backed state cannot be the
    # FIRST recorded entry for a destination -- there must be a prior
    # CONTACT_PATH_FOUND/CONTACT_ATTEMPTED entry first. This mirrors real
    # usage: an operator/caller records the path-found stage (this
    # module's own to_contact_attempt() output when attempt_contact=False)
    # before recording the verified-identity stage.
    from lantern.contact_ledger import ContactAttempt
    path_found = ContactAttempt(destination=attempt.destination, state="CONTACT_PATH_FOUND")
    ledger.record(path_found)
    recorded = ledger.record(attempt)
    assert recorded in ledger.real_peer_contacts()
    summary = ledger.summary()
    # IDENTITY_VERIFIED alone is not COLLABORATION_ACTIVE/NEGOTIATED --
    # peer_contact_status must remain NOT_ESTABLISHED even for a fully
    # verified identity, because trust/authority are separate decisions.
    assert summary["peer_contact_status"] == "NOT_ESTABLISHED"


def test_identity_verified_without_explicit_policy_authorizes_nothing(tmp_path: Path):
    """Identity verification must never imply authorization. With no
    authorization_policy supplied, capability_decision.authorized_capabilities
    must be empty even though identity_status is CRYPTOGRAPHICALLY_VERIFIED.
    """
    local = _make_identity(tmp_path, "local-node")
    remote = _make_identity(tmp_path, "remote-node")
    state = _NodeState(
        node_id=remote.node_id,
        identity=remote,
        capabilities={**DEFAULT_CAPABILITIES, "identity_proof": True},
    )

    with _remote_server(state) as ((host, port), record):
        endpoint = f"http://{host}:{port}"
        monitor = JoinMonitor(tmp_path / "joins.jsonl")
        request = _submit_join(monitor, node_id=remote.node_id, peer_endpoint=endpoint)

        policy = NetworkContactPolicy(allow_loopback_for_testing=True, allowed_ports=frozenset(range(1, 65536)))
        transport = NetworkContactTransport(policy=policy, allow_loopback_for_testing=True)

        evaluation = evaluate_join_request(
            request,
            local_node_id=local.node_id,
            local_identity=local,
            attempt_contact=True,
            policy=policy,
            transport=transport,
            # authorization_policy intentionally omitted (defaults to None)
        )

    assert evaluation.is_verified_peer is True
    assert evaluation.capability_decision is not None
    assert evaluation.capability_decision.authorized_capabilities == frozenset()
    assert evaluation.capability_decision.authorized is False


def test_compass_orientation_over_verified_peer_never_asserts_allowed_without_decision(tmp_path: Path):
    """Compass, fed via orient_from_evaluation(), must report web_research
    (or any capability) as allowed only because a real CapabilityDecision
    said so -- never because identity was verified, never by default.
    """
    local = _make_identity(tmp_path, "local-node")
    remote = _make_identity(tmp_path, "remote-node")
    state = _NodeState(
        node_id=remote.node_id,
        identity=remote,
        capabilities={**DEFAULT_CAPABILITIES, "identity_proof": True},
    )
    registry = create_default_registry()

    with _remote_server(state) as ((host, port), record):
        endpoint = f"http://{host}:{port}"
        monitor = JoinMonitor(tmp_path / "joins.jsonl")
        request = _submit_join(monitor, node_id=remote.node_id, peer_endpoint=endpoint)

        policy = NetworkContactPolicy(allow_loopback_for_testing=True, allowed_ports=frozenset(range(1, 65536)))
        transport = NetworkContactTransport(policy=policy, allow_loopback_for_testing=True)

        # No authorization policy -> nothing authorized.
        evaluation_unauthorized = evaluate_join_request(
            request, local_node_id=local.node_id, local_identity=local,
            attempt_contact=True, policy=policy, transport=transport,
        )

    reading_unauthorized = orient_from_evaluation(evaluation_unauthorized, registry=registry)
    # Every capability must be reported not-allowed: identity verification
    # alone granted nothing.
    assert all(not action.allowed for action in reading_unauthorized.what_is_allowed)
    # The verified-but-unauthorized contact should still surface as
    # something Compass considers worth attention (WHAT is next).
    assert any(item.kind == "open_contact" for item in reading_unauthorized.what_is_next)


def test_receiver_evaluation_serializes_without_secrets(tmp_path: Path):
    local = _make_identity(tmp_path, "local-node")
    remote = _make_identity(tmp_path, "remote-node")
    state = _NodeState(
        node_id=remote.node_id,
        identity=remote,
        capabilities={**DEFAULT_CAPABILITIES, "identity_proof": True},
    )
    with _remote_server(state) as ((host, port), record):
        endpoint = f"http://{host}:{port}"
        monitor = JoinMonitor(tmp_path / "joins.jsonl")
        request = _submit_join(monitor, node_id=remote.node_id, peer_endpoint=endpoint)
        policy = NetworkContactPolicy(allow_loopback_for_testing=True, allowed_ports=frozenset(range(1, 65536)))
        transport = NetworkContactTransport(policy=policy, allow_loopback_for_testing=True)
        evaluation = evaluate_join_request(
            request, local_node_id=local.node_id, local_identity=local,
            attempt_contact=True, policy=policy, transport=transport,
        )
    blob = json.dumps(evaluation.to_dict())
    assert "private_key" not in blob
    assert bytes(local.identity_dir.joinpath("private_key.bin").read_bytes()).hex() not in blob
    assert bytes(remote.identity_dir.joinpath("private_key.bin").read_bytes()).hex() not in blob
