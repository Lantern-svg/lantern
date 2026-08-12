from pathlib import Path

import pytest

from lantern.capability_authorization import CapabilityDecision
from lantern.mcp_client import MCP_SDK_AVAILABLE, StdioMCPClient, StdioServerTarget
from lantern.mcp_integration import MCPExecutionRequest, MCPIntegrationBoundary
from lantern.orchestration import create_default_registry

_LOCAL_MCP_SERVER = Path("/home/ubuntu/self-improving/mcp_server.py")

pytestmark = pytest.mark.skipif(
    not MCP_SDK_AVAILABLE or not _LOCAL_MCP_SERVER.exists(),
    reason=(
        "requires the optional `mcp` extra (pip install .[mcp]) and a local "
        "MCP test server that only exists on the maintainer's machine; this "
        "test proves Lantern's MCP boundary against a real subprocess, not "
        "a portable fixture"
    ),
)


def _authorized(capability_name: str) -> CapabilityDecision:
    return CapabilityDecision(
        node_id="self-improving-memory",
        identity_status="CRYPTOGRAPHICALLY_VERIFIED",
        shared_capabilities=frozenset({capability_name}),
        authorized_capabilities=frozenset({capability_name}),
        denied_capabilities={},
        reason="test fixture",
    )


def test_real_mcp_stdio_server_can_flow_through_existing_boundary():
    registry = create_default_registry()
    target = StdioServerTarget(
        server_id="self-improving-memory",
        command="/home/ubuntu/self-improving/.venv/bin/python",
        args=("/home/ubuntu/self-improving/mcp_server.py", "run-stdio"),
        cwd="/home/ubuntu/self-improving",
    )
    client = StdioMCPClient(target)

    discovery = client.discover()
    tool_names = {tool.name for tool in discovery.tools}
    assert "memory_read" in tool_names

    boundary = MCPIntegrationBoundary(registry, adapter=client)
    delegation = boundary.scoped_delegation_for_mcp(
        objective="read memory summary through a real MCP stdio server",
        capability_name="memory_boundary",
        server_id=target.server_id,
        tool_name="memory_read",
        allowed_arguments=("caller_id", "origin", "read_target"),
    )

    result = boundary.execute(
        request=MCPExecutionRequest(
            capability_name="memory_boundary",
            server_id=target.server_id,
            tool_name="memory_read",
            arguments={
                "caller_id": "lantern-live-mcp-test",
                "origin": "lantern",
                "read_target": "summary",
            },
            purpose="real read-only MCP verification round-trip",
        ),
        delegation=delegation,
        capability_decision=_authorized("memory_boundary"),
    )

    assert result.status == "RETURNED"
    assert result.provenance is not None
    assert result.provenance.source_class == "MCP_ENDPOINT"
    assert result.provenance.is_remote is True
    assert result.verification_required is True
    assert result.verification_policy is not None
    assert result.verification_policy["worker_claim_sufficient"] is False
    assert result.raw_result is not None
    assert result.raw_result["structured_content"]["ok"] is True
