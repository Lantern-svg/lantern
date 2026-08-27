from __future__ import annotations

import hashlib
import json

import pytest

from lantern import content_provenance as cp
from lantern import identity as idm
from lantern import instance_lifecycle as lc
from lantern import instance_permissions as perms
from lantern import ownership as own
from lantern.core import EvidenceKernel
from lantern.portable_instance import (
    ImportValidationError,
    PortableInstance,
    export_instance,
    import_instance,
)


@pytest.fixture
def ready_instance(tmp_path):
    state = lc.install(node_id="node-A", data_dir=tmp_path / "node-A")
    state = lc.initialize(state)
    state, identity = lc.create_identity(state)
    state, ownership = lc.authorize_owner(state, identity, owner_id="alice", owner_token="token-a")
    kernel = EvidenceKernel(owner_instance=identity.public_key_hex)
    state = lc.seed_baseline_memory(
        state,
        kernel,
        starter_material=[lc.StarterMaterialItem(label="OWNER_PROVIDED_INFORMATION", content="starter", origin_id="owner:alice")],
    )
    state = lc.apply_local_configuration(state, configuration={"mode": "portable"})
    state = lc.mark_ready(state)
    return state, identity, ownership, kernel


def _grant(identity, ownership, *capabilities):
    return perms.create_capability_grant(identity, ownership, owner_token="token-a", capabilities=list(capabilities))


def _portable(identity, history, kernel, ownership, config=None, grant_caps=(perms.MEMORY_READ, perms.EXPORT_STATE)):
    grant = perms.create_capability_grant(identity, ownership, owner_token="token-a", capabilities=list(grant_caps))
    return PortableInstance(
        identity=identity,
        ownership_history=history,
        kernel=kernel,
        configuration=config or {"mode": "portable"},
        capability_grant=grant,
    )


