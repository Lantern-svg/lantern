"""Malformed-/handshake regression tests (integrity review 2026-09-02, fix implemented).

Invariant: every untrusted /handshake field is type-validated before unsafe
processing. Malformed input yields a clean HTTP 400; the node stays alive;
no session, identity, trust, or authorization state is created or mutated.
evaluate_handshake() is additionally hardened so a direct library call with
malformed fields returns a rejection instead of raising.

Uses an isolated local HTTP server on an ephemeral port. No external
network access.
"""

import json
import threading
import urllib.error
import urllib.request

import pytest

from lantern import identity as identity_module
from lantern.bootstrap_node import create_server
from lantern.capability_authorization import AuthorizationPolicy
from lantern.handshake import HandshakeRequest, create_handshake, evaluate_handshake


@pytest.fixture
def live_node(tmp_path):
    server = create_server(
        "127.0.0.1",
        0,
        "malformed-hs-node",
        tmp_path / "chronicle.jsonl",
        authorization_policy=AuthorizationPolicy.authorize(
            "malformed-hs-node", ["evidence_exchange"]
        ),
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    yield base, server
    server.shutdown()


def _post(base, path, payload):
    req = urllib.request.Request(
        base + path,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read())


def _get_health(base):
    with urllib.request.urlopen(base + "/health", timeout=5) as resp:
        return resp.status, json.loads(resp.read())


def _valid_handshake_body():
    hs = create_handshake()
    return {
        "node_id": "some-peer",
        "protocol_version": hs.protocol_version,
        "capabilities": dict(hs.capabilities),
        "timestamp": hs.timestamp,
    }


def test_valid_handshake_still_succeeds(live_node):
    base, server = live_node
    status, body = _post(base, "/handshake", _valid_handshake_body())
    assert status == 200
    assert body["accepted"] is True


def test_capabilities_as_string_returns_400_and_node_survives(live_node):
    base, server = live_node
    payload = _valid_handshake_body()
    payload["capabilities"] = "evidence_exchange"
    status, body = _post(base, "/handshake", payload)
    assert status == 400
    assert "capabilities must be an object" in body["error"]
    health_status, _ = _get_health(base)
    assert health_status == 200


def test_protocol_version_as_integer_returns_400_and_node_survives(live_node):
    base, server = live_node
    payload = _valid_handshake_body()
    payload["protocol_version"] = 123
    status, body = _post(base, "/handshake", payload)
    assert status == 400
    assert "protocol_version" in body["error"]
    assert _get_health(base)[0] == 200


def test_protocol_version_none_returns_400(live_node):
    base, server = live_node
    payload = _valid_handshake_body()
    payload["protocol_version"] = None
    status, _ = _post(base, "/handshake", payload)
    assert status == 400
    assert _get_health(base)[0] == 200


def test_missing_protocol_version_returns_400(live_node):
    base, server = live_node
    payload = _valid_handshake_body()
    del payload["protocol_version"]
    status, _ = _post(base, "/handshake", payload)
    assert status == 400
    assert _get_health(base)[0] == 200


def test_missing_capabilities_returns_400(live_node):
    base, server = live_node
    payload = _valid_handshake_body()
    del payload["capabilities"]
    status, _ = _post(base, "/handshake", payload)
    assert status == 400
    assert _get_health(base)[0] == 200


def test_malformed_handshake_creates_no_session_and_mutates_nothing(live_node):
    base, server = live_node
    node = server.node
    identity_before = node.identity()
    policy_before = node.authorization_policy
    sessions_before = list(node.sessions) if hasattr(node.sessions, "__iter__") else None

    for mutate in (
        lambda p: p.update(capabilities="not-a-dict"),
        lambda p: p.update(protocol_version=123),
        lambda p: p.update(protocol_version=""),
        lambda p: p.pop("timestamp"),
        lambda p: p.update(node_id=42),
    ):
        payload = _valid_handshake_body()
        mutate(payload)
        status, _ = _post(base, "/handshake", payload)
        assert status == 400, f"expected 400 for malformed {payload}"

    # node still healthy
    assert _get_health(base)[0] == 200
    # no session was created by any malformed request
    sessions_after = list(node.sessions) if hasattr(node.sessions, "__iter__") else None
    assert sessions_after == sessions_before
    # identity unchanged
    assert node.identity() == identity_before
    # authorization policy object unchanged (same object, explicit policy)
    assert node.authorization_policy is policy_before


def test_evaluate_handshake_direct_malformed_capabilities_does_not_crash():
    request = HandshakeRequest(
        node_id="peer",
        protocol_version="1.0.0",
        capabilities="not-a-dict",
        timestamp="2026-09-02T00:00:00+00:00",
    )
    response = evaluate_handshake(request)
    assert response.accepted is False
    assert "capabilities" in response.reason.lower()


def test_evaluate_handshake_direct_malformed_version_does_not_crash():
    request = HandshakeRequest(
        node_id="peer",
        protocol_version=123,
        capabilities={"evidence_exchange": True},
        timestamp="2026-09-02T00:00:00+00:00",
    )
    response = evaluate_handshake(request)
    assert response.accepted is False
    assert "version" in response.reason.lower()


def test_parse_version_rejects_non_string_explicitly():
    from lantern.compatibility import parse_version

    import pytest as _pytest

    with _pytest.raises(ValueError):
        parse_version(123)
    with _pytest.raises(ValueError):
        parse_version(None)
    with _pytest.raises(ValueError):
        parse_version("")
    assert parse_version("v1.2.3") == (1, 2, 3)
