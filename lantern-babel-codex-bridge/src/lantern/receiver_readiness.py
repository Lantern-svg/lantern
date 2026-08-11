"""Receiver readiness: the exact, already-existing sequence Lantern runs
when a real JOIN_REQUESTED appears, from discovery through to a
VerifiedContactResult / CapabilityDecision -- with nothing invented.

    JOIN_REQUESTED
        -> COMPATIBILITY   (lantern.participants.inspect, informational only)
        -> IDENTITY         (lantern.verified_contact.verify_contact,
                              itself built on lantern.handshake + lantern.identity)
        -> AUTHORIZATION    (lantern.capability_authorization.authorize)
        -> BOUNDED HANDSHAKE (the two fixed POST requests inside
                              verify_contact() -- REQUEST_BUDGET=2, no more)
        -> VERIFIED PEER    (VerifiedContactResult.verified is True)

This module introduces NO new peer system, NO new trust mechanism, and
NO automatic authorization. It is a single ordered call sequence over
functions that already exist elsewhere in this package, plus one
dataclass (`ReceiverEvaluation`) that bundles their outputs so a caller
(a human operator, or later an automated evaluator) can inspect exactly
what happened at each stage without re-deriving it.

Hard boundaries preserved, unchanged from the modules this wraps:

    - `participants.inspect()` never contacts the peer. Compatibility
      here is purely a claim comparison.
    - `verified_contact.verify_contact()` performs AT MOST 2 network
      requests (REQUEST_BUDGET) against the SAME endpoint the caller
      pins -- never re-derived from response data, never retried.
    - `capability_authorization.authorize()` returns an EMPTY
      authorized_capabilities set unless the caller supplies an
      explicit `AuthorizationPolicy` -- i.e. an operator must decide,
      by name, which capabilities to grant. This module's default
      (`policy=None`) authorizes NOTHING, exactly like `authorize()`
      itself. This function does not choose a policy on the operator's
      behalf.
    - Nothing here writes a Chronicle event, a Scar, or a Codex
      mutation. If a caller wants to record the resulting
      `ContactAttempt` into a `ContactLedger`, or the resulting Compass
      reading, that remains the caller's own explicit, separate step
      (see `to_contact_attempt()` and `orient_from_evaluation()` below,
      both of which return NEW values rather than mutating anything).

Distinguishing "path exists" from "peer verified", explicitly:

    JOIN_REQUESTED alone            -> a claim was recorded, nothing more
    COMPATIBILITY == COMPATIBLE     -> the claim is self-consistent with
                                        this node's own protocol version;
                                        still just a claim
    contact_result.succeeded        -> the endpoint answered an HTTP GET;
                                        still not identity, not a peer
    VerifiedContactResult.verified  -> the endpoint proved control of the
                                        cryptographic key it claims; NOT
                                        trust, NOT authority
    CapabilityDecision.authorized   -> an operator's policy explicitly
                                        granted specific capabilities to
                                        this now-identity-verified node

This module never collapses any of those into any other.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from . import identity as identity_module
from .capability_authorization import CapabilityDecision, authorize
from .compass import CompassReading, orient
from .contact_ledger import ContactAttempt, ContactEvidence
from .network_contact_policy import ContactDecision, NetworkContactPolicy
from .network_contact_transport import ContactResult, NetworkContactTransport
from .orchestration import CapabilityRegistry
from .participants import ParticipantView, inspect, next_verification_step
from .rendezvous import JoinRequest
from .verified_contact import VerifiedContactResult, verify_contact


__all__ = [
    "ReceiverEvaluation",
    "evaluate_join_request",
    "to_contact_attempt",
    "orient_from_evaluation",
]


@dataclass(frozen=True)
class ReceiverEvaluation:
    """Bundles the output of every existing stage, in order, for one
    JoinRequest. Every field is the actual return value of an existing
    function -- nothing is synthesized or upgraded between stages.

    `verified_contact` and `capability_decision` are None whenever the
    evaluation legitimately never reached that stage (e.g. compatibility
    already failed, or no `peer_endpoint` was ever supplied) -- absence
    here means "not attempted", never "attempted and failed silently".
    """

    join_request: JoinRequest
    participant_view: ParticipantView
    next_step_advice: str
    contacted: bool
    verified_contact: Optional[VerifiedContactResult] = None
    capability_decision: Optional[CapabilityDecision] = None

    @property
    def is_verified_peer(self) -> bool:
        return self.verified_contact is not None and self.verified_contact.verified

    def to_dict(self) -> dict[str, Any]:
        return {
            "join_request": self.join_request.to_dict(),
            "participant_view": self.participant_view.to_dict(),
            "next_step_advice": self.next_step_advice,
            "contacted": self.contacted,
            "verified_contact": (
                self.verified_contact.to_dict() if self.verified_contact is not None else None
            ),
            "capability_decision": (
                self.capability_decision.to_dict() if self.capability_decision is not None else None
            ),
            "is_verified_peer": self.is_verified_peer,
        }


def evaluate_join_request(
    request: JoinRequest,
    *,
    local_node_id: str,
    local_identity: identity_module.NodeIdentity,
    attempt_contact: bool = False,
    policy: NetworkContactPolicy | None = None,
    transport: NetworkContactTransport | None = None,
    authorization_policy: object | None = None,
    requested_capabilities: Optional[list] = None,
) -> ReceiverEvaluation:
    """Run the existing JOIN_REQUESTED -> COMPATIBILITY -> IDENTITY ->
    AUTHORIZATION -> BOUNDED HANDSHAKE -> VERIFIED PEER sequence for one
    already-recorded JoinRequest.

    `attempt_contact` defaults to False: by default this function ONLY
    performs the read-only COMPATIBILITY stage (`participants.inspect`)
    plus advisory next-step text (`next_verification_step`) -- exactly
    what `joins_cli.py` already does today. It contacts nobody unless the
    caller explicitly opts in with `attempt_contact=True` AND the
    JoinRequest actually carries a `peer_endpoint`. This mirrors
    `participants.next_verification_step()`'s own guidance: "An operator
    may manually run the existing handshake flow ... nothing will contact
    it automatically."

    When `attempt_contact=True` and a `peer_endpoint` is present, this
    function:
        1. Evaluates the endpoint through `NetworkContactPolicy`
           (SSRF-safe, zero-I/O gate).
        2. If ALLOWED, issues exactly one bounded GET via
           `NetworkContactTransport` -- the ONLY new network operation
           this function performs itself, and only after the policy
           gate passed.
        3. Feeds that `ContactResult` into `verify_contact()`, which
           performs its own fixed, bounded 2-request handshake +
           identity-proof exchange against the SAME pinned endpoint.
        4. Feeds the resulting `VerifiedContactResult` into
           `capability_authorization.authorize()`. With no
           `authorization_policy` supplied, this authorizes NOTHING
           (the existing conservative default) -- an operator must
           pass an explicit policy naming exactly which capabilities to
           grant this specific, now-identity-verified node.

    If policy denies the endpoint, or the GET fails, or the handshake/
    identity exchange fails at any stage, this function returns a
    `ReceiverEvaluation` with `verified_contact.verified is False` (or
    `contacted=False` if it never got that far) rather than raising --
    a failed/refused stage is itself a valid, reportable result, never
    silently treated as success.
    """
    participant_view = inspect(request)
    advice = next_verification_step(participant_view)

    if not attempt_contact or not request.peer_endpoint:
        return ReceiverEvaluation(
            join_request=request,
            participant_view=participant_view,
            next_step_advice=advice,
            contacted=False,
        )

    active_policy = policy if policy is not None else NetworkContactPolicy()
    active_transport = (
        transport if transport is not None else NetworkContactTransport(policy=active_policy)
    )

    verdict = active_policy.evaluate(request.peer_endpoint)
    if verdict.decision is not ContactDecision.ALLOWED:
        # Policy-denied endpoints are never contacted -- zero socket/DNS
        # activity happens below this branch, enforced by returning here.
        return ReceiverEvaluation(
            join_request=request,
            participant_view=participant_view,
            next_step_advice=advice,
            contacted=False,
        )

    contact_result: ContactResult = active_transport.contact(request.peer_endpoint, verdict=verdict)

    verified = verify_contact(
        contact_result,
        transport=active_transport,
        verdict=verdict,
        local_node_id=local_node_id,
        local_identity=local_identity,
    )

    decision = authorize(
        verified,
        requested=requested_capabilities,
        policy=authorization_policy,
    )

    return ReceiverEvaluation(
        join_request=request,
        participant_view=participant_view,
        next_step_advice=advice,
        contacted=True,
        verified_contact=verified,
        capability_decision=decision,
    )


def to_contact_attempt(evaluation: ReceiverEvaluation) -> ContactAttempt:
    """Translate a ReceiverEvaluation into the existing contact_ledger
    vocabulary, as a NEW ContactAttempt (never mutates anything). The
    caller decides whether/how to record it into a ContactLedger --
    this function only performs the translation, honestly, stage by
    stage, using contact_ledger's own EVIDENCE_BACKED_STATES semantics
    rather than inventing a parallel state model.
    """
    destination = evaluation.join_request.peer_endpoint or evaluation.join_request.node_id

    if not evaluation.contacted:
        return ContactAttempt(
            destination=destination,
            state="CONTACT_PATH_FOUND",
            contact_type="UNKNOWN",
            evidence=ContactEvidence(
                peer_identity_claim=evaluation.join_request.node_id,
            ),
            notes=(
                "JOIN_REQUESTED recorded; compatibility/next-step advice "
                "computed; no contact attempted yet"
            ),
        )

    verified = evaluation.verified_contact
    if verified is None or not verified.verified:
        reason = verified.reason if verified is not None else "contact stage did not run"
        return ContactAttempt(
            destination=destination,
            state="CONTACT_FAILED",
            contact_type="UNKNOWN",
            evidence=ContactEvidence(
                peer_identity_claim=evaluation.join_request.node_id,
                failure_reason=reason,
            ),
            notes="contact and/or identity verification did not succeed",
        )

    return ContactAttempt(
        destination=destination,
        state="IDENTITY_VERIFIED",
        contact_type="REAL_INDEPENDENT_PEER",
        evidence=ContactEvidence(
            peer_identity_claim=verified.remote_node_id,
            response_status="handshake+identity proof succeeded",
            acknowledgment_evidence=verified.reason,
        ),
        notes=(
            "cryptographic identity verified via verify_contact(); "
            "trust and authority remain separate, unaffected decisions "
            "(see capability_decision for the explicit, still-conservative "
            "authorization outcome)"
        ),
    )


def orient_from_evaluation(
    evaluation: ReceiverEvaluation,
    *,
    registry: Optional[CapabilityRegistry] = None,
) -> CompassReading:
    """Read-only Compass orientation over one ReceiverEvaluation's result.

    This is the existing `compass.orient()` function -- not a new
    reasoning layer -- fed the `CapabilityDecision` (if any) and the
    translated `ContactAttempt` so Compass can answer WHAT matters / WHY
    / WHAT is allowed / WHAT is next using its own existing rules
    (structural NEVER_EXTERNALLY_EXPOSE floor, `.is_authorized()` on a
    real decision, open-contact severity ranking). Compass performs no
    I/O and mutates nothing; calling this twice with the same evaluation
    returns equal, independent CompassReading values.
    """
    attempt = to_contact_attempt(evaluation)
    return orient(
        registry=registry,
        capability_decision=evaluation.capability_decision,
        open_contacts=(attempt,),
    )
