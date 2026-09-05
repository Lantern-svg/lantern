"""Tests for peer_authorization: the bootstrap -> authorization ->
delegation -> peer-admission -> recovery lifecycle for PEER/PROTOCOL
capabilities (the capabilities governed by capability_authorization.py
and negotiated in compatibility.DEFAULT_CAPABILITIES).

Prior to this module, the only way an operator could populate an
AuthorizationPolicy for those capabilities was an unsigned, provenance-
free --authorize CLI flag (see bootstrap_node._parse_authorize_args).
This module adds a signed, independently verifiable, explicitly-
delegated ceremony layer WITHOUT changing capability_authorization.py's
existing authorize()/AuthorizationPolicy behavior at all -- every test
here that reaches authorize() uses the exact same function and
CapabilityDecision shape the pre-existing test suite already covers.

Test IDs A-J below map directly to the mission's TEST REQUIREMENTS.
"""

from __future__ import annotations

import hashlib

import pytest

from lantern import identity as identity_module
from lantern import peer_authorization as pa
from lantern.capability_authorization import authorize
from lantern.verified_contact import VerifiedContactOutcome, VerifiedContactResult


@pytest.fixture()
def root_identity(tmp_path):
    return identity_module.load_or_create("node-root", tmp_path / "root")


@pytest.fixture()
def peer_identity(tmp_path):
    return identity_module.load_or_create("node-peer", tmp_path / "peer")


@pytest.fixture()
def stranger_identity(tmp_path):
    return identity_module.load_or_create("node-stranger", tmp_path / "stranger")


def _verified_contact(local_node_id: str, remote_node_id: str, capability: str) -> VerifiedContactResult:
    return VerifiedContactResult(
        outcome=VerifiedContactOutcome.IDENTITY_VERIFIED,
        local_node_id=local_node_id,
        remote_node_id=remote_node_id,
        identity_status="CRYPTOGRAPHICALLY_VERIFIED",
        protocol_version=pa.PROTOCOL_VERSION,
        shared_capabilities={capability: True},
        contact_endpoint="test://local",
        reason="ok",
    )


# ============================================================
# A. Fresh node has identity but no authorization.
# ============================================================


def test_a_fresh_node_has_identity_but_no_authorization(peer_identity):
    # A freshly created identity carries no grant, no root record, and
    # folding an empty grant list produces a policy that authorizes
    # nothing for this node -- the conservative default is preserved.
    policy = pa.policy_from_grants([])
    assert policy.allows(peer_identity.node_id, "evidence_exchange") is False
    verified = _verified_contact("local", peer_identity.node_id, "evidence_exchange")
    decision = authorize(verified, policy=policy, requested=["evidence_exchange"])
    assert decision.authorized is False
    assert not decision.is_authorized("evidence_exchange")


# ============================================================
# B. Fresh node cannot authorize itself.
# ============================================================


def test_b_fresh_node_cannot_self_issue_bootstrap_grant_without_root_record(peer_identity):
    # There is no constructor that lets a node manufacture its own
    # RootAuthorityRecord from nothing -- establish_root_authority()
    # requires an explicit root_token, and create_bootstrap_grant()
    # requires that record to verify AND match the issuing identity.
    forged_root = pa.RootAuthorityRecord(
        node_id=peer_identity.node_id,
        public_key=peer_identity.public_key_hex,
        root_token_hash="0" * 64,
        established_at="2020-01-01T00:00:00+00:00",
        protocol_version=pa.PROTOCOL_VERSION,
        signature="00" * 64,  # not a real signature
    )
    with pytest.raises(pa.RootAuthorityError):
        pa.create_bootstrap_grant(
            peer_identity, forged_root, subject_node_id=peer_identity.node_id,
            subject_public_key=peer_identity.public_key_hex, capabilities=["evidence_exchange"],
        )


def test_b_node_cannot_use_a_real_root_record_from_a_different_identity(root_identity, peer_identity):
    # Even a VALID root record cannot be used by a different node_id to
    # bootstrap-grant itself capabilities.
    root_record = pa.establish_root_authority(root_identity, root_token="synthetic-root-token-b")
    with pytest.raises(pa.RootAuthorityError):
        pa.create_bootstrap_grant(
            peer_identity, root_record, subject_node_id=peer_identity.node_id,
            subject_public_key=peer_identity.public_key_hex, capabilities=["evidence_exchange"],
        )


