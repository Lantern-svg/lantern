"""
Lantern Node Identity v1

Purpose:
- Give a Lantern node a durable, verifiable cryptographic identity
- Bind that identity to the existing human-readable node_id
- Provide a challenge/response proof that a peer controls the private
  key bound to the node_id it claims

Purpose it does NOT serve -- read this before wiring it into anything:
- It does not establish trust. See lantern.participants: trust_status
  stays "unverified" regardless of identity_status.
- It does not grant authority. authority_level stays "none" regardless
  of identity_status.
- It does not vouch for the software, the operator, or the content of
  any message the node later sends.
- It does not provide confidentiality or transport-layer protection.
  It proves who signed a specific challenge, not that nobody else can
  observe the exchange.

PROVES:
    "The responder controls the private key corresponding to the
    public key bound to node identity X, as of this specific
    challenge/response exchange."

DOES NOT PROVE:
    - That the responder is a trustworthy human or well-behaved agent.
    - That the software running at that identity is unmodified.
    - That any capability the node advertises is truthfully implemented.
    - That the node should receive any trust or authority.
    - That a first-contact node_id/key pairing is legitimate (this is a
      trust-on-first-use scheme; it protects an *already known* binding
      from being silently replaced, it does not vet a brand-new one).

============================================================
Storage format
============================================================

One identity = one directory, default `<data_dir>/identity/<node_id>/`,
configurable via the `identity_dir` argument to NodeIdentity.load_or_create().

Files:
    private_key.bin   -- raw 32-byte Ed25519 seed, mode 0600. NEVER
                          copied, logged, serialized into a Chronicle,
                          returned by any HTTP endpoint, or included in
                          any handshake/proof message. Nothing in this
                          module ever puts its bytes into a dict that
                          could be JSON-encoded and sent anywhere.
    public_key.bin     -- raw 32-byte Ed25519 verify key. Shareable.
    binding.json       -- {"node_id": ..., "public_key": <hex>,
                            "signature": <hex>, "created_at": <iso8601>}
                          signature = sign(node_id + public_key_bytes)
                          by the matching private key. This is the
                          node_id <-> public_key binding, independently
                          verifiable by anyone holding only the public
                          key (see verify_binding()).

This directory is deliberately separate from any Chronicle path. The
Chronicle is an append-only audit log of belief/evidence/join events;
identity key material is a credential, not an event, and mixing the
two would make "never let the private key enter the Chronicle" a
convention instead of a structural guarantee. Keeping identity/ as its
own directory with no writer other than this module makes it
structural.

============================================================
Key lifecycle
============================================================

1. First run: load_or_create() finds no existing private_key.bin,
   generates a fresh Ed25519 keypair, writes private_key.bin (0600),
   public_key.bin, and a self-signed binding.json.
2. Every subsequent run with the same identity_dir: load_or_create()
   loads the existing key material unchanged. The public key and
   node_id binding are stable across restarts.
3. Rotation (deliberate, operator-initiated only -- never automatic):
   rotate_identity() generates a NEW keypair, and produces a
   RotationRecord signed by the OLD private key attesting
   "node_id X now binds to NEW public key, as of TIME, signed by the
   key it supersedes". This is the smallest safe mechanism: an
   attacker who only ever observed the OLD public key (never possessed
   the OLD private key) cannot forge a valid rotation record, so
   silently swapping in a replacement identity is not possible. This
   module does not implement propagation/announcement of a rotation to
   any peer -- that is an explicit, separate, operator-driven action
   (e.g. re-running handshake/identity proof with the new binding),
   deliberately not automated here.

============================================================
node_id <-> public_key binding: design choice
============================================================

node_id remains a stable, human-readable identifier (unchanged from
existing Lantern convention -- see handshake.py, bootstrap_node.py).
The binding is a SEPARATE, independently-verifiable signed record
rather than `node_id = hash(public_key)`, specifically so that:
  - node_id stays human-readable (no rename of existing code/tests)
  - key rotation does not change the node_id an existing peer already
    knows the node by
  - rotation becomes an explicit, auditable, signed transition instead
    of "this is now a different identity"
"""

from __future__ import annotations

import json
import os
import stat
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from nacl.exceptions import BadSignatureError
from nacl.signing import SigningKey, VerifyKey
from nacl.encoding import HexEncoder

from .protocol import PROTOCOL_VERSION


# ============================================================
# Domain separation
# ============================================================
#
# A signature produced for one purpose must not be trivially replayable
# as a signature for a different purpose. Every signed payload below is
# prefixed with a purpose tag so a binding signature can never be
# mistaken for (or replayed as) a challenge-proof signature, etc.

