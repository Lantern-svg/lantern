"""
Lantern Agent Bridge v0.84

Connects:
External messages
 |
 v
LanternBoundary
 |
 v
LanternAgent
 |
 v
Lantern Core

The bridge does not modify kernel logic.
It only controls verified entry and exit.

Wiring note:
    The bridge registers its own handlers with the internal
    LanternBoundary for every message type it knows how to turn
    into a LanternAgent action (OBSERVATION_SHARE, EVIDENCE_REQUEST).
    Without registration, LanternRouter rejects every message with
    "No handler registered" before _process() is ever reached.

    CODEX_UPDATE is deliberately NOT wired to agent.add_evidence()
    yet: allowing a remote peer to directly move local belief state
    is a trust-model decision that hasn't been made. Until decided,
    CODEX_UPDATE falls through to the UNHANDLED result below.

Remote reliability (v0.93 revision):
    A peer's self-declared "reliability" on an OBSERVATION_SHARE is a
    REMOTE CLAIM, not an independently established property. It must
    never become Observation.reliability directly, because
    EvidenceKernel.add_evidence() later multiplies weight by
    obs.reliability unmediated -- letting the remote number through
    as-is would let a peer scale its own epistemic influence simply
    by declaring a higher value.

    LOCAL_DEFAULT_RELIABILITY below matches the conservative default
    lantern.federation.FederationAdapter already uses for the same
    reason. The remote claim is preserved, unaltered, as
    Observation.metadata["claimed_reliability"] -- so provenance is
    never discarded -- but it never substitutes for a local
    evaluation of trust.
"""

from dataclasses import dataclass

from .boundary import LanternBoundary
from .agent import LanternAgent


# A self-declared remote reliability is a claim, not a verified fact.
# See module docstring ("Remote reliability") above.
LOCAL_DEFAULT_RELIABILITY = 0.5


@dataclass
class BridgeResult:
    accepted: bool
    action: str
    reason: str
    data: dict


class LanternAgentBridge:

    def __init__(self, agent: LanternAgent):
        self.agent = agent
        self.boundary = LanternBoundary()

        self.boundary.register("OBSERVATION_SHARE", self._on_observation_share)
        self.boundary.register("EVIDENCE_REQUEST", self._on_evidence_request)

    def connect(self, remote_version, capabilities):
        return self.boundary.connect(remote_version, capabilities)

    def receive(self, message, compatibility):
        self._last_result = None

        result = self.boundary.receive(message, compatibility)

        if not result.accepted:
            return BridgeResult(False, "REJECTED", result.reason, {})

        if self._last_result is None:
            return BridgeResult(
                False,
                "UNHANDLED",
                "Message type has no action",
                {},
            )

        return self._last_result

    # ==================================================
    # Handlers (registered with LanternBoundary above)
    # ==================================================

    def _on_observation_share(self, message):
        observation = message.payload["observation"]

        # The remote value is recorded as a claim (metadata), never as
        # the trusted Observation.reliability -- see LOCAL_DEFAULT_RELIABILITY
        # above. Default of 1.0 here only describes what an omitted field
        # implicitly claims; it does not raise local trust.
        claimed_reliability = observation.get("reliability", 1.0)

        result = self.agent.observe(
            content=observation["content"],
            source=message.source,
            reliability=LOCAL_DEFAULT_RELIABILITY,
            metadata={"claimed_reliability": claimed_reliability},
        )

        self._last_result = BridgeResult(
            True,
            "OBSERVATION_CREATED",
            "Accepted into Lantern",
            {"observation": result},
        )

    def _on_evidence_request(self, message):
        belief = self.agent.ask_belief(message.payload["concept"])

        self._last_result = BridgeResult(
            True,
            "BELIEF_RETURNED",
            "Query answered",
            {"belief": belief},
        )
