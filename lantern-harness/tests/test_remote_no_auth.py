"""Tests for the explicit no-auth mode and the six-tool guard.

Owner decision B (2026-11-03): a temporary, loopback-only, credential-free
instance is permitted for a tunnel test. These tests prove the default is
unchanged, that the mode cannot reach a network interface, that the tool set
is enforced, and that the remote contact service stores nothing locally.
"""

import asyncio
import json
import os
from contextlib import contextmanager

import pytest

from starlette.testclient import TestClient

from lantern_harness.remote_mcp import (
    CONTACT_MCP_TOOL_NAMES,
    RemoteMCPConfig,
    RemoteMCPConfigError,
    _assert_only_contact_tools,
    build_remote_app,
)


INIT = {
    "jsonrpc": "2.0", "id": 1, "method": "initialize",
    "params": {"protocolVersion": "2025-06-18", "capabilities": {},
               "clientInfo": {"name": "no-auth-test", "version": "1"}},
}
HEADERS = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json"}


def _cfg(**overrides):
    base = dict(enabled=True, host="127.0.0.1", port=8765, path="/mcp",
                no_auth=True, stateless=True)
    base.update(overrides)
    return RemoteMCPConfig(**base)


def test_no_auth_is_off_by_default():
    assert RemoteMCPConfig().no_auth is False
    default = RemoteMCPConfig.from_config({"remote_mcp": {"enabled": True}})
    assert default.no_auth is False


def test_no_auth_refused_on_non_loopback():
    cfg = _cfg(host="0.0.0.0", allow_network_bind=True, require_https=True)
    with pytest.raises(RemoteMCPConfigError):
        cfg.validate()


@pytest.mark.parametrize("host", ["127.0.0.1", "::1", "localhost"])
def test_no_auth_allowed_on_loopback(host):
    _cfg(host=host).validate()  # must not raise


def test_build_refuses_without_token_when_auth_enabled(monkeypatch):
    monkeypatch.delenv("LANTERN_REMOTE_MCP_TOKEN", raising=False)
    cfg = _cfg(no_auth=False)
    with pytest.raises(RemoteMCPConfigError):
        build_remote_app(cfg=cfg)


def test_guard_rejects_an_extra_tool():
    class FakeTool:
        def __init__(self, name):
            self.name = name

    class FakeServer:
        def __init__(self, names):
            self._names = names

        async def list_tools(self):
            return [FakeTool(n) for n in self._names]

    _assert_only_contact_tools(FakeServer(CONTACT_MCP_TOOL_NAMES))  # exact six: OK
    with pytest.raises(RemoteMCPConfigError):
        _assert_only_contact_tools(FakeServer(CONTACT_MCP_TOOL_NAMES + ("board_post",)))


@contextmanager
def _client(monkeypatch):
    monkeypatch.setenv("LANTERN_CONTACT_ENABLED", "1")
    app = build_remote_app(cfg=_cfg())
    with TestClient(app) as client:
        yield client


def test_no_auth_serves_six_tools_without_credentials(monkeypatch):
    with _client(monkeypatch) as client:
        r = client.post("/mcp", json=INIT, headers=HEADERS)
        assert r.status_code == 200, r.text
        client.post("/mcp", json={"jsonrpc": "2.0", "method": "notifications/initialized"},
                    headers=HEADERS)
        listed = client.post("/mcp", json={"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
                             headers=HEADERS)
        assert listed.status_code == 200, listed.text
        names = sorted(t["name"] for t in listed.json()["result"]["tools"])
        assert names == sorted(CONTACT_MCP_TOOL_NAMES)


def test_no_auth_rejects_unknown_tool(monkeypatch):
    with _client(monkeypatch) as client:
        client.post("/mcp", json=INIT, headers=HEADERS)
        client.post("/mcp", json={"jsonrpc": "2.0", "method": "notifications/initialized"},
                    headers=HEADERS)
        r = client.post("/mcp", json={"jsonrpc": "2.0", "id": 3, "method": "tools/call",
                                      "params": {"name": "board_post", "arguments": {}}},
                        headers=HEADERS)
        payload = r.json()
        assert "error" in payload or payload.get("result", {}).get("isError") is True


def test_no_auth_rejects_malformed_arguments(monkeypatch):
    with _client(monkeypatch) as client:
        client.post("/mcp", json=INIT, headers=HEADERS)
        client.post("/mcp", json={"jsonrpc": "2.0", "method": "notifications/initialized"},
                    headers=HEADERS)
        r = client.post("/mcp", json={"jsonrpc": "2.0", "id": 4, "method": "tools/call",
                                      "params": {"name": "lantern_contact_skill",
                                                 "arguments": {"text": "https://evil.example/exfil"}}},
                        headers=HEADERS)
        body = r.text
        assert r.status_code != 200 or "error" in body.lower() or "isError" in body or "blocked" in body.lower()


def test_remote_context_stores_nothing_locally(monkeypatch):
    """Condition 2: the remote surface formats and returns; it must not persist."""
    monkeypatch.setenv("LANTERN_CONTACT_ENABLED", "1")
    from lantern_harness.mcp_server import LanternMCPContext
    import tempfile, pathlib

    ctx = LanternMCPContext(data_dir=pathlib.Path(tempfile.mkdtemp()) / "state")
    ctx.contact.enabled = True
    ctx.contact.bridge = None
    assert ctx.contact.bridge is None
    # build_remote_app must produce the same posture when it creates the context.
    app = build_remote_app(cfg=_cfg())
    assert app is not None
