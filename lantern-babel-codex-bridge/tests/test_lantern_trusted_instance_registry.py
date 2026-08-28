from __future__ import annotations

import pytest

from lantern import identity as idm
from lantern import instance_permissions as perms
from lantern import ownership as own
from lantern import trusted_instance_registry as reg
from lantern.core import EvidenceKernel
from lantern.portable_instance import (
    ImportValidationError,
    PortableInstance,
    export_instance,
    import_instance_with_registry,
)


# ============================================================
# Basic lifecycle
# ============================================================

def test_unknown_peer_has_no_trusted_state(tmp_path):
    registry = reg.TrustedInstanceRegistry(tmp_path / "registry")
    state = registry.prior_state("never-seen")
    assert state.trust_state == reg.TrustState.UNKNOWN
    assert state.has_trusted_state is False
    assert state.expected_public_key is None
    assert state.min_ownership_sequence == 0


def test_first_contact_is_recorded_but_not_trusted():
    """First contact must NOT be treated as trusted merely because it is
    internally self-consistent -- this is the TOFU limitation that must
    stay explicit, not silently upgraded to TRUSTED."""
    import tempfile
    d = tempfile.mkdtemp()
    registry = reg.TrustedInstanceRegistry(d)
    state = registry.check_and_record(
        node_id="peer-1", presented_public_key="key-1",
        presented_ownership_sequence=0, outcome="accepted",
    )
    assert state.trust_state == reg.TrustState.UNKNOWN
    assert state.has_trusted_state is True
    assert state.expected_public_key == "key-1"


def test_repeated_contact_with_same_key_advances_sequence(tmp_path):
    registry = reg.TrustedInstanceRegistry(tmp_path / "registry")
    registry.check_and_record(node_id="peer-1", presented_public_key="key-1", presented_ownership_sequence=0, outcome="accepted")
    state = registry.check_and_record(node_id="peer-1", presented_public_key="key-1", presented_ownership_sequence=1, outcome="accepted")
    assert state.min_ownership_sequence == 1
    assert state.expected_public_key == "key-1"


# ============================================================
# Collision detection (never silently overwrite conflicting identity)
# ============================================================

def test_key_collision_after_first_contact_is_detected_not_silently_accepted(tmp_path):
    registry = reg.TrustedInstanceRegistry(tmp_path / "registry")
    registry.check_and_record(node_id="peer-1", presented_public_key="key-1", presented_ownership_sequence=0, outcome="accepted")
    with pytest.raises(reg.CollisionError):
        registry.check_and_record(node_id="peer-1", presented_public_key="key-EVIL", presented_ownership_sequence=1, outcome="accepted")
    state = registry.prior_state("peer-1")
    assert state.trust_state == reg.TrustState.COLLISION_DETECTED
    assert state.expected_public_key == "key-1"  # original key still authoritative
    assert len(state.collisions) == 1
    assert state.collisions[0].presented_public_key == "key-EVIL"


def test_key_collision_after_explicit_enrollment_is_detected(tmp_path):
    registry = reg.TrustedInstanceRegistry(tmp_path / "registry")
    registry.enroll_peer("peer-1", "key-1", 0)
    with pytest.raises(reg.CollisionError):
        registry.check_and_record(node_id="peer-1", presented_public_key="key-EVIL", presented_ownership_sequence=1, outcome="accepted")
    state = registry.prior_state("peer-1")
    assert state.trust_state == reg.TrustState.COLLISION_DETECTED


def test_collision_does_not_erase_prior_contact_history(tmp_path):
    """Collisions must be recorded, not erased -- the full contact
    history (including pre-collision accepted contacts) must survive."""
    registry = reg.TrustedInstanceRegistry(tmp_path / "registry")
    registry.check_and_record(node_id="peer-1", presented_public_key="key-1", presented_ownership_sequence=0, outcome="accepted")
    registry.check_and_record(node_id="peer-1", presented_public_key="key-1", presented_ownership_sequence=1, outcome="accepted")
    with pytest.raises(reg.CollisionError):
        registry.check_and_record(node_id="peer-1", presented_public_key="key-EVIL", presented_ownership_sequence=2, outcome="accepted")
    state = registry.prior_state("peer-1")
    assert len(state.contact_history) == 3
    outcomes = [e.outcome for e in state.contact_history]
    assert outcomes == ["accepted", "accepted", "collision"]