_DOMAIN_BINDING = b"lantern.identity.binding.v1"
_DOMAIN_CHALLENGE_PROOF = b"lantern.identity.challenge_proof.v1"
_DOMAIN_ROTATION = b"lantern.identity.rotation.v1"

DEFAULT_CHALLENGE_TTL_SECONDS = 90


class IdentityError(Exception):
    """Raised for identity storage/binding/proof failures."""


# ============================================================
# Storage
# ============================================================

class NodeIdentity:
    """Deliberately a plain class, not a dataclass.

    dataclasses.asdict() walks every field regardless of repr=False/
    compare=False -- those only affect __repr__/__eq__, not asdict().
    A dataclass NodeIdentity would let a single accidental
    dataclasses.asdict(identity) call anywhere in the codebase pull the
    live nacl.signing.SigningKey object out into a plain dict, one step
    away from an accidental json.dumps() or log line. Using a plain
    class makes that mistake structurally impossible: there is no
    asdict() for a non-dataclass, full stop.
    """

    def __init__(self, node_id: str, public_key_hex: str, identity_dir: Path, signing_key: SigningKey):
        self.node_id = node_id
        self.public_key_hex = public_key_hex
        self.identity_dir = identity_dir
        self._signing_key = signing_key

    def __repr__(self) -> str:
        return (
            f"NodeIdentity(node_id={self.node_id!r}, "
            f"public_key_hex={self.public_key_hex!r}, "
            f"identity_dir={self.identity_dir!r})"
        )

    def verify_key_hex(self) -> str:
        return self.public_key_hex

    def sign(self, domain: bytes, payload: bytes) -> str:
        """Sign domain||payload, return hex signature. Never exposes key bytes."""
        signed = self._signing_key.sign(domain + b"|" + payload)
        return signed.signature.hex()


def _identity_paths(identity_dir: Path) -> dict:
    return {
        "dir": identity_dir,
        "private_key": identity_dir / "private_key.bin",
        "public_key": identity_dir / "public_key.bin",
        "binding": identity_dir / "binding.json",
    }


def default_identity_dir(data_dir: str | Path, node_id: str) -> Path:
    return Path(data_dir) / "identity" / node_id


def load_or_create(node_id: str, identity_dir: str | Path) -> NodeIdentity:
    """Load an existing identity, or generate + persist a new one.

    identity_dir is fully caller-configurable -- it is never implicitly
    the Chronicle path or its parent. Callers (e.g. bootstrap_node.py)
    are responsible for keeping it outside any Chronicle directory if
    they want that separation enforced at the filesystem layer too;
    this function does not silently nest itself inside a chronicle
    path, but it also does not forbid a caller from misconfiguring
    that -- see architecture-level test for an explicit assertion.
    """
    identity_dir = Path(identity_dir)
    paths = _identity_paths(identity_dir)

    if paths["private_key"].exists():
        return _load_existing(node_id, paths)

    return _create_new(node_id, paths)


def _load_existing(node_id: str, paths: dict) -> NodeIdentity:
    private_bytes = paths["private_key"].read_bytes()
    if len(private_bytes) != 32:
        raise IdentityError(f"Corrupt private key material at {paths['private_key']}")

    signing_key = SigningKey(private_bytes)
    public_key_hex = signing_key.verify_key.encode(encoder=HexEncoder).decode("ascii")

    if not paths["binding"].exists():
        raise IdentityError(
            f"Private key exists at {paths['private_key']} but binding.json is missing "
            "-- refusing to synthesize a binding for existing key material."
        )

    binding = json.loads(paths["binding"].read_text())
    if binding.get("node_id") != node_id:
        raise IdentityError(
            f"Identity directory {paths['dir']} is bound to node_id "
            f"{binding.get('node_id')!r}, not the requested {node_id!r}."
        )
    if binding.get("public_key") != public_key_hex:
        raise IdentityError(
            f"binding.json public_key does not match the key material on disk at "
            f"{paths['dir']} -- refusing to load a mismatched identity."
        )
    if not verify_binding(node_id, public_key_hex, binding.get("signature", "")):
        raise IdentityError(f"binding.json signature is invalid for {paths['dir']}.")

    return NodeIdentity(
        node_id=node_id,
        public_key_hex=public_key_hex,
        identity_dir=paths["dir"],
        signing_key=signing_key,
    )


