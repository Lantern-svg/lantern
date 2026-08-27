"""
Lantern Content Provenance Tests

Covers:

TAGGING
  - all seven classes are constructible
  - unknown class rejected
  - EXTERNAL_CLASSES require a non-empty origin_id
  - ALREADY_FIRST_PARTY_CLASSES do not require relay_path

METADATA ROUND-TRIP
  - tag_metadata / read_tag round-trip through an Observation
  - read_tag returns None when no tag was ever attached (never
    defaults to an implicit first-party assumption)

PROMOTION (the PROVENANCE_TAG invariant, enforced)
  - promoting already-first-party content raises
  - promotion with no evidence raises
  - promotion with more than one evidence field raises
  - promotion via artifact verification produces VERIFIED_ARTIFACT
  - promotion via human override produces AUTHORIZED_OVERRIDE
  - promotion via ownership transfer produces FIRST_PARTY_OBSERVATION
  - the original external tag is never mutated by promotion

RELAY AMPLIFICATION
  - four instances repeating the same claim is 1 witness, not 4
  - a genuinely new origin_id is counted as a new witness
  - is_independent_corroboration matches count_independent_witnesses
"""

from __future__ import annotations

import pytest

from lantern import content_provenance as cp
from lantern.core import EvidenceKernel


# ============================================================
# TAGGING
# ============================================================

def test_all_seven_classes_constructible():
    for source_class in cp.CONTENT_PROVENANCE_CLASSES:
        if source_class in cp.EXTERNAL_CLASSES:
            tag = cp.ContentProvenanceTag(source_class=source_class, origin_id="peer-1")
        else:
            tag = cp.ContentProvenanceTag(source_class=source_class, origin_id="")
        assert tag.source_class == source_class


def test_unknown_class_rejected():
    with pytest.raises(cp.ContentProvenanceError):
        cp.ContentProvenanceTag(source_class="NOT_REAL", origin_id="x")


def test_external_classes_require_origin_id():
    with pytest.raises(cp.ContentProvenanceError):
        cp.ContentProvenanceTag(source_class=cp.PEER_CONTENT, origin_id="")


def test_first_party_and_external_properties():
    fp = cp.ContentProvenanceTag(source_class=cp.FIRST_PARTY_OBSERVATION, origin_id="")
    ext = cp.ContentProvenanceTag(source_class=cp.PEER_CONTENT, origin_id="peer-1")
    assert fp.is_first_party is True
    assert fp.is_external is False
    assert ext.is_first_party is False
    assert ext.is_external is True


# ============================================================
# METADATA ROUND-TRIP
# ============================================================

def test_tag_metadata_and_read_tag_round_trip():
    tag = cp.ContentProvenanceTag(source_class=cp.PEER_CONTENT, origin_id="peer-node-7", note="from handshake")
    metadata = cp.tag_metadata(tag)
    read_back = cp.read_tag(metadata)
    assert read_back == tag


def test_tag_metadata_does_not_mutate_existing_dict():
    original = {"other_field": "value"}
    tag = cp.ContentProvenanceTag(source_class=cp.OWNER_ASSERTION, origin_id="")
    merged = cp.tag_metadata(tag, original)
    assert "content_provenance" not in original
    assert "content_provenance" in merged
    assert merged["other_field"] == "value"


def test_read_tag_returns_none_when_absent():
    assert cp.read_tag({}) is None
    assert cp.read_tag(None) is None
    assert cp.read_tag({"unrelated": 1}) is None


def test_tag_survives_through_a_real_observation():
    """Attach a tag to an actual Observation.metadata via EvidenceKernel,
    confirm it round-trips exactly as core.py's snapshot/restore would
    persist and reload it."""
    kernel = EvidenceKernel(owner_instance="instance-A")
    tag = cp.ContentProvenanceTag(source_class=cp.IMPORTED_EXTERNAL_CONTENT, origin_id="https://example.invalid/doc")
    metadata = cp.tag_metadata(tag)
    obs = kernel.observe("some imported claim", source="import", reliability=0.4, metadata=metadata)

    snapshot = kernel.snapshot()
    restored = EvidenceKernel.restore(snapshot)
    restored_obs = restored.observations[obs.id]

    read_back = cp.read_tag(restored_obs.metadata)
    assert read_back == tag


# ============================================================
# PROMOTION (the invariant)
# ============================================================

def test_promoting_already_first_party_raises():
    tag = cp.ContentProvenanceTag(source_class=cp.FIRST_PARTY_OBSERVATION, origin_id="")
    with pytest.raises(cp.ContentProvenanceError):
        cp.promote_to_first_party(tag, cp.PromotionEvidence(artifact_verification="chronicle:abc123"))


