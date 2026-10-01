"""Regression tests for the v2 relay tunnel (relay-boundary repair).

These tests FAIL against the old implementation: importing the old
relay_tunneld started a network polling loop at import time; the old
module had no main(), no route_allowed, no credential handling.
"""
import importlib.util
import subprocess
import sys
import os

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TUNNELD = os.path.join(REPO, "relay-transport", "relay_tunneld.py")


def _load():
    spec = importlib.util.spec_from_file_location("relay_tunneld_v2_under_test", TUNNELD)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_import_performs_no_network(monkeypatch):
    def boom(*a, **k):
        raise AssertionError("network activity at import time")
    monkeypatch.setattr("urllib.request.urlopen", boom)
    monkeypatch.setattr("urllib.request.Request", boom)
    mod = _load()  # must not raise
    assert hasattr(mod, "main"), "explicit entry point required"
    assert hasattr(mod, "route_allowed")


def test_repeated_import_safe(monkeypatch):
    def boom(*a, **k):
        raise AssertionError("network activity at import time")
    monkeypatch.setattr("urllib.request.urlopen", boom)
    _load()
    _load()  # second import also must not activate anything


def test_route_allowlist():
    mod = _load()
    assert mod.route_allowed("POST", "/message")[0] is True
    assert mod.route_allowed("GET", "/health")[0] is True
    assert mod.route_allowed("post", "/message")[0] is True  # method normalized
    assert mod.route_allowed("POST", "/join")[0] is False
    assert mod.route_allowed("GET", "/observations/xyz")[0] is False
    assert mod.route_allowed("POST", "/message?x=1")[0] is False
    assert mod.route_allowed("POST", "/message%3Fx")[0] is False
    assert mod.route_allowed("POST", "/../message")[0] is False
    assert mod.route_allowed("PUT", "/message")[0] is False
    assert mod.route_allowed("GET", "/HEALTH")[0] is False  # exact match, case-sensitive
    assert mod.route_allowed("POST", "/message ")[0] is False  # no whitespace tricks


def test_handle_request_forwards_advertised(monkeypatch):
    mod = _load()
    calls, sent = [], []

    def fake_call_node(method, path, body, node_url=mod.NODE):
        calls.append((method, path))
        return 200, {"ok": True, "status": "ok"}

    def fake_relay(payload, relay_url=mod.RELAY):
        sent.append(payload)
        return {"ok": True}

    monkeypatch.setattr(mod, "call_node", fake_call_node)
    monkeypatch.setattr(mod, "relay", fake_relay)
    ok = mod.handle_request({"id": "s1", "method": "POST", "path": "/message", "body": {}}, "cred")
    assert ok is True
    assert calls == [("POST", "/message")]
    assert sent[-1]["action"] == "respond" and sent[-1]["code"] == 200


def test_handle_request_rejects_unadvertised_before_node_contact(monkeypatch):
    mod = _load()
    calls, sent = [], []

    def fake_call_node(method, path, body, node_url=mod.NODE):
        calls.append((method, path))
        return 200, {}

    def fake_relay(payload, relay_url=mod.RELAY):
        sent.append(payload)
        return {"ok": True}

    monkeypatch.setattr(mod, "call_node", fake_call_node)
    monkeypatch.setattr(mod, "relay", fake_relay)
    for req in ({"id": "s2", "method": "GET", "path": "/observations/x", "body": {}},
                {"id": "s3", "method": "POST", "path": "/join", "body": {}},
                {"id": "s4", "method": "DELETE", "path": "/health", "body": {}},
                {"id": "s5", "method": "POST", "path": "/message?a=b", "body": {}}):
        assert mod.handle_request(req, "cred") is False
    assert calls == [], "no unadvertised route may reach the node"
    assert all(s["body"].get("error") == "RELAY_ROUTE_NOT_ADVERTISED" for s in sent)


def test_no_run_flag_refuses_to_start():
    r = subprocess.run([sys.executable, TUNNELD], capture_output=True, timeout=15)
    assert r.returncode == 2
    assert b"explicit operator opt-in" in r.stderr or b"--run" in r.stderr
    assert b"tunneld up" not in r.stdout, "must not activate without opt-in"


def test_run_without_credential_refuses_to_start():
    r = subprocess.run([sys.executable, TUNNELD, "--run"], capture_output=True, timeout=15)
    assert r.returncode == 2
    assert b"credential" in r.stderr
    assert b"tunneld up" not in r.stdout
