"""
Lantern Personal Instance Lifecycle Tests

Covers:

HAPPY PATH
  - full lifecycle install -> ... -> READY in order
  - optional peer connection after READY

ORDERING ENFORCEMENT
  - each stage function raises LifecycleError if called out of order
  - cannot skip stages (e.g. authorize_owner before create_identity)
  - cannot reach READY without passing through every mandatory stage
  - peer connection requires READY

BASELINE MEMORY / STARTER MATERIAL LABELING
  - seeding with zero starter material is valid (the common case)
  - each starter material label maps to the correct provenance class
  - unknown label is rejected
  - labeled content is never tagged FIRST_PARTY_OBSERVATION

IDENTITY / OWNERSHIP INTEGRATION
  - create_identity uses the real lantern.identity module (not a stub)
  - authorize_owner rejects an identity that doesn't match the instance
  - ownership history is actually persisted to disk and verifiable

PERSISTENCE
  - InstanceState save/load round-trip preserves stage + history

VERIFICATION HELPERS
  - has_reached is correct at every stage
  - has_reached treats PEER_CONNECTED as at-or-past READY
"""

from __future__ import annotations

import pytest

from lantern import content_provenance as cp
from lantern import instance_lifecycle as lc
from lantern import ownership as own
from lantern.core import EvidenceKernel


def _run_to_ready(tmp_path, node_id="node-A"):
    state = lc.install(node_id=node_id, data_dir=tmp_path / "instance")
    state = lc.initialize(state)
    state, identity = lc.create_identity(state)
    state, record = lc.authorize_owner(state, identity, owner_id="alice", owner_token="tok-1")
    kernel = EvidenceKernel(owner_instance=identity.public_key_hex)
    state = lc.seed_baseline_memory(state, kernel, starter_material=None)
    state = lc.apply_local_configuration(state, configuration={"heartbeat_interval": 30})
    state = lc.mark_ready(state)
    return state, identity, record, kernel


# ============================================================
# HAPPY PATH
# ============================================================

def test_full_lifecycle_reaches_ready(tmp_path):
    state, identity, record, kernel = _run_to_ready(tmp_path)
    assert state.stage == lc.STAGE_READY
    assert state.identity_public_key == identity.public_key_hex
    assert state.ownership_history_path is not None
    stages_seen = [entry["stage"] for entry in state.stage_history]
    assert stages_seen == [
        lc.STAGE_INSTALLED,
        lc.STAGE_INITIALIZED,
        lc.STAGE_IDENTITY_CREATED,
        lc.STAGE_OWNER_AUTHORIZED,
        lc.STAGE_BASELINE_MEMORY,
        lc.STAGE_LOCALLY_CONFIGURED,
        lc.STAGE_READY,
    ]


def test_optional_peer_connection_after_ready(tmp_path):
    state, *_ = _run_to_ready(tmp_path)
    state = lc.mark_peer_connected(state)
    assert state.stage == lc.STAGE_PEER_CONNECTED
    # Calling it again is idempotent, not an error.
    state = lc.mark_peer_connected(state)
    assert state.stage == lc.STAGE_PEER_CONNECTED


# ============================================================
# ORDERING ENFORCEMENT
# ============================================================

def test_initialize_before_install_raises(tmp_path):
    state = lc.install(node_id="node-A", data_dir=tmp_path / "instance")
    state.stage = lc.STAGE_READY  # simulate having jumped ahead
    with pytest.raises(lc.LifecycleError):
        lc.initialize(state)


def test_create_identity_before_initialize_raises(tmp_path):
    state = lc.install(node_id="node-A", data_dir=tmp_path / "instance")
    with pytest.raises(lc.LifecycleError):
        lc.create_identity(state)


def test_authorize_owner_before_identity_created_raises(tmp_path):
    state = lc.install(node_id="node-A", data_dir=tmp_path / "instance")
    state = lc.initialize(state)
    # Build a real identity separately, but do not advance state through
    # create_identity() -- state.stage is still INITIALIZED.
    from lantern import identity as idm
    identity = idm.load_or_create("node-A", tmp_path / "instance" / "identity" / "node-A")
    with pytest.raises(lc.LifecycleError):
        lc.authorize_owner(state, identity, owner_id="alice", owner_token="tok-1")


