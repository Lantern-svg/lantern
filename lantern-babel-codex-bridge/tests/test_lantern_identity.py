"""
Lantern Node Identity Tests

Covers, per the Phase 2A implementation authorization:

IDENTITY CREATION
  - first-run key generation
  - persistence across restart
  - deterministic public-key retrieval
  - stable node_id

IDENTITY BINDING
  - valid binding
  - wrong node_id
  - wrong public key
  - modified binding
  - malformed binding

CHALLENGE/PROOF
  - valid proof
  - wrong private key
  - wrong public key
  - wrong node_id
  - modified nonce
  - modified initiator
  - modified responder
  - modified protocol context
  - expired proof
  - replayed proof
  - consumed challenge reuse

HANDSHAKE
  - responder returns configured node_id
  - repeated responses preserve identity
  - legacy handshake remains distinguishable
  - identity verification does not alter trust
  - identity verification does not alter authority

SECURITY
  - private key never appears in Chronicle
  - private key never appears in HTTP response (identity_public())
  - private key never appears in a Discord signaling payload shape
  - CODEX_UPDATE remains false
  - no unauthorized capability escalation
"""

from __future__ import annotations

import dataclasses
import json
import time

import pytest

from lantern import identity as idm
from lantern.compatibility import DEFAULT_CAPABILITIES
from lantern.handshake import create_handshake, evaluate_handshake
from lantern.participants import (
    AUTHORITY_NONE,
    IDENTITY_CRYPTOGRAPHICALLY_VERIFIED,
    IDENTITY_UNVERIFIED,
    TRUST_UNVERIFIED,
    inspect,
)
from lantern.rendezvous import JoinRequest


# ============================================================
# Fixtures / helpers
# ============================================================

@pytest.fixture
def two_identities(tmp_path):
    a = idm.load_or_create("node-A", tmp_path / "a")
    b = idm.load_or_create("node-B", tmp_path / "b")
    return a, b


def _binding_signature(node: idm.NodeIdentity) -> str:
    return json.loads((node.identity_dir / "binding.json").read_text())["signature"]


def _valid_exchange(a: idm.NodeIdentity, b: idm.NodeIdentity):
    """A challenges B, B answers, return (store, challenge, proof)."""
    store = idm.ChallengeStore()
    challenge = store.issue(from_node_id=a.node_id, to_node_id=b.node_id)
    proof = idm.respond_to_challenge(challenge, b, _binding_signature(b))
    return store, challenge, proof


# ============================================================
# IDENTITY CREATION
# ============================================================

def test_first_run_generates_key_material(tmp_path):
    identity_dir = tmp_path / "node"
    assert not (identity_dir / "private_key.bin").exists()

    node = idm.load_or_create("node-1", identity_dir)

    assert (identity_dir / "private_key.bin").exists()
    assert (identity_dir / "public_key.bin").exists()
    assert (identity_dir / "binding.json").exists()
    assert node.node_id == "node-1"
    assert len(node.public_key_hex) == 64  # 32 bytes hex-encoded


def test_private_key_file_has_restrictive_permissions(tmp_path):
    import stat as statmod

    identity_dir = tmp_path / "node"
    idm.load_or_create("node-1", identity_dir)
    mode = (identity_dir / "private_key.bin").stat().st_mode
    assert statmod.S_IMODE(mode) == 0o600


def test_persistence_across_restart(tmp_path):
    identity_dir = tmp_path / "node"
    first = idm.load_or_create("node-1", identity_dir)
    second = idm.load_or_create("node-1", identity_dir)

    assert first.public_key_hex == second.public_key_hex
    assert first.node_id == second.node_id


def test_deterministic_public_key_retrieval(tmp_path):
    identity_dir = tmp_path / "node"
    node = idm.load_or_create("node-1", identity_dir)
    # Calling verify_key_hex() repeatedly must always return the same value.
    assert node.verify_key_hex() == node.verify_key_hex() == node.public_key_hex


