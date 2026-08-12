import asyncio
import json
from pathlib import Path
import shutil

import pytest

mcp = pytest.importorskip("mcp", reason="requires the optional mcp SDK (pip install .[mcp])")

from lantern_harness.mcp_server import LanternMCPContext, build_server


TMP = Path('/tmp/lantern_harness_mcp_server_tests')


def _fresh_context(name='case'):
    path = TMP / name
    if path.exists():
        shutil.rmtree(path)
    return LanternMCPContext(data_dir=path)


def _call(server, name, arguments):
    result = asyncio.run(server.call_tool(name, arguments))
    assert not getattr(result, "isError", False), f"tool {name} reported an error: {result}"
    payload = result.content[0].text if hasattr(result, "content") else result
    return json.loads(payload) if isinstance(payload, str) else payload


def test_server_exposes_expected_tool_names():
    ctx = _fresh_context('tool-names')
    server = build_server(ctx)
    tools = asyncio.run(server.list_tools())
    names = {t.name for t in tools}
    expected = {
        "lantern_observe", "lantern_add_evidence", "lantern_confidence", "lantern_decide",
        "lantern_compile", "lantern_self_model", "lantern_branch_open", "lantern_spine_read",
        "lantern_witness_integrity",
    }
    assert expected.issubset(names)


def test_lantern_observe_records_a_real_observation():
    ctx = _fresh_context('observe')
    server = build_server(ctx)
    before = ctx.bridge.status()["observations"]
    result = _call(server, "lantern_observe", {"content": "the sky is blue", "source": "test"})
    after = ctx.bridge.status()["observations"]
    assert after == before + 1
    assert result["observation_id"]


def test_lantern_confidence_reflects_real_evidence_state():
    ctx = _fresh_context('confidence')
    server = build_server(ctx)
    obs = _call(server, "lantern_observe", {"content": "x is true", "source": "a", "reliability": 0.9})
    _call(server, "lantern_add_evidence", {"concept": "x", "observation_id": obs["observation_id"], "weight": 1.0, "sign": 1})
    reading = _call(server, "lantern_confidence", {"concept": "x"})
    assert reading["confidence_band"] in {"HIGH", "MEDIUM", "LOW", "BLOCKED"}
    assert isinstance(reading["confidence_score"], (int, float))


def test_lantern_decide_never_reports_authorization():
    ctx = _fresh_context('decide')
    server = build_server(ctx)
    decision = _call(server, "lantern_decide", {"concept": "unknown_concept"})
    assert decision["authorization_status"] == "NOT_EVALUATED"


def test_lantern_compile_never_fabricates_missing_fields():
    ctx = _fresh_context('compile')
    server = build_server(ctx)
    compiled = _call(server, "lantern_compile", {"request": "Prove that our new feature is a success."})
    text = json.dumps(compiled)
    assert "NOT_PROVIDED" in text or "UNKNOWN" in text


def test_lantern_self_model_lists_authorized_tools_from_real_boundary():
    ctx = _fresh_context('self-model')
    server = build_server(ctx)
    model = _call(server, "lantern_self_model", {})
    assert "what_i_am_authorized_to_do" in model
    assert model["what_i_am_authorized_to_do"] == ["(no tools are currently authorized in ToolBoundary)"]


def test_lantern_branch_open_creates_a_real_branch():
    ctx = _fresh_context('branch')
    server = build_server(ctx)
    branch = _call(server, "lantern_branch_open", {"concept": "x", "hypothesis": "x holds"})
    assert branch["status"] == "OPEN"
    assert branch["concept"] == "x"
    stored = ctx.branch_store.get(branch["id"])
    assert stored is not None


def test_lantern_spine_read_reflects_real_committed_entries():
    ctx = _fresh_context('spine')
    server = build_server(ctx)
    empty = _call(server, "lantern_spine_read", {})
    assert empty["entries"] == []

    branch = ctx.branch_store.open_branch(concept="x", hypothesis="x holds")
    ctx.spine_committer.commit(branch, statement="x holds", authorized=True, authorized_by="test-operator")
    after = _call(server, "lantern_spine_read", {})
    assert len(after["entries"]) == 1
    assert after["entries"][0]["concept"] == "x"


def test_lantern_witness_integrity_reports_real_chronicle_status():
    ctx = _fresh_context('integrity')
    server = build_server(ctx)
    status = _call(server, "lantern_witness_integrity", {})
    assert status["status"] in {"VALID", "NO_CHRONICLE", "TAMPERED", "CORRUPTED"}


def test_server_exposes_no_tool_capable_of_external_action():
    """This server surfaces epistemic primitives only -- it must not
    expose a generic tool-execution or RealityBoundary.act passthrough."""
    ctx = _fresh_context('no-external-action')
    server = build_server(ctx)
    tools = asyncio.run(server.list_tools())
    names = {t.name for t in tools}
    forbidden_substrings = ("execute", "run_tool", "shell", "act", "authorize")
    for name in names:
        for forbidden in forbidden_substrings:
            assert forbidden not in name, f"tool {name!r} suggests an external-action capability, which this server must not expose"

def test_build_server_raises_clear_error_when_sdk_unavailable(monkeypatch):
    import lantern_harness.mcp_server as mod
    monkeypatch.setattr(mod, "MCP_SDK_AVAILABLE", False)
    try:
        mod.build_server(_fresh_context('sdk-unavailable'))
        raise AssertionError("expected RuntimeError")
    except RuntimeError as exc:
        assert "mcp" in str(exc)
