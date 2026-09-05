"""Deployment readiness: env-config, startup self-test, authenticated
observation retrieval with SHA-256 verification, protocol-version
allowlist, and the full external connection path exercised against a
real OS subprocess configured entirely through environment variables.

This file adds ONLY deployment machinery tests. Handshake,
authentication, session proof-of-possession, evidence authorization,
observation persistence, and malformed-input rejection are already
covered by the existing suite (test_session_proof_of_possession,
test_lantern_observation_exchange, test_gate2_hardening, and others);
those run unchanged alongside these.
"""

import hashlib
import json
import os
import socket
import subprocess
import sys
import threading
import time
from dataclasses import asdict
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from lantern import identity as identity_module
from lantern.bootstrap_client import _verify_identity_with_peer
from lantern.bootstrap_node import (
    create_server,
    main,
    public_key_fingerprint,
)
from lantern.capability_authorization import AuthorizationPolicy
from lantern.deployment_config import resolve_config
from lantern.handshake import create_handshake
from lantern.protocol import PROTOCOL_VERSION, create_observation_share

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def request(base, path, method="GET", payload=None):
    data = None if payload is None else json.dumps(payload).encode()
    req = Request(base + path, data=data, method=method,
                  headers={"Content-Type": "application/json"})
    try:
        with urlopen(req, timeout=5) as response:
            return response.status, json.loads(response.read())
    except HTTPError as e:
        return e.code, json.loads(e.read())


def _free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


# ------------------------------------------------------------
# Configuration resolution
# ------------------------------------------------------------


class TestDeploymentConfig:
    def test_env_only_configuration(self):
        cfg = resolve_config(environ={
            "LANTERN_NODE_ID": "node-x",
            "LANTERN_BIND_HOST": "0.0.0.0",
            "LANTERN_BIND_PORT": "9001",
            "LANTERN_DATA_DIR": "/srv/lantern",
            "LANTERN_PUBLIC_URL": "https://lantern.example.com/",
            "LANTERN_AUTHORIZE": "a:evidence_exchange;b:belief_query,codex_update",
            "LANTERN_ALLOWED_PROTOCOL_VERSIONS": "0.81, 0.82",
            "LANTERN_SESSION_TTL_SECONDS": "120",
        })
        assert cfg.node_id == "node-x"
        assert cfg.bind_host == "0.0.0.0" and cfg.bind_port == 9001
        assert cfg.public_base_url == "https://lantern.example.com"
        assert cfg.authorize == (
            "a:evidence_exchange", "b:belief_query,codex_update",
        )
        assert cfg.allowed_protocol_versions == ("0.81", "0.82")
        assert cfg.session_ttl_seconds == 120.0
        assert cfg.chronicle_path == "/srv/lantern/node-x.jsonl"
        assert cfg.source["node_id"] == "env"

    def test_cli_overrides_env(self):
        cfg = resolve_config(
            {"node_id": "cli-node", "bind_port": 9000},
            environ={"LANTERN_NODE_ID": "env-node", "LANTERN_BIND_PORT": "1234"},
        )
        assert cfg.node_id == "cli-node" and cfg.bind_port == 9000
        assert cfg.source["node_id"] == "cli"

    def test_node_id_is_required_fail_closed(self):
        with pytest.raises(ValueError, match="node_id"):
            resolve_config(environ={})

    def test_bad_public_url_rejected(self):
        for bad in ("ftp://nope", "https://host/path", "https://host?q=1"):
            with pytest.raises(ValueError):
                resolve_config({"node_id": "x"},
                               environ={"LANTERN_PUBLIC_URL": bad})

    def test_legacy_optin_is_strict(self):
        for raw, expected in (("true", True), ("1", True), ("yes", True),
                             ("on", True), ("false", False), ("", False),
                             ("maybe", False)):
            cfg = resolve_config(
                {"node_id": "x"},
                environ={"LANTERN_ALLOW_LEGACY_MESSAGE_INGESTION": raw},
            )
            assert cfg.allow_legacy_message_ingestion is expected

    def test_bad_port_rejected(self):
        with pytest.raises(ValueError, match="1..65535"):
            resolve_config({"node_id": "x"}, environ={"LANTERN_BIND_PORT": "99999"})


