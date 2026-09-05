"""
Lantern Secret Transfer Tests

Deterministic, in-process coverage for lantern.secret_transfer and its
wiring into bootstrap_node.LanternNode.offer_secret_transfer() /
receive_secret_transfer(). Complements the ad hoc live two/three-node
HTTP proof (which exercised the same code paths end-to-end over real
subprocesses and real sockets) with fast, deterministic pytest coverage
that isolates each behavior individually.

SECURITY NOTE: every "secret" value used in this file is a short-lived,
in-memory-only bytes object generated with secrets.token_bytes() inside
each test function. Nothing here is a real credential. No secret value
is ever printed, logged, or asserted directly -- only digests, lengths,
and control-flow/exception outcomes are checked, matching the module's
own guarantee that only sha256(secret) is safe to report.

Covers:
  MODULE-LEVEL (secret_transfer.py in isolation)
    - round-trip seal/open recovers the exact original bytes
    - tampered ciphertext is rejected (SecretTransferIntegrityError)
    - wrong ephemeral key pair is rejected
    - session_id/transfer_id relabeling is rejected
    - bad ephemeral-key binding signature is rejected
    - a replayed transfer_id is rejected by SecretTransferStore
    - the sealed envelope never contains the raw secret bytes

  NODE-LEVEL (bootstrap_node.LanternNode, in-process, no HTTP/subprocess)
    - full offer -> send round trip between two authorized nodes,
      receipt carries only digest/length, never plaintext
    - unauthorized peer (capability not granted) is rejected at both
      offer and send
    - request against a session bound to the wrong node_id is rejected
    - unknown/fake session_id is rejected
    - exact replay of a consumed transfer_id is rejected
    - tampered ciphertext is rejected at the node layer too
    - the 'secret_transfer' capability is present in DEFAULT_CAPABILITIES
      and in architecture.py's independent CANONICAL_CAPABILITIES
      reference (drift-detection parity)
"""

from __future__ import annotations

import hashlib
import secrets

import pytest
from nacl.public import PrivateKey

from lantern import bootstrap_node
from lantern import identity as idm
from lantern import secret_transfer as st
from lantern.architecture import CANONICAL_CAPABILITIES
from lantern.capability_authorization import AuthorizationPolicy
from lantern.compatibility import DEFAULT_CAPABILITIES


# ============================================================
# Fixtures / helpers
# ============================================================

@pytest.fixture
def two_identities(tmp_path):
    a = idm.load_or_create("secret-node-A", tmp_path / "id-a")
    b = idm.load_or_create("secret-node-B", tmp_path / "id-b")
    return a, b


@pytest.fixture
def two_nodes(tmp_path):
    """Two in-process LanternNode instances, mutually authorized for
    'secret_transfer', with each other's long-term public key already
    pinned in _known_public_keys (simulating a completed prior identity
    verification -- the real precondition for secret transfer)."""
    policy_a = AuthorizationPolicy.authorize(node_id="node-b", capabilities={"secret_transfer"})
    policy_b = AuthorizationPolicy.authorize(node_id="node-a", capabilities={"secret_transfer"})

    node_a = bootstrap_node.LanternNode(
        "node-a", tmp_path / "a" / "chronicle.json", identity_dir=tmp_path / "a" / "identity",
        authorization_policy=policy_a,
    )
    node_b = bootstrap_node.LanternNode(
        "node-b", tmp_path / "b" / "chronicle.json", identity_dir=tmp_path / "b" / "identity",
        authorization_policy=policy_b,
    )

    # Simulate a prior successful cryptographic identity verification in
    # both directions -- this is the actual precondition secret_transfer
    # relies on (bootstrap_node._known_public_keys, populated only after
    # CRYPTOGRAPHICALLY_VERIFIED proof in the real /identity/* flow).
    node_a._known_public_keys["node-b"] = node_b.crypto_identity.public_key_hex
    node_b._known_public_keys["node-a"] = node_a.crypto_identity.public_key_hex

    session_a_result = node_a.sessions.create_session(
        node_id="node-b", identity_status=idm.CRYPTOGRAPHICALLY_VERIFIED
    )
    session_b_result = node_b.sessions.create_session(
        node_id="node-a", identity_status=idm.CRYPTOGRAPHICALLY_VERIFIED
    )
    session_id_on_a = session_a_result.session.session_id  # A's record of B talking to it
    session_id_on_b = session_b_result.session.session_id  # B's record of A talking to it

    return {
        "node_a": node_a,
        "node_b": node_b,
        "session_id_on_a": session_id_on_a,  # used when calling node_a, claiming node_id="node-b"
        "session_id_on_b": session_id_on_b,  # used when calling node_b, claiming node_id="node-a"
    }


