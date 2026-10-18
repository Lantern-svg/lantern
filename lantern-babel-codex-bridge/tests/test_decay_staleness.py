"""
Decay policy tests (v0.85, Tier 2 item 9 — operator-approved 2026-10-17)

Locks the behavioral laws of the new decay policy:

- Default "staleness-v1": NO silent age-based decay; only explicit
  staleness or supersession drops weight.
- "legacy-steps": the original age-based decay preserved exactly,
  including the verified zero-at-20-steps behavior.
- Supersession drops weight once and records an auditable pointer.
- Scar-linked evidence can never be stale-marked or superseded
  (permanent scars).
- belief() can report both aggregates (with and without stale evidence).
"""

import pytest

import lantern.core as core_module
from lantern.core import Lantern


def build_lantern_with_evidence(concept="test", weight=1.0, sign=1):
    lantern = Lantern()
    obs = lantern.observe("Test evidence", "source", 1.0)
    evidence, _ = lantern.kernel.add_evidence(concept, obs.id, weight, sign)
    return lantern, evidence


def test_decayed_weight_reaches_zero_at_20_steps_legacy():
    # Verified fact behind Tier 2 item 9: under legacy-steps, unit-weight
    # evidence decays to exactly 0.0 at 20 ledger steps and never recovers.
    core_module.DECAY_POLICY = "legacy-steps"
    try:
        lantern, evidence = build_lantern_with_evidence()
        step0 = evidence.step
        assert evidence.decayed_weight(step0) == pytest.approx(1.0)
        assert evidence.decayed_weight(step0 + 10) == pytest.approx(0.5)
        assert evidence.decayed_weight(step0 + 19) == pytest.approx(0.05)
        assert evidence.decayed_weight(step0 + 20) == 0.0
        assert evidence.decayed_weight(step0 + 200) == 0.0
    finally:
        core_module.DECAY_POLICY = "staleness-v1"


def test_weight_stable_across_100_steps_staleness_v1():
    # Default policy: weight does NOT decay with the passage of steps.
    lantern, evidence = build_lantern_with_evidence()
    step0 = evidence.step
    for age in (0, 1, 10, 19, 20, 50, 100):
        assert evidence.decayed_weight(step0 + age) == pytest.approx(1.0)
    initial = lantern.kernel.belief("test")
    for _ in range(100):
        lantern.kernel.step += 1
    assert lantern.kernel.belief("test") == pytest.approx(initial)


def test_supersession_drops_weight_once_and_records_pointer():
    lantern, old = build_lantern_with_evidence()
    obs2 = lantern.observe("Fresh observation", "source2", 1.0)
    new, _ = lantern.kernel.add_evidence("test", obs2.id, 1.0, 1)

    before = lantern.kernel.belief("test")
    lantern.kernel.mark_superseded(old.id, new.id)

    stored = [e for e in lantern.kernel.evidence if e.id == old.id][0]
    assert stored.superseded_by == new.id
    assert stored.decayed_weight(lantern.kernel.step) == 0.0
    # Weight drops ONCE at the supersession event, not continuously.
    for _ in range(30):
        lantern.kernel.step += 1
    assert stored.decayed_weight(lantern.kernel.step) == 0.0
    assert lantern.kernel.belief("test") < before


def test_mark_stale_sets_flag_and_belief_excludes():
    lantern, evidence = build_lantern_with_evidence()
    initial = lantern.kernel.belief("test")
    lantern.kernel.mark_stale(evidence.id, reason="freshness probe failed")

    stored = [e for e in lantern.kernel.evidence if e.id == evidence.id][0]
    assert stored.stale is True
    assert stored.stale_reason == "freshness probe failed"
    assert stored.decayed_weight(lantern.kernel.step) == 0.0
    # Only evidence in this concept: belief collapses to sigmoid(0) = 0.5.
    assert lantern.kernel.belief("test") == pytest.approx(0.5)
    assert initial > 0.5


def test_belief_include_stale_reports_both_aggregates():
    lantern, evidence = build_lantern_with_evidence()
    lantern.kernel.mark_stale(evidence.id, reason="probe")
    excluded = lantern.kernel.belief("test")
    included = lantern.kernel.belief("test", include_stale=True)
    assert excluded == pytest.approx(0.5)
    assert included > excluded  # stale evidence still visible on request


def test_scar_protected_evidence_cannot_be_stale_or_superseded():
    lantern, evidence = build_lantern_with_evidence()
    obs2 = lantern.observe("Superseding observation", "source2", 1.0)
    new, _ = lantern.kernel.add_evidence("test", obs2.id, 1.0, 1)

    lantern.kernel.protect_for_scar([evidence.id])

    with pytest.raises(ValueError, match="EVIDENCE_SCAR_PROTECTED"):
        lantern.kernel.mark_stale(evidence.id)
    with pytest.raises(ValueError, match="EVIDENCE_SCAR_PROTECTED"):
        lantern.kernel.mark_superseded(evidence.id, new.id)

    stored = [e for e in lantern.kernel.evidence if e.id == evidence.id][0]
    assert stored.stale is False
    assert stored.superseded_by == ""
    # Weight survives regardless of step count.
    for _ in range(50):
        lantern.kernel.step += 1
    assert stored.decayed_weight(lantern.kernel.step) == pytest.approx(1.0)


def test_persist_scar_protects_related_evidence():
    lantern = Lantern(chronicle_filename=None)
    # persist_scar requires a chronicle; use a temp file via pytest.
    import tempfile, os
    with tempfile.TemporaryDirectory() as td:
        lantern = Lantern(chronicle_filename=os.path.join(td, "chronicle.jsonl"))
        obs = lantern.observe("Scar evidence", "source", 1.0)
        evidence, _ = lantern.kernel.add_evidence("scar-concept", obs.id, 1.0, 1)

        record = lantern.create_scar(
            source="kernel", trigger="test", observation="scar test",
            outcome="DISPROVEN", severity="high",
            related_evidence_ids=[evidence.id])
        lantern.persist_scar(record)

        assert evidence.id in lantern.kernel.scar_protected
        with pytest.raises(ValueError, match="EVIDENCE_SCAR_PROTECTED"):
            lantern.kernel.mark_stale(evidence.id)


def test_version_bumped():
    # v0.85 per Tier 2 item 9 (math-core change requires a version bump).
    import pathlib
    pyproject = pathlib.Path(__file__).resolve().parents[1] / "pyproject.toml"
    assert 'version = "0.85"' in pyproject.read_text(encoding="utf-8")
