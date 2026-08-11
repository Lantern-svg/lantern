"""Contact ledger: local record-keeping for the search for another sovereign
Lantern/agent instance.

This module does not perform outreach itself and does not contact a
network endpoint. It exists to make the difference between these states
explicit, machine-checkable, and impossible to silently collapse:

    CONTACT ATTEMPTED   -- we tried to reach a destination
    CONTACT PATH FOUND  -- a plausible destination/interface exists
    MESSAGE SENT        -- we transmitted something
    MESSAGE REACHABLE   -- the destination was live/responsive
    MESSAGE RECEIVED    -- there is independent evidence the destination
                           actually received the content
    MESSAGE ACKNOWLEDGED-- the destination responded referencing the
                           specific message
    IDENTITY VERIFIED   -- the responder's claimed identity has been
                           checked by *some* means (this module does not
                           implement cryptographic verification itself --
                           see lantern.identity / lantern.verified_contact
                           for the actual Ed25519 challenge/response flow;
                           this ledger records the *result* of that, not a
                           substitute for it)
    COLLABORATION AUTHORIZED -- an explicit, separate authorization
                           decision was made to proceed

None of these states is inferred from an earlier one. A ledger entry can
only advance by recording a new event with its own evidence; there is no
"upgrade" method that jumps stages.

This module is intentionally consistent with the existing live field
rendezvous experiment's verification ladder (see the operator's own
memory log): "UNVERIFIED_CLAIM -> DISCOVERED_COUNTERPARTY ->
PROTOCOL_COMPATIBLE -> IDENTITY_CRYPTOGRAPHICALLY_VERIFIED ->
CAPABILITY_AUTHORIZED -> SESSION_ESTABLISHED -> OBSERVATION_EXCHANGED".
`CONTACT_STATES` below is the more general vocabulary requested for this
phase; `LEGACY_FIELD_LADDER` is retained purely as a cross-reference so
the two vocabularies can be reasoned about side by side without treating
either as authoritative over the other.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from typing import Any, Optional
import uuid


CONTACT_LEDGER_VERSION = "0.1"

#: General contact-state vocabulary for this phase. Ordered for reference
#: only -- CONTACT_FAILED and NO_CONTACT_PATH can occur from any state,
#: and states are not required to be visited strictly in this order (e.g.
#: DISCOVERY_IN_PROGRESS can recur after CONTACT_FAILED).
CONTACT_STATES = (
    "NO_CONTACT_PATH",
    "DISCOVERY_IN_PROGRESS",
    "CONTACT_PATH_FOUND",
    "CONTACT_ATTEMPTED",
    "MESSAGE_SENT",
    "DELIVERY_UNKNOWN",
    "MESSAGE_RECEIVED",
    "ACKNOWLEDGED",
    "IDENTITY_VERIFIED",
    "COLLABORATION_NEGOTIATED",
    "COLLABORATION_ACTIVE",
    "CONTACT_FAILED",
)

#: Cross-reference only. This is the ladder already in active use by the
#: live public field rendezvous experiment; kept here so a caller can
#: relate the two vocabularies without this module claiming ownership of
#: that experiment's own bookkeeping.
LEGACY_FIELD_LADDER = (
    "UNVERIFIED_CLAIM",
    "DISCOVERED_COUNTERPARTY",
    "PROTOCOL_COMPATIBLE",
    "IDENTITY_CRYPTOGRAPHICALLY_VERIFIED",
    "CAPABILITY_AUTHORIZED",
    "SESSION_ESTABLISHED",
    "OBSERVATION_EXCHANGED",
)

#: States that count as "we know something concrete happened", as opposed
#: to states that are just our own intent/effort.
EVIDENCE_BACKED_STATES = frozenset({
    "MESSAGE_RECEIVED",
    "ACKNOWLEDGED",
    "IDENTITY_VERIFIED",
    "COLLABORATION_NEGOTIATED",
    "COLLABORATION_ACTIVE",
})

#: Contact types. LOCAL_SIMULATION must always be labeled as such and is
#: never reported as independent interoperability.
CONTACT_TYPES = (
    "REAL_INDEPENDENT_PEER",
    "LOCAL_SIMULATION",
    "UNKNOWN",
)


@dataclass(frozen=True)
class ContactEvidence:
    """Evidence for one contact-state transition. Fields are optional
    because early states (NO_CONTACT_PATH, DISCOVERY_IN_PROGRESS) may
    have little or nothing to attach yet -- but whatever is known should
    be recorded rather than asserted from memory."""

    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    destination: Optional[str] = None
    transport: Optional[str] = None
    request_id: Optional[str] = None
    response: Optional[str] = None
    response_status: Optional[str] = None
    peer_identity_claim: Optional[str] = None
    provenance: Optional[str] = None
    delivery_evidence: Optional[str] = None
    acknowledgment_evidence: Optional[str] = None
    failure_reason: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "destination": self.destination,
            "transport": self.transport,
            "request_id": self.request_id,
            "response": self.response,
            "response_status": self.response_status,
            "peer_identity_claim": self.peer_identity_claim,
            "provenance": self.provenance,
            "delivery_evidence": self.delivery_evidence,
            "acknowledgment_evidence": self.acknowledgment_evidence,
            "failure_reason": self.failure_reason,
        }


@dataclass(frozen=True)
class ContactAttempt:
    """One line of the contact ledger: a single state, with its evidence,
    for a single destination. Advancing state creates a NEW ContactAttempt
    via `advance()` rather than mutating history -- the ledger is a list
    of ContactAttempt objects, append-only in spirit even though this
    in-memory version does not persist to disk itself."""

    destination: str
    state: str
    contact_type: str = "UNKNOWN"
    evidence: ContactEvidence = field(default_factory=ContactEvidence)
    notes: str = ""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))

    def __post_init__(self) -> None:
        if self.state not in CONTACT_STATES:
            raise ValueError(f"unknown contact state: {self.state}")
        if self.contact_type not in CONTACT_TYPES:
            raise ValueError(f"unknown contact type: {self.contact_type}")

    @property
    def is_evidence_backed(self) -> bool:
        return self.state in EVIDENCE_BACKED_STATES

    @property
    def is_local_simulation(self) -> bool:
        return self.contact_type == "LOCAL_SIMULATION"

    def advance(
        self,
        state: str,
        *,
        evidence: Optional[ContactEvidence] = None,
        notes: Optional[str] = None,
    ) -> "ContactAttempt":
        """Create a new ContactAttempt entry recording a state transition.

        This never asserts a stronger state than the evidence given --
        callers are responsible for only calling advance() when they
        actually have the evidence for that specific state. There is no
        validation here that automatically checks evidence sufficiency,
        by design: that judgment belongs to whatever produced the
        evidence (e.g. an actual HTTP response, an actual identity proof
        verification), not to this bookkeeping layer.
        """
        if state not in CONTACT_STATES:
            raise ValueError(f"unknown contact state: {state}")
        return ContactAttempt(
            destination=self.destination,
            state=state,
            contact_type=self.contact_type,
            evidence=(evidence if evidence is not None else self.evidence),
            notes=(self.notes if notes is None else notes),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "destination": self.destination,
            "state": self.state,
            "contact_type": self.contact_type,
            "is_evidence_backed": self.is_evidence_backed,
            "is_local_simulation": self.is_local_simulation,
            "evidence": self.evidence.to_dict(),
            "notes": self.notes,
        }


class ContactLedger:
    """In-memory, append-only-in-spirit history of contact attempts.

    Guarantees this ledger enforces:
      - a destination cannot be reported as MESSAGE_RECEIVED or later
        without at least one prior recorded attempt for that destination
      - LOCAL_SIMULATION entries are always distinguishable from
        REAL_INDEPENDENT_PEER entries, and summary() never merges them
      - the ledger never asserts state on the caller's behalf; it only
        records what it is told, plus the sequencing/labeling invariants
        above
    """

    def __init__(self):
        self._entries: list[ContactAttempt] = []

    def record(self, attempt: ContactAttempt) -> ContactAttempt:
        history = self.history_for(attempt.destination)
        if not history and attempt.state not in ("NO_CONTACT_PATH", "DISCOVERY_IN_PROGRESS", "CONTACT_PATH_FOUND", "CONTACT_ATTEMPTED"):
            raise ValueError(
                f"cannot record {attempt.state!r} for {attempt.destination!r} "
                "with no prior contact history for that destination"
            )
        self._entries.append(attempt)
        return attempt

    def history_for(self, destination: str) -> list[ContactAttempt]:
        return [entry for entry in self._entries if entry.destination == destination]

    def latest_for(self, destination: str) -> Optional[ContactAttempt]:
        history = self.history_for(destination)
        return history[-1] if history else None

    def all(self) -> list[ContactAttempt]:
        return list(self._entries)

    def real_peer_contacts(self) -> list[ContactAttempt]:
        return [entry for entry in self._entries if entry.contact_type == "REAL_INDEPENDENT_PEER"]

    def evidence_backed_contacts(self) -> list[ContactAttempt]:
        return [entry for entry in self._entries if entry.is_evidence_backed]

    def summary(self) -> dict[str, Any]:
        destinations = sorted({entry.destination for entry in self._entries})
        latest_by_destination = {
            destination: self.latest_for(destination).to_dict()
            for destination in destinations
        }
        real_peer_established = any(
            entry.contact_type == "REAL_INDEPENDENT_PEER"
            and entry.state in ("COLLABORATION_NEGOTIATED", "COLLABORATION_ACTIVE")
            for entry in self._entries
        )
        return {
            "destinations_tracked": len(destinations),
            "total_attempts": len(self._entries),
            "latest_by_destination": latest_by_destination,
            "peer_contact_status": (
                "ESTABLISHED" if real_peer_established else "NOT_ESTABLISHED"
            ),
        }


# ==========================================================
# First inter-Lantern message template
# ==========================================================

FIRST_CONTACT_MESSAGE = (
    "I am a Lantern instance.\n"
    "I am testing sovereign agent interoperability.\n"
    "My authority is bounded.\n"
    "I do not grant authority to myself.\n"
    "I am looking for another independent agent/Lantern instance willing "
    "to acknowledge this message and establish a bounded interoperability "
    "test.\n"
    "No code execution or authority transfer is requested by this initial "
    "message.\n"
    "Please return:\n"
    "- your identity\n"
    "- your protocol/interface\n"
    "- whether you received this message\n"
    "- whether you are willing to perform a bounded handshake\n"
    "- any constraints on communication\n"
)


def build_contact_report(ledger: ContactLedger) -> dict[str, Any]:
    """Produce the exact reporting fields requested for the contact
    track of this phase. Values that are genuinely unknown are reported
    as the string "UNKNOWN" rather than omitted or guessed."""
    entries = ledger.all()
    real_peers = ledger.real_peer_contacts()
    sent = [e for e in entries if e.state in ("MESSAGE_SENT", "DELIVERY_UNKNOWN", "MESSAGE_RECEIVED", "ACKNOWLEDGED", "IDENTITY_VERIFIED", "COLLABORATION_NEGOTIATED", "COLLABORATION_ACTIVE")]
    delivered = [e for e in entries if e.state in ("MESSAGE_RECEIVED", "ACKNOWLEDGED", "IDENTITY_VERIFIED", "COLLABORATION_NEGOTIATED", "COLLABORATION_ACTIVE")]
    acknowledged = [e for e in entries if e.state in ("ACKNOWLEDGED", "IDENTITY_VERIFIED", "COLLABORATION_NEGOTIATED", "COLLABORATION_ACTIVE")]
    identity_verified = [e for e in entries if e.state in ("IDENTITY_VERIFIED", "COLLABORATION_NEGOTIATED", "COLLABORATION_ACTIVE")]
    peer_found = any(e.contact_type == "REAL_INDEPENDENT_PEER" and e.state != "CONTACT_FAILED" for e in entries)
    interoperability_active = any(e.state == "COLLABORATION_ACTIVE" for e in real_peers)

    return {
        "CONTACT_STATUS": (
            "COLLABORATION_ACTIVE" if interoperability_active
            else (ledger.latest_for(real_peers[-1].destination).state if real_peers else "NO_CONTACT_PATH")
        ),
        "DISCOVERY_ATTEMPTS": len({e.destination for e in entries}),
        "CONTACT_PATHS_FOUND": len({e.destination for e in entries if e.state != "NO_CONTACT_PATH"}),
        "MESSAGES_SENT": len(sent),
        "DELIVERY_CONFIRMED": len(delivered),
        "ACKNOWLEDGMENTS": len(acknowledged),
        "IDENTITY_VERIFIED": len(identity_verified),
        "PEER_FOUND": peer_found,
        "INTEROPERABILITY_TEST": "ACTIVE" if interoperability_active else "NOT_STARTED",
        "PEER_CONTACT_STATUS": "ESTABLISHED" if interoperability_active else "NOT_ESTABLISHED",
    }
