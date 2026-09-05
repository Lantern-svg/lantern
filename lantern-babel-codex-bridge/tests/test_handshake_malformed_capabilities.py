"""Regression coverage for Gate 9: malformed /handshake `capabilities`
input must be rejected cleanly (controlled 400 at the HTTP layer, or a
non-accepted HandshakeResponse at the evaluate_handshake() layer) rather
than crashing the request handler with an uncaught AttributeError.

Root cause (fixed): HandshakeRequest is a plain dataclass and does not
enforce its `capabilities: dict` type hint at runtime. Before this fix,
`HandshakeRequest(**body)` in bootstrap_node.py's do_POST happily
constructed an instance with capabilities as a string (or any other
type), and the crash only surfaced later, inside evaluate_handshake()'s
`for capability, enabled in request.capabilities.items()` loop, as an
uncaught AttributeError -- outside the (TypeError, ValueError, KeyError,
json.JSONDecodeError, IdentityError) tuple do_POST already catches, so
it propagated as an unhandled exception (500-equivalent socketserver
traceback) instead of a controlled 400 response.

Two layers are covered here:
1. bootstrap_node.py do_POST -- the real HTTP boundary, matching the
   isinstance() validation convention every other endpoint
   (/identity/challenge, /session/open, /message, /connection-state)
   already used.
2. handshake.evaluate_handshake() itself -- defense in depth, since it
   is a public function other callers (tests, future code paths) can
   invoke directly with a hand-built HandshakeRequest, bypassing the
   HTTP layer's validation entirely.

The three original malformed-request crashes (observed 2026-09-02,
127.0.0.1, source process unidentified) are preserved as-is in
/tmp/lantern_public_experiment/node.log; they are not reproduced or
deleted by this suite.
"""

import threading

import pytest
from urllib.error import HTTPError

from lantern.bootstrap_node import create_server
from lantern.capability_authorization import AuthorizationPolicy
from lantern.handshake import HandshakeRequest, create_handshake, evaluate_handshake

from test_bootstrap_transport import request as http_request


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


# ============================================================
# Layer 2: evaluate_handshake() unit-level defense in depth
# ============================================================

def test_evaluate_handshake_rejects_capabilities_as_string():
    req = HandshakeRequest(
        node_id="x", protocol_version="0.82", capabilities="not-a-dict", timestamp="t"
    )
    response = evaluate_handshake(req)
    assert response.accepted is False
    assert response.shared_capabilities == {}
    assert "capabilities" in response.reason.lower()


def test_evaluate_handshake_rejects_capabilities_as_list():
    req = HandshakeRequest(
        node_id="x", protocol_version="0.82", capabilities=["evidence_exchange"], timestamp="t"
    )
    response = evaluate_handshake(req)
    assert response.accepted is False
    assert response.shared_capabilities == {}


def test_evaluate_handshake_rejects_capabilities_as_none():
    req = HandshakeRequest(
        node_id="x", protocol_version="0.82", capabilities=None, timestamp="t"
    )
    response = evaluate_handshake(req)
    assert response.accepted is False
    assert response.shared_capabilities == {}


def test_evaluate_handshake_rejects_capabilities_as_int():
    req = HandshakeRequest(
        node_id="x", protocol_version="0.82", capabilities=123, timestamp="t"
    )
    response = evaluate_handshake(req)
    assert response.accepted is False


def test_evaluate_handshake_still_accepts_valid_capabilities_dict():
    # Compatibility: existing well-formed callers must behave identically.
    request_message = create_handshake()
    response = evaluate_handshake(request_message)
    assert response.accepted is True
    assert response.reason == "Compatible"


def test_evaluate_handshake_malformed_nested_values_do_not_crash_and_are_not_widened():
    # Malformed VALUES (not the container itself) inside an otherwise
    # valid dict must not crash, and must never be echoed back as
    # anything other than a real bool True for genuinely shared,
    # supported, truthy capabilities. This already worked correctly
    # before this fix (truthiness handles non-bool values safely) --
    # locking it in explicitly so it can't silently regress.
    request_message = create_handshake(
        capabilities={"evidence_exchange": "yes", "handshake": None, "belief_query": 1}
    )
    response = evaluate_handshake(request_message)
    assert response.accepted is True
    assert response.shared_capabilities == {"evidence_exchange": True, "belief_query": True}
    for value in response.shared_capabilities.values():
        assert value is True


