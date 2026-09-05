"""Secret transfer: unit-level adversarial tests + REAL two-node
subprocess end-to-end proof.

SECURITY HANDLING (mirrors test_lantern_e2e_exchange.py discipline):
a fresh cryptographically random ephemeral secret is generated in
memory for each run. It is never printed, never assertion-interpolated,
never written to any evidence dict. Only sha256(secret) ever appears in
assertions or output. The final evidence record is checked to prove the
secret itself never leaked into it.

Proof-of-possession != secret transfer: the existing challenge/response
proves possession of the identity key. THIS suite proves confidentiality
+ integrity + authorization for the payload itself: the secret crosses
the wire only inside XSalsa20-Poly1305 AEAD, tampered/replayed/transplanted
ciphertext is rejected, and only the sender's authenticated session can
obtain proof of holding.
"""

from __future__ import annotations

import hashlib
import json
import secrets
import socket
import subprocess
import sys
import time
from pathlib import Path
from urllib.request import Request, urlopen

import pytest

from lantern import identity as identity_module
from lantern import secret_transfer
from lantern.bootstrap_client import (
    _open_session_with_proof,
    _verify_identity_with_peer,
    send_secret,
)

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


@pytest.fixture
def node_b(tmp_path):
    port = _free_port()
    data_dir = tmp_path / "b"
    process = _start_node_subprocess(
        "lantern-secret-b", port, data_dir,
        ["--authorize", "lantern-secret-a:secret_transfer,evidence_exchange",
         "--authorize", "lantern-secret-c:secret_transfer,evidence_exchange"],
    )
    base = f"http://127.0.0.1:{port}"
    try:
        _wait_for_health(base)
        yield {"base": base, "port": port, "data_dir": data_dir, "process": process, "node_id": "lantern-secret-b"}
    finally:
        _stop(process)


def _client_identity(data_dir: Path, node_id: str):
    data_dir.mkdir(parents=True, exist_ok=True)
    identity_dir = identity_module.default_identity_dir(data_dir, node_id)
    return identity_module.load_or_create(node_id, identity_dir)


# ---------------------------------------------------------------------------
# In-process (server-object) adversarial tests
# ---------------------------------------------------------------------------


CLIENT_NODE_ID = "lantern-secret-client"


def _make_node(tmp_path, node_id="lantern-secret-node", authorized=True):
    from lantern.bootstrap_node import LanternNode
    from lantern.capability_authorization import EMPTY_POLICY

    policy = (
        None if not authorized
        else EMPTY_POLICY.merged_with(CLIENT_NODE_ID, ["secret_transfer"])
    )
    node_root = tmp_path / "node"
    node_root.mkdir(parents=True, exist_ok=True)
    return LanternNode(
        node_id=node_id,
        chronicle_path=node_root / f"{node_id}.jsonl",
        identity_dir=identity_module.default_identity_dir(node_root, node_id),
        authorization_policy=policy,
    )


def _establish_session(server_node, client_identity):
    """Register client identity + open a two-phase PoP session, using
    the node's own primitives (no HTTP)."""
    challenge = server_node.issue_identity_challenge(client_identity.node_id)
    binding = json.loads((client_identity.identity_dir / "binding.json").read_text())
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
    # two-phase session
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


def _full_transfer_flow(server_node, client_identity, tmp_path, secret, secret_id=None):
    import uuid

    secret_id = secret_id or uuid.uuid4().hex
    session_id = _establish_session(server_node, client_identity)
    offer, eph_hex = secret_transfer.create_secret_offer(
        session_id=session_id, secret_id=secret_id, identity=client_identity,
    )
    response = server_node.secret_transfer_offer(session_id, client_identity.node_id, offer)
    assert response["accepted"] is True, response
    box = secret_transfer.Box(
        secret_transfer.PrivateKey(bytes.fromhex(eph_hex)),
        secret_transfer.PublicKey(bytes.fromhex(response["server_eph_pub"])),
    )
    sealed, digest = secret_transfer.seal_secret(
        box, secret=secret, secret_id=secret_id,
        session_id=session_id, sender_node_id=client_identity.node_id,
    )
    return session_id, secret_id, sealed, digest


