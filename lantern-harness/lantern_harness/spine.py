"""Spine + Branch: committed-knowledge and exploratory-knowledge model.

This is a NEW component. Lantern v0.84 has no branch/spine/commitment
concept (see bridge.py's LanternBridge.branches() -> NotImplementedError,
harness_status.py's branching_status). This module implements a real one,
on top of Lantern's existing, real primitives only:

  - Chronicle (append-only, hash-chained, tamper-evident) for durability
    of committed Spine entries -- the same mechanism Scars already use.
  - EvidenceKernel for evidence/contradiction linkage -- reads real
    Evidence/Contradiction records, does not invent a second ledger.
  - Chronicle.verify() for integrity, the same check ConfidenceField uses
    for its hard BLOCKED path.

Hard invariants (enforced in code, not just documented):

  1. A Branch cannot commit itself. Sealing a branch into the Spine
     requires an explicit, separately-supplied `authorized=True` from the
     caller -- confidence alone (however high) never triggers a commit.
     See SpineCommitter.commit()'s required `authorized` parameter.
  2. A commit is refused if Chronicle integrity is not VALID/NO_CHRONICLE
     (same hard-BLOCKED discipline as ConfidenceField). No score can
     override this.
  3. A commit is refused if there are unresolved (OPEN) contradictions
     for the branch's concept, unless the caller explicitly acknowledges
     them via `acknowledge_open_contradictions=True` -- contradictions
     are never silently hidden by commitment.
  4. Committed entries are appended to the real Chronicle -- once
     written, altering history requires breaking the hash chain, which
     Chronicle.verify() (and therefore ConfidenceField) will detect. This
     is Lantern's actual immutability model (integrity-protected,
     tamper-evident) -- this module does not claim stronger guarantees
     than that.
  5. A failed/abandoned Branch is preservable as a learning artifact via
     to_scar() -- it becomes a real Scar (Lantern's existing durable
     consequence record), not silently discarded.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional
import uuid


SPINE_COMMIT_EVENT_TYPE = "SPINE_COMMIT_SEALED"


def _uid() -> str:
    return str(uuid.uuid4())


@dataclass
class Branch:
    """An exploratory line of investigation. Lives outside committed
    state (the Spine) until commit() succeeds. Never persisted to
    Chronicle on its own -- only a successful commit or an explicit
    to_scar() call produces a durable record."""

    id: str
    concept: str
    hypothesis: str
    parent_branch_id: Optional[str] = None
    observation_ids: list = field(default_factory=list)
    evidence_ids: list = field(default_factory=list)
    notes: list = field(default_factory=list)
    status: str = "OPEN"  # OPEN | COMMITTED | ABANDONED

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "concept": self.concept,
            "hypothesis": self.hypothesis,
            "parent_branch_id": self.parent_branch_id,
            "observation_ids": list(self.observation_ids),
            "evidence_ids": list(self.evidence_ids),
            "notes": list(self.notes),
            "status": self.status,
        }


@dataclass(frozen=True)
class SpineEntry:
    """One committed, integrity-protected entry in the Spine."""

    id: str
    branch_id: str
    concept: str
    statement: str
    provenance: dict
    evidence_ids: tuple
    contradiction_acknowledgement: Optional[str]
    authorized_by: str
    timestamp: str
    chronicle_hash: Optional[str]

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "branch_id": self.branch_id,
            "concept": self.concept,
            "statement": self.statement,
            "provenance": dict(self.provenance),
            "evidence_ids": list(self.evidence_ids),
            "contradiction_acknowledgement": self.contradiction_acknowledgement,
            "authorized_by": self.authorized_by,
            "timestamp": self.timestamp,
            "chronicle_hash": self.chronicle_hash,
        }


@dataclass(frozen=True)
class CommitResult:
    status: str  # "COMMITTED" | "REFUSED"
    reason: str
    entry: Optional[SpineEntry] = None

    def to_dict(self) -> dict:
        return {
            "status": self.status,
            "reason": self.reason,
            "entry": self.entry.to_dict() if self.entry is not None else None,
        }


class BranchStore:
    """In-memory registry of open/committed/abandoned branches for one
    process lifetime. Not a second persistence layer -- committed
    branches' durable record lives in Chronicle via SpineCommitter;
    abandoned branches' durable record (if any) lives in a real Scar."""

    def __init__(self):
        self._branches: dict = {}

    def open_branch(self, *, concept: str, hypothesis: str, parent_branch_id: Optional[str] = None) -> Branch:
        if not concept or not concept.strip():
            raise ValueError("concept must be a non-empty string")
        if not hypothesis or not hypothesis.strip():
            raise ValueError("hypothesis must be a non-empty string")
        if parent_branch_id is not None and parent_branch_id not in self._branches:
            raise ValueError(f"unknown parent_branch_id: {parent_branch_id!r}")
        branch = Branch(id=_uid(), concept=concept.strip(), hypothesis=hypothesis.strip(), parent_branch_id=parent_branch_id)
        self._branches[branch.id] = branch
        return branch

    def get(self, branch_id: str) -> Optional[Branch]:
        return self._branches.get(branch_id)

    def add_note(self, branch_id: str, note: str) -> Branch:
        branch = self._require(branch_id)
        branch.notes.append(note)
        return branch

    def link_observation(self, branch_id: str, observation_id: str) -> Branch:
        branch = self._require(branch_id)
        if observation_id not in branch.observation_ids:
            branch.observation_ids.append(observation_id)
        return branch

    def link_evidence(self, branch_id: str, evidence_id: str) -> Branch:
        branch = self._require(branch_id)
        if evidence_id not in branch.evidence_ids:
            branch.evidence_ids.append(evidence_id)
        return branch

    def abandon(self, branch_id: str) -> Branch:
        branch = self._require(branch_id)
        if branch.status == "COMMITTED":
            raise ValueError("cannot abandon a branch that is already COMMITTED")
        branch.status = "ABANDONED"
        return branch

    def _require(self, branch_id: str) -> Branch:
        branch = self._branches.get(branch_id)
        if branch is None:
            raise ValueError(f"unknown branch_id: {branch_id!r}")
        if branch.status != "OPEN":
            raise ValueError(f"branch {branch_id!r} is {branch.status}, not OPEN")
        return branch

    def all(self) -> list:
        return list(self._branches.values())


