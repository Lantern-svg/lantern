"""Authorized observation exchange: the first phase where an explicitly
AUTHORIZED capability (not merely a shared/negotiated one) may actually be
exercised, plus the minimum machinery to detect a contradiction between a
local and a remote-sourced observation.

Position in the pipeline:

    NetworkContactPolicy -> NetworkContactTransport -> verify_contact()
        -> VerifiedContactResult
        -> capability_authorization.authorize()
        -> CapabilityDecision (must have "evidence_exchange" AUTHORIZED)
        -> observation_exchange.receive_observation()   <-- THIS MODULE
        -> local Observation (+ optional contradiction result)

This module answers exactly one question:

    "Given that this remote node is cryptographically verified AND has
    been explicitly authorized (not merely negotiated) for
    evidence_exchange, may I create a LOCAL Observation recording what
    it claims to have observed?"

It never answers, and never touches:

    - "Is the remote claim true?"            (belief; not this module)
    - "Should I trust this node more now?"   (trust_status; not this module)
    - "Does this outrank my own evidence?"   (evidence promotion is a
      separate, explicit, local act -- see EVIDENCE BOUNDARY below).

============================================================
Why this module exists instead of reusing lantern.bridge
============================================================

lantern.bridge.LanternAgentBridge._on_observation_share already turns an
OBSERVATION_SHARE message into a local Observation -- but its gate is
LanternRouter.route(), which only checks
compatibility.can_exchange(compat, "evidence_exchange"): i.e. it accepts
any message from a peer that merely NEGOTIATED the evidence_exchange
capability during handshake, with no cryptographic identity check and no
explicit operator authorization at all (see
tests/test_two_instance_integration.py's own module docstring, which
already flags this as a known open item, mirroring the same gap in
lantern.federation.FederationAdapter).

This phase requires a strictly stronger gate:

    cryptographically verified identity
    AND
    explicit CapabilityDecision.is_authorized("evidence_exchange")

which is a narrower condition than "shared capability" alone.
lantern.bridge / lantern.router / lantern.boundary are intentionally NOT
modified here (their internal gating logic is out of scope for this
phase) -- this module is a new, stricter, additive entry point. The
weaker bridge.py path continues to exist unchanged; that is recorded
below under KNOWN LIMITATIONS in the final report, not silently patched
over.

============================================================
Authorization must happen before any state mutation
============================================================

    incoming ProtocolMessage
      -> identify sender (message.source, VerifiedContactResult.remote_node_id)
      -> confirm identity_status == CRYPTOGRAPHICALLY_VERIFIED
      -> confirm CapabilityDecision.is_authorized("evidence_exchange")
      -> NO  -> reject, ZERO local state mutation
      -> YES -> validate message structure/bounds (hostile input)
             -> NO  -> reject, ZERO local state mutation
             -> YES -> replay check (bounded in-memory message_id set)
                    -> already seen -> reject as duplicate, ZERO mutation
                    -> new -> create local Observation (agent.observe())

Every rejection path returns a structured ObservationExchangeResult and
touches no Lantern state. There is no partial-entry case.

============================================================
Remote observation vs remote belief
============================================================

The remote node sends "node A observed X", never "believe X". This
module's output is always a lantern.core.Observation (an unopinionated
record of a claim + its provenance), never a call to add_evidence() or
belief(). Promoting a received Observation into Evidence (and therefore
into belief()) remains a separate, explicit, LOCAL decision the caller
makes afterward by calling agent.add_evidence() directly, exactly as
tests/test_two_instance_integration.py's own
test_persistence_after_receiving_observation_via_protocol already does.
This module never calls add_evidence(), belief(), or resolve() itself.

============================================================
Remote reliability is a claim, never local authority
============================================================

Mirrors lantern.bridge.LOCAL_DEFAULT_RELIABILITY exactly (same constant
value, same reasoning): a peer's self-declared "reliability" is
untrusted input. It is preserved verbatim as
Observation.metadata["claimed_reliability"] for provenance, but the
Observation's actual `reliability` field always resolves to
LOCAL_DEFAULT_RELIABILITY, regardless of what the peer claims. This
module does not invent a second reliability-handling rule.

============================================================
Contradiction detection is read-only analysis, not a verdict
============================================================

analyze_contradiction() is a thin, optional, explicitly-invoked wrapper
around lantern.core.EvidenceKernel.detect_contradiction() (the existing
mechanism -- not reimplemented here). It requires Evidence to already
exist for the concept on both sides of the disagreement, which in turn
requires the caller to have explicitly promoted observations via
add_evidence() first (this module does not do that automatically -- see
EVIDENCE BOUNDARY above). Finding a contradiction never mutates trust,
authority, identity_status, or resolves itself; it is purely descriptive.

============================================================
No architecture-boundary access beyond the agent's own observe()
============================================================

This module imports lantern.agent.LanternAgent (to call the SAME
.observe() every other ingestion path in this codebase already uses --
not a new one) and lantern.protocol (for ProtocolMessage/validate_message
-- the existing wire format). It does not import lantern.router,
lantern.boundary, lantern.bridge, lantern.scars, lantern.federation, or
lantern.core directly, and never calls add_evidence()/belief()/resolve()/
persist_scar() itself.

============================================================
Replay protection
============================================================

protocol.ProtocolMessage.message_id is already a per-message UUID
(protocol.py's create_message() calls uuid.uuid4() for every message).
That is sufficient message identity to deduplicate against -- no new
protocol field is introduced. ObservationExchangeLedger keeps a bounded,
in-memory (never persisted to disk) set of (source, message_id) pairs
already accepted, capped at `max_tracked_messages` entries with FIFO
eviction so memory cannot grow unbounded from a long-running or hostile
peer. This is intentionally NOT a persistence layer: it is scoped to a
single process's lifetime, matching the "smallest bounded deduplication
mechanism necessary" instruction. If a caller needs replay protection
that survives a process restart, that is a distinct, future, explicitly
flagged decision (see KNOWN_LIMITATIONS in the final report) -- not
something silently added here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from .agent import LanternAgent
from .capability_authorization import CapabilityDecision
from . import identity as identity_module
from .protocol import ProtocolMessage, validate_message

__all__ = [
    "EvidenceExchangeCapability",
    "LOCAL_DEFAULT_RELIABILITY",
    "MAX_OBSERVATION_CONTENT_BYTES",
    "MAX_TRACKED_MESSAGES",
    "ObservationExchangeOutcome",
    "ObservationExchangeResult",
    "ObservationExchangeLedger",
    "receive_observation",
    "analyze_contradiction",
]


# The single existing capability name for observation sharing --
# see router.MESSAGE_REQUIREMENTS["OBSERVATION_SHARE"] and
# architecture.CANONICAL_MESSAGE_REQUIREMENTS, both of which already map
# OBSERVATION_SHARE -> "evidence_exchange". Not a new capability name.
EvidenceExchangeCapability = "evidence_exchange"

# Mirrors lantern.bridge.LOCAL_DEFAULT_RELIABILITY exactly. Duplicated
# as a literal constant (not imported) so this module has zero coupling
# to lantern.bridge's internals -- the two modules independently agree
# on the same conservative default because it is the same architectural
# rule (see FROZEN_CONSTANTS["remote_default_reliability"] in
# architecture.py), not a coincidence to be silently drifted apart.
LOCAL_DEFAULT_RELIABILITY = 0.5

# Hard cap on the observation "content" field, enforced BEFORE the
# message reaches agent.observe(). Chosen well under
# NetworkContactTransport's 64 KiB response cap so a full-size transport
# response could never even theoretically smuggle an oversized single
# field through this layer.
MAX_OBSERVATION_CONTENT_BYTES = 8192

# Bounded FIFO replay-dedup window size (see module docstring, "Replay
# protection"). Process-lifetime only; never persisted.
MAX_TRACKED_MESSAGES = 4096


class ObservationExchangeOutcome:
    """String constants for ObservationExchangeResult.outcome."""

    IDENTITY_NOT_VERIFIED = "identity_not_verified"
    NOT_AUTHORIZED = "not_authorized"
    MALFORMED_MESSAGE = "malformed_message"
    WRONG_MESSAGE_TYPE = "wrong_message_type"
    SOURCE_MISMATCH = "source_mismatch"
    INVALID_OBSERVATION_PAYLOAD = "invalid_observation_payload"
    CONTENT_TOO_LARGE = "content_too_large"
    DUPLICATE_MESSAGE = "duplicate_message"
    OBSERVATION_CREATED = "observation_created"

    _ACCEPTED = {OBSERVATION_CREATED}

    @classmethod
    def accepted(cls, outcome: str) -> bool:
        return outcome in cls._ACCEPTED


@dataclass(frozen=True)
class ObservationExchangeResult:
    """Immutable, structured result. Contains no private key material.

    observation_id is populated only on OBSERVATION_CREATED; every
    rejection path leaves it None, with `accepted` False and `reason`
    explaining exactly why, so a rejection is always explicit and never
    silently swallowed.
    """

    outcome: str
    accepted: bool
    reason: str
    source_node_id: Optional[str]
    message_id: Optional[str]
    observation_id: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "outcome": self.outcome,
            "accepted": self.accepted,
            "reason": self.reason,
            "source_node_id": self.source_node_id,
            "message_id": self.message_id,
            "observation_id": self.observation_id,
        }


def _reject(outcome, reason, source_node_id=None, message_id=None) -> ObservationExchangeResult:
    return ObservationExchangeResult(
        outcome=outcome,
        accepted=False,
        reason=reason,
        source_node_id=source_node_id,
        message_id=message_id,
    )


@dataclass
class ObservationExchangeLedger:
    """Bounded, in-memory, per-process replay-dedup tracker.

    Deliberately NOT a persistence layer -- see module docstring
    ("Replay protection"). Keyed on (source_node_id, message_id) so two
    different senders reusing coincidentally equal message_id values
    (which should not happen given uuid4(), but hostile input must not
    be trusted to behave) cannot shadow each other.
    """

    max_tracked_messages: int = MAX_TRACKED_MESSAGES
    _seen: "list[tuple[str, str]]" = field(default_factory=list)
    _seen_set: "set[tuple[str, str]]" = field(default_factory=set)

    def seen(self, source_node_id: str, message_id: str) -> bool:
        return (source_node_id, message_id) in self._seen_set

    def record(self, source_node_id: str, message_id: str) -> None:
        key = (source_node_id, message_id)
        if key in self._seen_set:
            return
        self._seen_set.add(key)
        self._seen.append(key)
        while len(self._seen) > self.max_tracked_messages:
            oldest = self._seen.pop(0)
            self._seen_set.discard(oldest)


def _validate_observation_payload(payload) -> Optional[str]:
    """Returns an error reason string, or None if the payload is well
    formed. Treats every field as hostile: wrong types, missing
    required fields, and oversized content are all rejected here,
    before agent.observe() is ever called.
    """
    if not isinstance(payload, dict):
        return "observation payload is not an object"

    observation = payload.get("observation")
    if not isinstance(observation, dict):
        return "payload.observation is not an object"

    content = observation.get("content")
    if not isinstance(content, str):
        return "observation.content is missing or not a string"

    if len(content.encode("utf-8", errors="replace")) > MAX_OBSERVATION_CONTENT_BYTES:
        return "observation.content exceeds maximum size"

    if "reliability" in observation:
        reliability = observation["reliability"]
        if isinstance(reliability, bool) or not isinstance(reliability, (int, float)):
            return "observation.reliability must be numeric"
        # Bounded sanity check only -- the claimed value is NEVER
        # trusted as local reliability regardless of what it is (see
        # RELIABILITY_MODEL). This just rejects nonsense/impossible
        # values (NaN, inf) rather than letting them reach metadata.
        if reliability != reliability or reliability in (float("inf"), float("-inf")):
            return "observation.reliability is not a finite number"

    if "concept" in observation and not isinstance(observation["concept"], str):
        return "observation.concept must be a string if present"

    return None


def receive_observation(
    message: ProtocolMessage,
    *,
    identity_status: str,
    decision: CapabilityDecision,
    agent: LanternAgent,
    ledger: Optional[ObservationExchangeLedger] = None,
) -> ObservationExchangeResult:
    """Validate, authorize, and (if accepted) admit ONE remote
    OBSERVATION_SHARE ProtocolMessage as a local Observation.

    identity_status: the CALLER's own already-established
        VerifiedContactResult.identity_status for this sender (this
        function does not perform network I/O or re-verify identity --
        it only trusts a value the caller obtained via
        verified_contact.verify_contact()).

    decision: a CapabilityDecision from
        capability_authorization.authorize() for the SAME sender. Must
        have "evidence_exchange" in decision.authorized_capabilities,
        i.e. an operator explicitly authorized it -- shared_capabilities
        alone is never sufficient (see module docstring).

    agent: the receiving LanternAgent whose .observe() will be called on
        acceptance. This module never touches agent.add_evidence(),
        agent.resolve(), or lantern.core directly.

    ledger: optional ObservationExchangeLedger for replay protection. A
        fresh ledger is created per call if omitted, which means replay
        protection is only meaningful when the SAME ledger instance is
        reused by the caller across multiple receive_observation() calls
        for the same peer/session -- this is intentional: this function
        is otherwise a pure gate, and does not maintain hidden global
        state of its own.
    """
    source_node_id = getattr(message, "source", None) if message is not None else None
    message_id = getattr(message, "message_id", None) if message is not None else None

    # ---- Structural validation first: nothing below this point may
    # execute, interpret, or select code/paths based on message content.
    if not isinstance(message, ProtocolMessage) or not validate_message(message):
        return _reject(
            ObservationExchangeOutcome.MALFORMED_MESSAGE,
            "message failed protocol structural validation",
            source_node_id,
            message_id,
        )

    if message.message_type != "OBSERVATION_SHARE":
        return _reject(
            ObservationExchangeOutcome.WRONG_MESSAGE_TYPE,
            f"expected OBSERVATION_SHARE, got {message.message_type!r}",
            source_node_id,
            message_id,
        )

    # ---- Identity check (BEFORE authorization, BEFORE validation of
    # payload contents, BEFORE any mutation).
    if identity_status != identity_module.CRYPTOGRAPHICALLY_VERIFIED:
        return _reject(
            ObservationExchangeOutcome.IDENTITY_NOT_VERIFIED,
            f"identity_status={identity_status!r} is not CRYPTOGRAPHICALLY_VERIFIED",
            source_node_id,
            message_id,
        )

    # ---- Sender identity must match the verified/authorized node_id --
    # a message CLAIMING to be from someone else cannot ride on another
    # node's CapabilityDecision.
    if decision.node_id != message.source:
        return _reject(
            ObservationExchangeOutcome.SOURCE_MISMATCH,
            f"message.source={message.source!r} does not match authorized node_id={decision.node_id!r}",
            source_node_id,
            message_id,
        )

    # ---- Authorization check (explicit CapabilityDecision, not shared
    # capability, not identity verification alone).
    if not decision.is_authorized(EvidenceExchangeCapability):
        return _reject(
            ObservationExchangeOutcome.NOT_AUTHORIZED,
            f"{EvidenceExchangeCapability!r} is not in authorized_capabilities for {decision.node_id!r}",
            source_node_id,
            message_id,
        )

    # ---- Payload validation (hostile input; still zero mutation so far).
    validation_error = _validate_observation_payload(message.payload)
    if validation_error is not None:
        return _reject(
            ObservationExchangeOutcome.INVALID_OBSERVATION_PAYLOAD,
            validation_error,
            source_node_id,
            message_id,
        )

    # ---- Replay protection (still zero Lantern-core mutation).
    ledger = ledger if ledger is not None else ObservationExchangeLedger()
    if ledger.seen(source_node_id, message_id):
        return _reject(
            ObservationExchangeOutcome.DUPLICATE_MESSAGE,
            "message_id already processed for this source; ignoring replay",
            source_node_id,
            message_id,
        )

    # ---- All checks passed: exactly one, narrowly scoped mutation.
    observation_payload = message.payload["observation"]
    claimed_reliability = observation_payload.get("reliability", 1.0)

    observation = agent.observe(
        content=observation_payload["content"],
        source=message.source,
        reliability=LOCAL_DEFAULT_RELIABILITY,
        metadata={
            "claimed_reliability": claimed_reliability,
            "claimed_concept": observation_payload.get("concept", ""),
            "remote_message_id": message_id,
            "remote_timestamp": message.timestamp,
            "origin_type": "authorized_observation_exchange",
        },
    )

    ledger.record(source_node_id, message_id)

    return ObservationExchangeResult(
        outcome=ObservationExchangeOutcome.OBSERVATION_CREATED,
        accepted=True,
        reason="observation accepted into local Lantern state",
        source_node_id=source_node_id,
        message_id=message_id,
        observation_id=observation.id,
    )


def analyze_contradiction(agent: LanternAgent, concept: str):
    """Thin, explicitly-invoked, read-only wrapper around the EXISTING
    lantern.core.EvidenceKernel.detect_contradiction(). Not called
    automatically by receive_observation() -- see module docstring
    ("Contradiction detection is read-only analysis, not a verdict").

    Returns the same Contradiction-or-None that
    agent.lantern.kernel.detect_contradiction(concept) already returns.
    Requires Evidence to already exist for `concept` (on both signs) --
    the caller must have explicitly promoted one or more Observations
    via agent.add_evidence() first; this function itself never calls
    add_evidence(), belief(), or resolve().
    """
    return agent.lantern.kernel.detect_contradiction(concept)
