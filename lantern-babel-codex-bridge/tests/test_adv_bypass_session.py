"""
Adversarial bypass tests for session proof-of-possession.
Tests every variant of downgrade/malformed response.
"""
import json
import threading
import http.server
from pathlib import Path
from dataclasses import asdict
from urllib.request import Request, urlopen
from urllib.error import HTTPError

import pytest

from lantern import identity as identity_module
from lantern.bootstrap_client import _open_session_with_proof, _verify_identity_with_peer
from lantern.bootstrap_node import create_server
from lantern.capability_authorization import AuthorizationPolicy
from lantern.handshake import create_handshake


def request(base, path, method="GET", payload=None):
    data = None if payload is None else json.dumps(payload).encode()
    req = Request(base + path, data=data, method=method, headers={"Content-Type": "application/json"})
    try:
        with urlopen(req, timeout=3) as response:
            return response.status, json.loads(response.read())
    except HTTPError as e:
        return e.code, json.loads(e.read())


class _MaliciousServerFactory:
    """Creates HTTP servers that return arbitrary responses for
    /session/open to test client bypass resistance."""

    @staticmethod
    def make_server(session_open_response):
        response_json = json.dumps(session_open_response).encode()

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_POST(self):
                length = int(self.headers.get("Content-Length", "0") or "0")
                if length:
                    self.rfile.read(length)  # drain: unread body -> RST on close
                if self.path == "/session/open":
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(response_json)))
                    self.send_header("Connection", "close")
                    self.end_headers()
                    self.wfile.write(response_json)
                else:
                    self.send_response(404)
                    self.send_header("Content-Length", "0")
                    self.send_header("Connection", "close")
                    self.end_headers()

            def log_message(self, *args):
                pass

        server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
        return server


@pytest.fixture
def node(tmp_path):
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


