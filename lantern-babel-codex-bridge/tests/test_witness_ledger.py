"""LAR-1 Phase 1: Identity Witness Ledger.

One test per reconciliation-matrix cell and per ceremony, per the
implementation directive. The invariant is absolute: a node_id maps
to at most one public key for its entire lifetime.
"""

import json
from pathlib import Path

import pytest

from lantern.identity import (
    FORK_DETECTED,
    IDENTITY_PREVIOUSLY_REGISTERED,
    NODE_ID_RETIRED,
    REGISTRY_CORRUPTED,
    IdentityError,
    WitnessError,
    load_or_create,
)
from lantern.witness_ledger import (
    IdentityWitness,
    export_identity_encrypted,
    restore_identity_from_backup,
)


def make_witness(tmp_path):
    return IdentityWitness(tmp_path / "registry.jsonl")


def make_identity(node_id, base):
    return load_or_create(node_id, base / node_id)


# ------------------------------------------------------------
# 1. First creation + REGISTER (atomic)
# ------------------------------------------------------------


def test_first_creation_with_witness_registers_atomically(tmp_path):
    witness = make_witness(tmp_path)
    identity = load_or_create("node-x", tmp_path / "id", witness=witness)
    status, pk = witness.lookup("node-x")
    assert status == "active"
    assert pk == identity.public_key_hex
    assert witness.verify_chain()
    events = witness._load_verified_events()
    types = [e["type"] for e in events]
    assert types == ["GENESIS", "REGISTER"]
    reg = events[1]
    assert reg["public_key"] == identity.public_key_hex
    assert reg["binding_signature"]
    assert reg["pop"]["nonce"] and reg["pop"]["signature"]
    # PoP signature actually verifies against the registered key
    from lantern.witness_ledger import _DOMAIN_REGISTER, _pop_payload, _verify_pop

    assert _verify_pop(
        _DOMAIN_REGISTER,
        _pop_payload("REGISTER", "node-x", reg["public_key"], reg["pop"]["nonce"]),
        reg["public_key"],
        reg["pop"]["signature"],
    )


# ------------------------------------------------------------
# 2. Registration rollback on failure
# ------------------------------------------------------------


def test_registration_rollback_on_failure(tmp_path, monkeypatch):
    witness = make_witness(tmp_path)
    id_dir = tmp_path / "id"

    def boom(*a, **k):
        raise WitnessError(REGISTRY_CORRUPTED, "simulated registration failure")

    monkeypatch.setattr(witness, "register", boom)
    with pytest.raises(WitnessError):
        load_or_create("node-x", id_dir, witness=witness)
    # The just-created local identity MUST be rolled back -- no
    # partially initialized identity left behind.
    assert not id_dir.exists()


# ------------------------------------------------------------
# 3. Destroyed local identity + surviving active ledger
# ------------------------------------------------------------


def test_destroyed_local_identity_with_active_ledger_fails_closed(tmp_path):
    witness = make_witness(tmp_path)
    identity = load_or_create("node-x", tmp_path / "id", witness=witness)
    original_pk = identity.public_key_hex
    # TOTAL local loss: the whole directory is obliterated.
    import shutil

    shutil.rmtree(tmp_path / "id")
    with pytest.raises(WitnessError) as exc:
        load_or_create("node-x", tmp_path / "id", witness=witness)
    assert exc.value.code == IDENTITY_PREVIOUSLY_REGISTERED
    assert original_pk in str(exc.value)
    # And nothing was silently created in its place.
    assert not (tmp_path / "id").exists()
    status, pk = witness.lookup("node-x")
    assert (status, pk) == ("active", original_pk)


# ------------------------------------------------------------
# 4. Destroyed local identity + retired ledger
# ------------------------------------------------------------


def test_destroyed_local_identity_with_retired_ledger_fails_closed(tmp_path):
    witness = make_witness(tmp_path)
    identity = load_or_create("node-x", tmp_path / "id", witness=witness)
    witness.retire("node-x", identity, reason="decommissioned")
    import shutil

    shutil.rmtree(tmp_path / "id")
    with pytest.raises(WitnessError) as exc:
        load_or_create("node-x", tmp_path / "id", witness=witness)
    assert exc.value.code == NODE_ID_RETIRED
    assert not (tmp_path / "id").exists()


