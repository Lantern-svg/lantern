"""
Gate 2 Hardening — Regression Tests for Findings 1-4.

These tests deliberately prove that each security/integrity finding
remains closed. They must not be weakened or deleted to restore green.
"""
from __future__ import annotations

import dataclasses
import math
from types import MappingProxyType

import pytest

from lantern.core import (
    Contradiction,
    Evidence,
    EvidenceAccessError,
    EvidenceKernel,
    Observation,
    ResolutionEvent,
)
from dataclasses import replace


# Finding 1: Immutability

class TestFinding1Immutability:
    """Evidence, Observation, Contradiction, ResolutionEvent must be
    structurally immutable. Nested mutable fields must also be protected."""

    def test_evidence_rejects_direct_mutation(self):
        ev = Evidence(concept="c", observation_id="o", weight=1.0, sign=1, step=1, owner_instance="n")
        with pytest.raises(dataclasses.FrozenInstanceError):
            ev.concept = "changed"

    def test_observation_rejects_direct_mutation(self):
        obs = Observation(content="sky is blue", source="s", reliability=0.9, step=1, owner_instance="n")
        with pytest.raises(dataclasses.FrozenInstanceError):
            obs.content = "changed"

    def test_contradiction_rejects_direct_mutation(self):
        c = Contradiction(concept="c", evidence_snapshot=("e1",), historical_severity=0.5,
                          current_severity=0.5, created_step=1, owner_instance="n")
        with pytest.raises(dataclasses.FrozenInstanceError):
            c.concept = "changed"

    def test_resolution_event_rejects_direct_mutation(self):
        r = ResolutionEvent(contradiction_id="c1", decision="d", reasoning="r",
                            confidence=0.8, evidence_snapshot=("e1",), owner_instance="n")
        with pytest.raises(dataclasses.FrozenInstanceError):
            r.decision = "changed"

    def test_observation_nested_metadata_is_mapping_proxy(self):
        """metadata must be a MappingProxyType (read-only view), not a
        plain dict that callers can mutate through the object."""
        obs = Observation(content="x", source="s", reliability=0.9, step=1,
                          owner_instance="n", metadata={"key": "val"})
        assert isinstance(obs.metadata, MappingProxyType)
        with pytest.raises(TypeError):
            obs.metadata["key"] = "changed"

    def test_contradiction_evidence_snapshot_is_tuple(self):
        """evidence_snapshot must be a tuple (immutable), not a list."""
        c = Contradiction(concept="c", evidence_snapshot=["e1", "e2"],
                          historical_severity=0.5, current_severity=0.5,
                          created_step=1, owner_instance="n")
        assert isinstance(c.evidence_snapshot, tuple)
        with pytest.raises((TypeError, AttributeError)):
            c.evidence_snapshot.append("e3")

    def test_resolution_evidence_snapshot_is_tuple(self):
        r = ResolutionEvent(contradiction_id="c1", decision="d", reasoning="r",
                            confidence=0.8, evidence_snapshot=["e1"],
                            owner_instance="n")
        assert isinstance(r.evidence_snapshot, tuple)

    def test_replacement_creates_new_instance(self):
        """Legitimate state transitions use dataclasses.replace, not
        in-place mutation."""
        ev = Evidence(concept="c", observation_id="o", weight=1.0, sign=1,
                      step=1, owner_instance="n", id="ev-1")
        ev2 = replace(ev, concept="changed")
        assert ev.concept == "c"
        assert ev2.concept == "changed"
        assert ev is not ev2

    def test_serialization_preserves_immutability(self):
        """After serialize -> dict -> deserialize, the objects remain frozen."""
        kernel = EvidenceKernel(owner_instance="test")
        obs = kernel.observe("fact", "local", 0.9, metadata={"k": "v"})
        kernel.add_evidence("c", obs.id, 1.0, 1)
        for e in kernel.evidence:
            assert dataclasses.is_dataclass(e)
            with pytest.raises(dataclasses.FrozenInstanceError):
                e.concept = "x"
        for o in kernel.observations.values():
            with pytest.raises(dataclasses.FrozenInstanceError):
                o.content = "x"
            assert isinstance(o.metadata, MappingProxyType)


# Finding 2: Source Deduplication