# ============================================================
# Layer 1: real HTTP boundary (bootstrap_node.py do_POST)
# ============================================================

def test_http_handshake_rejects_capabilities_as_string(node):
    base, server = node
    with pytest.raises(HTTPError) as error:
        http_request(
            base,
            "/handshake",
            "POST",
            {
                "node_id": "lantern-a",
                "protocol_version": "0.82",
                "capabilities": "not-a-dict",
                "timestamp": "2026-09-02T00:00:00Z",
            },
        )
    assert error.value.code == 400


def test_http_handshake_rejects_capabilities_as_list(node):
    base, server = node
    with pytest.raises(HTTPError) as error:
        http_request(
            base,
            "/handshake",
            "POST",
            {
                "node_id": "lantern-a",
                "protocol_version": "0.82",
                "capabilities": ["evidence_exchange"],
                "timestamp": "2026-09-02T00:00:00Z",
            },
        )
    assert error.value.code == 400


def test_http_handshake_rejects_missing_capabilities(node):
    base, server = node
    with pytest.raises(HTTPError) as error:
        http_request(
            base,
            "/handshake",
            "POST",
            {
                "node_id": "lantern-a",
                "protocol_version": "0.82",
                "timestamp": "2026-09-02T00:00:00Z",
            },
        )
    assert error.value.code == 400


def test_http_handshake_malformed_request_does_not_mutate_chronicle(node):
    base, server = node
    with pytest.raises(HTTPError):
        http_request(
            base,
            "/handshake",
            "POST",
            {
                "node_id": "lantern-a",
                "protocol_version": "0.82",
                "capabilities": "not-a-dict",
                "timestamp": "2026-09-02T00:00:00Z",
            },
        )
    # NOT authenticated, NOT a session, NOT a Chronicle/Codex mutation --
    # a rejected handshake must leave zero trace in observation state.
    assert len(server.node.lantern.kernel.observations) == 0


def test_http_handshake_still_accepts_valid_dict_capabilities(node):
    base, server = node
    request_message = create_handshake()
    from dataclasses import asdict
    status, response = http_request(base, "/handshake", "POST", asdict(request_message))
    assert status == 200
    assert response["accepted"] is True


def test_http_handshake_malformed_then_valid_request_succeeds_and_server_stays_healthy(node):
    """The critical invariant: MALFORMED REQUEST -> controlled rejection
    -> SERVER STILL HEALTHY -> VALID REQUEST -> NORMAL SUCCESS."""
    base, server = node

    with pytest.raises(HTTPError) as error:
        http_request(
            base,
            "/handshake",
            "POST",
            {
                "node_id": "lantern-a",
                "protocol_version": "0.82",
                "capabilities": "not-a-dict",
                "timestamp": "2026-09-02T00:00:00Z",
            },
        )
    assert error.value.code == 400

    # Server must still be alive and answer a normal, unrelated request.
    status, health = http_request(base, "/health", "GET")
    assert status == 200
    assert health["status"] == "ok"

    # And a subsequent VALID handshake must succeed normally, exactly as
    # if the malformed request had never happened.
    from dataclasses import asdict
    request_message = create_handshake()
    status, response = http_request(base, "/handshake", "POST", asdict(request_message))
    assert status == 200
    assert response["accepted"] is True


def test_http_handshake_repeated_malformed_requests_do_not_degrade_server(node):
    base, server = node

    for _ in range(5):
        with pytest.raises(HTTPError) as error:
            http_request(
                base,
                "/handshake",
                "POST",
                {
                    "node_id": "lantern-a",
                    "protocol_version": "0.82",
                    "capabilities": "not-a-dict",
                    "timestamp": "2026-09-02T00:00:00Z",
                },
            )
        assert error.value.code == 400

    # Still healthy, still accepting valid requests after repeated abuse.
    status, health = http_request(base, "/health", "GET")
    assert status == 200
    assert health["status"] == "ok"

    from dataclasses import asdict
    request_message = create_handshake()
    status, response = http_request(base, "/handshake", "POST", asdict(request_message))
    assert status == 200
    assert response["accepted"] is True

    # Zero observations/session state leaked in from any of the 5
    # malformed attempts.
    assert len(server.node.lantern.kernel.observations) == 0