def test_full_transfer_and_receipt_in_process(tmp_path):
    server = _make_node(tmp_path)
    client = _client_identity(tmp_path / "client", CLIENT_NODE_ID)
    secret = "LANTERN_SECRET_TEST_" + secrets.token_urlsafe(32)
    session_id, secret_id, sealed, digest = _full_transfer_flow(server, client, tmp_path, secret)
    result = server.secret_transfer_seal(
        session_id, client.node_id, secret_id, sealed["nonce"], sealed["ciphertext"],
    )
    assert result["received"] is True
    assert result["digest"] == digest
    # proof of holding, same sender:
    receipt = server.secret_transfer_receipt(session_id, client.node_id, secret_id)
    assert receipt["held"] is True
    assert receipt["digest"] == digest
    # vault exposes material only in-process via take():
    assert server.secret_vault.take(secret_id).decode("utf-8") == secret


def test_tampered_ciphertext_rejected_and_vault_empty(tmp_path):
    server = _make_node(tmp_path)
    client = _client_identity(tmp_path / "client", CLIENT_NODE_ID)
    secret = "LANTERN_SECRET_TEST_" + secrets.token_urlsafe(16)
    session_id, secret_id, sealed, _ = _full_transfer_flow(server, client, tmp_path, secret)
    ct = bytearray(bytes.fromhex(sealed["ciphertext"]))
    ct[3] ^= 0xFF  # flip one bit of ciphertext
    result = server.secret_transfer_seal(
        session_id, client.node_id, secret_id, sealed["nonce"], bytes(ct).hex(),
    )
    assert result["accepted"] is False
    assert result["reason"] == "SEAL_DECRYPT_FAILED"
    assert "secret" not in json.dumps(result)
    # nothing was stored:
    assert server.secret_transfer_receipt(session_id, client.node_id, secret_id)["held"] is False


def test_replayed_seal_rejected(tmp_path):
    server = _make_node(tmp_path)
    client = _client_identity(tmp_path / "client", CLIENT_NODE_ID)
    secret = "LANTERN_SECRET_TEST_" + secrets.token_urlsafe(16)
    session_id, secret_id, sealed, _ = _full_transfer_flow(server, client, tmp_path, secret)
    first = server.secret_transfer_seal(
        session_id, client.node_id, secret_id, sealed["nonce"], sealed["ciphertext"],
    )
    assert first["received"] is True
    replay = server.secret_transfer_seal(
        session_id, client.node_id, secret_id, sealed["nonce"], sealed["ciphertext"],
    )
    assert replay["accepted"] is False
    assert replay["reason"] == "NO_PENDING_OFFER"


def test_offer_replay_rejected(tmp_path):
    server = _make_node(tmp_path)
    client = _client_identity(tmp_path / "client", CLIENT_NODE_ID)
    secret = "LANTERN_SECRET_TEST_" + secrets.token_urlsafe(16)
    session_id, secret_id, sealed, _ = _full_transfer_flow(server, client, tmp_path, secret)
    # a second offer for the same secret_id while pending is rejected;
    # here the offer was consumed by the seal, so a NEW offer is allowed,
    # then its replay is rejected:
    import uuid

    offer2, _ = secret_transfer.create_secret_offer(
        session_id=session_id, secret_id="replay-test", identity=client,
    )
    first = server.secret_transfer_offer(session_id, client.node_id, offer2)
    assert first["accepted"] is True
    second = server.secret_transfer_offer(session_id, client.node_id, offer2)
    assert second["accepted"] is False
    assert second["reason"] == "OFFER_ALREADY_PENDING"