def test_multiple_distinct_collisions_are_all_preserved(tmp_path):
    """A second, different colliding key must produce a second
    CollisionRecord rather than overwriting the first."""
    registry = reg.TrustedInstanceRegistry(tmp_path / "registry")
    registry.enroll_peer("peer-1", "key-1", 0)
    with pytest.raises(reg.CollisionError):
        registry.check_and_record(node_id="peer-1", presented_public_key="key-EVIL-A", presented_ownership_sequence=1, outcome="accepted")
    # Registry stays in COLLISION_DETECTED; a second distinct bad key attempt
    # must also be recorded as its own collision, not silently dropped.
    with pytest.raises(reg.CollisionError):
        registry.check_and_record(node_id="peer-1", presented_public_key="key-EVIL-B", presented_ownership_sequence=1, outcome="accepted")
    state = registry.prior_state("peer-1")
    assert len(state.collisions) == 2
    presented_keys = {c.presented_public_key for c in state.collisions}
    assert presented_keys == {"key-EVIL-A", "key-EVIL-B"}


# ============================================================
# Replay / sequence rollback (never silently move sequence backward)
# ============================================================

def test_sequence_rollback_is_rejected_as_replay(tmp_path):
    registry = reg.TrustedInstanceRegistry(tmp_path / "registry")
    registry.check_and_record(node_id="peer-1", presented_public_key="key-1", presented_ownership_sequence=0, outcome="accepted")
    registry.check_and_record(node_id="peer-1", presented_public_key="key-1", presented_ownership_sequence=3, outcome="accepted")
    with pytest.raises(reg.SequenceRollbackError):
        registry.check_and_record(node_id="peer-1", presented_public_key="key-1", presented_ownership_sequence=1, outcome="accepted")
    # Highest accepted sequence must remain unaffected by the rejected replay.
    state = registry.prior_state("peer-1")
    assert state.min_ownership_sequence == 3


def test_equal_sequence_is_accepted_not_treated_as_rollback(tmp_path):
    """Re-presenting the SAME sequence (e.g. a legitimate retry) must not
    be treated as a rollback -- only strictly lower sequences are replay."""
    registry = reg.TrustedInstanceRegistry(tmp_path / "registry")
    registry.check_and_record(node_id="peer-1", presented_public_key="key-1", presented_ownership_sequence=2, outcome="accepted")
    state = registry.check_and_record(node_id="peer-1", presented_public_key="key-1", presented_ownership_sequence=2, outcome="accepted")
    assert state.min_ownership_sequence == 2


def test_rejected_replay_is_still_recorded_in_history(tmp_path):
    registry = reg.TrustedInstanceRegistry(tmp_path / "registry")
    registry.check_and_record(node_id="peer-1", presented_public_key="key-1", presented_ownership_sequence=5, outcome="accepted")
    with pytest.raises(reg.SequenceRollbackError):
        registry.check_and_record(node_id="peer-1", presented_public_key="key-1", presented_ownership_sequence=1, outcome="accepted")
    state = registry.prior_state("peer-1")
    assert len(state.contact_history) == 2
    assert state.contact_history[-1].outcome == "rejected"
    assert "replay" in state.contact_history[-1].notes


# ============================================================
# Identity substitution (collision is the correct classification)
# ============================================================

def test_identity_substitution_after_trust_is_a_collision_not_a_silent_swap(tmp_path):
    """A node_id that was previously trusted with key A, later presenting
    key B, must never be silently re-trusted as key B -- this would be
    an unnoticed identity substitution."""
    registry = reg.TrustedInstanceRegistry(tmp_path / "registry")
    registry.enroll_peer("victim-node", "key-legit", 4)
    with pytest.raises(reg.CollisionError):
        registry.check_and_record(node_id="victim-node", presented_public_key="key-attacker", presented_ownership_sequence=5, outcome="accepted")
    state = registry.prior_state("victim-node")
    assert state.expected_public_key == "key-legit"  # not silently swapped
    assert state.trust_state == reg.TrustState.COLLISION_DETECTED