def _do_full_transfer(nodes: dict, secret: bytes, transfer_id: str | None = None) -> dict:
    """Drive a full offer(on B) -> seal(on A) -> send(to B) round trip
    entirely in-process. Returns node_b's receipt dict. Mirrors exactly
    what /secret/offer and /secret/send do over HTTP in bootstrap_node.py."""
    node_a, node_b = nodes["node_a"], nodes["node_b"]
    transfer_id = transfer_id or st.new_transfer_id()

    offer = node_b.offer_secret_transfer(nodes["session_id_on_b"], "node-a", transfer_id)
    assert offer["accepted"] is True, offer
    b_bundle = st.EphemeralKeyBundle(
        transfer_id=offer["bundle"]["transfer_id"],
        session_id=offer["bundle"]["session_id"],
        from_node_id=offer["bundle"]["from_node_id"],
        to_node_id=offer["bundle"]["to_node_id"],
        ephemeral_public_key_hex=offer["bundle"]["ephemeral_public_key"],
        binding_signature_hex=offer["bundle"]["binding_signature"],
    )
    st.verify_ephemeral_bundle(b_bundle, expected_public_key_hex=node_a._known_public_keys["node-b"])

    a_priv, a_bundle = st.create_ephemeral_bundle(
        transfer_id=transfer_id,
        session_id=nodes["session_id_on_b"],
        from_node_id="node-a",
        to_node_id="node-b",
        identity=node_a.crypto_identity,
    )
    sealed = st.seal_secret(
        my_ephemeral_private=a_priv,
        their_ephemeral_public_hex=b_bundle.ephemeral_public_key_hex,
        session_id=nodes["session_id_on_b"],
        transfer_id=transfer_id,
        secret=secret,
    )
    return node_b.receive_secret_transfer(
        nodes["session_id_on_b"], "node-a", transfer_id, a_bundle.to_dict(), sealed
    )


# ============================================================
# MODULE-LEVEL: secret_transfer.py in isolation
# ============================================================

def test_round_trip_recovers_exact_secret(two_identities):
    a, b = two_identities
    transfer_id = st.new_transfer_id()
    session_id = "sess-1"

    b_priv, b_bundle = st.create_ephemeral_bundle(
        transfer_id=transfer_id, session_id=session_id,
        from_node_id=b.node_id, to_node_id=a.node_id, identity=b,
    )
    a_priv, a_bundle = st.create_ephemeral_bundle(
        transfer_id=transfer_id, session_id=session_id,
        from_node_id=a.node_id, to_node_id=b.node_id, identity=a,
    )
    st.verify_ephemeral_bundle(a_bundle, expected_public_key_hex=a.public_key_hex)
    st.verify_ephemeral_bundle(b_bundle, expected_public_key_hex=b.public_key_hex)

    secret = secrets.token_bytes(40)
    sealed = st.seal_secret(
        my_ephemeral_private=a_priv, their_ephemeral_public_hex=b_bundle.ephemeral_public_key_hex,
        session_id=session_id, transfer_id=transfer_id, secret=secret,
    )
    recovered = st.open_secret(
        my_ephemeral_private=b_priv, their_ephemeral_public_hex=a_bundle.ephemeral_public_key_hex,
        sealed=sealed, expected_session_id=session_id, expected_transfer_id=transfer_id,
    )
    assert recovered == secret


