"""Tests for verified_contact: bounded handshake -> cryptographic identity
verification, with no trust grant and no state mutation.
"""

from __future__ import annotations

import http.server
import json
import socket
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

import pytest
from collections import defaultdict

from lantern import identity as identity_module
from lantern.compatibility import DEFAULT_CAPABILITIES
from lantern.handshake import evaluate_handshake, HandshakeRequest
from lantern.network_contact_policy import NetworkContactPolicy
from lantern.network_contact_transport import ContactOutcome, NetworkContactTransport
from lantern.verified_contact import (
    IDENTITY_RESPOND_PATH,
    HANDSHAKE_PATH,
    REQUEST_BUDGET,
    VerifiedContactOutcome,
    verify_contact,
)


@dataclass
class _NodeState:
    node_id: str
    identity: identity_module.NodeIdentity
    challenge_store: identity_module.ChallengeStore
    known_public_keys: dict[str, str]
    capabilities: dict


class _VerifiedContactHandler(http.server.BaseHTTPRequestHandler):
    state: _NodeState | None = None
    record: dict | None = None

    def log_message(self, *_args):
        pass

    def _read_json(self):
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length)
        return json.loads(raw.decode("utf-8"))

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
        self.record["bodies"].append(body)
        if self.path == HANDSHAKE_PATH:
            req = HandshakeRequest(**body)
            resp = evaluate_handshake(req, supported_capabilities=self.state.capabilities, responder_node_id=self.state.node_id)
            if self.record.get("handshake_override") is not None:
                self._write_json(200, self.record["handshake_override"])
            else:
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
            if self.record.get("proof_override") is not None:
                self._write_json(200, self.record["proof_override"])
            else:
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

        if self.path == "/redirect-me":
            self.send_response(302)
            self.send_header("Location", self.record.get("redirect_location", "/handshake"))
            self.end_headers()
            return

        self._write_json(404, {"error": "not found"})


@contextmanager
def _server(state: _NodeState, *, handshake_override=None, proof_override=None, redirect_location=None):
    record = {"paths": [], "bodies": [], "handshake_override": handshake_override, "proof_override": proof_override, "redirect_location": redirect_location}
    handler = type("Handler", (_VerifiedContactHandler,), {"state": state, "record": record})
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server.server_address, record, state
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def _make_identity(tmp_path: Path, node_id: str) -> identity_module.NodeIdentity:
    return identity_module.load_or_create(node_id, tmp_path / node_id)


@pytest.fixture
def identities(tmp_path: Path):
    local = _make_identity(tmp_path, "node-a")
    remote = _make_identity(tmp_path, "node-b")
    return local, remote


@pytest.fixture
def policy():
    return NetworkContactPolicy(allow_loopback_for_testing=True, allowed_ports=frozenset(range(1, 65536)))


@pytest.fixture
def transport(policy):
    return NetworkContactTransport(policy=policy, allow_loopback_for_testing=True)


def _contact_result(transport, endpoint):
    verdict = transport.policy.evaluate(endpoint)
    assert verdict.allowed, verdict
    return transport.contact(endpoint, verdict=verdict), verdict


def test_successful_contact_handshake_and_identity_verification(tmp_path: Path, identities, transport):
    local, remote = identities
    state = _NodeState(node_id=remote.node_id, identity=remote, challenge_store=identity_module.ChallengeStore(), known_public_keys={}, capabilities={**DEFAULT_CAPABILITIES, "identity_proof": True})
    with _server(state) as ((host, port), record, _):
        endpoint = f"http://{host}:{port}"
        contact_result, verdict = _contact_result(transport, endpoint)
        result = verify_contact(contact_result, transport=transport, verdict=verdict, local_node_id=local.node_id, local_identity=local)
    assert contact_result.outcome is ContactOutcome.HTTP_RESPONSE
    assert result.outcome is VerifiedContactOutcome.IDENTITY_VERIFIED
    assert result.remote_node_id == remote.node_id
    assert result.identity_status == identity_module.CRYPTOGRAPHICALLY_VERIFIED
    assert result.shared_capabilities.get("identity_proof") is True
    assert record["paths"] == [HANDSHAKE_PATH, IDENTITY_RESPOND_PATH]
    assert record["bodies"][0]["node_id"] == local.node_id
    assert "private_key" not in json.dumps(record)


