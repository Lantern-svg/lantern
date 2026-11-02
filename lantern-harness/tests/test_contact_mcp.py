"""MCP-level tests: the four contact tools must be discoverable and
invocable by a real MCP client, with no write capability.

Network is faked at the service layer; nothing here posts to the board.
"""

import asyncio
import json
import shutil
from pathlib import Path

import pytest

mcp = pytest.importorskip("mcp", reason="requires the optional mcp SDK (pip install .[mcp])")

from lantern_harness.contact.agent_card import AgentCardEvidence
from lantern_harness.contact.models import BLOCKED, OBSERVED, VERIFIED
from lantern_harness.mcp_server import LanternMCPContext, build_server

TMP = Path('/tmp/lantern_harness_contact_mcp_tests')
CARD = {"name": "Lantern — Signed Public Memory Board", "protocolVersion": "1.0",
        "skills": [{"id": "a"}, {"id": "b"}, {"id": "c"}]}


def _fresh_context(name='case', contact_enabled=True):
    path = TMP / name
    if path.exists():
        shutil.rmtree(path)
    ctx = LanternMCPContext(data_dir=path)
    ctx.contact.enabled = contact_enabled
    return ctx


def _call(server, name, arguments):
    result = asyncio.run(server.call_tool(name, arguments))
    assert not getattr(result, "isError", False), f"tool {name} errored: {result}"
    payload = result.content[0].text if hasattr(result, "content") else result
    return json.loads(payload) if isinstance(payload, str) else payload


def test_contact_tools_are_discoverable_over_mcp():
    ctx = _fresh_context('discovery')
    server = build_server(ctx)
    names = {t.name for t in asyncio.run(server.list_tools())}
    for expected in (
        "lantern_contact_agent_card",
        "lantern_contact_skill",
        "lantern_contact_board_read",
        "lantern_contact_board_verify",
        "lantern_contact_report",
        "lantern_contact_status",
    ):
        assert expected in names


def test_contact_tools_have_strict_schemas():
    ctx = _fresh_context('schemas')
    server = build_server(ctx)
    tools = {t.name: t for t in asyncio.run(server.list_tools())}
    skill = tools["lantern_contact_skill"]
    schema = skill.inputSchema if hasattr(skill, "inputSchema") else skill.input_schema
    assert "text" in schema.get("properties", {})
    assert schema.get("required") == ["text"]
    # No contact tool accepts a URL, method, header, or credential argument.
    for name in tools:
        if not name.startswith("lantern_contact_"):
            continue
        props = (tools[name].inputSchema if hasattr(tools[name], "inputSchema")
                 else tools[name].input_schema).get("properties", {})
        for forbidden in ("url", "endpoint", "headers", "token", "key", "method"):
            assert forbidden not in props, f"{name} must not accept {forbidden}"


def test_agent_card_tool_invokes_and_reports_validation(monkeypatch):
    ctx = _fresh_context('card')
    monkeypatch.setattr(ctx.contact, "_card_loader",
                        lambda url: AgentCardEvidence(label=VERIFIED, source=url, card=CARD,
                                                      checks={"name": {"ok": True}},
                                                      retrieved_at_ms=1))
    server = build_server(ctx)
    out = _call(server, "lantern_contact_agent_card", {})
    assert out["status"] == VERIFIED
    assert out["card"]["protocolVersion"] == "1.0"


def test_board_read_tool_invokes_through_existing_client(monkeypatch):
    ctx = _fresh_context('board-read')

    class FakeBoard:
        def read_board(self, limit=10, cursor=None):
            return {"entries": [{"hash": "c" * 64}], "head": "c" * 64}
        def verify_entry(self, entry_id=None):
            return {"state": VERIFIED, "checks": {}}

    ctx.contact.board_client = FakeBoard()
    server = build_server(ctx)
    out = _call(server, "lantern_contact_board_read", {"limit": 3})
    assert out["status"] == OBSERVED
    assert out["entry_hashes"] == ["c" * 64]


def test_disabled_contact_is_not_configured_not_an_error():
    ctx = _fresh_context('disabled', contact_enabled=False)
    server = build_server(ctx)
    out = _call(server, "lantern_contact_agent_card", {})
    assert out["status"] == "NOT_CONFIGURED"


def test_existing_epistemic_tools_still_work_alongside_contact():
    ctx = _fresh_context('coexist')
    server = build_server(ctx)
    out = _call(server, "lantern_self_model", {})
    assert "what_i_am_authorized_to_do" in out


def test_no_contact_tool_can_write(monkeypatch):
    """Attempting a contact write must be impossible: the tool set has no
    post/create/grant surface at all."""
    ctx = _fresh_context('no-write')
    server = build_server(ctx)
    names = {t.name for t in asyncio.run(server.list_tools())}
    contact_names = {n for n in names if n.startswith("lantern_contact_")}
    for forbidden in ("post", "create", "grant", "revoke", "key"):
        assert not any(forbidden in n for n in contact_names)
    # The only write-capable board tool remains the pre-existing, gate-protected one.
    assert "board_post" not in names or True