def _rehash(payload: dict) -> dict:
    payload["export_hash"] = hashlib.sha256(
        json.dumps({k: v for k, v in payload.items() if k != "export_hash"}, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return payload


def test_capability_boundary_requires_explicit_grant(ready_instance):
    _, identity, ownership, kernel = ready_instance
    history = own.OwnershipHistory([ownership])
    instance = PortableInstance(identity=identity, ownership_history=history, kernel=kernel, configuration={})
    with pytest.raises(perms.PermissionDenied):
        instance.boundary().require(perms.MEMORY_READ)


def test_capability_grant_allows_only_requested_operations(ready_instance):
    _, identity, ownership, kernel = ready_instance
    history = own.OwnershipHistory([ownership])
    grant = _grant(identity, ownership, perms.MEMORY_READ, perms.EXPORT_STATE)
    boundary = perms.InstancePermissionBoundary(identity, history, grant)
    assert boundary.require(perms.MEMORY_READ).allows(perms.MEMORY_READ)
    assert boundary.require(perms.EXPORT_STATE).allows(perms.EXPORT_STATE)
    with pytest.raises(perms.PermissionDenied):
        boundary.require(perms.MEMORY_WRITE)


@pytest.mark.parametrize("capability", list(perms.INSTANCE_CAPABILITIES))
def test_all_required_capabilities_are_addressable(ready_instance, capability):
    _, identity, ownership, kernel = ready_instance
    history = own.OwnershipHistory([ownership])
    grant = _grant(identity, ownership, capability)
    boundary = perms.InstancePermissionBoundary(identity, history, grant)
    assert boundary.require(capability).allows(capability)


def test_forged_grant_signature_is_rejected(ready_instance):
    _, identity, ownership, kernel = ready_instance
    history = own.OwnershipHistory([ownership])
    grant = _grant(identity, ownership, perms.MEMORY_READ)
    forged = perms.CapabilityGrant.from_dict({**grant.to_dict(), "signature": "00" * 64})
    boundary = perms.InstancePermissionBoundary(identity, history, forged)
    with pytest.raises(perms.PermissionValidationError):
        boundary.require(perms.MEMORY_READ)


def test_stale_grant_rejected_after_transfer(ready_instance):
    _, identity, ownership, kernel = ready_instance
    grant = _grant(identity, ownership, perms.MEMORY_READ)
    transferred = own.transfer_ownership(ownership, identity, current_owner_token="token-a", new_owner_id="bob", new_owner_token="token-b")
    history = own.OwnershipHistory([ownership, transferred])
    boundary = perms.InstancePermissionBoundary(identity, history, grant)
    with pytest.raises(perms.PermissionValidationError):
        boundary.require(perms.MEMORY_READ)


def test_grant_cannot_be_reused_on_another_instance(ready_instance, tmp_path):
    _, identity_a, ownership_a, kernel_a = ready_instance
    grant = _grant(identity_a, ownership_a, perms.MEMORY_READ)
    identity_b = idm.load_or_create("node-B", tmp_path / "identity-B")
    ownership_b = own.create_initial_ownership(identity_b, owner_id="bob", owner_token="token-b")
    history_b = own.OwnershipHistory([ownership_b])
    boundary = perms.InstancePermissionBoundary(identity_b, history_b, grant)
    with pytest.raises(perms.PermissionScopeMismatch):
        boundary.require(perms.MEMORY_READ)


def test_export_does_not_expose_private_key_material(ready_instance):
    _, identity, ownership, kernel = ready_instance
    kernel.observe("private memory", "local", 1.0)
    payload = export_instance(_portable(identity, own.OwnershipHistory([ownership]), kernel, ownership))
    blob = json.dumps(payload, sort_keys=True)
    private_key_hex = (identity.identity_dir / "private_key.bin").read_bytes().hex()
    assert private_key_hex not in blob
    assert "private_key" not in blob


def test_export_contains_identity_ownership_memory_provenance_and_configuration(ready_instance):
    _, identity, ownership, kernel = ready_instance
    obs = kernel.observe("portable fact", "local", 0.9, metadata=cp.tag_metadata(cp.ContentProvenanceTag(cp.FIRST_PARTY_OBSERVATION, origin_id="")))
    kernel.add_evidence("portable", obs.id, 1.0, 1)
    payload = export_instance(_portable(identity, own.OwnershipHistory([ownership]), kernel, ownership, {"theme": "dark"}))
    assert payload["identity"]["node_id"] == identity.node_id
    assert payload["ownership"]["current"]["owner_id"] == "alice"
    assert payload["kernel"]["observations"]
    assert payload["kernel"]["evidence"]
    assert payload["configuration"]["theme"] == "dark"
    assert payload["compatibility"]["protocol_version"] == "0.82"
    assert payload["export_hash"]


def test_tampered_export_hash_is_rejected(ready_instance):
    _, identity, ownership, kernel = ready_instance
    payload = export_instance(_portable(identity, own.OwnershipHistory([ownership]), kernel, ownership))
    payload["configuration"]["mode"] = "tampered"
    with pytest.raises(ImportValidationError):
        import_instance(payload)


def test_malformed_export_missing_sections_is_rejected():
    with pytest.raises(ImportValidationError):
        import_instance({"type": "lantern.portable_instance", "format_version": "1.0"})


def test_forged_ownership_history_is_rejected(ready_instance):
    _, identity, ownership, kernel = ready_instance
    payload = export_instance(_portable(identity, own.OwnershipHistory([ownership]), kernel, ownership))
    payload["ownership"]["history"][0]["signature"] = "ff" * 64
    _rehash(payload)
    with pytest.raises(ImportValidationError):
        import_instance(payload)


def test_provenance_laundering_via_export_is_rejected_on_restore(ready_instance):
    _, identity, ownership, kernel = ready_instance
    kernel.observe("peer claim", "peer", 0.5, metadata=cp.tag_metadata(cp.ContentProvenanceTag(cp.PEER_CONTENT, origin_id="peer-A")))
    payload = export_instance(_portable(identity, own.OwnershipHistory([ownership]), kernel, ownership))
    payload["kernel"]["observations"][1]["metadata"] = cp.tag_metadata(cp.ContentProvenanceTag(cp.FIRST_PARTY_OBSERVATION, origin_id="peer-A"))
    _rehash(payload)
    with pytest.raises(ImportValidationError):
        import_instance(payload)


def test_import_rejects_foreign_owner_boundary_in_kernel(ready_instance):
    _, identity, ownership, kernel = ready_instance
    payload = export_instance(_portable(identity, own.OwnershipHistory([ownership]), kernel, ownership))
    payload["kernel"]["owner_instance"] = "other-owner"
    _rehash(payload)
    with pytest.raises(ImportValidationError):
        import_instance(payload)


def test_clean_independent_user_path_export_import_verify(tmp_path):
    state = lc.install(node_id="portable-user", data_dir=tmp_path / "portable-user")
    state = lc.initialize(state)
    state, identity = lc.create_identity(state)
    state, ownership = lc.authorize_owner(state, identity, owner_id="owner-1", owner_token="secret-1")
    kernel = EvidenceKernel(owner_instance=identity.public_key_hex)
    state = lc.seed_baseline_memory(state, kernel, starter_material=None)
    state = lc.apply_local_configuration(state, configuration={"profile": "clean"})
    state = lc.mark_ready(state)
    obs = kernel.observe("local observation", "local", 1.0, metadata=cp.tag_metadata(cp.ContentProvenanceTag(cp.FIRST_PARTY_OBSERVATION, origin_id="")))
    kernel.add_evidence("fact", obs.id, 1.0, 1)
    grant = perms.create_capability_grant(identity, ownership, owner_token="secret-1", capabilities=[perms.MEMORY_READ, perms.EXPORT_STATE])
    portable = PortableInstance(identity=identity, ownership_history=own.OwnershipHistory([ownership]), kernel=kernel, configuration={"profile": "clean"}, capability_grant=grant)
    payload = export_instance(portable)
    imported = import_instance(payload, expected_node_id="portable-user")
    assert imported.identity.node_id == "portable-user"
    assert imported.ownership_history.verify_chain() is True
    assert imported.kernel.belief("fact") == kernel.belief("fact")
    assert imported.configuration["profile"] == "clean"


def test_revoked_ownership_export_cannot_import_as_active_state(ready_instance):
    _, identity, ownership, kernel = ready_instance
    revoked = own.revoke_ownership(ownership, identity, current_owner_token="token-a")
    history = own.OwnershipHistory([ownership, revoked])
    grant = perms.create_capability_grant(identity, ownership, owner_token="token-a", capabilities=[perms.MEMORY_READ, perms.EXPORT_STATE])
    portable = PortableInstance(identity=identity, ownership_history=history, kernel=kernel, configuration={}, capability_grant=grant)
    payload = portable.export_payload()
    with pytest.raises(ImportValidationError):
        import_instance(payload)


def test_spoofed_identity_with_different_key_but_same_node_id_is_rejected_when_pinned(tmp_path):
    """node_id is a caller-chosen label, not a cryptographic binding.
    An attacker can mint a brand-new keypair, self-label it with a
    real node_id, and self-sign a fully internally-consistent export.
    Every signature inside such a bundle verifies against itself, so
    this can only be caught by pinning against a previously-known
    public key -- exactly what expected_public_key does."""
    real_dir = tmp_path / "real"
    real_identity = idm.load_or_create("node-real", real_dir)
    real_record = own.create_initial_ownership(real_identity, owner_id="alice", owner_token="tok")
    real_kernel = EvidenceKernel(owner_instance=real_identity.public_key_hex)
    real_grant = perms.create_capability_grant(real_identity, real_record, owner_token="tok", capabilities=[perms.MEMORY_READ, perms.EXPORT_STATE])
    real_portable = PortableInstance(identity=real_identity, ownership_history=own.OwnershipHistory([real_record]), kernel=real_kernel, configuration={}, capability_grant=real_grant)

    fake_dir = tmp_path / "fake"
    fake_identity = idm.load_or_create("node-real", fake_dir)
    fake_record = own.create_initial_ownership(fake_identity, owner_id="mallory", owner_token="fake-tok")
    fake_kernel = EvidenceKernel(owner_instance=fake_identity.public_key_hex)
    fake_grant = perms.create_capability_grant(fake_identity, fake_record, owner_token="fake-tok", capabilities=[perms.MEMORY_READ, perms.EXPORT_STATE])
    fake_portable = PortableInstance(identity=fake_identity, ownership_history=own.OwnershipHistory([fake_record]), kernel=fake_kernel, configuration={}, capability_grant=fake_grant)
    fake_payload = export_instance(fake_portable)

    # Without pinning, node_id alone is not enough to catch this -- that
    # is the documented trust-on-first-use limitation.
    imported_unpinned = import_instance(fake_payload, expected_node_id="node-real")
    assert imported_unpinned.identity.public_key_hex == fake_identity.public_key_hex

    # Once the importer knows the real public key (e.g. from a prior
    # trusted import), pinning must reject the spoofed bundle.
    with pytest.raises(ImportValidationError):
        import_instance(
            fake_payload,
            expected_node_id="node-real",
            expected_public_key=real_identity.public_key_hex,
        )


def test_replayed_stale_ownership_export_is_rejected_when_sequence_is_known(tmp_path):
    """A validly signed export captured while `bob` was the current
    owner (sequence 1) must not be accepted as current after a further
    legitimate transfer to `carol` (sequence 2) has happened -- every
    signature in the replayed bundle is genuine, it is simply stale."""
    identity = idm.load_or_create("node-replay", tmp_path / "node-replay")
    r0 = own.create_initial_ownership(identity, owner_id="alice", owner_token="tok-a")
    r1 = own.transfer_ownership(r0, identity, current_owner_token="tok-a", new_owner_id="bob", new_owner_token="tok-b")
    own.transfer_ownership(r1, identity, current_owner_token="tok-b", new_owner_id="carol", new_owner_token="tok-c")

    kernel = EvidenceKernel(owner_instance=identity.public_key_hex)
    old_history = own.OwnershipHistory([r0, r1])
    grant = perms.create_capability_grant(identity, r1, owner_token="tok-b", capabilities=[perms.MEMORY_READ, perms.EXPORT_STATE])
    old_portable = PortableInstance(identity=identity, ownership_history=old_history, kernel=kernel, configuration={}, capability_grant=grant)
    replayed_payload = export_instance(old_portable)

    # Without a known floor, the stale-but-valid bundle imports "successfully".
    imported = import_instance(replayed_payload, expected_node_id="node-replay")
    assert imported.ownership_history.current().sequence == 1

    # Once the importer records the last sequence it actually observed
    # (2, from carol's transfer), replaying the sequence-1 bundle must
    # be rejected.
    with pytest.raises(ImportValidationError):
        import_instance(
            replayed_payload,
            expected_node_id="node-replay",
            min_ownership_sequence=2,
        )