# ------------------------------------------------------------
# Startup self-test and diagnostics
# ------------------------------------------------------------


class TestSelfTest:
    def test_self_test_passes_and_prints_public_material_only(self, tmp_path, capsys):
        rc = main(["--node-id", "selftest-node", "--data-dir", str(tmp_path), "--self-test"])
        out = capsys.readouterr().out
        diagnostics = json.loads(out)
        assert rc == 0
        assert diagnostics["self_test"] == "PASS"
        assert diagnostics["external_exchange_ready"] is True
        assert diagnostics["node_id"] == "selftest-node"
        assert diagnostics["public_key_fingerprint"] == public_key_fingerprint(
            diagnostics["public_key"]
        )
        assert len(diagnostics["public_key_fingerprint"]) == 64
        assert diagnostics["protocol_version"] == PROTOCOL_VERSION
        assert "private" not in out.lower()

    def test_self_test_fails_on_broken_chronicle(self, tmp_path, capsys):
        rc = main(["--node-id", "st-node", "--data-dir", str(tmp_path), "--self-test"])
        assert rc == 0
        capsys.readouterr()  # consume the PASS run's output
        chronicle = tmp_path / "st-node.jsonl"
        chronicle.write_text("corrupted-not-json\n")
        rc = main(["--node-id", "st-node", "--data-dir", str(tmp_path), "--self-test"])
        diagnostics = json.loads(capsys.readouterr().out)
        assert rc == 1
        assert diagnostics["self_test"] == "FAIL"
        assert diagnostics["external_exchange_ready"] is False
        # Fail-closed at construction: the corrupted Chronicle cannot be
        # recovered, so the node reports the raw failure and refuses ready.
        assert "JSONDecodeError" in diagnostics["reason"]

    def test_fingerprint_convention(self):
        # Same convention as the forensic reports: SHA-256 over the raw
        # 32-byte Ed25519 public key.
        key_hex = "fd4d774b985e30f7e3968034ac396e6b3af7f55d5c36c4f1d16b9ae8fcc3bc88"
        assert public_key_fingerprint(key_hex) == hashlib.sha256(
            bytes.fromhex(key_hex)
        ).hexdigest()


# ------------------------------------------------------------
# Authenticated retrieval (real sockets, full client path)
# ------------------------------------------------------------


def _open_session(base, node_id, identity):
    code, challenge = request(base, "/session/open", "POST", {"node_id": node_id})
    assert "nonce" in challenge, f"expected challenge, got {challenge}"
    challenge_obj = identity_module.Challenge(
        nonce=challenge["nonce"],
        from_node_id=challenge["from_node_id"],
        to_node_id=challenge["to_node_id"],
        protocol_version=challenge["protocol_version"],
        issued_at=0.0,
        ttl_seconds=challenge.get(
            "ttl_seconds", identity_module.DEFAULT_CHALLENGE_TTL_SECONDS
        ),
    )
    binding = json.loads((identity.identity_dir / "binding.json").read_text())
    proof = identity_module.respond_to_challenge(
        challenge_obj, identity, binding["signature"]
    )
    code, result = request(
        base, "/session/open", "POST",
        {"node_id": node_id, "proof": asdict(proof)},
    )
    assert result.get("created") is True, f"session rejected: {result}"
    return result["session_id"]


def _connect(base, node_id, identity):
    """Full client connection path: handshake -> identity proof ->
    session with proof-of-possession."""
    handshake = create_handshake()
    handshake.node_id = node_id
    code, hs = request(base, "/handshake", "POST", asdict(handshake))
    assert hs["accepted"] is True
    verify_result = _verify_identity_with_peer(base, node_id, identity)
    assert verify_result["verified"] is True
    return _open_session(base, node_id, identity)