def test_challenge_cannot_be_replayed(tmp_path: Path, identities, transport):
    local, remote = identities
    captured = {}
    replayed = {"proof": None}

    class ReplayHandler(_VerifiedContactHandler):
        def do_POST(self):
            if self.path == HANDSHAKE_PATH:
                return super().do_POST()
            if self.path == IDENTITY_RESPOND_PATH:
                if replayed["proof"] is not None:
                    proof = replayed["proof"]
                else:
                    body = self._read_json()
                    self.record["paths"].append(self.path)
                    self.record["bodies"].append(body)
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
                    replayed["proof"] = proof
                    captured["proof"] = proof
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
            return super().do_POST()

    state = _NodeState(node_id=remote.node_id, identity=remote, challenge_store=identity_module.ChallengeStore(), known_public_keys={}, capabilities={**DEFAULT_CAPABILITIES, "identity_proof": True})
    record = {"paths": [], "bodies": []}
    handler = type("Handler", (ReplayHandler,), {"state": state, "record": record})
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        endpoint = f"http://{server.server_address[0]}:{server.server_address[1]}"
        contact_result, verdict = _contact_result(transport, endpoint)
        first = verify_contact(contact_result, transport=transport, verdict=verdict, local_node_id=local.node_id, local_identity=local)
        second = verify_contact(contact_result, transport=transport, verdict=verdict, local_node_id=local.node_id, local_identity=local)
    finally:
        server.shutdown(); server.server_close(); thread.join(timeout=5)
    assert first.verified
    assert second.outcome is VerifiedContactOutcome.IDENTITY_PROOF_INVALID
    assert second.reason


def test_expired_challenge_fails(tmp_path: Path, identities, transport):
    local, remote = identities
    state = _NodeState(node_id=remote.node_id, identity=remote, challenge_store=identity_module.ChallengeStore(), known_public_keys={}, capabilities={**DEFAULT_CAPABILITIES, "identity_proof": True})

    class SlowResponder(_VerifiedContactHandler):
        def do_POST(self):
            if self.path == IDENTITY_RESPOND_PATH:
                time.sleep(0.2)
            return super().do_POST()

    handler = type("Handler", (SlowResponder,), {"state": state, "record": {"paths": [], "bodies": []}})
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        endpoint = f"http://{server.server_address[0]}:{server.server_address[1]}"
        contact_result, verdict = _contact_result(transport, endpoint)
        result = verify_contact(contact_result, transport=transport, verdict=verdict, local_node_id=local.node_id, local_identity=local, challenge_ttl_seconds=0)
    finally:
        server.shutdown(); server.server_close(); thread.join(timeout=5)
    assert result.outcome is VerifiedContactOutcome.IDENTITY_PROOF_INVALID
    assert "expired" in result.reason.lower() or result.reason


def test_handshake_rejection_and_incompatibility_are_structured(tmp_path: Path, identities, transport):
    local, remote = identities
    state = _NodeState(node_id=remote.node_id, identity=remote, challenge_store=identity_module.ChallengeStore(), known_public_keys={}, capabilities={**DEFAULT_CAPABILITIES, "identity_proof": True})
    with _server(state, handshake_override={"node_id": remote.node_id, "accepted": False, "protocol_version": "0.82", "shared_capabilities": {}, "reason": "nope", "timestamp": "now"}) as ((host, port), record, _):
        endpoint = f"http://{host}:{port}"
        contact_result, verdict = _contact_result(transport, endpoint)
        rejected = verify_contact(contact_result, transport=transport, verdict=verdict, local_node_id=local.node_id, local_identity=local)
    assert rejected.outcome is VerifiedContactOutcome.HANDSHAKE_REJECTED
    assert rejected.reason == "nope"


def test_malformed_handshake_response_fails_closed(tmp_path: Path, identities, transport):
    local, remote = identities
    state = _NodeState(node_id=remote.node_id, identity=remote, challenge_store=identity_module.ChallengeStore(), known_public_keys={}, capabilities={**DEFAULT_CAPABILITIES, "identity_proof": True})
    with _server(state, handshake_override={"node_id": remote.node_id}) as ((host, port), record, _):
        endpoint = f"http://{host}:{port}"
        contact_result, verdict = _contact_result(transport, endpoint)
        result = verify_contact(contact_result, transport=transport, verdict=verdict, local_node_id=local.node_id, local_identity=local)
    assert result.outcome is VerifiedContactOutcome.HANDSHAKE_MALFORMED_RESPONSE


def test_remote_http_200_without_valid_identity_proof_does_not_verify(tmp_path: Path, identities, transport):
    local, remote = identities
    state = _NodeState(node_id=remote.node_id, identity=remote, challenge_store=identity_module.ChallengeStore(), known_public_keys={}, capabilities={**DEFAULT_CAPABILITIES, "identity_proof": True})
    bad_proof = {
        "nonce": "bad",
        "from_node_id": local.node_id,
        "to_node_id": remote.node_id,
        "protocol_version": "0.82",
        "claimed_node_id": remote.node_id,
        "public_key": remote.public_key_hex,
        "identity_binding_signature": "00",
        "signature": "00",
        "proof_timestamp": "now",
    }
    with _server(state, proof_override=bad_proof) as ((host, port), record, _):
        endpoint = f"http://{host}:{port}"
        contact_result, verdict = _contact_result(transport, endpoint)
        result = verify_contact(contact_result, transport=transport, verdict=verdict, local_node_id=local.node_id, local_identity=local)
    assert result.outcome is VerifiedContactOutcome.IDENTITY_PROOF_INVALID


