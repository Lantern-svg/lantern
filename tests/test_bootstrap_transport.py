"""Real process-boundary tests for the minimal external bootstrap adapter."""

import json
import threading
from dataclasses import asdict
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from lantern.bootstrap_node import create_server
from lantern.handshake import create_handshake
from lantern.protocol import create_codex_update, create_observation_share


def request(base, path, method="GET", payload=None):
    data = None if payload is None else json.dumps(payload).encode()
    req = Request(base + path, data=data, method=method, headers={"Content-Type": "application/json"})
    with urlopen(req, timeout=3) as response:
        return response.status, json.loads(response.read())


@pytest.fixture
def node(tmp_path):
    server = create_server("127.0.0.1", 0, "lantern-b", tmp_path / "b.jsonl")
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    yield base, server
    server.shutdown()
    server.server_close()
    thread.join(timeout=3)


def handshake_with(base):
    request_message = create_handshake()
    _, response = request(base, "/handshake", "POST", asdict(request_message))
    return request_message, response


def test_external_process_boundary_handshake_and_observation(node):
    base, server = node
    local_handshake, response = handshake_with(base)

    assert response["accepted"] is True
    assert response["protocol_version"] == "0.82"
    assert response["shared_capabilities"]["evidence_exchange"] is True
    assert "codex_update" not in response["shared_capabilities"]

    message = create_observation_share(
        local_handshake.node_id,
        {"content": "external claim", "source": "operator-a", "reliability": 0.99},
    )
    _, result = request(
        base,
        "/message",
        "POST",
        {"message": asdict(message), "peer_capabilities": local_handshake.capabilities},
    )

    assert result["accepted"] is True
    assert result["source"] == local_handshake.node_id
    assert result["protocol"] == "0.82"
    assert result["data"]["observation"]["source"] == local_handshake.node_id
    assert result["data"]["observation"]["content"] == "external claim"
    assert len(server.node.lantern.kernel.observations) == 1
    assert len(server.node.lantern.kernel.evidence) == 0
    assert server.node.lantern.bus.chronicle.verify() is True


def test_external_boundary_rejects_bad_version_and_capability(node):
    base, server = node
    local_handshake = create_handshake()
    message = create_observation_share("lantern-a", {"content": "blocked"})

    bad_version = asdict(message)
    bad_version["protocol"] = "9.0"
    _, result = request(
        base,
        "/message",
        "POST",
        {"message": bad_version, "peer_capabilities": {"evidence_exchange": True}},
    )
    assert result["accepted"] is False
    assert len(server.node.lantern.kernel.observations) == 0

    _, result = request(
        base,
        "/message",
        "POST",
        {"message": asdict(message), "peer_capabilities": {}},
    )
    assert result["accepted"] is False
    assert len(server.node.lantern.kernel.observations) == 0


def test_external_boundary_rejects_malformed_and_codex_update(node):
    base, server = node
    with pytest.raises(HTTPError) as error:
        request(base, "/message", "POST", {"message": {"bad": "shape"}, "peer_capabilities": {}})
    assert error.value.code == 400
    assert len(server.node.lantern.kernel.observations) == 0

    handshake = create_handshake()
    codex = create_codex_update("lantern-a", "gravity", 0.99, ["remote-evidence"])
    _, result = request(
        base,
        "/message",
        "POST",
        {"message": asdict(codex), "peer_capabilities": {"codex_update": True}},
    )
    assert result["accepted"] is False
    assert "codex_update" in result["reason"]
    assert len(server.node.lantern.kernel.evidence) == 0


def test_restart_reuses_chronicle_and_snapshot(tmp_path):
    path = tmp_path / "persisted.jsonl"
    first = create_server("127.0.0.1", 0, "lantern-b", path)
    handshake = create_handshake()
    message = create_observation_share("lantern-a", {"content": "persist me"})
    first.node.receive(asdict(message), handshake.capabilities)
    first.node.lantern.save_snapshot()
    first.server_close()

    second = create_server("127.0.0.1", 0, "lantern-b", path)
    assert len(second.node.lantern.kernel.observations) == 1
    assert second.node.lantern.bus.chronicle.verify() is True
    second.server_close()


def test_join_write_failure_is_reported_as_failure_not_success(node):
    """PRINCIPLE 2: if the durable write (Chronicle.append) fails, the
    HTTP layer must report a clear failure with persisted=False -- never
    a false "accepted" response. This forces the real append() call to
    raise OSError and checks the adapter does not swallow it.
    """
    import datetime as _dt

    base, server = node

    def _boom(self, event):
        raise OSError("simulated disk failure")

    original_append = type(server.node.rendezvous.chronicle).append
    type(server.node.rendezvous.chronicle).append = _boom
    try:
        payload = {
            "request_id": "req-fail-1",
            "node_id": "external-test-fail",
            "protocol_version": "0.82",
            "capabilities": {"evidence_exchange": True},
            "timestamp": _dt.datetime.now(_dt.timezone.utc).isoformat(),
        }
        with pytest.raises(HTTPError) as error:
            request(base, "/join", "POST", payload)
        assert error.value.code == 500
        body = json.loads(error.value.read())
        assert body["persisted"] is False
        assert "durable write failed" in body["error"].lower()
    finally:
        type(server.node.rendezvous.chronicle).append = original_append

    # The failed write must not have left a phantom pending request behind.
    assert "req-fail-1" not in server.node.rendezvous.requests
