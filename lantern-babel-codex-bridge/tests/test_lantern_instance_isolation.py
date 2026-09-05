from __future__ import annotations

import copy
import dataclasses

import pytest

from lantern import content_provenance as cp
from lantern import identity as idm
from lantern import instance_lifecycle as lc
from lantern import ownership as own
from lantern.core import EvidenceKernel, Lantern, Observation


@pytest.fixture
def identity_a(tmp_path):
    return idm.load_or_create("node-A", tmp_path / "identity-A")


@pytest.fixture
def identity_b(tmp_path):
    return idm.load_or_create("node-B", tmp_path / "identity-B")


def _ready_instance(tmp_path, node_id, owner_id, token):
    state = lc.install(node_id=node_id, data_dir=tmp_path / node_id)
    state = lc.initialize(state)
    state, identity = lc.create_identity(state)
    state, record = lc.authorize_owner(state, identity, owner_id=owner_id, owner_token=token)
    kernel = EvidenceKernel(owner_instance=identity.public_key_hex)
    state = lc.seed_baseline_memory(state, kernel, starter_material=None)
    state = lc.apply_local_configuration(state, configuration={})
    state = lc.mark_ready(state)
    return state, identity, record, kernel


def test_same_process_two_kernels_remain_isolated(tmp_path):
    _, identity_a, _, kernel_a = _ready_instance(tmp_path, "node-A", "alice", "tok-a")
    _, identity_b, _, kernel_b = _ready_instance(tmp_path, "node-B", "bob", "tok-b")

    obs_a = kernel_a.observe("A private fact", "local", 0.9)
    ev_a, _ = kernel_a.add_evidence("fact", obs_a.id, 1.0, 1)

    obs_b = kernel_b.observe("B private fact", "local", 0.9)
    ev_b, _ = kernel_b.add_evidence("fact", obs_b.id, 1.0, 1)

    assert obs_a.id in kernel_a.observations
    assert obs_a.id not in kernel_b.observations
    assert obs_b.id in kernel_b.observations
    assert obs_b.id not in kernel_a.observations
    assert all(e.owner_instance == identity_a.public_key_hex for e in kernel_a.evidence)
    assert all(e.owner_instance == identity_b.public_key_hex for e in kernel_b.evidence)
    assert ev_a.id != ev_b.id


def test_cross_instance_read_fails_by_state_boundary(tmp_path):
    _, identity_a, _, kernel_a = _ready_instance(tmp_path, "node-A", "alice", "tok-a")
    _, identity_b, _, kernel_b = _ready_instance(tmp_path, "node-B", "bob", "tok-b")

    obs_a = kernel_a.observe("A private fact", "local", 0.9)
    imported = dataclasses.replace(copy.deepcopy(obs_a), owner_instance=identity_a.public_key_hex)
    with pytest.raises(own.PermissionError if hasattr(own, "PermissionError") else PermissionError):
        kernel_b.observations[imported.id] = imported


def test_cross_instance_write_fails_by_state_boundary(tmp_path):
    _, identity_a, _, kernel_a = _ready_instance(tmp_path, "node-A", "alice", "tok-a")
    _, identity_b, _, kernel_b = _ready_instance(tmp_path, "node-B", "bob", "tok-b")

    obs_a = kernel_a.observe("A private fact", "local", 0.9)
    foreign = dataclasses.replace(obs_a, owner_instance=identity_a.public_key_hex)
    with pytest.raises(Exception):
        kernel_b.observations[obs_a.id] = foreign


def test_cross_instance_mutation_fails_via_resolution_boundary(tmp_path):
    _, _, _, kernel_a = _ready_instance(tmp_path, "node-A", "alice", "tok-a")
    _, identity_b, _, kernel_b = _ready_instance(tmp_path, "node-B", "bob", "tok-b")

    pos = kernel_a.observe("true", "local", 1.0)
    neg = kernel_a.observe("false", "local", 1.0)
    kernel_a.add_evidence("claim", pos.id, 1.0, 1)
    _, contradiction = kernel_a.add_evidence("claim", neg.id, 1.0, -1)

    with pytest.raises(Exception):
        kernel_b.contradictions.append(dataclasses.replace(contradiction, owner_instance=kernel_a.owner_instance))


