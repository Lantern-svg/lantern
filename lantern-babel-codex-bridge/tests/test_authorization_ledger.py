"""Authorization ledger: the origin of authority must be explicit.

Every test here enforces the invariant:

    A node may prove who it is.
    A node may NOT manufacture its own authority.

Identity is established via the existing lantern.identity PoP machinery.
Authorization originates ONLY from:
  - the human operator ceremony (BOOTSTRAP / RECOVERY events), or
  - runtime admission performed by a node within the scope the
    operator explicitly delegated to it (ADMISSION events).

The required model maps to these tests:
  A. fresh node: identity, no authorization
  B. fresh node cannot authorize itself
  C. valid root/bootstrap ceremony authorizes the initial node
  D. authorized node performs an explicitly permitted delegation
  E. unauthorized node cannot authorize another node
  F. peer admission requires a proven session + verified identity
  G. authorization provenance is fully preserved
  H. invalid/tampered authorization is rejected (fail-closed)
  I. recovery cannot be performed by the recovering node alone
  J. existing security invariants continue to pass (full suite)
plus a REAL two-node subprocess end-to-end admission ceremony.
"""

from __future__ import annotations

import hashlib
import json
import socket
import subprocess
import sys
import time
from pathlib import Path
from urllib.request import Request, urlopen

import pytest

from lantern import identity as identity_module
from lantern.authorization_ledger import (
    AuthorizationLedger,
    AuthorizationLedgerError,
    PROVENANCE_FIELDS,
)
from lantern.bootstrap_node import LanternNode, public_key_fingerprint
from lantern.capability_authorization import EMPTY_POLICY
from lantern.protocol import PROTOCOL_VERSION

PROJECT_ROOT = Path(__file__).parent.parent


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _wait_for_health(base: str, timeout: float = 5.0) -> dict:
    deadline = time.time() + timeout
    last_error = None
    while time.time() < deadline:
        try:
            with urlopen(base + "/health", timeout=1) as response:
                return json.loads(response.read())
        except OSError as exc:
            last_error = exc
            time.sleep(0.05)
    raise TimeoutError(f"Node at {base} did not become healthy: {last_error}")


def _request(url: str, method: str = "GET", payload: dict | None = None):
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    request = Request(url, data=data, method=method, headers={"Content-Type": "application/json"})
    with urlopen(request, timeout=5) as response:
        return response.status, json.loads(response.read())


def _start_node_subprocess(node_id: str, port: int, data_dir: Path, extra_args=None) -> subprocess.Popen:
    return subprocess.Popen(
        [
            sys.executable, "-m", "lantern.bootstrap_node",
            "--node-id", node_id,
            "--host", "127.0.0.1",
            "--port", str(port),
            "--data-dir", str(data_dir),
            *(extra_args or []),
        ],
        cwd=PROJECT_ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )


def _stop(process: subprocess.Popen):
    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=3)


def _client_identity(data_dir: Path, node_id: str):
    data_dir.mkdir(parents=True, exist_ok=True)
    identity_dir = identity_module.default_identity_dir(data_dir, node_id)
    return identity_module.load_or_create(node_id, identity_dir)


def _ledger(tmp_path, node_id="lantern-auth-node"):
    return AuthorizationLedger(
        tmp_path / "authorization_ledger.jsonl", owner_node_id=node_id
    )


def _make_node(tmp_path, ledger, node_id="lantern-auth-node", policy=None):
    node_root = tmp_path / "node"
    node_root.mkdir(parents=True, exist_ok=True)
    return LanternNode(
        node_id=node_id,
        chronicle_path=node_root / f"{node_id}.jsonl",
        identity_dir=identity_module.default_identity_dir(node_root, node_id),
        authorization_policy=policy if policy is not None else _policy_with(ledger),
        authorization_ledger=ledger,
    )


def _policy_with(ledger: AuthorizationLedger):
    """Startup derivation exactly as main() performs it: operator
    static entries plus ledger admissions, fail-closed on a broken
    chain."""
    policy = EMPTY_POLICY
    if not ledger.chain_valid:
        return policy
    for admitted_node, admitted_caps in ledger.admissions_policy().grants.items():
        policy = policy.merged_with(admitted_node, admitted_caps)
    return policy


