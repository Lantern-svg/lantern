"""
Test: snapshot-based fast recovery (snapshot + event stream)

Verifies:
- kernel.snapshot() serializes complete state
- EvidenceKernel.restore() rebuilds kernel exactly
- Chronicle.records_after() yields only events after a given chain hash
- Lantern.save_snapshot()/load_snapshot() persist/restore via file
- Lantern.startup() uses snapshot-first fast recovery
"""

from lantern.core import Lantern, EvidenceKernel, Chronicle


def test_kernel_snapshot_restore_roundtrip():
    kernel = EvidenceKernel()
    obs = kernel.observe("Water freezes", "experiment", 1.0)
    kernel.add_evidence("water", obs.id, 1, 1)

    snapshot = kernel.snapshot(chronicle_chain="test_chain_123")

    restored = EvidenceKernel.restore(snapshot)

    assert restored.step == kernel.step
    assert len(restored.observations) == len(kernel.observations)
    assert len(restored.evidence) == len(kernel.evidence)
    assert restored.belief("water") == kernel.belief("water")


def test_chronicle_records_after(tmp_path):
    chronicle_path = tmp_path / "test.jsonl"
    chronicle = Chronicle(chronicle_path)

    lantern = Lantern()
    lantern.bus.chronicle = chronicle

    obs1 = lantern.observe("First", "source", 1.0)
    lantern.add_evidence("concept_a", obs1.id, 1, 1)

    chain_after_first = chronicle.chain

    obs2 = lantern.observe("Second", "source", 1.0)
    lantern.add_evidence("concept_b", obs2.id, 1, 1)

    all_records = list(chronicle.replay())
    after_first = list(chronicle.records_after(chain_after_first))

    assert len(after_first) < len(all_records)
    assert all(r["payload"].get("concept") != "concept_a" for r in after_first)


def test_lantern_snapshot_fast_recovery(tmp_path):
    chronicle_path = tmp_path / "recovery.jsonl"

    writer = Lantern(chronicle_filename=chronicle_path)
    obs1 = writer.observe("Water freezes", "experiment", 1.0)
    writer.add_evidence("water", obs1.id, 1, 1)

    writer.save_snapshot()
    snapshot_chain = writer.bus.chronicle.chain

    obs2 = writer.observe("Second observation", "experiment", 1.0)
    writer.add_evidence("water", obs2.id, 0.5, 1)

    expected_belief = writer.kernel.belief("water")
    expected_step = writer.kernel.step

    reader = Lantern(chronicle_filename=chronicle_path)
    reader.startup()

    assert reader.kernel.step == expected_step
    assert len(reader.kernel.observations) == 2
    assert len(reader.kernel.evidence) == 2
    assert abs(reader.kernel.belief("water") - expected_belief) < 0.0001


def test_snapshot_fallback_when_missing(tmp_path):
    chronicle_path = tmp_path / "fallback.jsonl"

    writer = Lantern(chronicle_filename=chronicle_path)
    obs = writer.observe("Water freezes", "experiment", 1.0)
    writer.add_evidence("water", obs.id, 1, 1)

    reader = Lantern(chronicle_filename=chronicle_path)
    reader.startup()

    codex = next(m for m in reader.modules if m.name == "codex")
    event_types = [e["type"] for e in codex.state.values()]

    assert "OBSERVATION_CREATED" in event_types
    assert "EVIDENCE_CREATED" in event_types
    assert "BELIEF_UPDATED" in event_types


def test_snapshot_only_replays_newer_events(tmp_path):
    """The snapshot-bounded recovery path must apply strictly fewer
    events to the kernel/bus than a full-history replay would,
    proportional to how many events occurred before the snapshot.
    """
    chronicle_path = tmp_path / "newer.jsonl"

    writer = Lantern(chronicle_filename=chronicle_path)
    obs1 = writer.observe("First", "experiment", 1.0)
    writer.add_evidence("concept_a", obs1.id, 1, 1)

    writer.save_snapshot()

    obs2 = writer.observe("Second", "experiment", 1.0)
    writer.add_evidence("concept_b", obs2.id, 1, 1)

    total_chronicle_records = len(list(Chronicle(chronicle_path).replay()))

    reader = Lantern(chronicle_filename=chronicle_path)
    applied_events = []
    original_apply = reader._apply_to_kernel

    def counting_apply(event):
        applied_events.append(event)
        return original_apply(event)

    reader._apply_to_kernel = counting_apply
    reader.startup()

    assert len(applied_events) < total_chronicle_records
    assert reader.kernel.step == 2
