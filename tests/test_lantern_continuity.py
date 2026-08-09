"""
Lantern Continuity Watermark Tests (v0.92)

Locks:
- local watermark is a read-only view over EvidenceKernel.step and
  Chronicle.chain -- no new counter, no new chain
- snapshot/restore preserves continuity (startup() after restart
  reaches the identical watermark as before restart)
- Chronicle replay preserves continuity
- remote watermark is parsed, not trusted -- compare_watermarks()
  only classifies, it never asserts truth
- COMPATIBLE / BEHIND / AHEAD / DIVERGED / INCOMPATIBLE are produced
  only from states the repository can actually justify
- protocol incompatibility (different major) always wins over
  watermark comparison
- watermark comparison cannot mutate belief, evidence, or bypass
  codex_update
"""

import os
import tempfile

import pytest

from lantern.core import Lantern
from lantern.continuity import (
    AHEAD,
    BEHIND,
    COMPATIBLE,
    DIVERGED,
    INCOMPATIBLE,
    Watermark,
    compare_watermarks,
    local_watermark,
    parse_remote_watermark,
)


@pytest.fixture
def chronicle_path():
    path = tempfile.mktemp(suffix=".jsonl")
    yield path
    if os.path.exists(path):
        os.remove(path)
    snap = path + ".snapshot.json"
    if os.path.exists(snap):
        os.remove(snap)


def test_local_watermark_reads_kernel_step_and_chronicle_chain(chronicle_path):
    lantern = Lantern(chronicle_filename=chronicle_path)
    obs = lantern.observe("water freezes at 0C", "sensor", 0.9)
    lantern.add_evidence("water_freezing", obs.id, 0.8, 1)

    wm = local_watermark(lantern)

    assert wm.step == lantern.kernel.step
    assert wm.chain == lantern.bus.chronicle.chain
    assert wm.step != 0
    assert wm.chain != "GENESIS"


def test_local_watermark_with_no_chronicle_defaults_to_genesis():
    lantern = Lantern(chronicle_filename=None)
    lantern.kernel.observe("x", "source", 0.9)

    wm = local_watermark(lantern)

    assert wm.chain == "GENESIS"


def test_local_watermark_does_not_advance_kernel_step(chronicle_path):
    lantern = Lantern(chronicle_filename=chronicle_path)
    lantern.observe("water freezes at 0C", "sensor", 0.9)

    before = lantern.kernel.step
    local_watermark(lantern)
    local_watermark(lantern)
    after = lantern.kernel.step

    assert before == after


def test_snapshot_restore_preserves_continuity(chronicle_path):
    lantern = Lantern(chronicle_filename=chronicle_path)
    obs = lantern.observe("water freezes at 0C", "sensor", 0.9)
    lantern.add_evidence("water_freezing", obs.id, 0.8, 1)

    wm_before = local_watermark(lantern)
    lantern.save_snapshot()

    restarted = Lantern(chronicle_filename=chronicle_path)
    restarted.startup()

    wm_after = local_watermark(restarted)

    assert wm_after == wm_before


def test_chronicle_replay_preserves_continuity(chronicle_path):
    lantern = Lantern(chronicle_filename=chronicle_path)
    obs = lantern.observe("water freezes at 0C", "sensor", 0.9)
    lantern.add_evidence("water_freezing", obs.id, 0.8, 1)
    wm_before = local_watermark(lantern)

    # No snapshot this time -- startup() must fall back to a full
    # Chronicle replay and still land on the same watermark.
    restarted = Lantern(chronicle_filename=chronicle_path)
    restarted.startup()

    wm_after = local_watermark(restarted)

    assert wm_after == wm_before


def test_parse_remote_watermark_is_a_plain_parse_no_trust_decision():
    remote = parse_remote_watermark({"step": 5, "chain": "abc123"})

    assert remote == Watermark(step=5, chain="abc123")


def test_parse_remote_watermark_defaults_missing_fields():
    remote = parse_remote_watermark({})

    assert remote == Watermark(step=0, chain="GENESIS")


def test_compare_watermarks_same_step_same_chain_is_compatible():
    local = Watermark(step=5, chain="abc")
    remote = Watermark(step=5, chain="abc")

    result = compare_watermarks("0.92", "0.92", local, remote)

    assert result.status == COMPATIBLE


def test_compare_watermarks_same_step_different_chain_is_diverged():
    local = Watermark(step=5, chain="abc")
    remote = Watermark(step=5, chain="xyz")

    result = compare_watermarks("0.92", "0.92", local, remote)

    assert result.status == DIVERGED


def test_compare_watermarks_lower_remote_step_is_behind():
    local = Watermark(step=5, chain="abc")
    remote = Watermark(step=2, chain="xyz")

    result = compare_watermarks("0.92", "0.92", local, remote)

    assert result.status == BEHIND


def test_compare_watermarks_higher_remote_step_is_ahead():
    local = Watermark(step=5, chain="abc")
    remote = Watermark(step=9, chain="xyz")

    result = compare_watermarks("0.92", "0.92", local, remote)

    assert result.status == AHEAD


def test_compare_watermarks_different_major_is_incompatible_regardless_of_step():
    local = Watermark(step=5, chain="abc")
    remote = Watermark(step=5, chain="abc")

    result = compare_watermarks("0.92", "1.0", local, remote)

    assert result.status == INCOMPATIBLE


def test_compare_watermarks_protocol_incompatibility_overrides_ahead_behind():
    # Even if the remote step looks "ahead" or "behind", a different
    # major protocol version is checked first and wins.
    local = Watermark(step=5, chain="abc")
    remote_ahead = Watermark(step=99, chain="xyz")

    result = compare_watermarks("0.92", "2.0", local, remote_ahead)

    assert result.status == INCOMPATIBLE


def test_compare_watermarks_malformed_remote_step_still_classifies():
    # parse_remote_watermark coerces to int; a malformed/missing step
    # becomes 0, which just reads as BEHIND -- not a crash, not a
    # silent AHEAD/COMPATIBLE assumption.
    remote = parse_remote_watermark({"chain": "abc"})
    local = Watermark(step=5, chain="abc")

    result = compare_watermarks("0.92", "0.92", local, remote)

    assert result.status == BEHIND


def test_watermark_comparison_cannot_mutate_belief_or_evidence(chronicle_path):
    lantern = Lantern(chronicle_filename=chronicle_path)
    obs = lantern.observe("water freezes at 0C", "sensor", 0.9)
    lantern.add_evidence("water_freezing", obs.id, 0.8, 1)

    belief_before = lantern.kernel.belief("water_freezing")
    evidence_count_before = len(lantern.kernel.evidence)

    remote = parse_remote_watermark({"step": 999, "chain": "someone-elses-chain"})
    local = local_watermark(lantern)
    compare_watermarks("0.92", "0.92", local, remote)

    assert lantern.kernel.belief("water_freezing") == belief_before
    assert len(lantern.kernel.evidence) == evidence_count_before


def test_watermark_module_does_not_reference_capability_gating():
    import inspect
    from lantern import continuity as continuity_module

    source = inspect.getsource(continuity_module)

    assert "can_exchange" not in source
    assert "MESSAGE_REQUIREMENTS" not in source
    assert "add_evidence(" not in source
    assert ".belief(" not in source
