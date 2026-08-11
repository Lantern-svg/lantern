"""Read-only participant inspection / informational compatibility layer.

Given a JoinRequest already recorded by rendezvous.JoinMonitor, this module
answers: "what protocol/capabilities does this participant CLAIM to speak,
and how does that compare to what this node supports?"

It never contacts a peer, never performs a handshake, never mutates
trust/authority/belief/Codex state, and never treats a claim as verified.
Every ParticipantView carries trust_status="unverified" and
authority_level="none" unconditionally -- compatibility here is
informational only and must never be read as an authorization decision.
The existing handshake (handshake.py) and capability negotiation
(compatibility.negotiate()) remain the only path to an actual verified
exchange; this module does not call either of them.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .compatibility import DEFAULT_CAPABILITIES, compatible_versions
from .protocol import PROTOCOL_VERSION
from .rendezvous import EXPIRED, JoinMonitor, JoinRequest


UNKNOWN = "unknown"
COMPATIBLE = "compatible"
INCOMPATIBLE = "incompatible"
REQUIRES_NEGOTIATION = "requires_negotiation"

COMPATIBILITY_STATES = (UNKNOWN, COMPATIBLE, INCOMPATIBLE, REQUIRES_NEGOTIATION)

TRUST_UNVERIFIED = "unverified"
AUTHORITY_NONE = "none"

# Identity status is a THIRD, independent axis from trust_status and
# authority_level -- see lantern.identity module docstring. A
# CRYPTOGRAPHICALLY_VERIFIED identity_status means a challenge/response
# proof succeeded; it says nothing about trust_status or
# authority_level, which remain unconditionally "unverified"/"none" in
# this module regardless of identity_status. inspect() never performs
# verification itself (that would violate this module's "never contacts
# a peer" invariant) -- a caller that already ran lantern.identity
# verification elsewhere may pass the resulting status in explicitly.
IDENTITY_UNVERIFIED = "UNVERIFIED"
IDENTITY_CRYPTOGRAPHICALLY_VERIFIED = "CRYPTOGRAPHICALLY_VERIFIED"


def _claimed_compatibility(
    claimed_protocol_version: str | None,
    claimed_capabilities: dict[str, bool] | None,
) -> tuple[str, list[str]]:
    """Compare a claim against local support without contacting anyone.

    This mirrors compatibility.compatible_versions()'s major-version rule
    for reporting purposes only -- it does not call negotiate() and does
    not produce a CompatibilityResult that any transport code consumes.
    """
    if not claimed_protocol_version:
        return UNKNOWN, []

    try:
        major_match = compatible_versions(PROTOCOL_VERSION, claimed_protocol_version)
    except (ValueError, AttributeError, IndexError):
        return UNKNOWN, []

    if not major_match:
        return INCOMPATIBLE, []

    shared = sorted(
        name
        for name, enabled in (claimed_capabilities or {}).items()
        if enabled and DEFAULT_CAPABILITIES.get(name)
    )
    if not shared:
        return REQUIRES_NEGOTIATION, shared
    return COMPATIBLE, shared


@dataclass(frozen=True)
class ParticipantView:
    node_id: str
    request_id: str
    protocol_version: str
    capabilities_claimed: dict[str, bool]
    peer_endpoint: str | None
    timestamp: str
    join_status: str
    compatibility_status: str
    trust_status: str
    authority_level: str
    shared_capabilities_if_compatible: list[str]
    identity_status: str = IDENTITY_UNVERIFIED

    def to_dict(self) -> dict[str, Any]:
        return {
            "node_id": self.node_id,
            "request_id": self.request_id,
            "protocol_version": self.protocol_version,
            "capabilities_claimed": dict(self.capabilities_claimed),
            "peer_endpoint": self.peer_endpoint,
            "timestamp": self.timestamp,
            "join_status": self.join_status,
            "compatibility_status": self.compatibility_status,
            "trust_status": self.trust_status,
            "authority_level": self.authority_level,
            "shared_capabilities_if_compatible": list(self.shared_capabilities_if_compatible),
            "identity_status": self.identity_status,
        }


def inspect(request: JoinRequest, identity_status: str = IDENTITY_UNVERIFIED) -> ParticipantView:
    """Build a read-only view of one JoinRequest. Never contacts the peer.

    identity_status defaults to IDENTITY_UNVERIFIED and is never computed
    here -- if a caller already has a lantern.identity.VerificationResult
    for this participant from a real challenge/response exchange, it may
    pass identity_status=result.identity_status explicitly. This keeps
    verification itself entirely outside this read-only module.
    """
    compatibility_status, shared = _claimed_compatibility(
        request.protocol_version, request.capabilities
    )
    return ParticipantView(
        node_id=request.node_id,
        request_id=request.request_id,
        protocol_version=request.protocol_version,
        capabilities_claimed=dict(request.capabilities),
        peer_endpoint=request.peer_endpoint,
        timestamp=request.timestamp,
        join_status=request.status,
        compatibility_status=compatibility_status,
        trust_status=TRUST_UNVERIFIED,
        authority_level=AUTHORITY_NONE,
        shared_capabilities_if_compatible=shared,
        identity_status=identity_status,
    )


def inspect_all(monitor: JoinMonitor, include_expired: bool = True) -> list[ParticipantView]:
    requests = monitor.all_requests() if include_expired else monitor.pending()
    return [inspect(request) for request in requests]


def find(monitor: JoinMonitor, request_id: str) -> ParticipantView | None:
    for request in monitor.all_requests():
        if request.request_id == request_id:
            return inspect(request)
    return None


def next_verification_step(view: ParticipantView) -> str:
    """Describe the recommended next step for a human operator.

    This is advice text only. It never triggers a connection, handshake,
    or any other outbound action -- the operator decides whether and how
    to act on it using the existing bootstrap_client/handshake tooling.
    """
    if view.join_status == EXPIRED:
        return "Request expired before verification. Ask the participant to submit a new /join request."

    if view.compatibility_status == INCOMPATIBLE:
        return (
            "Claimed protocol_version has a different major version than this node. "
            "No safe verification step available; a handshake would be rejected."
        )

    if view.compatibility_status == UNKNOWN:
        return "protocol_version is missing or unparseable. Ask the participant to resubmit a valid /join request."

    if view.compatibility_status == REQUIRES_NEGOTIATION:
        return (
            "Claimed capabilities do not overlap with anything this node supports. "
            "An operator may manually run the existing handshake flow against the "
            "participant's declared peer_endpoint to confirm; nothing will contact "
            "it automatically."
        )

    if view.peer_endpoint:
        return (
            f"Claimed protocol/capabilities look compatible. An operator may manually run "
            f"the existing handshake flow (e.g. python -m lantern.bootstrap_client) against "
            f"{view.peer_endpoint} to verify the claim; nothing will contact it automatically."
        )

    return (
        "Claimed protocol/capabilities look compatible, but no peer_endpoint was provided. "
        "An operator needs a reachable address out-of-band before any verification handshake "
        "can be attempted."
    )
