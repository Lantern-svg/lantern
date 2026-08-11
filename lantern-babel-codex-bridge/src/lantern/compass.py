"""Compass: orientation over EXISTING Lantern state. Not a new memory
system, not a new belief store, not a new authority mechanism.

Compass answers four questions by reading state that already exists
elsewhere in this codebase:

    WHAT matters?   -> lantern.core.EvidenceKernel (belief magnitude,
                       contradiction severity) + lantern.scars (unresolved
                       lessons) + open orchestration/contact states
    WHY?            -> evidence trail (Observation/Evidence ids),
                       provenance (orchestration.ProvenanceTag),
                       contradiction history
    WHAT is allowed? -> lantern.capability_authorization.CapabilityDecision
                       (per-peer) + orchestration.PROTECTED_AUTHORITIES /
                       NEVER_EXTERNALLY_EXPOSE (structural floor) +
                       CapabilityDescriptor.authority_requirements
    WHAT is next?    -> open DelegationRecord / ContactAttempt states that
                       have not reached a terminal state, ranked by
                       contradiction severity / belief uncertainty

Compass performs NO I/O, holds NO persistent state of its own, and NEVER
mutates anything it reads. It is a read-only lens over:
    - lantern.core.EvidenceKernel
    - lantern.scars (Scar / ScarRecord history, supplied by caller)
    - lantern.capability_authorization.CapabilityDecision (supplied by
      caller, since producing one requires an actual verified contact)
    - lantern.orchestration (DelegationRecord list, CapabilityDescriptor
      lookups via CapabilityRegistry, PROTECTED_AUTHORITIES /
      NEVER_EXTERNALLY_EXPOSE)
    - lantern.contact_ledger.ContactAttempt list

If a caller has no EvidenceKernel yet, has authorized nothing yet, has no
open delegations, and has no contact attempts, Compass returns a
CompassReading whose fields say so honestly (empty tuples / None) rather
than inventing salience out of nothing.

Nothing here introduces a second contradiction system, a second
authorization system, or a second contact ledger. Compass only reads and
ranks what the existing modules already recorded.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Optional, Sequence

from .core import Contradiction, EvidenceKernel
from .orchestration import (
    NEVER_EXTERNALLY_EXPOSE,
    PROTECTED_AUTHORITIES,
    TERMINAL_DELEGATION_STATUSES,
    CapabilityDescriptor,
    CapabilityRegistry,
    DelegationRecord,
)
from .contact_ledger import EVIDENCE_BACKED_STATES, ContactAttempt


COMPASS_VERSION = "0.1"


@dataclass(frozen=True)
class AttentionItem:
    """One thing Compass thinks may deserve attention, with its reason.

    `kind` identifies which existing subsystem this came from
    ("contradiction" | "open_delegation" | "open_contact" | "scar_lesson")
    so a caller can trace every AttentionItem back to the concrete
    existing record it was derived from via `source_id`.
    """

    kind: str
    subject: str
    reason: str
    source_id: Optional[str] = None
    severity: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "subject": self.subject,
            "reason": self.reason,
            "source_id": self.source_id,
            "severity": self.severity,
        }


@dataclass(frozen=True)
class AllowedAction:
    """One thing Compass has confirmed is allowed, with the exact
    existing-mechanism reason -- never asserted independently of
    capability_authorization / orchestration's own authority model."""

    capability: str
    allowed: bool
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {"capability": self.capability, "allowed": self.allowed, "reason": self.reason}