def test_seed_baseline_memory_before_owner_authorized_raises(tmp_path):
    state = lc.install(node_id="node-A", data_dir=tmp_path / "instance")
    state = lc.initialize(state)
    state, identity = lc.create_identity(state)
    kernel = EvidenceKernel(owner_instance=identity.public_key_hex)
    with pytest.raises(lc.LifecycleError):
        lc.seed_baseline_memory(state, kernel, starter_material=None)


def test_apply_local_configuration_before_baseline_memory_raises(tmp_path):
    state = lc.install(node_id="node-A", data_dir=tmp_path / "instance")
    state = lc.initialize(state)
    state, identity = lc.create_identity(state)
    state, record = lc.authorize_owner(state, identity, owner_id="alice", owner_token="tok-1")
    with pytest.raises(lc.LifecycleError):
        lc.apply_local_configuration(state, configuration={})


def test_mark_ready_before_local_configuration_raises(tmp_path):
    state = lc.install(node_id="node-A", data_dir=tmp_path / "instance")
    state = lc.initialize(state)
    state, identity = lc.create_identity(state)
    state, record = lc.authorize_owner(state, identity, owner_id="alice", owner_token="tok-1")
    kernel = EvidenceKernel(owner_instance=identity.public_key_hex)
    state = lc.seed_baseline_memory(state, kernel, starter_material=None)
    with pytest.raises(lc.LifecycleError):
        lc.mark_ready(state)


def test_peer_connection_before_ready_raises(tmp_path):
    state = lc.install(node_id="node-A", data_dir=tmp_path / "instance")
    with pytest.raises(lc.LifecycleError):
        lc.mark_peer_connected(state)


# ============================================================
# BASELINE MEMORY / STARTER MATERIAL LABELING
# ============================================================

def test_seed_with_no_starter_material_is_valid(tmp_path):
    state = lc.install(node_id="node-A", data_dir=tmp_path / "instance")
    state = lc.initialize(state)
    state, identity = lc.create_identity(state)
    state, record = lc.authorize_owner(state, identity, owner_id="alice", owner_token="tok-1")
    kernel = EvidenceKernel(owner_instance=identity.public_key_hex)
    state = lc.seed_baseline_memory(state, kernel, starter_material=None)
    assert state.baseline_memory_items == 0
    assert len(kernel.observations) == 0


@pytest.mark.parametrize("label,expected_class", [
    ("ARCHITECTURE", cp.IMPORTED_EXTERNAL_CONTENT),
    ("DOCUMENTATION", cp.IMPORTED_EXTERNAL_CONTENT),
    ("EXTERNAL_KNOWLEDGE", cp.IMPORTED_EXTERNAL_CONTENT),
    ("IMPORTED_CONTENT", cp.IMPORTED_EXTERNAL_CONTENT),
    ("EXAMPLE_DATA", cp.UNVERIFIED_CONTENT),
    ("VERIFIED_ARTIFACT", cp.VERIFIED_ARTIFACT),
    ("OWNER_PROVIDED_INFORMATION", cp.OWNER_ASSERTION),
])
def test_starter_material_label_maps_to_correct_provenance_class(tmp_path, label, expected_class):
    state = lc.install(node_id="node-A", data_dir=tmp_path / "instance")
    state = lc.initialize(state)
    state, identity = lc.create_identity(state)
    state, record = lc.authorize_owner(state, identity, owner_id="alice", owner_token="tok-1")
    kernel = EvidenceKernel(owner_instance=identity.public_key_hex)

    item = lc.StarterMaterialItem(label=label, content="some starter content", origin_id="source-x")
    state = lc.seed_baseline_memory(state, kernel, starter_material=[item])

    assert state.baseline_memory_items == 1
    [obs] = list(kernel.observations.values())
    tag = cp.read_tag(obs.metadata)
    assert tag is not None
    assert tag.source_class == expected_class
    assert tag.source_class != cp.FIRST_PARTY_OBSERVATION or expected_class == cp.FIRST_PARTY_OBSERVATION


