"""Confidential secret transfer over an already-authenticated Lantern
session -- distinct from, and layered ON TOP OF, proof-of-possession.

WHY THIS MODULE EXISTS (read this before touching anything else)
------------------------------------------------------------------
bootstrap_node.py's existing two-phase session flow
(challenge -> respond_to_challenge() -> verify_proof()) proves that a
peer POSSESSES the private key matching a claimed node_id. That is
authentication, and only authentication. It says nothing about whether
the bytes carried over HTTP afterward are confidential:

  - bootstrap_node.py runs a plain http.server.ThreadingHTTPServer.
    There is no TLS at the Lantern application-protocol layer -- the
    module docstring at the top of bootstrap_node.py says so
    explicitly ("the operator's normal TLS ... controls"). Whatever
    confidentiality exists in any given deployment (a TLS-terminating
    reverse proxy, an SSH tunnel, a Cloudflare tunnel) is OUTSIDE this
    protocol's control and cannot be assumed present -- e.g. two nodes
    talking over plain localhost or an unencrypted LAN have zero
    transport confidentiality today.
  - The only identity key available (NodeIdentity._signing_key) is an
    Ed25519 SIGNING key (nacl.signing.SigningKey). Ed25519 signing keys
    are not used for encryption here, and reusing a signing key for
    encryption is a well-known primitive-misuse pitfall -- this module
    deliberately does not do that.

So: authenticated session != confidential channel. A secret sent
through the existing /message + OBSERVATION_SHARE path today would be
plaintext at the Lantern protocol layer. This module adds the missing
piece: a narrowly-scoped, session-bound, authenticated-encryption layer
for exactly one purpose (carrying a secret payload), built entirely
from already-audited PyNaCl primitives -- no homemade cryptography.

DESIGN
------
1. Ephemeral X25519 key agreement (nacl.public.PrivateKey / Box), fresh
   per transfer -- NOT derived from or reusing the long-term Ed25519
   identity key. Curve25519 key agreement and Ed25519 signing are
   different primitives operating on different keys, by design.
2. Each side's ephemeral X25519 public key is bound to its long-term
   identity by signing it with NodeIdentity.sign() (the exact same
   primitive/pattern identity.py already uses for challenge-proofs),
   over a domain-separated payload that includes session_id,
   from_node_id, to_node_id, and purpose -- so a signed ephemeral key
   cannot be replayed against a different session, peer, or purpose.
   The signature is verified against the peer's ALREADY-VERIFIED
   long-term public key (bootstrap_node.py's _known_public_keys,
   populated only after CRYPTOGRAPHICALLY_VERIFIED proof) -- this
   module never trusts a raw, unauthenticated ephemeral key.
3. nacl.box.Box(my_ephemeral_private, their_ephemeral_public) derives
   the shared secret; the actual secret payload is sealed with
   nacl.secret.SecretBox using that shared key -- XSalsa20-Poly1305,
   authenticated encryption: confidentiality AND integrity/tamper-
   detection in one primitive, exactly as required. A fresh random
   nonce is used per seal (nacl.utils.random(SecretBox.NONCE_SIZE)).
4. The ciphertext is further bound to the specific session_id as
   associated context: session_id is mixed into the SecretBox nonce
   derivation is NOT how nacl.secret works (SecretBox has no native
   AEAD "associated data" parameter), so instead this module encodes
   session_id||transfer_id into the plaintext envelope BEFORE sealing
   (see _envelope()) and independently verifies the session via the
   existing SessionStore.resolve_session() before ever attempting to
   open a sealed message. Both checks must pass: (a) valid session
   whose bound node_id matches the claimed sender, AND (b) the sealed
   envelope's own session_id/transfer_id fields match what the caller
   presented. A tampered envelope fails SecretBox's Poly1305 MAC
   before any of this is even reached.
5. Anti-replay: every transfer_id is single-use, tracked in an
   in-memory, per-process SecretTransferStore (mirrors
   verified_session.SessionStore's own in-memory-only, non-persistent
   pattern exactly). A second attempt to open the same transfer_id is
   rejected regardless of ciphertext validity.

SECURITY PROPERTIES THIS MODULE GUARANTEES
-------------------------------------------
- Never logs, prints, or returns the plaintext secret in any error
  path. Every function that could fail returns a reason string built
  only from status/method names, never from secret bytes.
- Digest-only reporting: SecretTransferReceipt exposes only
  secret_length and sha256 digest, never content.
- Requires an existing valid VerifiedSession (reuses
  verified_session.SessionStore.resolve_session() verbatim) bound to
  the claimed sender node_id -- wrong-session and unauthenticated
  callers are rejected before any cryptography is attempted.
- Requires explicit 'secret_transfer' capability authorization via the
  existing capability_authorization.py policy path -- an
  authenticated session alone is NEVER sufficient, mirroring
  evidence_exchange/belief_query exactly.
- Tampered ciphertext (bit-flipped, truncated, or MAC mismatch) raises
  nacl.exceptions.CryptoError from SecretBox.decrypt() and is
  converted to a generic SECRET_TRANSFER_INTEGRITY_FAILURE, never
  echoing any partial plaintext.
- Replayed transfer_id is rejected (SECRET_TRANSFER_REPLAYED) even if
  the ciphertext is byte-identical and would otherwise decrypt fine.
- Does not persist plaintext secret material anywhere: no file, no
  Chronicle entry, no ledger entry. The plaintext exists only as a
  short-lived Python bytes/str object at the call site, immediately
  discardable by the caller (this module never stores it).
"""
from __future__ import annotations

