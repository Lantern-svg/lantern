"""
Lantern Reference Core Tests

Locks the behavioral laws of the frozen core.

These tests protect:

- Evidence-driven belief
- Temporal replay
- Evidence decay
- Contradiction lifecycle
- Non-destructive resolution
- Contradiction threading
- Event propagation
- Audit chain integrity
"""

import pytest

from lantern.core import Lantern


# ==================================================
# Helpers
# ==================================================

def build_conflict():
    lantern = Lantern()

    support = lantern.observe(
        "Water freezes near zero Celsius",
        "experiment",
        0.95
    )

    lantern.add_evidence(
        "water_freezing",
        support.id,
        1,
        1
    )

    opposition = lantern.observe(
        "Water never freezes",
        "claim",
        0.20
    )

    lantern.add_evidence(
        "water_freezing",
        opposition.id,
        1,
        -1
    )

    return lantern


# ==================================================
# Belief Tests
# ==================================================

def test_belief_is_evidence_derived():
    lantern = Lantern()

    obs = lantern.observe(
        "Water freezes",
        "experiment",
        1.0
    )

    lantern.add_evidence(
        "water",
        obs.id,
        1,
        1
    )

    belief = lantern.kernel.belief("water")

    assert belief > 0.5


def test_temporal_replay():
    lantern = Lantern()

    first = lantern.observe(
        "Water freezes",
        "experiment",
        1.0
    )

    lantern.add_evidence(
        "water",
        first.id,
        1,
        1
    )

    step_one = lantern.kernel.step

    second = lantern.observe(
        "Water does not freeze",
        "claim",
        1.0
    )

    lantern.add_evidence(
        "water",
        second.id,
        1,
        -1
    )

    past = lantern.kernel.belief("water", at_step=step_one)
    current = lantern.kernel.belief("water")

    assert past != current


def test_evidence_decay():
    lantern = Lantern()

    obs = lantern.observe(
        "Test evidence",
        "source",
        1.0
    )

    lantern.add_evidence(
        "test",
        obs.id,
        1,
        1
    )

    initial = lantern.kernel.belief("test")

    for _ in range(10):
        lantern.kernel.step += 1

    later = lantern.kernel.belief("test")

    assert later < initial


# ==================================================
# Contradiction Tests
# ==================================================

def test_contradiction_detected():
    lantern = build_conflict()

    assert len(lantern.kernel.contradictions) == 1
    assert lantern.kernel.contradictions[0].status == "OPEN"


def test_resolution_is_non_destructive():
    lantern = build_conflict()

    contradiction = lantern.kernel.contradictions[0]

    before = lantern.kernel.belief("water_freezing")

    lantern.resolve(
        contradiction.id,
        "experiment stronger",
        "higher reliability source",
        0.9
    )

    after = lantern.kernel.belief("water_freezing")

    # Re-fetch: with immutable Contradiction (frozen dataclass), resolve()
    # replaces the object in the kernel list rather than mutating it in place.
    resolved_contradiction = next(
        c for c in lantern.kernel.contradictions if c.id == contradiction.id
    )
    assert resolved_contradiction.status == "RESOLVED"
    assert before == after


def test_contradiction_threading():
    lantern = build_conflict()

    first = lantern.kernel.contradictions[0]

    # new opposing evidence state
    obs = lantern.observe(
        "Water behavior changes",
        "new_source",
        0.8
    )

    lantern.add_evidence(
        "water_freezing",
        obs.id,
        1,
        -1
    )

    contradictions = lantern.kernel.contradictions

    assert len(contradictions) >= 2

    latest = contradictions[-1]

    assert latest.supersedes == first.id
    # Re-fetch: with immutable Contradiction (frozen dataclass), the old
    # contradiction is replaced in the list rather than mutated in place.
    superseded = next(c for c in contradictions if c.id == first.id)
    assert superseded.superseded_by == latest.id


# ==================================================
# Event System Tests
# ==================================================

def test_modules_receive_events():
    lantern = build_conflict()

    codex = next(m for m in lantern.modules if m.name == "codex")

    event_types = [e["type"] for e in codex.state.values()]

    assert "BELIEF_UPDATED" in event_types
    assert "CONTRADICTION_DETECTED" in event_types


def test_resolution_event_propagates():
    lantern = build_conflict()

    contradiction = lantern.kernel.contradictions[0]

    lantern.resolve(
        contradiction.id,
        "resolved",
        "reviewed",
        0.9
    )

    codex = next(m for m in lantern.modules if m.name == "codex")

    event_types = [e["type"] for e in codex.state.values()]

    assert "CONTRADICTION_RESOLVED" in event_types


# ==================================================
# Audit Tests
# ==================================================

def test_audit_chain_changes():
    lantern = Lantern()

    start = lantern.bus.chain

    lantern.observe(
        "audit test",
        "tester",
        1.0
    )

    end = lantern.bus.chain

    assert start != end


def test_chronicle_persists_and_replays_module_history(tmp_path):
    chronicle_path = tmp_path / "chronicle.jsonl"

    writer = Lantern(chronicle_filename=chronicle_path)
    obs = writer.observe("Water freezes", "experiment", 1.0)
    writer.add_evidence("water", obs.id, 1, 1)

    written_history = len(writer.bus.history)
    written_chain = writer.bus.chain

    reader = Lantern(chronicle_filename=chronicle_path)
    reader.startup()

    assert len(reader.bus.history) == written_history
    assert reader.bus.chain == written_chain

    codex = next(m for m in reader.modules if m.name == "codex")
    event_types = [e["type"] for e in codex.state.values()]
    assert "OBSERVATION_CREATED" in event_types
    assert "EVIDENCE_CREATED" in event_types
    assert "BELIEF_UPDATED" in event_types


def test_chronicle_full_replay_reconstructs_kernel_state(tmp_path):
    """Without a snapshot, startup() falls back to a full Chronicle
    replay from GENESIS. Event payloads carry full reconstruction
    fields, so this still rebuilds kernel state exactly -- it's just
    slower than the snapshot-bounded path (see test_snapshot_recovery.py).
    """
    chronicle_path = tmp_path / "chronicle.jsonl"

    lantern = Lantern(chronicle_filename=chronicle_path)
    obs = lantern.observe("Water freezes", "experiment", 1.0)
    lantern.add_evidence("water", obs.id, 1, 1)
    expected_belief = lantern.kernel.belief("water")

    reader = Lantern(chronicle_filename=chronicle_path)
    reader.startup()

    assert expected_belief > 0.5
    assert reader.kernel.step == lantern.kernel.step
    assert len(reader.kernel.observations) == 1
    assert len(reader.kernel.evidence) == 1
    assert reader.kernel.belief("water") == expected_belief


def test_chronicle_verify_rejects_tampering(tmp_path):
    chronicle_path = tmp_path / "chronicle.jsonl"

    lantern = Lantern(chronicle_filename=chronicle_path)
    obs = lantern.observe("Water freezes", "experiment", 1.0)
    lantern.add_evidence("water", obs.id, 1, 1)

    records = chronicle_path.read_text(encoding="utf-8").splitlines()
    tampered = []
    for index, line in enumerate(records):
        record = __import__("json").loads(line)
        if index == len(records) - 1:
            record["payload"] = {"concept": "water", "belief": 0.9999}
        tampered.append(__import__("json").dumps(record, sort_keys=True))
    chronicle_path.write_text("\n".join(tampered) + "\n", encoding="utf-8")

    reader = Lantern(chronicle_filename=chronicle_path)
    assert reader.bus.chronicle.verify() is False

    with pytest.raises(RuntimeError, match="Chronicle verification failed"):
        reader.startup()