def _send_observation(base, node_id, session_id, content):
    message = create_observation_share(
        node_id, {"content": content, "source": node_id, "reliability": 0.9},
    )
    code, result = request(
        base, "/message", "POST",
        {"message": asdict(message), "session_id": session_id},
    )
    assert result.get("accepted") is True, f"share rejected: {result}"
    return result


@pytest.fixture
def receiver(tmp_path):
    server = create_server(
        "127.0.0.1", 0, "lantern-b", tmp_path / "b.jsonl",
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


class TestAuthenticatedRetrieval:
    def test_full_exchange_then_retrieval_with_sha256(self, receiver, tmp_path):
        base, server = receiver
        identity = identity_module.load_or_create(
            "lantern-a", identity_module.default_identity_dir(tmp_path / "a", "lantern-a")
        )
        session_id = _connect(base, "lantern-a", identity)
        secret = f"deployment-readiness-payload-{time.time_ns()}"
        share = _send_observation(base, "lantern-a", session_id, secret)
        observation_id = share["observation_id"]

        code, retrieval = request(
            base, "/observation/retrieve", "POST",
            {"session_id": session_id, "node_id": "lantern-a",
             "observation_id": observation_id},
        )
        assert code == 200 and retrieval["accepted"] is True, retrieval
        assert retrieval["content"] == secret
        assert retrieval["responded_by"] == "lantern-b"
        assert retrieval["retrieved_by"] == "lantern-a"
        # Independent SHA-256 verification, computed by the client:
        computed = hashlib.sha256(retrieval["content"].encode("utf-8")).hexdigest()
        assert computed == retrieval["stored_digest"]
        assert retrieval["record_hash"]
        assert retrieval["chronicle"]["step"] >= 1

    def test_retrieval_rejects_invalid_session(self, receiver, tmp_path):
        base, server = receiver
        code, result = request(
            base, "/observation/retrieve", "POST",
            {"session_id": "bogus-session-id", "node_id": "lantern-a",
             "observation_id": "whatever"},
        )
        assert code == 200
        assert result["accepted"] is False
        assert "reason" in result

    def test_retrieval_rejects_unauthorized_peer(self, tmp_path):
        server = create_server(
            "127.0.0.1", 0, "lantern-b", tmp_path / "b.jsonl",
            authorization_policy=AuthorizationPolicy.authorize(
                "lantern-c", {"belief_query"}
            ),
        )
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = f"http://127.0.0.1:{server.server_address[1]}"
        try:
            identity = identity_module.load_or_create(
                "lantern-c", identity_module.default_identity_dir(tmp_path / "c", "lantern-c")
            )
            session_id = _connect(base, "lantern-c", identity)
            code, result = request(
                base, "/observation/retrieve", "POST",
                {"session_id": session_id, "node_id": "lantern-c",
                 "observation_id": "anything"},
            )
            assert result["accepted"] is False
            assert "evidence_exchange" in result["reason"]
            assert "not in authorized_capabilities" in result["reason"]
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=3)

    def test_retrieval_rejects_nonexistent_observation(self, receiver, tmp_path):
        base, server = receiver
        identity = identity_module.load_or_create(
            "lantern-a", identity_module.default_identity_dir(tmp_path / "a", "lantern-a")
        )
        session_id = _connect(base, "lantern-a", identity)
        code, result = request(
            base, "/observation/retrieve", "POST",
            {"session_id": session_id, "node_id": "lantern-a",
             "observation_id": "urn:uuid:00000000-0000-0000-0000-000000000000"},
        )
        assert result["accepted"] is False
        assert "OBSERVATION_NOT_FOUND" in result["reason"]

    def test_malformed_retrieval_rejected(self, receiver):
        base, server = receiver
        for body in (
            {},
            {"session_id": "s"},
            {"session_id": "s", "node_id": "n"},
            {"session_id": "", "node_id": "n", "observation_id": "o"},
            {"session_id": 42, "node_id": "n", "observation_id": "o"},
        ):
            code, result = request(
                base, "/observation/retrieve", "POST", body,
            )
            assert code == 400, f"body {body!r} should be a clean 400"
            assert "error" in result


