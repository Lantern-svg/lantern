"""Self-Model: a bounded, read-only description of the harness's current
state and capabilities. NEW component; not present in Lantern v0.84 or
in prior harness turns.

This module answers exactly one question, honestly: "what does this
system currently know about itself?" It distinguishes:

    WHAT I KNOW               -- verified from real Lantern/harness state
    WHAT I INFER               -- derived, not directly observed
    WHAT I DO NOT KNOW         -- explicitly unknown, not guessed
    WHAT I CAN DO               -- capabilities that actually exist and work
    WHAT I CANNOT DO            -- capabilities that do not exist (honest gaps)
    WHAT I AM AUTHORIZED TO DO  -- always sourced from ToolBoundary.is_authorized(),
                                    never inferred or assumed
    WHAT REQUIRES OPERATOR ACTION -- explicit list of standing external
                                      boundaries (push, publish, payment, etc.)

Hard rule: SelfModel.describe() never grants authority. It can only
*report* what ToolBoundary/DecisionStateMachine/RealityBoundary already
say is true. There is no code path in this module that sets
is_authorized=True or otherwise changes any other component's state --
verified by test_self_model.py's test_self_model_is_read_only and
test_self_model_cannot_self_authorize.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from .bridge import LanternBridge


KNOWN_CAPABILITIES = (
    "observe (record an Observation into the real EvidenceKernel)",
    "add_evidence (link Evidence to a concept, real EvidenceKernel)",
    "detect and read contradictions (real EvidenceKernel.detect_contradiction)",
    "resolve contradictions (real EvidenceKernel resolution path)",
    "compute belief (real EvidenceKernel.belief sigmoid scoring)",
    "compile a structured prompt (PromptCompiler)",
    "compare independent perspectives (PerspectiveDifferentialEngine, variance only, no voting)",
    "compute a read-only confidence reading (ConfidenceField)",
    "recommend (not authorize) a decision state (DecisionStateMachine)",
    "open/link/abandon exploratory branches (spine.BranchStore)",
    "commit a branch into the Spine, only with explicit external authorization (spine.SpineCommitter)",
    "record real vs. simulated external actions (RealityBoundary)",
    "verify Chronicle integrity (real Chronicle.verify() hash-chain check)",
    "create and persist Scars (real Lantern.create_scar/persist_scar)",
    "remember capability-scope permission grants and combine them with an alignment result "
    "(PermissionAuthority) -- in-process memory only, never persisted, never self-granted",
)

KNOWN_GAPS = (
    "full Perspective Mesh (merge/vote/consensus across perspectives) -- only variance computation exists",
    "autonomous self-modification of Lantern core or the harness's own source",
    "unrestricted autonomous promotion (posting/contacting/publishing without a boundary check)",
    "a live, credentialed payment settlement path (x402 facilitator + wallet are not configured)",
    "PyPI package publication (no publishing credentials present, and a "
    "verified-empty local build/install test found a deeper blocker: no "
    "declared dependency on Lantern core, which is itself unpublished, "
    "plus prompts/ and config/ are not reachable by an installed wheel's "
    "Path(__file__)-relative lookups -- see RELEASE.md)",
    "pushing commits to a public git remote without a separate explicit authorization step",
)

STANDING_OPERATOR_BOUNDARIES = (
    "push commits to origin/any public remote",
    "publish a package to PyPI or any package index",
    "configure or use real payment/wallet credentials",
    "sign any contract, license grant, or legal commitment",
    "contact external parties/platforms on the operator's behalf",
    "install or run services that expose network ports beyond localhost",
)


@dataclass(frozen=True)
class SelfModelReading:
    what_i_know: tuple
    what_i_infer: tuple
    what_i_do_not_know: tuple
    what_i_can_do: tuple
    what_i_cannot_do: tuple
    what_i_am_authorized_to_do: tuple
    what_requires_operator_action: tuple
    notes: tuple = field(default_factory=tuple)

    def to_dict(self) -> dict:
        return {
            "what_i_know": list(self.what_i_know),
            "what_i_infer": list(self.what_i_infer),
            "what_i_do_not_know": list(self.what_i_do_not_know),
            "what_i_can_do": list(self.what_i_can_do),
            "what_i_cannot_do": list(self.what_i_cannot_do),
            "what_i_am_authorized_to_do": list(self.what_i_am_authorized_to_do),
            "what_requires_operator_action": list(self.what_requires_operator_action),
            "notes": list(self.notes),
        }

    def format(self) -> str:
        lines = ["SELF-MODEL"]
        sections = [
            ("WHAT I KNOW", self.what_i_know),
            ("WHAT I INFER", self.what_i_infer),
            ("WHAT I DO NOT KNOW", self.what_i_do_not_know),
            ("WHAT I CAN DO", self.what_i_can_do),
            ("WHAT I CANNOT DO", self.what_i_cannot_do),
            ("WHAT I AM AUTHORIZED TO DO", self.what_i_am_authorized_to_do),
            ("WHAT REQUIRES OPERATOR ACTION", self.what_requires_operator_action),
        ]
        for title, items in sections:
            lines.append("")
            lines.append(f"{title}:")
            if not items:
                lines.append("  (none)")
            for item in items:
                lines.append(f"  - {item}")
        return "\n".join(lines)


class SelfModel:
    """Reads existing harness/Lantern state and reports it. Produces no
    side effects on any other component -- see module docstring."""

    def __init__(self, bridge: LanternBridge, tool_boundary):
        self.bridge = bridge
        self.tool_boundary = tool_boundary

    def describe(self) -> SelfModelReading:
        identity = self.bridge.identity_status()
        integrity = self.bridge.witness_integrity()
        status = self.bridge.status()

        what_i_know = [
            f"node identity status={identity.get('status')}",
            f"Chronicle integrity={integrity.get('status')}",
            f"memory: step={status.get('step')}, observations={status.get('observations')}, "
            f"evidence={status.get('evidence')}, contradictions={status.get('contradictions')}",
        ]

        what_i_infer = []
        if integrity.get("status") == "NO_CHRONICLE":
            what_i_infer.append(
                "no Chronicle file exists yet for this data_dir -- inferred to mean this is a fresh, unused node, "
                "not verified against any external record"
            )
        if status.get("contradictions", 0) and status.get("contradictions", 0) > 0:
            what_i_infer.append(
                f"presence of {status.get('contradictions')} contradiction(s) suggests at least one concept "
                f"has conflicting evidence -- which concept(s) is not inferred here, read EvidenceKernel directly"
            )

        what_i_do_not_know = [
            "whether any reasoning engine response was independently verified as true (only that it was returned)",
            "whether any external user has adopted, paid for, or benefited from this system (no such record exists)",
            "anything about conditions outside the data this bridge has actually observed",
        ]

        what_i_can_do = list(KNOWN_CAPABILITIES)
        what_i_cannot_do = list(KNOWN_GAPS)

        authorized_tools = sorted(self.tool_boundary._authorized)  # noqa: SLF001 - read-only self-report
        what_i_am_authorized_to_do = (
            [f"tool: {name}" for name in authorized_tools]
            if authorized_tools
            else ["(no tools are currently authorized in ToolBoundary)"]
        )

        return SelfModelReading(
            what_i_know=tuple(what_i_know),
            what_i_infer=tuple(what_i_infer),
            what_i_do_not_know=tuple(what_i_do_not_know),
            what_i_can_do=tuple(what_i_can_do),
            what_i_cannot_do=tuple(what_i_cannot_do),
            what_i_am_authorized_to_do=tuple(what_i_am_authorized_to_do),
            what_requires_operator_action=STANDING_OPERATOR_BOUNDARIES,
            notes=(
                "This model reports what ToolBoundary/Chronicle/EvidenceKernel already say; "
                "it has no method that sets authorization state on any other component.",
            ),
        )
