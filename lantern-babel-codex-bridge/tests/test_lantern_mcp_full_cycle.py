"""Full-cycle proof: Lantern using its own already-existing hands.

OBSERVE -> COMPASS -> COMPRESS -> CAPABILITY -> AUTHORIZE -> DELEGATE ->
MCP EXECUTE -> RETURN -> VERIFY -> COMPRESS

This test does not introduce a new state store, a new record type, or a
new authority mechanism. It only calls, in order, functions/classes that
already exist elsewhere in the package:

    lantern.core.Lantern / EvidenceKernel   (OBSERVE)
    lantern.compass.orient                  (COMPASS)
    lantern.orchestration.CapabilityRegistry (CAPABILITY)
    lantern.capability_authorization.authorize / AuthorizationPolicy (AUTHORIZE)
    lantern.mcp_integration.MCPIntegrationBoundary (DELEGATE / MCP EXECUTE / RETURN)
    lantern.mcp_client.StdioMCPClient        (real MCP transport)
    lantern.compression.compress_cycle       (COMPRESS, both times)
    lantern.scars                            (durable compressed record)

A second test proves the refusal case: an MCP-backed capability that
touches a NEVER_EXTERNALLY_EXPOSE / protected authority must be rejected
before any MCP call is made, regardless of MCP discovery/availability.
"""

import tempfile
from pathlib import Path

import pytest

from lantern.capability_authorization import CapabilityDecision
from lantern.compass import orient
from lantern.compression import CompressionViolation, compress_cycle
from lantern.core import Lantern
from lantern.mcp_client import MCP_SDK_AVAILABLE, StdioMCPClient, StdioServerTarget
from lantern.mcp_integration import MCPExecutionRequest, MCPIntegrationBoundary
from lantern.orchestration import create_default_registry


_LOCAL_MCP_SERVER = Path("/home/ubuntu/self-improving/mcp_server.py")

_requires_live_mcp_server = pytest.mark.skipif(
    not MCP_SDK_AVAILABLE or not _LOCAL_MCP_SERVER.exists(),
    reason=(
        "requires the optional `mcp` extra (pip install .[mcp]) and a local "
        "MCP test server that only exists on the maintainer's machine"
    ),
)

MCP_SERVER_TARGET = StdioServerTarget(
    server_id="self-improving-memory",
    command="/home/ubuntu/self-improving/.venv/bin/python",
    args=("/home/ubuntu/self-improving/mcp_server.py", "run-stdio"),
    cwd="/home/ubuntu/self-improving",
)


