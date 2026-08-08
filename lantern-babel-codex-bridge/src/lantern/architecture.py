"""
Lantern Architecture Referee v0.91

Purpose:
- Preserve an independent architectural reference state
- Inspect the live implementation read-only
- Detect drift without rewriting live protocol modules\n- Keep CODEX_UPDATE disabled until its trust semantics are defined

This referee describes the architecture.
It does not mutate runtime behavior.
It only: OBSERVE -> COMPARE -> REPORT.
"""

from dataclasses import dataclass, field
from pathlib import Path
import hashlib
import inspect
import json


ARCHITECTURE_VERSION = "0.91"


# ============================================================
# INDEPENDENT ARCHITECTURAL REFERENCE STATE
# ============================================================

CANONICAL_CAPABILITIES = {
    "evidence_exchange": True,
    "belief_query": True,
    "contradiction_tracking": True,
    "snapshot_exchange": True,
    "handshake": True,

    # Explicitly disabled.
    # A remote Codex claim must never directly mutate local belief.
    "codex_update": False,
}


# Keyed by the actual wire message_type strings used by
# protocol.py / router.py, not by capability name.
CANONICAL_MESSAGE_REQUIREMENTS = {
    "OBSERVATION_SHARE": "evidence_exchange",
    "EVIDENCE_REQUEST": "belief_query",
    "CODEX_UPDATE": "codex_update",
}


CANONICAL_PROTOCOL_MESSAGE_TYPES = {
    "OBSERVATION_SHARE",
    "EVIDENCE_REQUEST",
    "CODEX_UPDATE",
}





FROZEN_CONSTANTS = {
    "belief_neutral_value": 0.5,
    "decay_rate": 0.05,
    "remote_default_reliability": 0.5,
    "comparison_contradiction_gap": 0.30,
    "comparison_confidence_gap": 0.10,
    "resolution_mutates_evidence": False,
    "remote_confidence_mutates_local_belief": False,

    # Continuity watermark (v0.92). The watermark is a read-only view
    # over already-existing state (EvidenceKernel.step +
    # Chronicle.chain), not a new persisted mechanism. These two
    # flags are the trust invariants the referee enforces on it:
    # a watermark describes position, it never grants authority.
    "watermark_mutates_belief": False,
    "watermark_bypasses_capability_gate": False,
}


MODULES = {
    "core": "Evidence and belief kernel",
    "continuity": "Read-only watermark view over kernel step + Chronicle chain",
    "agent": "Stable external API",
    "protocol": "Wire message definitions",
    "handshake": "Peer capability negotiation",
    "compatibility": "Protocol compatibility",
    "router": "Message routing",
    "boundary": "Capability-gated ingress",
    "bridge": "Protocol-to-agent bridge",
    "federation": "Remote observation ingestion",
    "evaluation": "Observation-to-evidence gate",
    "codex_compare": "Perspective comparison",
    "codex_explanation": "Read-only perspective explanation",
    "architecture": "Independent read-only architecture referee",
}


OPEN_DECISIONS = {
    "custom_message_capabilities":
        "Whether every custom wire message requires explicit capability registration",

    "step_vs_wall_clock_decay":
        "Whether decay remains observation-step based",

    "architecture_document_sync":
        "Keep ARCHITECTURE.md synchronized with shipped implementation",

    "concept_relationship_graph":
        "Explicit semantic relationships between Codex concepts",

    "codex_update_trust":
        "How CODEX_UPDATE could ever influence local state",

    "watermark_remote_chain_provenance":
        "Remote chain hashes cannot be cryptographically re-derived "
        "locally (no shared ledger between instances); DIVERGED is "
        "currently a structural flag, not a proof of tampering",
}


# ============================================================
# RESULT TYPES
# ============================================================

@dataclass(frozen=True)
class Finding:
    severity: str
    category: str
    name: str
    expected: object
    actual: object

    @property
    def message(self):
        return (
            f"{self.name}: expected={self.expected!r}, "
            f"actual={self.actual!r}"
        )


@dataclass
class ArchitectureReport:
    findings: list[Finding] = field(default_factory=list)
    reference_fingerprint: str = ""
    live_fingerprint: str = ""

    @property
    def healthy(self) -> bool:
        return not any(item.severity == "ERROR" for item in self.findings)

    def errors(self):
        return [item for item in self.findings if item.severity == "ERROR"]

    def warnings(self):
        return [item for item in self.findings if item.severity == "WARNING"]

    def infos(self):
        return [item for item in self.findings if item.severity == "INFO"]

    def by_category(self, category):
        return [item for item in self.findings if item.category == category]

    def to_dict(self):
        return {
            "healthy": self.healthy,
            "reference_fingerprint": self.reference_fingerprint,
            "live_fingerprint": self.live_fingerprint,
            "findings": [
                {
                    "severity": item.severity,
                    "category": item.category,
                    "name": item.name,
                    "expected": item.expected,
                    "actual": item.actual,
                    "message": item.message,
                }
                for item in self.findings
            ],
        }