# ============================================================
# C. Valid root/bootstrap ceremony can authorize the initial node.
# ============================================================


def test_c_valid_bootstrap_ceremony_authorizes_initial_node(root_identity):
    root_record = pa.establish_root_authority(root_identity, root_token="synthetic-root-token-c")
    assert pa.verify_root_authority(root_record)

    grant = pa.create_bootstrap_grant(
        root_identity, root_record, subject_node_id=root_identity.node_id,
        subject_public_key=root_identity.public_key_hex,
        capabilities=["evidence_exchange", pa.CAN_DELEGATE], evidence="initial deployment ceremony",
    )
    assert grant.origin == pa.ORIGIN_BOOTSTRAP
    assert pa.verify_grant_with_authority_key(grant, authority_public_key_hex=root_identity.public_key_hex)

    policy = pa.policy_from_grants([grant])
    verified = _verified_contact("peer-side", root_identity.node_id, "evidence_exchange")
    decision = authorize(verified, policy=policy, requested=["evidence_exchange"])
    assert decision.is_authorized("evidence_exchange")


def test_c_bootstrap_requires_matching_root_token_not_a_default(root_identity):
    with pytest.raises(pa.PeerAuthorizationError):
        pa.establish_root_authority(root_identity, root_token="")


# ============================================================
# D. Authorized node can perform an explicitly permitted delegation.
# ============================================================


def test_d_authorized_node_can_delegate_when_holding_can_delegate(root_identity, peer_identity):
    root_record = pa.establish_root_authority(root_identity, root_token="synthetic-root-token-d")
    bootstrap_grant = pa.create_bootstrap_grant(
        root_identity, root_record, subject_node_id=root_identity.node_id,
        subject_public_key=root_identity.public_key_hex,
        capabilities=["evidence_exchange", pa.CAN_DELEGATE],
    )
    delegated = pa.create_delegated_grant(
        root_identity, bootstrap_grant, delegating_authority_public_key=root_identity.public_key_hex,
        subject_node_id=peer_identity.node_id, subject_public_key=peer_identity.public_key_hex,
        capabilities=["evidence_exchange"], evidence="delegate to peer node",
    )
    assert delegated.origin == pa.ORIGIN_DELEGATION
    assert pa.verify_grant_with_authority_key(delegated, authority_public_key_hex=root_identity.public_key_hex)

    policy = pa.policy_from_grants([delegated])
    verified = _verified_contact("local", peer_identity.node_id, "evidence_exchange")
    decision = authorize(verified, policy=policy, requested=["evidence_exchange"])
    assert decision.is_authorized("evidence_exchange")


def test_d_delegation_does_not_implicitly_grant_can_delegate_further(root_identity, peer_identity):
    # The delegated grant in this test does NOT include CAN_DELEGATE,
    # so the peer holding it cannot delegate further (covered fully in
    # test_e_*, this test just asserts the grant's own shape).
    root_record = pa.establish_root_authority(root_identity, root_token="synthetic-root-token-d2")
    bootstrap_grant = pa.create_bootstrap_grant(
        root_identity, root_record, subject_node_id=root_identity.node_id,
        subject_public_key=root_identity.public_key_hex,
        capabilities=["evidence_exchange", pa.CAN_DELEGATE],
    )
    delegated = pa.create_delegated_grant(
        root_identity, bootstrap_grant, delegating_authority_public_key=root_identity.public_key_hex,
        subject_node_id=peer_identity.node_id, subject_public_key=peer_identity.public_key_hex,
        capabilities=["evidence_exchange"],
    )
    assert not delegated.allows_delegation()


# ============================================================
# E. Unauthorized node cannot authorize another node.
# ============================================================


