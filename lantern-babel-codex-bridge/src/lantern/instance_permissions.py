"""
Lantern Instance Permissions v1

Purpose:
- Provide an explicit, inspectable, per-instance capability model for
  personal-instance operations that must not be inferred from process
  ownership, call path, or peer negotiation.
- Enforce permission at the actual state/action boundary, not merely in
  callers.

This module governs LOCAL instance capabilities, distinct from:
    - lantern.identity        -> who controls a node key
    - lantern.ownership       -> who is currently authorized owner
    - lantern.capability_authorization -> what a verified remote peer may do

The capabilities required by Phase B are exactly:
    memory_read
    memory_write
    import_state
    export_state
    peer_send
    peer_receive
    external_tool_access
    ownership_transfer

Rules:
- No wildcard "Lantern permission" exists.
- Every grant is explicit and inspectable.
- A permission token is caller-supplied, never inferred from the OS user,
  environment, or current process identity.
- The bound owner_token hash must match the current ownership record.
- Stale grants (for an older ownership sequence) are rejected.
- Revoked ownership records cannot authorize any capability.
- Enforcers are stateful boundary objects that must be invoked by the
  state/action surface itself.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Iterable, Optional

from . import ownership as own

MEMORY_READ = "memory_read"
MEMORY_WRITE = "memory_write"
IMPORT_STATE = "import_state"
EXPORT_STATE = "export_state"
PEER_SEND = "peer_send"
PEER_RECEIVE = "peer_receive"
EXTERNAL_TOOL_ACCESS = "external_tool_access"
OWNERSHIP_TRANSFER = "ownership_transfer"

INSTANCE_CAPABILITIES = (
    MEMORY_READ,
    MEMORY_WRITE,
    IMPORT_STATE,
    EXPORT_STATE,
    PEER_SEND,
    PEER_RECEIVE,
    EXTERNAL_TOOL_ACCESS,
    OWNERSHIP_TRANSFER,
)


class PermissionError(Exception):
    """Raised when an instance capability is missing, malformed, stale, or forged."""


class PermissionValidationError(PermissionError):
    """Raised when a presented grant fails integrity or ownership validation."""


class PermissionDenied(PermissionError):
    """Raised when a validly structured grant lacks the requested capability."""


class PermissionScopeMismatch(PermissionError):
    """Raised when a grant is presented to the wrong instance or key."""



def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class CapabilityGrant:
    node_id: str
    instance_public_key: str
    owner_id: str
    ownership_sequence: int
    owner_token_hash: str
    capabilities: tuple[str, ...]
    issued_at: str
    note: str
    signature: str

    def __post_init__(self) -> None:
        unknown = [cap for cap in self.capabilities if cap not in INSTANCE_CAPABILITIES]
        if unknown:
            raise PermissionError(f"unknown instance capability(s): {sorted(unknown)}")
        if not self.node_id or not self.instance_public_key or not self.owner_id:
            raise PermissionError("capability grant requires node_id, instance_public_key, and owner_id")

    def to_dict(self) -> dict:
        return {
            "node_id": self.node_id,
            "instance_public_key": self.instance_public_key,
            "owner_id": self.owner_id,
            "ownership_sequence": self.ownership_sequence,
            "owner_token_hash": self.owner_token_hash,
            "capabilities": list(self.capabilities),
            "issued_at": self.issued_at,
            "note": self.note,
            "signature": self.signature,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "CapabilityGrant":
        return cls(
            node_id=data["node_id"],
            instance_public_key=data["instance_public_key"],
            owner_id=data["owner_id"],
            ownership_sequence=data["ownership_sequence"],
            owner_token_hash=data["owner_token_hash"],
            capabilities=tuple(data.get("capabilities", [])),
            issued_at=data["issued_at"],
            note=data.get("note", ""),
            signature=data["signature"],
        )

    def allows(self, capability: str) -> bool:
        return capability in self.capabilities


_PERMISSION_DOMAIN = b"lantern.instance_permissions.v1"


def _grant_payload(
    *,
    node_id: str,
    instance_public_key: str,
    owner_id: str,
    ownership_sequence: int,
    owner_token_hash: str,
    capabilities: Iterable[str],
    issued_at: str,
    note: str,
) -> bytes:
    normalized_caps = ",".join(sorted(set(capabilities)))
    return "|".join([
        node_id,
        instance_public_key,
        owner_id,
        str(ownership_sequence),
        owner_token_hash,
        normalized_caps,
        issued_at,
        note,
    ]).encode("utf-8")



def create_capability_grant(
    identity,
    current_record: own.OwnershipRecord,
    *,
    owner_token: str,
    capabilities: Iterable[str],
    note: str = "",
) -> CapabilityGrant:
    if current_record.revoked:
        raise PermissionError("revoked ownership record cannot authorize instance capabilities")
    if current_record.node_id != identity.node_id:
        raise PermissionScopeMismatch("ownership record node_id does not match signing identity")
    if current_record.instance_public_key != identity.public_key_hex:
        raise PermissionScopeMismatch("ownership record public key does not match signing identity")
    if own._hash_owner_token(owner_token) != current_record.owner_token_hash:
        raise PermissionValidationError("owner_token does not match current ownership record")

    capabilities = tuple(sorted(set(capabilities)))
    for capability in capabilities:
        if capability not in INSTANCE_CAPABILITIES:
            raise PermissionError(f"unknown instance capability: {capability}")

    issued_at = _now()
    payload = _grant_payload(
        node_id=identity.node_id,
        instance_public_key=identity.public_key_hex,
        owner_id=current_record.owner_id,
        ownership_sequence=current_record.sequence,
        owner_token_hash=current_record.owner_token_hash,
        capabilities=capabilities,
        issued_at=issued_at,
        note=note,
    )
    signature = identity.sign(_PERMISSION_DOMAIN, payload)
    return CapabilityGrant(
        node_id=identity.node_id,
        instance_public_key=identity.public_key_hex,
        owner_id=current_record.owner_id,
        ownership_sequence=current_record.sequence,
        owner_token_hash=current_record.owner_token_hash,
        capabilities=capabilities,
        issued_at=issued_at,
        note=note,
        signature=signature,
    )



def verify_capability_grant(grant: CapabilityGrant) -> bool:
    try:
        payload = _grant_payload(
            node_id=grant.node_id,
            instance_public_key=grant.instance_public_key,
            owner_id=grant.owner_id,
            ownership_sequence=grant.ownership_sequence,
            owner_token_hash=grant.owner_token_hash,
            capabilities=grant.capabilities,
            issued_at=grant.issued_at,
            note=grant.note,
        )
        from nacl.encoding import HexEncoder
        from nacl.exceptions import BadSignatureError
        from nacl.signing import VerifyKey
        verify_key = VerifyKey(grant.instance_public_key, encoder=HexEncoder)
        verify_key.verify(_PERMISSION_DOMAIN + b"|" + payload, bytes.fromhex(grant.signature))
        return True
    except (BadSignatureError, ValueError, TypeError, KeyError):
        return False


@dataclass
class InstancePermissionBoundary:
    identity: object
    ownership_history: own.OwnershipHistory
    presented_grant: Optional[CapabilityGrant] = None

    def current_record(self) -> own.OwnershipRecord:
        record = self.ownership_history.current()
        if record is None:
            raise PermissionValidationError("no ownership record is present")
        return record

    def describe(self) -> dict:
        current = self.current_record()
        return {
            "node_id": self.identity.node_id,
            "instance_public_key": self.identity.public_key_hex,
            "current_owner_id": current.owner_id,
            "current_ownership_sequence": current.sequence,
            "ownership_revoked": current.revoked,
            "presented_grant": None if self.presented_grant is None else self.presented_grant.to_dict(),
            "available_capabilities": list(INSTANCE_CAPABILITIES),
        }

    def bind(self, grant: CapabilityGrant) -> None:
        self.presented_grant = grant

    def require(self, capability: str) -> CapabilityGrant:
        if capability not in INSTANCE_CAPABILITIES:
            raise PermissionError(f"unknown instance capability: {capability}")
        grant = self.presented_grant
        if grant is None:
            raise PermissionDenied(f"{capability} requires an explicit capability grant")
        if not verify_capability_grant(grant):
            raise PermissionValidationError("capability grant signature is invalid")
        current = self.current_record()
        if current.revoked:
            raise PermissionValidationError("current ownership is revoked; no capability use is allowed")
        if grant.node_id != self.identity.node_id or grant.instance_public_key != self.identity.public_key_hex:
            raise PermissionScopeMismatch("capability grant is not scoped to this instance")
        if grant.node_id != current.node_id or grant.instance_public_key != current.instance_public_key:
            raise PermissionScopeMismatch("capability grant does not match current ownership scope")
        if grant.ownership_sequence != current.sequence:
            raise PermissionValidationError("capability grant is stale for the current ownership sequence")
        if grant.owner_id != current.owner_id:
            raise PermissionValidationError("capability grant owner_id does not match current owner")
        if grant.owner_token_hash != current.owner_token_hash:
            raise PermissionValidationError("capability grant owner continuity proof does not match current ownership")
        if not grant.allows(capability):
            raise PermissionDenied(f"capability grant does not allow {capability}")
        return grant


@dataclass
class PermissionedConfigStore:
    boundary: InstancePermissionBoundary
    _config: dict = field(default_factory=dict)

    def export_view(self) -> dict:
        self.boundary.require(MEMORY_READ)
        return json.loads(json.dumps(self._config, sort_keys=True))

    def update(self, values: dict) -> None:
        self.boundary.require(MEMORY_WRITE)
        self._config.update(json.loads(json.dumps(values, sort_keys=True)))

    def snapshot_unsafe(self) -> dict:
        return json.loads(json.dumps(self._config, sort_keys=True))