def test_promotion_with_no_evidence_raises():
    tag = cp.ContentProvenanceTag(source_class=cp.PEER_CONTENT, origin_id="peer-1")
    with pytest.raises(cp.ContentProvenanceError):
        cp.promote_to_first_party(tag, cp.PromotionEvidence())


def test_promotion_with_multiple_evidence_fields_raises():
    tag = cp.ContentProvenanceTag(source_class=cp.PEER_CONTENT, origin_id="peer-1")
    with pytest.raises(cp.ContentProvenanceError):
        cp.promote_to_first_party(
            tag,
            cp.PromotionEvidence(
                artifact_verification="chronicle:abc123",
                human_override_authority="operator-alice",
            ),
        )


def test_promotion_via_artifact_verification():
    tag = cp.ContentProvenanceTag(source_class=cp.IMPORTED_EXTERNAL_CONTENT, origin_id="doc-1")
    promoted = cp.promote_to_first_party(tag, cp.PromotionEvidence(artifact_verification="chronicle:hash-xyz"))
    assert promoted.source_class == cp.VERIFIED_ARTIFACT
    assert promoted.origin_id == "doc-1"
    assert "chronicle:hash-xyz" in promoted.note


def test_promotion_via_human_override():
    tag = cp.ContentProvenanceTag(source_class=cp.UNVERIFIED_CONTENT, origin_id="rumor-1")
    promoted = cp.promote_to_first_party(tag, cp.PromotionEvidence(human_override_authority="operator-bob"))
    assert promoted.source_class == cp.AUTHORIZED_OVERRIDE
    assert "operator-bob" in promoted.note


def test_promotion_via_ownership_transfer():
    tag = cp.ContentProvenanceTag(source_class=cp.PEER_CONTENT, origin_id="peer-9")
    promoted = cp.promote_to_first_party(
        tag, cp.PromotionEvidence(ownership_transfer_record_signature="deadbeef")
    )
    assert promoted.source_class == cp.FIRST_PARTY_OBSERVATION


def test_original_tag_is_never_mutated_by_promotion():
    tag = cp.ContentProvenanceTag(source_class=cp.PEER_CONTENT, origin_id="peer-9")
    cp.promote_to_first_party(tag, cp.PromotionEvidence(human_override_authority="operator-carol"))
    # tag itself (frozen dataclass) must be completely unchanged.
    assert tag.source_class == cp.PEER_CONTENT
    assert tag.origin_id == "peer-9"


# ============================================================
# RELAY AMPLIFICATION
# ============================================================

def test_relay_chain_a_to_d_is_one_witness_not_four():
    # A's claim reaches D via three different relay paths (B, C, and
    # a direct restatement) -- all trace back to the same terminal origin A.
    tag_via_b = cp.ContentProvenanceTag(source_class=cp.PEER_CONTENT, origin_id="B", relay_path=("A",))
    tag_via_c = cp.ContentProvenanceTag(source_class=cp.PEER_CONTENT, origin_id="C", relay_path=("A",))
    tag_via_bc = cp.ContentProvenanceTag(source_class=cp.PEER_CONTENT, origin_id="D-restate", relay_path=("A", "B", "C"))

    witnesses = cp.count_independent_witnesses([tag_via_b, tag_via_c, tag_via_bc])
    assert witnesses == 1


def test_genuinely_new_origin_counts_as_new_witness():
    tag_a = cp.ContentProvenanceTag(source_class=cp.PEER_CONTENT, origin_id="A")
    tag_e = cp.ContentProvenanceTag(source_class=cp.PEER_CONTENT, origin_id="E")

    witnesses = cp.count_independent_witnesses([tag_a, tag_e])
    assert witnesses == 2


def test_is_independent_corroboration_true_for_new_origin():
    existing = [cp.ContentProvenanceTag(source_class=cp.PEER_CONTENT, origin_id="A")]
    new_tag = cp.ContentProvenanceTag(source_class=cp.PEER_CONTENT, origin_id="E")
    assert cp.is_independent_corroboration(existing, new_tag) is True


def test_is_independent_corroboration_false_for_relayed_same_origin():
    existing = [cp.ContentProvenanceTag(source_class=cp.PEER_CONTENT, origin_id="A")]
    relayed = cp.ContentProvenanceTag(source_class=cp.PEER_CONTENT, origin_id="B", relay_path=("A",))
    assert cp.is_independent_corroboration(existing, relayed) is False


def test_terminal_origin_uses_relay_path_when_present():
    direct = cp.ContentProvenanceTag(source_class=cp.PEER_CONTENT, origin_id="A")
    relayed = cp.ContentProvenanceTag(source_class=cp.PEER_CONTENT, origin_id="B", relay_path=("A",))
    assert cp.terminal_origin(direct) == "A"
    assert cp.terminal_origin(relayed) == "A"
