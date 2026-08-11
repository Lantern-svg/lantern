from lantern.compass import (
    AllowedAction,
    AttentionItem,
    CompassReading,
    orient,
    what_is_allowed,
)
from lantern.core import EvidenceKernel
from lantern.orchestration import (
    NEVER_EXTERNALLY_EXPOSE,
    CapabilityRegistry,
    DelegationRecord,
    ProvenanceTag,
    create_default_registry,
)
from lantern.contact_ledger import ContactAttempt, ContactEvidence
from lantern.capability_authorization import CapabilityDecision


def test_compass_uses_existing_evidence_kernel_for_what_matters():
    kernel = EvidenceKernel()
    obs = kernel.observe("peer claims X", source="peer", reliability=0.9)
    kernel.add_evidence("peer_trustworthy", obs.id, weight=1.0, sign=1)
    obs2 = kernel.observe("peer contradicted itself", source="peer", reliability=0.9)
    kernel.add_evidence("peer_trustworthy", obs2.id, weight=1.0, sign=-1)

    reading = orient(kernel=kernel, concepts_of_interest=["peer_trustworthy"])

    assert any(item.kind == "contradiction" for item in reading.what_matters)
    assert any("peer_trustworthy" in line for line in reading.why)
    # The evidence trail is not invented -- it comes straight from
    # kernel.belief()/kernel.evidence, not a new store.
    assert kernel.contradictions  # existing mechanism actually fired


def test_compass_what_matters_ranked_by_existing_contradiction_severity():
    kernel = EvidenceKernel()
    for i in range(3):
        obs = kernel.observe(f"obs-{i}", source="s", reliability=1.0)
        kernel.add_evidence("concept_a", obs.id, weight=2.0, sign=1 if i % 2 == 0 else -1)

    reading = orient(kernel=kernel)
    severities = [item.severity for item in reading.what_matters if item.kind == "contradiction"]
    assert severities == sorted(severities, reverse=True)


def test_compass_what_is_allowed_never_asserts_allowed_without_a_capability_decision():
    registry = create_default_registry()
    reading = orient(registry=registry)  # no capability_decision supplied

    # web_research requires protected authority (capability_selection,
    # provenance) but is not in NEVER_EXTERNALLY_EXPOSE, so it is a
    # genuine "needs a real CapabilityDecision" case (unlike messaging,
    # which touches `permissions` and is therefore always structurally
    # forbidden regardless of any decision).
    research = next(a for a in reading.what_is_allowed if a.capability == "web_research")
    assert research.allowed is False
    assert "CapabilityDecision" in research.reason


def test_compass_what_is_allowed_reflects_actual_capability_decision():
    registry = create_default_registry()
    decision = CapabilityDecision(
        node_id="peer-1",
        identity_status="CRYPTOGRAPHICALLY_VERIFIED",
        shared_capabilities=frozenset({"web_research"}),
        authorized_capabilities=frozenset({"web_research"}),
        denied_capabilities={},
        reason="test fixture",
    )
    reading = orient(registry=registry, capability_decision=decision)
    research = next(a for a in reading.what_is_allowed if a.capability == "web_research")
    assert research.allowed is True


def test_compass_never_allows_never_externally_exposed_capabilities_regardless_of_decision():
    registry = create_default_registry()
    # Even a maximally-permissive decision cannot unlock memory_boundary /
    # core_governance -- those touch NEVER_EXTERNALLY_EXPOSE authorities.
    decision = CapabilityDecision(
        node_id="peer-1",
        identity_status="CRYPTOGRAPHICALLY_VERIFIED",
        shared_capabilities=frozenset({"memory_boundary", "core_governance"}),
        authorized_capabilities=frozenset({"memory_boundary", "core_governance"}),
        denied_capabilities={},
        reason="test fixture (should not matter)",
    )
    reading = orient(registry=registry, capability_decision=decision)
    for name in ("memory_boundary", "core_governance"):
        item = next(a for a in reading.what_is_allowed if a.capability == name)
        assert item.allowed is False
        assert "NEVER_EXTERNALLY_EXPOSE" in item.reason


def test_compass_what_is_next_surfaces_open_delegations_not_terminal_ones():
    open_record = DelegationRecord(objective="x", capability="testing", worker="TESTER")
    closed_record = DelegationRecord(
        objective="y", capability="testing", worker="TESTER"
    ).transition("DELEGATED").transition("EXECUTING").transition(
        "RETURNED", result_summary="done"
    ).transition("VERIFIED", verification_summary="checked")

    reading = orient(open_delegations=[open_record, closed_record])
    subjects_flagged = {item.source_id for item in reading.what_is_next if item.kind == "open_delegation"}
    assert open_record.id in subjects_flagged
    assert closed_record.id not in subjects_flagged


def test_compass_what_is_next_surfaces_open_contact_not_failed_ones():
    open_contact = ContactAttempt(destination="peer-x", state="MESSAGE_SENT")
    failed_contact = ContactAttempt(destination="peer-y", state="CONTACT_FAILED")

    reading = orient(open_contacts=[open_contact, failed_contact])
    subjects = {item.subject for item in reading.what_is_next if item.kind == "open_contact"}
    assert "peer-x" in subjects
    assert "peer-y" not in subjects


def test_compass_reading_is_a_read_only_snapshot_with_no_mutation_side_effects():
    kernel = EvidenceKernel()
    kernel.observe("x", source="s", reliability=1.0)
    step_before = kernel.step
    contradictions_before = list(kernel.contradictions)

    orient(kernel=kernel)

    assert kernel.step == step_before
    assert list(kernel.contradictions) == contradictions_before


def test_compass_reading_to_dict_round_trips_shape():
    reading = orient()
    payload = reading.to_dict()
    assert payload == {
        "what_matters": [],
        "why": [],
        "what_is_allowed": [],
        "what_is_next": [],
    }