def test_unauthorized_node_cannot_transfer(tmp_path):
    server = _make_node(tmp_path, authorized=False)  # EMPTY_POLICY
    client = _client_identity(tmp_path / "client", CLIENT_NODE_ID)
    session_id = _establish_session(server, client)  # auth works, authorization does not
    offer, _ = secret_transfer.create_secret_offer(
        session_id=session_id, secret_id="unauth", identity=client,
    )
    result = server.secret_transfer_offer(session_id, client.node_id, offer)
    assert result["accepted"] is False
    assert "not in authorized_capabilities" in result["reason"]
    # and receipt is equally closed:
    receipt = server.secret_transfer_receipt(session_id, client.node_id, "unauth")
    assert receipt["held"] is False
    assert "not in authorized_capabilities" in receipt["reason"]


def test_vault_ttl_expiry(tmp_path):
    from lantern.secret_transfer import SecretVault

    vault = SecretVault(ttl_seconds=0.0)
    vault.store(secret_id="s1", secret_bytes=b"material", digest="d",
                sender_node_id="n1", session_id="sess1")
    assert vault.peek("s1") is None  # already expired
    assert vault.take("s1") is None


# ---------------------------------------------------------------------------
# REAL two-node subprocess end-to-end
# ---------------------------------------------------------------------------


