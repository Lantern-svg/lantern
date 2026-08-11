import pytest

from lantern.compass import CompassReading, orient
from lantern.compression import CompressionViolation, compress_cycle
from lantern.orchestration import DelegationRecord, ProvenanceTag
from lantern.contact_ledger import ContactAttempt, ContactEvidence
from lantern.scars import Scar


def test_compression_preserves_evidence_and_provenance_into_the_scar():
    delegation = DelegationRecord(
        objective="research a topic", capability="web_research", worker="RESEARCHER"
    ).transition("DELEGATED").transition("EXECUTING").transition(
        "RETURNED",
        result_summary="worker returned three sources",
        result_provenance=ProvenanceTag(source_class="LOCAL_WORKER", identifier="researcher-1"),
    ).transition("VERIFIED", verification_summary="sources triangulated independently")

    cycle = compress_cycle(
        compass_before=CompassReading(),
        delegation=delegation,
        source="orchestration",
        trigger="delegation completed",
        observation="RESEARCHER returned 3 sources; independently triangulated",
        outcome="SUCCESSFUL_INTEGRATION",
        severity="LOW",
        lesson="web_research verification via triangulation works well for this capability",
    )

    scar = cycle.scar_record.scar
    assert scar.provenance["delegation_id"] == delegation.id
    assert scar.provenance["delegation_status"] == "VERIFIED"
    assert scar.provenance["result_provenance"]["source_class"] == "LOCAL_WORKER"
    assert scar.lesson == "web_research verification via triangulation works well for this capability"


def test_compression_preserves_uncertainty_and_contradiction_links():
    reading = orient()  # empty reading is fine; we build one with content manually
    from lantern.compass import AttentionItem
    reading_with_contradiction = CompassReading(
        what_matters=(AttentionItem(kind="contradiction", subject="peer_trust", reason="r", source_id="c-123", severity=0.8),),
    )

    cycle = compress_cycle(
        compass_before=reading_with_contradiction,
        source="compass",
        trigger="unresolved contradiction observed during cycle",
        observation="peer_trust contradiction was open during this cycle",
        outcome="CONTRADICTORY_OBSERVATION",
        severity="MEDIUM",
    )

    assert cycle.scar_record.scar.related_contradiction_id == "c-123"
    assert "c-123" in cycle.scar_record.scar.related_evidence_ids


def test_compression_refuses_to_collapse_returned_into_verified():
    delegation = DelegationRecord(
        objective="x", capability="testing", worker="TESTER"
    ).transition("DELEGATED").transition("EXECUTING").transition(
        "RETURNED", result_summary="worker says success"
    )
    # Caller mistakenly tries to compress a RETURNED delegation while
    # attaching a verification_summary post-hoc via a bad manual replace --
    # simulate this by constructing a record that has both RETURNED status
    # AND a verification_summary, which should never legitimately happen
    # via transition() but compress_cycle must still refuse it defensively.
    import dataclasses
    corrupted = dataclasses.replace(delegation, verification_summary="not really verified")

    with pytest.raises(CompressionViolation):
        compress_cycle(
            compass_before=CompassReading(),
            delegation=corrupted,
            source="x", trigger="x", observation="x",
            outcome="SUCCESSFUL_INTEGRATION", severity="LOW",
        )


def test_compression_refuses_to_collapse_verified_without_verification_summary():
    import dataclasses
    delegation = DelegationRecord(
        objective="x", capability="testing", worker="TESTER"
    ).transition("DELEGATED").transition("EXECUTING").transition(
        "RETURNED", result_summary="worker says success"
    )
    fake_verified = dataclasses.replace(delegation, status="VERIFIED", verification_summary=None)

    with pytest.raises(CompressionViolation):
        compress_cycle(
            compass_before=CompassReading(),
            delegation=fake_verified,
            source="x", trigger="x", observation="x",
            outcome="SUCCESSFUL_INTEGRATION", severity="LOW",
        )


def test_compression_refuses_to_collapse_attempted_into_received():
    attempt = ContactAttempt(
        destination="peer-1",
        state="CONTACT_ATTEMPTED",
        evidence=ContactEvidence(delivery_evidence="peer confirmed receipt"),
    )

    with pytest.raises(CompressionViolation):
        compress_cycle(
            compass_before=CompassReading(),
            contact=attempt,
            source="x", trigger="x", observation="x",
            outcome="SUCCESSFUL_COLLABORATION", severity="LOW",
        )


def test_compression_allows_honest_attempted_state_with_no_premature_evidence():
    attempt = ContactAttempt(destination="peer-1", state="CONTACT_ATTEMPTED")

    cycle = compress_cycle(
        compass_before=CompassReading(),
        contact=attempt,
        source="contact", trigger="outreach attempt",
        observation="sent introduction message, no reply yet",
        outcome="FAILED_HANDSHAKE",
        severity="LOW",
    )
    assert cycle.scar_record.scar.provenance["contact_state"] == "CONTACT_ATTEMPTED"


def test_compression_never_rewrites_remote_provenance_to_local():
    delegation = DelegationRecord(
        objective="x", capability="lantern_interoperability", worker="NETWORK_INTEROPERABILITY"
    ).transition("DELEGATED").transition("EXECUTING").transition(
        "RETURNED",
        result_summary="peer responded",
        result_provenance=ProvenanceTag(source_class="REMOTE_LANTERN", identifier="peer-node-1"),
    ).transition("VERIFIED", verification_summary="handshake fields independently checked")

    cycle = compress_cycle(
        compass_before=CompassReading(),
        delegation=delegation,
        source="x", trigger="x", observation="x",
        outcome="SUCCESSFUL_INTEGRATION", severity="LOW",
    )
    assert cycle.scar_record.scar.provenance["result_provenance"]["source_class"] == "REMOTE_LANTERN"


def test_compression_output_is_the_existing_scar_type_not_a_new_record_type():
    cycle = compress_cycle(
        compass_before=CompassReading(),
        source="x", trigger="x", observation="x",
        outcome="SUCCESSFUL_INTEGRATION", severity="LOW",
    )
    assert isinstance(cycle.scar_record.scar, Scar)
    # constructed but not persisted -- compress_cycle never writes to a
    # Chronicle itself, matching scars.py's own constructed/persisted
    # distinction.
    assert cycle.scar_record.constructed is True
    assert cycle.scar_record.persisted is False


def test_compression_to_dict_is_fully_serializable():
    cycle = compress_cycle(
        compass_before=CompassReading(),
        source="x", trigger="x", observation="x",
        outcome="SUCCESSFUL_INTEGRATION", severity="LOW",
    )
    import json
    json.dumps(cycle.to_dict())  # must not raise