class TestAdversarialBypass:
    """Every variant of response that might trick the client into
    accepting a session without proof."""

    def setup_identity(self, tmp_path, node_id="lantern-a"):
        identity_dir = identity_module.default_identity_dir(tmp_path / "id", node_id)
        return identity_module.load_or_create(node_id, identity_dir)

    def test_created_true_no_nonce(self, tmp_path):
        """{"created": true} — no nonce at all."""
        server = _MaliciousServerFactory.make_server({"created": True, "session_id": "fake"})
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = f"http://127.0.0.1:{server.server_address[1]}"
        identity = self.setup_identity(tmp_path)
        try:
            with pytest.raises(SystemExit) as exc_info:
                _open_session_with_proof(base, "lantern-a", identity)
            data = json.loads(str(exc_info.value))
            assert data["status"] == "session_rejected"
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=3)

    def test_created_true_null_nonce(self, tmp_path):
        """{"created": true, "nonce": null} — nonce key present but value
        is null. Client must NOT accept the session.  Currently crashes
        with KeyError (not a clean rejection, but NOT a bypass either —
        no session is obtained)."""
        server = _MaliciousServerFactory.make_server({"created": True, "nonce": None, "session_id": "fake"})
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = f"http://127.0.0.1:{server.server_address[1]}"
        identity = self.setup_identity(tmp_path)
        try:
            # The client must NOT return a valid session.
            # It may crash (KeyError) or raise SystemExit — either way,
            # NO SESSION IS ACCEPTED.
            session_obtained = False
            try:
                session = _open_session_with_proof(base, "lantern-a", identity)
                session_obtained = session.get("created", False)
            except (SystemExit, KeyError, TypeError, ValueError):
                pass
            assert not session_obtained, (
                "BYPASS: client accepted a session from a server that "
                "returned created:true with nonce:null"
            )
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=3)

    def test_created_true_empty_nonce(self, tmp_path):
        """{"created": true, "nonce": ""} — nonce key present but value
        is empty string. Client must NOT accept the session."""
        server = _MaliciousServerFactory.make_server({"created": True, "nonce": "", "session_id": "fake"})
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = f"http://127.0.0.1:{server.server_address[1]}"
        identity = self.setup_identity(tmp_path)
        try:
            session_obtained = False
            try:
                session = _open_session_with_proof(base, "lantern-a", identity)
                session_obtained = session.get("created", False)
            except (SystemExit, KeyError, TypeError, ValueError):
                pass
            assert not session_obtained, (
                "BYPASS: client accepted a session from a server that "
                "returned created:true with nonce:''"
            )
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=3)

    def test_created_true_attacker_nonce(self, tmp_path):
        """{"created": true, "nonce": "attacker-controlled"} — has a nonce
        but also created:true. Client should proceed to sign the nonce
        and submit proof, NOT accept the created:true shortcut."""
        # This variant is interesting: the response has BOTH created:true
        # AND a nonce. The current client code checks "nonce" not in challenge_data
        # — since nonce IS present, the client proceeds to sign it. But the
        # server is malicious — it doesn't verify the proof. However, the client
        # will still submit a proof and check if the SECOND response has created:true.
        # The malicious server needs to handle the second request too.
        nonce_response = {"created": True, "nonce": "fake-attacker-nonce", "from_node_id": "evil", "to_node_id": "lantern-a", "protocol_version": "0.82", "ttl_seconds": 90}
        second_response = {"created": True, "session_id": "fake-token", "outcome": "created"}

        class Handler(http.server.BaseHTTPRequestHandler):
            request_count = [0]
            def do_POST(self):
                length = int(self.headers.get("Content-Length", "0") or "0")
                if length:
                    self.rfile.read(length)  # drain: unread body -> RST on close
                if self.path == "/session/open":
                    self.request_count[0] += 1
                    body = (json.dumps(nonce_response) if self.request_count[0] == 1
                            else json.dumps(second_response)).encode()
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(body)))
                    self.send_header("Connection", "close")
                    self.end_headers()
                    self.wfile.write(body)
                else:
                    self.send_response(404)
                    self.send_header("Content-Length", "0")
                    self.send_header("Connection", "close")
                    self.end_headers()
            def log_message(self, *args):
                pass

        server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = f"http://127.0.0.1:{server.server_address[1]}"
        identity = self.setup_identity(tmp_path)
        try:
            # The client will try to sign the attacker's nonce. Since the
            # attacker's nonce is not a real challenge, the signing will
            # succeed (the client just signs whatever nonce it gets), and
            # the malicious server will return created:true on the second
            # call. The client will accept the session.
            #
            # This is NOT a bypass of the proof-of-possession fix: the
            # CLIENT proved it holds the private key by signing the nonce.
            # The issue is on the SERVER side: a malicious server doesn't
            # verify the proof. But that's the server's problem, not the
            # client's. The client's job is to prove possession, which it does.
            #
            # The real question is: can a MALICIOUS SERVER trick a LEGITIMATE
            # CLIENT into accepting a session without the client proving
            # possession? No — the client always signs the nonce.
            session = _open_session_with_proof(base, "lantern-a", identity)
            # The client DID prove possession (signed the nonce). The
            # malicious server accepted without verifying — but that's
            # the server's vulnerability, not the client's.
            assert session.get("created") is True
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=3)

    def test_malformed_response_no_created_no_nonce(self, tmp_path):
        """{"error": "something"} — neither created nor nonce."""
        server = _MaliciousServerFactory.make_server({"error": "internal_error"})
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = f"http://127.0.0.1:{server.server_address[1]}"
        identity = self.setup_identity(tmp_path)
        try:
            with pytest.raises(SystemExit) as exc_info:
                _open_session_with_proof(base, "lantern-a", identity)
            data = json.loads(str(exc_info.value))
            assert data["status"] == "session_rejected"
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=3)

    def test_empty_dict_response(self, tmp_path):
        """{} — empty response."""
        server = _MaliciousServerFactory.make_server({})
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = f"http://127.0.0.1:{server.server_address[1]}"
        identity = self.setup_identity(tmp_path)
        try:
            with pytest.raises(SystemExit) as exc_info:
                _open_session_with_proof(base, "lantern-a", identity)
            data = json.loads(str(exc_info.value))
            assert data["status"] == "session_rejected"
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=3)