def _establish_session(server_node: LanternNode, client_identity):
    """Register client identity + open a two-phase PoP session using the
    node's own primitives (no HTTP)."""
    challenge = server_node.issue_identity_challenge(client_identity.node_id)
    binding = json.loads(
        (client_identity.identity_dir / "binding.json").read_text()
    )
    challenge_obj = identity_module.Challenge(
        nonce=challenge["nonce"], from_node_id=challenge["from_node_id"],
        to_node_id=challenge["to_node_id"], protocol_version=challenge["protocol_version"],
        issued_at=0.0,
        ttl_seconds=challenge.get("ttl_seconds", identity_module.DEFAULT_CHALLENGE_TTL_SECONDS),
    )
    proof = identity_module.respond_to_challenge(challenge_obj, client_identity, binding["signature"])
    verify = server_node.verify_identity_proof({
        "nonce": proof.nonce, "from_node_id": proof.from_node_id,
        "to_node_id": proof.to_node_id, "protocol_version": proof.protocol_version,
        "claimed_node_id": proof.claimed_node_id, "public_key": proof.public_key,
        "identity_binding_signature": proof.identity_binding_signature,
        "signature": proof.signature, "proof_timestamp": proof.proof_timestamp,
    })
    assert verify["verified"] is True, verify
    phase1 = server_node.open_session(client_identity.node_id)
    assert "nonce" in phase1
    session_challenge = identity_module.Challenge(
        nonce=phase1["nonce"], from_node_id=phase1["from_node_id"],
        to_node_id=phase1["to_node_id"], protocol_version=phase1["protocol_version"],
        issued_at=0.0, ttl_seconds=phase1.get("ttl_seconds", 60.0),
    )
    session_proof = identity_module.respond_to_challenge(session_challenge, client_identity, binding["signature"])
    session = server_node.open_session(client_identity.node_id, proof_data={
        "nonce": session_proof.nonce, "from_node_id": session_proof.from_node_id,
        "to_node_id": session_proof.to_node_id, "protocol_version": session_proof.protocol_version,
        "claimed_node_id": session_proof.claimed_node_id, "public_key": session_proof.public_key,
        "identity_binding_signature": session_proof.identity_binding_signature,
        "signature": session_proof.signature, "proof_timestamp": session_proof.proof_timestamp,
    })
    assert session.get("created") is True, session
    return session["session_id"]


# ---------------------------------------------------------------------------
# A. Fresh node: identity, no authorization
# ---------------------------------------------------------------------------


def test_fresh_node_has_identity_but_no_authorization(tmp_path):
    ledger = _ledger(tmp_path)
    node = _make_node(tmp_path, ledger)
    # identity established:
    assert node.crypto_identity.public_key_hex
    # ...but authorization is EMPTY in every dimension:
    assert ledger.events() == []
    assert ledger.admission_authority() == frozenset()
    assert ledger.admissions_policy().grants == {}
    assert node.authorization_policy.grants == {}


# ---------------------------------------------------------------------------
# B. A node cannot authorize itself
# ---------------------------------------------------------------------------


def test_node_cannot_authorize_itself(tmp_path):
    ledger = _ledger(tmp_path, node_id="self-seeker")
    node = _make_node(tmp_path, ledger, node_id="self-seeker")
    # (1) ledger-level: self-admission event refused
    with pytest.raises(AuthorizationLedgerError, match="self-authorization"):
        ledger.admit_peer(
            subject_node="self-seeker", subject_fingerprint="f" * 64,
            scope=["evidence_exchange"], evidence="self-grant attempt",
        )
    # (2) runtime: even with a valid session and delegated scope, a node
    #     never admits itself
    ledger.record_operator_ceremony(
        authorize_entries=[], admission_scope=["evidence_exchange"],
    )
    result = node.request_authorization(
        "any-session", "self-seeker", ["evidence_exchange"]
    )
    assert result["status"] == "denied"
    assert result["reason"] == "SELF_ADMISSION_PROHIBITED"
    assert ledger.events()[-1]["event_type"] == "BOOTSTRAP"  # nothing else appended
    # (3) an unauthorized node cannot mint a BOOTSTRAP event either:
    #     root ceremony events may only be authored by the operator, and
    #     the ledger refuses undefined portable delegation outright.
    with pytest.raises(AuthorizationLedgerError, match="operator"):
        ledger._append("BOOTSTRAP", authority="self-seeker",
                       subject_node="self-seeker", subject_fingerprint="",
                       scope=frozenset(["evidence_exchange"]), delegable=True,
                       evidence="forged")