# ============================================================
# Enrollment
# ============================================================

def test_enroll_peer_moves_from_unknown_to_trusted(tmp_path):
    registry = reg.TrustedInstanceRegistry(tmp_path / "registry")
    state = registry.enroll_peer("peer-1", "key-1", 0)
    assert state.trust_state == reg.TrustState.TRUSTED
    assert state.expected_public_key == "key-1"


def test_enroll_peer_already_trusted_with_same_key_is_idempotent(tmp_path):
    registry = reg.TrustedInstanceRegistry(tmp_path / "registry")
    registry.enroll_peer("peer-1", "key-1", 0)
    state = registry.enroll_peer("peer-1", "key-1", 3)
    assert state.trust_state == reg.TrustState.TRUSTED
    assert state.min_ownership_sequence == 3


def test_enroll_peer_with_different_key_while_trusted_is_rejected(tmp_path):
    registry = reg.TrustedInstanceRegistry(tmp_path / "registry")
    registry.enroll_peer("peer-1", "key-1", 0)
    with pytest.raises(reg.CollisionError):
        registry.enroll_peer("peer-1", "key-DIFFERENT", 1)


def test_enroll_peer_while_collision_pending_is_rejected(tmp_path):
    registry = reg.TrustedInstanceRegistry(tmp_path / "registry")
    registry.enroll_peer("peer-1", "key-1", 0)
    with pytest.raises(reg.CollisionError):
        registry.check_and_record(node_id="peer-1", presented_public_key="key-EVIL", presented_ownership_sequence=1, outcome="accepted")
    with pytest.raises(reg.CollisionError):
        registry.enroll_peer("peer-1", "key-1", 2)


# ============================================================
# Collision resolution (forged / invalid resolution attempts)
# ============================================================

def test_resolve_collision_requires_collision_detected_state(tmp_path):
    """Attempting to 'resolve' a collision that doesn't exist must be
    rejected -- this is the forged-collision-resolution adversarial case."""
    registry = reg.TrustedInstanceRegistry(tmp_path / "registry")
    registry.enroll_peer("peer-1", "key-1", 0)
    with pytest.raises(reg.RegistryError):
        registry.resolve_collision(
            "peer-1", resolution="fabricated",
            resolved_public_key="key-ATTACKER",
            resolved_ownership_sequence=99,
        )
    # State must remain untouched by the rejected forged resolution.
    state = registry.prior_state("peer-1")
    assert state.trust_state == reg.TrustState.TRUSTED
    assert state.expected_public_key == "key-1"


def test_resolve_collision_on_unknown_node_id_is_rejected(tmp_path):
    registry = reg.TrustedInstanceRegistry(tmp_path / "registry")
    with pytest.raises(reg.RegistryError):
        registry.resolve_collision(
            "never-contacted", resolution="fabricated",
            resolved_public_key="key-X", resolved_ownership_sequence=1,
        )


def test_resolve_collision_succeeds_and_preserves_collision_record(tmp_path):
    registry = reg.TrustedInstanceRegistry(tmp_path / "registry")
    registry.enroll_peer("peer-1", "key-1", 0)
    with pytest.raises(reg.CollisionError):
        registry.check_and_record(node_id="peer-1", presented_public_key="key-2", presented_ownership_sequence=1, outcome="accepted")

    state = registry.resolve_collision(
        "peer-1", resolution="key_rotation_confirmed_out_of_band",
        resolved_public_key="key-2", resolved_ownership_sequence=1,
        notes="operator verified via phone call",
    )
    assert state.trust_state == reg.TrustState.RESOLVED
    assert state.expected_public_key == "key-2"
    assert state.min_ownership_sequence == 1
    # The collision record itself must NOT be erased -- it should carry
    # the resolution metadata, preserving full audit history.
    assert len(state.collisions) == 1
    assert state.collisions[0].resolution == "key_rotation_confirmed_out_of_band"
    assert state.collisions[0].presented_public_key == "key-2"
    assert state.collisions[0].trusted_public_key == "key-1"