# ------------------------------------------------------------
# 5. Local identity + matching witness -> normal operation
# ------------------------------------------------------------


def test_local_identity_with_matching_witness_proceeds(tmp_path):
    witness = make_witness(tmp_path)
    first = load_or_create("node-x", tmp_path / "id", witness=witness)
    second = load_or_create("node-x", tmp_path / "id", witness=witness)
    assert second.public_key_hex == first.public_key_hex
    # No duplicate REGISTER events on a normal re-load.
    types = [e["type"] for e in witness._load_verified_events()]
    assert types.count("REGISTER") == 1


# ------------------------------------------------------------
# 6. Local identity + mismatching witness -> FORK_DETECTED
# ------------------------------------------------------------


def test_local_identity_with_mismatching_witness_fork_detected(tmp_path):
    witness = make_witness(tmp_path)
    # Two different data dirs holding the same node_id with different keys.
    a = load_or_create("node-x", tmp_path / "a", witness=witness)
    b = load_or_create("node-x", tmp_path / "b")  # no witness: raw creation
    assert a.public_key_hex != b.public_key_hex
    with pytest.raises(WitnessError) as exc:
        load_or_create("node-x", tmp_path / "b", witness=witness)
    assert exc.value.code == FORK_DETECTED


# ------------------------------------------------------------
# 7. Local identity + no ledger entry -> backfill REGISTER
# ------------------------------------------------------------


def test_local_identity_no_ledger_entry_backfills(tmp_path):
    witness = make_witness(tmp_path)
    # Identity created pre-LAR-1 (witness=None), like all existing identities.
    identity = load_or_create("node-x", tmp_path / "id")
    assert not witness.path.exists()
    # First witnessed boot: backfill.
    again = load_or_create("node-x", tmp_path / "id", witness=witness)
    assert again.public_key_hex == identity.public_key_hex
    status, pk = witness.lookup("node-x")
    assert status == "active" and pk == identity.public_key_hex
    events = witness._load_verified_events()
    assert events[-1]["type"] == "REGISTER"
    assert events[-1]["backfill"] is True
    assert witness.verify_chain()


# ------------------------------------------------------------
# 8. Corrupted / tampered hash chain
# ------------------------------------------------------------


def test_corrupted_chain_registry_corrupted(tmp_path):
    witness = make_witness(tmp_path)
    load_or_create("node-x", tmp_path / "id", witness=witness)
    lines = witness.path.read_text().splitlines()
    record = json.loads(lines[1])
    record["public_key"] = "0" * 64  # tamper WITHOUT rehashing
    lines[1] = json.dumps(record, sort_keys=True)
    witness.path.write_text("\n".join(lines) + "\n")
    with pytest.raises(WitnessError) as exc:
        load_or_create("node-x", tmp_path / "id", witness=witness)
    assert exc.value.code == REGISTRY_CORRUPTED
    assert witness.verify_chain() is False


def test_semantically_conflicting_ledger_detected(tmp_path):
    # A hash-intact but semantically conflicting hand-crafted ledger.
    witness = make_witness(tmp_path)
    a = load_or_create("node-x", tmp_path / "a", witness=witness)
    b = load_or_create("node-x", tmp_path / "b")
    from lantern.witness_ledger import _canonical_digest, _event_body, _now

    events = witness._load_verified_events()
    prev = events[-1]["current_hash"]
    forged = {
        "index": len(events),
        "type": "REGISTER",
        "node_id": "node-x",
        "public_key": b.public_key_hex,
        "binding_signature": "",
        "pop": {"nonce": "n", "signature": "", "signed_at": _now()},
        "backfill": False,
    }
    forged["previous_hash"] = prev
    forged["current_hash"] = _canonical_digest(prev, _event_body(forged))
    record = {
        "timestamp": _now(),
        "previous_hash": prev,
        "current_hash": forged["current_hash"],
        **_event_body(forged),
    }
    with witness.path.open("a") as handle:
        handle.write(json.dumps(record, sort_keys=True) + "\n")
    # Chain is hash-valid...
    with pytest.raises(WitnessError) as exc:  # ...but node-x now has two keys
        witness.lookup("node-x")
    assert exc.value.code == REGISTRY_CORRUPTED


