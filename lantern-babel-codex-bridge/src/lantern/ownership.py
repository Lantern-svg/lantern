"""
Lantern Instance Ownership v1

Purpose:
- Answer, for any Lantern instance, two questions with actual evidence
  behind the answer, not an inference from "whoever is running the
  process right now":
      Who owns this instance?
      What evidence authorizes that ownership?
- Support initial ownership, authenticated ownership transfer, transfer
  history, and revocation, without weakening any existing provenance
  guarantee (lantern.identity, lantern.orchestration.ProvenanceTag) to
  make onboarding easier.

This module deliberately does NOT replace or duplicate:
    lantern.identity.NodeIdentity
        -- the durable cryptographic INSTANCE identity. Ownership here
           is always expressed as a claim signed BY that identity's own
           key, never as a new, competing identity mechanism.
    lantern_harness.transfer_manifest.TransferManifest (harness layer)
        -- a read-only, non-authorizing description of an instance for
           a receiving operator to inspect. This module is upstream of
           that: it is the actual authorization record a transfer
           manifest can later point to, not a replacement for it.

============================================================
Design: what "ownership" means here
============================================================

An instance's OWNER is whoever can present the current owner_token --
a secret supplied by the owner out-of-band (e.g. at first-run) that
this module never persists in plaintext, only as a salted-free SHA-256
hash. This is deliberately the same shape as a password-authenticated
claim, not a new cryptographic primitive, because the property we need
is narrow: "can this caller prove continuity with the previously
established owner," not "is this caller a specific verified human."

Every OwnershipRecord is signed by the INSTANCE's own NodeIdentity key
(domain-separated from identity.py's binding/challenge/rotation
signatures -- see _DOMAIN_* constants below). That signature proves
"this specific instance attested, as of this time, that owner_id X
presented the correct token for the FIRST time / for a transfer." It
does not, and cannot, prove the token itself was never leaked -- exactly
like identity.py's binding signature does not prove the private key was
never copied. Read lantern.identity's module docstring section "DOES
NOT PROVE" for the same discipline applied here.

============================================================
What this module refuses to do
============================================================

- No method here can manufacture ownership from nothing. Every
  create_initial_ownership() / transfer_ownership() call requires an
  explicit, caller-supplied owner_token (or, for transfer, the
  CURRENT owner_token) -- there is no "self-claim" path, no default,
  no environment-variable fallback. A caller that has no token cannot
  produce a valid OwnershipRecord, on purpose.
- No peer instance, and no code path anywhere in this module, can
  authorize a transfer for an instance it does not itself own. This
  module only ever signs with the identity passed in by the caller
  operating THIS instance; it never accepts or verifies a signature
  claiming authority over a different node_id's ownership.
- Revocation does not delete history. A revoked record is appended to
  the same ownership history any other transfer would be, never
  overwriting or erasing a prior record.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from nacl.exceptions import BadSignatureError
from nacl.signing import VerifyKey
from nacl.encoding import HexEncoder

from .identity import NodeIdentity

# ============================================================
# Domain separation (see identity.py for why this matters)
# ============================================================

_DOMAIN_OWNERSHIP_INITIAL = b"lantern.ownership.initial.v1"
_DOMAIN_OWNERSHIP_TRANSFER = b"lantern.ownership.transfer.v1"
_DOMAIN_OWNERSHIP_REVOCATION = b"lantern.ownership.revocation.v1"

REVOKED_OWNER_ID = "REVOKED"


class OwnershipError(Exception):
    """Raised for ownership record / claim / transfer / revocation failures."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _hash_owner_token(owner_token: str) -> str:
    if not owner_token or not owner_token.strip():
        raise OwnershipError("owner_token must be a non-empty string")
    return hashlib.sha256(owner_token.encode("utf-8")).hexdigest()


# ============================================================
# Ownership record
# ============================================================