def test_resolve_collision_twice_is_rejected_second_time(tmp_path):
    """Once resolved, state moves to RESOLVED -- attempting to resolve
    again (no active collision) must fail, preventing a forged replay of
    the resolution action itself."""
    registry = reg.TrustedInstanceRegistry(tmp_path / "registry")
    registry.enroll_peer("peer-1", "key-1", 0)
    with pytest.raises(reg.CollisionError):
        registry.check_and_record(node_id="peer-1", presented_public_key="key-2", presented_ownership_sequence=1, outcome="accepted")
    registry.resolve_collision("peer-1", resolution="ok", resolved_public_key="key-2", resolved_ownership_sequence=1)
    with pytest.raises(reg.RegistryError):
        registry.resolve_collision("peer-1", resolution="again", resolved_public_key="key-3", resolved_ownership_sequence=2)


def test_new_collision_after_resolution_is_recorded_independently(tmp_path):
    """After a resolution, a NEW distinct collision must be detected and
    recorded as its own event, not conflated with the resolved one."""
    registry = reg.TrustedInstanceRegistry(tmp_path / "registry")
    registry.enroll_peer("peer-1", "key-1", 0)
    with pytest.raises(reg.CollisionError):
        registry.check_and_record(node_id="peer-1", presented_public_key="key-2", presented_ownership_sequence=1, outcome="accepted")
    registry.resolve_collision("peer-1", resolution="ok", resolved_public_key="key-2", resolved_ownership_sequence=1)

    with pytest.raises(reg.CollisionError):
        registry.check_and_record(node_id="peer-1", presented_public_key="key-3", presented_ownership_sequence=2, outcome="accepted")

    state = registry.prior_state("peer-1")
    assert len(state.collisions) == 2
    assert state.collisions[0].resolution == "ok"
    assert state.collisions[1].resolution is None  # newest collision still unresolved


# ============================================================
# Persistence across restart
# ============================================================

def test_registry_state_persists_across_reload(tmp_path):
    path = tmp_path / "registry"
    reg1 = reg.TrustedInstanceRegistry(path)
    reg1.enroll_peer("peer-1", "key-1", 3)

    reg2 = reg.TrustedInstanceRegistry(path)  # simulate restart: fresh instance, same data_dir
    state = reg2.prior_state("peer-1")
    assert state.trust_state == reg.TrustState.TRUSTED
    assert state.expected_public_key == "key-1"
    assert state.min_ownership_sequence == 3


def test_collision_history_persists_across_reload(tmp_path):
    path = tmp_path / "registry"
    reg1 = reg.TrustedInstanceRegistry(path)
    reg1.enroll_peer("peer-1", "key-1", 0)
    with pytest.raises(reg.CollisionError):
        reg1.check_and_record(node_id="peer-1", presented_public_key="key-EVIL", presented_ownership_sequence=1, outcome="accepted")

    reg2 = reg.TrustedInstanceRegistry(path)
    state = reg2.prior_state("peer-1")
    assert state.trust_state == reg.TrustState.COLLISION_DETECTED
    assert len(state.collisions) == 1
    assert state.collisions[0].presented_public_key == "key-EVIL"


def test_sequence_floor_persists_and_still_rejects_replay_after_reload(tmp_path):
    path = tmp_path / "registry"
    reg1 = reg.TrustedInstanceRegistry(path)
    reg1.check_and_record(node_id="peer-1", presented_public_key="key-1", presented_ownership_sequence=7, outcome="accepted")

    reg2 = reg.TrustedInstanceRegistry(path)
    with pytest.raises(reg.SequenceRollbackError):
        reg2.check_and_record(node_id="peer-1", presented_public_key="key-1", presented_ownership_sequence=2, outcome="accepted")


def test_malformed_registry_file_on_disk_is_treated_as_no_prior_state(tmp_path):
    """A corrupted registry.json must not crash the registry or be
    silently trusted -- it should be treated as if no prior state exists
    (equivalent to first contact), never as an authorization bypass."""
    path = tmp_path / "registry"
    peer_dir = path / "peers" / "peer-1"
    peer_dir.mkdir(parents=True)
    (peer_dir / "registry.json").write_text("{not valid json")

    registry = reg.TrustedInstanceRegistry(path)
    state = registry.prior_state("peer-1")
    assert state.trust_state == reg.TrustState.UNKNOWN
    assert state.has_trusted_state is False