class TestFinding2Deduplication:
    """Repeated identical evidence from the same source must not inflate
    belief. Distinct evidence must remain accepted."""

    def test_identical_evidence_same_source_does_not_inflate_belief(self):
        kernel = EvidenceKernel(owner_instance="test")
        obs = kernel.observe("claim", source="sensor_a", reliability=0.9)
        kernel.add_evidence("concept", obs.id, 1.0, 1)
        belief1 = kernel.belief("concept")
        kernel.add_evidence("concept", obs.id, 1.0, 1)
        belief2 = kernel.belief("concept")
        assert len(kernel.evidence) == 1
        assert belief1 == belief2

    def test_repeated_identical_observations_no_inflation(self):
        kernel = EvidenceKernel(owner_instance="test")
        obs1 = kernel.observe("claim", source="sensor_a", reliability=0.9)
        obs2 = kernel.observe("claim", source="sensor_a", reliability=0.9)
        kernel.add_evidence("concept", obs1.id, 1.0, 1)
        belief1 = kernel.belief("concept")
        kernel.add_evidence("concept", obs2.id, 1.0, 1)
        belief2 = kernel.belief("concept")
        assert len(kernel.evidence) == 1
        assert belief1 == belief2

    def test_distinct_evidence_remains_accepted(self):
        kernel = EvidenceKernel(owner_instance="test")
        obs1 = kernel.observe("claim", source="sensor_a", reliability=0.9)
        obs2 = kernel.observe("claim", source="sensor_b", reliability=0.8)
        kernel.add_evidence("concept", obs1.id, 1.0, 1)
        kernel.add_evidence("concept", obs2.id, 1.0, 1)
        assert len(kernel.evidence) == 2

    def test_different_sign_from_same_source_accepted(self):
        kernel = EvidenceKernel(owner_instance="test")
        obs = kernel.observe("claim", source="sensor_a", reliability=0.9)
        kernel.add_evidence("concept", obs.id, 1.0, 1)
        kernel.add_evidence("concept", obs.id, 1.0, -1)
        assert len(kernel.evidence) == 2

    def test_identical_evidence_different_sources_accepted(self):
        kernel = EvidenceKernel(owner_instance="test")
        obs_a = kernel.observe("claim", source="sensor_a", reliability=0.9)
        obs_b = kernel.observe("claim", source="sensor_b", reliability=0.9)
        kernel.add_evidence("concept", obs_a.id, 1.0, 1)
        kernel.add_evidence("concept", obs_b.id, 1.0, 1)
        assert len(kernel.evidence) == 2

    def test_dedup_is_deterministic(self):
        def build():
            k = EvidenceKernel(owner_instance="test")
            o = k.observe("claim", source="s", reliability=0.9)
            k.add_evidence("c", o.id, 1.0, 1)
            k.add_evidence("c", o.id, 1.0, 1)
            k.add_evidence("c", o.id, 1.0, 1)
            return k
        k1 = build()
        k2 = build()
        assert len(k1.evidence) == len(k2.evidence) == 1
        assert k1.belief("c") == k2.belief("c")

    def test_dedup_returns_existing_evidence(self):
        kernel = EvidenceKernel(owner_instance="test")
        obs = kernel.observe("claim", source="s", reliability=0.9)
        ev1, _ = kernel.add_evidence("c", obs.id, 1.0, 1)
        ev2, _ = kernel.add_evidence("c", obs.id, 1.0, 1)
        assert ev1.id == ev2.id


# Finding 3: Reliability Validation

class TestFinding3ReliabilityValidation:
    """Reliability must be in [0.0, 1.0]. Negative and >1.0 must be
    rejected with ValueError."""

    def test_reliability_zero_accepted(self):
        kernel = EvidenceKernel(owner_instance="test")
        obs = kernel.observe("claim", source="s", reliability=0.0)
        assert obs.reliability == 0.0

    def test_reliability_one_accepted(self):
        kernel = EvidenceKernel(owner_instance="test")
        obs = kernel.observe("claim", source="s", reliability=1.0)
        assert obs.reliability == 1.0

    def test_reliability_half_accepted(self):
        kernel = EvidenceKernel(owner_instance="test")
        obs = kernel.observe("claim", source="s", reliability=0.5)
        assert obs.reliability == 0.5

    def test_negative_reliability_rejected(self):
        kernel = EvidenceKernel(owner_instance="test")
        with pytest.raises(ValueError, match="reliability"):
            kernel.observe("claim", source="s", reliability=-0.1)

    def test_reliability_above_one_rejected(self):
        kernel = EvidenceKernel(owner_instance="test")
        with pytest.raises(ValueError, match="reliability"):
            kernel.observe("claim", source="s", reliability=1.1)

    def test_reliability_far_above_one_rejected(self):
        kernel = EvidenceKernel(owner_instance="test")
        with pytest.raises(ValueError, match="reliability"):
            kernel.observe("claim", source="s", reliability=5.0)

    def test_reliability_not_silently_clamped(self):
        kernel = EvidenceKernel(owner_instance="test")
        try:
            kernel.observe("claim", source="s", reliability=-0.5)
            assert False, "Should have raised ValueError"
        except ValueError:
            pass
        assert len(kernel.observations) == 0
        assert kernel.step == 0


