import tempfile

import pytest

from lantern.capability_authorization import CapabilityDecision
from lantern.compass import orient
from lantern.memory_boundary import MemoryBoundary, MemoryWriteStatus
from lantern.mcp_integration import (
    MCPExecutionRequest,
    MCPIntegrationBoundary,
    MCPResourceDescriptor,
    MCPServerDiscovery,
    MCPToolDescriptor,
    infer_bindings,
)
from lantern.orchestration import create_default_registry


class FakeAdapter:
    def execute(self, request):
        return {
            "ok": True,
            "tool": request.tool_name,
            "arguments": dict(request.arguments),
        }


def _authorized(capability_name: str) -> CapabilityDecision:
    return CapabilityDecision(
        node_id="mcp-server-1",
        identity_status="CRYPTOGRAPHICALLY_VERIFIED",
        shared_capabilities=frozenset({capability_name}),
        authorized_capabilities=frozenset({capability_name}),
        denied_capabilities={},
        reason="test fixture",
    )


def test_mcp_discovery_works_and_is_represented_explicitly():
    discovery = MCPServerDiscovery(
        server_id="server-1",
        endpoint="stdio://example",
        tools=(MCPToolDescriptor(name="web_search"), MCPToolDescriptor(name="web_fetch")),
        resources=(MCPResourceDescriptor(uri="memo://sources"),),
    )
    assert discovery.tool_names() == frozenset({"web_search", "web_fetch"})
    assert discovery.resource_uris() == frozenset({"memo://sources"})


def test_discovered_mcp_capabilities_enter_existing_registry_correctly():
    registry = create_default_registry()
    discovery = MCPServerDiscovery(
        server_id="server-1",
        endpoint="stdio://example",
        tools=(MCPToolDescriptor(name="web_search"), MCPToolDescriptor(name="web_fetch")),
    )

    snapshot = infer_bindings(registry, [discovery])
    boundary = MCPIntegrationBoundary(registry)
    integrated = boundary.integrate_discovery(snapshot)

    assert integrated["count"] == 1
    entry = integrated["capabilities"][0]
    assert entry["capability"]["name"] == "web_research"
    assert entry["mcp_binding"]["tool_names"] == ["web_fetch", "web_search"]
    assert entry["authorized"] is False
    assert entry["executed"] is False
    assert entry["verified"] is False


def test_discovery_does_not_grant_authorization():
    registry = create_default_registry()
    discovery = MCPServerDiscovery(
        server_id="server-1",
        endpoint="stdio://example",
        tools=(MCPToolDescriptor(name="web_search"),),
    )
    snapshot = infer_bindings(registry, [discovery])
    boundary = MCPIntegrationBoundary(registry)

    summary = boundary.summarize_for_compass(snapshot)
    item = next(x for x in summary if x.capability == "web_research")
    assert item.allowed is False
    assert "authorization still required" in item.reason


def test_scoped_delegation_works_through_mcp():
    registry = create_default_registry()
    boundary = MCPIntegrationBoundary(registry, adapter=FakeAdapter())
    delegation = boundary.scoped_delegation_for_mcp(
        objective="gather sources on topic x",
        capability_name="web_research",
        server_id="server-1",
        tool_name="web_search",
        allowed_arguments=("query",),
    )
    result = boundary.execute(
        request=MCPExecutionRequest(
            capability_name="web_research",
            server_id="server-1",
            tool_name="web_search",
            arguments={"query": "topic x"},
            purpose="triangulate external claims",
        ),
        delegation=delegation,
        capability_decision=_authorized("web_research"),
    )

    assert delegation.allowed_capabilities == frozenset({"web_research"})
    assert delegation.worker == "MCP::server-1"
    assert result.status == "RETURNED"
    assert result.verification_required is True


def test_mcp_provenance_is_preserved():
    registry = create_default_registry()
    boundary = MCPIntegrationBoundary(registry, adapter=FakeAdapter())
    delegation = boundary.scoped_delegation_for_mcp(
        objective="search", capability_name="web_research", server_id="server-1", tool_name="web_search"
    )
    result = boundary.execute(
        request=MCPExecutionRequest(
            capability_name="web_research",
            server_id="server-1",
            tool_name="web_search",
            purpose="search for independent corroboration",
        ),
        delegation=delegation,
        capability_decision=_authorized("web_research"),
    )

    assert result.provenance is not None
    assert result.provenance.source_class == "MCP_ENDPOINT"
    assert result.provenance.identifier == "server-1:web_search"