def _create_new(node_id: str, paths: dict) -> NodeIdentity:
    paths["dir"].mkdir(parents=True, exist_ok=True)

    signing_key = SigningKey.generate()
    public_key_hex = signing_key.verify_key.encode(encoder=HexEncoder).decode("ascii")

    signature = signing_key.sign(
        _DOMAIN_BINDING + b"|" + node_id.encode("utf-8") + b"|" + public_key_hex.encode("ascii")
    ).signature.hex()

    binding = {
        "node_id": node_id,
        "public_key": public_key_hex,
        "signature": signature,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    # Private key written last-but-one, with restrictive permissions
    # applied immediately after write -- never left world/group
    # readable even momentarily beyond the umask-limited window
    # inherent to any create-then-chmod sequence.
    paths["private_key"].write_bytes(bytes(signing_key))
    os.chmod(paths["private_key"], stat.S_IRUSR | stat.S_IWUSR)  # 0600

    paths["public_key"].write_bytes(bytes(signing_key.verify_key))
    paths["binding"].write_text(json.dumps(binding, indent=2, sort_keys=True))

    return NodeIdentity(
        node_id=node_id,
        public_key_hex=public_key_hex,
        identity_dir=paths["dir"],
        signing_key=signing_key,
    )


# ============================================================
# node_id <-> public_key binding verification
# ============================================================

def verify_binding(node_id: str, public_key_hex: str, signature_hex: str) -> bool:
    """Anyone holding only the public key can verify the binding.

    Returns False on any malformed input rather than raising -- a
    verification function must have exactly two outcomes for a caller:
    verified or not verified, never an exception that could be
    mishandled into a false-accept.
    """
    try:
        verify_key = VerifyKey(public_key_hex, encoder=HexEncoder)
        message = (
            _DOMAIN_BINDING + b"|" + node_id.encode("utf-8") + b"|" + public_key_hex.encode("ascii")
        )
        verify_key.verify(message, bytes.fromhex(signature_hex))
        return True
    except (BadSignatureError, ValueError, TypeError, KeyError):
        return False


# ============================================================
# Rotation
# ============================================================

@dataclass(frozen=True)
class RotationRecord:
    node_id: str
    old_public_key: str
    new_public_key: str
    signature: str  # signed by the OLD key
    rotated_at: str

    def to_dict(self) -> dict:
        return {
            "node_id": self.node_id,
            "old_public_key": self.old_public_key,
            "new_public_key": self.new_public_key,
            "signature": self.signature,
            "rotated_at": self.rotated_at,
        }


def rotate_identity(old_identity: NodeIdentity, identity_dir: str | Path) -> tuple[NodeIdentity, RotationRecord]:
    """Generate a new keypair and a rotation record signed by the OLD key.

    Deliberately NOT automatic and NOT triggered by any handshake or
    proof code path -- this is only ever called by an explicit operator
    action. This function only produces the record; propagating it to
    peers (so they can update which public key they trust for this
    node_id) is an explicit, separate, out-of-scope step -- see module
    docstring "Key lifecycle" section.
    """
    identity_dir = Path(identity_dir)
    paths = _identity_paths(identity_dir)

    new_signing_key = SigningKey.generate()
    new_public_key_hex = new_signing_key.verify_key.encode(encoder=HexEncoder).decode("ascii")

    rotated_at = datetime.now(timezone.utc).isoformat()
    message = (
        _DOMAIN_ROTATION
        + b"|"
        + old_identity.node_id.encode("utf-8")
        + b"|"
        + old_identity.public_key_hex.encode("ascii")
        + b"|"
        + new_public_key_hex.encode("ascii")
        + b"|"
        + rotated_at.encode("ascii")
    )
    signature = old_identity._signing_key.sign(message).signature.hex()

    record = RotationRecord(
        node_id=old_identity.node_id,
        old_public_key=old_identity.public_key_hex,
        new_public_key=new_public_key_hex,
        signature=signature,
        rotated_at=rotated_at,
    )

    new_binding_signature = new_signing_key.sign(
        _DOMAIN_BINDING
        + b"|"
        + old_identity.node_id.encode("utf-8")
        + b"|"
        + new_public_key_hex.encode("ascii")
    ).signature.hex()
    binding = {
        "node_id": old_identity.node_id,
        "public_key": new_public_key_hex,
        "signature": new_binding_signature,
        "created_at": rotated_at,
        "rotated_from": old_identity.public_key_hex,
    }

    paths["private_key"].write_bytes(bytes(new_signing_key))
    os.chmod(paths["private_key"], stat.S_IRUSR | stat.S_IWUSR)
    paths["public_key"].write_bytes(bytes(new_signing_key.verify_key))
    paths["binding"].write_text(json.dumps(binding, indent=2, sort_keys=True))

    new_identity = NodeIdentity(
        node_id=old_identity.node_id,
        public_key_hex=new_public_key_hex,
        identity_dir=paths["dir"],
        signing_key=new_signing_key,
    )
    return new_identity, record


def verify_rotation(record: RotationRecord) -> bool:
    """Verify a rotation record was signed by the OLD key it claims."""
    try:
        old_key = VerifyKey(record.old_public_key, encoder=HexEncoder)
        message = (
            _DOMAIN_ROTATION
            + b"|"
            + record.node_id.encode("utf-8")
            + b"|"
            + record.old_public_key.encode("ascii")
            + b"|"
            + record.new_public_key.encode("ascii")
            + b"|"
            + record.rotated_at.encode("ascii")
        )
        old_key.verify(message, bytes.fromhex(record.signature))
        return True
    except (BadSignatureError, ValueError, TypeError, KeyError):
        return False


# ============================================================
# Challenge / Proof (identity handshake extension)
# ============================================================

@dataclass(frozen=True)
class Challenge:
    """Issued by the initiator (A), given to the responder (B) to sign.

    consumed: mutable bookkeeping owned exclusively by ChallengeStore
    below -- a Challenge object itself is otherwise immutable.
    """

    nonce: str
    from_node_id: str  # the initiator issuing the challenge (A)
    to_node_id: str  # the responder expected to answer (B)
    protocol_version: str
    issued_at: float  # time.monotonic() for expiry math; not wall-clock
    ttl_seconds: int


@dataclass(frozen=True)
class IdentityProof:
    nonce: str
    from_node_id: str
    to_node_id: str
    protocol_version: str
    claimed_node_id: str
    public_key: str
    identity_binding_signature: str
    signature: str
    proof_timestamp: str


def create_challenge(from_node_id: str, to_node_id: str, ttl_seconds: int = DEFAULT_CHALLENGE_TTL_SECONDS) -> Challenge:
    import secrets

    return Challenge(
        nonce=secrets.token_hex(32),
        from_node_id=from_node_id,
        to_node_id=to_node_id,
        protocol_version=PROTOCOL_VERSION,
        issued_at=time.monotonic(),
        ttl_seconds=ttl_seconds,
    )


def _challenge_proof_payload(nonce, from_node_id, to_node_id, protocol_version, claimed_node_id, public_key_hex):
    # Every field the response must NOT be able to alter without
    # invalidating the signature -- this is the context binding that
    # prevents a proof for one (challenger, responder, protocol,
    # nonce) tuple from being reinterpreted as valid for another. This
    # is the raw payload (no domain prefix) -- NodeIdentity.sign() and
    # the verify call below both apply _DOMAIN_CHALLENGE_PROOF the same
    # way, so signing and verification never need to agree on slicing.
    parts = [nonce, from_node_id, to_node_id, protocol_version, claimed_node_id, public_key_hex]
    return "|".join(parts).encode("utf-8")


def respond_to_challenge(challenge: Challenge, identity: NodeIdentity, binding_signature_hex: str) -> IdentityProof:
    """Called by the RESPONDER (B). Never touches A's state.

    binding_signature_hex is B's own node_id<->public_key binding
    signature (from its own binding.json / NodeIdentity storage),
    included so A can verify the binding without a prior out-of-band
    fetch.
    """
    if challenge.to_node_id != identity.node_id:
        raise IdentityError(
            f"Challenge addressed to {challenge.to_node_id!r}, not this identity's "
            f"node_id {identity.node_id!r}."
        )

    payload = _challenge_proof_payload(
        challenge.nonce,
        challenge.from_node_id,
        challenge.to_node_id,
        challenge.protocol_version,
        identity.node_id,
        identity.public_key_hex,
    )
    signature = identity.sign(_DOMAIN_CHALLENGE_PROOF, payload)

    return IdentityProof(
        nonce=challenge.nonce,
        from_node_id=challenge.from_node_id,
        to_node_id=challenge.to_node_id,
        protocol_version=challenge.protocol_version,
        claimed_node_id=identity.node_id,
        public_key=identity.public_key_hex,
        identity_binding_signature=binding_signature_hex,
        signature=signature,
        proof_timestamp=datetime.now(timezone.utc).isoformat(),
    )


@dataclass(frozen=True)
class VerificationResult:
    verified: bool
    reason: str
    identity_status: str  # "UNVERIFIED" | "CRYPTOGRAPHICALLY_VERIFIED"


UNVERIFIED = "UNVERIFIED"
CRYPTOGRAPHICALLY_VERIFIED = "CRYPTOGRAPHICALLY_VERIFIED"


def verify_proof(
    challenge: Challenge,
    proof: IdentityProof,
    expected_public_key: Optional[str] = None,
) -> VerificationResult:
    """Called by the INITIATOR (A). Pure function -- no state mutation.

    expected_public_key: if A has previously recorded a public key for
    this node_id (trust-on-first-use pinning), pass it here -- a proof
    presenting a DIFFERENT key for an already-known node_id is rejected
    outright, which is what prevents public-key substitution once a
    binding is known. If None, this is treated as first contact: the
    binding is checked for internal validity, but there is no prior
    key to compare against (see module docstring "DOES NOT PROVE").
    """
    if proof.nonce != challenge.nonce:
        return VerificationResult(False, "Nonce does not match issued challenge", UNVERIFIED)
    if proof.from_node_id != challenge.from_node_id or proof.to_node_id != challenge.to_node_id:
        return VerificationResult(False, "Proof context (from/to node_id) does not match challenge", UNVERIFIED)
    if proof.protocol_version != challenge.protocol_version:
        return VerificationResult(False, "Proof protocol_version does not match challenge", UNVERIFIED)
    if proof.claimed_node_id != challenge.to_node_id:
        return VerificationResult(False, "Proof claims a different node_id than the challenge addressed", UNVERIFIED)

    elapsed = time.monotonic() - challenge.issued_at
    if elapsed > challenge.ttl_seconds or elapsed < 0:
        return VerificationResult(False, "Challenge expired", UNVERIFIED)

    if expected_public_key is not None and proof.public_key != expected_public_key:
        return VerificationResult(
            False,
            "Public key does not match the previously known key for this node_id "
            "(possible public-key substitution)",
            UNVERIFIED,
        )

    if not verify_binding(proof.claimed_node_id, proof.public_key, proof.identity_binding_signature):
        return VerificationResult(False, "node_id <-> public_key binding signature invalid", UNVERIFIED)

    try:
        verify_key = VerifyKey(proof.public_key, encoder=HexEncoder)
        payload = _challenge_proof_payload(
            proof.nonce,
            proof.from_node_id,
            proof.to_node_id,
            proof.protocol_version,
            proof.claimed_node_id,
            proof.public_key,
        )
        verify_key.verify(_DOMAIN_CHALLENGE_PROOF + b"|" + payload, bytes.fromhex(proof.signature))
    except (BadSignatureError, ValueError, TypeError, KeyError):
        return VerificationResult(False, "Challenge-proof signature invalid", UNVERIFIED)

    return VerificationResult(True, "Signature and binding verified", CRYPTOGRAPHICALLY_VERIFIED)


# ============================================================
# Single-use challenge tracking (replay protection)
# ============================================================

class ChallengeStore:
    """In-memory, per-process challenge issuance/consumption tracker.

    Not durable and not shared across processes -- a challenge is a
    short-lived, single-exchange artifact (default TTL 90s), not an
    audit record; it does not belong in the Chronicle any more than a
    TLS nonce would. If a process restarts mid-handshake, in-flight
    challenges are simply lost and the exchange must be retried, which
    is safe and correct (never a replay risk) because a lost challenge
    can never be presented again by definition.
    """

    def __init__(self):
        self._issued: dict[str, Challenge] = {}
        self._consumed: set[str] = set()

    def issue(self, from_node_id: str, to_node_id: str, ttl_seconds: int = DEFAULT_CHALLENGE_TTL_SECONDS) -> Challenge:
        challenge = create_challenge(from_node_id, to_node_id, ttl_seconds)
        self._issued[challenge.nonce] = challenge
        return challenge

    def consume(self, proof: IdentityProof, expected_public_key: Optional[str] = None) -> VerificationResult:
        """Verify + mark single-use in one step. A nonce not previously
        issued by this store, or already consumed, is rejected."""
        if proof.nonce in self._consumed:
            return VerificationResult(False, "Challenge already consumed (replay)", UNVERIFIED)

        challenge = self._issued.get(proof.nonce)
        if challenge is None:
            return VerificationResult(False, "Unknown challenge nonce", UNVERIFIED)

        # Mark consumed unconditionally, whether or not verification
        # succeeds -- a failed proof attempt must not leave the
        # challenge available for a second attempt either (prevents
        # brute-force retry against a live challenge).
        self._consumed.add(proof.nonce)
        del self._issued[proof.nonce]

        return verify_proof(challenge, proof, expected_public_key=expected_public_key)