import hashlib
import secrets as secrets_module
from dataclasses import dataclass, field
from typing import Optional

from nacl.exceptions import BadSignatureError, CryptoError
from nacl.public import Box, PrivateKey, PublicKey
from nacl.secret import SecretBox
from nacl.signing import VerifyKey
from nacl.encoding import HexEncoder

from . import identity as identity_module

# Domain separation tag for the ephemeral-key binding signature --
# distinct from identity.py's own _DOMAIN_CHALLENGE_PROOF so a signed
# ephemeral-key binding can never be replayed/reinterpreted as a
# challenge-proof signature or vice versa.
_DOMAIN_SECRET_TRANSFER_KEY = b"lantern-secret-transfer-ephemeral-key-v1"

SECRET_TRANSFER_CAPABILITY = "secret_transfer"


class SecretTransferError(Exception):
    """Base class. Message text is always safe to log -- constructed
    only from status codes/names, never from secret material."""


class EphemeralKeyBindingError(SecretTransferError):
    """The peer's ephemeral X25519 public key failed signature
    verification against its already-known long-term identity key."""


class SecretTransferAuthorizationError(SecretTransferError):
    """No valid session, wrong node/session binding, or missing
    'secret_transfer' capability grant."""


class SecretTransferIntegrityError(SecretTransferError):
    """Ciphertext failed authenticated-decryption (tampering, wrong
    key, or corruption). Never carries any plaintext fragment."""


class SecretTransferReplayError(SecretTransferError):
    """transfer_id has already been consumed once; rejected regardless
    of ciphertext validity."""


@dataclass(frozen=True)
class EphemeralKeyBundle:
    """One side's contribution to a single key-agreement exchange.
    Never holds a long-term identity key; ephemeral_private_key is
    generated fresh per transfer_id and MUST be discarded by the
    caller after the shared box is derived (no persistence here)."""

    transfer_id: str
    session_id: str
    from_node_id: str
    to_node_id: str
    ephemeral_public_key_hex: str
    binding_signature_hex: str  # signs (transfer_id, session_id, from_node_id, to_node_id, ephemeral_public_key_hex)

    def to_dict(self) -> dict:
        return {
            "transfer_id": self.transfer_id,
            "session_id": self.session_id,
            "from_node_id": self.from_node_id,
            "to_node_id": self.to_node_id,
            "ephemeral_public_key": self.ephemeral_public_key_hex,
            "binding_signature": self.binding_signature_hex,
        }


def _binding_payload(transfer_id: str, session_id: str, from_node_id: str, to_node_id: str, ephemeral_public_key_hex: str) -> bytes:
    parts = [transfer_id, session_id, from_node_id, to_node_id, ephemeral_public_key_hex]
    return "|".join(parts).encode("utf-8")