# ---------------------------------------------------------------------------
# C. Valid root/bootstrap ceremony authorizes the initial node
# ---------------------------------------------------------------------------


def test_operator_bootstrap_ceremony(tmp_path):
    ledger = _ledger(tmp_path)
    recorded = ledger.record_operator_ceremony(
        authorize_entries=[("peer-x", ["belief_query"])],
        admission_scope=["evidence_exchange"],
    )
    # one static grant + one delegated admission authority event
    assert len(recorded) == 2
    assert ledger.chain_valid is True
    events = ledger.events()
    types = [e["event_type"] for e in events]
    assert types == ["BOOTSTRAP", "BOOTSTRAP"]
    assert events[0]["authority"] == "operator"
    assert events[0]["subject_node"] == "peer-x"
    assert events[0]["scope"] == ["belief_query"]
    assert events[1]["delegable"] is True
    assert events[1]["subject_node"] == "lantern-auth-node"
    assert ledger.admission_authority() == frozenset({"evidence_exchange"})
    # idempotent: re-running the same ceremony records NOTHING new
    again = ledger.record_operator_ceremony(
        authorize_entries=[("peer-x", ["belief_query"])],
        admission_scope=["evidence_exchange"],
    )
    assert again == []
    assert len(ledger.events()) == 2


# ---------------------------------------------------------------------------
# D. Authorized node performs an explicitly permitted delegation (admission)
# ---------------------------------------------------------------------------


def test_authorized_node_admits_peer_within_delegated_scope(tmp_path):
    ledger = _ledger(tmp_path)
    ledger.record_operator_ceremony(
        authorize_entries=[], admission_scope=["evidence_exchange"],
    )
    node = _make_node(tmp_path, ledger)
    client = _client_identity(tmp_path / "peer-identity", "peer-joiner")
    session_id = _establish_session(node, client)
    result = node.request_authorization(
        session_id, "peer-joiner", ["evidence_exchange"]
    )
    assert result["status"] == "admitted", result
    assert result["capabilities"] == ["evidence_exchange"]
    assert result["authority"] == "delegated:lantern-auth-node"
    # policy actually updated for the peer:
    assert node.authorization_policy.allows("peer-joiner", "evidence_exchange")
    # provenance: the ADMISSION event carries the verified fingerprint
    event = ledger.events()[-1]
    assert event["event_type"] == "ADMISSION"
    assert event["authority"] == "lantern-auth-node"
    assert event["subject_fingerprint"] == public_key_fingerprint(
        client.public_key_hex
    )
    # restart persistence: a fresh ledger at the same path still yields
    # the admission (operator re-derives policy at startup)
    reloaded = AuthorizationLedger(
        ledger.path, owner_node_id="lantern-auth-node"
    )
    assert reloaded.chain_valid is True
    assert reloaded.admissions_policy().allows("peer-joiner", "evidence_exchange")
    # re-request is recognized, no duplicate event:
    before = len(reloaded.events())
    node2 = _make_node(tmp_path, reloaded)
    session2 = _establish_session(node2, client)
    result2 = node2.request_authorization(session2, "peer-joiner", ["evidence_exchange"])
    assert result2["status"] == "already_authorized"
    assert len(reloaded.events()) == before


# ---------------------------------------------------------------------------
# E. Unauthorized node cannot authorize another node
# ---------------------------------------------------------------------------


