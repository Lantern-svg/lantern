"""Real, end-to-end, cross-process Lantern artifact exchange proof.

This is the promotion-gate test distinguishing three previously-conflated
things:

    1. Delivery    -- B's HTTP server accepted A's OBSERVATION_SHARE.
    2. Persistence -- B durably wrote the observation into its own
                      Chronicle/EvidenceKernel state.
    3. Retrieval   -- B can read the ACTUAL CONTENT back out, through its
                      own authenticated HTTP interface, and prove it holds
                      the genuine value (via a cryptographic digest, never
                      the raw secret) back to the sender.

Two independent OS subprocesses (real TCP sockets, no shared memory, same
pattern as test_two_process_bootstrap.py). The test harness (this file)
NEVER reads either node's Chronicle file to establish retrieval -- that
would be exactly the filesystem-peeking shortcut this test exists to rule
out. Retrieval is proven ONLY via B's own authenticated
GET /observations/<id> HTTP call, made by a driver acting as B.

Secret handling: a fresh, cryptographically random one-time test secret is
generated in memory for each test run. It is passed to node A only via a
real HTTP POST body (through bootstrap_client's existing secure workflow
functions, imported and called directly -- not shelled out to a CLI whose
stdout could echo it). It is never logged, never assertion-interpolated,
never written to the evidence dict. Only sha256(secret) ever appears
anywhere in this file's assertions or evidence output.
"""

from __future__ import annotations

import hashlib
import json
import secrets
import socket
import subprocess
import sys
import time
from dataclasses import asdict
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from lantern import identity as identity_module
from lantern.bootstrap_client import _verify_identity_with_peer
from lantern.protocol import create_observation_share

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
def node_a(tmp_path):
    port = _free_port()
    data_dir = tmp_path / "a"
    process = _start_node_subprocess(
        "lantern-e2e-a", port, data_dir, ["--authorize", "lantern-e2e-b:evidence_exchange"]
    )
    base = f"http://127.0.0.1:{port}"
    try:
        _wait_for_health(base)
        yield {"base": base, "port": port, "data_dir": data_dir, "process": process, "node_id": "lantern-e2e-a"}
    finally:
        _stop(process)


@pytest.fixture
def node_b(tmp_path):
    port = _free_port()
    data_dir = tmp_path / "b"
    process = _start_node_subprocess(
        "lantern-e2e-b", port, data_dir, ["--authorize", "lantern-e2e-a:evidence_exchange"]
    )
    base = f"http://127.0.0.1:{port}"
    try:
        _wait_for_health(base)
        yield {"base": base, "port": port, "data_dir": data_dir, "process": process, "node_id": "lantern-e2e-b"}
    finally:
        _stop(process)


