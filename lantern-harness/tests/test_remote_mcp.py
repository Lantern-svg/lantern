"""Remote MCP transport tests (Streamable HTTP).

All network is mocked: a fake board client, no outbound calls, no public
writes. TestClient is used as a context manager because the Streamable HTTP
session manager starts with the ASGI lifespan.
"""

from __future__ import annotations

import json
from contextlib import contextmanager
from types import SimpleNamespace

import pytest

pytest.importorskip("mcp", reason="requires the optional mcp SDK (pip install .[mcp])")

from starlette.testclient import TestClient

from lantern_harness.contact import ContactService
from lantern_harness.remote_mcp import (
    RemoteMCPConfig,
    RemoteMCPConfigError,
    build_remote_app,
)

TOKEN = "test-remote-token-0123456789abcdef"
ACCEPT = "application/json, text/event-stream"

INIT = {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {
        "protocolVersion": "2025-06-18",
        "capabilities": {},
        "clientInfo": {"name": "pytest", "version": "1.0"},
    },
}


class FakeBoard:
    endpoint = "https://example.invalid/board"
    board = "lantern-board"

    def read_board(self, limit=10, cursor=None):
        return {"status": "OBSERVED", "count": min(limit, 1),
                "entries": [{"entry_id": "a" * 64, "seq": 1}][:limit]}

    def verify_entry(self, entry_id=None):
        return {"status": "CORROBORATED", "checked": 1,
                "entries": [{"entry_id": "a" * 64, "status": "CORROBORATED",
                             "checks": {"signature": {"state": "CORROBORATED"}}}]}


def _app(monkeypatch, **overrides):
    monkeypatch.setenv("LANTERN_REMOTE_MCP_TOKEN", overrides.pop("token", TOKEN))
    cfg = RemoteMCPConfig(enabled=True, **overrides)
    ctx = SimpleNamespace(contact=ContactService(board_client=FakeBoard(), enabled=True))
    return build_remote_app(context=ctx, cfg=cfg)


def _headers(token=TOKEN):
    h = {"Accept": ACCEPT, "Content-Type": "application/json"}
    if token is not None:
        h["Authorization"] = f"Bearer {token}"
    return h


@contextmanager
def _session(monkeypatch, **overrides):
    app = _app(monkeypatch, **overrides)
    with TestClient(app) as client:
        h = _headers()
        r = client.post("/mcp", json=INIT, headers=h)
        assert r.status_code == 200, r.text[:300]
        client.post("/mcp", json={"jsonrpc": "2.0", "method": "notifications/initialized"},
                    headers=h)
        yield client, h


def _rpc(client, headers, method, params=None, rid=2):
    body = {"jsonrpc": "2.0", "id": rid, "method": method}
    if params is not None:
        body["params"] = params
    return client.post("/mcp", json=body, headers=headers)


# ------------------------------------------------------------------ config

def test_remote_is_disabled_by_default_and_never_builds():
    with pytest.raises(RemoteMCPConfigError):
        build_remote_app(cfg=RemoteMCPConfig())


def test_public_bind_is_refused_without_explicit_operator_decision():
    with pytest.raises(RemoteMCPConfigError):
        RemoteMCPConfig(enabled=True, host="0.0.0.0").validate()


def test_public_bind_requires_https_flag():
    with pytest.raises(RemoteMCPConfigError):
        RemoteMCPConfig(enabled=True, host="0.0.0.0", allow_network_bind=True).validate()


def test_missing_token_refuses_to_start(monkeypatch):
    monkeypatch.delenv("LANTERN_REMOTE_MCP_TOKEN", raising=False)
    with pytest.raises(RemoteMCPConfigError):
        build_remote_app(cfg=RemoteMCPConfig(enabled=True))


def test_weak_token_is_refused(monkeypatch):
    monkeypatch.setenv("LANTERN_REMOTE_MCP_TOKEN", "short")
    with pytest.raises(RemoteMCPConfigError):
        build_remote_app(cfg=RemoteMCPConfig(enabled=True))