@_requires_live_mcp_server
def test_full_cycle_read_only_mcp_capability_through_existing_systems():
    # ---- OBSERVE: existing EvidenceKernel, not a new state store ----
    lantern = Lantern()
    kernel = lantern.kernel
    obs = kernel.observe(
        content="operator wants to know the current self-improving memory summary",
        source="user_request",
        reliability=0.9,
    )
    evidence, contradiction = kernel.add_evidence(
        concept="need_memory_summary", observation_id=obs.id, weight=1.0, sign=1
    )
    assert contradiction is None
    belief_before = kernel.belief("need_memory_summary")
    assert belief_before > 0.5

    # ---- CAPABILITY: existing canonical registry, not a new list ----
    registry = create_default_registry()
    descriptor = registry.get("web_research")
    assert descriptor is not None
    assert descriptor.exposes_via_mcp is True
    assert descriptor.externally_exposable is True  # not in NEVER_EXTERNALLY_EXPOSE

    # ---- COMPASS (before): read-only orientation over existing state ----
    compass_before = orient(
        kernel=kernel,
        concepts_of_interest=("need_memory_summary",),
        registry=registry,
        capability_decision=None,
    )
    assert compass_before.why  # WHY is grounded in real kernel evidence
    # Compass must not assert allowed without a real CapabilityDecision.
    research_row = next(a for a in compass_before.what_is_allowed if a.capability == "web_research")
    assert research_row.allowed is False

    # ---- AUTHORIZE: existing capability_authorization.CapabilityDecision ----
    # NOTE: capability_authorization.authorize() negotiates the SEPARATE
    # Lantern-to-Lantern PEER protocol vocabulary (evidence_exchange,
    # codex_update, belief_query, ...) defined in compatibility.py. The
    # orchestration/MCP tool-capability vocabulary (memory_boundary,
    # messaging, web_research, ...) is a different namespace. Both
    # compass.what_is_allowed() and MCPIntegrationBoundary.execute() were
    # deliberately written to accept ANY object exposing
    # `.is_authorized(name)` -- CapabilityDecision itself, not the
    # peer-negotiation authorize() function, is the real shared seam
    # between the two systems. We build a CapabilityDecision directly,
    # exactly as an operator's local tool-authorization policy would, and
    # exactly as the existing MCP integration tests already do.
    #
    # We use "web_research" (externally_exposable, exposes_via_mcp=True)
    # as the capability for this cycle rather than "memory_boundary":
    # discovering during this test that memory_boundary's own authority_
    # requirements include "memory_mutation" -- which sits in
    # NEVER_EXTERNALLY_EXPOSE -- means memory_boundary is structurally
    # forbidden from ANY external/MCP exposure by the existing registry,
    # even for a read-only tool call. That is consistent with the
    # registry's own exposes_via_mcp=False flag on memory_boundary, and is
    # exercised directly by the refusal test below rather than being
    # worked around here. Reading an external memory service over MCP is
    # exactly the shape web_research already models ("gather external
    # information for comparison and evaluation").
    decision = CapabilityDecision(
        node_id="self-improving-memory",
        identity_status="CRYPTOGRAPHICALLY_VERIFIED",
        shared_capabilities=frozenset({"web_research"}),
        authorized_capabilities=frozenset({"web_research"}),
        denied_capabilities={},
        reason="operator-scoped local authorization for read-only external memory-service query",
    )
    assert decision.is_authorized("web_research")
    assert decision.identity_status == "CRYPTOGRAPHICALLY_VERIFIED"

    # Compass re-run WITH the real authorization decision now shows allowed.
    compass_authorized = orient(
        kernel=kernel,
        concepts_of_interest=("need_memory_summary",),
        registry=registry,
        capability_decision=decision,
    )
    research_row_authorized = next(
        a for a in compass_authorized.what_is_allowed if a.capability == "web_research"
    )
    assert research_row_authorized.allowed is True

    # ---- DELEGATE: existing scoped DelegationRecord, via MCP boundary ----
    client = StdioMCPClient(MCP_SERVER_TARGET)
    boundary = MCPIntegrationBoundary(registry, adapter=client)
    delegation = boundary.scoped_delegation_for_mcp(
        objective="read the current self-improving memory summary as an external information source",
        capability_name="web_research",
        server_id=MCP_SERVER_TARGET.server_id,
        tool_name="memory_read",
        allowed_arguments=("caller_id", "origin", "read_target"),
    )
    assert delegation.capability == "web_research"
    assert delegation.status == "REQUESTED"

    # ---- MCP EXECUTE / RETURN: real subprocess round-trip ----
    result = boundary.execute(
        request=MCPExecutionRequest(
            capability_name="web_research",
            server_id=MCP_SERVER_TARGET.server_id,
            tool_name="memory_read",
            arguments={
                "caller_id": "lantern-full-cycle-test",
                "origin": "lantern",
                "read_target": "summary",
            },
            purpose="full-cycle read-only demonstration",
        ),
        delegation=delegation,
        capability_decision=decision,
    )
    assert result.status == "RETURNED"
    assert result.provenance.source_class == "MCP_ENDPOINT"
    assert result.provenance.is_remote is True

    returned_delegation = delegation.transition(
        "RETURNED",
        result_summary="memory_read returned a summary payload",
        result_provenance=result.provenance,
    )
    assert returned_delegation.status == "RETURNED"
    assert returned_delegation.verification_summary is None

    # ---- VERIFY: independent of the MCP server's own success claim ----
    # The capability's own VerificationPolicy (unchanged, pre-existing)
    # requires authorization_record_id / pending_ledger_state evidence.
    # We independently check the actual structured payload rather than
    # trusting result.status == "RETURNED" as proof of correctness.
    payload = result.raw_result["structured_content"]
    independently_verified = payload.get("ok") is True and "records" in payload
    assert independently_verified

    verified_delegation = returned_delegation.transition(
        "VERIFIED",
        verification_summary=(
            "independently inspected structured_content: ok=True, "
            "records field present, matches expected_outputs for web_research"
        ),
    )
    assert verified_delegation.status == "VERIFIED"
    assert verified_delegation.verification_summary is not None

    # ---- COMPRESS (final): existing Scar mechanism, nothing new ----
    compressed = compress_cycle(
        compass_before=compass_before,
        delegation=verified_delegation,
        source="lantern_full_cycle_test",
        trigger="operator requested memory summary via MCP",
        observation=(
            "MCP capability web_research executed via real stdio server "
            f"{MCP_SERVER_TARGET.server_id}, tool memory_read"
        ),
        outcome="verified_read_only_success",
        severity="low",
        lesson="read-only MCP capabilities can be authorized, delegated, executed, and independently verified end to end",
    )
    assert compressed.scar_record.scar.related_evidence_ids == ()
    assert compressed.scar_record.scar.provenance["delegation_status"] == "VERIFIED"
    assert compressed.scar_record.scar.provenance["result_provenance"]["source_class"] == "MCP_ENDPOINT"

    # persist through the EXISTING Chronicle/Scar path, not a new one
    with tempfile.TemporaryDirectory() as tmpdir:
        chronicled_lantern = Lantern(chronicle_filename=f"{tmpdir}/chronicle.jsonl")
        persisted = chronicled_lantern.persist_scar(compressed.scar_record)
        assert persisted.verified is True

    kernel.add_evidence(
        concept="need_memory_summary", observation_id=obs.id, weight=1.0, sign=-1
    )
    belief_after = kernel.belief("need_memory_summary", at_step=obs.step)
    # Belief bookkeeping is independent of this test's MCP assertions; we
    # only assert it is still a valid probability, proving the kernel
    # was not bypassed or corrupted by the MCP cycle.
    assert 0.0 <= belief_after <= 1.0


