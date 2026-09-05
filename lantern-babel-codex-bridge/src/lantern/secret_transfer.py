"""Lantern Secret Transfer v1 -- confidential transfer over an
authenticated session.

PROBLEM IT SOLVES
-----------------
The existing Lantern session proves WHO the caller is (two-phase
proof-of-possession), but the transport is plaintext HTTP: every
/message payload, including observation content, crosses the wire in
cleartext. Authentication != confidentiality. This module adds the
minimum confidential layer ON TOP of the existing authenticated
session, using established libsodium primitives (PyNaCl) only:

  X25519 ephemeral key agreement
  + Ed25519 identity signatures over the ephemeral keys
  + XSalsa20-Poly1305 authenticated encryption (nacl.public.Box)

No new trust model. No homemade cryptography. No downgrade: the secret
never travels unencrypted, and a tampered, replayed, or transplanted
ciphertext is rejected.

PROTOCOL (two-phase over the existing authenticated session)
-------------------------------------------------------------
Phase 1  POST /secret/offer
  client -> {session_id, node_id, offer:{secret_id, eph_pub, sig}}
  sig = identity-sign("lantern.secret.offer.v1" | secret_id | eph_pub
                      | session_id)
  server -> {accepted, server_eph_pub, server_public_key_hex,
             server_sig, ttl_seconds}
  server_sig = identity-sign("lantern.secret.respond.v1" | secret_id
                             | server_eph_pub | eph_pub | session_id)

Phase 2  POST /secret/seal
  client -> {session_id, node_id, secret_id, nonce, ciphertext}
  ciphertext = Box(client_eph_priv, server_eph_pub).encrypt(inner)
  inner = json {secret, digest, secret_id, session_id, sender_node_id}
  The context fields inside the encrypted envelope are the equivalent
  of AEAD associated data: a ciphertext cannot be transplanted across
  sessions, senders, or secret_ids.
  server: derive Box, decrypt, verify context + digest, hold in an
  in-memory SecretVault (TTL, never persisted), return
  {received, secret_id, digest}

Proof of holding without exposure:
  POST /secret/receipt {session_id, node_id, secret_id}
  Only the original sender's authenticated session may ask; the vault
  returns the stored digest -- never the plaintext.

INVARIANTS
  - secret plaintext exists only in sender memory, inside the AEAD
    envelope, and in the receiver's in-memory vault entry
  - never written to disk, Chronicle, EvidenceKernel, logs, evidence
  - offers and sealed transfers are single-use (burned on consumption)
  - Python cannot guarantee zeroization of immutable bytes; the vault
    drops all references on expiry and this limitation is documented
    rather than hidden
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from typing import Any, Optional

from nacl.exceptions import BadSignatureError
from nacl.public import Box, PrivateKey, PublicKey
from nacl.signing import VerifyKey

OFFER_DOMAIN = b"lantern.secret.offer.v1"
RESPOND_DOMAIN = b"lantern.secret.respond.v1"
OFFER_TTL_SECONDS = 120.0
VAULT_TTL_SECONDS = 600.0
CAPABILITY = "secret_transfer"

# ---------------------------------------------------------------------------
# Client side
# ---------------------------------------------------------------------------


def create_secret_offer(*, session_id: str, secret_id: str, identity) -> tuple:
    """Build the phase-1 offer plus the private ephemeral key material.

    Returns (offer, eph_private_hex). The private hex stays client-side
    and is never included in any request.
    """
    eph = PrivateKey.generate()
    eph_pub_hex = bytes(eph.public_key).hex()
    payload = "|".join([secret_id, eph_pub_hex, session_id]).encode("utf-8")
    sig = identity.sign(OFFER_DOMAIN, payload)
    offer = {
        "secret_id": secret_id,
        "eph_pub": eph_pub_hex,
        "sig": sig,
    }
    return offer, bytes(eph).hex()


def verify_secret_response(*, response: dict, client_offer: dict, session_id: str, secret_id: str) -> bool:
    """Authenticate the server's key-agreement response.

    Trust-on-first-use, exactly like the rest of the architecture: the
    response carries the server's identity public key and a signature
    over the agreement material. A caller that wants a pinned binding
    can record server_public_key_hex from the accepted response.
    """
    payload = "|".join(
        [secret_id, response["server_eph_pub"], client_offer["eph_pub"], session_id]
    ).encode("utf-8")
    try:
        VerifyKey(bytes.fromhex(response["server_public_key_hex"])).verify(
            RESPOND_DOMAIN + b"|" + payload, bytes.fromhex(response["server_sig"])
        )
        return True
    except (BadSignatureError, KeyError, ValueError):
        return False


def seal_secret(box, *, secret: str, secret_id: str, session_id: str, sender_node_id: str) -> tuple:
    """Encrypt the secret into the AEAD envelope.

    Returns (sealed_payload, digest). The digest is the SHA-256
    fingerprint of the secret -- the only form in which the secret may
    ever appear in reports, responses, or evidence.
    """
    digest = hashlib.sha256(secret.encode("utf-8")).hexdigest()
    inner = json.dumps(
        {
            "secret": secret,
            "digest": digest,
            "secret_id": secret_id,
            "session_id": session_id,
            "sender_node_id": sender_node_id,
        },
        sort_keys=True,
    ).encode("utf-8")
    nonce = os.urandom(Box.NONCE_SIZE)
    encrypted = box.encrypt(inner, nonce)
    return (
        {"nonce": nonce.hex(), "ciphertext": encrypted.ciphertext.hex()},
        digest,
    )


# ---------------------------------------------------------------------------
# Server side
# ---------------------------------------------------------------------------


def verify_secret_offer(*, offer: dict, session_id: str, expected_public_key_hex: str) -> bool:
    """Verify the client's offer signature against the ALREADY-VERIFIED
    identity public key for the caller's node_id (from the node's
    _known_public_keys table, populated only by a successful
    cryptographic /identity/verify)."""
    payload = "|".join([offer["secret_id"], offer["eph_pub"], session_id]).encode("utf-8")
    try:
        VerifyKey(bytes.fromhex(expected_public_key_hex)).verify(
            OFFER_DOMAIN + b"|" + payload, bytes.fromhex(offer["sig"])
        )
        return True
    except (BadSignatureError, KeyError, ValueError):
        return False


def build_secret_response(*, client_offer: dict, session_id: str, secret_id: str, server_identity) -> tuple:
    """Generate the server's ephemeral keypair, sign the agreement
    material with the server's long-term identity key, and return the
    response dict plus the server's Box (server eph priv + client eph
    pub)."""
    eph = PrivateKey.generate()
    eph_pub_hex = bytes(eph.public_key).hex()
    payload = "|".join(
        [secret_id, eph_pub_hex, client_offer["eph_pub"], session_id]
    ).encode("utf-8")
    sig = server_identity.sign(RESPOND_DOMAIN, payload)
    response = {
        "server_eph_pub": eph_pub_hex,
        "server_public_key_hex": server_identity.public_key_hex,
        "server_sig": sig,
        "ttl_seconds": OFFER_TTL_SECONDS,
    }
    box = Box(eph, PublicKey(bytes.fromhex(client_offer["eph_pub"])))
    return response, box


def unseal_secret(*, box, nonce_hex: str, ciphertext_hex: str) -> dict:
    """Decrypt and parse the inner envelope. Raises nacl CryptoError on
    any tampering -- the caller must treat that as a clean rejection
    and must never echo decrypted material on failure."""
    plaintext = box.decrypt(bytes.fromhex(ciphertext_hex), bytes.fromhex(nonce_hex))
    inner = json.loads(plaintext.decode("utf-8"))
    if not isinstance(inner, dict):
        raise ValueError("inner envelope must be an object")
    return inner


# ---------------------------------------------------------------------------
# In-memory stores
# ---------------------------------------------------------------------------


class SecretVault:
    """In-memory, TTL-bound storage for received secrets.

    SECURITY PROPERTIES:
    - never persisted to disk, Chronicle, EvidenceKernel, or any log
    - entries are bound to the transfer (secret_id, sender node_id,
      session_id) and to a monotonic expiry
    - expired entries have all references dropped immediately
    - plaintext is never included in any dict this class returns
    """

    def __init__(self, ttl_seconds: float = VAULT_TTL_SECONDS):
        self._ttl_seconds = ttl_seconds
        self._entries = {}

    def store(self, *, secret_id: str, secret_bytes: bytes, digest: str,
              sender_node_id: str, session_id: str) -> None:
        self._entries[secret_id] = {
            "secret_bytes": secret_bytes,
            "digest": digest,
            "sender_node_id": sender_node_id,
            "session_id": session_id,
            "expires_monotonic": time.monotonic() + self._ttl_seconds,
        }

    def evict_expired(self, now_monotonic=None) -> int:
        now = time.monotonic() if now_monotonic is None else now_monotonic
        expired = [k for k, v in self._entries.items() if v["expires_monotonic"] <= now]
        for k in expired:
            del self._entries[k]  # drop all references; bytes are immutable
        return len(expired)

    def peek(self, secret_id: str):
        """Return the entry's NON-SECRET fields (digest, binding, expiry)
        if present and unexpired. The plaintext bytes stay inside the
        vault; callers must go through take() for actual material."""
        self.evict_expired()
        entry = self._entries.get(secret_id)
        if entry is None:
            return None
        return {
            "digest": entry["digest"],
            "sender_node_id": entry["sender_node_id"],
            "session_id": entry["session_id"],
            "expires_monotonic": entry["expires_monotonic"],
        }

    def take(self, secret_id: str):
        """Return the plaintext bytes for the receiving node's own
        in-process use. This is the ONLY path to the material, and it is
        never exposed over HTTP."""
        self.evict_expired()
        entry = self._entries.get(secret_id)
        if entry is None:
            return None
        return entry["secret_bytes"]
