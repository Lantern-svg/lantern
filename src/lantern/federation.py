"""
Lantern Federation Layer v0.86

Remote Lantern communication.

Rule:
A Lantern may share meaning.
A Lantern may not donate certainty.

Remote claims become Observations, with structured provenance
preserved in Observation.metadata. Remote confidence is metadata
only -- it never becomes local confidence (never reaches
add_evidence() or belief()).
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import uuid4


@dataclass
class FederationMetadata:

    origin_type: str = "remote_lantern"
    remote_instance: str = ""
    claimed_concept: str = ""
    claimed_confidence: float = 0.0
    received_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


@dataclass
class RemoteObservation:

    id: str
    source: str
    concept: str
    content: str
    metadata: FederationMetadata


@dataclass
class FederationResult:

    accepted: bool
    observation_id: str
    reason: str


class FederationAdapter:

    def __init__(self, agent):
        self.agent = agent

    def receive_observation(self, message):
        payload = message.payload["observation"]

        metadata = FederationMetadata(
            remote_instance=message.source,
            claimed_concept=payload.get("concept", ""),
            claimed_confidence=payload.get("confidence", 0.0),
        )

        remote = RemoteObservation(
            id=str(uuid4()),
            source=message.source,
            concept=metadata.claimed_concept,
            content=payload.get("content", ""),
            metadata=metadata,
        )

        # Remote claims enter as observations. They do not alter
        # belief: remote_confidence is stored as metadata only and is
        # never passed to add_evidence()/belief().
        observation = self.agent.observe(
            content=remote.content,
            source="remote:" + remote.source,
            reliability=0.5,
            metadata={
                "origin_type": metadata.origin_type,
                "remote_instance": metadata.remote_instance,
                "claimed_concept": metadata.claimed_concept,
                "claimed_confidence": metadata.claimed_confidence,
            },
        )

        return FederationResult(
            True,
            observation.id,
            "Remote observation preserved with provenance",
        )
