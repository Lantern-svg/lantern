"""Proves lantern_harness.mcp_server works as a REAL stdio subprocess,
not just as a Python object under direct test. Launches
`python -m lantern_harness.mcp_server` as a real child process and
talks to it using Lantern core's own already-tested StdioMCPClient
(the same client class real MCP-compatible agent hosts would use),
mirroring the pattern in lantern-babel-codex-bridge's
tests/test_lantern_mcp_live_stdio.py (which proves the reverse
direction: Lantern core connecting OUT to a real MCP server)."""

import shutil
import sys
import tempfile
from pathlib import Path

import pytest

lantern_client = pytest.importorskip(
    "lantern.mcp_client", reason="requires Lantern core's mcp_client module (same repo family, adjacent checkout)"
)

from lantern.mcp_client import MCP_SDK_AVAILABLE, StdioMCPClient, StdioServerTarget  # noqa: E402

pytestmark = pytest.mark.skipif(
    not MCP_SDK_AVAILABLE, reason="requires the optional `mcp` extra (pip install lantern-harness[mcp])"
)

_HARNESS_ROOT = Path(__file__).resolve().parent.parent


def _fresh_target(name: str) -> StdioServerTarget:
    data_dir = Path(tempfile.mkdtemp()) / name
    return StdioServerTarget(
        server_id="lantern-harness-mcp-live",
        command=sys.executable,
        args=("-m", "lantern_harness.mcp_server"),
        cwd=str(_HARNESS_ROOT),
        env={"LANTERN_MCP_DATA_DIR": str(data_dir)},
    )


def test_real_stdio_subprocess_lists_all_nine_tools():
    target = _fresh_target("discover")
    client = StdioMCPClient(target)
    discovery = client.discover()
    tool_names = {tool.name for tool in discovery.tools}
    expected = {
        "lantern_observe", "lantern_add_evidence", "lantern_confidence", "lantern_decide",
        "lantern_compile", "lantern_self_model", "lantern_branch_open", "lantern_spine_read",
        "lantern_witness_integrity",
    }
    assert expected.issubset(tool_names)


def test_real_stdio_subprocess_records_a_real_observation():
    from lantern.mcp_integration import MCPExecutionRequest

    target = _fresh_target("observe")
    client = StdioMCPClient(target)

    result = client.execute(
        MCPExecutionRequest(
            capability_name="lantern_observe",
            server_id=target.server_id,
            tool_name="lantern_observe",
            arguments={"content": "real subprocess round-trip", "source": "live-stdio-test"},
            purpose="prove the MCP server works as a real subprocess, not just a Python object",
        )
    )
    assert "observation_id" in result.get("structured_content", {}) or "observation_id" in result.get("text", "")


def test_real_stdio_subprocess_never_authorizes_a_decision():
    from lantern.mcp_integration import MCPExecutionRequest

    target = _fresh_target("decide")
    client = StdioMCPClient(target)
    result = client.execute(
        MCPExecutionRequest(
            capability_name="lantern_decide",
            server_id=target.server_id,
            tool_name="lantern_decide",
            arguments={"concept": "unobserved_concept"},
            purpose="confirm authorization_status is NOT_EVALUATED even via the real wire protocol",
        )
    )
    payload = result.get("structured_content") or {}
    if not payload and result.get("text"):
        import json
        payload = json.loads(result["text"])
    assert payload.get("authorization_status") == "NOT_EVALUATED"