# Finding 4: Admission Boundary

class TestFinding4AdmissionBoundary:
    """Direct kernel.evidence.append() must be rejected. Evidence must
    enter through add_evidence() so that deduplication, contradiction
    detection, and ownership checks cannot be bypassed."""

    def test_add_evidence_succeeds(self):
        kernel = EvidenceKernel(owner_instance="test")
        obs = kernel.observe("claim", source="s", reliability=0.9)
        ev, contra = kernel.add_evidence("concept", obs.id, 1.0, 1)
        assert ev is not None
        assert len(kernel.evidence) == 1

    def test_direct_append_rejected(self):
        kernel = EvidenceKernel(owner_instance="test")
        obs = kernel.observe("claim", source="s", reliability=0.9)
        ev = Evidence(concept="c", observation_id=obs.id, weight=0.9, sign=1,
                      step=1, owner_instance="test")
        with pytest.raises(EvidenceAccessError, match="direct mutation"):
            kernel.evidence.append(ev)

    def test_direct_extend_rejected(self):
        kernel = EvidenceKernel(owner_instance="test")
        obs = kernel.observe("claim", source="s", reliability=0.9)
        ev = Evidence(concept="c", observation_id=obs.id, weight=0.9, sign=1,
                      step=1, owner_instance="test")
        with pytest.raises(EvidenceAccessError, match="direct mutation"):
            kernel.evidence.extend([ev])

    def test_direct_insert_rejected(self):
        kernel = EvidenceKernel(owner_instance="test")
        obs = kernel.observe("claim", source="s", reliability=0.9)
        ev = Evidence(concept="c", observation_id=obs.id, weight=0.9, sign=1,
                      step=1, owner_instance="test")
        with pytest.raises(EvidenceAccessError, match="direct mutation"):
            kernel.evidence.insert(0, ev)

    def test_direct_setitem_rejected(self):
        kernel = EvidenceKernel(owner_instance="test")
        obs = kernel.observe("claim", source="s", reliability=0.9)
        kernel.add_evidence("c", obs.id, 1.0, 1)
        ev_replacement = Evidence(concept="c", observation_id=obs.id, weight=0.9, sign=1,
                                  step=1, owner_instance="test", id="replacement")
        with pytest.raises(EvidenceAccessError, match="direct mutation"):
            kernel.evidence[0] = ev_replacement

    def test_direct_append_cannot_bypass_dedup(self):
        kernel = EvidenceKernel(owner_instance="test")
        obs = kernel.observe("claim", source="s", reliability=0.9)
        kernel.add_evidence("c", obs.id, 1.0, 1)
        assert len(kernel.evidence) == 1
        dup = Evidence(concept="c", observation_id=obs.id, weight=0.9, sign=1,
                       step=1, owner_instance="test")
        with pytest.raises(EvidenceAccessError):
            kernel.evidence.append(dup)
        assert len(kernel.evidence) == 1

    def test_direct_append_cannot_bypass_contradiction_detection(self):
        kernel = EvidenceKernel(owner_instance="test")
        obs = kernel.observe("claim", source="s", reliability=0.9)
        kernel.add_evidence("c", obs.id, 1.0, 1)
        contra_ev = Evidence(concept="c", observation_id=obs.id, weight=0.9, sign=-1,
                             step=1, owner_instance="test")
        with pytest.raises(EvidenceAccessError):
            kernel.evidence.append(contra_ev)
        assert len(kernel.contradictions) == 0

    def test_direct_append_wrong_owner_rejected(self):
        kernel = EvidenceKernel(owner_instance="test")
        foreign = Evidence(concept="c", observation_id="o", weight=1.0, sign=1,
                           step=1, owner_instance="other")
        with pytest.raises(EvidenceAccessError):
            kernel.evidence.append(foreign)

    def test_restore_uses_admission_context(self):
        """restore() must set _admitting before appending — legitimate path."""
        kernel = EvidenceKernel(owner_instance="test")
        obs = kernel.observe("claim", source="s", reliability=0.9)
        kernel.add_evidence("c", obs.id, 1.0, 1)
        snapshot = kernel.snapshot()
        restored = EvidenceKernel.restore(snapshot)
        assert len(restored.evidence) == 1
        assert restored.belief("c") == kernel.belief("c")

    def test_legitimate_add_evidence_runs_contradiction_detection(self):
        kernel = EvidenceKernel(owner_instance="test")
        obs1 = kernel.observe("claim", source="s1", reliability=0.9)
        obs2 = kernel.observe("counter", source="s2", reliability=0.8)
        kernel.add_evidence("c", obs1.id, 1.0, 1)
        ev2, contra = kernel.add_evidence("c", obs2.id, 1.0, -1)
        assert contra is not None
        assert contra.status == "OPEN"
