"""Generalization proof: the same full cycle, on a SECOND real,
independent, read-only MCP capability (memory_read_pending, not
memory_read). Proves the pattern generalizes rather than being an
accident of one specific tool.

OBSERVE -> COMPASS -> COMPRESS -> CAPABILITY -> AUTHORIZE -> DELEGATE ->
MCP -> RETURN -> VERIFY -> COMPRESS -> SCAR

No new architecture. Reuses exactly the same components as
test_lantern_mcp_full_cycle.py: lantern.core.Lantern/EvidenceKernel,
lantern.compass.orient, lantern.orchestration.create_default_registry,
lantern.capability_authorization.CapabilityDecision,
lantern.mcp_integration.MCPIntegrationBoundary,
lantern.mcp_client.StdioMCPClient, lantern.compression.compress_cycle,
lantern.core.Lantern.persist_scar.

A second test in this file re-proves the refusal case against a
DIFFERENT protected capability (memory_boundary, via memory_confirm --
a tool that could mutate state if called) to show the boundary refuses
based on the CAPABILITY's structural floor, not on which specific tool
name happens to be requested.
"""

import tempfile
from dataclasses import replace

import pytest

from lantern.capability_authorization import CapabilityDecision
from lantern.compass import orient
from lantern.compression import CompressionViolation, compress_cycle
from lantern.core import Lantern
from lantern.mcp_client import StdioMCPClient, StdioServerTarget
from lantern.mcp_integration import MCPExecutionRequest, MCPIntegrationBoundary
from lantern.orchestration import create_default_registry


MCP_SERVER_TARGET = StdioServerTarget(
    server_id="self-improving-memory",
    command="/home/ubuntu/self-improving/.venv/bin/python",
    args=("/home/ubuntu/self-improving/mcp_server.py", "run-stdio"),
    cwd="/home/ubuntu/self-improving",
)


def test_full_cycle_generalizes_to_a_second_independent_read_only_mcp_tool():
    # ---- OBSERVE ----
    lantern = Lantern()
    kernel = lantern.kernel
    obs = kernel.observe(
        content="operator wants to know whether any pending memory items are unresolved",
        source="user_request",
        reliability=0.9,
    )
    kernel.add_evidence(
        concept="need_pending_status", observation_id=obs.id, weight=1.0, sign=1
    )
    assert kernel.belief("need_pending_status") > 0.5

    # ---- CAPABILITY ----
    registry = create_default_registry()
    descriptor = registry.get("web_research")
    assert descriptor is not None
    assert descriptor.exposes_via_mcp is True
    assert descriptor.externally_exposable is True

    # ---- COMPASS (before authorization): not allowed yet ----
    compass_before = orient(
        kernel=kernel,
        concepts_of_interest=("need_pending_status",),
        registry=registry,
        capability_decision=None,
    )
    row_before = next(a for a in compass_before.what_is_allowed if a.capability == "web_research")
    assert row_before.allowed is False

    # ---- AUTHORIZE: CapabilityDecision built directly (same seam as before) ----
    decision = CapabilityDecision(
        node_id="self-improving-memory",
        identity_status="CRYPTOGRAPHICALLY_VERIFIED",
        shared_capabilities=frozenset({"web_research"}),
        authorized_capabilities=frozenset({"web_research"}),
        denied_capabilities={},
        reason="operator-scoped local authorization for read-only pending-status query",
    )
    assert decision.is_authorized("web_research")

    compass_after = orient(
        kernel=kernel,
        concepts_of_interest=("need_pending_status",),
        registry=registry,
        capability_decision=decision,
    )
    row_after = next(a for a in compass_after.what_is_allowed if a.capability == "web_research")
    assert row_after.allowed is True

    # ---- DELEGATE: scoped to memory_read_pending specifically ----
    client = StdioMCPClient(MCP_SERVER_TARGET)
    boundary = MCPIntegrationBoundary(registry, adapter=client)
    delegation = boundary.scoped_delegation_for_mcp(
        objective="check for unresolved pending memory items as an external information source",
        capability_name="web_research",
        server_id=MCP_SERVER_TARGET.server_id,
        tool_name="memory_read_pending",
        allowed_arguments=("caller_id", "origin"),
    )
    assert delegation.capability == "web_research"
    assert delegation.status == "REQUESTED"

    # ---- MCP EXECUTE / RETURN: real subprocess round-trip, different tool ----
    result = boundary.execute(
        request=MCPExecutionRequest(
            capability_name="web_research",
            server_id=MCP_SERVER_TARGET.server_id,
            tool_name="memory_read_pending",
            arguments={
                "caller_id": "lantern-generalization-test",
                "origin": "lantern",
            },
            purpose="generalization proof: second independent read-only MCP tool",
        ),
        delegation=delegation,
        capability_decision=decision,
    )
    assert result.status == "RETURNED"
    assert result.provenance.source_class == "MCP_ENDPOINT"
    assert result.provenance.is_remote is True

    returned_delegation = delegation.transition(
        "RETURNED",
        result_summary="memory_read_pending returned a pending-items payload",
        result_provenance=result.provenance,
    )
    assert returned_delegation.status == "RETURNED"
    # RETURNED must never carry a verification_summary automatically.
    assert returned_delegation.verification_summary is None

    # ---- VERIFY: independent inspection, not trust in the server's status ----
    payload = result.raw_result["structured_content"]
    independently_verified = payload.get("ok") is True and "pending" in payload
    assert independently_verified

    verified_delegation = returned_delegation.transition(
        "VERIFIED",
        verification_summary=(
            "independently inspected structured_content: ok=True, "
            "pending field present, consistent with memory_read_pending's contract"
        ),
    )
    assert verified_delegation.status == "VERIFIED"
    assert verified_delegation.verification_summary is not None

    # ---- COMPRESS -> SCAR: existing mechanism, nothing new ----
    compressed = compress_cycle(
        compass_before=compass_before,
        delegation=verified_delegation,
        source="lantern_mcp_generalization_test",
        trigger="operator requested pending-item status via MCP",
        observation=(
            "MCP capability web_research executed via real stdio server "
            f"{MCP_SERVER_TARGET.server_id}, tool memory_read_pending"
        ),
        outcome="verified_read_only_success",
        severity="low",
        lesson="the OBSERVE..COMPRESS cycle generalizes across distinct read-only MCP tools, not just one",
    )
    assert compressed.scar_record.scar.provenance["delegation_status"] == "VERIFIED"
    assert compressed.scar_record.scar.provenance["result_provenance"]["source_class"] == "MCP_ENDPOINT"

    # ---- Persist through the EXISTING Chronicle/Scar path ----
    with tempfile.TemporaryDirectory() as tmpdir:
        chronicled_lantern = Lantern(chronicle_filename=f"{tmpdir}/chronicle.jsonl")
        persisted = chronicled_lantern.persist_scar(compressed.scar_record)
        assert persisted.verified is True

    kernel.add_evidence(
        concept="need_pending_status", observation_id=obs.id, weight=1.0, sign=-1
    )
    belief_after = kernel.belief("need_pending_status", at_step=obs.step)
    assert 0.0 <= belief_after <= 1.0