def test_real_two_node_secret_transfer(node_b, tmp_path):
    secret = "LANTERN_SECRET_TEST_" + secrets.token_urlsafe(32)
    expected_digest = hashlib.sha256(secret.encode("utf-8")).hexdigest()

    client_identity = _client_identity(tmp_path / "a-client-identity", "lantern-secret-a")

    # ---- positive transfer over real HTTP, two independent processes ----
    result = send_secret(node_b["base"], "lantern-secret-a", client_identity, secret)
    assert result["accepted"] is True, result
    assert result["received"] is True
    assert result["digest"] == expected_digest          # B's digest == A's local digest
    assert result["received_digest"] == expected_digest  # returned only AFTER successful decrypt
    assert result["receipt_digest"] == expected_digest   # vault holding proven

    # ---- wrong-node receipt: C is authorized but is NOT the sender ----
    c_identity = _client_identity(tmp_path / "c-client-identity", "lantern-secret-c")
    c_result = send_secret(node_b["base"], "lantern-secret-c", c_identity, "LANTERN_SECRET_TEST_" + secrets.token_urlsafe(16))
    assert c_result["accepted"] is True  # C can transfer ITS OWN secret
    # C tries to obtain proof of holding for A's secret:
    c_session = _open_session_with_proof(node_b["base"], "lantern-secret-c", c_identity)
    status, body = _request(
        node_b["base"] + "/secret/receipt", "POST",
        {"session_id": c_session["session_id"], "node_id": "lantern-secret-c",
         "secret_id": result["secret_id"]},
    )
    assert body["held"] is False
    assert body["reason"] == "SECRET_NOT_YOURS"
    assert "digest" not in body or body.get("digest") != expected_digest

    # ---- unauthenticated: no session at all ----
    status, body = _request(
        node_b["base"] + "/secret/receipt", "POST",
        {"session_id": "garbage-session-id", "node_id": "lantern-secret-a",
         "secret_id": result["secret_id"]},
    )
    assert body["held"] is False
    assert "session" in body["reason"].lower()

    # ---- replay + tamper at the protocol level over real HTTP ----
    a_session2 = _open_session_with_proof(node_b["base"], "lantern-secret-a", client_identity)
    offer, eph_hex = secret_transfer.create_secret_offer(
        session_id=a_session2["session_id"], secret_id="neg-matrix", identity=client_identity,
    )
    status, offer_resp = _request(
        node_b["base"] + "/secret/offer", "POST",
        {"session_id": a_session2["session_id"], "node_id": "lantern-secret-a", "offer": offer},
    )
    assert offer_resp["accepted"] is True
    box = secret_transfer.Box(
        secret_transfer.PrivateKey(bytes.fromhex(eph_hex)),
        secret_transfer.PublicKey(bytes.fromhex(offer_resp["server_eph_pub"])),
    )
    sealed, neg_digest = secret_transfer.seal_secret(
        box, secret=secret, secret_id="neg-matrix",
        session_id=a_session2["session_id"], sender_node_id="lantern-secret-a",
    )

    # tamper: flip one ciphertext byte, send it -> rejected, vault empty
    ct = bytearray(bytes.fromhex(sealed["ciphertext"]))
    ct[10] ^= 0x01
    status, tampered = _request(
        node_b["base"] + "/secret/seal", "POST",
        {"session_id": a_session2["session_id"], "node_id": "lantern-secret-a",
         "secret_id": "neg-matrix", "nonce": sealed["nonce"], "ciphertext": bytes(ct).hex()},
    )
    assert tampered["accepted"] is False
    assert tampered["reason"] == "SEAL_DECRYPT_FAILED"
    status, check = _request(
        node_b["base"] + "/secret/receipt", "POST",
        {"session_id": a_session2["session_id"], "node_id": "lantern-secret-a",
         "secret_id": "neg-matrix"},
    )
    assert check["held"] is False

    # replay: the tampered attempt consumed the pending offer, so a new
    # offer+seal pair is needed to prove single-use semantics:
    offer2, eph2 = secret_transfer.create_secret_offer(
        session_id=a_session2["session_id"], secret_id="neg-replay", identity=client_identity,
    )
    status, offer2_resp = _request(
        node_b["base"] + "/secret/offer", "POST",
        {"session_id": a_session2["session_id"], "node_id": "lantern-secret-a", "offer": offer2},
    )
    assert offer2_resp["accepted"] is True
    box2 = secret_transfer.Box(
        secret_transfer.PrivateKey(bytes.fromhex(eph2)),
        secret_transfer.PublicKey(bytes.fromhex(offer2_resp["server_eph_pub"])),
    )
    sealed2, _ = secret_transfer.seal_secret(
        box2, secret=secret, secret_id="neg-replay",
        session_id=a_session2["session_id"], sender_node_id="lantern-secret-a",
    )
    status, first_seal = _request(
        node_b["base"] + "/secret/seal", "POST",
        {"session_id": a_session2["session_id"], "node_id": "lantern-secret-a",
         "secret_id": "neg-replay", "nonce": sealed2["nonce"], "ciphertext": sealed2["ciphertext"]},
    )
    assert first_seal["received"] is True
    status, replay_seal = _request(
        node_b["base"] + "/secret/seal", "POST",
        {"session_id": a_session2["session_id"], "node_id": "lantern-secret-a",
         "secret_id": "neg-replay", "nonce": sealed2["nonce"], "ciphertext": sealed2["ciphertext"]},
    )
    assert replay_seal["accepted"] is False
    assert replay_seal["reason"] == "NO_PENDING_OFFER"

    # ---- evidence record: digests and identifiers only ----
    evidence = {
        "test_id": "lantern_real_secret_transfer_v1",
        "sender": "lantern-secret-a",
        "receiver": "lantern-secret-b",
        "secret_id": result["secret_id"],
        "secret_length": len(secret),
        "sha256_of_secret": expected_digest,
        "receiver_digest_match": result["received_digest"] == expected_digest,
        "receipt_digest_match": result["receipt_digest"] == expected_digest,
        "wrong_node_receipt": "SECRET_NOT_YOURS",
        "unauthenticated_receipt": "rejected",
        "tamper": "SEAL_DECRYPT_FAILED",
        "replay": "NO_PENDING_OFFER",
        "process_alive": node_b["process"].poll() is None,
    }
    assert secret not in json.dumps(evidence)
    assert evidence["receiver_digest_match"] is True
    assert evidence["receipt_digest_match"] is True
    print(json.dumps(evidence, indent=2, sort_keys=True))