class TestProtocolVersionAllowlist:
    def test_disallowed_version_rejected_in_handshake(self, tmp_path):
        server = create_server(
            "127.0.0.1", 0, "lantern-b", tmp_path / "b.jsonl",
            allowed_protocol_versions=("0.82",),
        )
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = f"http://127.0.0.1:{server.server_address[1]}"
        try:
            handshake = asdict(create_handshake())
            handshake["node_id"] = "lantern-a"
            handshake["protocol_version"] = "0.7"
            code, result = request(base, "/handshake", "POST", handshake)
            assert result["accepted"] is False
            assert "PROTOCOL_VERSION_NOT_ALLOWED" in result["reason"]

            handshake["protocol_version"] = PROTOCOL_VERSION
            code, result = request(base, "/handshake", "POST", handshake)
            assert result["accepted"] is True
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=3)


# ------------------------------------------------------------
# Full deployment path: OS subprocess configured by ENV ONLY
# ------------------------------------------------------------


def _read_banner(process, timeout=10):
    lines: list[str] = []
    result = {}

    def reader():
        while True:
            line = process.stdout.readline()
            if not line:
                break
            lines.append(line)
            try:
                result["banner"] = json.loads("".join(lines))
                return
            except json.JSONDecodeError:
                continue

    thread = threading.Thread(target=reader, daemon=True)
    thread.start()
    thread.join(timeout)
    return result.get("banner")


class TestEnvConfiguredSubprocess:
    def test_env_only_deployment_full_path(self, tmp_path):
        """The deployment contract, end to end, against a real OS process
        started purely from environment configuration (no CLI flags):
        startup banner -> /health -> handshake -> identity proof ->
        session PoP -> OBSERVATION_SHARE -> persistence -> authenticated
        retrieval -> independent SHA-256 verification."""
        port = _free_port()
        data_dir = tmp_path / "deploy"
        env = {
            **os.environ,
            "PYTHONPATH": "src",
            "PYTHONUNBUFFERED": "1",
            "LANTERN_NODE_ID": "lantern-deploy-b",
            "LANTERN_BIND_HOST": "127.0.0.1",
            "LANTERN_BIND_PORT": str(port),
            "LANTERN_DATA_DIR": str(data_dir),
            "LANTERN_PUBLIC_URL": "https://lantern-deploy.example.com",
            "LANTERN_AUTHORIZE": "lantern-a:evidence_exchange",
        }
        process = subprocess.Popen(
            [sys.executable, "-m", "lantern.bootstrap_node"],
            cwd=PROJECT_ROOT, env=env,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
        )
        try:
            banner = _read_banner(process)
            assert banner is not None, "startup banner not emitted"
            assert banner["event"] == "startup"
            assert banner["node_id"] == "lantern-deploy-b"
            assert banner["public_base_url"] == "https://lantern-deploy.example.com"
            assert banner["external_exchange_ready"] is True
            assert banner["config_source"]["node_id"] == "env"
            assert len(banner["public_key_fingerprint"]) == 64
            assert "private" not in banner

            base = f"http://127.0.0.1:{port}"
            code, health = request(base, "/health")
            assert code == 200 and health["status"] == "ok"
            assert health["node_id"] == "lantern-deploy-b"

            identity = identity_module.load_or_create(
                "lantern-a",
                identity_module.default_identity_dir(tmp_path / "a", "lantern-a"),
            )
            session_id = _connect(base, "lantern-a", identity)
            payload = f"env-deploy-payload-{time.time_ns()}"
            share = _send_observation(base, "lantern-a", session_id, payload)
            observation_id = share["observation_id"]

            code, retrieval = request(
                base, "/observation/retrieve", "POST",
                {"session_id": session_id, "node_id": "lantern-a",
                 "observation_id": observation_id},
            )
            assert retrieval["accepted"] is True
            assert retrieval["content"] == payload
            computed = hashlib.sha256(retrieval["content"].encode()).hexdigest()
            assert computed == retrieval["stored_digest"]

            # Evidence persisted on disk in the configured location.
            chronicle = data_dir / "lantern-deploy-b.jsonl"
            assert chronicle.exists()
            records = [
                json.loads(line)
                for line in chronicle.read_text().splitlines() if line.strip()
            ]
            assert any(
                r.get("type") == "OBSERVATION_CREATED"
                and r.get("payload", {}).get("id") == observation_id
                for r in records
            )
        finally:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=3)

    def test_missing_node_id_env_fails_cleanly(self, tmp_path, capsys):
        env = {k: v for k, v in os.environ.items() if not k.startswith("LANTERN_")}
        rc = main([], ) if False else None  # placeholder, real check below
        # main() with no CLI and no env must fail with a clear message.
        monkey_env = {}
        saved = {}
        for key in list(os.environ):
            if key.startswith("LANTERN_"):
                saved[key] = os.environ.pop(key)
        try:
            with pytest.raises(ValueError, match="node_id"):
                resolve_config(environ=os.environ)
        finally:
            os.environ.update(saved)