# ============================================================
# REGISTRY / REFEREE
# ============================================================

class ArchitectureRegistry:

    def __init__(self):
        # Independent reference state. Must not alias live module dicts.
        self.capabilities = dict(CANONICAL_CAPABILITIES)
        self.message_requirements = dict(CANONICAL_MESSAGE_REQUIREMENTS)
        self.protocol_message_types = set(CANONICAL_PROTOCOL_MESSAGE_TYPES)
        self.constants = dict(FROZEN_CONSTANTS)
        self.modules = dict(MODULES)
        self.open_decisions = dict(OPEN_DECISIONS)

    # --------------------------------------------------------
    # Reference-state helpers
    # --------------------------------------------------------

    def capability_exists(self, name):
        return name in self.capabilities

    def capability_enabled(self, name):
        return bool(self.capabilities.get(name, False))

    def required_capability(self, message_type):
        return self.message_requirements.get(message_type)

    def message_allowed(self, message_type):
        capability = self.required_capability(message_type)
        if capability is None:
            return False
        return self.capability_enabled(capability)

    def fingerprint(self):
        payload = {
            "version": ARCHITECTURE_VERSION,
            "capabilities": self.capabilities,
            "message_requirements": self.message_requirements,
            "protocol_message_types": sorted(self.protocol_message_types),
            "constants": self.constants,
            "modules": self.modules,
            "open_decisions": self.open_decisions,
        }
        encoded = json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    # --------------------------------------------------------
    # Live inspection
    # --------------------------------------------------------

    def inspect_live_system(self):
        from . import compatibility as compatibility_module
        from . import continuity as continuity_module
        from . import federation as federation_module
        from . import protocol as protocol_module
        from . import router as router_module
        from .codex_compare import compare_beliefs
        from .core import Evidence, EvidenceKernel

        live_modules = {
            path.stem: path.name
            for path in Path(__file__).resolve().parent.glob("*.py")
        }

        live_protocol_message_types = {
            protocol_module.create_observation_share(
                "source", {"content": "x"}
            ).message_type,
            protocol_module.create_evidence_request(
                "source", "concept"
            ).message_type,
            protocol_module.create_codex_update(
                "source", "concept", 0.5, []
            ).message_type,
        }

        live_constants = {
            "belief_neutral_value": EvidenceKernel().sigmoid(0),
            "decay_rate": inspect.signature(
                Evidence.decayed_weight
            ).parameters["decay_rate"].default,
            "remote_default_reliability": self._federation_default_reliability(
                federation_module
            ),
            "comparison_contradiction_gap": inspect.signature(
                compare_beliefs
            ).parameters["contradiction_threshold"].default,
            "comparison_confidence_gap": inspect.signature(
                compare_beliefs
            ).parameters["agreement_threshold"].default,
            "resolution_mutates_evidence": self._resolution_mutates_evidence(),
            "remote_confidence_mutates_local_belief": self._remote_confidence_mutates_local_belief(
                federation_module
            ),
            "watermark_mutates_belief": self._watermark_mutates_belief(
                continuity_module
            ),
            "watermark_bypasses_capability_gate": self._watermark_bypasses_capability_gate(
                continuity_module
            ),
        }

        live_state = {
            "version": ARCHITECTURE_VERSION,
            "capabilities": dict(compatibility_module.DEFAULT_CAPABILITIES),
            "message_requirements": dict(router_module.MESSAGE_REQUIREMENTS),
            "protocol_message_types": sorted(live_protocol_message_types),
            "modules": live_modules,
            "constants": live_constants,
        }

        encoded = json.dumps(
            live_state,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")

        return live_state, hashlib.sha256(encoded).hexdigest()

    def _federation_default_reliability(self, federation_module):
        source = inspect.getsource(
            federation_module.FederationAdapter.receive_observation
        )
        if "reliability=0.5" in source:
            return 0.5
        return None

    def _remote_confidence_mutates_local_belief(self, federation_module):
        source = inspect.getsource(
            federation_module.FederationAdapter.receive_observation
        )
        return "reliability=payload.get(\"confidence\"" in source

    def _watermark_mutates_belief(self, continuity_module):
        # Structural guarantee: none of the continuity module's public
        # functions may touch belief/evidence/observation mutation
        # APIs. Checked by source inspection rather than trusting a
        # docstring claim.
        forbidden = ("add_evidence(", ".belief(", "observe(", "resolve(")
        for name in ("local_watermark", "parse_remote_watermark", "compare_watermarks"):
            source = inspect.getsource(getattr(continuity_module, name))
            if any(token in source for token in forbidden):
                return True
        return False

    def _watermark_bypasses_capability_gate(self, continuity_module):
        # Structural guarantee: compare_watermarks must never itself
        # decide capability/message-gate outcomes -- it only ever
        # returns a ContinuityResult, and never imports can_exchange
        # or router.MESSAGE_REQUIREMENTS.
        module_source = inspect.getsource(continuity_module)
        if "can_exchange" in module_source or "MESSAGE_REQUIREMENTS" in module_source:
            return True
        return False

    def _resolution_mutates_evidence(self):
        from .core import EvidenceKernel

        source = inspect.getsource(EvidenceKernel.resolve)
        return (
            ".evidence.append(" in source
            or ".observations[" in source
            or "add_evidence(" in source
        )

    # --------------------------------------------------------
    # Drift detection
    # --------------------------------------------------------

    def compare_capabilities(self, live):
        findings = []
        live = dict(live)

        for name, expected in self.capabilities.items():
            if name not in live:
                findings.append(Finding(
                    "ERROR",
                    "capability_drift",
                    name,
                    expected,
                    "<missing>",
                ))
                continue

            if bool(live[name]) != bool(expected):
                findings.append(Finding(
                    "ERROR",
                    "capability_drift",
                    name,
                    expected,
                    bool(live[name]),
                ))

        for name, actual in live.items():
            if name not in self.capabilities:
                findings.append(Finding(
                    "WARNING",
                    "capability_drift",
                    name,
                    "<unexpected>",
                    actual,
                ))

        return findings

    def compare_message_requirements(self, live):
        findings = []
        live = dict(live)

        for message_type, expected in self.message_requirements.items():
            if message_type not in live:
                findings.append(Finding(
                    "ERROR",
                    "message_requirement_drift",
                    message_type,
                    expected,
                    "<missing>",
                ))
                continue

            if live[message_type] != expected:
                findings.append(Finding(
                    "ERROR",
                    "message_requirement_drift",
                    message_type,
                    expected,
                    live[message_type],
                ))

        for message_type, actual in live.items():
            if message_type not in self.message_requirements:
                findings.append(Finding(
                    "WARNING",
                    "message_requirement_drift",
                    message_type,
                    "<unexpected>",
                    actual,
                ))

        return findings

    def compare_protocol_message_types(self, live):
        findings = []
        live = set(live)

        for message_type in sorted(self.protocol_message_types):
            if message_type not in live:
                findings.append(Finding(
                    "ERROR",
                    "protocol_drift",
                    message_type,
                    "present",
                    "<missing>",
                ))

        for message_type in sorted(live):
            if message_type not in self.protocol_message_types:
                findings.append(Finding(
                    "WARNING",
                    "protocol_drift",
                    message_type,
                    "<unexpected>",
                    "present",
                ))

        return findings

    def compare_modules(self, live):
        findings = []
        live = dict(live)

        for module_name in sorted(self.modules):
            if module_name not in live:
                findings.append(Finding(
                    "ERROR",
                    "module_drift",
                    module_name,
                    "present",
                    "<missing>",
                ))

        for module_name in sorted(live):
            if module_name not in self.modules:
                findings.append(Finding(
                    "WARNING",
                    "module_drift",
                    module_name,
                    "<unexpected>",
                    "present",
                ))

        return findings

    def compare_constants(self, live):
        findings = []
        live = dict(live)

        for constant_name, expected in self.constants.items():
            if constant_name not in live:
                findings.append(Finding(
                    "ERROR",
                    "frozen_constant_drift",
                    constant_name,
                    expected,
                    "<missing>",
                ))
                continue

            if live[constant_name] != expected:
                findings.append(Finding(
                    "ERROR",
                    "frozen_constant_drift",
                    constant_name,
                    expected,
                    live[constant_name],
                ))

        for constant_name, actual in live.items():
            if constant_name not in self.constants:
                findings.append(Finding(
                    "WARNING",
                    "frozen_constant_drift",
                    constant_name,
                    "<unexpected>",
                    actual,
                ))

        return findings

    def validate_reference(self):
        findings = []

        for message_type, capability in self.message_requirements.items():
            if capability not in self.capabilities:
                findings.append(Finding(
                    "ERROR",
                    "message_requirement_drift",
                    message_type,
                    "known capability",
                    capability,
                ))

        if self.capabilities.get("codex_update") is not False:
            findings.append(Finding(
                "ERROR",
                "trust_invariant",
                "codex_update",
                False,
                self.capabilities.get("codex_update"),
            ))

        if self.constants.get("remote_confidence_mutates_local_belief") is not False:
            findings.append(Finding(
                "ERROR",
                "trust_invariant",
                "remote_confidence_mutates_local_belief",
                False,
                self.constants.get("remote_confidence_mutates_local_belief"),
            ))

        if self.constants.get("watermark_mutates_belief") is not False:
            findings.append(Finding(
                "ERROR",
                "trust_invariant",
                "watermark_mutates_belief",
                False,
                self.constants.get("watermark_mutates_belief"),
            ))

        if self.constants.get("watermark_bypasses_capability_gate") is not False:
            findings.append(Finding(
                "ERROR",
                "trust_invariant",
                "watermark_bypasses_capability_gate",
                False,
                self.constants.get("watermark_bypasses_capability_gate"),
            ))

        return findings

    def validate_open_decisions(self):
        return [
            Finding(
                "INFO",
                "open_decision",
                name,
                "unresolved",
                description,
            )
            for name, description in self.open_decisions.items()
        ]

    # --------------------------------------------------------
    # Full referee pass
    # --------------------------------------------------------

    def validate(self):
        live_state, live_fingerprint = self.inspect_live_system()

        findings = []
        findings.extend(self.validate_reference())
        findings.extend(self.compare_capabilities(live_state["capabilities"]))
        findings.extend(self.compare_message_requirements(live_state["message_requirements"]))
        findings.extend(self.compare_protocol_message_types(live_state["protocol_message_types"]))
        findings.extend(self.compare_modules(live_state["modules"]))
        findings.extend(self.compare_constants(live_state["constants"]))

        # Structural trust invariants in the live implementation.
        if live_state["capabilities"].get("codex_update") is not False:
            findings.append(Finding(
                "ERROR",
                "trust_invariant",
                "codex_update",
                False,
                live_state["capabilities"].get("codex_update"),
            ))

        if live_state["constants"].get("remote_confidence_mutates_local_belief") is not False:
            findings.append(Finding(
                "ERROR",
                "trust_invariant",
                "remote_confidence_mutates_local_belief",
                False,
                live_state["constants"].get("remote_confidence_mutates_local_belief"),
            ))

        if live_state["constants"].get("watermark_mutates_belief") is not False:
            findings.append(Finding(
                "ERROR",
                "trust_invariant",
                "watermark_mutates_belief",
                False,
                live_state["constants"].get("watermark_mutates_belief"),
            ))

        if live_state["constants"].get("watermark_bypasses_capability_gate") is not False:
            findings.append(Finding(
                "ERROR",
                "trust_invariant",
                "watermark_bypasses_capability_gate",
                False,
                live_state["constants"].get("watermark_bypasses_capability_gate"),
            ))

        findings.extend(self.validate_open_decisions())

        return ArchitectureReport(
            findings=findings,
            reference_fingerprint=self.fingerprint(),
            live_fingerprint=live_fingerprint,
        )

    # --------------------------------------------------------
    # Snapshot / status
    # --------------------------------------------------------

    def snapshot(self):
        live_state, live_fingerprint = self.inspect_live_system()
        return {
            "architecture_version": ARCHITECTURE_VERSION,
            "capabilities": dict(self.capabilities),
            "message_requirements": dict(self.message_requirements),
            "protocol_message_types": sorted(self.protocol_message_types),
            "constants": dict(self.constants),
            "modules": dict(self.modules),
            "open_decisions": dict(self.open_decisions),
            "fingerprint": self.fingerprint(),
            "live_fingerprint": live_fingerprint,
            "live_state": live_state,
        }


# ============================================================
# SINGLE REGISTRY INSTANCE
# ============================================================

REGISTRY = ArchitectureRegistry()


def architecture_status():
    report = REGISTRY.validate()
    return {
        "version": ARCHITECTURE_VERSION,
        "healthy": report.healthy,
        "errors": [item.message for item in report.errors()],
        "warnings": [item.message for item in report.warnings()],
        "reference_fingerprint": report.reference_fingerprint,
        "live_fingerprint": report.live_fingerprint,
    }


# ============================================================
# SELF CHECK
# ============================================================

if __name__ == "__main__":
    print(json.dumps(architecture_status(), indent=2, sort_keys=True))
