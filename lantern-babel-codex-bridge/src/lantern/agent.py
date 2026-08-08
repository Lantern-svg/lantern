"""
lantern.agent

Lantern Agent Adapter v0.80

Purpose:
    Thin interface around the frozen Lantern core.

Responsibilities:
    - expose stable API
    - connect Chronicle if available
    - provide status
    - avoid modifying kernel behavior

The agent is not the intelligence.
The kernel remains the intelligence.
"""

from datetime import datetime, timezone


class LanternAgent:

    def __init__(self, lantern, chronicle=None):
        self.lantern = lantern
        self.chronicle = chronicle

        self.started = datetime.now(timezone.utc).isoformat()

    # ==================================================
    # Observation Interface
    # ==================================================

    def observe(self, content, source, reliability=1.0, metadata=None):
        return self.lantern.observe(content, source, reliability, metadata)

    # ==================================================
    # Evidence Interface
    # ==================================================

    def add_evidence(self, concept, observation_id, weight, sign):
        return self.lantern.add_evidence(concept, observation_id, weight, sign)

    # ==================================================
    # Contradiction Resolution
    # ==================================================

    def resolve(self, contradiction_id, decision, reasoning, confidence):
        return self.lantern.resolve(contradiction_id, decision, reasoning, confidence)

    # ==================================================
    # State Query
    # ==================================================

    def status(self):
        kernel = self.lantern.kernel

        return {
            "started": self.started,
            "step": kernel.step,
            "observations": len(kernel.observations),
            "evidence": len(kernel.evidence),
            "contradictions": len(kernel.contradictions),
            "modules": [module.name for module in self.lantern.modules],
            "chronicle": self.chronicle is not None,
        }

    # ==================================================
    # Chronicle Startup
    # ==================================================

    def startup(self):
        """Verify and recover the Chronicle (if any) via the wrapped
        Lantern's snapshot-first fast recovery. This delegates to
        Lantern.startup() rather than duplicating its replay logic, so
        the agent always gets the same kernel-state reconstruction
        guarantees as the underlying core (see lantern.core's
        module docstring for exactly what's reconstructed).
        """
        if self.chronicle is None:
            return {"status": "NO_CHRONICLE"}

        before = len(self.lantern.bus.history)

        self.lantern.startup()

        restored = len(self.lantern.bus.history) - before

        return {"status": "READY", "events_replayed": restored}

    # ==================================================
    # Convenience
    # ==================================================

    def ask_belief(self, concept, at_step=None):
        return self.lantern.kernel.belief(concept, at_step=at_step)
