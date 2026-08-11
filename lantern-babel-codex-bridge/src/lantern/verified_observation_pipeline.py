"""End-to-end verified observation path orchestrator (Phase: Discord ->
verified observation exchange).

This module composes existing, already-tested Lantern primitives into one
explicit state-machine pipeline. It contains no cryptography, no HTTP
implementation, no Discord parsing, no capability policy logic, and no
Lantern core logic of its own -- every one of those already exists
elsewhere in this package and is called here, unmodified:

    discord_rendezvous.normalize_discord_announcement()   (untrusted claim)
      -> rendezvous.JoinMonitor.submit()                  (audit record only)
      -> network_contact_policy.NetworkContactPolicy.evaluate()
      -> network_contact_transport.NetworkContactTransport.contact()
      -> verified_contact.verify_contact()                (crypto identity)
      -> capability_authorization.authorize()              (explicit grant)
      -> observation_exchange.receive_observation()        (one Observation)

============================================================
What this module is not
============================================================

It is not a second Lantern. It is not a second identity system, a second
capability system, a second observation-ingestion system, or a second
policy engine. Every security-relevant decision (endpoint safety,
cryptographic identity, capability authorization, observation admission)
is delegated entirely to the existing module that already owns that
decision. This module's only job is SEQUENCING: run stage N, and only if
it succeeds, run stage N+1 -- otherwise stop and report exactly where and
why.

============================================================
Explicit state progression
============================================================

    ANNOUNCED
      -> CONTACT_POLICY_ALLOWED  -> (else CONTACT_POLICY_DENIED, stop)
      -> CONTACTED                -> (else CONTACT_FAILED, stop)
      -> IDENTITY_VERIFIED        -> (else IDENTITY_FAILED, stop)
      -> CAPABILITY_AUTHORIZED    -> (else AUTHORIZATION_DENIED, stop)
      -> OBSERVATION_ACCEPTED     -> (else OBSERVATION_REJECTED /
                                        REPLAY_REJECTED, stop)

A malformed/hostile Discord announcement never reaches ANNOUNCED at all --
see `run_pipeline()`'s first step, which stops at normalization with
DISCORD_INVALID and touches nothing else (no JoinMonitor, no network, no
Lantern state).

Every stage transition is captured in `PipelineResult.stage_history` (a
list of stage-name strings in the order they were actually reached) so a
caller/test can assert the exact path taken, not just the final outcome.
A failure at any stage returns immediately; the pipeline never silently
advances past a failed stage.

============================================================
Discord remains signaling only
============================================================

A Discord announcement, once normalized, is fed to the EXISTING
`rendezvous.JoinMonitor` purely as an audit record (via
`discord_rendezvous.submit_discord_announcement()`, unmodified). This
module never treats a Discord claim -- node_id, public_key, capabilities,
or endpoint -- as verified. The claimed public key is not even used by
this pipeline: `verified_contact.verify_contact()` performs its own
independent challenge/response against the actual contacted endpoint
using the EXISTING `lantern.identity` mechanism, and the resulting
`identity_status` is what every later stage relies on -- never the
Discord-claimed key. If the endpoint answering the challenge does not
control the private key for `verified.remote_node_id`, identity
verification fails structurally (this is exactly what the "Discord
impersonation" test below exercises), independent of anything the
Discord announcement claimed.

============================================================
One observation, no synchronization loop
============================================================

`run_pipeline()` performs at most one observation exchange per call and
never loops, retries, polls, or schedules further contact. Calling it
twice with the same underlying `ProtocolMessage` (same `message_id`) is
exactly how replay protection is exercised -- see `REPLAY_REJECTED`.

============================================================
No new authority
============================================================

This module never calls `add_evidence()`, `belief()`, `resolve()`,
`persist_scar()`, or `create_scar()`, never imports `lantern.core`
directly, and never touches `trust_status`/`authority_level`. Those
boundaries are enforced by `observation_exchange.py` (already tested
there) and are not re-implemented or bypassed here. An AST-based
architecture test below confirms this module contains no such calls,
guarding against future accidental authority escalation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from . import identity as identity_module
from .capability_authorization import AuthorizationPolicy, CapabilityDecision, authorize
from .discord_rendezvous import DiscordRendezvousResult, submit_discord_announcement
from .network_contact_policy import ContactDecision, ContactVerdict, NetworkContactPolicy
from .network_contact_transport import ContactOutcome, ContactResult, NetworkContactTransport
from .observation_exchange import (
    ObservationExchangeLedger,
    ObservationExchangeOutcome,
    ObservationExchangeResult,
    receive_observation,
)
from .protocol import ProtocolMessage, create_observation_share
from .verified_contact import VerifiedContactOutcome, VerifiedContactResult, verify_contact

__all__ = [
    "PipelineStage",
    "PipelineResult",
    "run_pipeline",
]


class PipelineStage:
    """String constants for PipelineResult.stage / stage_history entries.

    Mirrors the state diagram in the module docstring exactly -- these
    are the only stage names this module ever produces.
    """

    ANNOUNCED = "ANNOUNCED"
    DISCORD_INVALID = "DISCORD_INVALID"
    CONTACT_POLICY_ALLOWED = "CONTACT_POLICY_ALLOWED"
    CONTACT_POLICY_DENIED = "CONTACT_POLICY_DENIED"
    CONTACTED = "CONTACTED"
    CONTACT_FAILED = "CONTACT_FAILED"
    IDENTITY_VERIFIED = "IDENTITY_VERIFIED"
    IDENTITY_FAILED = "IDENTITY_FAILED"
    CAPABILITY_AUTHORIZED = "CAPABILITY_AUTHORIZED"
    AUTHORIZATION_DENIED = "AUTHORIZATION_DENIED"
    OBSERVATION_ACCEPTED = "OBSERVATION_ACCEPTED"
    OBSERVATION_REJECTED = "OBSERVATION_REJECTED"
    REPLAY_REJECTED = "REPLAY_REJECTED"

    _TERMINAL_FAILURES = frozenset({
        DISCORD_INVALID,
        CONTACT_POLICY_DENIED,
        CONTACT_FAILED,
        IDENTITY_FAILED,
        AUTHORIZATION_DENIED,
        OBSERVATION_REJECTED,
        REPLAY_REJECTED,
    })

    @classmethod
    def is_failure(cls, stage: str) -> bool:
        return stage in cls._TERMINAL_FAILURES


@dataclass(frozen=True)
class PipelineResult:
    """Immutable, structured result of one run_pipeline() call.

    `stage` is the FINAL stage reached (success or failure).
    `stage_history` lists every stage actually transitioned through, in
    order, so a test/caller can assert the exact path, not just the
    endpoint. `succeeded` is True only when `stage ==
    PipelineStage.OBSERVATION_ACCEPTED`.

    Intermediate artifacts (`normalized_announcement`, `join_result`,
    `contact_verdict`, `contact_result`, `verified_contact`,
    `capability_decision`, `observation_result`) are populated only up to
    the stage actually reached; anything not reached is None. None of
    these fields ever carries private key material (checked by tests
    mirroring the same check already applied to observation_exchange
    results).
    """

    stage: str
    stage_history: tuple
    succeeded: bool
    reason: str
    node_id: Optional[str] = None
    normalized_announcement: Optional[Any] = None
    join_result: Optional[DiscordRendezvousResult] = None
    contact_verdict: Optional[ContactVerdict] = None
    contact_result: Optional[ContactResult] = None
    verified_contact: Optional[VerifiedContactResult] = None
    capability_decision: Optional[CapabilityDecision] = None
    observation_result: Optional[ObservationExchangeResult] = None

    def to_dict(self) -> dict:
        return {
            "stage": self.stage,
            "stage_history": list(self.stage_history),
            "succeeded": self.succeeded,
            "reason": self.reason,
            "node_id": self.node_id,
        }


def _stop(stage: str, reason: str, history: list, **fields) -> PipelineResult:
    history = history + [stage]
    return PipelineResult(
        stage=stage,
        stage_history=tuple(history),
        succeeded=(stage == PipelineStage.OBSERVATION_ACCEPTED),
        reason=reason,
        **fields,
    )


def run_pipeline(
    raw_discord_payload: Any,
    *,
    join_monitor: Any,
    local_node_id: str,
    local_identity: identity_module.NodeIdentity,
    contact_policy: Optional[NetworkContactPolicy] = None,
    transport: Optional[NetworkContactTransport] = None,
    authorization_policy: Optional[object] = None,
    requested_capabilities: Optional[set] = None,
    receiving_agent: Any = None,
    observation_content: str = "",
    observation_reliability: float = 1.0,
    observation_concept: Optional[str] = None,
    ledger: Optional[ObservationExchangeLedger] = None,
    observation_message: Optional[ProtocolMessage] = None,
) -> PipelineResult:
    """Run the complete Discord-announcement -> verified-observation
    pipeline exactly once. Never retries, never loops, never schedules
    further contact.

    Parameters mirror each existing stage's own required inputs one to
    one -- see module docstring for the full chain. `receiving_agent` is
    the local `LanternAgent` (or duck-typed equivalent exposing
    `.observe()`) that will receive the resulting Observation; if
    omitted, the pipeline stops after CAPABILITY_AUTHORIZED without
    attempting an observation exchange (useful for callers who only want
    to prove contact + identity + authorization).

    `observation_message`, if supplied, is used as-is for the
    observation-exchange stage (useful for replay tests: pass the exact
    same ProtocolMessage twice). If omitted, one is built via
    `protocol.create_observation_share()` from
    `observation_content`/`observation_reliability`/`observation_concept`,
    sourced from the VERIFIED remote_node_id (never the Discord-claimed
    node_id, though in the non-impersonation path these are the same
    value by construction).
    """
    history: list = []
    contact_policy = contact_policy or NetworkContactPolicy()
    transport = transport or NetworkContactTransport(policy=contact_policy)

    # ---- Stage: normalize + submit Discord announcement (audit only) ----
    join_result = submit_discord_announcement(raw_discord_payload, join_monitor)
    normalized = join_result.normalized

    if not normalized.valid:
        return _stop(
            PipelineStage.DISCORD_INVALID,
            f"Discord announcement failed normalization: {normalized.rejection_reason}",
            history,
            normalized_announcement=normalized,
            join_result=join_result,
        )

    history.append(PipelineStage.ANNOUNCED)
    claimed_node_id = normalized.node_id
    claimed_endpoint = normalized.claimed_endpoint

    # ---- Stage: contact policy -------------------------------------
    verdict = contact_policy.evaluate(claimed_endpoint)
    if verdict.decision is not ContactDecision.ALLOWED:
        return _stop(
            PipelineStage.CONTACT_POLICY_DENIED,
            f"endpoint denied by NetworkContactPolicy: {verdict.reason}",
            history,
            node_id=claimed_node_id,
            normalized_announcement=normalized,
            join_result=join_result,
            contact_verdict=verdict,
        )

    history.append(PipelineStage.CONTACT_POLICY_ALLOWED)

    # ---- Stage: bounded network contact -----------------------------
    contact_result = transport.contact(claimed_endpoint, verdict=verdict)
    if not contact_result.succeeded:
        return _stop(
            PipelineStage.CONTACT_FAILED,
            f"transport contact did not succeed: {contact_result.outcome}",
            history,
            node_id=claimed_node_id,
            normalized_announcement=normalized,
            join_result=join_result,
            contact_verdict=verdict,
            contact_result=contact_result,
        )

    history.append(PipelineStage.CONTACTED)

    # ---- Stage: cryptographic identity verification -------------------
    verified = verify_contact(
        contact_result,
        transport=transport,
        verdict=verdict,
        local_node_id=local_node_id,
        local_identity=local_identity,
    )
    if verified.identity_status != identity_module.CRYPTOGRAPHICALLY_VERIFIED:
        return _stop(
            PipelineStage.IDENTITY_FAILED,
            f"identity verification did not succeed: {verified.outcome} ({verified.reason})",
            history,
            node_id=claimed_node_id,
            normalized_announcement=normalized,
            join_result=join_result,
            contact_verdict=verdict,
            contact_result=contact_result,
            verified_contact=verified,
        )

    history.append(PipelineStage.IDENTITY_VERIFIED)

    # Discord's claimed node_id is NEVER trusted for anything from this
    # point on -- the verified remote_node_id (proven by the challenge
    # response, not by anything Discord said) is authoritative. If they
    # differ, this is exactly the impersonation case, and no capability
    # can be authorized for a node_id nobody actually proved control of.
    if verified.remote_node_id != claimed_node_id:
        return _stop(
            PipelineStage.IDENTITY_FAILED,
            (
                f"verified identity ({verified.remote_node_id!r}) does not match "
                f"the Discord-claimed node_id ({claimed_node_id!r}); refusing to "
                "proceed as a possible impersonation"
            ),
            history,
            node_id=claimed_node_id,
            normalized_announcement=normalized,
            join_result=join_result,
            contact_verdict=verdict,
            contact_result=contact_result,
            verified_contact=verified,
        )

    # ---- Stage: explicit capability authorization ----------------------
    requested = requested_capabilities if requested_capabilities is not None else {"evidence_exchange"}
    decision = authorize(verified, requested=requested, policy=authorization_policy)
    if not decision.is_authorized("evidence_exchange"):
        return _stop(
            PipelineStage.AUTHORIZATION_DENIED,
            f"evidence_exchange not authorized for {verified.remote_node_id!r}: {decision.denied_capabilities}",
            history,
            node_id=verified.remote_node_id,
            normalized_announcement=normalized,
            join_result=join_result,
            contact_verdict=verdict,
            contact_result=contact_result,
            verified_contact=verified,
            capability_decision=decision,
        )

    history.append(PipelineStage.CAPABILITY_AUTHORIZED)

    if receiving_agent is None:
        # Caller only wanted to prove contact + identity + authorization;
        # no observation exchange requested this call.
        return PipelineResult(
            stage=PipelineStage.CAPABILITY_AUTHORIZED,
            stage_history=tuple(history),
            succeeded=False,
            reason="capability authorized; no receiving_agent supplied, observation exchange skipped",
            node_id=verified.remote_node_id,
            normalized_announcement=normalized,
            join_result=join_result,
            contact_verdict=verdict,
            contact_result=contact_result,
            verified_contact=verified,
            capability_decision=decision,
        )

    # ---- Stage: authorized observation exchange -----------------------
    message = observation_message
    if message is None:
        observation_payload: dict[str, Any] = {"content": observation_content, "reliability": observation_reliability}
        if observation_concept is not None:
            observation_payload["concept"] = observation_concept
        message = create_observation_share(verified.remote_node_id, observation_payload)

    obs_result = receive_observation(
        message,
        identity_status=verified.identity_status,
        decision=decision,
        agent=receiving_agent,
        ledger=ledger,
    )

    if obs_result.outcome == ObservationExchangeOutcome.DUPLICATE_MESSAGE:
        final_stage = PipelineStage.REPLAY_REJECTED
    elif not obs_result.accepted:
        final_stage = PipelineStage.OBSERVATION_REJECTED
    else:
        final_stage = PipelineStage.OBSERVATION_ACCEPTED

    return _stop(
        final_stage,
        obs_result.reason,
        history,
        node_id=verified.remote_node_id,
        normalized_announcement=normalized,
        join_result=join_result,
        contact_verdict=verdict,
        contact_result=contact_result,
        verified_contact=verified,
        capability_decision=decision,
        observation_result=obs_result,
    )