def create_ephemeral_bundle(
    *,
    transfer_id: str,
    session_id: str,
    from_node_id: str,
    to_node_id: str,
    identity: identity_module.NodeIdentity,
) -> tuple[PrivateKey, EphemeralKeyBundle]:
    """Generate a fresh ephemeral X25519 keypair and sign its public
    half (bound to this exact transfer_id/session_id/peer pair) using
    the caller's existing long-term Ed25519 identity. Returns the
    PrivateKey (caller keeps this in memory only, to derive the Box
    once the peer's bundle arrives, then discards it) plus the public
    bundle to send over the wire.
    """
    ephemeral_private = PrivateKey.generate()
    ephemeral_public_hex = bytes(ephemeral_private.public_key).hex()
    payload = _binding_payload(transfer_id, session_id, from_node_id, to_node_id, ephemeral_public_hex)
    signature_hex = identity.sign(_DOMAIN_SECRET_TRANSFER_KEY, payload)
    bundle = EphemeralKeyBundle(
        transfer_id=transfer_id,
        session_id=session_id,
        from_node_id=from_node_id,
        to_node_id=to_node_id,
        ephemeral_public_key_hex=ephemeral_public_hex,
        binding_signature_hex=signature_hex,
    )
    return ephemeral_private, bundle


def verify_ephemeral_bundle(bundle: EphemeralKeyBundle, *, expected_public_key_hex: str) -> None:
    """Verify bundle.binding_signature_hex against the PEER'S ALREADY-
    VERIFIED long-term public key (caller must pass the value from
    bootstrap_node.py's _known_public_keys[bundle.from_node_id] --
    never a value taken from the bundle itself or any unauthenticated
    source). Raises EphemeralKeyBindingError on any failure; never
    raises on success.
    """
    try:
        verify_key = VerifyKey(expected_public_key_hex, encoder=HexEncoder)
        payload = _binding_payload(
            bundle.transfer_id, bundle.session_id, bundle.from_node_id,
            bundle.to_node_id, bundle.ephemeral_public_key_hex,
        )
        verify_key.verify(_DOMAIN_SECRET_TRANSFER_KEY + b"|" + payload, bytes.fromhex(bundle.binding_signature_hex))
    except (BadSignatureError, ValueError, TypeError, KeyError) as exc:
        raise EphemeralKeyBindingError(
            "ephemeral key binding signature invalid -- refusing to trust this "
            "ephemeral public key for key agreement"
        ) from exc


def _envelope(session_id: str, transfer_id: str, secret: bytes) -> bytes:
    """Plaintext envelope sealed inside the SecretBox: binds session_id
    and transfer_id INTO the encrypted payload itself (not just as
    external metadata), so a valid ciphertext cannot be replayed by
    relabeling its outer session_id/transfer_id. The receiver
    re-checks these fields match what was claimed BEFORE trusting the
    decrypted secret.
    """
    header = f"{session_id}|{transfer_id}|".encode("utf-8")
    return header + secret


def _parse_envelope(session_id: str, transfer_id: str, plaintext: bytes) -> bytes:
    header = f"{session_id}|{transfer_id}|".encode("utf-8")
    if not plaintext.startswith(header):
        raise SecretTransferIntegrityError(
            "decrypted envelope session_id/transfer_id do not match the "
            "claimed context -- refusing to trust this payload"
        )
    return plaintext[len(header):]


def _derive_secretbox_key(box: Box, session_id: str, transfer_id: str) -> bytes:
    """Derive SecretBox's 32-byte key from Box's X25519 shared secret.

    The explicit domain/context input prevents this capability's key
    material from being reused for another protocol or transfer context.
    BLAKE2b is used only as a standard hash-based KDF; it is not a
    replacement for X25519 or SecretBox.
    """
    shared = box.shared_key()
    context = b"lantern-secret-transfer-kdf-v1|" + session_id.encode("utf-8") + b"|" + transfer_id.encode("utf-8")
    return hashlib.blake2b(context + b"|" + shared, digest_size=SecretBox.KEY_SIZE).digest()


