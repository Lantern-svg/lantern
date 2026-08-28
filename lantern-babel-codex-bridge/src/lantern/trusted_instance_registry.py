"""
Trusted Instance Registry - Lantern Phase C

Purpose:
    Establish and maintain a persistent, provenance-aware record of what
    this personal Lantern instance knows about each PEER instance it has
    contacted -- specifically: which public key is trusted for which node_id,
    what the highest accepted ownership sequence is, and the full history
    of how that state was arrived at.

    This is the missing piece that makes Phase B's opt-in
    expected_public_key and min_ownership_sequence parameters
    default-enforced rather than caller-optional.

Design constraints:
    - Never silently overwrite conflicting identity state.
    - A node_id presenting a DIFFERENT public key = collision event
      requiring EXPLICIT resolution.
    - Never silently move a known ownership sequence backward.
    - Do NOT treat first contact as trusted (TOFU limitation documented).
    - Registry is persistent and instance-scoped (not globally shared).
    - Do not erase conflicting history -- record every collision.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Optional


class RegistryError(Exception): pass
class CollisionError(RegistryError): pass
class SequenceRollbackError(RegistryError): pass
class UntrustedError(RegistryError): pass


class TrustState(str, Enum):
    UNKNOWN = "unknown"
    TRUSTED = "trusted"
    COLLISION_DETECTED = "collision_detected"
    RESOLVED = "resolved"


class ProvenanceTag(str, Enum):
    FIRST_CONTACT_SELF_CONSISTENT = "first_contact_self_consistent"
    FIRST_CONTACT_ENROLLMENT = "first_contact_enrollment"
    OWNERSHIP_TRANSFER_EVIDENCE = "ownership_transfer_evidence"
    PORTABLE_EXPORT_IMPORT = "portable_export_import"
    PEER_IDENTITY_PROOF = "peer_identity_proof"
    EXPLICIT_OPERATOR_ENTRY = "explicit_operator_entry"
    COLLISION_RESOLUTION = "collision_resolution"


@dataclass(frozen=True)
class ContactEvent:
    event_id: str
    timestamp: str
    event_type: str
    trust_state: TrustState
    public_key: Optional[str]
    ownership_sequence: Optional[int]
    outcome: str
    provenance: ProvenanceTag
    notes: str = ""
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "event_id": self.event_id,
            "timestamp": self.timestamp,
            "event_type": self.event_type,
            "trust_state": self.trust_state.value,
            "public_key": self.public_key,
            "ownership_sequence": self.ownership_sequence,
            "outcome": self.outcome,
            "provenance": self.provenance.value,
            "notes": self.notes,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "ContactEvent":
        return cls(
            event_id=d["event_id"],
            timestamp=d["timestamp"],
            event_type=d["event_type"],
            trust_state=TrustState(d["trust_state"]),
            public_key=d.get("public_key"),
            ownership_sequence=d.get("ownership_sequence"),
            outcome=d["outcome"],
            provenance=ProvenanceTag(d["provenance"]),
            notes=d.get("notes", ""),
            metadata=d.get("metadata", {}),
        )


@dataclass(frozen=True)
class CollisionRecord:
    collision_id: str
    timestamp: str
    node_id: str
    trusted_public_key: str
    presented_public_key: str
    trusted_ownership_sequence: int
    presented_ownership_sequence: int
    resolution: Optional[str] = None
    resolution_notes: str = ""
    resolved_at: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "collision_id": self.collision_id,
            "timestamp": self.timestamp,
            "node_id": self.node_id,
            "trusted_public_key": self.trusted_public_key,
            "presented_public_key": self.presented_public_key,
            "trusted_ownership_sequence": self.trusted_ownership_sequence,
            "presented_ownership_sequence": self.presented_ownership_sequence,
            "resolution": self.resolution,
            "resolution_notes": self.resolution_notes,
            "resolved_at": self.resolved_at,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "CollisionRecord":
        return cls(
            collision_id=d["collision_id"],
            timestamp=d["timestamp"],
            node_id=d["node_id"],
            trusted_public_key=d["trusted_public_key"],
            presented_public_key=d["presented_public_key"],
            trusted_ownership_sequence=d["trusted_ownership_sequence"],
            presented_ownership_sequence=d["presented_ownership_sequence"],
            resolution=d.get("resolution"),
            resolution_notes=d.get("resolution_notes", ""),
            resolved_at=d.get("resolved_at"),
        )


@dataclass(frozen=True)
class PriorState:
    node_id: str
    trust_state: TrustState
    expected_public_key: Optional[str]
    min_ownership_sequence: int
    first_contact_at: Optional[str] = None
    last_contact_at: Optional[str] = None
    collisions: tuple[CollisionRecord, ...] = ()
    contact_history: tuple[ContactEvent, ...] = ()

    @property
    def has_trusted_state(self) -> bool:
        return self.expected_public_key is not None


@dataclass
class PeerRegistryEntry:
    node_id: str
    trust_state: TrustState
    trusted_public_key: Optional[str] = None
    highest_accepted_sequence: int = 0
    first_contact_at: Optional[str] = None
    last_contact_at: Optional[str] = None
    collisions: list[CollisionRecord] = field(default_factory=list)
    contact_history: list[ContactEvent] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "node_id": self.node_id,
            "trust_state": self.trust_state.value,
            "trusted_public_key": self.trusted_public_key,
            "highest_accepted_sequence": self.highest_accepted_sequence,
            "first_contact_at": self.first_contact_at,
            "last_contact_at": self.last_contact_at,
            "collisions": [c.to_dict() for c in self.collisions],
            "contact_history": [e.to_dict() for e in self.contact_history],
        }

    @classmethod
    def from_dict(cls, d: dict) -> "PeerRegistryEntry":
        return cls(
            node_id=d["node_id"],
            trust_state=TrustState(d["trust_state"]),
            trusted_public_key=d.get("trusted_public_key"),
            highest_accepted_sequence=d.get("highest_accepted_sequence", 0),
            first_contact_at=d.get("first_contact_at"),
            last_contact_at=d.get("last_contact_at"),
            collisions=[CollisionRecord.from_dict(c) for c in d.get("collisions", [])],
            contact_history=[ContactEvent.from_dict(e) for e in d.get("contact_history", [])],
        )


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _default_registry_path(data_dir):
    return Path(data_dir) / "peers"


class TrustedInstanceRegistry:
    def __init__(self, data_dir, *, read_only: bool = False):
        self._data_dir = Path(data_dir)
        self._read_only = read_only
        self._entries: dict = {}
        self._dirty = False

    def _validate_node_id(self, node_id: str) -> str:
        """Reject any node_id that could escape the registry's own
        directory when used as a path segment (e.g. "../../etc/passwd",
        absolute paths, embedded path separators, or empty/whitespace
        values). node_id is caller-supplied and untrusted -- it must
        never be interpolated into a filesystem path without this check.
        """
        if not isinstance(node_id, str) or not node_id or node_id.strip() != node_id:
            raise RegistryError(f"invalid node_id: {node_id!r}")
        if node_id in (".", ".."):
            raise RegistryError(f"invalid node_id: {node_id!r}")
        if "/" in node_id or "\\" in node_id or "\x00" in node_id:
            raise RegistryError(f"invalid node_id: {node_id!r}")
        candidate = _default_registry_path(self._data_dir) / node_id
        resolved_base = _default_registry_path(self._data_dir).resolve()
        resolved_candidate = candidate.resolve()
        if resolved_base not in resolved_candidate.parents and resolved_candidate != resolved_base:
            raise RegistryError(f"invalid node_id: {node_id!r} escapes registry directory")
        return node_id

    def _peer_file(self, node_id: str) -> Path:
        node_id = self._validate_node_id(node_id)
        return _default_registry_path(self._data_dir) / node_id / "registry.json"

    def _load_entry(self, node_id: str):
        path = self._peer_file(node_id)
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text())
            entry = PeerRegistryEntry.from_dict(data)
            if entry.node_id != node_id:
                return None
            return entry
        except (json.JSONDecodeError, KeyError, ValueError):
            return None

    def _save_entry(self, entry) -> None:
        if self._read_only:
            return
        path = self._peer_file(entry.node_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(entry.to_dict(), indent=2, sort_keys=True))

    def _ensure_loaded(self, node_id: str):
        if node_id not in self._entries:
            loaded = self._load_entry(node_id)
            self._entries[node_id] = loaded if loaded is not None else PeerRegistryEntry(node_id=node_id, trust_state=TrustState.UNKNOWN)
        return self._entries[node_id]

    def prior_state(self, node_id: str) -> PriorState:
        entry = self._ensure_loaded(node_id)
        return PriorState(
            node_id=entry.node_id,
            trust_state=entry.trust_state,
            expected_public_key=entry.trusted_public_key,
            min_ownership_sequence=entry.highest_accepted_sequence,
            first_contact_at=entry.first_contact_at,
            last_contact_at=entry.last_contact_at,
            collisions=tuple(entry.collisions),
            contact_history=tuple(entry.contact_history),
        )

    def all_peers(self) -> list:
        base = _default_registry_path(self._data_dir)
        if base.exists():
            for subdir in base.iterdir():
                if subdir.is_dir() and (subdir / "registry.json").exists():
                    self._ensure_loaded(subdir.name)
        return [self.prior_state(node_id) for node_id in self._entries]

    def unverified_first_contacts(self) -> list:
        return [s for s in self.all_peers() if s.trust_state == TrustState.UNKNOWN and s.has_trusted_state]

    def active_collisions(self) -> list:
        return [s for s in self.all_peers() if s.trust_state == TrustState.COLLISION_DETECTED]

    def check_and_record(
        self,
        *,
        node_id: str,
        presented_public_key: str,
        presented_ownership_sequence: int,
        outcome: str,
        event_type: str = "import_attempt",
        provenance: ProvenanceTag = ProvenanceTag.PORTABLE_EXPORT_IMPORT,
        notes: str = "",
        metadata: Optional[dict] = None,
    ) -> PriorState:
        entry = self._ensure_loaded(node_id)
        now = _now()
        event_id = str(uuid.uuid4())

        # Collision check
        if entry.trust_state in (TrustState.TRUSTED, TrustState.RESOLVED) or entry.trusted_public_key is not None:
            if entry.trusted_public_key is not None and presented_public_key != entry.trusted_public_key:
                collision = CollisionRecord(
                    collision_id=str(uuid.uuid4()),
                    timestamp=now,
                    node_id=node_id,
                    trusted_public_key=entry.trusted_public_key,
                    presented_public_key=presented_public_key,
                    trusted_ownership_sequence=entry.highest_accepted_sequence,
                    presented_ownership_sequence=presented_ownership_sequence,
                )
                entry.collisions.append(collision)
                entry.trust_state = TrustState.COLLISION_DETECTED
                self._dirty = True
                event = ContactEvent(
                    event_id=event_id, timestamp=now, event_type=event_type,
                    trust_state=TrustState.COLLISION_DETECTED,
                    public_key=presented_public_key,
                    ownership_sequence=presented_ownership_sequence,
                    outcome="collision", provenance=provenance,
                    notes=notes, metadata=metadata or {},
                )
                entry.contact_history.append(event)
                self._save_entry(entry)
                raise CollisionError(
                    f"public key mismatch for {node_id!r}: "
                    f"trusted {entry.trusted_public_key[:16]}..., "
                    f"presented {presented_public_key[:16]}...; "
                    "collision recorded, awaiting explicit resolution"
                )

        # Sequence rollback check
        if entry.highest_accepted_sequence > 0 and presented_ownership_sequence < entry.highest_accepted_sequence:
            event = ContactEvent(
                event_id=event_id, timestamp=now, event_type=event_type,
                trust_state=entry.trust_state,
                public_key=presented_public_key,
                ownership_sequence=presented_ownership_sequence,
                outcome="rejected", provenance=provenance,
                notes=f"rejected: sequence {presented_ownership_sequence} < highest accepted {entry.highest_accepted_sequence} (possible replay)",
                metadata=metadata or {},
            )
            entry.contact_history.append(event)
            self._dirty = True
            self._save_entry(entry)
            raise SequenceRollbackError(
                f"ownership sequence rollback for {node_id!r}: "
                f"presented {presented_ownership_sequence}, highest accepted {entry.highest_accepted_sequence}"
            )

        # Accept
        if entry.first_contact_at is None:
            entry.first_contact_at = now
        entry.last_contact_at = now

        if presented_ownership_sequence >= entry.highest_accepted_sequence:
            entry.highest_accepted_sequence = presented_ownership_sequence
            if entry.trust_state == TrustState.UNKNOWN and entry.trusted_public_key is None:
                entry.trusted_public_key = presented_public_key

        event = ContactEvent(
            event_id=event_id, timestamp=now, event_type=event_type,
            trust_state=entry.trust_state,
            public_key=presented_public_key,
            ownership_sequence=presented_ownership_sequence,
            outcome=outcome, provenance=provenance,
            notes=notes, metadata=metadata or {},
        )
        entry.contact_history.append(event)
        self._dirty = True
        self._save_entry(entry)
        return self.prior_state(node_id)

    def enroll_peer(
        self,
        node_id: str,
        trusted_public_key: str,
        trusted_ownership_sequence: int,
        *,
        provenance: ProvenanceTag = ProvenanceTag.FIRST_CONTACT_ENROLLMENT,
        notes: str = "",
    ) -> PriorState:
        entry = self._ensure_loaded(node_id)
        now = _now()
        event_id = str(uuid.uuid4())

        if entry.trust_state == TrustState.TRUSTED:
            if entry.trusted_public_key != trusted_public_key:
                raise CollisionError(f"cannot enroll {node_id!r}: different key already trusted")
            if trusted_ownership_sequence > entry.highest_accepted_sequence:
                entry.highest_accepted_sequence = trusted_ownership_sequence
            self._save_entry(entry)
            return self.prior_state(node_id)

        if entry.trust_state == TrustState.COLLISION_DETECTED:
            raise CollisionError(f"cannot enroll {node_id!r}: collision recorded; resolve it first")

        entry.trust_state = TrustState.TRUSTED
        entry.trusted_public_key = trusted_public_key
        entry.highest_accepted_sequence = max(entry.highest_accepted_sequence, trusted_ownership_sequence)
        entry.last_contact_at = now
        if entry.first_contact_at is None:
            entry.first_contact_at = now

        event = ContactEvent(
            event_id=event_id, timestamp=now, event_type="enrollment",
            trust_state=TrustState.TRUSTED,
            public_key=trusted_public_key,
            ownership_sequence=trusted_ownership_sequence,
            outcome="enrollment", provenance=provenance, notes=notes,
        )
        entry.contact_history.append(event)
        self._dirty = True
        self._save_entry(entry)
        return self.prior_state(node_id)

    def resolve_collision(
        self,
        node_id: str,
        resolution: str,
        *,
        resolved_public_key: str,
        resolved_ownership_sequence: int,
        provenance: ProvenanceTag = ProvenanceTag.COLLISION_RESOLUTION,
        notes: str = "",
    ) -> PriorState:
        """Record an operator's resolution of a pending collision.

        SECURITY NOTE: this method does NOT itself verify that the
        resolution is authentic -- it has no independent way to confirm
        which of the two colliding keys is legitimate. It trusts its
        caller. This mirrors content_provenance.promote_to_first_party():
        the registry provides the STATE MACHINE (only COLLISION_DETECTED
        -> RESOLVED is a legal transition, and the full collision record
        is preserved either way), but actual authentication of "is this
        really the rightful owner resolving their own collision" is the
        caller's responsibility (e.g. an out-of-band verified channel,
        an ownership-transfer signature, or explicit human review).
        Anyone with access to this registry object can call this method
        and have it accepted. Do not expose resolve_collision() to an
        untrusted network caller without an authentication layer in
        front of it.
        """
        entry = self._ensure_loaded(node_id)
        if entry.trust_state != TrustState.COLLISION_DETECTED:
            raise RegistryError(f"{node_id!r} is not in COLLISION_DETECTED state")
        now = _now()
        event_id = str(uuid.uuid4())

        for coll in reversed(entry.collisions):
            if coll.resolution is None:
                object.__setattr__(coll, "resolution", resolution)
                object.__setattr__(coll, "resolved_at", now)
                object.__setattr__(coll, "resolution_notes", notes)
                break

        entry.trust_state = TrustState.RESOLVED
        entry.trusted_public_key = resolved_public_key
        entry.highest_accepted_sequence = max(entry.highest_accepted_sequence, resolved_ownership_sequence)
        entry.last_contact_at = now

        event = ContactEvent(
            event_id=event_id, timestamp=now, event_type="collision_resolution",
            trust_state=TrustState.RESOLVED,
            public_key=resolved_public_key,
            ownership_sequence=resolved_ownership_sequence,
            outcome="enrollment", provenance=provenance,
            notes=f"resolved: {resolution}. {notes}",
        )
        entry.contact_history.append(event)
        self._dirty = True
        self._save_entry(entry)
        return self.prior_state(node_id)

    def flush(self) -> None:
        if not self._dirty or self._read_only:
            return
        for entry in self._entries.values():
            self._save_entry(entry)
        self._dirty = False

    def reload(self) -> None:
        self._entries.clear()
        self._dirty = False