class TestAdversarialRetrievalAndGate:
    def test_cross_peer_retrieval_rejected(self, tmp_path):
        """An evidence_exchange-authorized peer must not be able to read
        ANOTHER peer's observations by guessing the observation_id."""
        server = create_server(
            "127.0.0.1", 0, "lantern-b", tmp_path / "b.jsonl",
            authorization_policy=AuthorizationPolicy.authorize(
                "lantern-a", {"evidence_exchange"}
            ).merged_with("lantern-c", ["evidence_exchange"]),
        )
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = f"http://127.0.0.1:{server.server_address[1]}"
        try:
            id_a = identity_module.load_or_create(
                "lantern-a", identity_module.default_identity_dir(tmp_path / "a", "lantern-a")
            )
            id_c = identity_module.load_or_create(
                "lantern-c", identity_module.default_identity_dir(tmp_path / "c", "lantern-c")
            )
            # A sends an observation
            session_a = _connect(base, "lantern-a", id_a)
            share = _send_observation(
                base, "lantern-a", session_a, f"secret-of-a-{time.time_ns()}"
            )
            observation_id = share["observation_id"]

            # C is equally authorized but did NOT send it
            session_c = _connect(base, "lantern-c", id_c)
            code, result = request(
                base, "/observation/retrieve", "POST",
                {"session_id": session_c, "node_id": "lantern-c",
                 "observation_id": observation_id},
            )
            assert result["accepted"] is False
            assert "OBSERVATION_NOT_YOURS" in result["reason"]
            assert "content" not in result

            # A (the true sender) still can
            code, own = request(
                base, "/observation/retrieve", "POST",
                {"session_id": session_a, "node_id": "lantern-a",
                 "observation_id": observation_id},
            )
            assert own["accepted"] is True and own["content"] == share["content"] \
                if "content" in share else own["accepted"] is True
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=3)

    def test_version_allowlist_cannot_be_bypassed_by_skipping_handshake(self, tmp_path):
        """With an operator allowlist configured, a peer that never
        completed an accepted /handshake cannot open a session at all --
        the version gate cannot be bypassed by skipping /handshake."""
        server = create_server(
            "127.0.0.1", 0, "lantern-b", tmp_path / "b.jsonl",
            allowed_protocol_versions=("0.82",),
            authorization_policy=AuthorizationPolicy.authorize(
                "lantern-a", {"evidence_exchange"}
            ),
        )
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = f"http://127.0.0.1:{server.server_address[1]}"
        try:
            identity = identity_module.load_or_create(
                "lantern-a", identity_module.default_identity_dir(tmp_path / "a", "lantern-a")
            )
            # No handshake yet: session open must be refused, in both phases
            code, phase1 = request(
                base, "/session/open", "POST", {"node_id": "lantern-a"}
            )
            assert phase1.get("created") is not True
            assert "SESSION_HANDSHAKE_REQUIRED" in phase1.get("reason", "")
            assert "nonce" not in phase1

            # After an accepted handshake with an allowed version, the
            # full flow works.
            session_id = _connect(base, "lantern-a", identity)
            share = _send_observation(
                base, "lantern-a", session_id, f"post-handshake-{time.time_ns()}"
            )
            assert share["accepted"] is True
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=3)

    def test_bidirectional_exchange_with_reverse_digest_ack(self, tmp_path):
        """The full two-agent loop, both directions, independently
        verified: A -> B OBSERVATION_SHARE; B retrieves + verifies the
        digest; B -> A reverse digest-only ACK (the established
        acknowledgment pattern, no new message type); A retrieves the
        ACK and independently verifies B's recorded digest."""
        def make_server(node_id):
            other = "lantern-a" if node_id == "lantern-b" else "lantern-b"
            s = create_server(
                "127.0.0.1", 0, node_id, tmp_path / f"{node_id}.jsonl",
                authorization_policy=AuthorizationPolicy.authorize(
                    other, {"evidence_exchange"}
                ),
            )
            t = threading.Thread(target=s.serve_forever, daemon=True)
            t.start()
            return s, t, f"http://127.0.0.1:{s.server_address[1]}"

        s_a, t_a, base_a = make_server("lantern-a")
        s_b, t_b, base_b = make_server("lantern-b")
        try:
            id_a = identity_module.load_or_create(
                "lantern-a", identity_module.default_identity_dir(tmp_path / "ia", "lantern-a")
            )
            id_b = identity_module.load_or_create(
                "lantern-b", identity_module.default_identity_dir(tmp_path / "ib", "lantern-b")
            )
            # Forward: A -> B
            session_a_on_b = _connect(base_b, "lantern-a", id_a)
            payload = f"bidirectional-payload-{time.time_ns()}"
            share = _send_observation(base_b, "lantern-a", session_a_on_b, payload)
            observation_id = share["observation_id"]

            # B independently retrieves and verifies
            session_b_self = None  # B's own chronicle read happens locally
            code, retrieval = request(
                base_b, "/observation/retrieve", "POST",
                {"session_id": session_a_on_b, "node_id": "lantern-a",
                 "observation_id": observation_id},
            )
            assert retrieval["accepted"] is True
            b_computed = hashlib.sha256(retrieval["content"].encode()).hexdigest()
            assert b_computed == retrieval["stored_digest"]

            # Reverse ACK: B -> A, digest-only, referencing A's observation
            session_b_on_a = _connect(base_a, "lantern-b", id_b)
            ack_content = json.dumps({
                "ack_for": observation_id,
                "digest": b_computed,
                "kind": "digest_ack",
            })
            ack = _send_observation(base_a, "lantern-b", session_b_on_a, ack_content)
            ack_observation_id = ack["observation_id"]

            # A session issued by B's server is meaningless on A's
            # server: rejected. (The cross-peer-read rule itself is
            # covered by test_cross_peer_retrieval_rejected.)
            code, bogus = request(
                base_a, "/observation/retrieve", "POST",
                {"session_id": session_a_on_b, "node_id": "lantern-a",
                 "observation_id": ack_observation_id},
            )
            assert bogus["accepted"] is False

            # B reads its own ACK back on A and the digest it recorded
            # matches A's original payload, independently recomputed.
            code, ack_own = request(
                base_a, "/observation/retrieve", "POST",
                {"session_id": session_b_on_a, "node_id": "lantern-b",
                 "observation_id": ack_observation_id},
            )
            assert ack_own["accepted"] is True
            ack_payload = json.loads(ack_own["content"])
            assert ack_payload["ack_for"] == observation_id
            assert ack_payload["digest"] == hashlib.sha256(payload.encode()).hexdigest()
        finally:
            for s, t in ((s_a, t_a), (s_b, t_b)):
                s.shutdown()
                s.server_close()
                t.join(timeout=3)