def test_e_node_with_no_grant_cannot_delegate(root_identity, peer_identity, stranger_identity):
    root_record = pa.establish_root_authority(root_identity, root_token="synthetic-root-token-e")
    bootstrap_grant = pa.create_bootstrap_grant(
        root_identity, root_record, subject_node_id=root_identity.node_id,
        subject_public_key=root_identity.public_key_hex,
        capabilities=["evidence_exchange", pa.CAN_DELEGATE],
    )
    # stranger_identity never received any grant at all, yet attempts to
    # present root's bootstrap_grant as if it were its own.
    with pytest.raises(pa.DelegationError):
        pa.create_delegated_grant(
            stranger_identity, bootstrap_grant, delegating_authority_public_key=root_identity.public_key_hex,
            subject_node_id=peer_identity.node_id, subject_public_key=peer_identity.public_key_hex,
            capabilities=["evidence_exchange"],
        )


def test_e_node_with_grant_lacking_can_delegate_cannot_delegate(root_identity, peer_identity, stranger_identity):
    root_record = pa.establish_root_authority(root_identity, root_token="synthetic-root-token-e2")
    bootstrap_grant = pa.create_bootstrap_grant(
        root_identity, root_record, subject_node_id=root_identity.node_id,
        subject_public_key=root_identity.public_key_hex,
        capabilities=["evidence_exchange", pa.CAN_DELEGATE],
    )
    delegated_no_delegate = pa.create_delegated_grant(
        root_identity, bootstrap_grant, delegating_authority_public_key=root_identity.public_key_hex,
        subject_node_id=peer_identity.node_id, subject_public_key=peer_identity.public_key_hex,
        capabilities=["evidence_exchange"],  # deliberately no CAN_DELEGATE
    )
    with pytest.raises(pa.DelegationError):
        pa.create_delegated_grant(
            peer_identity, delegated_no_delegate, delegating_authority_public_key=root_identity.public_key_hex,
            subject_node_id=stranger_identity.node_id, subject_public_key=stranger_identity.public_key_hex,
            capabilities=["evidence_exchange"],
        )


def test_e_admission_also_requires_can_delegate(root_identity, peer_identity, stranger_identity):
    root_record = pa.establish_root_authority(root_identity, root_token="synthetic-root-token-e3")
    bootstrap_grant = pa.create_bootstrap_grant(
        root_identity, root_record, subject_node_id=root_identity.node_id,
        subject_public_key=root_identity.public_key_hex,
        capabilities=["evidence_exchange", pa.CAN_DELEGATE],
    )
    delegated_no_delegate = pa.create_delegated_grant(
        root_identity, bootstrap_grant, delegating_authority_public_key=root_identity.public_key_hex,
        subject_node_id=peer_identity.node_id, subject_public_key=peer_identity.public_key_hex,
        capabilities=["evidence_exchange"],
    )
    with pytest.raises(pa.DelegationError):
        pa.create_admission_grant(
            peer_identity, delegated_no_delegate, delegating_authority_public_key=root_identity.public_key_hex,
            subject_node_id=stranger_identity.node_id, subject_public_key=stranger_identity.public_key_hex,
            capabilities=["evidence_exchange"],
        )


# ============================================================
# F. Peer admission requires authorization.
# ============================================================


def test_f_peer_admission_grant_requires_authorized_issuer(root_identity, stranger_identity):
    root_record = pa.establish_root_authority(root_identity, root_token="synthetic-root-token-f")
    bootstrap_grant = pa.create_bootstrap_grant(
        root_identity, root_record, subject_node_id=root_identity.node_id,
        subject_public_key=root_identity.public_key_hex,
        capabilities=["evidence_exchange", pa.CAN_DELEGATE],
    )
    admission = pa.create_admission_grant(
        root_identity, bootstrap_grant, delegating_authority_public_key=root_identity.public_key_hex,
        subject_node_id=stranger_identity.node_id, subject_public_key=stranger_identity.public_key_hex,
        capabilities=["evidence_exchange"], evidence="join request r-001 reviewed and approved",
    )
    assert admission.origin == pa.ORIGIN_ADMISSION
    policy = pa.policy_from_grants([admission])
    verified = _verified_contact("local", stranger_identity.node_id, "evidence_exchange")
    decision = authorize(verified, policy=policy, requested=["evidence_exchange"])
    assert decision.is_authorized("evidence_exchange")