def test_registry_file_with_mismatched_node_id_is_rejected(tmp_path):
    """A registry.json under peers/peer-1/ that internally claims a
    different node_id must not be trusted for peer-1 -- defends against
    a copy/rename-based substitution attack on the on-disk files."""
    import json as jsonlib
    path = tmp_path / "registry"
    peer_dir = path / "peers" / "peer-1"
    peer_dir.mkdir(parents=True)
    forged = {
        "node_id": "peer-DIFFERENT",
        "trust_state": "trusted",
        "trusted_public_key": "key-ATTACKER",
        "highest_accepted_sequence": 99,
        "first_contact_at": None,
        "last_contact_at": None,
        "collisions": [],
        "contact_history": [],
    }
    (peer_dir / "registry.json").write_text(jsonlib.dumps(forged))

    registry = reg.TrustedInstanceRegistry(path)
    state = registry.prior_state("peer-1")
    assert state.trust_state == reg.TrustState.UNKNOWN
    assert state.has_trusted_state is False


# ============================================================
# Cross-instance leakage
# ============================================================

def test_two_registries_at_different_data_dirs_are_fully_isolated(tmp_path):
    dir_a = tmp_path / "instance-a"
    dir_b = tmp_path / "instance-b"
    reg_a = reg.TrustedInstanceRegistry(dir_a)
    reg_b = reg.TrustedInstanceRegistry(dir_b)

    reg_a.enroll_peer("shared-peer-id", "key-seen-by-a", 5)

    state_from_b = reg_b.prior_state("shared-peer-id")
    assert state_from_b.trust_state == reg.TrustState.UNKNOWN
    assert state_from_b.has_trusted_state is False
    assert state_from_b.min_ownership_sequence == 0

    # And instance A's state must be untouched by B's independent read.
    state_from_a = reg_a.prior_state("shared-peer-id")
    assert state_from_a.expected_public_key == "key-seen-by-a"


def test_all_peers_only_lists_peers_under_this_instances_data_dir(tmp_path):
    dir_a = tmp_path / "instance-a"
    dir_b = tmp_path / "instance-b"
    reg_a = reg.TrustedInstanceRegistry(dir_a)
    reg_b = reg.TrustedInstanceRegistry(dir_b)
    reg_a.enroll_peer("peer-x", "key-x", 0)
    reg_a.enroll_peer("peer-y", "key-y", 0)
    reg_b.enroll_peer("peer-z", "key-z", 0)

    node_ids_a = {s.node_id for s in reg_a.all_peers()}
    node_ids_b = {s.node_id for s in reg_b.all_peers()}
    assert node_ids_a == {"peer-x", "peer-y"}
    assert node_ids_b == {"peer-z"}


# ============================================================
# Concurrent / conflicting contact events
# ============================================================

def test_concurrent_conflicting_contacts_first_wins_second_is_collision(tmp_path):
    """Two 'simultaneous' contact events presenting different keys for
    the same node_id: whichever is processed first establishes trust;
    the second must be flagged as a collision, never silently merged or
    silently overwritten."""
    registry = reg.TrustedInstanceRegistry(tmp_path / "registry")
    registry.check_and_record(node_id="peer-1", presented_public_key="key-first", presented_ownership_sequence=0, outcome="accepted")
    with pytest.raises(reg.CollisionError):
        registry.check_and_record(node_id="peer-1", presented_public_key="key-second", presented_ownership_sequence=0, outcome="accepted")
    state = registry.prior_state("peer-1")
    assert state.expected_public_key == "key-first"
    assert state.trust_state == reg.TrustState.COLLISION_DETECTED