def test_starter_material_unknown_label_rejected(tmp_path):
    state = lc.install(node_id="node-A", data_dir=tmp_path / "instance")
    state = lc.initialize(state)
    state, identity = lc.create_identity(state)
    state, record = lc.authorize_owner(state, identity, owner_id="alice", owner_token="tok-1")
    kernel = EvidenceKernel(owner_instance=identity.public_key_hex)

    item = lc.StarterMaterialItem(label="NOT_A_REAL_LABEL", content="x")
    with pytest.raises(lc.LifecycleError):
        lc.seed_baseline_memory(state, kernel, starter_material=[item])


def test_no_starter_material_label_is_ever_tagged_first_party_observation(tmp_path):
    """Explicit regression for the mission's core requirement: starter
    material must never be indistinguishable from the instance's own
    first-party observations."""
    for label in lc.STARTER_MATERIAL_LABELS:
        mapped_class = lc._STARTER_LABEL_TO_PROVENANCE_CLASS[label]
        assert mapped_class != cp.FIRST_PARTY_OBSERVATION


# ============================================================
# IDENTITY / OWNERSHIP INTEGRATION
# ============================================================

def test_create_identity_persists_real_key_material(tmp_path):
    state = lc.install(node_id="node-A", data_dir=tmp_path / "instance")
    state = lc.initialize(state)
    state, identity = lc.create_identity(state)

    identity_dir = tmp_path / "instance" / "identity" / "node-A"
    assert (identity_dir / "private_key.bin").exists()
    assert (identity_dir / "public_key.bin").exists()
    assert (identity_dir / "binding.json").exists()
    assert identity.node_id == "node-A"


def test_authorize_owner_rejects_mismatched_identity(tmp_path):
    from lantern import identity as idm

    state = lc.install(node_id="node-A", data_dir=tmp_path / "instance")
    state = lc.initialize(state)
    state, identity = lc.create_identity(state)

    other_identity = idm.load_or_create("node-B", tmp_path / "other")
    with pytest.raises(lc.LifecycleError):
        lc.authorize_owner(state, other_identity, owner_id="alice", owner_token="tok-1")


def test_ownership_history_is_persisted_and_verifiable(tmp_path):
    state = lc.install(node_id="node-A", data_dir=tmp_path / "instance")
    state = lc.initialize(state)
    state, identity = lc.create_identity(state)
    state, record = lc.authorize_owner(state, identity, owner_id="alice", owner_token="tok-1")

    loaded = own.load_history(state.ownership_history_path)
    assert loaded is not None
    assert loaded.verify_chain() is True
    assert loaded.current().owner_id == "alice"


# ============================================================
# PERSISTENCE
# ============================================================

def test_instance_state_save_load_round_trip(tmp_path):
    state, *_ = _run_to_ready(tmp_path)
    path = tmp_path / "instance_state.json"
    state.save(path)

    loaded = lc.InstanceState.load(path)
    assert loaded is not None
    assert loaded.stage == lc.STAGE_READY
    assert loaded.node_id == state.node_id
    assert loaded.identity_public_key == state.identity_public_key
    assert loaded.stage_history == state.stage_history


def test_instance_state_load_returns_none_when_missing(tmp_path):
    assert lc.InstanceState.load(tmp_path / "nope.json") is None


# ============================================================
# VERIFICATION HELPERS
# ============================================================

def test_has_reached_is_correct_along_the_way(tmp_path):
    state = lc.install(node_id="node-A", data_dir=tmp_path / "instance")
    assert lc.has_reached(state, lc.STAGE_INSTALLED) is True
    assert lc.has_reached(state, lc.STAGE_READY) is False

    state, *_ = _run_to_ready(tmp_path, node_id="node-B")
    assert lc.has_reached(state, lc.STAGE_INSTALLED) is True
    assert lc.has_reached(state, lc.STAGE_IDENTITY_CREATED) is True
    assert lc.has_reached(state, lc.STAGE_READY) is True


def test_has_reached_treats_peer_connected_as_at_or_past_ready(tmp_path):
    state, *_ = _run_to_ready(tmp_path)
    state = lc.mark_peer_connected(state)
    assert lc.has_reached(state, lc.STAGE_READY) is True
    assert lc.has_reached(state, lc.STAGE_LOCALLY_CONFIGURED) is True


def test_describe_produces_a_readable_summary(tmp_path):
    state, *_ = _run_to_ready(tmp_path)
    text = lc.describe(state)
    assert "node-A" in text
    assert lc.STAGE_READY in text