def test_unauthorized_node_cannot_admit(tmp_path):
    ledger = _ledger(tmp_path)
    # operator granted a STATIC capability to a peer, but delegated NO
    # admission authority to this node:
    ledger.record_operator_ceremony(
        authorize_entries=[("peer-x", ["belief_query"])],
        admission_scope=[],
    )
    node = _make_node(tmp_path, ledger)
    client = _client_identity(tmp_path / "peer-identity", "peer-joiner")
    session_id = _establish_session(node, client)
    result = node.request_authorization(session_id, "peer-joiner", ["evidence_exchange"])
    assert result["status"] == "denied"
    assert result["reason"] == "ADMISSION_SCOPE_EXCEEDED"
    assert result["delegated_scope"] == []
    # no ADMISSION event was created, policy unchanged:
    assert all(e["event_type"] != "ADMISSION" for e in ledger.events())
    assert not node.authorization_policy.allows("peer-joiner", "evidence_exchange")


# ---------------------------------------------------------------------------
# F. Peer admission requires a proven session + verified identity
# ---------------------------------------------------------------------------


def test_admission_requires_verified_session_and_identity(tmp_path):
    ledger = _ledger(tmp_path)
    ledger.record_operator_ceremony(
        authorize_entries=[], admission_scope=["evidence_exchange"],
    )
    node = _make_node(tmp_path, ledger)
    # no session at all:
    result = node.request_authorization(
        "not-a-session", "peer-joiner", ["evidence_exchange"]
    )
    assert result["status"] == "denied"
    assert "session" in result["reason"].lower()
    client = _client_identity(tmp_path / "peer-identity", "peer-joiner")
    session_id = _establish_session(node, client)
    # empty capability request is refused:
    result = node.request_authorization(session_id, "peer-joiner", [])
    assert result["status"] == "denied"
    # structurally unauthorizable capabilities are refused at ANY scope:
    result = node.request_authorization(session_id, "peer-joiner", ["codex_update"])
    assert result["status"] == "denied"
    assert result["reason"] == "STRUCTURALLY_UNAUTHORIZABLE"
    # valid session, but identity never verified (unknown public key):
    node._known_public_keys.pop("peer-joiner", None)
    result = node.request_authorization(session_id, "peer-joiner", ["evidence_exchange"])
    assert result["status"] == "denied"
    assert result["reason"] == "IDENTITY_NOT_VERIFIED"


# ---------------------------------------------------------------------------
# G. Authorization provenance is preserved
# ---------------------------------------------------------------------------


def test_provenance_fields_complete(tmp_path):
    ledger = _ledger(tmp_path)
    ledger.record_operator_ceremony(
        authorize_entries=[("peer-x", ["belief_query"])],
        admission_scope=["evidence_exchange"],
    )
    node = _make_node(tmp_path, ledger)
    client = _client_identity(tmp_path / "peer-identity", "peer-joiner")
    session_id = _establish_session(node, client)
    node.request_authorization(session_id, "peer-joiner", ["evidence_exchange"])
    for event in ledger.events():
        for field_name in PROVENANCE_FIELDS:
            assert field_name in event, f"missing provenance field {field_name}"
        assert event["protocol_version"] == PROTOCOL_VERSION
        assert event["timestamp"]
        assert event["evidence"]
        assert event["scope"]
    admission = [e for e in ledger.events() if e["event_type"] == "ADMISSION"][0]
    required = {
        "authorizing authority": admission["authority"],
        "subject node": admission["subject_node"],
        "identity/fingerprint": admission["subject_fingerprint"],
        "authorization/delegation scope": admission["scope"],
        "timestamp": admission["timestamp"],
        "protocol version": admission["protocol_version"],
        "evidence/provenance": admission["evidence"],
        "event kind": admission["event_type"],
    }
    assert all(str(v) for v in required.values())
    assert admission["subject_fingerprint"] == hashlib.sha256(
        bytes.fromhex(client.public_key_hex)
    ).hexdigest()


# ---------------------------------------------------------------------------
# H. Invalid/tampered authorization is rejected (fail-closed)
# ---------------------------------------------------------------------------