def _open_session_via_proof(*, base: str, node_id: str, local_identity) -> dict:
    """Two-phase /session/open for a caller that has already completed
    /identity/verify (this is the initiator-side analogue of
    _self_open_session's own inline version -- kept as one shared helper
    so the two-phase mechanics exist in exactly one place in this test
    file, mirroring bootstrap_client.py's own
    `_open_session_with_proof`). Returns the full session dict; caller
    asserts on `created`.
    """
    _, challenge_body = _request(base + "/session/open", "POST", {"node_id": node_id})
    assert "nonce" in challenge_body, challenge_body

    challenge = identity_module.Challenge(
        nonce=challenge_body["nonce"],
        from_node_id=challenge_body["from_node_id"],
        to_node_id=challenge_body["to_node_id"],
        protocol_version=challenge_body["protocol_version"],
        issued_at=0.0,
        ttl_seconds=challenge_body.get("ttl_seconds", identity_module.DEFAULT_CHALLENGE_TTL_SECONDS),
    )
    binding = json.loads((local_identity.identity_dir / "binding.json").read_text())
    proof = identity_module.respond_to_challenge(challenge, local_identity, binding["signature"])
    proof_payload = {
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
    _, session = _request(base + "/session/open", "POST", {"node_id": node_id, "proof": proof_payload})
    return session


def _secure_send(
    *, peer_base: str, sender_node_id: str, sender_data_dir: Path, content: str, source: str
) -> dict:
    """Reuses the existing secure client workflow's own building blocks
    (imported directly, not shelled out) to send exactly one
    OBSERVATION_SHARE over a real HTTP connection to peer_base. Returns
    the full step-by-step result dict. This is the same sequence
    bootstrap_client.main()'s --legacy=False path performs; duplicated
    here (not calling main() itself) only so the test can hold the
    returned dict in memory without ever letting it hit a subprocess's
    captured stdout.
    """
    sender_data_dir.mkdir(parents=True, exist_ok=True)
    identity_dir = identity_module.default_identity_dir(sender_data_dir, sender_node_id)
    sender_identity = identity_module.load_or_create(sender_node_id, identity_dir)

    verify_result = _verify_identity_with_peer(peer_base, sender_node_id, sender_identity)
    assert verify_result.get("verified") is True, verify_result

    session = _open_session_via_proof(base=peer_base, node_id=sender_node_id, local_identity=sender_identity)
    assert session.get("created") is True, session

    message = create_observation_share(sender_node_id, {"content": content, "source": source, "reliability": 1.0})
    _, exchange = _request(
        peer_base + "/message",
        "POST",
        {"message": asdict(message), "session_id": session["session_id"]},
    )

    return {
        "identity": verify_result,
        "session": session,
        "exchange": exchange,
        "message_id": message.message_id,
    }


def _self_open_session(*, base: str, node_id: str, data_dir: Path) -> str:
    """A node opening a session against ITSELF.

    open_session() only succeeds for a node_id already present in
    _known_public_keys, which is populated ONLY by a real, successful
    /identity/verify round trip (see verify_identity_proof()) -- a node
    does NOT automatically trust its own node_id without one. So this
    performs the exact same challenge/response/verify sequence any
    other caller uses (_verify_identity_with_peer, reused verbatim),
    with `base` acting as both initiator and responder of its own
    challenge -- i.e. B proves its own identity to itself, over its own
    real HTTP server, using its own already-persisted NodeIdentity. This
    is the credential B's own driver then uses to call B's self-only
    GET /observations/<id> endpoint -- distinct from any session a
    remote peer might hold.

    Reuses /identity/challenge, /identity/verify, and /session/open
    exactly as any other caller would; no new server-side code path.
    """
    data_dir.mkdir(parents=True, exist_ok=True)
    identity_dir = identity_module.default_identity_dir(data_dir, node_id)
    node_identity = identity_module.load_or_create(node_id, identity_dir)

    verify_result = _verify_identity_with_peer(base, node_id, node_identity)
    assert verify_result.get("verified") is True, verify_result

    session = _open_session_via_proof(base=base, node_id=node_id, local_identity=node_identity)
    assert session.get("created") is True, session
    return session["session_id"]


def _get_observation(base: str, observation_id: str, session_id: str | None):
    url = base + f"/observations/{observation_id}"
    if session_id is not None:
        url += f"?session_id={session_id}"
    try:
        status, body = _request(url, "GET")
        return status, body
    except HTTPError as exc:
        return exc.code, json.loads(exc.read())


def test_real_e2e_exchange_delivery_persistence_retrieval_and_ack(node_a, node_b, tmp_path):
    """The full promotion-gate proof, all legs over real HTTP between two
    real, independent subprocesses.

    A generates secret R -> A sends R to B (secure OBSERVATION_SHARE) ->
    B accepts (delivery) -> B durably persists (existing Chronicle
    mechanism, not re-verified via filesystem here) -> B's OWN driver
    calls B's authenticated self-only GET /observations/<id> (retrieval)
    -> B computes sha256(retrieved content) -> B sends an ack
    (OBSERVATION_SHARE containing only the digest + original message_id)
    back to A -> A verifies the digest against the R it generated,
    without B ever having told A the secret directly.
    """
    test_secret = "LANTERN_E2E_TEST_" + secrets.token_urlsafe(32)
    expected_digest = hashlib.sha256(test_secret.encode("utf-8")).hexdigest()

    # ---- Leg 1: A -> B real secure delivery ----
    send_result = _secure_send(
        peer_base=node_b["base"],
        sender_node_id=node_a["node_id"],
        sender_data_dir=tmp_path / "a-client-identity",
        content=test_secret,
        source=node_a["node_id"],
    )
    assert send_result["identity"]["identity_status"] == "CRYPTOGRAPHICALLY_VERIFIED"
    exchange = send_result["exchange"]
    assert exchange["accepted"] is True
    assert exchange["action"] == "accept"
    observation_id = exchange["observation_id"]
    assert isinstance(observation_id, str) and observation_id
    original_message_id = send_result["message_id"]

    # ---- Leg 2: B retrieves ITS OWN accepted observation over real
    # authenticated HTTP (not filesystem, not in-process shortcut). B's
    # driver opens a self-session for its own node_id, then calls the
    # new endpoint exactly as an external caller would.
    b_self_session_id = _self_open_session(base=node_b["base"], node_id=node_b["node_id"], data_dir=node_b["data_dir"])
    status, retrieved = _get_observation(node_b["base"], observation_id, b_self_session_id)
    assert status == 200, retrieved
    retrieved_content = retrieved["content"]
    assert retrieved_content == test_secret  # only ever compared in-memory, never printed
    retrieval_digest = hashlib.sha256(retrieved_content.encode("utf-8")).hexdigest()
    assert retrieval_digest == expected_digest

    # ---- Leg 3: B -> A authenticated acknowledgment, carrying ONLY the
    # digest and the original message_id -- never the raw secret. Reuses
    # the existing OBSERVATION_SHARE type (no new protocol/message type).
    ack_payload = json.dumps({"ack_for_message_id": original_message_id, "digest": retrieval_digest})
    ack_result = _secure_send(
        peer_base=node_a["base"],
        sender_node_id=node_b["node_id"],
        sender_data_dir=tmp_path / "b-client-identity",
        content=ack_payload,
        source=node_b["node_id"],
    )
    assert ack_result["identity"]["identity_status"] == "CRYPTOGRAPHICALLY_VERIFIED"
    ack_exchange = ack_result["exchange"]
    assert ack_exchange["accepted"] is True
    ack_observation_id = ack_exchange["observation_id"]
    assert isinstance(ack_observation_id, str) and ack_observation_id

    # ---- Leg 4: A retrieves B's ack via the SAME authenticated,
    # self-only mechanism (A reading its own accepted observation back
    # to itself) and verifies the digest against the R it generated.
    a_self_session_id = _self_open_session(base=node_a["base"], node_id=node_a["node_id"], data_dir=node_a["data_dir"])
    status, ack_retrieved = _get_observation(node_a["base"], ack_observation_id, a_self_session_id)
    assert status == 200, ack_retrieved
    ack_body = json.loads(ack_retrieved["content"])
    assert ack_body["ack_for_message_id"] == original_message_id
    assert ack_body["digest"] == expected_digest  # A's independent verification

    # ---- Machine-readable evidence record. Contains sha256(R) only;
    # test_secret itself is never assigned into this dict.
    evidence = {
        "test_id": "lantern_real_e2e_exchange_v1",
        "node_a_id": node_a["node_id"],
        "node_b_id": node_b["node_id"],
        "message_id": original_message_id,
        "observation_id": observation_id,
        "ack_observation_id": ack_observation_id,
        "a_to_b_session_id": send_result["session"]["session_id"],
        "b_to_a_session_id": ack_result["session"]["session_id"],
        "b_self_session_id": b_self_session_id,
        "a_self_session_id": a_self_session_id,
        "sha256_of_secret": expected_digest,
        "b_retrieval_digest": retrieval_digest,
        "b_retrieval_success": True,
        "ack_digest": ack_body["digest"],
        "ack_verified_against_original": ack_body["digest"] == expected_digest,
        "identity_cryptographically_verified_a_to_b": send_result["identity"]["identity_status"] == "CRYPTOGRAPHICALLY_VERIFIED",
        "identity_cryptographically_verified_b_to_a": ack_result["identity"]["identity_status"] == "CRYPTOGRAPHICALLY_VERIFIED",
        "process_exit_status": {
            "node_a_alive_during_test": node_a["process"].poll() is None,
            "node_b_alive_during_test": node_b["process"].poll() is None,
        },
        "witness_ledger_verification": "not_applicable_no_witness_ledger_exists_in_this_codebase",
    }
    assert test_secret not in json.dumps(evidence)
    assert evidence["ack_verified_against_original"] is True

    # Print only the evidence record (digest-only) so pytest -s output
    # is itself safe; the raw secret is never passed to print()/repr()
    # anywhere in this test.
    print(json.dumps(evidence, indent=2, sort_keys=True))


def test_wrong_node_session_cannot_retrieve_observation(node_a, node_b, tmp_path):
    """An authenticated session belonging to a DIFFERENT node_id (not
    node_b's own) must be rejected by B's self-only observation
    endpoint, even though that node_id may hold a perfectly valid,
    fully evidence_exchange-authorized session against B. This is the
    precise security property: authorization to exchange observations
    is not the same as authorization to read them back.
    """
    send_result = _secure_send(
        peer_base=node_b["base"],
        sender_node_id=node_a["node_id"],
        sender_data_dir=tmp_path / "a-client-identity",
        content="LANTERN_E2E_TEST_" + secrets.token_urlsafe(16),
        source=node_a["node_id"],
    )
    observation_id = send_result["exchange"]["observation_id"]

    # lantern-e2e-a already has a valid, cryptographically verified
    # session against B (from the send above) -- reuse THAT session_id
    # to attempt retrieval, proving that evidence_exchange session alone
    # is insufficient.
    a_session_id = send_result["session"]["session_id"]
    status, body = _get_observation(node_b["base"], observation_id, a_session_id)
    assert status == 403, body
    assert "content" not in body


def test_unauthenticated_request_cannot_retrieve_observation(node_a, node_b, tmp_path):
    """No session_id at all, and a garbage/unknown session_id, must both
    be rejected -- the endpoint never falls back to some weaker
    unauthenticated read path.
    """
    send_result = _secure_send(
        peer_base=node_b["base"],
        sender_node_id=node_a["node_id"],
        sender_data_dir=tmp_path / "a-client-identity",
        content="LANTERN_E2E_TEST_" + secrets.token_urlsafe(16),
        source=node_a["node_id"],
    )
    observation_id = send_result["exchange"]["observation_id"]

    # No session_id at all.
    status, body = _get_observation(node_b["base"], observation_id, None)
    assert status == 401, body
    assert "content" not in body

    # Garbage/unknown session_id.
    status, body = _get_observation(node_b["base"], observation_id, "not-a-real-session-id")
    assert status == 401, body
    assert "content" not in body


def test_nonexistent_observation_id_returns_404_without_leak(node_a, node_b):
    """A well-authenticated self-session against B, but for an
    observation_id that was never accepted, must 404 cleanly with no
    content/internal-state leakage.
    """
    b_self_session_id = _self_open_session(base=node_b["base"], node_id=node_b["node_id"], data_dir=node_b["data_dir"])
    status, body = _get_observation(node_b["base"], "does-not-exist-observation-id", b_self_session_id)
    assert status == 404, body
    assert "content" not in body