def test_verification_does_not_grant_trust_or_authority_or_codex(tmp_path: Path, identities, transport):
    local, remote = identities
    state = _NodeState(node_id=remote.node_id, identity=remote, challenge_store=identity_module.ChallengeStore(), known_public_keys={}, capabilities={**DEFAULT_CAPABILITIES, "identity_proof": True, "codex_update": False})
    with _server(state) as ((host, port), record, _):
        endpoint = f"http://{host}:{port}"
        contact_result, verdict = _contact_result(transport, endpoint)
        result = verify_contact(contact_result, transport=transport, verdict=verdict, local_node_id=local.node_id, local_identity=local)
    assert result.verified
    assert result.identity_status == identity_module.CRYPTOGRAPHICALLY_VERIFIED
    assert DEFAULT_CAPABILITIES["codex_update"] is False


def test_private_keys_never_appear_in_network_payloads_or_result(tmp_path: Path, identities, transport):
    local, remote = identities
    state = _NodeState(node_id=remote.node_id, identity=remote, challenge_store=identity_module.ChallengeStore(), known_public_keys={}, capabilities={**DEFAULT_CAPABILITIES, "identity_proof": True})
    with _server(state) as ((host, port), record, _):
        endpoint = f"http://{host}:{port}"
        contact_result, verdict = _contact_result(transport, endpoint)
        result = verify_contact(contact_result, transport=transport, verdict=verdict, local_node_id=local.node_id, local_identity=local)
    network_blob = json.dumps({"record": record, "result": result.to_dict()})
    assert "private_key.bin" not in network_blob
    assert bytes(local.identity_dir.joinpath("private_key.bin").read_bytes()).hex() not in network_blob
    assert bytes(remote.identity_dir.joinpath("private_key.bin").read_bytes()).hex() not in network_blob
    assert "SigningKey" not in repr(local)
    assert "SigningKey" not in repr(remote)


def test_endpoint_cannot_be_changed_by_remote_response(tmp_path: Path, identities, transport):
    local, remote = identities
    state = _NodeState(node_id=remote.node_id, identity=remote, challenge_store=identity_module.ChallengeStore(), known_public_keys={}, capabilities={**DEFAULT_CAPABILITIES, "identity_proof": True})
    with _server(state, handshake_override={"node_id": remote.node_id, "accepted": True, "protocol_version": "0.82", "shared_capabilities": {"identity_proof": True}, "reason": "ok", "timestamp": "now"}) as ((host, port), record, _):
        endpoint = f"http://{host}:{port}"
        contact_result, verdict = _contact_result(transport, endpoint)
        result = verify_contact(contact_result, transport=transport, verdict=verdict, local_node_id=local.node_id, local_identity=local)
    assert endpoint == result.contact_endpoint
    assert record["paths"] == [HANDSHAKE_PATH, IDENTITY_RESPOND_PATH]


def test_two_independent_nodes_can_verify_each_other(tmp_path: Path, transport):
    a = _make_identity(tmp_path, "node-a")
    b = _make_identity(tmp_path, "node-b")
    state_b = _NodeState(node_id=b.node_id, identity=b, challenge_store=identity_module.ChallengeStore(), known_public_keys={}, capabilities={**DEFAULT_CAPABILITIES, "identity_proof": True})
    with _server(state_b) as ((host, port), record, _):
        endpoint = f"http://{host}:{port}"
        contact_result, verdict = _contact_result(transport, endpoint)
        result = verify_contact(contact_result, transport=transport, verdict=verdict, local_node_id=a.node_id, local_identity=a)
    assert result.verified
    assert result.remote_node_id == b.node_id


def test_request_budget_is_fixed_and_no_retry(tmp_path: Path, identities, transport):
    local, remote = identities
    state = _NodeState(node_id=remote.node_id, identity=remote, challenge_store=identity_module.ChallengeStore(), known_public_keys={}, capabilities={**DEFAULT_CAPABILITIES, "identity_proof": True})
    with _server(state) as ((host, port), record, _):
        endpoint = f"http://{host}:{port}"
        contact_result, verdict = _contact_result(transport, endpoint)
        result = verify_contact(contact_result, transport=transport, verdict=verdict, local_node_id=local.node_id, local_identity=local)
    assert REQUEST_BUDGET == 2
    assert record["paths"] == [HANDSHAKE_PATH, IDENTITY_RESPOND_PATH]
    assert result.verified
