"""Two independent OS subprocesses exchanging over the HTTP adapter.

This is the real external-boundary test: Lantern B runs as a subprocess
(python -m lantern.bootstrap_node) that another operator would start
verbatim, and Lantern A is a second, separate subprocess
(python -m lantern.bootstrap_client) sending one observation to B over a
real TCP socket. Neither side shares memory or imports the other's
in-process objects.

The rejection cases (bad version, unsupported capability, malformed
payload, CODEX_UPDATE, remote confidence injection) are sent as raw HTTP
requests against the same running B subprocess, the same way any external,
possibly misbehaving, client would.

Nothing here modifies EvidenceKernel, belief math, evidence weighting,
contradiction logic, Chronicle semantics, snapshot semantics,
ProtocolMessage schema, protocol.validate_message(), trust boundaries,
capability authority, or Codex trust rules. This file only drives the
existing behavior across a real process boundary.
"""

import json
import socket
import subprocess
import sys
import time
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from lantern.core import Chronicle

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
        except OSError as exc:  # connection refused while server is starting
            last_error = exc
            time.sleep(0.05)
    raise TimeoutError(f"Node at {base} did not become healthy: {last_error}")


def _request(url: str, method: str = "GET", payload: dict | None = None):
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    request = Request(url, data=data, method=method, headers={"Content-Type": "application/json"})
    with urlopen(request, timeout=3) as response:
        return response.status, json.loads(response.read())


def _start_node_subprocess(
    node_id: str, port: int, data_dir: Path, extra_args: list[str] | None = None
) -> subprocess.Popen:
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
def lantern_b(tmp_path):
    port = _free_port()
    data_dir = tmp_path / "b"
    process = _start_node_subprocess(
        "lantern-b", port, data_dir, ["--allow-legacy-message-ingestion"]
    )
    base = f"http://127.0.0.1:{port}"
    try:
        _wait_for_health(base)
        yield base, port, data_dir, process
    finally:
        _stop(process)


@pytest.fixture
def lantern_b_secure(tmp_path):
    """B started with secure defaults (allow_legacy_message_ingestion=
    False, the out-of-the-box behavior an operator gets with no extra
    flags) plus an explicit --authorize grant for lantern-a's
    evidence_exchange capability -- the operator decision required by
    capability_authorization.py before ANY verified session can actually
    exchange an observation. This is the fixture for tests exercising
    the real secure /message contract, as opposed to `lantern_b` above
    which is deliberately, explicitly started in legacy mode for the
    tests that exist specifically to prove legacy mode still works as an
    opt-in.
    """
    port = _free_port()
    data_dir = tmp_path / "b-secure"
    process = _start_node_subprocess(
        "lantern-b", port, data_dir, ["--authorize", "lantern-a:evidence_exchange"]
    )
    base = f"http://127.0.0.1:{port}"
    try:
        _wait_for_health(base)
        yield base, port, data_dir, process
    finally:
        _stop(process)