def test_cross_instance_deletion_not_exposed_and_enumeration_is_scoped(tmp_path):
    _, _, _, kernel_a = _ready_instance(tmp_path, "node-A", "alice", "tok-a")
    _, identity_b, _, kernel_b = _ready_instance(tmp_path, "node-B", "bob", "tok-b")

    obs_a = kernel_a.observe("A private fact", "local", 0.9)
    with pytest.raises(Exception):
        kernel_b.observations[obs_a.id] = dataclasses.replace(obs_a, owner_instance=kernel_a.owner_instance)

    snap_b = kernel_b.snapshot()
    assert all(o["owner_instance"] == identity_b.public_key_hex for o in snap_b["observations"])
    assert obs_a.id not in [o["id"] for o in snap_b["observations"]]
    assert not hasattr(kernel_b, "delete_observation")


def test_shared_mutable_metadata_does_not_leak_across_observation_copies(tmp_path):
    _, _, _, kernel_a = _ready_instance(tmp_path, "node-A", "alice", "tok-a")
    metadata = {"nested": {"x": 1}}
    obs = kernel_a.observe("fact", "local", 0.9, metadata=metadata)

    clone = copy.deepcopy(obs)
    # With immutable Observation (frozen dataclass + MappingProxyType metadata),
    # direct mutation of metadata is blocked at the language level.
    import pytest as _pytest
    with _pytest.raises(TypeError):
        clone.metadata["nested"] = {"x": 2}

    # Original metadata is still intact — no leak across copies.
    assert kernel_a.observations[obs.id].metadata["nested"] == {"x": 1}


def test_snapshot_and_restore_preserve_owner_boundary(tmp_path):
    _, identity_a, _, kernel_a = _ready_instance(tmp_path, "node-A", "alice", "tok-a")
    obs_a = kernel_a.observe("A private fact", "local", 0.9)
    kernel_a.add_evidence("fact", obs_a.id, 1.0, 1)

    snapshot = kernel_a.snapshot()
    restored = EvidenceKernel.restore(snapshot)

    assert restored.owner_instance == identity_a.public_key_hex
    assert set(restored.observations.keys()) == {obs_a.id}
    assert all(e.owner_instance == identity_a.public_key_hex for e in restored.evidence)


def test_tampered_snapshot_with_foreign_owner_is_filtered_on_restore(tmp_path):
    _, identity_a, _, kernel_a = _ready_instance(tmp_path, "node-A", "alice", "tok-a")
    obs_a = kernel_a.observe("A private fact", "local", 0.9)
    snapshot = kernel_a.snapshot()
    snapshot["observations"].append(
        {
            "id": "foreign-obs",
            "content": "foreign",
            "source": "peer",
            "reliability": 0.5,
            "step": 1,
            "owner_instance": "forged-owner",
            "metadata": {},
        }
    )

    restored = EvidenceKernel.restore(snapshot)
    assert restored.owner_instance == identity_a.public_key_hex
    assert "foreign-obs" not in restored.observations


def test_lantern_snapshot_same_process_isolation_survives_restart(tmp_path):
    chronicle_a = tmp_path / "a.jsonl"
    chronicle_b = tmp_path / "b.jsonl"
    lantern_a = Lantern(chronicle_filename=chronicle_a, owner_instance="owner-A")
    lantern_b = Lantern(chronicle_filename=chronicle_b, owner_instance="owner-B")

    obs_a = lantern_a.observe("A private fact", "local", 0.9)
    lantern_a.add_evidence("fact", obs_a.id, 1.0, 1)
    obs_b = lantern_b.observe("B private fact", "local", 0.9)
    lantern_b.add_evidence("fact", obs_b.id, 1.0, 1)

    lantern_a.save_snapshot()
    lantern_b.save_snapshot()

    restarted_a = Lantern(chronicle_filename=chronicle_a, owner_instance="owner-A")
    restarted_b = Lantern(chronicle_filename=chronicle_b, owner_instance="owner-B")
    restarted_a.startup()
    restarted_b.startup()

    assert obs_a.id in restarted_a.kernel.observations
    assert obs_a.id not in restarted_b.kernel.observations
    assert obs_b.id in restarted_b.kernel.observations
    assert obs_b.id not in restarted_a.kernel.observations