def test_tampered_ledger_fails_closed(tmp_path):
    ledger = _ledger(tmp_path)
    ledger.record_operator_ceremony(
        authorize_entries=[], admission_scope=["evidence_exchange"],
    )
    node = _make_node(tmp_path, ledger)
    client = _client_identity(tmp_path / "peer-identity", "peer-joiner")
    session_id = _establish_session(node, client)
    node.request_authorization(session_id, "peer-joiner", ["evidence_exchange"])
    # TAMPER: silently widen the granted scope in the on-disk ledger
    lines = ledger.path.read_text().splitlines()
    tampered = []
    for line in lines:
        event = json.loads(line)
        if event["event_type"] == "ADMISSION":
            event["scope"] = ["evidence_exchange", "codex_update", "belief_query"]
            # digest left untouched on purpose: the tamper must be DETECTED
        tampered.append(json.dumps(event, sort_keys=True))
    ledger.path.write_text("\n".join(tampered) + "\n")
    reloaded = AuthorizationLedger(
        ledger.path, owner_node_id="lantern-auth-node"
    )
    assert reloaded.chain_valid is False
    # fail-closed: zero authority derived from a tampered chain
    assert reloaded.events() == []
    assert reloaded.admission_authority() == frozenset()
    assert reloaded.admissions_policy().grants == {}
    with pytest.raises(AuthorizationLedgerError):
        reloaded.admit_peer(
            subject_node="peer-joiner", subject_fingerprint="f" * 64,
            scope=["evidence_exchange"], evidence="tampered-state append",
        )


# ---------------------------------------------------------------------------
# I. Recovery cannot be performed by the recovering node alone
# ---------------------------------------------------------------------------


def test_recovery_requires_operator_ceremony(tmp_path):
    ledger = _ledger(tmp_path)
    ledger.record_operator_ceremony(
        authorize_entries=[], admission_scope=["evidence_exchange"],
    )
    # (1) authorization state LOST: a fresh ledger at the same path has
    #     no authority, and no runtime path can re-create it:
    ledger.path.unlink()
    fresh = AuthorizationLedger(ledger.path, owner_node_id="lantern-auth-node")
    assert fresh.admission_authority() == frozenset()
    with pytest.raises(AuthorizationLedgerError, match="self-authorization"):
        fresh.admit_peer(
            subject_node="lantern-auth-node", subject_fingerprint="f" * 64,
            scope=["evidence_exchange"], evidence="self-recovery attempt",
        )
    # (2) authorization state CORRUPTED: the node cannot even run the
    #     ceremony on a broken chain -- restoration requires the
    #     operator (clean backup or a deliberate new ledger):
    ledger2 = _ledger(tmp_path)
    ledger2.record_operator_ceremony(
        authorize_entries=[], admission_scope=["evidence_exchange"],
    )
    ledger2.path.write_text("{\"tampered\": true}\n")
    broken = AuthorizationLedger(ledger2.path, owner_node_id="lantern-auth-node")
    assert broken.chain_valid is False
    with pytest.raises(AuthorizationLedgerError, match="self-recover"):
        broken.record_operator_ceremony(
            authorize_entries=[], admission_scope=["evidence_exchange"],
            recovery_note="node tried to recover itself",
        )
    # (3) the legitimate path: the OPERATOR runs the explicit recovery
    #     ceremony, recorded as RECOVERY events with a note:
    ledger2.path.unlink()
    restored = AuthorizationLedger(ledger2.path, owner_node_id="lantern-auth-node")
    restored.record_operator_ceremony(
        authorize_entries=[], admission_scope=["evidence_exchange"],
        recovery_note="operator restored after ledger loss 2026-09-05",
    )
    events = restored.events()
    assert all(e["event_type"] == "RECOVERY" for e in events)
    assert restored.admission_authority() == frozenset({"evidence_exchange"})
    assert "operator restored after ledger loss" in events[0]["evidence"]


# ---------------------------------------------------------------------------
# REAL two-node subprocess end-to-end (synthetic data only)
# ---------------------------------------------------------------------------