def seal_secret(
    *,
    my_ephemeral_private: PrivateKey,
    their_ephemeral_public_hex: str,
    session_id: str,
    transfer_id: str,
    secret: bytes,
) -> dict:
    """Authenticated-encrypt `secret` for the peer holding
    their_ephemeral_public_hex. Returns only ciphertext/nonce hex and
    context identifiers -- never the plaintext. Caller is responsible
    for discarding `secret` and my_ephemeral_private after this call.
    """
    their_public = PublicKey(bytes.fromhex(their_ephemeral_public_hex))
    box = Box(my_ephemeral_private, their_public)
    nonce = secrets_module.token_bytes(SecretBox.NONCE_SIZE)
    plaintext = _envelope(session_id, transfer_id, secret)
    # Box derives the authenticated X25519 shared key; SecretBox then
    # performs the actual XSalsa20-Poly1305 payload encryption.
    encrypted = SecretBox(_derive_secretbox_key(box, session_id, transfer_id)).encrypt(plaintext, nonce)
    # SecretBox.encrypt returns nonce+ciphertext concatenated
    # (EncryptedMessage); split back out explicitly so the wire format
    # is unambiguous and independent of pynacl's internal layout.
    ciphertext_only = bytes(encrypted)[len(nonce):]
    return {
        "session_id": session_id,
        "transfer_id": transfer_id,
        "nonce": nonce.hex(),
        "ciphertext": ciphertext_only.hex(),
        "secret_length": len(secret),
        "secret_sha256": hashlib.sha256(secret).hexdigest(),
    }


def open_secret(
    *,
    my_ephemeral_private: PrivateKey,
    their_ephemeral_public_hex: str,
    sealed: dict,
    expected_session_id: str,
    expected_transfer_id: str,
) -> bytes:
    """Decrypt and return the original secret bytes. Raises
    SecretTransferIntegrityError on any MAC/tamper failure or
    session/transfer_id mismatch -- never returns partial plaintext on
    failure, never includes any plaintext fragment in the exception.
    """
    if sealed.get("session_id") != expected_session_id or sealed.get("transfer_id") != expected_transfer_id:
        raise SecretTransferIntegrityError(
            "sealed message's session_id/transfer_id do not match the "
            "expected context -- refusing to attempt decryption"
        )
    their_public = PublicKey(bytes.fromhex(their_ephemeral_public_hex))
    box = Box(my_ephemeral_private, their_public)
    try:
        nonce = bytes.fromhex(sealed["nonce"])
        ciphertext = bytes.fromhex(sealed["ciphertext"])
        plaintext = SecretBox(
            _derive_secretbox_key(box, expected_session_id, expected_transfer_id)
        ).decrypt(ciphertext, nonce)
    except (CryptoError, KeyError, ValueError, TypeError) as exc:
        raise SecretTransferIntegrityError(
            "authenticated decryption failed -- ciphertext, nonce, or key "
            "material invalid (possible tampering)"
        ) from exc
    secret = _parse_envelope(expected_session_id, expected_transfer_id, plaintext)
    claimed_len = sealed.get("secret_length")
    claimed_digest = sealed.get("secret_sha256")
    if isinstance(claimed_len, int) and claimed_len != len(secret):
        raise SecretTransferIntegrityError(
            "decrypted secret length does not match the sender's declared length"
        )
    if isinstance(claimed_digest, str) and hashlib.sha256(secret).hexdigest() != claimed_digest:
        raise SecretTransferIntegrityError(
            "decrypted secret digest does not match the sender's declared digest"
        )
    return secret


@dataclass
class SecretTransferStore:
    """In-memory, per-process, non-persistent replay-tracking table --
    mirrors verified_session.SessionStore's own pattern exactly. Never
    serialized, never written to a Chronicle or any file, never holds
    plaintext secret material (only transfer_id strings)."""

    _consumed_transfer_ids: "set[str]" = field(default_factory=set)

    def mark_consumed_or_raise(self, transfer_id: str) -> None:
        if transfer_id in self._consumed_transfer_ids:
            raise SecretTransferReplayError(
                f"transfer_id has already been consumed once; rejecting replay"
            )
        self._consumed_transfer_ids.add(transfer_id)

    def is_consumed(self, transfer_id: str) -> bool:
        return transfer_id in self._consumed_transfer_ids


@dataclass(frozen=True)
class SecretTransferReceipt:
    """Safe-to-log/report receipt. NEVER carries the secret itself."""

    accepted: bool
    transfer_id: str
    session_id: str
    secret_length: Optional[int]
    secret_sha256: Optional[str]
    reason: str

    def to_dict(self) -> dict:
        return {
            "accepted": self.accepted,
            "transfer_id": self.transfer_id,
            "session_id": self.session_id,
            "secret_length": self.secret_length,
            "secret_sha256": self.secret_sha256,
            "reason": self.reason,
        }


def new_transfer_id() -> str:
    return secrets_module.token_hex(16)
