"""Identity-continuity regression tests (integrity review 2026-09-02, fix implemented).

Lantern's identity continuity invariant:

    established node_id + missing expected key material
        -> explicit IdentityError
        -> NO silent regeneration, NO binding overwrite, NO identity fork

Fresh creation is only permitted for an identity directory that does not
exist at all. Creation and recovery are distinguished by the filesystem:
an existing directory without key material is treated as an established
identity in a broken state and fails closed.

All tests use isolated pytest tmp_path fixtures. No production identity
is touched.
"""

import json

import pytest

from lantern.identity import (
    IdentityError,
    load_or_create,
    verify_binding,
)


def _binding(id_dir):
    return json.loads((id_dir / "binding.json").read_text())


def test_fresh_identity_creation(tmp_path):
    """1. A fresh identity can still be created normally (absent dir)."""
    ident_dir = tmp_path / "fresh"
    assert not ident_dir.exists()
    ident = load_or_create("continuity-fresh", ident_dir)
    assert ident.node_id == "continuity-fresh"
    assert (ident_dir / "private_key.bin").exists()
    assert (ident_dir / "binding.json").exists()


def test_fresh_identity_correspondence(tmp_path):
    """2. The resulting keypair is valid and correctly bound."""
    from nacl.signing import VerifyKey

    ident_dir = tmp_path / "corr"
    ident = load_or_create("continuity-corr", ident_dir)
    sig = ident.sign(b"test", b"payload")
    VerifyKey(bytes.fromhex(ident.public_key_hex)).verify(
        b"test|payload", bytes.fromhex(sig)
    )
    binding = _binding(ident_dir)
    assert verify_binding(ident.node_id, binding["public_key"], binding["signature"])


def test_identity_persisted_and_reloadable(tmp_path):
    """3. The identity persists and reloads to the same key."""
    ident_dir = tmp_path / "persist"
    first = load_or_create("continuity-persist", ident_dir)
    second = load_or_create("continuity-persist", ident_dir)
    assert first.public_key_hex == second.public_key_hex


def test_established_identity_missing_key_material_fails_closed(tmp_path):
    """4-5. Removing expected key material from an established identity
    (all files deleted, directory remains) must raise IdentityError and
    must NOT silently generate a replacement keypair under the same
    node_id.
    """
    ident_dir = tmp_path / "established"
    ident = load_or_create("continuity-established", ident_dir)
    original_pk = ident.public_key_hex

    # Simulate loss of the identity's key material.
    for name in ("private_key.bin", "public_key.bin", "binding.json"):
        (ident_dir / name).unlink()

    with pytest.raises(IdentityError):
        load_or_create("continuity-established", ident_dir)

    # 5. No replacement identity was written.
    assert not (ident_dir / "private_key.bin").exists()
    assert not (ident_dir / "binding.json").exists()
    assert original_pk  # original fingerprint observed before loss


def test_partial_state_missing_private_key_does_not_overwrite_binding(tmp_path):
    """Dangerous overwrite path from the review: binding.json survives but
    the private key is gone. Must fail closed AND leave the surviving
    binding.json untouched (it is the last record of the old identity).
    """
    ident_dir = tmp_path / "partial"
    ident = load_or_create("continuity-partial", ident_dir)
    original_pk = ident.public_key_hex
    original_binding = (ident_dir / "binding.json").read_text()
    (ident_dir / "private_key.bin").unlink()
    # binding.json + public_key.bin intentionally left in place

    with pytest.raises(IdentityError):
        load_or_create("continuity-partial", ident_dir)

    # 6. Existing binding.json is not overwritten.
    assert (ident_dir / "binding.json").read_text() == original_binding
    assert _binding(ident_dir)["public_key"] == original_pk
    # and no replacement private key appeared
    assert not (ident_dir / "private_key.bin").exists()


def test_pre_created_empty_directory_fails_closed(tmp_path):
    """A directory that exists without any identity material is treated as
    a broken established identity, not a fresh-creation target."""
    ident_dir = tmp_path / "precreated"
    ident_dir.mkdir()
    with pytest.raises(IdentityError):
        load_or_create("continuity-precreated", ident_dir)
    assert not (ident_dir / "private_key.bin").exists()
    assert not (ident_dir / "binding.json").exists()


def test_original_identity_unchanged_outside_fixture(tmp_path):
    """7-8. A separate established identity outside the damaged fixture is
    unaffected by the fail-closed refusals and still loads identically.
    """
    damaged = tmp_path / "damaged"
    healthy = tmp_path / "healthy"

    healthy_ident = load_or_create("continuity-healthy", healthy)
    healthy_pk = healthy_ident.public_key_hex
    healthy_binding = (healthy / "binding.json").read_text()

    load_or_create("continuity-damaged", damaged)
    for name in ("private_key.bin", "public_key.bin", "binding.json"):
        (damaged / name).unlink()

    # the damaged identity refuses to regenerate...
    with pytest.raises(IdentityError):
        load_or_create("continuity-damaged", damaged)

    # ...and the healthy identity is untouched and reloadable.
    reloaded = load_or_create("continuity-healthy", healthy)
    assert reloaded.public_key_hex == healthy_pk
    assert (healthy / "binding.json").read_text() == healthy_binding


def test_create_new_never_overwrites_existing_material(tmp_path):
    """Direct guard: _create_new refuses when any identity file exists."""
    from lantern.identity import _create_new, _identity_paths

    ident_dir = tmp_path / "guard"
    load_or_create("continuity-guard", ident_dir)
    (ident_dir / "private_key.bin").unlink()  # binding + public_key remain

    paths = _identity_paths(ident_dir)
    with pytest.raises(IdentityError):
        _create_new("continuity-guard", paths)