def test_real_two_node_admission_ceremony(tmp_path):
    """Root node A (operator-delegated admission scope) admits verified
    peer B at runtime, over real HTTP between two OS processes, through
    the full existing identity-proof + two-phase session machinery.
    B never declares itself authorized; A performs the ceremony."""
    from lantern.bootstrap_client import (
        _open_session_with_proof,
        _verify_identity_with_peer,
    )

    port = _free_port()
    data_dir = tmp_path / "a"
    process = _start_node_subprocess(
        "lantern-auth-root", port, data_dir,
        ["--grant-admission", "evidence_exchange"],
    )
    base = f"http://127.0.0.1:{port}"
    try:
        _wait_for_health(base)
        b_identity = _client_identity(tmp_path / "b-identity", "lantern-joiner-b")

        # joiner proves identity, opens a two-phase PoP session, requests
        _verify_identity_with_peer(base, "lantern-joiner-b", b_identity)
        session = _open_session_with_proof(base, "lantern-joiner-b", b_identity)

        status, denied = _request(
            base + "/authorization/request", "POST",
            {"session_id": session["session_id"], "node_id": "lantern-joiner-b",
             "capabilities": ["belief_query"]},
        )
        assert denied["status"] == "denied"          # out of delegated scope
        assert denied["reason"] == "ADMISSION_SCOPE_EXCEEDED"

        status, admitted = _request(
            base + "/authorization/request", "POST",
            {"session_id": session["session_id"], "node_id": "lantern-joiner-b",
             "capabilities": ["evidence_exchange"]},
        )
        assert admitted["status"] == "admitted", admitted
        assert admitted["authority"] == "delegated:lantern-auth-root"

        # re-request is recognized across the wire:
        status, repeat = _request(
            base + "/authorization/request", "POST",
            {"session_id": session["session_id"], "node_id": "lantern-joiner-b",
             "capabilities": ["evidence_exchange"]},
        )
        assert repeat["status"] == "already_authorized"

        # the ADMISSION event is on A's ledger, with B's verified fingerprint:
        ledger_path = data_dir / "authorization_ledger.jsonl"
        assert ledger_path.exists()
        events = [
            json.loads(line)
            for line in ledger_path.read_text().splitlines()
            if line.strip()
        ]
        admissions = [e for e in events if e["event_type"] == "ADMISSION"]
        assert len(admissions) == 1
        assert admissions[0]["subject_node"] == "lantern-joiner-b"
        assert admissions[0]["subject_fingerprint"] == public_key_fingerprint(
            b_identity.public_key_hex
        )
        assert admissions[0]["authority"] == "lantern-auth-root"

        # a session-less request is refused outright:
        status, nosession = _request(
            base + "/authorization/request", "POST",
            {"session_id": "forged-session", "node_id": "lantern-joiner-b",
             "capabilities": ["evidence_exchange"]},
        )
        assert nosession["status"] == "denied"
    finally:
        _stop(process)


def test_real_two_node_no_delegation_no_admission(tmp_path):
    """Without an explicit operator --grant-admission, the node can NEVER
    admit a peer, no matter how genuine the peer's identity is."""
    from lantern.bootstrap_client import (
        _open_session_with_proof,
        _verify_identity_with_peer,
    )

    port = _free_port()
    data_dir = tmp_path / "plain"
    process = _start_node_subprocess("lantern-plain", port, data_dir)
    base = f"http://127.0.0.1:{port}"
    try:
        _wait_for_health(base)
        b_identity = _client_identity(tmp_path / "b-identity", "lantern-joiner-b")
        _verify_identity_with_peer(base, "lantern-joiner-b", b_identity)
        session = _open_session_with_proof(base, "lantern-joiner-b", b_identity)
        status, result = _request(
            base + "/authorization/request", "POST",
            {"session_id": session["session_id"], "node_id": "lantern-joiner-b",
             "capabilities": ["evidence_exchange"]},
        )
        assert result["status"] == "denied"
        assert result["reason"] == "ADMISSION_SCOPE_EXCEEDED"
        assert result["delegated_scope"] == []
    finally:
        _stop(process)