@dataclass(frozen=True)
class OwnershipRecord:
    """One ownership claim, signed by the instance's own key.

    transferred_from is None for the very first ownership record of an
    instance, and set to the PREVIOUS record's owner_id for every
    subsequent transfer -- this is what makes transfer_history
    verifiable as an unbroken chain (see verify_history()).
    """

    node_id: str
    instance_public_key: str
    owner_id: str
    owner_token_hash: str
    authorized_at: str
    signature: str  # signed by the instance's OWN private key
    sequence: int  # 0 for initial ownership, incrementing per transfer/revocation
    transferred_from: Optional[str] = None
    revoked: bool = False

    def to_dict(self) -> dict:
        return {
            "node_id": self.node_id,
            "instance_public_key": self.instance_public_key,
            "owner_id": self.owner_id,
            "owner_token_hash": self.owner_token_hash,
            "authorized_at": self.authorized_at,
            "signature": self.signature,
            "sequence": self.sequence,
            "transferred_from": self.transferred_from,
            "revoked": self.revoked,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "OwnershipRecord":
        return cls(
            node_id=data["node_id"],
            instance_public_key=data["instance_public_key"],
            owner_id=data["owner_id"],
            owner_token_hash=data["owner_token_hash"],
            authorized_at=data["authorized_at"],
            signature=data["signature"],
            sequence=data["sequence"],
            transferred_from=data.get("transferred_from"),
            revoked=data.get("revoked", False),
        )


def _record_payload(node_id: str, instance_public_key: str, owner_id: str, owner_token_hash: str,
                     authorized_at: str, sequence: int, transferred_from: Optional[str], revoked: bool) -> bytes:
    parts = [
        node_id,
        instance_public_key,
        owner_id,
        owner_token_hash,
        authorized_at,
        str(sequence),
        transferred_from or "",
        "1" if revoked else "0",
    ]
    return "|".join(parts).encode("utf-8")


def _domain_for(sequence: int, revoked: bool) -> bytes:
    if revoked:
        return _DOMAIN_OWNERSHIP_REVOCATION
    return _DOMAIN_OWNERSHIP_INITIAL if sequence == 0 else _DOMAIN_OWNERSHIP_TRANSFER


def verify_ownership_record(record: OwnershipRecord) -> bool:
    """Anyone holding only the instance's public key can verify that
    THIS instance actually signed this specific ownership claim.

    Returns False on any malformed input rather than raising, matching
    lantern.identity.verify_binding()'s discipline: a verification
    function has exactly two outcomes, never an exception a caller
    could mishandle into a false-accept.
    """
    try:
        verify_key = VerifyKey(record.instance_public_key, encoder=HexEncoder)
        payload = _record_payload(
            record.node_id, record.instance_public_key, record.owner_id,
            record.owner_token_hash, record.authorized_at, record.sequence,
            record.transferred_from, record.revoked,
        )
        domain = _domain_for(record.sequence, record.revoked)
        verify_key.verify(domain + b"|" + payload, bytes.fromhex(record.signature))
        return True
    except (BadSignatureError, ValueError, TypeError, KeyError):
        return False


# ============================================================
# Initial ownership
# ============================================================

def create_initial_ownership(identity: NodeIdentity, *, owner_id: str, owner_token: str) -> OwnershipRecord:
    """Establish the FIRST owner of a freshly created instance.

    Deliberately requires an explicit owner_id and owner_token from the
    caller -- there is no default owner_id ("self", "operator", the
    process user) and no way to call this without a real token. This is
    what prevents ownership from being inferred merely from whoever
    happens to be running the process.
    """
    if not owner_id or not owner_id.strip():
        raise OwnershipError("owner_id must be a non-empty string")

    owner_token_hash = _hash_owner_token(owner_token)
    authorized_at = _now()
    sequence = 0

    payload = _record_payload(
        identity.node_id, identity.public_key_hex, owner_id.strip(),
        owner_token_hash, authorized_at, sequence, None, False,
    )
    signature = identity.sign(_DOMAIN_OWNERSHIP_INITIAL, payload)

    return OwnershipRecord(
        node_id=identity.node_id,
        instance_public_key=identity.public_key_hex,
        owner_id=owner_id.strip(),
        owner_token_hash=owner_token_hash,
        authorized_at=authorized_at,
        signature=signature,
        sequence=sequence,
        transferred_from=None,
        revoked=False,
    )


# ============================================================
# Transfer
# ============================================================

def transfer_ownership(
    current_record: OwnershipRecord,
    identity: NodeIdentity,
    *,
    current_owner_token: str,
    new_owner_id: str,
    new_owner_token: str,
) -> OwnershipRecord:
    """Authenticated ownership transfer.

    Requires presenting the CURRENT owner_token. The instance hashes
    what was presented and compares it against current_record's stored
    hash BEFORE producing any new record -- a caller cannot transfer
    ownership merely by asking, and a caller who does not know the
    current token cannot produce a valid transfer no matter what
    new_owner_id/new_owner_token it supplies.

    Refuses to transfer a REVOKED record -- a revoked instance must be
    explicitly re-authorized via a fresh create_initial_ownership()-style
    flow by whoever now controls it, not silently reanimated by transfer.
    """
    if current_record.revoked:
        raise OwnershipError(
            f"ownership record for {current_record.node_id!r} is revoked; "
            "cannot transfer a revoked ownership record"
        )
    if current_record.node_id != identity.node_id:
        raise OwnershipError(
            f"current_record is for node_id {current_record.node_id!r}, "
            f"not this identity's node_id {identity.node_id!r}"
        )
    if current_record.instance_public_key != identity.public_key_hex:
        raise OwnershipError(
            "current_record.instance_public_key does not match this identity's "
            "public key -- refusing to transfer a mismatched ownership record"
        )
    if not verify_ownership_record(current_record):
        raise OwnershipError("current_record signature is invalid; refusing to build a transfer on top of it")
    if _hash_owner_token(current_owner_token) != current_record.owner_token_hash:
        raise OwnershipError("current_owner_token does not match the recorded owner; transfer refused")
    if not new_owner_id or not new_owner_id.strip():
        raise OwnershipError("new_owner_id must be a non-empty string")

    new_owner_token_hash = _hash_owner_token(new_owner_token)
    authorized_at = _now()
    sequence = current_record.sequence + 1

    payload = _record_payload(
        identity.node_id, identity.public_key_hex, new_owner_id.strip(),
        new_owner_token_hash, authorized_at, sequence, current_record.owner_id, False,
    )
    signature = identity.sign(_DOMAIN_OWNERSHIP_TRANSFER, payload)

    return OwnershipRecord(
        node_id=identity.node_id,
        instance_public_key=identity.public_key_hex,
        owner_id=new_owner_id.strip(),
        owner_token_hash=new_owner_token_hash,
        authorized_at=authorized_at,
        signature=signature,
        sequence=sequence,
        transferred_from=current_record.owner_id,
        revoked=False,
    )


# ============================================================
# Revocation
# ============================================================

def revoke_ownership(
    current_record: OwnershipRecord,
    identity: NodeIdentity,
    *,
    current_owner_token: str,
) -> OwnershipRecord:
    """Revoke the current owner's ownership, still requiring proof of
    the current token (revocation is an owner action, not something a
    third party can trigger). The resulting record has
    owner_id=REVOKED_OWNER_ID and revoked=True; instance_lifecycle
    treats a revoked ownership record as blocking READY status until a
    fresh ownership is explicitly established."""
    if current_record.revoked:
        raise OwnershipError("ownership record is already revoked")
    if current_record.node_id != identity.node_id:
        raise OwnershipError(
            f"current_record is for node_id {current_record.node_id!r}, "
            f"not this identity's node_id {identity.node_id!r}"
        )
    if not verify_ownership_record(current_record):
        raise OwnershipError("current_record signature is invalid; refusing to revoke on top of it")
    if _hash_owner_token(current_owner_token) != current_record.owner_token_hash:
        raise OwnershipError("current_owner_token does not match the recorded owner; revocation refused")

    authorized_at = _now()
    sequence = current_record.sequence + 1

    payload = _record_payload(
        identity.node_id, identity.public_key_hex, REVOKED_OWNER_ID,
        current_record.owner_token_hash, authorized_at, sequence, current_record.owner_id, True,
    )
    signature = identity.sign(_DOMAIN_OWNERSHIP_REVOCATION, payload)

    return OwnershipRecord(
        node_id=identity.node_id,
        instance_public_key=identity.public_key_hex,
        owner_id=REVOKED_OWNER_ID,
        owner_token_hash=current_record.owner_token_hash,
        authorized_at=authorized_at,
        signature=signature,
        sequence=sequence,
        transferred_from=current_record.owner_id,
        revoked=True,
    )


# ============================================================
# History (append-only, chain-verifiable)
# ============================================================

class OwnershipHistory:
    """An append-only list of OwnershipRecord, in sequence order.

    This is the auditable trail mission section 4 asks for
    ("transfer history"). It is intentionally a thin wrapper, not a
    Chronicle-backed structure -- ownership records are already
    individually signed and chain via transferred_from/sequence, so a
    plain ordered list plus verify_chain() is sufficient without
    introducing a second hash-chain implementation alongside
    lantern.core.Chronicle.
    """

    def __init__(self, records: Optional[list] = None):
        self._records: list[OwnershipRecord] = list(records or [])

    def append(self, record: OwnershipRecord) -> None:
        if self._records:
            latest = self._records[-1]
            if record.sequence != latest.sequence + 1:
                raise OwnershipError(
                    f"non-contiguous ownership sequence: expected {latest.sequence + 1}, got {record.sequence}"
                )
            if record.transferred_from != latest.owner_id:
                raise OwnershipError(
                    f"record.transferred_from ({record.transferred_from!r}) does not match "
                    f"previous record's owner_id ({latest.owner_id!r})"
                )
        elif record.sequence != 0:
            raise OwnershipError(f"first record in history must have sequence=0, got {record.sequence}")
        self._records.append(record)

    def current(self) -> Optional[OwnershipRecord]:
        return self._records[-1] if self._records else None

    def all_records(self) -> tuple:
        return tuple(self._records)

    def verify_chain(self) -> bool:
        """Every record signs verifiably, and the transferred_from/sequence
        chain is unbroken from the first record to the last."""
        previous: Optional[OwnershipRecord] = None
        for record in self._records:
            if not verify_ownership_record(record):
                return False
            if previous is None:
                if record.sequence != 0 or record.transferred_from is not None:
                    return False
            else:
                if record.sequence != previous.sequence + 1:
                    return False
                if record.transferred_from != previous.owner_id:
                    return False
            previous = record
        return True

    def to_list(self) -> list:
        return [record.to_dict() for record in self._records]

    @classmethod
    def from_list(cls, data: list) -> "OwnershipHistory":
        return cls([OwnershipRecord.from_dict(item) for item in data])


# ============================================================
# Persistence (plain JSON file, deliberately separate from Chronicle
# and from the identity directory -- see instance_lifecycle.py for how
# these paths are wired together)
# ============================================================

def save_history(path: str | Path, history: OwnershipHistory) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(history.to_list(), indent=2, sort_keys=True))


def load_history(path: str | Path) -> Optional[OwnershipHistory]:
    path = Path(path)
    if not path.exists():
        return None
    return OwnershipHistory.from_list(json.loads(path.read_text()))