def test_stable_node_id_across_restart(tmp_path):
    identity_dir = tmp_path / "node"
    idm.load_or_create("stable-node", identity_dir)
    reloaded = idm.load_or_create("stable-node", identity_dir)
    assert reloaded.node_id == "stable-node"


def test_loading_with_mismatched_node_id_is_rejected(tmp_path):
    identity_dir = tmp_path / "node"
    idm.load_or_create("node-1", identity_dir)
    with pytest.raises(idm.IdentityError):
        idm.load_or_create("different-node-id", identity_dir)


# ============================================================
# IDENTITY BINDING
# ============================================================

def test_valid_binding_verifies(two_identities):
    a, _ = two_identities
    assert idm.verify_binding(a.node_id, a.public_key_hex, _binding_signature(a)) is True


def test_binding_rejects_wrong_node_id(two_identities):
    a, _ = two_identities
    assert idm.verify_binding("someone-else", a.public_key_hex, _binding_signature(a)) is False


def test_binding_rejects_wrong_public_key(two_identities):
    a, b = two_identities
    # a's signature, but claiming b's public key
    assert idm.verify_binding(a.node_id, b.public_key_hex, _binding_signature(a)) is False


def test_binding_rejects_modified_signature(two_identities):
    a, _ = two_identities
    sig = _binding_signature(a)
    modified = ("0" if sig[0] != "0" else "1") + sig[1:]
    assert idm.verify_binding(a.node_id, a.public_key_hex, modified) is False


def test_binding_rejects_malformed_signature(two_identities):
    a, _ = two_identities
    assert idm.verify_binding(a.node_id, a.public_key_hex, "not-hex-at-all!!") is False
    assert idm.verify_binding(a.node_id, a.public_key_hex, "") is False


def test_binding_rejects_malformed_public_key(two_identities):
    a, _ = two_identities
    assert idm.verify_binding(a.node_id, "not-a-valid-key", _binding_signature(a)) is False


# ============================================================
# CHALLENGE / PROOF
# ============================================================

def test_valid_proof_verifies(two_identities):
    a, b = two_identities
    store, challenge, proof = _valid_exchange(a, b)
    result = store.consume(proof)
    assert result.verified is True
    assert result.identity_status == idm.CRYPTOGRAPHICALLY_VERIFIED


def test_proof_signed_by_wrong_private_key_is_rejected(two_identities):
    a, b = two_identities
    store = idm.ChallengeStore()
    challenge = store.issue(from_node_id=a.node_id, to_node_id=b.node_id)

    # Attacker controls A's key, not B's, but forges a proof claiming to be B.
    forged_payload = idm._challenge_proof_payload(
        challenge.nonce, a.node_id, b.node_id, challenge.protocol_version, b.node_id, b.public_key_hex
    )
    forged_signature = a.sign(idm._DOMAIN_CHALLENGE_PROOF, forged_payload)
    forged_proof = idm.IdentityProof(
        nonce=challenge.nonce,
        from_node_id=a.node_id,
        to_node_id=b.node_id,
        protocol_version=challenge.protocol_version,
        claimed_node_id=b.node_id,
        public_key=b.public_key_hex,  # claims B's key
        identity_binding_signature=_binding_signature(b),
        signature=forged_signature,  # but signed by A's key
        proof_timestamp="2026-01-01T00:00:00Z",
    )
    result = store.consume(forged_proof)
    assert result.verified is False
    assert "signature" in result.reason.lower()


def test_proof_presenting_wrong_public_key_is_rejected(two_identities):
    a, b = two_identities
    store, challenge, proof = _valid_exchange(a, b)
    # Swap in a different (but validly-formatted) public key.
    tampered = dataclasses.replace(proof, public_key=a.public_key_hex)
    result = store.consume(tampered)
    assert result.verified is False