def test_active_collisions_and_all_peers_reflect_registry_wide_queries(tmp_path):
    registry = reg.TrustedInstanceRegistry(tmp_path / "registry")
    registry.enroll_peer("peer-clean", "key-clean", 0)
    registry.enroll_peer("peer-colliding", "key-1", 0)
    with pytest.raises(reg.CollisionError):
        registry.check_and_record(node_id="peer-colliding", presented_public_key="key-2", presented_ownership_sequence=1, outcome="accepted")

    collisions = registry.active_collisions()
    assert {s.node_id for s in collisions} == {"peer-colliding"}
    all_ids = {s.node_id for s in registry.all_peers()}
    assert all_ids == {"peer-clean", "peer-colliding"}


# ============================================================
# Integration with Phase B: import_instance_with_registry
# ============================================================

def _make_portable(node_id, owner_id, owner_token, data_dir, sequence_transfers=None):
    identity = idm.load_or_create(node_id, data_dir)
    record = own.create_initial_ownership(identity, owner_id=owner_id, owner_token=owner_token)
    history_records = [record]
    if sequence_transfers:
        current = record
        for new_owner, new_token, cur_token in sequence_transfers:
            current = own.transfer_ownership(current, identity, current_owner_token=cur_token, new_owner_id=new_owner, new_owner_token=new_token)
            history_records.append(current)
    kernel = EvidenceKernel(owner_instance=identity.public_key_hex)
    grant = perms.create_capability_grant(identity, history_records[-1], owner_token=(sequence_transfers[-1][1] if sequence_transfers else owner_token), capabilities=[perms.MEMORY_READ, perms.EXPORT_STATE])
    portable = PortableInstance(
        identity=identity,
        ownership_history=own.OwnershipHistory(history_records),
        kernel=kernel,
        configuration={},
        capability_grant=grant,
    )
    return identity, portable


def test_import_with_registry_first_contact_has_no_pinning(tmp_path):
    """First contact via the registry-aware wrapper must behave like a
    plain import_instance() call with no pinning -- the TOFU limitation
    stays explicit rather than being hidden by a false sense of safety."""
    identity, portable = _make_portable("node-fresh", "alice", "tok-a", tmp_path / "real")
    payload = export_instance(portable)

    registry = reg.TrustedInstanceRegistry(tmp_path / "registry")
    imported = import_instance_with_registry(payload, registry, expected_node_id="node-fresh")
    assert imported.identity.public_key_hex == identity.public_key_hex

    state = registry.prior_state("node-fresh")
    assert state.expected_public_key == identity.public_key_hex
    assert state.min_ownership_sequence == 0


def test_import_with_registry_rejects_spoofed_identity_on_second_import(tmp_path):
    """This is the exact bypass found and fixed manually in Phase B
    (test_spoofed_identity_with_different_key_but_same_node_id_is_rejected_when_pinned)
    -- but here the pinning must be AUTOMATIC via the registry rather
    than requiring the caller to remember to pass expected_public_key."""
    real_identity, real_portable = _make_portable("node-real", "alice", "tok-a", tmp_path / "real")
    real_payload = export_instance(real_portable)

    registry = reg.TrustedInstanceRegistry(tmp_path / "registry")
    import_instance_with_registry(real_payload, registry, expected_node_id="node-real")

    fake_identity, fake_portable = _make_portable("node-real", "mallory", "fake-tok", tmp_path / "fake")
    fake_payload = export_instance(fake_portable)

    # Caller does NOT pass expected_public_key manually -- the registry
    # supplies it automatically because prior trusted state exists.
    # The registry's own collision check runs first, so this raises
    # CollisionError (not ImportValidationError) -- and the collision is
    # recorded.
    with pytest.raises(reg.CollisionError):
        import_instance_with_registry(fake_payload, registry, expected_node_id="node-real")

    # And the registry itself must have recorded the collision.
    state = registry.prior_state("node-real")
    assert state.trust_state == reg.TrustState.COLLISION_DETECTED
    assert len(state.collisions) == 1