# -------------------------------------------------------------------- auth

def test_unauthenticated_request_is_rejected(monkeypatch):
    app = _app(monkeypatch)
    with TestClient(app) as client:
        r = client.post("/mcp", json=INIT, headers=_headers(token=None))
        assert r.status_code == 401
        assert r.json()["error"] == "UNAUTHORIZED"


def test_invalid_token_is_rejected(monkeypatch):
    app = _app(monkeypatch)
    with TestClient(app) as client:
        r = client.post("/mcp", json=INIT, headers=_headers(token="wrong-" + "x" * 30))
        assert r.status_code == 401


def test_valid_token_initializes(monkeypatch):
    with _session(monkeypatch) as (client, h):
        r = _rpc(client, h, "tools/list")
        assert r.status_code == 200
        assert "result" in json.loads(r.text)


# ---------------------------------------------------------------- surface

def test_remote_exposes_exactly_the_six_contact_tools(monkeypatch):
    with _session(monkeypatch) as (client, h):
        payload = json.loads(_rpc(client, h, "tools/list").text)
        names = sorted(t["name"] for t in payload["result"]["tools"])
        assert names == sorted([
            "lantern_contact_agent_card", "lantern_contact_skill",
            "lantern_contact_board_read", "lantern_contact_board_verify",
            "lantern_contact_report", "lantern_contact_status",
        ])


def test_remote_exposes_no_write_capable_tool(monkeypatch):
    with _session(monkeypatch) as (client, h):
        payload = json.loads(_rpc(client, h, "tools/list").text)
        for tool in payload["result"]["tools"]:
            name = tool["name"].lower()
            assert not any(k in name for k in
                           ("post", "key", "config", "grant", "authorize", "deploy"))


def test_status_is_invocable(monkeypatch):
    with _session(monkeypatch) as (client, h):
        payload = json.loads(_rpc(
            client, h, "tools/call",
            {"name": "lantern_contact_status", "arguments": {}}).text)
        assert "result" in payload


def test_board_read_is_invocable_with_fake_board(monkeypatch):
    with _session(monkeypatch) as (client, h):
        payload = json.loads(_rpc(
            client, h, "tools/call",
            {"name": "lantern_contact_board_read", "arguments": {"limit": 2}}).text)
        assert "OBSERVED" in json.dumps(payload)


def test_unknown_tool_is_refused(monkeypatch):
    with _session(monkeypatch) as (client, h):
        payload = json.loads(_rpc(
            client, h, "tools/call", {"name": "board_post", "arguments": {}}).text)
        assert payload.get("error") or payload["result"].get("isError")


# ------------------------------------------------------------------ abuse

def test_oversized_request_is_rejected(monkeypatch):
    app = _app(monkeypatch, max_body_bytes=2048)
    body = b'{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"pad":"' + b"x" * 8192 + b'"}}'
    with TestClient(app) as client:
        r = client.post("/mcp", content=body, headers=_headers())
        assert r.status_code == 413


def test_malformed_json_does_not_crash(monkeypatch):
    app = _app(monkeypatch)
    with TestClient(app) as client:
        r = client.post("/mcp", content=b"{not json", headers=_headers())
        assert r.status_code in (200, 400, 422)
        assert '"result"' not in r.text


def test_rate_limit_trips(monkeypatch):
    app = _app(monkeypatch, rate_limit_per_minute=2)
    with TestClient(app) as client:
        codes = [client.post("/mcp", json=INIT, headers=_headers()).status_code
                 for _ in range(4)]
    assert 429 in codes


def test_transport_recovers_after_failed_request(monkeypatch):
    with _session(monkeypatch) as (client, h):
        assert client.post("/mcp", content=b"{}", headers=h).status_code in (200, 400, 422)
        r = _rpc(client, h, "tools/list")
        assert r.status_code == 200
        assert "result" in json.loads(r.text)