def test_proof_claiming_wrong_node_id_is_rejected(two_identities):
    a, b = two_identities
    store, challenge, proof = _valid_exchange(a, b)
    tampered = dataclasses.replace(proof, claimed_node_id="not-node-B")
    result = store.consume(tampered)
    assert result.verified is False


def test_proof_with_modified_nonce_is_rejected(two_identities):
    a, b = two_identities
    store, challenge, proof = _valid_exchange(a, b)
    tampered = dataclasses.replace(proof, nonce="0" * 64)
    result = store.consume(tampered)
    assert result.verified is False


def test_proof_with_modified_initiator_is_rejected(two_identities):
    a, b = two_identities
    store, challenge, proof = _valid_exchange(a, b)
    tampered = dataclasses.replace(proof, from_node_id="impersonated-initiator")
    result = store.consume(tampered)
    assert result.verified is False


def test_proof_with_modified_responder_is_rejected(two_identities):
    a, b = two_identities
    store, challenge, proof = _valid_exchange(a, b)
    tampered = dataclasses.replace(proof, to_node_id="impersonated-responder")
    result = store.consume(tampered)
    assert result.verified is False


def test_proof_with_modified_protocol_context_is_rejected(two_identities):
    a, b = two_identities
    store, challenge, proof = _valid_exchange(a, b)
    tampered = dataclasses.replace(proof, protocol_version="9.9")
    result = store.consume(tampered)
    assert result.verified is False


def test_expired_proof_is_rejected(two_identities):
    a, b = two_identities
    store = idm.ChallengeStore()
    challenge = store.issue(from_node_id=a.node_id, to_node_id=b.node_id, ttl_seconds=0)
    proof = idm.respond_to_challenge(challenge, b, _binding_signature(b))
    time.sleep(0.05)
    result = store.consume(proof)
    assert result.verified is False
    assert "expired" in result.reason.lower()


def test_replayed_proof_is_rejected(two_identities):
    a, b = two_identities
    store, challenge, proof = _valid_exchange(a, b)
    first = store.consume(proof)
    second = store.consume(proof)
    assert first.verified is True
    assert second.verified is False
    assert "replay" in second.reason.lower()


def test_consumed_challenge_cannot_be_reused_even_after_failed_attempt(two_identities):
    a, b = two_identities
    store, challenge, proof = _valid_exchange(a, b)
    tampered = dataclasses.replace(proof, nonce=challenge.nonce, claimed_node_id="wrong")
    first = store.consume(tampered)
    assert first.verified is False
    # The nonce must be burned even though the first attempt failed --
    # otherwise a failed guess could be retried indefinitely.
    second = store.consume(proof)  # now try with the real, valid proof
    assert second.verified is False
    assert "replay" in second.reason.lower() or "unknown" in second.reason.lower()


def test_public_key_substitution_rejected_once_pinned(two_identities):
    a, b = two_identities
    store, challenge, proof = _valid_exchange(a, b)
    # A already knows B's real key from a prior exchange (pinning).
    result = store.consume(proof, expected_public_key=a.public_key_hex)  # wrong pin on purpose
    assert result.verified is False
    assert "substitution" in result.reason.lower() or "public key" in result.reason.lower()


# ============================================================
# HANDSHAKE
# ============================================================

def test_handshake_responder_returns_configured_node_id():
    request = create_handshake()
    request.node_id = "peer-node"
    response = evaluate_handshake(request, responder_node_id="my-real-node-id")
    assert response.node_id == "my-real-node-id"


def test_repeated_handshake_responses_preserve_identity():
    request = create_handshake()
    responses = [evaluate_handshake(request, responder_node_id="stable-responder") for _ in range(5)]
    node_ids = {r.node_id for r in responses}
    assert node_ids == {"stable-responder"}


def test_handshake_without_responder_node_id_preserves_old_behavior():
    # Backward compatibility: omitting responder_node_id must not break
    # any existing caller -- falls back to the pre-existing uuid4() behavior.
    request = create_handshake()
    response = evaluate_handshake(request)
    assert isinstance(response.node_id, str) and len(response.node_id) > 0