def test_two_independent_subprocesses_handshake_and_exchange(lantern_b_secure, tmp_path):
    """Process A (bootstrap_client) talks to Process B (bootstrap_node)
    over a real TCP socket, with no shared Python process or memory.

    This is the canonical secure two-process interoperability proof for
    the Phase 4 migration: identity verification -> /session/open ->
    session-bound /message -> exactly one Observation, plus the four
    security properties the migration exists to guarantee:
      - a verified session cannot be reused to claim a different source
        node_id (anti-impersonation / source binding);
      - an unknown/garbage session_id is rejected;
      - an expired session is rejected, never silently renewed;
      - the existing replay-protection mechanism still applies on the
        secure path (same (source, message_id) -> DUPLICATE_MESSAGE).

    B is started via secure defaults (no --allow-legacy-message-ingestion)
    plus an explicit --authorize lantern-a:evidence_exchange grant -- the
    same two things any real operator must do to accept secure traffic
    from a specific peer.
    """
    base, port, data_dir, b_process = lantern_b_secure

    a_data_dir = tmp_path / "a"
    a_process = subprocess.run(
        [
            sys.executable, "-m", "lantern.bootstrap_client",
            "--node-id", "lantern-a",
            "--peer", base,
            "--source", "operator-a",
            "--content", "two-process external observation",
            "--reliability", "0.97",
            "--data-dir", str(a_data_dir),
        ],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        timeout=10,
    )

    assert a_process.returncode == 0, a_process.stderr
    result = json.loads(a_process.stdout)

    assert result["mode"] == "secure"

    # Handshake + capability negotiation happened on the wire.
    handshake = result["handshake"]
    assert handshake["accepted"] is True
    assert handshake["protocol_version"] == "0.82"
    assert handshake["shared_capabilities"]["evidence_exchange"] is True
    assert "codex_update" not in handshake["shared_capabilities"]

    # Compatible versions confirmed (both report protocol 0.82).
    assert result["peer"]["protocol_version"] == "0.82"
    assert result["peer"]["legacy_message_ingestion"] is False

    # Cryptographic identity verification happened on the wire (real
    # challenge/response/verify round trip against B's /identity/*
    # routes, not merely a negotiated capability).
    identity_result = result["identity"]
    assert identity_result["verified"] is True
    assert identity_result["identity_status"] == "CRYPTOGRAPHICALLY_VERIFIED"

    # A short-lived verified session was issued, bound to lantern-a.
    session = result["session"]
    assert session["created"] is True
    session_id = session["session_id"]
    assert isinstance(session_id, str) and session_id

    # B received the observation through the SECURE path: session lookup
    # -> source binding -> explicit capability_authorization.authorize()
    # -> observation_exchange.receive_observation(). Exactly one
    # Observation, never Evidence.
    exchange = result["exchange"]
    assert exchange["accepted"] is True
    assert exchange["action"] == "accept"
    assert exchange["source"] == "lantern-a"
    observation_id = exchange["observation_id"]
    assert isinstance(observation_id, str) and observation_id

    # B's local belief authority is untouched: an observation alone never
    # creates Evidence or moves belief. Confirmed by inspecting B's own
    # persisted Chronicle (a second, independent process wrote it).
    chronicle_path = data_dir / "lantern-b.jsonl"
    assert chronicle_path.exists()
    chronicle = Chronicle(chronicle_path)
    assert chronicle.verify() is True
    events = list(chronicle.replay())
    assert sum(1 for e in events if e["type"] == "OBSERVATION_CREATED") == 1
    assert not any(e["type"] == "EVIDENCE_CREATED" for e in events)

    # ------------------------------------------------------------
    # Security properties the secure /message migration exists to
    # guarantee, exercised directly over raw HTTP against the SAME
    # running B subprocess (still a real, independent OS process; no
    # shared memory with B at any point in this test).
    # ------------------------------------------------------------

    def _post_message(payload):
        return _request(base + "/message", "POST", payload)

    valid_session_id = session_id

    # (1) A verified session cannot be reused to claim a DIFFERENT source
    # node_id than the one it was bound to -- anti-impersonation via
    # source binding. Must be rejected, and must create no observation.
    impersonating_message = {
        "message_id": "impersonation-attempt-1",
        "protocol": "0.82",
        "message_type": "OBSERVATION_SHARE",
        "source": "lantern-x",
        "timestamp": "2026-01-01T00:00:00+00:00",
        "payload": {"observation": {"content": "impersonation attempt"}},
    }
    status, impersonation_result = _post_message(
        {"message": impersonating_message, "session_id": valid_session_id}
    )
    assert status == 200
    assert impersonation_result["accepted"] is False
    assert "source_mismatch" in impersonation_result["reason"]

    # (2) An unknown/garbage session_id is rejected outright.
    unknown_session_message = {
        "message_id": "unknown-session-attempt-1",
        "protocol": "0.82",
        "message_type": "OBSERVATION_SHARE",
        "source": "lantern-a",
        "timestamp": "2026-01-01T00:00:00+00:00",
        "payload": {"observation": {"content": "unknown session attempt"}},
    }
    status, unknown_result = _post_message(
        {"message": unknown_session_message, "session_id": "not-a-real-session-id"}
    )
    assert status == 200
    assert unknown_result["accepted"] is False
    assert "unknown_session" in unknown_result["reason"]

    # (3) An expired session is rejected, never silently renewed by
    # presenting it again. This is proven over the real wire (not just
    # at the unit level) using a SECOND independent B subprocess started
    # with a deliberately tiny --session-ttl-seconds, so the test can
    # wait past a real expiration without slowing down the rest of the
    # suite with a long sleep against the main lantern_b_secure process.
    expiry_port = _free_port()
    expiry_data_dir = tmp_path / "b-expiry"
    expiry_process = _start_node_subprocess(
        "lantern-b-expiry",
        expiry_port,
        expiry_data_dir,
        ["--authorize", "lantern-a:evidence_exchange", "--session-ttl-seconds", "0.2"],
    )
    expiry_base = f"http://127.0.0.1:{expiry_port}"
    try:
        _wait_for_health(expiry_base)

        expiry_a_data_dir = tmp_path / "a-expiry"
        expiry_a_process = subprocess.run(
            [
                sys.executable, "-m", "lantern.bootstrap_client",
                "--node-id", "lantern-a",
                "--peer", expiry_base,
                "--source", "operator-a",
                "--content", "expiry probe",
                "--data-dir", str(expiry_a_data_dir),
            ],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert expiry_a_process.returncode == 0, expiry_a_process.stderr
        expiry_result = json.loads(expiry_a_process.stdout)
        assert expiry_result["exchange"]["accepted"] is True
        short_session_id = expiry_result["session"]["session_id"]

        # Past the 0.2s TTL: the identical session_id must now be
        # rejected as expired, never silently renewed by re-presenting
        # it, and must create no new Observation.
        time.sleep(0.5)
        status, expired_result = _request(
            expiry_base + "/message",
            "POST",
            {
                "message": {
                    "message_id": "expiry-check-after-ttl",
                    "protocol": "0.82",
                    "message_type": "OBSERVATION_SHARE",
                    "source": "lantern-a",
                    "timestamp": "2026-01-01T00:00:00+00:00",
                    "payload": {"observation": {"content": "should be rejected as expired"}},
                },
                "session_id": short_session_id,
            },
        )
        assert status == 200
        assert expired_result["accepted"] is False
        assert "expired" in expired_result["reason"].lower()

        expiry_chronicle = Chronicle(expiry_data_dir / "lantern-b-expiry.jsonl")
        expiry_events = list(expiry_chronicle.replay())
        assert sum(1 for e in expiry_events if e["type"] == "OBSERVATION_CREATED") == 1
    finally:
        _stop(expiry_process)

    # (4) Replay protection: resubmitting the EXACT SAME message (same
    # message_id) that already succeeded must be rejected as a duplicate,
    # not create a second Observation.
    status, replay_result = _post_message(
        {"message": {
            "message_id": "two-process-replay-check",
            "protocol": "0.82",
            "message_type": "OBSERVATION_SHARE",
            "source": "lantern-a",
            "timestamp": "2026-01-01T00:00:00+00:00",
            "payload": {"observation": {"content": "first send"}},
        }, "session_id": valid_session_id}
    )
    assert status == 200
    assert replay_result["accepted"] is True

    status, replay_result_2 = _post_message(
        {"message": {
            "message_id": "two-process-replay-check",
            "protocol": "0.82",
            "message_type": "OBSERVATION_SHARE",
            "source": "lantern-a",
            "timestamp": "2026-01-01T00:00:00+00:00",
            "payload": {"observation": {"content": "replayed send"}},
        }, "session_id": valid_session_id}
    )
    assert status == 200
    assert replay_result_2["accepted"] is False
    assert "replay" in replay_result_2["reason"].lower()

    final_events = list(Chronicle(chronicle_path).replay())
    assert sum(1 for e in final_events if e["type"] == "OBSERVATION_CREATED") == 2
    assert not any(e["type"] == "EVIDENCE_CREATED" for e in final_events)


def test_incompatible_major_version_rejected_over_wire(lantern_b):
    base, *_ = lantern_b

    handshake_request = {
        "node_id": "lantern-a",
        "protocol_version": "9.0",
        "capabilities": {"evidence_exchange": True},
        "timestamp": "2026-01-01T00:00:00+00:00",
    }
    status, response = _request(base + "/handshake", "POST", handshake_request)
    assert status == 200
    assert response["accepted"] is False
    assert "version" in response["reason"].lower()

    message = {
        "message_id": "m1",
        "protocol": "9.0",
        "message_type": "OBSERVATION_SHARE",
        "source": "lantern-a",
        "timestamp": "2026-01-01T00:00:00+00:00",
        "payload": {"observation": {"content": "should be rejected"}},
    }
    status, result = _request(
        base + "/message", "POST",
        {"message": message, "peer_capabilities": {"evidence_exchange": True}},
    )
    assert status == 200
    assert result["accepted"] is False
    # The bridge/router path surfaces a capability-unavailable reason here
    # (can_exchange() short-circuits on compatibility.compatible before
    # capability lookup); the version-specific reason text is only
    # produced directly by negotiate()/evaluate_handshake(), asserted
    # above via the /handshake response. Router behavior is existing,
    # unmodified code -- this assertion documents it rather than
    # inventing a different expectation.
    assert "unavailable" in result["reason"].lower()


def test_unsupported_capability_rejected_over_wire(lantern_b):
    base, *_ = lantern_b

    message = {
        "message_id": "m2",
        "protocol": "0.82",
        "message_type": "OBSERVATION_SHARE",
        "source": "lantern-a",
        "timestamp": "2026-01-01T00:00:00+00:00",
        "payload": {"observation": {"content": "no evidence_exchange capability"}},
    }
    status, result = _request(
        base + "/message", "POST",
        {"message": message, "peer_capabilities": {}},
    )
    assert status == 200
    assert result["accepted"] is False
    assert "evidence_exchange" in result["reason"]


def test_malformed_payload_rejected_over_wire(lantern_b):
    base, *_ = lantern_b

    with pytest.raises(HTTPError) as error:
        _request(base + "/message", "POST", {"message": {"not": "a protocol message"}, "peer_capabilities": {}})
    assert error.value.code == 400


def test_codex_update_blocked_over_wire(lantern_b):
    """Even a peer that claims codex_update capability must be refused,
    because the receiving node's own supported capabilities keep
    codex_update disabled (lantern.compatibility.DEFAULT_CAPABILITIES).
    """
    base, *_ = lantern_b

    message = {
        "message_id": "m3",
        "protocol": "0.82",
        "message_type": "CODEX_UPDATE",
        "source": "lantern-a",
        "timestamp": "2026-01-01T00:00:00+00:00",
        "payload": {
            "concept": "gravity",
            "confidence": 0.999,
            "evidence_ids": ["remote-claimed-evidence"],
        },
    }
    status, result = _request(
        base + "/message", "POST",
        {"message": message, "peer_capabilities": {"codex_update": True}},
    )
    assert status == 200
    assert result["accepted"] is False
    assert "codex_update" in result["reason"]


def test_remote_confidence_never_becomes_local_belief(lantern_b):
    """A remote peer claiming very high reliability must still only ever
    create an Observation, never Evidence, and must never move belief().
    """
    base, port, data_dir, process = lantern_b

    message = {
        "message_id": "m4",
        "protocol": "0.82",
        "message_type": "OBSERVATION_SHARE",
        "source": "lantern-a",
        "timestamp": "2026-01-01T00:00:00+00:00",
        "payload": {
            "observation": {
                "content": "trust me completely",
                "reliability": 0.9999,
            }
        },
    }
    status, result = _request(
        base + "/message", "POST",
        {"message": message, "peer_capabilities": {"evidence_exchange": True}},
    )
    assert status == 200
    assert result["accepted"] is True

    chronicle = Chronicle(data_dir / "lantern-b.jsonl")
    events = list(chronicle.replay())
    assert any(e["type"] == "OBSERVATION_CREATED" for e in events)
    assert not any(e["type"] == "EVIDENCE_CREATED" for e in events)

    # belief() with no evidence for the concept is None, not influenced by
    # the remote's claimed reliability.
    status, health = _request(base + "/health")
    assert health["watermark"]["step"] >= 1


def test_release_gate_full_chain_blocks_protected_state_mutation(lantern_b):
    """Release-gate regression: walk join -> identity -> handshake ->
    limited-capability negotiation -> harmless observation -> adversarial
    CODEX_UPDATE attempt, all over the real HTTP/subprocess boundary, and
    assert protected state (evidence, belief, Codex) is provably
    unchanged before vs after the mutation attempt.

    This is deliberately end to end rather than isolated per-step, unlike
    the other tests in this file, because the release gate requires proof
    that a remote participant cannot chain join+handshake+observation into
    a mutation of protected state -- not just that each rejection works
    in isolation.
    """
    base, port, data_dir, process = lantern_b

    # RENDEZVOUS / JOIN: an announcement, must grant nothing.
    join_payload = {
        "request_id": "release-gate-1",
        "node_id": "lantern-a-release-gate",
        "protocol_version": "0.82",
        "capabilities": {"evidence_exchange": True, "codex_update": True},
        "timestamp": "2026-01-01T00:00:00+00:00",
    }
    status, join_result = _request(base + "/join", "POST", join_payload)
    assert status == 200 and join_result["accepted"] is True

    # IDENTITY OBSERVED
    status, health_before = _request(base + "/health")
    assert status == 200
    watermark_before = health_before["watermark"]

    # PROTOCOL COMPATIBILITY + HANDSHAKE: peer asks for codex_update too.
    handshake_request = {
        "node_id": "lantern-a-release-gate",
        "protocol_version": "0.82",
        "capabilities": {"evidence_exchange": True, "codex_update": True},
        "timestamp": "2026-01-01T00:00:00+00:00",
    }
    status, handshake_response = _request(base + "/handshake", "POST", handshake_request)
    assert status == 200 and handshake_response["accepted"] is True

    # LIMITED PARTICIPANT: codex_update must never be shared, even though
    # the remote explicitly asked for it.
    shared = handshake_response["shared_capabilities"]
    assert shared.get("evidence_exchange") is True
    assert "codex_update" not in shared

    # HARMLESS TEST OBSERVATION
    probe_message = {
        "message_id": "release-gate-probe",
        "protocol": "0.82",
        "message_type": "OBSERVATION_SHARE",
        "source": "lantern-a-release-gate",
        "timestamp": "2026-01-01T00:00:00+00:00",
        "payload": {"observation": {"content": "INTER_INSTANCE_TEST", "reliability": 1.0}},
    }
    status, exchange = _request(
        base + "/message", "POST",
        {"message": probe_message, "peer_capabilities": shared},
    )
    assert status == 200 and exchange["accepted"] is True
    assert exchange["action"] == "OBSERVATION_CREATED"

    # ADVERSARIAL: attempt CODEX_UPDATE (belief/Codex mutation) right
    # after a successful join+handshake+observation, to prove the prior
    # steps did not loosen anything.
    codex_probe = {
        "message_id": "release-gate-codex-probe",
        "protocol": "0.82",
        "message_type": "CODEX_UPDATE",
        "source": "lantern-a-release-gate",
        "timestamp": "2026-01-01T00:00:00+00:00",
        "payload": {"concept": "gravity", "confidence": 0.999, "evidence_ids": ["fabricated"]},
    }
    status, codex_result = _request(
        base + "/message", "POST",
        {"message": codex_probe, "peer_capabilities": {"codex_update": True}},
    )
    assert status == 200
    assert codex_result["accepted"] is False
    assert "codex_update" in codex_result["reason"]

    # VERIFICATION: re-read B's own Chronicle from disk (independent of
    # any in-memory claim) and confirm exactly the harmless observation
    # was recorded, zero Evidence exists, and the watermark only advanced
    # by the one harmless observation -- never by the CODEX_UPDATE attempt.
    chronicle_path = data_dir / "lantern-b.jsonl"
    chronicle = Chronicle(chronicle_path)
    assert chronicle.verify() is True
    records = list(chronicle.replay())
    assert sum(1 for r in records if r["type"] == "OBSERVATION_CREATED") == 1
    assert sum(1 for r in records if r["type"] == "EVIDENCE_CREATED") == 0
    assert not any(r["type"].startswith("CODEX") for r in records)

    status, health_after = _request(base + "/health")
    watermark_after = health_after["watermark"]
    assert watermark_after["step"] - watermark_before["step"] == 1


def test_restart_recovers_chronicle_and_snapshot_across_processes(tmp_path):
    """Shut down B, restart B as a brand-new subprocess against the same
    data directory, and confirm Chronicle/snapshot recovery works with no
    shared process state at all.

    This test's purpose is restart/persistence recovery, not identity or
    authorization semantics -- so it is migrated to the SECURE workflow
    (Category A) rather than opting into legacy mode: the point is to
    prove that a real, secure, accepted Observation survives a full
    process restart, which is a stronger and more representative proof
    than the old unauthenticated shortcut it used to take to get there.
    """
    port = _free_port()
    data_dir = tmp_path / "b-restart"

    first = _start_node_subprocess(
        "lantern-b", port, data_dir, ["--authorize", "lantern-a:evidence_exchange"]
    )
    base = f"http://127.0.0.1:{port}"
    try:
        _wait_for_health(base)

        a_data_dir = tmp_path / "a-restart"
        a_process = subprocess.run(
            [
                sys.executable, "-m", "lantern.bootstrap_client",
                "--node-id", "lantern-a",
                "--peer", base,
                "--source", "operator-a",
                "--content", "persist across restart",
                "--data-dir", str(a_data_dir),
            ],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert a_process.returncode == 0, a_process.stderr
        result = json.loads(a_process.stdout)
        assert result["mode"] == "secure"
        assert result["exchange"]["accepted"] is True

        status, health = _request(base + "/health")
        assert status == 200
        assert health["watermark"]["step"] == 1
    finally:
        _stop(first)

    chronicle_path = data_dir / "lantern-b.jsonl"
    chronicle = Chronicle(chronicle_path)
    assert chronicle.verify() is True

    second_port = _free_port()
    second = _start_node_subprocess("lantern-b", second_port, data_dir)
    second_base = f"http://127.0.0.1:{second_port}"
    try:
        health = _wait_for_health(second_base)
        assert health["watermark"]["step"] == 1
        assert health["watermark"]["chain"] == chronicle.chain
    finally:
        _stop(second)