def test_import_with_registry_rejects_replayed_stale_export_automatically(tmp_path):
    """Mirrors test_replayed_stale_ownership_export_is_rejected_when_sequence_is_known
    from Phase B, but the sequence floor must be supplied automatically
    by the registry rather than requiring the caller to track it."""
    identity = idm.load_or_create("node-replay-2", tmp_path / "real")
    r0 = own.create_initial_ownership(identity, owner_id="alice", owner_token="tok-a")
    r1 = own.transfer_ownership(r0, identity, current_owner_token="tok-a", new_owner_id="bob", new_owner_token="tok-b")
    kernel = EvidenceKernel(owner_instance=identity.public_key_hex)
    old_history = own.OwnershipHistory([r0, r1])
    grant = perms.create_capability_grant(identity, r1, owner_token="tok-b", capabilities=[perms.MEMORY_READ, perms.EXPORT_STATE])
    old_portable = PortableInstance(identity=identity, ownership_history=old_history, kernel=kernel, configuration={}, capability_grant=grant)
    stale_payload = export_instance(old_portable)

    registry = reg.TrustedInstanceRegistry(tmp_path / "registry")
    # First import establishes prior state at sequence 1 (bob).
    import_instance_with_registry(stale_payload, registry, expected_node_id="node-replay-2")

    # Legitimate further transfer to carol happens; the registry only
    # learns about it via a fresh accepted import at sequence 2.
    r2 = own.transfer_ownership(r1, identity, current_owner_token="tok-b", new_owner_id="carol", new_owner_token="tok-c")
    new_history = own.OwnershipHistory([r0, r1, r2])
    grant2 = perms.create_capability_grant(identity, r2, owner_token="tok-c", capabilities=[perms.MEMORY_READ, perms.EXPORT_STATE])
    new_portable = PortableInstance(identity=identity, ownership_history=new_history, kernel=kernel, configuration={}, capability_grant=grant2)
    new_payload = export_instance(new_portable)
    import_instance_with_registry(new_payload, registry, expected_node_id="node-replay-2")

    state = registry.prior_state("node-replay-2")
    assert state.min_ownership_sequence == 2

    # Now replay the OLD (sequence 1) export -- must be rejected
    # automatically, without the caller passing min_ownership_sequence.
    # The registry's sequence-rollback check runs first.
    with pytest.raises(reg.SequenceRollbackError):
        import_instance_with_registry(stale_payload, registry, expected_node_id="node-replay-2")


def test_import_with_registry_accepts_legitimate_key_rotation_via_resolution(tmp_path):
    """After a genuine key rotation is explicitly resolved in the
    registry, subsequent imports with the NEW key must succeed --
    resolution must not be a permanent lockout."""
    old_identity, old_portable = _make_portable("node-rotate", "alice", "tok-a", tmp_path / "old")
    old_payload = export_instance(old_portable)

    registry = reg.TrustedInstanceRegistry(tmp_path / "registry")
    import_instance_with_registry(old_payload, registry, expected_node_id="node-rotate")

    new_identity, new_portable = _make_portable("node-rotate", "alice", "tok-a2", tmp_path / "new")
    new_payload = export_instance(new_portable)

    with pytest.raises(reg.CollisionError):
        import_instance_with_registry(new_payload, registry, expected_node_id="node-rotate")

    registry.resolve_collision(
        "node-rotate", resolution="key_rotation_confirmed",
        resolved_public_key=new_identity.public_key_hex,
        resolved_ownership_sequence=0,
    )

    imported = import_instance_with_registry(new_payload, registry, expected_node_id="node-rotate")
    assert imported.identity.public_key_hex == new_identity.public_key_hex


# ============================================================
# Adversarial: node_id used as a filesystem path segment
# ============================================================

@pytest.mark.parametrize("malicious_node_id", [
    "../../etc/passwd",
    "..",
    ".",
    "peer/../../escape",
    "/etc/passwd",
    "peer\\..\\..\\escape",
    "",
    "   ",
    "peer\x00null",
])
def test_malicious_node_id_cannot_escape_registry_directory(tmp_path, malicious_node_id):
    """node_id is caller-supplied and untrusted. Before this fix, a
    node_id like "../../etc/passwd" would be interpolated directly into
    a filesystem path, letting a caller read/write registry.json files
    OUTSIDE the registry's own data_dir -- a path traversal bypass of
    instance-scoping. Every variant here must be rejected, not silently
    sanitized or truncated."""
    registry = reg.TrustedInstanceRegistry(tmp_path / "registry")
    with pytest.raises(reg.RegistryError):
        registry.enroll_peer(malicious_node_id, "key-x", 0)
    # And confirm nothing was actually written outside the registry dir
    # (scoped to this test's own tmp_path, not the whole pytest tmp root).
    base = (tmp_path / "registry").resolve()
    for path in tmp_path.rglob("registry.json"):
        assert base in path.resolve().parents, f"registry.json escaped to {path}"