class SpineCommitter:
    """Seals a Branch into the Spine. This is the ONLY code path that may
    produce a SpineEntry, and it enforces every hard invariant listed in
    this module's docstring."""

    def __init__(self, bridge):
        self.bridge = bridge

    def commit(
        self,
        branch: Branch,
        *,
        statement: str,
        authorized: bool,
        authorized_by: str,
        acknowledge_open_contradictions: bool = False,
    ) -> CommitResult:
        if branch.status != "OPEN":
            return CommitResult(status="REFUSED", reason=f"branch is {branch.status}, not OPEN")

        if not authorized:
            return CommitResult(
                status="REFUSED",
                reason=(
                    "authorized=False: a branch cannot commit itself and no confidence "
                    "score alone may create commitment. An explicit authorized=True from "
                    "a caller outside this module is required."
                ),
            )
        if not authorized_by or not authorized_by.strip():
            return CommitResult(status="REFUSED", reason="authorized_by must identify who/what authorized this commit")

        integrity = self.bridge.witness_integrity()
        if integrity.get("status") not in ("VALID", "NO_CHRONICLE"):
            return CommitResult(
                status="REFUSED",
                reason=f"Chronicle integrity is {integrity.get('status')!r}; refusing to commit against an untrusted chain.",
            )

        kernel = self.bridge.lantern.kernel
        open_contradictions = [
            c for c in kernel.contradictions
            if c.status == "OPEN" and c.concept == branch.concept
        ]
        contradiction_ack = None
        if open_contradictions:
            if not acknowledge_open_contradictions:
                return CommitResult(
                    status="REFUSED",
                    reason=(
                        f"{len(open_contradictions)} unresolved contradiction(s) exist for "
                        f"concept={branch.concept!r}; commit refused unless "
                        f"acknowledge_open_contradictions=True is explicitly passed."
                    ),
                )
            contradiction_ack = (
                f"{len(open_contradictions)} open contradiction(s) explicitly acknowledged "
                f"at commit time: {[c.id for c in open_contradictions]}"
            )

        entry_id = _uid()
        provenance = {
            "branch_id": branch.id,
            "parent_branch_id": branch.parent_branch_id,
            "observation_ids": list(branch.observation_ids),
            "hypothesis": branch.hypothesis,
        }

        from lantern.core import KernelEvent

        payload = {
            "entry_id": entry_id,
            "branch_id": branch.id,
            "concept": branch.concept,
            "statement": statement,
            "provenance": provenance,
            "evidence_ids": list(branch.evidence_ids),
            "contradiction_acknowledgement": contradiction_ack,
            "authorized_by": authorized_by,
        }
        event = KernelEvent(SPINE_COMMIT_EVENT_TYPE, "lantern_harness.spine", payload, id=entry_id)
        self.bridge.lantern.bus.publish(event)

        chronicle_hash = self.bridge.lantern.bus.chronicle.chain if self.bridge.lantern.bus.chronicle is not None else None

        branch.status = "COMMITTED"

        entry = SpineEntry(
            id=entry_id,
            branch_id=branch.id,
            concept=branch.concept,
            statement=statement,
            provenance=provenance,
            evidence_ids=tuple(branch.evidence_ids),
            contradiction_acknowledgement=contradiction_ack,
            authorized_by=authorized_by,
            timestamp=event.timestamp,
            chronicle_hash=chronicle_hash,
        )
        return CommitResult(status="COMMITTED", reason="all commit invariants satisfied", entry=entry)

    def read_spine(self) -> list:
        """Reconstructs committed Spine entries by replaying the real
        Chronicle and filtering for this module's own event type. This is
        the same replay-based reconstruction pattern Lantern's own
        EvidenceKernel.replay() uses for OBSERVATION_CREATED/
        EVIDENCE_CREATED/SCAR_RECORDED -- Spine entries are just another
        event type in the same durable, hash-chained log."""
        chronicle = self.bridge.lantern.bus.chronicle
        if chronicle is None:
            return []
        entries = []
        for record in chronicle.replay():
            if record.get("type") != SPINE_COMMIT_EVENT_TYPE:
                continue
            payload = record["payload"]
            entries.append(
                SpineEntry(
                    id=payload["entry_id"],
                    branch_id=payload["branch_id"],
                    concept=payload["concept"],
                    statement=payload["statement"],
                    provenance=payload["provenance"],
                    evidence_ids=tuple(payload["evidence_ids"]),
                    contradiction_acknowledgement=payload["contradiction_acknowledgement"],
                    authorized_by=payload["authorized_by"],
                    timestamp=record["timestamp"],
                    chronicle_hash=record["current_hash"],
                )
            )
        return entries


def branch_to_scar(bridge, branch: Branch, *, outcome: str, lesson: str):
    """Preserve an abandoned/failed branch as a real Scar (Lantern's
    existing durable consequence record) rather than silently discarding
    it. `outcome` must be one of scars.NETWORK_SCAR_OUTCOMES-compatible
    strings is NOT enforced here (Scar.outcome is a free-text field in
    core Lantern for non-network outcomes); this function passes through
    to the real bridge.create_scar/persist_scar path unchanged."""
    if branch.status not in ("ABANDONED", "OPEN"):
        raise ValueError("only an ABANDONED or still-OPEN (never-committed) branch can become a learning-artifact Scar")
    record = bridge.create_scar(
        source="lantern_harness.spine",
        trigger=f"branch:{branch.id}",
        observation=branch.hypothesis,
        outcome=outcome,
        severity="LOW",
        lesson=lesson,
        related_evidence_ids=list(branch.evidence_ids),
    )
    return bridge.persist_scar(record)