def test_sealed_envelope_never_contains_raw_secret_hex(two_identities):
    a, b = two_identities
    transfer_id = st.new_transfer_id()
    session_id = "sess-2"
    b_priv, b_bundle = st.create_ephemeral_bundle(
        transfer_id=transfer_id, session_id=session_id, from_node_id=b.node_id,
        to_node_id=a.node_id, identity=b,
    )
    a_priv, _a_bundle = st.create_ephemeral_bundle(
        transfer_id=transfer_id, session_id=session_id, from_node_id=a.node_id,
        to_node_id=b.node_id, identity=a,
    )
    secret = secrets.token_bytes(32)
    sealed = st.seal_secret(
        my_ephemeral_private=a_priv, their_ephemeral_public_hex=b_bundle.ephemeral_public_key_hex,
        session_id=session_id, transfer_id=transfer_id, secret=secret,
    )
    assert set(sealed.keys()) == {
        "session_id", "transfer_id", "nonce", "ciphertext", "secret_length", "secret_sha256",
    }
    assert secret.hex() not in sealed["ciphertext"]
    assert sealed["secret_length"] == len(secret)
    assert sealed["secret_sha256"] == hashlib.sha256(secret).hexdigest()


def test_tampered_ciphertext_is_rejected(two_identities):
    a, b = two_identities
    transfer_id = st.new_transfer_id()
    session_id = "sess-3"
    b_priv, b_bundle = st.create_ephemeral_bundle(
        transfer_id=transfer_id, session_id=session_id, from_node_id=b.node_id,
        to_node_id=a.node_id, identity=b,
    )
    a_priv, a_bundle = st.create_ephemeral_bundle(
        transfer_id=transfer_id, session_id=session_id, from_node_id=a.node_id,
        to_node_id=b.node_id, identity=a,
    )
    sealed = st.seal_secret(
        my_ephemeral_private=a_priv, their_ephemeral_public_hex=b_bundle.ephemeral_public_key_hex,
        session_id=session_id, transfer_id=transfer_id, secret=secrets.token_bytes(24),
    )
    tampered = dict(sealed)
    flipped_byte = "00" if sealed["ciphertext"][:2] != "00" else "11"
    tampered["ciphertext"] = flipped_byte + sealed["ciphertext"][2:]

    with pytest.raises(st.SecretTransferIntegrityError):
        st.open_secret(
            my_ephemeral_private=b_priv, their_ephemeral_public_hex=a_bundle.ephemeral_public_key_hex,
            sealed=tampered, expected_session_id=session_id, expected_transfer_id=transfer_id,
        )


def test_wrong_ephemeral_key_pair_is_rejected(two_identities):
    a, b = two_identities
    transfer_id = st.new_transfer_id()
    session_id = "sess-4"
    b_priv, b_bundle = st.create_ephemeral_bundle(
        transfer_id=transfer_id, session_id=session_id, from_node_id=b.node_id,
        to_node_id=a.node_id, identity=b,
    )
    a_priv, a_bundle = st.create_ephemeral_bundle(
        transfer_id=transfer_id, session_id=session_id, from_node_id=a.node_id,
        to_node_id=b.node_id, identity=a,
    )
    sealed = st.seal_secret(
        my_ephemeral_private=a_priv, their_ephemeral_public_hex=b_bundle.ephemeral_public_key_hex,
        session_id=session_id, transfer_id=transfer_id, secret=secrets.token_bytes(16),
    )
    wrong_private = PrivateKey.generate()
    with pytest.raises(st.SecretTransferIntegrityError):
        st.open_secret(
            my_ephemeral_private=wrong_private, their_ephemeral_public_hex=a_bundle.ephemeral_public_key_hex,
            sealed=sealed, expected_session_id=session_id, expected_transfer_id=transfer_id,
        )


