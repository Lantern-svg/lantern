"""
Lantern Protocol v0.82 (lantern.protocol)

External communication contract.

Purpose:
- Define stable messages between Lantern instances
- Keep transport separate from reasoning
- Preserve the frozen core boundary

Protocol does not:
- modify beliefs
- resolve contradictions
- replace EvidenceKernel

It only defines exchange format.
"""

from dataclasses import dataclass, asdict
from datetime import datetime, timezone
import json
import uuid


PROTOCOL_VERSION = "0.82"


# ==================================================
# Base Message
# ==================================================

@dataclass
class ProtocolMessage:

    message_id: str
    protocol: str
    message_type: str
    source: str
    timestamp: str
    payload: dict

    def encode(self):
        return json.dumps(asdict(self), sort_keys=True)

    @staticmethod
    def decode(data):
        obj = json.loads(data)

        return ProtocolMessage(
            message_id=obj["message_id"],
            protocol=obj["protocol"],
            message_type=obj["message_type"],
            source=obj["source"],
            timestamp=obj["timestamp"],
            payload=obj["payload"],
        )


# ==================================================
# Message Factory
# ==================================================

def create_message(message_type, source, payload):
    return ProtocolMessage(
        message_id=str(uuid.uuid4()),
        protocol=PROTOCOL_VERSION,
        message_type=message_type,
        source=source,
        timestamp=datetime.now(timezone.utc).isoformat(),
        payload=payload,
    )


# ==================================================
# Lantern Exchange Types
# ==================================================

def create_observation_share(source, observation):
    return create_message(
        "OBSERVATION_SHARE",
        source,
        {"observation": observation},
    )


def create_evidence_request(source, concept):
    return create_message(
        "EVIDENCE_REQUEST",
        source,
        {"concept": concept},
    )


def create_codex_update(source, concept, confidence, evidence_ids):
    return create_message(
        "CODEX_UPDATE",
        source,
        {
            "concept": concept,
            "confidence": confidence,
            "evidence_ids": evidence_ids,
        },
    )


# ==================================================
# Validation
# ==================================================

def validate_message(message):
    required = [
        "message_id",
        "protocol",
        "message_type",
        "source",
        "timestamp",
        "payload",
    ]

    try:
        data = asdict(message)
    except (TypeError, AttributeError):
        # Not a dataclass instance at all, or a dataclass instance
        # missing a field value -- malformed input, not valid.
        return False

    for name in required:
        if name not in data:
            return False

    if message.protocol != PROTOCOL_VERSION:
        return False

    return True