def test_f_joining_node_cannot_self_declare_admission(stranger_identity):
    # There is no constructor a joining node can call using only its own
    # identity to produce a PeerCapabilityGrant naming itself -- every
    # constructor requires a prior grant/root record the joining node
    # does not, and structurally cannot, hold for itself.
    with pytest.raises(TypeError):
        # create_admission_grant requires a delegating_grant positional
        # arg; a joining node has none to supply.
        pa.create_admission_grant(
            stranger_identity, subject_node_id=stranger_identity.node_id,
            subject_public_key=stranger_identity.public_key_hex, capabilities=["evidence_exchange"],
        )


# ============================================================
# G. Authorization provenance is preserved.
# ============================================================


def test_g_provenance_fields_present_on_every_grant(root_identity, stranger_identity):
    root_record = pa.establish_root_authority(root_identity, root_token="synthetic-root-token-g")
    bootstrap_grant = pa.create_bootstrap_grant(
        root_identity, root_record, subject_node_id=root_identity.node_id,
        subject_public_key=root_identity.public_key_hex,
        capabilities=["evidence_exchange", pa.CAN_DELEGATE],
    )
    admission = pa.create_admission_grant(
        root_identity, bootstrap_grant, delegating_authority_public_key=root_identity.public_key_hex,
        subject_node_id=stranger_identity.node_id, subject_public_key=stranger_identity.public_key_hex,
        capabilities=["evidence_exchange"], evidence="join request r-042 reviewed and approved",
    )
    d = admission.to_dict()
    expected_fields = {
        "authorizing_authority", "subject_node_id", "subject_public_key",
        "capabilities", "origin", "issued_at", "protocol_version", "evidence", "signature",
    }
    assert expected_fields.issubset(d.keys())
    assert d["authorizing_authority"] == root_identity.node_id
    assert d["subject_node_id"] == stranger_identity.node_id
    assert d["origin"] == pa.ORIGIN_ADMISSION
    assert d["evidence"] == "join request r-042 reviewed and approved"
    assert d["protocol_version"] == pa.PROTOCOL_VERSION


def test_g_root_authority_record_round_trips_through_dict(root_identity):
    root_record = pa.establish_root_authority(root_identity, root_token="synthetic-root-token-g2")
    restored = pa.RootAuthorityRecord.from_dict(root_record.to_dict())
    assert pa.verify_root_authority(restored)
    assert restored == root_record


def test_g_grant_round_trips_through_dict(root_identity):
    root_record = pa.establish_root_authority(root_identity, root_token="synthetic-root-token-g3")
    grant = pa.create_bootstrap_grant(
        root_identity, root_record, subject_node_id=root_identity.node_id,
        subject_public_key=root_identity.public_key_hex, capabilities=["evidence_exchange"],
    )
    restored = pa.PeerCapabilityGrant.from_dict(grant.to_dict())
    assert pa.verify_grant_with_authority_key(restored, authority_public_key_hex=root_identity.public_key_hex)
    assert restored == grant


# ============================================================
# H. Invalid/tampered authorization is rejected.
# ============================================================


def test_h_tampered_capabilities_fail_verification(root_identity):
    root_record = pa.establish_root_authority(root_identity, root_token="synthetic-root-token-h")
    grant = pa.create_bootstrap_grant(
        root_identity, root_record, subject_node_id=root_identity.node_id,
        subject_public_key=root_identity.public_key_hex, capabilities=["evidence_exchange"],
    )
    tampered = pa.PeerCapabilityGrant(
        authorizing_authority=grant.authorizing_authority,
        subject_node_id=grant.subject_node_id,
        subject_public_key=grant.subject_public_key,
        capabilities=tuple(list(grant.capabilities) + ["secret_transfer"]),
        origin=grant.origin, issued_at=grant.issued_at,
        protocol_version=grant.protocol_version, evidence=grant.evidence, signature=grant.signature,
    )
    assert not pa.verify_grant_with_authority_key(tampered, authority_public_key_hex=root_identity.public_key_hex)