@dataclass(frozen=True)
class CompassReading:
    """One orientation snapshot. Nothing here is stored anywhere by
    Compass itself -- it is a value object a caller may choose to log,
    attach to a Scar, or discard."""

    what_matters: tuple[AttentionItem, ...] = field(default_factory=tuple)
    why: tuple[str, ...] = field(default_factory=tuple)
    what_is_allowed: tuple[AllowedAction, ...] = field(default_factory=tuple)
    what_is_next: tuple[AttentionItem, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        return {
            "what_matters": [item.to_dict() for item in self.what_matters],
            "why": list(self.why),
            "what_is_allowed": [item.to_dict() for item in self.what_is_allowed],
            "what_is_next": [item.to_dict() for item in self.what_is_next],
        }


def _contradiction_attention(contradictions: Iterable[Contradiction]) -> list[AttentionItem]:
    items = [
        AttentionItem(
            kind="contradiction",
            subject=c.concept,
            reason=(
                f"open contradiction on {c.concept!r}: "
                f"current_severity={c.current_severity:.3f}"
            ),
            source_id=c.id,
            severity=c.current_severity,
        )
        for c in contradictions
        if c.status == "OPEN"
    ]
    items.sort(key=lambda item: item.severity, reverse=True)
    return items


def _open_delegation_attention(delegations: Iterable[DelegationRecord]) -> list[AttentionItem]:
    items = []
    for record in delegations:
        if record.status in TERMINAL_DELEGATION_STATUSES:
            continue
        severity = 1.0 if record.requires_human_confirmation else 0.5
        items.append(AttentionItem(
            kind="open_delegation",
            subject=record.capability,
            reason=f"delegation {record.id} is {record.status}, not yet VERIFIED/FAILED",
            source_id=record.id,
            severity=severity,
        ))
    items.sort(key=lambda item: item.severity, reverse=True)
    return items


def _open_contact_attention(attempts: Iterable[ContactAttempt]) -> list[AttentionItem]:
    items = []
    for attempt in attempts:
        if attempt.state in ("CONTACT_FAILED",):
            continue
        if attempt.state in EVIDENCE_BACKED_STATES and attempt.state != "MESSAGE_RECEIVED":
            # ACKNOWLEDGED / IDENTITY_VERIFIED / COLLABORATION_* are
            # evidence-backed but may still need a next handshake step;
            # only fully negotiated collaboration is "done" for attention
            # purposes, and even that is left visible at low severity so
            # it stays inspectable rather than silently disappearing.
            severity = 0.3
        elif attempt.state == "COLLABORATION_ACTIVE":
            severity = 0.1
        else:
            severity = 0.6
        items.append(AttentionItem(
            kind="open_contact",
            subject=attempt.destination,
            reason=f"contact with {attempt.destination!r} is at {attempt.state}",
            source_id=attempt.id,
            severity=severity,
        ))
    items.sort(key=lambda item: item.severity, reverse=True)
    return items


def _evidence_trail(kernel: Optional[EvidenceKernel], concepts: Sequence[str]) -> list[str]:
    if kernel is None:
        return []
    trail: list[str] = []
    for concept in concepts:
        belief = kernel.belief(concept)
        related = [e for e in kernel.evidence if e.concept == concept]
        trail.append(
            f"{concept}: belief={belief:.3f} from {len(related)} evidence record(s)"
        )
    return trail


def what_is_allowed(
    registry: CapabilityRegistry,
    *,
    capability_decision: Optional[Any] = None,
) -> list[AllowedAction]:
    """Answer WHAT-is-allowed using ONLY existing authority mechanisms:

    - a capability that requires_protected_authority (orchestration's own
      computed property) is never asserted allowed by Compass itself
    - if the caller supplies a capability_authorization.CapabilityDecision
      (the actual existing per-peer authorization result), Compass
      reports exactly what that decision says via `.is_authorized()`
    - otherwise Compass can only report what is structurally forbidden
      (NEVER_EXTERNALLY_EXPOSE) or protected (PROTECTED_AUTHORITIES);
      it never invents an "allowed" answer with no CapabilityDecision
      behind it
    """
    results: list[AllowedAction] = []
    for descriptor in registry.all():
        if descriptor.requires_protected_authority:
            never_exposed = bool(
                descriptor.authority_requirements & NEVER_EXTERNALLY_EXPOSE
            )
            if never_exposed:
                results.append(AllowedAction(
                    capability=descriptor.name,
                    allowed=False,
                    reason=(
                        "structurally forbidden: touches a "
                        "NEVER_EXTERNALLY_EXPOSE authority"
                    ),
                ))
                continue
            if capability_decision is not None and hasattr(capability_decision, "is_authorized"):
                allowed = bool(capability_decision.is_authorized(descriptor.name))
                results.append(AllowedAction(
                    capability=descriptor.name,
                    allowed=allowed,
                    reason=(
                        "per existing capability_authorization.CapabilityDecision"
                        if allowed
                        else "not present in CapabilityDecision.authorized_capabilities"
                    ),
                ))
                continue
            results.append(AllowedAction(
                capability=descriptor.name,
                allowed=False,
                reason=(
                    "requires protected authority "
                    f"{sorted(descriptor.authority_requirements)}; no "
                    "CapabilityDecision supplied to authorize it"
                ),
            ))
            continue
        results.append(AllowedAction(
            capability=descriptor.name,
            allowed=True,
            reason="no protected authority required by this capability's descriptor",
        ))
    return results


def orient(
    *,
    kernel: Optional[EvidenceKernel] = None,
    concepts_of_interest: Sequence[str] = (),
    registry: Optional[CapabilityRegistry] = None,
    capability_decision: Optional[Any] = None,
    open_delegations: Sequence[DelegationRecord] = (),
    open_contacts: Sequence[ContactAttempt] = (),
) -> CompassReading:
    """Build one CompassReading from whatever existing state the caller
    supplies. Every argument is optional; Compass never fabricates state
    it was not given. This function performs no I/O and mutates nothing.
    """
    contradictions = list(kernel.contradictions) if kernel is not None else []

    what_matters = (
        _contradiction_attention(contradictions)
        + [
            item for item in _open_contact_attention(open_contacts)
            if item.severity >= 0.5
        ]
    )
    what_matters.sort(key=lambda item: item.severity, reverse=True)

    why = _evidence_trail(kernel, concepts_of_interest)

    allowed = what_is_allowed(registry, capability_decision=capability_decision) if registry is not None else []

    what_is_next = (
        _open_delegation_attention(open_delegations)
        + _open_contact_attention(open_contacts)
    )
    what_is_next.sort(key=lambda item: item.severity, reverse=True)

    return CompassReading(
        what_matters=tuple(what_matters),
        why=tuple(why),
        what_is_allowed=tuple(allowed),
        what_is_next=tuple(what_is_next),
    )
