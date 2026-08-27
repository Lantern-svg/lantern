"""
Lantern Portable Instance v1

Portable export/import format for a personal Lantern instance.

This module intentionally exports portable state, not private-key bytes.
It preserves identity binding information, ownership authorization,
memory/evidence/provenance, configuration, and compatibility metadata,
while keeping private-state boundaries instance-scoped on import.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from . import compatibility as compat
from . import content_provenance as cp
from . import instance_permissions as perms
from . import ownership as own
from .core import EvidenceKernel
from .protocol import PROTOCOL_VERSION

FORMAT_VERSION = "1.0"
PORTABLE_INSTANCE_TYPE = "lantern.portable_instance"


class PortableInstanceError(Exception):
    pass


class ImportValidationError(PortableInstanceError):
    pass


class ExportValidationError(PortableInstanceError):
    pass


@dataclass(frozen=True)
class ImportedIdentity:
    node_id: str
    public_key_hex: str


@dataclass(frozen=True)
class PortableExportMetadata:
    format_version: str
    exported_at: str
    protocol_version: str
    compatibility_version: str
    node_id: str
    instance_public_key: str
    ownership_sequence: int
    ownership_record_signature: str
    export_hash: str

    def to_dict(self) -> dict:
        return {
            "format_version": self.format_version,
            "exported_at": self.exported_at,
            "protocol_version": self.protocol_version,
            "compatibility_version": self.compatibility_version,
            "node_id": self.node_id,
            "instance_public_key": self.instance_public_key,
            "ownership_sequence": self.ownership_sequence,
            "ownership_record_signature": self.ownership_record_signature,
            "export_hash": self.export_hash,
        }


class PortableInstance:
    def __init__(
        self,
        *,
        identity,
        ownership_history: own.OwnershipHistory,
        kernel: EvidenceKernel,
        configuration: dict,
        capability_grant: Optional[perms.CapabilityGrant] = None,
    ):
        self.identity = identity
        self.ownership_history = ownership_history
        self.kernel = kernel
        self.configuration = dict(configuration or {})
        self.capability_grant = capability_grant

    @property
    def current_ownership(self) -> own.OwnershipRecord:
        current = self.ownership_history.current()
        if current is None:
            raise ExportValidationError("instance has no ownership record")
        return current

    def boundary(self) -> perms.InstancePermissionBoundary:
        return perms.InstancePermissionBoundary(self.identity, self.ownership_history, self.capability_grant)

    def export_metadata(self) -> PortableExportMetadata:
        payload = self._state_payload()
        export_hash = hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        current = self.current_ownership
        return PortableExportMetadata(
            format_version=FORMAT_VERSION,
            exported_at=payload["exported_at"],
            protocol_version=PROTOCOL_VERSION,
            compatibility_version="0.83",
            node_id=self.identity.node_id,
            instance_public_key=self.identity.public_key_hex,
            ownership_sequence=current.sequence,
            ownership_record_signature=current.signature,
            export_hash=export_hash,
        )

    def _state_payload(self) -> dict:
        return {
            "type": PORTABLE_INSTANCE_TYPE,
            "format_version": FORMAT_VERSION,
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "identity": {
                "node_id": self.identity.node_id,
                "public_key": self.identity.public_key_hex,
            },
            "ownership": {
                "current": self.current_ownership.to_dict(),
                "history": self.ownership_history.to_list(),
            },
            "kernel": {
                "owner_instance": self.kernel.owner_instance,
                "step": self.kernel.step,
                "observations": [obs.__dict__ for obs in self.kernel.list_observations()],
                "evidence": [ev.__dict__ for ev in self.kernel.evidence],
                "contradictions": [c.__dict__ for c in self.kernel.contradictions],
                "resolutions": [r.__dict__ for r in self.kernel.resolutions],
            },
            "provenance": {
                "observations": [obs.metadata for obs in self.kernel.list_observations()],
            },
            "configuration": dict(self.configuration),
            "compatibility": {
                "protocol_version": PROTOCOL_VERSION,
                "compatibility_version": "0.83",
                "local_capabilities": list(compat.DEFAULT_CAPABILITIES.keys()),
            },
        }

    def export_payload(self) -> dict:
        payload = self._state_payload()
        payload["export_hash"] = hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        return payload

    def export_json(self) -> str:
        return json.dumps(self.export_payload(), indent=2, sort_keys=True)


def export_instance(instance: PortableInstance) -> dict:
    boundary = instance.boundary()
    boundary.require(perms.EXPORT_STATE)
    boundary.require(perms.MEMORY_READ)
    return instance.export_payload()


def _canonical_export_hash(payload: dict) -> str:
    clone = dict(payload)
    clone.pop("export_hash", None)
    return hashlib.sha256(
        json.dumps(clone, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _validate_export_shape(payload: dict) -> None:
    if not isinstance(payload, dict):
        raise ImportValidationError("portable instance export must be a JSON object")
    if payload.get("type") != PORTABLE_INSTANCE_TYPE:
        raise ImportValidationError("invalid portable instance type")
    if payload.get("format_version") != FORMAT_VERSION:
        raise ImportValidationError("unsupported portable instance format version")
    for required in ("identity", "ownership", "kernel", "configuration", "compatibility", "export_hash"):
        if required not in payload:
            raise ImportValidationError(f"portable instance export missing required section: {required}")


def _validate_identity_section(identity_section: dict, *, expected_node_id: Optional[str]) -> None:
    if not isinstance(identity_section, dict):
        raise ImportValidationError("identity section must be an object")
    if not identity_section.get("node_id") or not identity_section.get("public_key"):
        raise ImportValidationError("identity section is incomplete")
    if expected_node_id is not None and identity_section["node_id"] != expected_node_id:
        raise ImportValidationError("identity node_id does not match expected target instance")


def _validate_ownership_section(ownership_section: dict, identity_section: dict) -> own.OwnershipHistory:
    if not isinstance(ownership_section, dict):
        raise ImportValidationError("ownership section must be an object")
    history = own.OwnershipHistory.from_list(ownership_section.get("history", []))
    if not history.verify_chain():
        raise ImportValidationError("ownership history failed verification")
    current = history.current()
    if current is None:
        raise ImportValidationError("ownership history is empty")
    if current.node_id != identity_section["node_id"]:
        raise ImportValidationError("ownership node_id does not match identity")
    if current.instance_public_key != identity_section["public_key"]:
        raise ImportValidationError("ownership public key does not match identity")
    if current.revoked:
        raise ImportValidationError("revoked ownership cannot be imported as active state")
    if ownership_section.get("current") != current.to_dict():
        raise ImportValidationError("ownership current record does not match history tip")
    return history


def _validate_compatibility_section(compatibility_section: dict) -> None:
    if not isinstance(compatibility_section, dict):
        raise ImportValidationError("compatibility section must be an object")
    remote_version = compatibility_section.get("protocol_version")
    if remote_version is None:
        raise ImportValidationError("compatibility section missing protocol_version")
    if not compat.compatible_versions(PROTOCOL_VERSION, remote_version):
        raise ImportValidationError("incompatible protocol version")
    if remote_version != PROTOCOL_VERSION:
        raise ImportValidationError("protocol version incompatible with this instance")


def _validate_kernel_section(kernel_section: dict, identity_section: dict) -> EvidenceKernel:
    if not isinstance(kernel_section, dict):
        raise ImportValidationError("kernel section must be an object")
    if kernel_section.get("owner_instance") != identity_section["public_key"]:
        raise ImportValidationError("kernel owner boundary does not match exported identity")
    snapshot = {
        "owner_instance": identity_section["public_key"],
        "step": kernel_section.get("step", 0),
        "observations": kernel_section.get("observations", []),
        "evidence": kernel_section.get("evidence", []),
        "contradictions": kernel_section.get("contradictions", []),
        "resolutions": kernel_section.get("resolutions", []),
        "scars": [],
    }
    return EvidenceKernel.restore(snapshot)


def _validate_provenance(kernel: EvidenceKernel) -> None:
    for observation in kernel.list_observations():
        tag = cp.read_tag(observation.metadata)
        if tag is None:
            continue
        if observation.source == "peer" and tag.source_class == cp.FIRST_PARTY_OBSERVATION:
            raise ImportValidationError("peer-sourced observation cannot be imported as first-party observation")
        if tag.source_class not in cp.CONTENT_PROVENANCE_CLASSES:
            raise ImportValidationError("unknown content provenance class present in imported observation")


def import_instance(
    payload: dict,
    *,
    expected_node_id: Optional[str] = None,
    expected_public_key: Optional[str] = None,
    min_ownership_sequence: Optional[int] = None,
) -> PortableInstance:
    """Validate and restore a portable export payload.

    expected_public_key: pin this import to a specific instance public
        key. node_id alone is a caller-chosen label, not a cryptographic
        binding -- anyone can mint a fresh keypair and self-sign a fully
        internally-consistent export claiming an arbitrary node_id. When
        the importer already knows the real instance's public key (e.g.
        this is a re-import / refresh of a previously trusted instance,
        not a first contact), it MUST pass expected_public_key so a
        spoofed identity with a different key is rejected even though
        every signature inside the bundle verifies against ITSELF.
        On a genuine first import with no prior knowledge, there is
        nothing to pin against -- that is an inherent trust-on-first-use
        limitation of any offline export format, not something this
        function can close; callers should persist the public key they
        saw on first import and always pass it on every subsequent
        import for the same node_id.
    min_ownership_sequence: reject an import whose current ownership
        sequence is lower than this. Without this check, a validly
        signed but OLD export (captured before a later legitimate
        ownership transfer) can be replayed and accepted as current --
        every signature inside it is genuinely valid, it is simply
        stale. Callers re-importing a previously-known instance should
        pass the last sequence number they observed.
    """
    _validate_export_shape(payload)
    if _canonical_export_hash(payload) != payload.get("export_hash"):
        raise ImportValidationError("portable instance export hash mismatch")
    _validate_compatibility_section(payload["compatibility"])
    _validate_identity_section(payload["identity"], expected_node_id=expected_node_id)
    if expected_public_key is not None and payload["identity"]["public_key"] != expected_public_key:
        raise ImportValidationError(
            "identity public key does not match the previously trusted public key for this node_id"
        )
    ownership_history = _validate_ownership_section(payload["ownership"], payload["identity"])
    if min_ownership_sequence is not None and ownership_history.current().sequence < min_ownership_sequence:
        raise ImportValidationError(
            "ownership history is stale: current sequence is older than the last known sequence "
            "(this export may be a replay of a previously superseded ownership state)"
        )
    kernel = _validate_kernel_section(payload["kernel"], payload["identity"])
    _validate_provenance(kernel)
    identity = ImportedIdentity(
        node_id=payload["identity"]["node_id"],
        public_key_hex=payload["identity"]["public_key"],
    )
    return PortableInstance(
        identity=identity,
        ownership_history=ownership_history,
        kernel=kernel,
        configuration=payload.get("configuration", {}),
        capability_grant=None,
    )