# ------------------------------------------------------------
# 9. Duplicate / conflicting registration
# ------------------------------------------------------------


def test_duplicate_registration_conflicting_key_refused(tmp_path):
    witness = make_witness(tmp_path)
    a = load_or_create("node-x", tmp_path / "a", witness=witness)
    b = load_or_create("node-x", tmp_path / "b")  # different key, same node_id
    with pytest.raises(WitnessError) as exc:
        witness.register("node-x", b)
    assert exc.value.code == FORK_DETECTED
    # Idempotent re-registration of the SAME key is a no-op, not an error.
    result = witness.register("node-x", a)
    assert result["status"] == "already_registered"


# ------------------------------------------------------------
# 10. RECOVER with the correct key
# ------------------------------------------------------------


def test_recover_with_correct_key_appends_recover_event(tmp_path):
    # Direct ceremony test (the full destroy->backup->restore path is
    # covered by test_recover_after_backup_restore below).
    witness = make_witness(tmp_path)
    identity = load_or_create("node-x", tmp_path / "id", witness=witness)
    result = witness.recover("node-x", identity, provenance="test ceremony")
    assert result["type"] == "RECOVER"
    events = witness._load_verified_events()
    recover = events[-1]
    assert recover["type"] == "RECOVER"
    assert recover["public_key"] == identity.public_key_hex
    assert recover["provenance"] == "test ceremony"
    # PoP signature in the RECOVER event verifies against the key.
    from lantern.witness_ledger import _DOMAIN_RECOVER, _pop_payload, _verify_pop

    assert _verify_pop(
        _DOMAIN_RECOVER,
        _pop_payload("RECOVER", "node-x", recover["public_key"], recover["pop"]["nonce"]),
        recover["public_key"],
        recover["pop"]["signature"],
    )
    assert witness.verify_chain()
    # Boot reconciliation still proceeds normally afterwards.
    again = load_or_create("node-x", tmp_path / "id", witness=witness)
    assert again.public_key_hex == identity.public_key_hex


def test_recover_after_backup_restore(tmp_path):
    witness = make_witness(tmp_path)
    identity = load_or_create("node-x", tmp_path / "id", witness=witness)
    registered_pk = identity.public_key_hex
    # Operator takes an encrypted backup while the identity is healthy.
    backup_file = tmp_path / "backup.json"
    export_identity_encrypted(identity, "operator-passphrase", backup_file)
    # TOTAL loss.
    import shutil

    shutil.rmtree(tmp_path / "id")
    with pytest.raises(WitnessError) as exc:
        load_or_create("node-x", tmp_path / "id", witness=witness)
    assert exc.value.code == IDENTITY_PREVIOUSLY_REGISTERED
    # Operator restores from backup into a NEW directory location.
    restored = restore_identity_from_backup(backup_file, "operator-passphrase", tmp_path / "id2")
    assert restored.public_key_hex == registered_pk
    # RECOVER ceremony: same key -> RECOVER event appended.
    result = witness.recover("node-x", restored, provenance="operator backup")
    assert result["type"] == "RECOVER"
    events = witness._load_verified_events()
    assert events[-1]["type"] == "RECOVER"
    assert events[-1]["public_key"] == registered_pk
    assert witness.verify_chain()
    # Node proceeds with the same identity from the restored dir.
    identity2 = load_or_create("node-x", tmp_path / "id2", witness=witness)
    assert identity2.public_key_hex == registered_pk


# ------------------------------------------------------------
# 11. RECOVER attempting a different key -> refused
# ------------------------------------------------------------


def test_recover_attempting_different_key_refused(tmp_path):
    witness = make_witness(tmp_path)
    load_or_create("node-x", tmp_path / "a", witness=witness)
    impostor = load_or_create("node-x", tmp_path / "b")
    with pytest.raises(WitnessError) as exc:
        witness.recover("node-x", impostor)
    assert exc.value.code == "RECOVER_KEY_MISMATCH"
    # No RECOVER event was written.
    types = [e["type"] for e in witness._load_verified_events()]
    assert "RECOVER" not in types


