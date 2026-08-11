"""
Lantern Scar Persistence v0.95

Purpose:
    Make Scar persistence real, durable, replayable, and machine-checkable
    without pretending a constructed Python object is already memory.

Design:
    - A Scar is a durable consequence record of a meaningful outcome,
      contradiction, failure, or learning event.
    - A Scar is not generic memory, not evidence, and not a belief.
    - Scar persistence reuses Lantern's existing durability primitive:
      the append-only, hash-chained Chronicle.
    - A Scar may be constructed in memory before it is persisted.
      Construction, persistence, verification, and replay are distinct states.

A Scar records experience; it does not automatically become a principle,
belief, or Codex mutation. Interpretation remains a later step.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional
import uuid

from .protocol import PROTOCOL_VERSION


NOT_IMPLEMENTED = "NOT_IMPLEMENTED"
ACTIVE = "ACTIVE"
SCAR_EVENT_TYPE = "SCAR_RECORDED"
NETWORK_SCAR_OUTCOMES = frozenset(
    {
        "FAILED_HANDSHAKE",
        "INCOMPATIBLE_PROTOCOL",
        "REJECTED_CAPABILITY",
        "CONTRADICTORY_OBSERVATION",
        "INVALID_PROVENANCE",
        "SUCCESSFUL_COLLABORATION",
        "SUCCESSFUL_INTEGRATION",
        "INTEGRATION_ROLLBACK",
    }
)


def _uid() -> str:
    return str(uuid.uuid4())


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class ScarPersistenceStatus:
    status: str
    reason: str

    def to_dict(self):
        return {"status": self.status, "reason": self.reason}


@dataclass(frozen=True)
class Scar:
    id: str
    timestamp: str
    source: str
    trigger: str
    observation: str
    outcome: str
    severity: str
    protocol_version: str
    lesson: str | None = None
    related_contradiction_id: str | None = None
    related_evidence_ids: tuple[str, ...] = field(default_factory=tuple)
    provenance: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "timestamp": self.timestamp,
            "source": self.source,
            "trigger": self.trigger,
            "observation": self.observation,
            "outcome": self.outcome,
            "severity": self.severity,
            "lesson": self.lesson,
            "related_contradiction_id": self.related_contradiction_id,
            "related_evidence_ids": list(self.related_evidence_ids),
            "protocol_version": self.protocol_version,
            "provenance": dict(self.provenance),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Scar":
        return cls(
            id=data["id"],
            timestamp=data["timestamp"],
            source=data["source"],
            trigger=data["trigger"],
            observation=data["observation"],
            outcome=data["outcome"],
            severity=data["severity"],
            lesson=data.get("lesson"),
            related_contradiction_id=data.get("related_contradiction_id"),
            related_evidence_ids=tuple(data.get("related_evidence_ids", [])),
            protocol_version=data["protocol_version"],
            provenance=dict(data.get("provenance", {})),
        )


@dataclass(frozen=True)
class ScarRecord:
    scar: Scar
    constructed: bool
    persisted: bool
    verified: bool
    replayed: bool

    def to_dict(self) -> dict:
        return {
            "scar": self.scar.to_dict(),
            "constructed": self.constructed,
            "persisted": self.persisted,
            "verified": self.verified,
            "replayed": self.replayed,
        }


def scar_persistence_status() -> ScarPersistenceStatus:
    return ScarPersistenceStatus(
        status=ACTIVE,
        reason=(
            "Scar persistence is implemented through Lantern's existing "
            "append-only hash-chained Chronicle. A Scar is only persisted "
            "after a durable Chronicle append succeeds and can later be "
            "verified and replayed."
        ),
    )


def create_scar(
    *,
    source: str,
    trigger: str,
    observation: str,
    outcome: str,
    severity: str,
    lesson: str | None = None,
    related_contradiction_id: str | None = None,
    related_evidence_ids: list[str] | tuple[str, ...] | None = None,
    protocol_version: str = PROTOCOL_VERSION,
    provenance: Optional[dict] = None,
    scar_id: str | None = None,
    timestamp: str | None = None,
) -> ScarRecord:
    scar = Scar(
        id=scar_id or _uid(),
        timestamp=timestamp or _now(),
        source=source,
        trigger=trigger,
        observation=observation,
        outcome=outcome,
        severity=severity,
        lesson=lesson,
        related_contradiction_id=related_contradiction_id,
        related_evidence_ids=tuple(related_evidence_ids or ()),
        protocol_version=protocol_version,
        provenance=dict(provenance or {}),
    )
    return ScarRecord(
        scar=scar,
        constructed=True,
        persisted=False,
        verified=False,
        replayed=False,
    )


def record_from_replay(scar: Scar) -> ScarRecord:
    return ScarRecord(
        scar=scar,
        constructed=True,
        persisted=True,
        verified=True,
        replayed=True,
    )


def persisted_record(scar: Scar, *, verified: bool) -> ScarRecord:
    return ScarRecord(
        scar=scar,
        constructed=True,
        persisted=True,
        verified=verified,
        replayed=False,
    )


def verify_scar_record(record: ScarRecord, scars_by_id: dict[str, Scar]) -> bool:
    return record.persisted and record.scar.id in scars_by_id


def replay_scars(scars_by_id: dict[str, Scar]) -> list[ScarRecord]:
    return [record_from_replay(scar) for scar in scars_by_id.values()]


def load_scar(scars_by_id: dict[str, Scar], scar_id: str) -> Optional[ScarRecord]:
    scar = scars_by_id.get(scar_id)
    if scar is None:
        return None
    return record_from_replay(scar)


def should_record_network_scar(*, outcome: str, meaningful: bool) -> bool:
    return meaningful and outcome in NETWORK_SCAR_OUTCOMES


def create_network_scar(
    *,
    source: str,
    trigger: str,
    observation: str,
    outcome: str,
    severity: str,
    provenance: Optional[dict] = None,
    lesson: str | None = None,
) -> ScarRecord:
    if not should_record_network_scar(outcome=outcome, meaningful=True):
        raise ValueError("network outcome is not scar-eligible")

    return create_scar(
        source=source,
        trigger=trigger,
        observation=observation,
        outcome=outcome,
        severity=severity,
        lesson=lesson,
        provenance=dict(provenance or {}),
    )


def describe_scar_claim(scar_id: str, summary: str) -> dict:
    """Build a Scar-shaped record WITHOUT claiming it was persisted.

    This helper remains deliberately honest: it returns a Scar-like dict
    for conversational/reporting use, but it is not a durable write and
    must never be confused with one.
    """
    return {
        "scar_id": scar_id,
        "summary": summary,
        "persisted": False,
        "persistence_status": {
            "status": ACTIVE,
            "reason": (
                "Scar persistence exists, but this helper does not invoke it. "
                "This value is generated structured data only, not a durable write."
            ),
        },
    }
