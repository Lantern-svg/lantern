"""Gate 2 Finding 9: Session issuance without per-request identity proof.

Vulnerability: /session/open grants a session based on
_known_public_keys membership alone — a set populated once, at first
successful verification. It does not require the current caller to
prove, at session-open time, that they hold the private key for that
node_id.

Any caller who knows a previously-verified node_id (which for
lantern-field-experiment-1 is public information, posted in a GitHub
Discussion) can call /session/open with that node_id and receive a
valid session bearer token without ever possessing the corresponding
private key.

This is distinct from the accepted TOFU tradeoff. TOFU is about
trusting the *first* contact for a given node_id. This is a gap on
*every* contact after the first: nothing at session-open time re-asks
"prove you're still the key-holder right now."

Fix: require a fresh signed challenge at session-open time.
"""

import json
import threading
from pathlib import Path
from dataclasses import asdict
from urllib.request import Request, urlopen
from urllib.error import HTTPError

import pytest

from lantern import identity as identity_module
from lantern.bootstrap_client import _verify_identity_with_peer
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


class TestSessionProofOfPossession:
    """Finding 9: /session/open must require per-request proof of
    private-key possession, not just _known_public_keys membership."""

    def test_session_open_rejects_caller_without_proof(self, node, tmp_path):
        """After identity X is verified, an attacker who knows X's
        node_id but does NOT hold X's private key must NOT be able to
        open a session for X.

        Before the fix: this test FAILS because /session/open creates
        a session based on _known_public_keys membership alone.
        After the fix: this test PASSES because /session/open requires
        a fresh signed challenge response.
        """
        base, server = node

        # Step 1: Legitimately verify identity "lantern-a" against the server.
        # This stores lantern-a's public key in _known_public_keys.
        identity_dir = identity_module.default_identity_dir(
            tmp_path / "legit", "lantern-a"
        )
        legit_identity = identity_module.load_or_create("lantern-a", identity_dir)

        # Handshake first
        hs = create_handshake()
        hs.node_id = "lantern-a"
        request(base, "/handshake", "POST", asdict(hs))

        # Full identity verification (challenge -> respond -> verify)
        verify_result = _verify_identity_with_peer(base, "lantern-a", legit_identity)
        assert verify_result["verified"] is True

        # Step 2: Attacker knows the node_id "lantern-a" but has NO
        # private key for it. Attacker calls /session/open with just
        # {"node_id": "lantern-a"} and no proof of private-key possession.
        code, result = request(base, "/session/open", "POST", {"node_id": "lantern-a"})

        # Step 3: The session MUST NOT be created without proof.
        # Before the fix, this assertion fails -- the vulnerability.
        assert result.get("created") is not True, (
            "VULNERABILITY: /session/open created a session for 'lantern-a' "
            "without requiring proof of private-key possession. Any caller who "
            "knows the node_id can obtain a session bearer token."
        )

    def test_session_open_with_valid_proof_succeeds(self, node, tmp_path):
        """After the fix, a caller who DOES hold the private key can
        complete the challenge-response and get a session.

        Before the fix: this test FAILS because /session/open does not
        support the challenge-response flow.
        After the fix: this test PASSES.
        """
        base, server = node

        # Verify identity
        identity_dir = identity_module.default_identity_dir(
            tmp_path / "legit2", "lantern-a"
        )
        legit_identity = identity_module.load_or_create("lantern-a", identity_dir)

        hs = create_handshake()
        hs.node_id = "lantern-a"
        request(base, "/handshake", "POST", asdict(hs))

        verify_result = _verify_identity_with_peer(base, "lantern-a", legit_identity)
        assert verify_result["verified"] is True

        # Phase 1: Request a challenge from /session/open
        code, challenge = request(
            base, "/session/open", "POST", {"node_id": "lantern-a"}
        )

        # The response should be a challenge, not a session
        assert challenge.get("created") is not True, (
            f"Expected challenge response, got session: {challenge}"
        )
        assert "nonce" in challenge, (
            f"Expected challenge with nonce, got: {challenge}"
        )

        # Phase 2: Sign the challenge with the private key
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
        binding = json.loads(
            (legit_identity.identity_dir / "binding.json").read_text()
        )
        proof = identity_module.respond_to_challenge(
            challenge_obj, legit_identity, binding["signature"]
        )

        # Phase 3: Submit the proof to get a session
        code, result = request(
            base, "/session/open", "POST",
            {"node_id": "lantern-a", "proof": asdict(proof)},
        )
        assert result.get("created") is True, (
            f"Session should be created with valid proof: {result}"
        )
        assert "session_id" in result


class TestSessionDowngradeRejection:
    """A malicious or unpatched server that returns {created: true}
    immediately -- no nonce, no challenge -- must NOT be accepted by
    the client.  This is a downgrade attack: the attacker skips the
    proof-of-possession scheme entirely by pretending the session is
    already issued.  The client must reject this by default."""

    def test_client_rejects_created_true_without_nonce(self, tmp_path):
        """Simulate a malicious server that returns created:true with no
        nonce for /session/open.  The client's _open_session_with_proof
        must reject it (raise SystemExit), not silently accept the
        session.

        Before the fix: the client has a fallback branch
        'if challenge_data.get("created"): session = challenge_data'
        that accepts the downgrade.  This test FAILS because the
        client does NOT raise SystemExit -- it accepts the session.
        After the fix: the fallback is removed, the client raises
        SystemExit, and this test PASSES.
        """
        import http.server
        import json as _json

        class _MaliciousHandler(http.server.BaseHTTPRequestHandler):
            """Always returns created:true for /session/open -- no
            challenge issued, no proof required."""

            def do_POST(self):
                if self.path == "/session/open":
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(_json.dumps({
                        "created": True,
                        "session_id": "FAKE-DOWNGRADE-TOKEN",
                        "outcome": "created",
                        "reason": "session created",
                    }).encode())
                else:
                    self.send_response(404)
                    self.end_headers()

            def log_message(self, *args):
                pass

        server = http.server.HTTPServer(("127.0.0.1", 0), _MaliciousHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = f"http://127.0.0.1:{server.server_address[1]}"

        try:
            from lantern.bootstrap_client import _open_session_with_proof

            # Create a real identity for the client to use.
            identity_dir = identity_module.default_identity_dir(
                tmp_path / "client_id", "lantern-a"
            )
            local_identity = identity_module.load_or_create("lantern-a", identity_dir)

            # The client calls _open_session_with_proof against the
            # malicious server.  It must raise SystemExit (reject),
            # NOT return a session.
            with pytest.raises(SystemExit) as exc_info:
                _open_session_with_proof(base, "lantern-a", local_identity)

            # Verify the exit message indicates session rejection.
            exit_data = json.loads(str(exc_info.value))
            assert exit_data["status"] == "session_rejected", (
                f"Expected session_rejected, got: {exit_data}"
            )
            assert exit_data["session"]["created"] is True, (
                "The malicious server's created:true response should be "
                "included in the rejection for diagnostic purposes."
            )
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=3)