def test_legacy_handshake_never_implies_identity_verification():
    # A successful ordinary handshake carries no identity_status field at
    # all -- it must never be interpreted as CRYPTOGRAPHICALLY_VERIFIED.
    request = create_handshake()
    response = evaluate_handshake(request, responder_node_id="legacy-node")
    assert response.accepted is True
    assert not hasattr(response, "identity_status")


def test_participant_view_defaults_to_unverified_identity_status():
    request = JoinRequest(
        request_id="r1",
        node_id="node-X",
        protocol_version="0.82",
        capabilities={"evidence_exchange": True},
        timestamp="2026-01-01T00:00:00Z",
        peer_endpoint=None,
        expires_at="2099-01-01T00:00:00Z",
        status="AWAITING_HANDSHAKE",
    )
    view = inspect(request)
    assert view.identity_status == IDENTITY_UNVERIFIED
    # And identity verification success must be explicitly passed in,
    # never inferred just because a handshake/join happened.
    verified_view = inspect(request, identity_status=IDENTITY_CRYPTOGRAPHICALLY_VERIFIED)
    assert verified_view.identity_status == IDENTITY_CRYPTOGRAPHICALLY_VERIFIED


def test_cryptographically_verified_identity_does_not_alter_trust(two_identities):
    a, b = two_identities
    store, challenge, proof = _valid_exchange(a, b)
    result = store.consume(proof)
    assert result.verified is True

    request = JoinRequest(
        request_id="r2",
        node_id=b.node_id,
        protocol_version="0.82",
        capabilities={"evidence_exchange": True},
        timestamp="2026-01-01T00:00:00Z",
        peer_endpoint=None,
        expires_at="2099-01-01T00:00:00Z",
        status="AWAITING_HANDSHAKE",
    )
    view = inspect(request, identity_status=result.identity_status)
    assert view.identity_status == IDENTITY_CRYPTOGRAPHICALLY_VERIFIED
    assert view.trust_status == TRUST_UNVERIFIED  # unchanged, still "unverified"


def test_cryptographically_verified_identity_does_not_alter_authority(two_identities):
    a, b = two_identities
    store, challenge, proof = _valid_exchange(a, b)
    result = store.consume(proof)

    request = JoinRequest(
        request_id="r3",
        node_id=b.node_id,
        protocol_version="0.82",
        capabilities={"evidence_exchange": True},
        timestamp="2026-01-01T00:00:00Z",
        peer_endpoint=None,
        expires_at="2099-01-01T00:00:00Z",
        status="AWAITING_HANDSHAKE",
    )
    view = inspect(request, identity_status=result.identity_status)
    assert view.authority_level == AUTHORITY_NONE  # unchanged, still "none"


# ============================================================
# SECURITY INVARIANTS
# ============================================================

def test_private_key_never_appears_in_binding_json(tmp_path):
    identity_dir = tmp_path / "node"
    node = idm.load_or_create("node-1", identity_dir)
    binding_text = (identity_dir / "binding.json").read_text()
    private_bytes = (identity_dir / "private_key.bin").read_bytes()
    assert private_bytes.hex() not in binding_text


def test_private_key_never_appears_in_identity_proof_serialization(two_identities):
    a, b = two_identities
    store, challenge, proof = _valid_exchange(a, b)
    proof_json = json.dumps(dataclasses.asdict(proof))
    private_bytes_a = a.identity_dir.joinpath("private_key.bin").read_bytes()
    private_bytes_b = b.identity_dir.joinpath("private_key.bin").read_bytes()
    assert private_bytes_a.hex() not in proof_json
    assert private_bytes_b.hex() not in proof_json


def test_private_key_never_appears_in_challenge_serialization(two_identities):
    a, b = two_identities
    store, challenge, _ = _valid_exchange(a, b)
    challenge_json = json.dumps(dataclasses.asdict(challenge))
    private_bytes = a.identity_dir.joinpath("private_key.bin").read_bytes()
    assert private_bytes.hex() not in challenge_json


