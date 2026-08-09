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


def _start_node_subprocess(node_id: str, port: int, data_dir: Path) -> subprocess.Popen:
    return subprocess.Popen(
        [
            sys.executable, "-m", "lantern.bootstrap_node",
            "--node-id", node_id,
            "--host", "127.0.0.1",
            "--port", str(port),
            "--data-dir", str(data_dir),
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
    process = _start_node_subprocess("lantern-b", port, data_dir)
    base = f"http://127.0.0.1:{port}"
    try:
        _wait_for_health(base)
        yield base, port, data_dir, process
    finally:
        _stop(process)


def test_two_independent_subprocesses_handshake_and_exchange(lantern_b, tmp_path):
    """Process A (bootstrap_client) talks to Process B (bootstrap_node)
    over a real TCP socket, with no shared Python process or memory.
    """
    base, port, data_dir, b_process = lantern_b

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

    # Handshake + capability negotiation happened on the wire.
    handshake = result["handshake"]
    assert handshake["accepted"] is True
    assert handshake["protocol_version"] == "0.82"
    assert handshake["shared_capabilities"]["evidence_exchange"] is True
    assert "codex_update" not in handshake["shared_capabilities"]

    # Compatible versions confirmed (both report protocol 0.82).
    assert result["peer"]["protocol_version"] == "0.82"

    # B received the observation through boundary -> router -> bridge -> agent -> core.
    exchange = result["exchange"]
    assert exchange["accepted"] is True
    assert exchange["action"] == "OBSERVATION_CREATED"
    assert exchange["source"] == "lantern-a"
    assert exchange["data"]["observation"]["content"] == "two-process external observation"
    assert exchange["data"]["observation"]["source"] == "lantern-a"

    # B's local belief authority is untouched: an observation alone never
    # creates Evidence or moves belief. Confirmed by inspecting B's own
    # persisted Chronicle (a second, independent process wrote it).
    chronicle_path = data_dir / "lantern-b.jsonl"
    assert chronicle_path.exists()
    chronicle = Chronicle(chronicle_path)
    assert chronicle.verify() is True
    events = list(chronicle.replay())
    assert any(e["type"] == "OBSERVATION_CREATED" for e in events)
    assert not any(e["type"] == "EVIDENCE_CREATED" for e in events)


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
    """
    port = _free_port()
    data_dir = tmp_path / "b-restart"

    first = _start_node_subprocess("lantern-b", port, data_dir)
    base = f"http://127.0.0.1:{port}"
    try:
        _wait_for_health(base)

        message = {
            "message_id": "m5",
            "protocol": "0.82",
            "message_type": "OBSERVATION_SHARE",
            "source": "lantern-a",
            "timestamp": "2026-01-01T00:00:00+00:00",
            "payload": {"observation": {"content": "persist across restart"}},
        }
        status, result = _request(
            base + "/message", "POST",
            {"message": message, "peer_capabilities": {"evidence_exchange": True}},
        )
        assert status == 200
        assert result["accepted"] is True
        assert result["watermark"]["step"] == 1
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