def test_peer_content_remains_external_when_passed_between_instances(tmp_path):
    _, identity_a, _, kernel_a = _ready_instance(tmp_path, "node-A", "alice", "tok-a")
    _, identity_b, _, kernel_b = _ready_instance(tmp_path, "node-B", "bob", "tok-b")

    obs_a = kernel_a.observe(
        "A says hello",
        "local",
        0.9,
        metadata=cp.tag_metadata(cp.ContentProvenanceTag(cp.FIRST_PARTY_OBSERVATION, origin_id="")),
    )

    imported_metadata = cp.tag_metadata(
        cp.ContentProvenanceTag(cp.PEER_CONTENT, origin_id=identity_a.public_key_hex)
    )
    obs_b = kernel_b.observe(obs_a.content, source="peer", reliability=0.5, metadata=imported_metadata)

    tag = cp.read_tag(obs_b.metadata)
    assert tag is not None
    assert tag.source_class == cp.PEER_CONTENT
    assert tag.source_class != cp.FIRST_PARTY_OBSERVATION


def test_unauthorized_promotion_still_fails_for_peer_content(tmp_path):
    _, identity_b, _, kernel_b = _ready_instance(tmp_path, "node-B", "bob", "tok-b")
    obs_b = kernel_b.observe(
        "imported claim",
        "peer",
        0.5,
        metadata=cp.tag_metadata(cp.ContentProvenanceTag(cp.PEER_CONTENT, origin_id="peer-A")),
    )
    tag = cp.read_tag(obs_b.metadata)
    with pytest.raises(cp.ContentProvenanceError):
        cp.promote_to_first_party(tag, cp.PromotionEvidence())


def test_legitimate_ownership_transfer_remains_distinct_from_peer_sharing(tmp_path):
    identity = idm.load_or_create("node-A", tmp_path / "identity")
    initial = own.create_initial_ownership(identity, owner_id="alice", owner_token="tok-a")
    transferred = own.transfer_ownership(initial, identity, current_owner_token="tok-a", new_owner_id="bob", new_owner_token="tok-b")
    assert transferred.owner_id == "bob"
    assert own.verify_ownership_record(transferred) is True

    tag = cp.ContentProvenanceTag(cp.PEER_CONTENT, origin_id=identity.public_key_hex)
    promoted = cp.promote_to_first_party(
        tag,
        cp.PromotionEvidence(ownership_transfer_record_signature=transferred.signature),
    )
    assert promoted.source_class == cp.FIRST_PARTY_OBSERVATION


def test_forged_instance_identity_cannot_restore_foreign_state(tmp_path):
    _, identity_a, _, kernel_a = _ready_instance(tmp_path, "node-A", "alice", "tok-a")
    obs_a = kernel_a.observe("A private fact", "local", 0.9)
    snapshot = kernel_a.snapshot()
    snapshot["owner_instance"] = "forged-owner"

    restored = EvidenceKernel.restore(snapshot)
    assert restored.owner_instance == "forged-owner"
    assert restored.observations == {}


def test_malformed_state_missing_owner_instance_is_rejected_from_cross_instance_use(tmp_path):
    _, _, _, kernel_a = _ready_instance(tmp_path, "node-A", "alice", "tok-a")
    malformed = Observation(content="x", source="peer", reliability=0.1, step=1, owner_instance="")
    with pytest.raises(Exception):
        kernel_a.observations[malformed.id] = malformed
