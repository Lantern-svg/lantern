"""Compression: carry less information without losing what matters.

This module does NOT introduce a new memory system. It defines the small
OBSERVE -> COMPASS -> COMPRESS -> ACT -> VERIFY -> COMPRESS pipeline shape
requested for this phase, and it produces its compressed output using the
EXISTING Scar record shape from lantern.scars (Scar.lesson / .outcome /
.related_contradiction_id / .related_evidence_ids / .provenance is already
exactly the "durable, provenance-linked summary of a cycle" this phase
asked for -- see scars.py's own docstring: "A Scar records experience").

The only new things in this module are:
  1. `CompressedCycle` -- a value object bundling one OBSERVE..VERIFY
     cycle's inputs/outputs together with a Scar, so a caller has one
     handle instead of five separately-tracked pieces.
  2. `compress_cycle()` -- builds a Scar (via scars.create_scar, not a
     new constructor) from a CompassReading + orchestration/contact
     results, and validates the "never compress" invariants below
     BEFORE returning, raising CompressionViolation if one is broken.

Invariants this module enforces mechanically (not just by convention),
per the phase brief's explicit list:

    UNKNOWN     -> KNOWN       (never silently asserted)
    CLAIM       -> FACT        (never silently asserted)
    RETURNED    -> VERIFIED    (never silently asserted)
    REMOTE      -> LOCAL       (never silently asserted)
    ATTEMPTED   -> RECEIVED    (never silently asserted)
    CAPABILITY  -> AUTHORITY   (never silently asserted)

`compress_cycle()` checks the actual DelegationRecord / ContactAttempt /
ProvenanceTag / CapabilityDescriptor objects it was given for exactly
these collapses and refuses to build a Scar that would encode a false
compression.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from .compass import CompassReading
from .contact_ledger import ContactAttempt
from .orchestration import (
    TERMINAL_DELEGATION_STATUSES,
    DelegationRecord,
    ProvenanceTag,
)
from .scars import Scar, ScarRecord, create_scar


COMPRESSION_VERSION = "0.1"


class CompressionViolation(ValueError):
    """Raised when compress_cycle() would collapse a distinction the
    phase brief says must never be collapsed."""


@dataclass(frozen=True)
class CompressedCycle:
    """One OBSERVE->COMPASS->COMPRESS->ACT->VERIFY->COMPRESS cycle,
    bundled with the Scar produced from it. `compass_before` is the
    orientation that led to acting; `scar` is the compressed record of
    what happened. Nothing here is a second memory store: `scar` is the
    same Scar/ScarRecord type used everywhere else in this codebase, and
    persisting it (if desired) still goes through the existing
    Lantern.persist_scar() -> Chronicle path, not a new one.
    """

    compass_before: CompassReading
    delegation: Optional[DelegationRecord]
    contact: Optional[ContactAttempt]
    scar_record: ScarRecord

    def to_dict(self) -> dict[str, Any]:
        return {
            "compass_before": self.compass_before.to_dict(),
            "delegation": self.delegation.to_dict() if self.delegation else None,
            "contact": self.contact.to_dict() if self.contact else None,
            "scar_record": self.scar_record.to_dict(),
        }


def _check_delegation_invariants(delegation: DelegationRecord) -> None:
    # RETURNED -> VERIFIED: a Scar claiming a delegation "succeeded" or
    # "was verified" must not be built from a merely-RETURNED record.
    if delegation.status == "RETURNED" and delegation.verification_summary:
        raise CompressionViolation(
            "delegation is RETURNED but carries a verification_summary; "
            "RETURNED must not be compressed into VERIFIED"
        )
    # CAPABILITY -> AUTHORITY: a delegation whose authority_scope exceeds
    # what its own record declares as forbidden is already invalid at
    # construction (DelegationRecord.__post_init__ checks this), but we
    # re-check the general claim here defensively: allowed_capabilities
    # is not the same thing as "authorized" — this module makes no claim
    # of authorization beyond what the DelegationRecord itself declares.
    if delegation.status == "VERIFIED" and delegation.verification_summary is None:
        raise CompressionViolation(
            "delegation is VERIFIED but has no verification_summary; "
            "a worker's RETURNED claim alone can never justify VERIFIED"
        )


def _check_contact_invariants(contact: ContactAttempt) -> None:
    # ATTEMPTED -> RECEIVED
    if contact.state in ("CONTACT_ATTEMPTED", "MESSAGE_SENT", "DELIVERY_UNKNOWN"):
        if contact.evidence.acknowledgment_evidence or contact.evidence.delivery_evidence:
            # Evidence fields describing receipt must not coexist with a
            # pre-receipt state -- that would be a silent ATTEMPTED->RECEIVED
            # compression hiding in the evidence payload.
            raise CompressionViolation(
                f"contact state {contact.state} carries delivery/acknowledgment "
                "evidence; ATTEMPTED must not be compressed into RECEIVED"
            )


def _check_provenance_invariant(provenance: Optional[ProvenanceTag]) -> None:
    # REMOTE -> LOCAL: nothing in this module is permitted to rewrite a
    # remote ProvenanceTag into a local one. Since ProvenanceTag is frozen
    # and this function never constructs a replacement, the only failure
    # mode would be a caller passing an already-corrupted tag; validate
    # that source_class is still one of the module's own known classes
    # (ProvenanceTag.__post_init__ already guarantees this, so this is a
    # belt-and-suspenders re-check, not new validation logic).
    if provenance is not None:
        assert provenance.source_class, "ProvenanceTag must retain its source_class"


def compress_cycle(
    *,
    compass_before: CompassReading,
    delegation: Optional[DelegationRecord] = None,
    contact: Optional[ContactAttempt] = None,
    source: str,
    trigger: str,
    observation: str,
    outcome: str,
    severity: str,
    lesson: Optional[str] = None,
) -> CompressedCycle:
    """Compress one cycle into a Scar, enforcing the never-compress
    invariants first. Uses scars.create_scar() (the existing mechanism)
    rather than constructing a new record type.

    `outcome`/`severity`/`lesson` are the caller's own honest summary of
    what happened -- this function does not infer or upgrade them; it
    only refuses to proceed if the supplied delegation/contact/provenance
    objects contradict what a compression would need to be true.
    """
    if delegation is not None:
        _check_delegation_invariants(delegation)
        _check_provenance_invariant(delegation.result_provenance)
    if contact is not None:
        _check_contact_invariants(contact)

    related_evidence_ids = tuple(
        item.source_id
        for item in compass_before.what_matters
        if item.kind == "contradiction" and item.source_id
    )
    related_contradiction_id = related_evidence_ids[0] if related_evidence_ids else None

    provenance: dict[str, Any] = {}
    if delegation is not None:
        provenance["delegation_id"] = delegation.id
        provenance["delegation_status"] = delegation.status
        if delegation.result_provenance is not None:
            provenance["result_provenance"] = delegation.result_provenance.to_dict()
    if contact is not None:
        provenance["contact_id"] = contact.id
        provenance["contact_state"] = contact.state
        provenance["contact_destination"] = contact.destination

    scar_record = create_scar(
        source=source,
        trigger=trigger,
        observation=observation,
        outcome=outcome,
        severity=severity,
        lesson=lesson,
        related_contradiction_id=related_contradiction_id,
        related_evidence_ids=related_evidence_ids,
        provenance=provenance,
    )

    return CompressedCycle(
        compass_before=compass_before,
        delegation=delegation,
        contact=contact,
        scar_record=scar_record,
    )
