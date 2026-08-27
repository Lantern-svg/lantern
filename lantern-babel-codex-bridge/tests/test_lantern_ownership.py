"""
Lantern Instance Ownership Tests

Covers:

INITIAL OWNERSHIP
  - creation requires explicit owner_id + owner_token
  - no self-claim / no default owner_id path
  - resulting record verifies against the instance's own public key

TRANSFER
  - valid transfer with correct current token
  - transfer refused with wrong current token
  - transfer refused for a different node_id's record
  - transfer refused for a revoked record
  - transfer chain (transferred_from/sequence) is verifiable

REVOCATION
  - valid revocation with correct token
  - revocation refused with wrong token
  - revoked record cannot be transferred
  - revocation is appended to history, not deleted

ADVERSARIAL
  - forged signature (different instance's key) is rejected
  - tampered record (owner_id changed post-signature) is rejected
  - non-contiguous sequence rejected by OwnershipHistory.append
  - transferred_from mismatch rejected by OwnershipHistory.append

PERSISTENCE
  - save/load round-trip preserves full chain verifiability
"""

from __future__ import annotations

import dataclasses

import pytest

from lantern import identity as idm
from lantern import ownership as own


@pytest.fixture
def node(tmp_path):
    return idm.load_or_create("node-A", tmp_path / "node-A")


@pytest.fixture
def other_node(tmp_path):
    return idm.load_or_create("node-B", tmp_path / "node-B")


# ============================================================
# INITIAL OWNERSHIP
# ============================================================

def test_create_initial_ownership_requires_owner_id_and_token(node):
    record = own.create_initial_ownership(node, owner_id="alice", owner_token="correct-token")
    assert record.owner_id == "alice"
    assert record.sequence == 0
    assert record.transferred_from is None
    assert record.revoked is False
    assert own.verify_ownership_record(record)


def test_create_initial_ownership_rejects_empty_owner_id(node):
    with pytest.raises(own.OwnershipError):
        own.create_initial_ownership(node, owner_id="  ", owner_token="tok")


def test_create_initial_ownership_rejects_empty_token(node):
    with pytest.raises(own.OwnershipError):
        own.create_initial_ownership(node, owner_id="alice", owner_token="")


def test_owner_token_is_never_stored_in_plaintext(node):
    record = own.create_initial_ownership(node, owner_id="alice", owner_token="super-secret-token")
    serialized = str(record.to_dict())
    assert "super-secret-token" not in serialized
    assert record.owner_token_hash != "super-secret-token"


def test_no_self_claim_path_exists():
    """There is no function anywhere in this module that produces an
    OwnershipRecord without an explicit owner_id/owner_token supplied
    by the caller -- confirm the only entry points require both."""
    import inspect

    sig = inspect.signature(own.create_initial_ownership)
    assert "owner_id" in sig.parameters
    assert "owner_token" in sig.parameters
    assert sig.parameters["owner_id"].default is inspect.Parameter.empty
    assert sig.parameters["owner_token"].default is inspect.Parameter.empty


# ============================================================
# TRANSFER
# ============================================================

def test_transfer_ownership_with_correct_token(node):
    initial = own.create_initial_ownership(node, owner_id="alice", owner_token="tok-1")
    transferred = own.transfer_ownership(
        initial, node, current_owner_token="tok-1", new_owner_id="bob", new_owner_token="tok-2"
    )
    assert transferred.owner_id == "bob"
    assert transferred.transferred_from == "alice"
    assert transferred.sequence == 1
    assert own.verify_ownership_record(transferred)


def test_transfer_ownership_refused_with_wrong_token(node):
    initial = own.create_initial_ownership(node, owner_id="alice", owner_token="tok-1")
    with pytest.raises(own.OwnershipError):
        own.transfer_ownership(
            initial, node, current_owner_token="wrong-token", new_owner_id="bob", new_owner_token="tok-2"
        )


def test_transfer_ownership_refused_for_mismatched_node(node, other_node):
    initial = own.create_initial_ownership(node, owner_id="alice", owner_token="tok-1")
    with pytest.raises(own.OwnershipError):
        own.transfer_ownership(
            initial, other_node, current_owner_token="tok-1", new_owner_id="bob", new_owner_token="tok-2"
        )


def test_transfer_ownership_refused_for_revoked_record(node):
    initial = own.create_initial_ownership(node, owner_id="alice", owner_token="tok-1")
    revoked = own.revoke_ownership(initial, node, current_owner_token="tok-1")
    with pytest.raises(own.OwnershipError):
        own.transfer_ownership(
            revoked, node, current_owner_token="tok-1", new_owner_id="bob", new_owner_token="tok-2"
        )


def test_multi_hop_transfer_chain_is_verifiable(node):
    initial = own.create_initial_ownership(node, owner_id="alice", owner_token="tok-1")
    to_bob = own.transfer_ownership(initial, node, current_owner_token="tok-1", new_owner_id="bob", new_owner_token="tok-2")
    to_carol = own.transfer_ownership(to_bob, node, current_owner_token="tok-2", new_owner_id="carol", new_owner_token="tok-3")

    history = own.OwnershipHistory()
    history.append(initial)
    history.append(to_bob)
    history.append(to_carol)

    assert history.verify_chain() is True
    assert history.current().owner_id == "carol"
    assert len(history.all_records()) == 3


# ============================================================
# REVOCATION
# ============================================================

