"""LanternBridge: a thin adapter over the real `lantern` package.

Does not recreate Lantern's internals. Every method here is a direct
call into lantern.core.Lantern / lantern.agent.LanternAgent / etc. If
Lantern doesn't have something (e.g. a "branch" concept), this bridge
does not invent it -- see NOT_IMPLEMENTED markers below and
harness_status.py's honest reporting.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from lantern.agent import LanternAgent
from lantern.core import Lantern
from lantern.identity import NodeIdentity, default_identity_dir, load_or_create


class LanternBridge:
    """Wraps a real Lantern instance + LanternAgent + NodeIdentity.

    Concepts referenced in the mission brief that Lantern v0.84 does not
    implement (branches/spine/commitment, perspective differential,
    witness ledger as a named object, forecast engine, intrinsic
    continuity values) are NOT faked here. Bridge methods for those
    return None / raise NotImplementedError with an honest message,
    rather than simulating behavior Lantern doesn't actually have.
    """

    def __init__(self, data_dir: str | Path, node_id: str = "lantern-harness-node"):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.node_id = node_id

        chronicle_path = self.data_dir / "chronicle.jsonl"
        self.lantern = Lantern(chronicle_filename=str(chronicle_path))
        self.agent = LanternAgent(self.lantern, chronicle=self.lantern.bus.chronicle)

        self._identity: Optional[NodeIdentity] = None
        self._identity_error: Optional[str] = None

    # ---- identity ----

    def ensure_identity(self) -> dict:
        """Loads or creates the real NodeIdentity. Returns a status dict;
        never raises to the caller (caller sees IDENTITY: ERROR instead)."""
        try:
            identity_dir = default_identity_dir(self.data_dir, self.node_id)
            self._identity = load_or_create(self.node_id, identity_dir)
            return {
                "status": "READY",
                "node_id": self.node_id,
                "public_key": self._identity.verify_key_hex(),
            }
        except Exception as exc:  # noqa: BLE001 - report, don't crash the harness
            self._identity_error = str(exc)
            return {"status": "ERROR", "detail": str(exc)}

    def identity_status(self) -> dict:
        if self._identity is not None:
            return {
                "status": "READY",
                "node_id": self.node_id,
                "public_key": self._identity.verify_key_hex(),
            }
        if self._identity_error is not None:
            return {"status": "ERROR", "detail": self._identity_error}
        return {"status": "NOT_INITIALIZED"}

    # ---- startup / recovery ----

    def startup(self) -> dict:
        """Runs LanternAgent.startup() (snapshot-first recovery) and
        returns its actual status dict."""
        return self.agent.startup()

    # ---- evidence flow (direct passthrough to EvidenceKernel via agent) ----

    def observe(self, content: str, source: str, reliability: float = 1.0, metadata: Optional[dict] = None):
        return self.agent.observe(content, source, reliability=reliability, metadata=metadata)

    def add_evidence(self, concept: str, observation_id: str, weight: float, sign: int):
        """Returns the created Evidence record. lantern.core.Lantern.add_evidence
        (unlike the lower-level EvidenceKernel.add_evidence) only returns
        the Evidence itself; check latest_contradiction() separately if
        a contradiction may have been raised."""
        return self.agent.add_evidence(concept, observation_id, weight, sign)

    def resolve(self, contradiction_id: str, decision: str, reasoning: str, confidence: float):
        return self.agent.resolve(contradiction_id, decision, reasoning, confidence)

    def belief(self, concept: str, at_step: Optional[int] = None) -> float:
        return self.agent.ask_belief(concept, at_step=at_step)

    def latest_contradiction(self, concept: str):
        return self.lantern.kernel.latest_contradiction(concept)

    # ---- persistence ----

    def save_snapshot(self):
        return self.lantern.save_snapshot()

    def status(self) -> dict:
        """Real LanternAgent.status() passthrough."""
        return self.agent.status()

    # ---- scars ----

    def create_scar(self, **kwargs):
        return self.lantern.create_scar(**kwargs)

    def persist_scar(self, record):
        return self.lantern.persist_scar(record)

    # ---- concepts not implemented in Lantern v0.84 ----
    # These are intentionally NOT faked. Calling them tells the caller
    # exactly what is missing rather than pretending it exists.

    def branches(self):
        raise NotImplementedError(
            "Lantern v0.84 has no branch/spine/commitment model. "
            "This is a genuine gap, not a bridge limitation -- see "
            "BRANCHING_STATUS: NOT_IMPLEMENTED in the harness status report."
        )

    def witness_integrity(self) -> dict:
        """Lantern has Chronicle.verify() (hash-chain integrity), which is
        the real underlying mechanism the mission's "Witness Ledger"
        concept maps onto. There is no separate WitnessLedger class."""
        chronicle = self.lantern.bus.chronicle
        if chronicle is None:
            return {"status": "NO_CHRONICLE", "mechanism": "Chronicle.verify() hash-chain check"}
        try:
            valid = chronicle.verify()
            return {"status": "VALID" if valid else "INVALID", "mechanism": "Chronicle.verify() hash-chain check"}
        except Exception as exc:  # noqa: BLE001
            return {"status": "ERROR", "detail": str(exc)}