def test_mcp_results_require_verification():
    registry = create_default_registry()
    boundary = MCPIntegrationBoundary(registry, adapter=FakeAdapter())
    delegation = boundary.scoped_delegation_for_mcp(
        objective="search", capability_name="web_research", server_id="server-1", tool_name="web_search"
    )
    result = boundary.execute(
        request=MCPExecutionRequest(
            capability_name="web_research",
            server_id="server-1",
            tool_name="web_search",
        ),
        delegation=delegation,
        capability_decision=_authorized("web_research"),
    )

    assert result.verification_required is True
    assert result.verification_policy is not None
    assert result.verification_policy["worker_claim_sufficient"] is False


def test_compass_can_compress_mcp_capability_information():
    registry = create_default_registry()
    discovery = MCPServerDiscovery(
        server_id="server-1",
        endpoint="stdio://example",
        tools=(MCPToolDescriptor(name="web_search"), MCPToolDescriptor(name="browser")),
    )
    snapshot = infer_bindings(registry, [discovery])
    boundary = MCPIntegrationBoundary(registry)

    summary = boundary.summarize_for_compass(snapshot)
    reading = orient(registry=registry)

    assert any(item.capability == "web_research" for item in summary)
    # Compass stays capability-level; raw MCP tool names are not carried
    # through the reading itself.
    assert all("web_search" not in str(item.to_dict()) for item in reading.what_is_allowed)


def test_protected_authorities_remain_inaccessible_even_if_mcp_discovers_tools():
    registry = create_default_registry()
    boundary = MCPIntegrationBoundary(registry, adapter=FakeAdapter())
    delegation = boundary.scoped_delegation_for_mcp(
        objective="send a message",
        capability_name="messaging",
        server_id="server-1",
        tool_name="message",
    )

    unauthorized = CapabilityDecision(
        node_id="mcp-server-1",
        identity_status="CRYPTOGRAPHICALLY_VERIFIED",
        shared_capabilities=frozenset({"messaging"}),
        authorized_capabilities=frozenset(),
        denied_capabilities={"messaging": "policy_denied"},
        reason="test fixture",
    )

    with pytest.raises(PermissionError):
        boundary.execute(
            request=MCPExecutionRequest(
                capability_name="messaging",
                server_id="server-1",
                tool_name="message",
            ),
            delegation=delegation,
            capability_decision=unauthorized,
        )


def test_unavailable_mcp_client_is_reported_honestly_not_faked():
    registry = create_default_registry()
    boundary = MCPIntegrationBoundary(registry)
    delegation = boundary.scoped_delegation_for_mcp(
        objective="search", capability_name="web_research", server_id="server-1", tool_name="web_search"
    )
    result = boundary.execute(
        request=MCPExecutionRequest(
            capability_name="web_research",
            server_id="server-1",
            tool_name="web_search",
        ),
        delegation=delegation,
        capability_decision=_authorized("web_research"),
    )
    assert result.status == "UNAVAILABLE"
    assert "no MCP client adapter" in result.raw_error


def test_memory_boundary_is_used_not_bypassed_for_mcp_memory_mutation():
    registry = create_default_registry()
    boundary = MCPIntegrationBoundary(registry)
    with tempfile.TemporaryDirectory() as tmpdir:
        memory = MemoryBoundary(tmpdir)
        path = f"{tmpdir}/memory.txt"
        first = boundary.memory_write(memory, path=path, content="hello", authorize=False)
        second = boundary.memory_write(memory, path=path, content="overwrite", authorize=False)
        third = boundary.memory_write(memory, path=path, content="overwrite", authorize=True)

        assert first.status == MemoryWriteStatus.WRITTEN
        assert second.status == MemoryWriteStatus.BLOCKED
        assert third.status == MemoryWriteStatus.WRITTEN
