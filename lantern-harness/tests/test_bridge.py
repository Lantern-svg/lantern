import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lantern_harness.bridge import LanternBridge


def _new_bridge():
    tmp = Path(tempfile.mkdtemp())
    return LanternBridge(tmp, node_id="test-node")


def test_identity_starts_uninitialized():
    bridge = _new_bridge()
    assert bridge.identity_status()["status"] == "NOT_INITIALIZED"


def test_ensure_identity_creates_real_node_identity():
    bridge = _new_bridge()
    result = bridge.ensure_identity()
    assert result["status"] == "READY"
    assert "public_key" in result
    assert len(result["public_key"]) == 64  # Ed25519 verify key hex


def test_identity_persists_across_bridge_instances():
    tmp = Path(tempfile.mkdtemp())
    bridge1 = LanternBridge(tmp, node_id="persist-test")
    result1 = bridge1.ensure_identity()

    bridge2 = LanternBridge(tmp, node_id="persist-test")
    result2 = bridge2.ensure_identity()

    assert result1["public_key"] == result2["public_key"]


def test_observe_and_belief_flow():
    bridge = _new_bridge()
    obs = bridge.observe("test content", source="unit_test", reliability=0.9)
    evidence = bridge.add_evidence("test_concept", obs.id, 0.8, 1)
    assert evidence.concept == "test_concept"
    belief = bridge.belief("test_concept")
    assert 0.5 < belief <= 1.0


def test_startup_with_no_prior_state():
    bridge = _new_bridge()
    result = bridge.startup()
    assert result["status"] == "READY"
    assert result["events_replayed"] == 0


def test_witness_integrity_valid_on_fresh_chronicle():
    bridge = _new_bridge()
    bridge.observe("content", source="test", reliability=1.0)
    result = bridge.witness_integrity()
    assert result["status"] == "VALID"


def test_branches_not_implemented_honestly():
    bridge = _new_bridge()
    try:
        bridge.branches()
        assert False, "expected NotImplementedError"
    except NotImplementedError as exc:
        assert "no branch" in str(exc)


def test_snapshot_and_restart_recovery():
    tmp = Path(tempfile.mkdtemp())
    bridge1 = LanternBridge(tmp, node_id="restart-test")
    obs = bridge1.observe("persisted fact", source="test", reliability=1.0)
    bridge1.add_evidence("persisted_concept", obs.id, 0.9, 1)
    bridge1.save_snapshot()

    bridge2 = LanternBridge(tmp, node_id="restart-test")
    startup_result = bridge2.startup()
    assert startup_result["status"] == "READY"
    belief = bridge2.belief("persisted_concept")
    assert belief > 0.5