# ------------------------------------------------------------
# 12. RETIRE (authenticated by proof of possession)
# ------------------------------------------------------------


def test_retire_requires_possession_and_records_event(tmp_path):
    witness = make_witness(tmp_path)
    identity = load_or_create("node-x", tmp_path / "id", witness=witness)
    # A different key cannot retire the node_id.
    impostor = load_or_create("node-x", tmp_path / "other")
    with pytest.raises(WitnessError) as exc:
        witness.retire("node-x", impostor)
    assert exc.value.code == FORK_DETECTED
    # The real key retires it.
    result = witness.retire("node-x", identity, reason="end of experiment")
    assert result["type"] == "RETIRE"
    events = witness._load_verified_events()
    assert events[-1]["type"] == "RETIRE"
    assert events[-1]["reason"] == "end of experiment"
    assert witness.verify_chain()


# ------------------------------------------------------------
# 13. Retired node_id can never be resurrected
# ------------------------------------------------------------


def test_retired_node_id_cannot_be_resurrected(tmp_path):
    witness = make_witness(tmp_path)
    identity = load_or_create("node-x", tmp_path / "id", witness=witness)
    witness.retire("node-x", identity)
    # A brand-new key under the retired node_id: refused at registration...
    new_identity = load_or_create("node-x", tmp_path / "fresh")
    with pytest.raises(WitnessError) as exc:
        witness.register("node-x", new_identity)
    assert exc.value.code == NODE_ID_RETIRED
    # ...and at boot reconciliation (local present + retired)...
    with pytest.raises(WitnessError) as exc:
        load_or_create("node-x", tmp_path / "fresh", witness=witness)
    assert exc.value.code == NODE_ID_RETIRED
    # ...and with the local identity destroyed.
    import shutil

    shutil.rmtree(tmp_path / "id")
    with pytest.raises(WitnessError) as exc:
        load_or_create("node-x", tmp_path / "id", witness=witness)
    assert exc.value.code == NODE_ID_RETIRED
    # RETIRE is also idempotent-safe: re-retiring is a no-op.
    assert witness.retire("node-x", identity) == {"status": "already_retired"}


# ------------------------------------------------------------
# 14. FORCE_RETIRE ceremony and audit record
# ------------------------------------------------------------


def test_force_retire_ceremony_and_audit_record(tmp_path):
    witness = make_witness(tmp_path)
    load_or_create("node-x", tmp_path / "id", witness=witness)
    # Without explicit acknowledgment: refused.
    with pytest.raises(WitnessError) as exc:
        witness.force_retire("node-x", note="keys lost")
    assert exc.value.code == "FORK_RISK_NOT_ACKNOWLEDGED"
    assert witness.lookup("node-x")[0] == "active"
    # With the explicit operator ceremony: recorded loudly.
    result = witness.force_retire(
        "node-x", note="keys lost 2026-09-02; fork risk acknowledged",
        acknowledged_fork_risk=True,
    )
    assert result["type"] == "FORCE_RETIRE"
    events = witness._load_verified_events()
    event = events[-1]
    assert event["acknowledged_fork_risk"] is True
    assert event["operator_note"].startswith("keys lost")
    assert witness.verify_chain()
    # FORCE_RETIRE does NOT authorize a new key under the node_id.
    new_identity = load_or_create("node-x", tmp_path / "fresh")
    with pytest.raises(WitnessError) as exc:
        witness.register("node-x", new_identity)
    assert exc.value.code == NODE_ID_RETIRED


# ------------------------------------------------------------
# 15. Replacement identity requires a NEW node_id
# ------------------------------------------------------------


def test_replacement_identity_requires_new_node_id(tmp_path):
    witness = make_witness(tmp_path)
    old = load_or_create("node-old", tmp_path / "old", witness=witness)
    witness.force_retire("node-old", note="decommissioned", acknowledged_fork_risk=True)
    new = load_or_create("node-new", tmp_path / "new", witness=witness)
    assert new.node_id == "node-new"
    assert new.public_key_hex != old.public_key_hex
    assert witness.lookup("node-new")[0] == "active"
    assert witness.lookup("node-old")[0] == "retired"
    assert witness.verify_chain()


# ------------------------------------------------------------
# 16. Registry export / import
# ------------------------------------------------------------