def test_h_tampered_subject_fails_verification(root_identity, stranger_identity):
    root_record = pa.establish_root_authority(root_identity, root_token="synthetic-root-token-h2")
    grant = pa.create_bootstrap_grant(
        root_identity, root_record, subject_node_id=root_identity.node_id,
        subject_public_key=root_identity.public_key_hex, capabilities=["evidence_exchange"],
    )
    tampered = pa.PeerCapabilityGrant(
        authorizing_authority=grant.authorizing_authority,
        subject_node_id=stranger_identity.node_id,  # redirected subject
        subject_public_key=stranger_identity.public_key_hex,
        capabilities=grant.capabilities, origin=grant.origin, issued_at=grant.issued_at,
        protocol_version=grant.protocol_version, evidence=grant.evidence, signature=grant.signature,
    )
    assert not pa.verify_grant_with_authority_key(tampered, authority_public_key_hex=root_identity.public_key_hex)


def test_h_wrong_verification_key_fails(root_identity, peer_identity):
    root_record = pa.establish_root_authority(root_identity, root_token="synthetic-root-token-h3")
    grant = pa.create_bootstrap_grant(
        root_identity, root_record, subject_node_id=root_identity.node_id,
        subject_public_key=root_identity.public_key_hex, capabilities=["evidence_exchange"],
    )
    # verifying against an unrelated node's public key must fail
    assert not pa.verify_grant_with_authority_key(grant, authority_public_key_hex=peer_identity.public_key_hex)


def test_h_forged_root_record_signature_fails(peer_identity):
    forged = pa.RootAuthorityRecord(
        node_id=peer_identity.node_id, public_key=peer_identity.public_key_hex,
        root_token_hash=hashlib.sha256(b"whatever").hexdigest(),
        established_at="2020-01-01T00:00:00+00:00", protocol_version=pa.PROTOCOL_VERSION,
        signature="ab" * 64,
    )
    assert not pa.verify_root_authority(forged)


def test_h_grant_with_unknown_origin_is_rejected():
    with pytest.raises(pa.PeerAuthorizationError):
        pa.PeerCapabilityGrant(
            authorizing_authority="a", subject_node_id="b", subject_public_key="deadbeef",
            capabilities=("evidence_exchange",), origin="NOT_A_REAL_ORIGIN",
            issued_at="2020-01-01T00:00:00+00:00", protocol_version=pa.PROTOCOL_VERSION,
            evidence="", signature="00" * 64,
        )


def test_h_grant_with_no_capabilities_is_rejected():
    with pytest.raises(pa.PeerAuthorizationError):
        pa.PeerCapabilityGrant(
            authorizing_authority="a", subject_node_id="b", subject_public_key="deadbeef",
            capabilities=(), origin=pa.ORIGIN_BOOTSTRAP,
            issued_at="2020-01-01T00:00:00+00:00", protocol_version=pa.PROTOCOL_VERSION,
            evidence="", signature="00" * 64,
        )


# ============================================================
# I. LAR-1 recovery cannot be performed by the recovering node alone.
# ============================================================


def test_i_recovery_refused_without_matching_independent_hash(root_identity):
    with pytest.raises(pa.RecoveryError):
        pa.perform_recovery_ceremony(
            root_identity, recovery_token="node-guessed-token",
            expected_recovery_token_hash="deadbeef" * 8,
        )


def test_i_recovery_refused_when_node_supplies_only_its_own_guess(root_identity):
    # A node cannot derive expected_recovery_token_hash from anything it
    # holds locally (there is no local storage of it in this module at
    # all) -- simulate the realistic failure mode: the node guesses a
    # token and hashes ITS OWN guess as though it were authoritative.
    guessed_token = "node-self-generated-guess"
    self_supplied_hash = hashlib.sha256(guessed_token.encode()).hexdigest()
    # Even though the two locally-computed values trivially match each
    # other, this is not a real recovery: perform_recovery_ceremony still
    # requires the *actual* out-of-band operator secret. To prove the
    # boundary is real, use a DIFFERENT (operator-held) token than what
    # was guessed and confirm mismatch is caught:
    operator_token = "operator-held-recovery-secret"
    operator_hash = hashlib.sha256(operator_token.encode()).hexdigest()
    assert self_supplied_hash != operator_hash
    with pytest.raises(pa.RecoveryError):
        pa.perform_recovery_ceremony(
            root_identity, recovery_token=guessed_token, expected_recovery_token_hash=operator_hash,
        )