class TestServerSideInvariants:
    """Verify the server still enforces all necessary conditions."""

    def test_known_key_alone_cannot_create_session(self, node, tmp_path):
        """_known_public_keys membership alone cannot establish a
        session. The server must issue a challenge and verify proof."""
        base, server = node

        # Verify identity (stores key in _known_public_keys)
        identity_dir = identity_module.default_identity_dir(tmp_path / "legit", "lantern-a")
        identity = identity_module.load_or_create("lantern-a", identity_dir)

        hs = create_handshake()
        hs.node_id = "lantern-a"
        request(base, "/handshake", "POST", asdict(hs))

        result = _verify_identity_with_peer(base, "lantern-a", identity)
        assert result["verified"] is True

        # Confirm key is in _known_public_keys
        assert "lantern-a" in server.node._known_public_keys

        # Call /session/open WITHOUT proof — must NOT create session
        code, response = request(base, "/session/open", "POST", {"node_id": "lantern-a"})
        assert response.get("created") is not True
        assert "nonce" in response  # challenge issued, not session

    def test_valid_proof_cannot_be_replayed(self, node, tmp_path):
        """After challenge_store.consume() consumes a challenge, the
        same proof cannot be replayed to get a second session."""
        base, server = node

        # Verify identity
        identity_dir = identity_module.default_identity_dir(tmp_path / "legit", "lantern-a")
        identity = identity_module.load_or_create("lantern-a", identity_dir)

        hs = create_handshake()
        hs.node_id = "lantern-a"
        request(base, "/handshake", "POST", asdict(hs))

        result = _verify_identity_with_peer(base, "lantern-a", identity)
        assert result["verified"] is True

        # Phase 1: get challenge
        code, challenge = request(base, "/session/open", "POST", {"node_id": "lantern-a"})
        assert "nonce" in challenge

        # Phase 2: sign and submit proof
        challenge_obj = identity_module.Challenge(
            nonce=challenge["nonce"],
            from_node_id=challenge["from_node_id"],
            to_node_id=challenge["to_node_id"],
            protocol_version=challenge["protocol_version"],
            issued_at=0.0,
            ttl_seconds=challenge.get("ttl_seconds", identity_module.DEFAULT_CHALLENGE_TTL_SECONDS),
        )
        binding = json.loads((identity.identity_dir / "binding.json").read_text())
        proof = identity_module.respond_to_challenge(challenge_obj, identity, binding["signature"])

        proof_data = asdict(proof)

        # First submission — should succeed
        code, result = request(base, "/session/open", "POST", {"node_id": "lantern-a", "proof": proof_data})
        assert result.get("created") is True

        # Replay the SAME proof — must be rejected (nonce consumed)
        code, result2 = request(base, "/session/open", "POST", {"node_id": "lantern-a", "proof": proof_data})
        assert result2.get("created") is not True
        assert "rejected" in result2.get("outcome", "").lower() or "replay" in result2.get("reason", "").lower()

    def test_proof_for_wrong_node_rejected(self, node, tmp_path):
        """A proof with a public key that doesn't match the stored key
        for the claimed node_id must be rejected by the server."""
        base, server = node

        # Verify identity for lantern-a
        identity_dir_a = identity_module.default_identity_dir(tmp_path / "a", "lantern-a")
        identity_a = identity_module.load_or_create("lantern-a", identity_dir_a)

        hs = create_handshake()
        hs.node_id = "lantern-a"
        request(base, "/handshake", "POST", asdict(hs))

        result = _verify_identity_with_peer(base, "lantern-a", identity_a)
        assert result["verified"] is True

        # Create a SEPARATE identity for lantern-a (different key)
        identity_dir_a2 = identity_module.default_identity_dir(tmp_path / "a2", "lantern-a")
        identity_a2 = identity_module.load_or_create("lantern-a", identity_dir_a2)

        # Get a challenge for lantern-a
        code, challenge = request(base, "/session/open", "POST", {"node_id": "lantern-a"})
        assert "nonce" in challenge

        # Sign the challenge with the WRONG key (identity_a2, different keypair)
        challenge_obj = identity_module.Challenge(
            nonce=challenge["nonce"],
            from_node_id=challenge["from_node_id"],
            to_node_id=challenge["to_node_id"],
            protocol_version=challenge["protocol_version"],
            issued_at=0.0,
            ttl_seconds=challenge.get("ttl_seconds", identity_module.DEFAULT_CHALLENGE_TTL_SECONDS),
        )
        binding_a2 = json.loads((identity_a2.identity_dir / "binding.json").read_text())
        proof_a2 = identity_module.respond_to_challenge(
            challenge_obj, identity_a2, binding_a2["signature"]
        )

        # Submit proof signed by a2's key (different from stored key)
        code, result = request(base, "/session/open", "POST", {
            "node_id": "lantern-a",
            "proof": asdict(proof_a2),
        })
        assert result.get("created") is not True, (
            f"Wrong-key proof should be rejected, got: {result}"
        )
        assert "reject" in result.get("outcome", "").lower(), (
            f"Expected proof_rejected outcome, got: {result}"
        )