def test_registry_export_import(tmp_path):
    witness = make_witness(tmp_path)
    load_or_create("node-x", tmp_path / "id", witness=witness)
    snapshot = tmp_path / "snapshot.jsonl"
    result = witness.export_snapshot(snapshot)
    assert result["records"] == 2  # GENESIS + REGISTER
    # Local ledger gets tampered.
    witness.path.write_text("garbage\n")
    assert witness.verify_chain() is False
    with pytest.raises(WitnessError):
        witness.lookup("node-x")
    # Operator restores from the held snapshot.
    installed = witness.import_snapshot(snapshot)
    assert installed["installed_records"] == 2
    assert witness.verify_chain() is True
    status, pk = witness.lookup("node-x")
    assert status == "active"
    # Importing a corrupted snapshot is refused.
    bad = tmp_path / "bad.jsonl"
    bad.write_text("garbage\n")
    with pytest.raises(WitnessError):
        witness.import_snapshot(bad)


# ------------------------------------------------------------
# 17. Encrypted identity export (roundtrip)
# ------------------------------------------------------------


def test_encrypted_identity_export_roundtrip(tmp_path):
    witness = make_witness(tmp_path)
    identity = load_or_create("node-x", tmp_path / "id", witness=witness)
    backup_file = tmp_path / "backup.json"
    meta = export_identity_encrypted(identity, "correct horse battery staple", backup_file)
    assert meta["node_id"] == "node-x"
    # The export file never contains plaintext private material.
    raw = backup_file.read_text()
    assert "private" not in raw.lower()
    assert identity.sign(b"test", b"payload") not in raw
    # Wrong passphrase is refused.
    with pytest.raises(WitnessError) as exc:
        restore_identity_from_backup(backup_file, "wrong", tmp_path / "id2")
    assert exc.value.code == "BACKUP_DECRYPT_FAILED"
    # Restoration never overwrites existing material.
    with pytest.raises(WitnessError) as exc:
        restore_identity_from_backup(backup_file, "correct horse battery staple", tmp_path / "id")
    assert exc.value.code == "REFUSING_OVERWRITE"
    # Correct passphrase restores byte-identical identity.
    restored = restore_identity_from_backup(
        backup_file, "correct horse battery staple", tmp_path / "id2"
    )
    assert restored.public_key_hex == identity.public_key_hex
    assert (tmp_path / "id2" / "private_key.bin").read_bytes() == (
        tmp_path / "id" / "private_key.bin"
    ).read_bytes()
    # 0600 on the restored private key.
    import stat as stat_module

    assert stat_module.S_IMODE((tmp_path / "id2" / "private_key.bin").stat().st_mode) == 0o600


# ------------------------------------------------------------
# 18. Default witness=None compatibility
# ------------------------------------------------------------


def test_witness_none_default_behavior_unchanged(tmp_path):
    # No witness: creation + loading work exactly as before LAR-1.
    identity = load_or_create("node-x", tmp_path / "id")
    assert not (tmp_path / "registry.jsonl").exists()
    again = load_or_create("node-x", tmp_path / "id")
    assert again.public_key_hex == identity.public_key_hex
    # Existing fail-closed behavior (partial loss) still raises IdentityError.
    (tmp_path / "id" / "private_key.bin").unlink()
    with pytest.raises(IdentityError):
        load_or_create("node-x", tmp_path / "id")


def test_bootstrap_node_witness_refuses_fork_before_serving(tmp_path):
    # Node-level wiring: reconciliation happens at construction, so a
    # fork is refused BEFORE any socket binds or Chronicle writes.
    from lantern.bootstrap_node import create_server

    witness = make_witness(tmp_path)
    original = load_or_create("node-x", tmp_path / "id", witness=witness)
    import shutil

    shutil.rmtree(tmp_path / "id")
    with pytest.raises(WitnessError) as exc:
        create_server(
            "127.0.0.1",
            0,
            "node-x",
            tmp_path / "chronicle.jsonl",
            witness=witness,
        )
    assert exc.value.code == IDENTITY_PREVIOUSLY_REGISTERED
    # No chronicle file was created by the refused construction.
    assert not (tmp_path / "chronicle.jsonl").exists()
