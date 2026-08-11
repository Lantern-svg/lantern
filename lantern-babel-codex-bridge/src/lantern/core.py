"""
Lantern Babel Codex Bridge
Reference Core (lantern.core)

This is the canonical reference implementation of the Evidence Kernel +
modular event shell. Future changes should be made as diffs against this
file, not as fresh rewrites, so verified behavior (decay, temporal replay,
contradiction threading, non-destructive resolution, hash-chained audit)
does not silently regress.

Design laws:
- Observations are immutable inputs.
- Evidence is immutable once recorded; only new Evidence changes belief.
- Belief is derived from Evidence, never assigned directly.
- Contradictions are historical events. They are updated in place while the
  underlying evidence set is unchanged, and threaded (supersedes /
  superseded_by) when the evidence set changes, rather than deleted.
- Resolution records a judgment (a ResolutionEvent) about a contradiction.
  It does not edit or remove Evidence, and it does not directly change
  belief. Only new Evidence changes belief.
- Scars are durable consequence records of meaningful outcomes; they are
  persisted via the same append-only Chronicle and replayed on startup, but
  they do not automatically mutate belief or Codex state.
- Modules communicate only through events on the EventBus; they do not
  call into each other directly.
- The audit chain is an append-only hash chain over published events.

Known open items (see ARCHITECTURE.md):
- decay_rate is a hardcoded constant (0.05/step), not yet a frozen,
  documented protocol constant.
- Decay is step-based (one step per observation), not wall-clock-based.
  This is a deliberate choice for this reference version; revisit if
  observation frequency needs to be decoupled from decay rate.
- Concept relationships / the full Codex semantic graph are out of scope
  for this file; this file covers Observation, Evidence, Belief,
  Contradiction, Resolution, Scar persistence, and the event shell only.
- Persistence: Chronicle is an append-only, hash-chained event log.
  Recovery uses "event stream + periodic snapshot" for fast
  deterministic recovery:
    - Lantern.save_snapshot() serializes full EvidenceKernel state
      (observations/evidence/contradictions/resolutions/scars) tagged with
      the Chronicle chain position at that moment.
    - Lantern.startup() restores the latest snapshot, then replays
      only Chronicle records after that chain position -- not the
      full history from GENESIS.
    - Event payloads (OBSERVATION_CREATED, EVIDENCE_CREATED,
      CONTRADICTION_RESOLVED, SCAR_RECORDED) carry full reconstruction
      fields, so post-snapshot events rebuild runtime state exactly,
      not just module/audit-chain history.
    - CONTRADICTION_DETECTED and BELIEF_UPDATED are NOT replayed
      directly during recovery -- they're pure functions of
      observations+evidence, so replaying EVIDENCE_CREATED already
      recomputes them via detect_contradiction().
    - If no snapshot exists yet, startup() falls back to a full
      Chronicle replay, which still fully reconstructs runtime state
      (from GENESIS) since payloads are self-sufficient -- it's just
      slower than the snapshot-bounded path.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import json
import math
import os
import tempfile
import uuid
from typing import Optional

from .scars import Scar, ScarRecord, create_scar as build_scar_record, persisted_record


# ==================================================
# Utilities
# ==================================================

def uid():
    return str(uuid.uuid4())


def now():
    return datetime.now(timezone.utc).isoformat()


def chronicle_body(event):
    return {
        "id": event.id,
        "type": event.event_type,
        "source": event.source,
        "payload": event.payload,
    }


# ==================================================
# Shared Event Layer
# ==================================================

@dataclass
class KernelEvent:
    event_type: str
    source: str
    payload: dict
    target: Optional[str] = None
    id: str = field(default_factory=uid)
    timestamp: str = field(default_factory=now)


# ==================================================
# Chronicle
# ==================================================

class Chronicle:
    def __init__(self, filename="chronicle.jsonl"):
        self.path = Path(filename)
        self.chain = "GENESIS"

        if self.path.exists():
            self._recover_chain()

    def append(self, event):
        body = chronicle_body(event)

        digest = hashlib.sha256(
            (self.chain + json.dumps(body, sort_keys=True)).encode()
        ).hexdigest()

        record = {
            "timestamp": now(),
            "previous_hash": self.chain,
            "current_hash": digest,
            **body,
        }

        serialized = json.dumps(record, sort_keys=True)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        staged = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=self.path.parent,
                prefix=f".{self.path.name}.",
                suffix=".tmp",
                delete=False,
            ) as handle:
                staged = Path(handle.name)
                if self.path.exists():
                    with self.path.open(encoding="utf-8") as existing:
                        handle.write(existing.read())
                handle.write(serialized)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())

            with staged.open(encoding="utf-8") as verify_handle:
                lines = [line for line in verify_handle if line.strip()]
            if not lines or lines[-1].strip() != serialized:
                raise OSError("chronicle staging verification failed")

            os.replace(staged, self.path)
            staged = None

            with self.path.open(encoding="utf-8") as verify_handle:
                persisted_lines = [line for line in verify_handle if line.strip()]
            if not persisted_lines or persisted_lines[-1].strip() != serialized:
                raise OSError("chronicle final content verification failed")
        except BaseException:
            if staged is not None:
                staged.unlink(missing_ok=True)
            raise

        self.chain = digest

    def replay(self):
        if not self.path.exists():
            return

        with self.path.open(encoding="utf-8") as handle:
            for line in handle:
                if line.strip():
                    yield json.loads(line)

    def verify(self):
        previous = "GENESIS"

        if not self.path.exists():
            return True

        with self.path.open(encoding="utf-8") as handle:
            for line in handle:
                if not line.strip():
                    continue

                record = json.loads(line)

                if record["previous_hash"] != previous:
                    return False

                body = {
                    "id": record["id"],
                    "type": record["type"],
                    "source": record["source"],
                    "payload": record["payload"],
                }

                digest = hashlib.sha256(
                    (previous + json.dumps(body, sort_keys=True)).encode()
                ).hexdigest()

                if digest != record["current_hash"]:
                    return False

                previous = digest

        return True

    def _recover_chain(self):
        previous = "GENESIS"

        with self.path.open(encoding="utf-8") as handle:
            for line in handle:
                if line.strip():
                    previous = json.loads(line)["current_hash"]

        self.chain = previous

    def records_after(self, chain_hash):
        if chain_hash == "GENESIS":
            yield from self.replay()
            return

        found = False
        for record in self.replay():
            if found:
                yield record
            elif record["current_hash"] == chain_hash:
                found = True

        if not found:
            yield from self.replay()


# ==================================================
# Evidence Kernel
# ==================================================

@dataclass
class Observation:
    content: str
    source: str
    reliability: float
    step: int
    id: str = field(default_factory=uid)
    metadata: dict = field(default_factory=dict)


@dataclass
class Evidence:
    concept: str
    observation_id: str
    weight: float
    sign: int
    step: int
    id: str = field(default_factory=uid)

    def decayed_weight(self, current_step, decay_rate=0.05):
        age = max(0, current_step - self.step)
        return self.weight * max(0, 1 - decay_rate * age)


@dataclass
class Contradiction:
    concept: str
    evidence_snapshot: list
    historical_severity: float
    current_severity: float
    created_step: int
    id: str = field(default_factory=uid)
    status: str = "OPEN"
    resolution_id: Optional[str] = None
    supersedes: Optional[str] = None
    superseded_by: Optional[str] = None


@dataclass
class ResolutionEvent:
    contradiction_id: str
    decision: str
    reasoning: str
    confidence: float
    evidence_snapshot: list
    id: str = field(default_factory=uid)


class EvidenceKernel:

    def __init__(self):
        self.step = 0
        self.observations = {}
        self.evidence = []
        self.contradictions = []
        self.resolutions = []

    def observe(self, content, source, reliability, metadata=None):
        self.step += 1
        obs = Observation(content, source, reliability, self.step, metadata=metadata or {})
        self.observations[obs.id] = obs
        return obs

    def add_evidence(self, concept, observation_id, weight, sign):
        obs = self.observations[observation_id]
        evidence = Evidence(
            concept,
            observation_id,
            weight * obs.reliability,
            sign,
            self.step
        )
        self.evidence.append(evidence)
        contradiction = self.detect_contradiction(concept)
        return evidence, contradiction

    def belief(self, concept, at_step=None):
        if at_step is None:
            at_step = self.step

        score = 0
        for evidence in self.evidence:
            if evidence.concept == concept and evidence.step <= at_step:
                score += evidence.decayed_weight(at_step) * evidence.sign

        return self.sigmoid(score)

    def sigmoid(self, value):
        return 1 / (1 + math.exp(-value))

    def latest_contradiction(self, concept):
        matches = [c for c in self.contradictions if c.concept == concept]
        return matches[-1] if matches else None

    def contradiction_severity(self, concept, at_step=None):
        if at_step is None:
            at_step = self.step

        positive = sum(
            e.decayed_weight(at_step)
            for e in self.evidence
            if e.concept == concept and e.sign == 1
        )
        negative = sum(
            e.decayed_weight(at_step)
            for e in self.evidence
            if e.concept == concept and e.sign == -1
        )
        return min(positive, negative)

    def detect_contradiction(self, concept):
        related = [e for e in self.evidence if e.concept == concept]

        positive = [e for e in related if e.sign == 1]
        negative = [e for e in related if e.sign == -1]

        if not positive or not negative:
            return None

        snapshot = sorted(e.id for e in related)

        latest = self.latest_contradiction(concept)

        if latest and latest.evidence_snapshot == snapshot:
            latest.current_severity = self.contradiction_severity(concept)
            return latest

        contradiction = Contradiction(
            concept,
            snapshot,
            self.contradiction_severity(concept),
            self.contradiction_severity(concept),
            self.step,
            supersedes=latest.id if latest else None
        )

        if latest:
            latest.superseded_by = contradiction.id

        self.contradictions.append(contradiction)

        return contradiction

    def resolve(self, contradiction_id, decision, reasoning, confidence):
        contradiction = next(
            (c for c in self.contradictions if c.id == contradiction_id),
            None
        )

        if not contradiction:
            return None

        resolution = ResolutionEvent(
            contradiction.id,
            decision,
            reasoning,
            confidence,
            contradiction.evidence_snapshot
        )

        contradiction.status = "RESOLVED"
        contradiction.resolution_id = resolution.id

        self.resolutions.append(resolution)

        return resolution

    def snapshot(self, chronicle_chain="GENESIS", scars=None):
        return {
            "chronicle_chain": chronicle_chain,
            "step": self.step,
            "observations": [
                vars(obs) for obs in self.observations.values()
            ],
            "evidence": [vars(e) for e in self.evidence],
            "contradictions": [vars(c) for c in self.contradictions],
            "resolutions": [vars(r) for r in self.resolutions],
            "scars": [scar.to_dict() for scar in (scars or [])],
        }

    @classmethod
    def restore(cls, snapshot):
        kernel = cls()
        kernel.step = snapshot["step"]
        kernel.observations = {
            obs["id"]: Observation(**obs)
            for obs in snapshot["observations"]
        }
        kernel.evidence = [Evidence(**e) for e in snapshot["evidence"]]
        kernel.contradictions = [
            Contradiction(**c) for c in snapshot["contradictions"]
        ]
        kernel.resolutions = [
            ResolutionEvent(**r) for r in snapshot["resolutions"]
        ]
        return kernel


# ==================================================
# Modular Shell
# ==================================================

class LanternModule:
    name = "module"

    def __init__(self):
        self.events = []

    def observe(self, event):
        self.events.append(event)


class MemoryModule(LanternModule):
    name = "memory"

    def __init__(self):
        super().__init__()
        self.history = []

    def observe(self, event):
        super().observe(event)
        self.history.append(event.payload)


class CodexModule(LanternModule):
    name = "codex"

    def __init__(self):
        super().__init__()
        self.state = {}

    def observe(self, event):
        super().observe(event)
        self.state[event.id] = {
            "type": event.event_type,
            "payload": event.payload
        }


class ReasoningModule(LanternModule):
    name = "reasoning"


# ==================================================
# Event Bus + Audit Chain
# ==================================================

class EventBus:

    def __init__(self, chronicle=None):
        self.modules = []
        self.history = []
        self.chain = "GENESIS"
        self.chronicle = chronicle

    def register(self, module):
        self.modules.append(module)

    def publish(self, event):
        self.history.append(event)
        self.audit(event)
        if self.chronicle is not None:
            self.chronicle.append(event)
        for module in self.modules:
            module.observe(event)

    def replay_publish(self, event):
        self.history.append(event)
        self.audit(event)
        for module in self.modules:
            module.observe(event)

    def audit(self, event):
        block = (
            self.chain
            + event.id
            + event.event_type
            + json.dumps(event.payload, sort_keys=True)
        )
        self.chain = hashlib.sha256(block.encode()).hexdigest()


# ==================================================
# Lantern Shell
# ==================================================

class Lantern:

    def __init__(self, chronicle_filename=None):
        self.kernel = EvidenceKernel()
        self.scars = {}
        chronicle = None
        if chronicle_filename is not None:
            chronicle = Chronicle(chronicle_filename)
        self.bus = EventBus(chronicle=chronicle)
        self.modules = [MemoryModule(), CodexModule(), ReasoningModule()]
        for module in self.modules:
            self.bus.register(module)

    def snapshot_path(self, chronicle_filename):
        return Path(str(chronicle_filename) + ".snapshot.json")

    def save_snapshot(self, path=None):
        if path is None:
            if self.bus.chronicle is None:
                raise ValueError("No chronicle attached; pass an explicit path.")
            path = self.snapshot_path(self.bus.chronicle.path)

        snapshot = self.kernel.snapshot(
            chronicle_chain=self.bus.chronicle.chain if self.bus.chronicle else "GENESIS",
            scars=list(self.scars.values()),
        )
        serialized = json.dumps(snapshot, sort_keys=True)
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)

        previous = None
        had_previous = target.exists()
        if had_previous:
            previous = target.read_bytes()

        staged = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=target.parent,
                prefix=f".{target.name}.",
                suffix=".tmp",
                delete=False,
            ) as handle:
                staged = Path(handle.name)
                handle.write(serialized)
                handle.flush()
                os.fsync(handle.fileno())

            if staged.read_text(encoding="utf-8") != serialized:
                raise OSError("snapshot staging verification failed")

            os.replace(staged, target)
            staged = None

            persisted = target.read_text(encoding="utf-8")
            if persisted != serialized:
                raise OSError("snapshot final content verification failed")
        except BaseException:
            if staged is not None:
                staged.unlink(missing_ok=True)
            try:
                if had_previous:
                    restore = target.parent / f".{target.name}.restore"
                    with restore.open("wb") as handle:
                        handle.write(previous)
                        handle.flush()
                        os.fsync(handle.fileno())
                    os.replace(restore, target)
                    if target.read_bytes() != previous:
                        raise OSError("snapshot restoration verification failed")
                else:
                    target.unlink(missing_ok=True)
            except OSError:
                pass
            raise

        return path

    def load_snapshot(self, path=None):
        if path is None:
            if self.bus.chronicle is None:
                raise ValueError("No chronicle attached; pass an explicit path.")
            path = self.snapshot_path(self.bus.chronicle.path)

        path = Path(path)
        if not path.exists():
            return None

        return json.loads(path.read_text(encoding="utf-8"))

    def startup(self, snapshot_path=None):
        if self.bus.chronicle is None:
            return

        if not self.bus.chronicle.verify():
            raise RuntimeError("Chronicle verification failed")

        snapshot = self.load_snapshot(snapshot_path)

        if snapshot is not None:
            self.kernel = EvidenceKernel.restore(snapshot)
            self.scars = {
                scar_data["id"]: Scar.from_dict(scar_data)
                for scar_data in snapshot.get("scars", [])
            }
            pending = self.bus.chronicle.records_after(snapshot["chronicle_chain"])
        else:
            pending = self.bus.chronicle.replay()

        for record in pending or []:
            event = KernelEvent(
                id=record["id"],
                event_type=record["type"],
                source=record["source"],
                payload=record["payload"],
            )
            self._apply_to_kernel(event)
            self.bus.replay_publish(event)

    def _apply_to_kernel(self, event):
        payload = event.payload

        if event.event_type == "OBSERVATION_CREATED":
            obs = Observation(
                content=payload["content"],
                source=payload["source"],
                reliability=payload["reliability"],
                step=payload["step"],
                id=payload["id"],
                metadata=payload.get("metadata", {}),
            )
            self.kernel.observations[obs.id] = obs
            self.kernel.step = max(self.kernel.step, obs.step)

        elif event.event_type == "EVIDENCE_CREATED":
            evidence = Evidence(
                concept=payload["concept"],
                observation_id=payload["observation_id"],
                weight=payload["weight"],
                sign=payload["sign"],
                step=payload["step"],
                id=payload["id"],
            )
            self.kernel.evidence.append(evidence)
            self.kernel.step = max(self.kernel.step, evidence.step)
            self.kernel.detect_contradiction(evidence.concept)

        elif event.event_type == "CONTRADICTION_RESOLVED":
            contradiction = next(
                (
                    c for c in self.kernel.contradictions
                    if c.id == payload["contradiction"]
                ),
                None,
            )
            if contradiction:
                contradiction.status = "RESOLVED"
                contradiction.resolution_id = payload["id"]
                self.kernel.resolutions.append(ResolutionEvent(
                    contradiction_id=payload["contradiction"],
                    decision=payload["decision"],
                    reasoning=payload["reasoning"],
                    confidence=payload["confidence"],
                    evidence_snapshot=payload["evidence_snapshot"],
                    id=payload["id"],
                ))

        elif event.event_type == "SCAR_RECORDED":
            scar = Scar.from_dict(payload)
            self.scars[scar.id] = scar

    def _apply_to_runtime(self, event):
        self._apply_to_kernel(event)

    def observe(self, content, source, reliability, metadata=None):
        obs = self.kernel.observe(content, source, reliability, metadata)
        self.bus.publish(KernelEvent(
            "OBSERVATION_CREATED", "kernel",
            {
                "id": obs.id,
                "content": content,
                "source": obs.source,
                "reliability": obs.reliability,
                "step": obs.step,
                "metadata": obs.metadata,
            }
        ))
        return obs

    def add_evidence(self, concept, observation_id, weight, sign):
        evidence, contradiction = self.kernel.add_evidence(
            concept, observation_id, weight, sign
        )

        self.bus.publish(KernelEvent(
            "EVIDENCE_CREATED", "kernel",
            {
                "id": evidence.id,
                "concept": concept,
                "observation_id": evidence.observation_id,
                "weight": evidence.weight,
                "sign": evidence.sign,
                "step": evidence.step,
            }
        ))

        self.bus.publish(KernelEvent(
            "BELIEF_UPDATED", "kernel",
            {"concept": concept, "belief": self.kernel.belief(concept)}
        ))

        if contradiction:
            self.bus.publish(KernelEvent(
                "CONTRADICTION_DETECTED", "kernel",
                {
                    "id": contradiction.id,
                    "concept": concept,
                    "evidence_snapshot": contradiction.evidence_snapshot,
                    "historical_severity": contradiction.historical_severity,
                    "current_severity": contradiction.current_severity,
                    "created_step": contradiction.created_step,
                    "status": contradiction.status,
                    "resolution_id": contradiction.resolution_id,
                    "supersedes": contradiction.supersedes,
                    "superseded_by": contradiction.superseded_by,
                }
            ))

        return evidence

    def resolve(self, contradiction_id, decision, reasoning, confidence):
        resolution = self.kernel.resolve(
            contradiction_id, decision, reasoning, confidence
        )

        if resolution:
            self.bus.publish(KernelEvent(
                "CONTRADICTION_RESOLVED", "kernel",
                {
                    "id": resolution.id,
                    "contradiction": contradiction_id,
                    "decision": resolution.decision,
                    "reasoning": resolution.reasoning,
                    "confidence": resolution.confidence,
                    "evidence_snapshot": resolution.evidence_snapshot,
                }
            ))

        return resolution

    def create_scar(self, **kwargs) -> ScarRecord:
        return build_scar_record(**kwargs)

    def persist_scar(self, record: ScarRecord) -> ScarRecord:
        if self.bus.chronicle is None:
            raise ValueError("No chronicle attached; cannot persist scar")

        scar = record.scar
        self.bus.publish(KernelEvent(
            "SCAR_RECORDED",
            scar.source,
            scar.to_dict(),
            id=scar.id,
            timestamp=scar.timestamp,
        ))
        self.scars[scar.id] = scar
        verified = self.bus.chronicle.verify() and scar.id in self.scars
        return persisted_record(scar, verified=verified)

    def load_scar(self, scar_id: str) -> Optional[ScarRecord]:
        scar = self.scars.get(scar_id)
        if scar is None:
            return None
        return ScarRecord(
            scar=scar,
            constructed=True,
            persisted=True,
            verified=self.bus.chronicle.verify() if self.bus.chronicle is not None else False,
            replayed=False,
        )

    def replay_scars(self):
        return [
            ScarRecord(scar=scar, constructed=True, persisted=True, verified=True, replayed=True)
            for scar in self.scars.values()
        ]

    def verify_scar(self, scar_id: str) -> bool:
        if self.bus.chronicle is None:
            return False
        return self.bus.chronicle.verify() and scar_id in self.scars


if __name__ == "__main__":
    lantern = Lantern()

    a = lantern.observe("Water freezes near zero", "experiment", .95)
    lantern.add_evidence("water_freezing", a.id, 1, 1)

    b = lantern.observe("Water never freezes", "claim", .2)
    lantern.add_evidence("water_freezing", b.id, 1, -1)

    contradiction = lantern.kernel.contradictions[0]

    lantern.resolve(
        contradiction.id,
        "Low reliability claim rejected",
        "Experimental evidence stronger",
        .9
    )

    print("Belief:", lantern.kernel.belief("water_freezing"))
    print("Contradiction:", contradiction.status)
    print("Codex events:", len(lantern.modules[1].events))
    print("Audit:", lantern.bus.chain)