def test_second_capability_refusal_holds_for_a_different_protected_tool():
    """Refusal generalizes too: memory_confirm (a tool that could mutate
    pending state) is bound to memory_boundary, which is structurally
    forbidden from MCP/external exposure. This must be refused before
    any MCP call, using the SAME mechanism as the messaging refusal in
    test_lantern_mcp_full_cycle.py -- proving the boundary enforces
    capability-level structural floors regardless of which specific
    tool or which specific protected capability is involved.
    """
    registry = create_default_registry()
    descriptor = registry.get("memory_boundary")
    assert descriptor is not None
    assert descriptor.exposes_via_mcp is False
    assert descriptor.requires_protected_authority is True

    client = StdioMCPClient(MCP_SERVER_TARGET)
    boundary = MCPIntegrationBoundary(registry, adapter=client)

    compass_reading = orient(registry=registry, capability_decision=None)
    row = next(a for a in compass_reading.what_is_allowed if a.capability == "memory_boundary")
    assert row.allowed is False

    delegation = boundary.scoped_delegation_for_mcp(
        objective="attempt to resolve a pending memory item via MCP memory_confirm",
        capability_name="memory_boundary",
        server_id=MCP_SERVER_TARGET.server_id,
        tool_name="memory_confirm",
    )
    assert delegation.requires_human_confirmation is True

    denied_decision = CapabilityDecision(
        node_id=MCP_SERVER_TARGET.server_id,
        identity_status="CRYPTOGRAPHICALLY_VERIFIED",
        shared_capabilities=frozenset({"memory_boundary"}),
        authorized_capabilities=frozenset(),
        denied_capabilities={"memory_boundary": "policy_denied"},
        reason="memory_boundary touches memory_mutation (NEVER_EXTERNALLY_EXPOSE); never authorized via MCP",
    )

    with pytest.raises(PermissionError):
        boundary.execute(
            request=MCPExecutionRequest(
                capability_name="memory_boundary",
                server_id=MCP_SERVER_TARGET.server_id,
                tool_name="memory_confirm",
                arguments={"pending_id": "fake", "decision": "CONFIRM"},
            ),
            delegation=delegation,
            capability_decision=denied_decision,
        )


def test_compression_still_refuses_returned_to_verified_collapse_for_second_tool():
    """Same regression guard as the first cycle, re-proven for the
    memory_read_pending delegation shape, to confirm compress_cycle's
    invariant is capability/delegation-shape based, not tied to a
    specific prior test's fixtures.
    """
    registry = create_default_registry()
    client = StdioMCPClient(MCP_SERVER_TARGET)
    boundary = MCPIntegrationBoundary(registry, adapter=client)
    delegation = boundary.scoped_delegation_for_mcp(
        objective="check pending items",
        capability_name="memory_boundary",
        server_id=MCP_SERVER_TARGET.server_id,
        tool_name="memory_read_pending",
    )
    compass_reading = orient(registry=registry, capability_decision=None)

    returned_only = delegation.transition("RETURNED", result_summary="looked fine")
    contaminated = replace(returned_only, verification_summary="claimed verified without independent check")

    with pytest.raises(CompressionViolation):
        compress_cycle(
            compass_before=compass_reading,
            delegation=contaminated,
            source="lantern_mcp_generalization_test",
            trigger="regression guard",
            observation="attempted silent RETURNED->VERIFIED collapse for a second tool",
            outcome="should_be_rejected",
            severity="low",
        )