def test_session_or_transfer_id_relabeling_is_rejected(two_identities):
    a, b = two_identities
    transfer_id = st.new_transfer_id()
    session_id = "sess-5"
    b_priv, b_bundle = st.create_ephemeral_bundle(
        transfer_id=transfer_id, session_id=session_id, from_node_id=b.node_id,
        to_node_id=a.node_id, identity=b,
    )
    a_priv, a_bundle = st.create_ephemeral_bundle(
        transfer_id=transfer_id, session_id=session_id, from_node_id=a.node_id,
        to_node_id=b.node_id, identity=a,
    )
    sealed = st.seal_secret(
        my_ephemeral_private=a_priv, their_ephemeral_public_hex=b_bundle.ephemeral_public_key_hex,
        session_id=session_id, transfer_id=transfer_id, secret=secrets.token_bytes(16),
    )
    # Attacker relabels the outer session_id/transfer_id while presenting
    # a ciphertext sealed for a different context. Must be rejected even
    # though the ciphertext itself is untouched.
    with pytest.raises(st.SecretTransferIntegrityError):
        st.open_secret(
            my_ephemeral_private=b_priv, their_ephemeral_public_hex=a_bundle.ephemeral_public_key_hex,
            sealed=sealed, expected_session_id="different-session", expected_transfer_id=transfer_id,
        )


def test_bad_ephemeral_key_binding_signature_is_rejected(two_identities):
    a, b = two_identities
    transfer_id = st.new_transfer_id()
    session_id = "sess-6"
    _priv, bundle = st.create_ephemeral_bundle(
        transfer_id=transfer_id, session_id=session_id, from_node_id=a.node_id,
        to_node_id=b.node_id, identity=a,
    )
    # Verifying against the WRONG long-term public key (not a's real one)
    # must fail -- this is the MITM-substitution defense.
    with pytest.raises(st.EphemeralKeyBindingError):
        st.verify_ephemeral_bundle(bundle, expected_public_key_hex=b.public_key_hex)


def test_secret_transfer_store_rejects_replayed_transfer_id():
    store = st.SecretTransferStore()
    transfer_id = st.new_transfer_id()
    store.mark_consumed_or_raise(transfer_id)
    assert store.is_consumed(transfer_id) is True
    with pytest.raises(st.SecretTransferReplayError):
        store.mark_consumed_or_raise(transfer_id)


# ============================================================
# NODE-LEVEL: bootstrap_node.LanternNode in-process wiring
# ============================================================

def test_full_transfer_between_authorized_nodes_succeeds(two_nodes):
    secret = secrets.token_bytes(32)
    receipt = _do_full_transfer(two_nodes, secret)
    assert receipt["accepted"] is True
    assert receipt["secret_length"] == len(secret)
    assert receipt["secret_sha256"] == hashlib.sha256(secret).hexdigest()
    # The receipt must never carry the plaintext under any key.
    assert secret.hex() not in str(receipt)


def test_unauthorized_peer_cannot_offer_or_receive(tmp_path):
    # No AuthorizationPolicy grants -- default EMPTY_POLICY on both sides.
    node_a = bootstrap_node.LanternNode(
        "node-a", tmp_path / "a" / "chronicle.json", identity_dir=tmp_path / "a" / "identity",
    )
    node_b = bootstrap_node.LanternNode(
        "node-b", tmp_path / "b" / "chronicle.json", identity_dir=tmp_path / "b" / "identity",
    )
    node_a._known_public_keys["node-b"] = node_b.crypto_identity.public_key_hex
    node_b._known_public_keys["node-a"] = node_a.crypto_identity.public_key_hex
    session_result = node_b.sessions.create_session(
        node_id="node-a", identity_status=idm.CRYPTOGRAPHICALLY_VERIFIED
    )
    session_id = session_result.session.session_id

    offer = node_b.offer_secret_transfer(session_id, "node-a", st.new_transfer_id())
    assert offer["accepted"] is False
    assert "secret_transfer" in offer["reason"]

    receive = node_b.receive_secret_transfer(
        session_id, "node-a", st.new_transfer_id(), {}, {}
    )
    assert receive["accepted"] is False
    assert "secret_transfer" in receive["reason"]