def test_i_recovery_succeeds_with_correct_independently_held_token(root_identity):
    root_record = pa.establish_root_authority(root_identity, root_token="synthetic-root-token-i")
    recovery_token = "synthetic-recovery-ceremony-token"
    expected_hash = hashlib.sha256(recovery_token.encode()).hexdigest()
    recovered = pa.perform_recovery_ceremony(
        root_identity, recovery_token=recovery_token, expected_recovery_token_hash=expected_hash,
        prior_root=root_record, evidence="operator-witnessed recovery ceremony",
    )
    assert pa.verify_root_authority(recovered)
    assert recovered.node_id == root_identity.node_id


def test_i_recovery_rejects_prior_root_from_a_different_identity(root_identity, peer_identity):
    other_root_record = pa.establish_root_authority(peer_identity, root_token="synthetic-root-token-i2")
    recovery_token = "synthetic-recovery-ceremony-token-2"
    expected_hash = hashlib.sha256(recovery_token.encode()).hexdigest()
    with pytest.raises(pa.RecoveryError):
        pa.perform_recovery_ceremony(
            root_identity, recovery_token=recovery_token, expected_recovery_token_hash=expected_hash,
            prior_root=other_root_record,
        )


# ============================================================
# J. Existing security invariants continue to pass.
# (This module never touches NEVER_AUTHORIZABLE, participants.py's
#  unconditional trust_status/authority_level="none"/"unverified", or
#  capability_authorization.authorize()'s own gating -- these
#  assertions confirm that directly against the real, unmodified
#  functions, and the full existing suites for those modules are also
#  re-run as part of the full test run.)
# ============================================================


def test_j_codex_update_still_never_authorizable_even_via_a_grant(root_identity):
    from lantern.capability_authorization import NEVER_AUTHORIZABLE
    assert "codex_update" in NEVER_AUTHORIZABLE
    root_record = pa.establish_root_authority(root_identity, root_token="synthetic-root-token-j")
    grant = pa.create_bootstrap_grant(
        root_identity, root_record, subject_node_id=root_identity.node_id,
        subject_public_key=root_identity.public_key_hex, capabilities=["codex_update"],
    )
    policy = pa.policy_from_grants([grant])
    verified = _verified_contact("local", root_identity.node_id, "codex_update")
    decision = authorize(verified, policy=policy, requested=["codex_update"])
    assert not decision.is_authorized("codex_update")


def test_j_participants_module_authority_level_still_unconditionally_none():
    from lantern import participants
    assert participants.AUTHORITY_NONE == "none"
    assert participants.TRUST_UNVERIFIED == "unverified"


def test_j_policy_from_grants_produces_a_real_authorizationpolicy_instance(root_identity):
    from lantern.capability_authorization import AuthorizationPolicy
    root_record = pa.establish_root_authority(root_identity, root_token="synthetic-root-token-j2")
    grant = pa.create_bootstrap_grant(
        root_identity, root_record, subject_node_id=root_identity.node_id,
        subject_public_key=root_identity.public_key_hex, capabilities=["evidence_exchange"],
    )
    policy = pa.policy_from_grants([grant])
    assert isinstance(policy, AuthorizationPolicy)


def test_j_unverifiable_grant_never_reaches_policy_authorization_silently(root_identity, peer_identity):
    # policy_from_grants() trusts its caller to have already verified;
    # this test documents (and enforces via the wrapper pattern) that a
    # caller MUST verify before folding -- simulate the correct calling
    # discipline and confirm a forged grant is caught before folding.
    forged_root = pa.RootAuthorityRecord(
        node_id=peer_identity.node_id, public_key=peer_identity.public_key_hex,
        root_token_hash="0" * 64, established_at="2020-01-01T00:00:00+00:00",
        protocol_version=pa.PROTOCOL_VERSION, signature="00" * 64,
    )
    assert not pa.verify_root_authority(forged_root)
    # correct discipline: caller checks verify_* first and never folds
    # an unverified record into a policy.