def test_revoke_ownership_with_correct_token(node):
    initial = own.create_initial_ownership(node, owner_id="alice", owner_token="tok-1")
    revoked = own.revoke_ownership(initial, node, current_owner_token="tok-1")
    assert revoked.revoked is True
    assert revoked.owner_id == own.REVOKED_OWNER_ID
    assert revoked.transferred_from == "alice"
    assert own.verify_ownership_record(revoked)


def test_revoke_ownership_refused_with_wrong_token(node):
    initial = own.create_initial_ownership(node, owner_id="alice", owner_token="tok-1")
    with pytest.raises(own.OwnershipError):
        own.revoke_ownership(initial, node, current_owner_token="wrong")


def test_revoke_already_revoked_record_raises(node):
    initial = own.create_initial_ownership(node, owner_id="alice", owner_token="tok-1")
    revoked = own.revoke_ownership(initial, node, current_owner_token="tok-1")
    with pytest.raises(own.OwnershipError):
        own.revoke_ownership(revoked, node, current_owner_token="tok-1")


def test_revocation_is_appended_not_deleted(node):
    initial = own.create_initial_ownership(node, owner_id="alice", owner_token="tok-1")
    revoked = own.revoke_ownership(initial, node, current_owner_token="tok-1")

    history = own.OwnershipHistory()
    history.append(initial)
    history.append(revoked)

    assert len(history.all_records()) == 2
    assert history.all_records()[0].owner_id == "alice"
    assert history.all_records()[0].revoked is False
    assert history.verify_chain() is True


# ============================================================
# ADVERSARIAL
# ============================================================

def test_forged_record_from_different_instance_key_is_rejected(node, other_node):
    """A record claiming to be signed by node's key, but actually
    produced by other_node's private key, must fail verification."""
    forged_from_other = own.create_initial_ownership(other_node, owner_id="attacker", owner_token="tok")
    # Splice other_node's signature onto a record claiming node's identity.
    impersonating = dataclasses.replace(
        forged_from_other,
        node_id=node.node_id,
        instance_public_key=node.public_key_hex,
    )
    assert own.verify_ownership_record(impersonating) is False


def test_tampered_owner_id_after_signing_is_rejected(node):
    record = own.create_initial_ownership(node, owner_id="alice", owner_token="tok-1")
    tampered = dataclasses.replace(record, owner_id="mallory")
    assert own.verify_ownership_record(tampered) is False


def test_tampered_owner_token_hash_after_signing_is_rejected(node):
    record = own.create_initial_ownership(node, owner_id="alice", owner_token="tok-1")
    tampered = dataclasses.replace(
        record, owner_token_hash=own._hash_owner_token("some-other-token")
    )
    assert own.verify_ownership_record(tampered) is False


def test_tampered_revoked_flag_is_rejected(node):
    record = own.create_initial_ownership(node, owner_id="alice", owner_token="tok-1")
    tampered = dataclasses.replace(record, revoked=True)
    assert own.verify_ownership_record(tampered) is False


def test_history_rejects_non_contiguous_sequence(node):
    initial = own.create_initial_ownership(node, owner_id="alice", owner_token="tok-1")
    to_bob = own.transfer_ownership(initial, node, current_owner_token="tok-1", new_owner_id="bob", new_owner_token="tok-2")

    history = own.OwnershipHistory()
    history.append(initial)
    # Skip directly to to_bob's transfer as if it were sequence 5 (simulate corruption).
    forged = dataclasses.replace(to_bob, sequence=5)
    with pytest.raises(own.OwnershipError):
        history.append(forged)


def test_history_rejects_transferred_from_mismatch(node):
    initial = own.create_initial_ownership(node, owner_id="alice", owner_token="tok-1")
    to_bob = own.transfer_ownership(initial, node, current_owner_token="tok-1", new_owner_id="bob", new_owner_token="tok-2")

    history = own.OwnershipHistory()
    history.append(initial)
    forged = dataclasses.replace(to_bob, transferred_from="not-alice")
    with pytest.raises(own.OwnershipError):
        history.append(forged)


def test_verify_chain_detects_a_spliced_in_forged_record(node, other_node):
    initial = own.create_initial_ownership(node, owner_id="alice", owner_token="tok-1")
    to_bob = own.transfer_ownership(initial, node, current_owner_token="tok-1", new_owner_id="bob", new_owner_token="tok-2")

    history = own.OwnershipHistory()
    history.append(initial)
    history.append(to_bob)
    assert history.verify_chain() is True

    # Directly mutate the internal list to simulate a record that
    # passed append()'s structural checks at write time but was
    # tampered with afterward (e.g. hand-edited JSON on disk).
    tampered_bob = dataclasses.replace(to_bob, owner_id="mallory")
    history._records[-1] = tampered_bob
    assert history.verify_chain() is False


# ============================================================
# PERSISTENCE
# ============================================================

def test_save_and_load_history_round_trip(node, tmp_path):
    initial = own.create_initial_ownership(node, owner_id="alice", owner_token="tok-1")
    to_bob = own.transfer_ownership(initial, node, current_owner_token="tok-1", new_owner_id="bob", new_owner_token="tok-2")

    history = own.OwnershipHistory()
    history.append(initial)
    history.append(to_bob)

    path = tmp_path / "ownership.json"
    own.save_history(path, history)

    loaded = own.load_history(path)
    assert loaded is not None
    assert loaded.verify_chain() is True
    assert loaded.current().owner_id == "bob"
    assert len(loaded.all_records()) == 2


def test_load_history_returns_none_when_file_missing(tmp_path):
    assert own.load_history(tmp_path / "does-not-exist.json") is None