def test_valid_node_id_with_safe_special_characters_still_works(tmp_path):
    """The path-traversal fix must not be so strict it breaks legitimate
    node_ids that merely contain dashes, underscores, or dots (but not
    path separators or traversal sequences)."""
    registry = reg.TrustedInstanceRegistry(tmp_path / "registry")
    state = registry.enroll_peer("lantern-field-experiment-1", "key-1", 0)
    assert state.trust_state == reg.TrustState.TRUSTED
    state2 = registry.enroll_peer("node.with.dots_and-dashes", "key-2", 0)
    assert state2.trust_state == reg.TrustState.TRUSTED


# ============================================================
# Documented limitation: in-memory cache staleness across concurrent
# registry instances sharing the same data_dir within one process
# ============================================================

def test_in_memory_cache_is_stale_until_explicit_reload_known_limitation(tmp_path):
    """Two TrustedInstanceRegistry objects pointed at the SAME data_dir
    within the same process do not automatically see each other's
    writes once a peer has been cached in memory -- this is a documented
    limitation, not a silent correctness bug: call reload() to pick up
    externally-written state. This test pins the behavior so a future
    change either preserves it deliberately or updates this test with a
    stated reason."""
    path = tmp_path / "registry"
    reg_a = reg.TrustedInstanceRegistry(path)
    reg_b = reg.TrustedInstanceRegistry(path)

    # reg_b caches peer-x as UNKNOWN (never contacted) before reg_a enrolls it.
    initial = reg_b.prior_state("peer-x")
    assert initial.has_trusted_state is False

    reg_a.enroll_peer("peer-x", "key-x", 0)

    stale = reg_b.prior_state("peer-x")
    assert stale.has_trusted_state is False  # stale cached view

    reg_b.reload()
    fresh = reg_b.prior_state("peer-x")
    assert fresh.has_trusted_state is True
    assert fresh.expected_public_key == "key-x"


def test_resolve_collision_does_not_itself_authenticate_the_caller_documented_limitation(tmp_path):
    """resolve_collision() is an operator-decision RECORDER, not a
    verifier: it enforces the legal state transition (only
    COLLISION_DETECTED -> RESOLVED, collision history always preserved)
    but has no independent way to confirm the resolution is authentic.
    This mirrors content_provenance.promote_to_first_party()'s design --
    authentication is the caller's responsibility. This test documents
    that boundary explicitly rather than silently assuming it is closed:
    any caller with access to the registry object CAN resolve a
    collision in an attacker's favor if the calling application does not
    itself verify the resolution out-of-band before invoking this
    method. Anything that exposes resolve_collision() to network input
    must add its own authentication layer in front of it."""
    registry = reg.TrustedInstanceRegistry(tmp_path / "registry")
    registry.enroll_peer("victim", "key-real", 0)
    with pytest.raises(reg.CollisionError):
        registry.check_and_record(node_id="victim", presented_public_key="key-attacker", presented_ownership_sequence=1, outcome="accepted")

    # No cryptographic proof is required here -- this call succeeds
    # purely because the caller is allowed to invoke it at all.
    state = registry.resolve_collision(
        "victim", resolution="unverified_claim",
        resolved_public_key="key-attacker", resolved_ownership_sequence=1,
    )
    assert state.expected_public_key == "key-attacker"
    # But the full collision record -- including the ORIGINAL trusted key
    # -- is preserved regardless, so this action is always auditable
    # after the fact even though it wasn't prevented in the moment.
    assert state.collisions[0].trusted_public_key == "key-real"
    assert state.collisions[0].presented_public_key == "key-attacker"
    assert state.collisions[0].resolution == "unverified_claim"