def test_session_bound_to_wrong_node_id_is_rejected(two_nodes):
    node_b = two_nodes["node_b"]
    # session_id_on_b is bound to "node-a"; claim it belongs to an
    # unrelated third node_id instead.
    offer = node_b.offer_secret_transfer(
        two_nodes["session_id_on_b"], "some-other-node", st.new_transfer_id()
    )
    assert offer["accepted"] is False


def test_unknown_session_id_is_rejected(two_nodes):
    node_b = two_nodes["node_b"]
    offer = node_b.offer_secret_transfer("totally-fake-session-id", "node-a", st.new_transfer_id())
    assert offer["accepted"] is False


def test_replayed_transfer_id_is_rejected_end_to_end(two_nodes):
    secret = secrets.token_bytes(20)
    transfer_id = st.new_transfer_id()
    first = _do_full_transfer(two_nodes, secret, transfer_id=transfer_id)
    assert first["accepted"] is True

    # Re-offering the exact same transfer_id a second time and replaying
    # the original sealed payload against it must fail. Simplest
    # deterministic replay: call receive_secret_transfer again directly
    # with the already-consumed transfer_id -- the pending private key
    # has already been popped, so this exercises the
    # SECRET_TRANSFER_REPLAYED / unknown-transfer guard paths.
    node_b = two_nodes["node_b"]
    replay = node_b.receive_secret_transfer(
        two_nodes["session_id_on_b"], "node-a", transfer_id, {}, {}
    )
    assert replay["accepted"] is False
    assert "REPLAYED" in replay["reason"] or "UNKNOWN_TRANSFER" in replay["reason"]


def test_tampered_ciphertext_rejected_at_node_layer(two_nodes):
    node_a, node_b = two_nodes["node_a"], two_nodes["node_b"]
    transfer_id = st.new_transfer_id()

    offer = node_b.offer_secret_transfer(two_nodes["session_id_on_b"], "node-a", transfer_id)
    assert offer["accepted"] is True
    b_bundle = st.EphemeralKeyBundle(
        transfer_id=offer["bundle"]["transfer_id"], session_id=offer["bundle"]["session_id"],
        from_node_id=offer["bundle"]["from_node_id"], to_node_id=offer["bundle"]["to_node_id"],
        ephemeral_public_key_hex=offer["bundle"]["ephemeral_public_key"],
        binding_signature_hex=offer["bundle"]["binding_signature"],
    )
    a_priv, a_bundle = st.create_ephemeral_bundle(
        transfer_id=transfer_id, session_id=two_nodes["session_id_on_b"],
        from_node_id="node-a", to_node_id="node-b", identity=node_a.crypto_identity,
    )
    sealed = st.seal_secret(
        my_ephemeral_private=a_priv, their_ephemeral_public_hex=b_bundle.ephemeral_public_key_hex,
        session_id=two_nodes["session_id_on_b"], transfer_id=transfer_id,
        secret=secrets.token_bytes(28),
    )
    sealed["ciphertext"] = ("00" if sealed["ciphertext"][:2] != "00" else "11") + sealed["ciphertext"][2:]

    result = node_b.receive_secret_transfer(
        two_nodes["session_id_on_b"], "node-a", transfer_id, a_bundle.to_dict(), sealed
    )
    assert result["accepted"] is False
    assert "authenticated decryption failed" in result["reason"]


# ============================================================
# CAPABILITY REGISTRY PARITY
# ============================================================

def test_secret_transfer_capability_supported_by_default():
    assert DEFAULT_CAPABILITIES["secret_transfer"] is True


def test_secret_transfer_present_in_canonical_capabilities_reference():
    # architecture.py's CANONICAL_CAPABILITIES is a deliberately
    # independent, hand-maintained drift-detection reference -- it must
    # be updated in lockstep with compatibility.DEFAULT_CAPABILITIES any
    # time a real capability is added, never bypassed.
    assert CANONICAL_CAPABILITIES["secret_transfer"] == DEFAULT_CAPABILITIES["secret_transfer"]