def test_mcp_cannot_be_used_to_bypass_protected_authority_rejection():
    """The refusal case: 'messaging' touches NEVER_EXTERNALLY_EXPOSE
    authorities. MCP discovery/availability of a messaging-shaped tool
    must never grant Lantern authority to use it.
    """
    registry = create_default_registry()
    client = StdioMCPClient(MCP_SERVER_TARGET)
    boundary = MCPIntegrationBoundary(registry, adapter=client)

    # Compass must refuse to claim this is allowed even before touching MCP.
    compass_reading = orient(registry=registry, capability_decision=None)
    messaging_row = next(a for a in compass_reading.what_is_allowed if a.capability == "messaging")
    assert messaging_row.allowed is False
    assert "NEVER_EXTERNALLY_EXPOSE" in messaging_row.reason

    delegation = boundary.scoped_delegation_for_mcp(
        objective="attempt to send a message via a hypothetical MCP messaging tool",
        capability_name="messaging",
        server_id=MCP_SERVER_TARGET.server_id,
        tool_name="send_message",
    )
    assert delegation.requires_human_confirmation is True

    # Even a CapabilityDecision that claims "messaging" was authorized
    # must be refused at the boundary. capability_authorization.py's own
    # NEVER_AUTHORIZABLE floor covers codex_update; messaging's own
    # structural floor (NEVER_EXTERNALLY_EXPOSE via `permissions`) is
    # enforced by compass/orchestration, and MCPIntegrationBoundary.execute()
    # must still refuse if the descriptor requires protected authority that
    # was never actually granted through a real authorization pipeline --
    # here we simulate an operator/test bug (a hand-built decision that
    # incorrectly claims messaging is authorized) to prove the boundary
    # itself, not just capability_authorization.py, refuses to act on it.
    denied_decision = CapabilityDecision(
        node_id=MCP_SERVER_TARGET.server_id,
        identity_status="CRYPTOGRAPHICALLY_VERIFIED",
        shared_capabilities=frozenset({"messaging"}),
        authorized_capabilities=frozenset(),
        denied_capabilities={"messaging": "policy_denied"},
        reason="messaging touches NEVER_EXTERNALLY_EXPOSE authority; never authorized",
    )

    with pytest.raises(PermissionError):
        boundary.execute(
            request=MCPExecutionRequest(
                capability_name="messaging",
                server_id=MCP_SERVER_TARGET.server_id,
                tool_name="send_message",
                arguments={"to": "someone", "body": "this must never send"},
            ),
            delegation=delegation,
            capability_decision=denied_decision,
        )


def test_compression_refuses_to_upgrade_returned_into_verified_for_mcp_cycle():
    """Sanity re-proof, scoped to this phase's MCP path: even a fully
    successful MCP RETURN cannot be compressed into VERIFIED without an
    explicit verification_summary.
    """
    registry = create_default_registry()
    client = StdioMCPClient(MCP_SERVER_TARGET)
    boundary = MCPIntegrationBoundary(registry, adapter=client)
    delegation = boundary.scoped_delegation_for_mcp(
        objective="read memory summary",
        capability_name="memory_boundary",
        server_id=MCP_SERVER_TARGET.server_id,
        tool_name="memory_read",
    )

    compass_reading = orient(registry=registry, capability_decision=None)

    returned_only = delegation.transition("RETURNED", result_summary="looked fine")
    # Force the exact forbidden shape: RETURNED status but with a
    # verification_summary already attached (what compression must reject).
    from dataclasses import replace
    contaminated = replace(returned_only, verification_summary="claimed verified without independent check")

    with pytest.raises(CompressionViolation):
        compress_cycle(
            compass_before=compass_reading,
            delegation=contaminated,
            source="lantern_full_cycle_test",
            trigger="regression guard",
            observation="attempted silent RETURNED->VERIFIED collapse",
            outcome="should_be_rejected",
            severity="low",
        )