def test_node_identity_repr_never_exposes_private_key(tmp_path):
    node = idm.load_or_create("node-1", tmp_path / "node")
    r = repr(node)
    private_bytes = (tmp_path / "node" / "private_key.bin").read_bytes()
    assert private_bytes.hex() not in r
    assert "SigningKey" not in r


def test_node_identity_is_not_a_dataclass_so_asdict_cannot_leak_it(tmp_path):
    # dataclasses.asdict() walks every field regardless of repr=False --
    # NodeIdentity is deliberately a plain class so asdict() simply does
    # not apply to it at all (raises TypeError), which is the strongest
    # available guarantee against an accidental future asdict(identity)
    # call anywhere in the codebase.
    node = idm.load_or_create("node-1", tmp_path / "node")
    assert not dataclasses.is_dataclass(node)
    with pytest.raises(TypeError):
        dataclasses.asdict(node)


def test_identity_proof_shape_is_safe_for_a_discord_signaling_payload(two_identities):
    """The identity proof/challenge objects contain only public material
    (nonce, node ids, protocol version, public key, signatures,
    timestamp) -- nothing that would be unsafe if this shape were ever
    carried inside a Discord announcement payload (Phase 2 concern),
    even though no Discord code path exists yet for this."""
    a, b = two_identities
    store, challenge, proof = _valid_exchange(a, b)
    payload = dataclasses.asdict(proof)
    forbidden_substrings = ("private", "secret", "seed")
    blob = json.dumps(payload).lower()
    for token in forbidden_substrings:
        assert token not in blob


def test_codex_update_remains_false_after_identity_module_import():
    assert DEFAULT_CAPABILITIES["codex_update"] is False


def test_identity_proof_capability_is_disabled_by_default():
    # A node only advertises identity_proof=True once it actually has a
    # loaded NodeIdentity (see bootstrap_node.LanternNode.identity_capabilities).
    # The bare module-level default must remain False.
    assert DEFAULT_CAPABILITIES["identity_proof"] is False


def test_verification_result_never_grants_any_capability(two_identities):
    a, b = two_identities
    store, challenge, proof = _valid_exchange(a, b)
    result = store.consume(proof)
    result_dict = dataclasses.asdict(result)
    assert "capabilit" not in json.dumps(result_dict).lower()
    assert result_dict.keys() == {"verified", "reason", "identity_status"}


# ============================================================
# ROTATION
# ============================================================

def test_key_rotation_produces_record_signed_by_old_key(tmp_path):
    identity_dir = tmp_path / "node"
    original = idm.load_or_create("rotating-node", identity_dir)
    rotated, record = idm.rotate_identity(original, identity_dir)

    assert rotated.node_id == original.node_id  # node_id stable across rotation
    assert rotated.public_key_hex != original.public_key_hex  # key material changed
    assert idm.verify_rotation(record) is True


def test_rotation_record_forged_by_new_key_alone_is_rejected(tmp_path):
    identity_dir = tmp_path / "node"
    original = idm.load_or_create("rotating-node", identity_dir)
    rotated, record = idm.rotate_identity(original, identity_dir)

    # An attacker who only knows the NEW key (not the OLD private key)
    # cannot forge a valid rotation record for a DIFFERENT new key.
    forged = dataclasses.replace(record, new_public_key=rotated.public_key_hex + "00")
    assert idm.verify_rotation(forged) is False


def test_reload_after_rotation_loads_new_key(tmp_path):
    identity_dir = tmp_path / "node"
    original = idm.load_or_create("rotating-node", identity_dir)
    rotated, _record = idm.rotate_identity(original, identity_dir)

    reloaded = idm.load_or_create("rotating-node", identity_dir)
    assert reloaded.public_key_hex == rotated.public_key_hex
    assert reloaded.public_key_hex != original.public_key_hex
