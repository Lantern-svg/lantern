"""Structured contact evidence.

No new epistemic primitives. The labels are the board's own vocabulary, and a
contact result carries exactly the provenance that was actually established:
a retrieval is OBSERVED, an independent check that passed is VERIFIED, and a
failure is BLOCKED -- never silently upgraded, never silently dropped.
"""

from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field
from typing import Any, Optional

# Display states. NOT_CONFIGURED / NOT_CONNECTED / NOT_PROBED are component
# states, not evidence labels: they describe wiring, reachability, and
# whether a check has run at all -- not belief. NOT_PROBED specifically
# means "no check has been attempted yet"; UNKNOWN is reserved for a check
# that ran and could not decide.
NOT_CONFIGURED = "NOT_CONFIGURED"
NOT_CONNECTED = "NOT_CONNECTED"
NOT_PROBED = "NOT_PROBED"
ERROR = "ERROR"

OBSERVED = "OBSERVED"
VERIFIED = "VERIFIED"
CORROBORATED = "CORROBORATED"
CLAIMED = "CLAIMED"
DISPROVEN = "DISPROVEN"
BLOCKED = "BLOCKED"
UNKNOWN = "UNKNOWN"

EVIDENCE_LABELS = (OBSERVED, VERIFIED, CORROBORATED, CLAIMED, DISPROVEN, BLOCKED, UNKNOWN)
COMPONENT_STATES = (NOT_CONFIGURED, NOT_CONNECTED, NOT_PROBED, ERROR)


def now_ms() -> int:
    return int(time.time() * 1000)


@dataclass
class ContactEvidence:
    """One contact event, preserved as its own record.

    Corrections are new evidence events; nothing here rewrites an earlier one.
    """

    operation: str
    label: str
    source: str
    retrieved_at_ms: int = field(default_factory=now_ms)
    protocol_version: Optional[str] = None
    entry_hashes: list[str] = field(default_factory=list)
    fingerprint: Optional[str] = None
    verification: dict[str, Any] = field(default_factory=dict)
    failures: list[str] = field(default_factory=list)
    detail: Optional[str] = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.label not in EVIDENCE_LABELS:
            raise ValueError(f"unknown evidence label: {self.label!r}")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def make_evidence(operation: str, label: str, source: str, **kwargs: Any) -> ContactEvidence:
    return ContactEvidence(operation=operation, label=label, source=source, **kwargs)


@dataclass
class ContactReport:
    """The result of the full read-only contact workflow."""

    status: str
    agent_card: dict[str, Any] = field(default_factory=dict)
    a2a_verify: dict[str, Any] = field(default_factory=dict)
    board_read: dict[str, Any] = field(default_factory=dict)
    board_verification: dict[str, Any] = field(default_factory=dict)
    evidence: list[dict[str, Any]] = field(default_factory=list)
    untested: list[str] = field(default_factory=list)
    started_at_ms: int = field(default_factory=now_ms)
    finished_at_ms: Optional[int] = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
