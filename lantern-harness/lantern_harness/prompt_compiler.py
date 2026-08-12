"""PromptCompiler: turns an ordinary user request into a structured
reasoning prompt for a downstream reasoning engine.

This is a NEW component (not present in Lantern v0.84, not present in
prior harness turns). It is not a Perspective Mesh, Confidence Field,
Decision State Machine, or Spine -- it does not decide, validate, or
commit anything. It organizes what is already known (real Evidence /
Observation / Contradiction records read through LanternBridge, when
supplied) and marks everything it was not given as NOT_PROVIDED rather
than inventing it.

Scaling: a request gets the full structured template only when it looks
consequential (heuristic, see _looks_consequential -- this is INFERRED,
not a validated classifier, and callers can override it). Otherwise it
gets a short template. Either way, no field is fabricated: fields with
no real backing data say so explicitly using one of the markers in
FieldStatus.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional


class FieldStatus:
    """Markers a compiled field may carry instead of fabricated content."""

    NOT_PROVIDED = "NOT_PROVIDED"
    UNKNOWN = "UNKNOWN"
    UNVERIFIED = "UNVERIFIED"
    INFERRED = "INFERRED"
    BLOCKED = "BLOCKED"


_PROVE_PATTERN = re.compile(
    r"\bproves?\b.{0,40}\b(correct|true|right|works?|valid)\b", re.IGNORECASE
)

_CONSEQUENTIAL_KEYWORDS = (
    "prove", "decide", "commit", "policy", "irreversible", "production",
    "delete", "publish", "legal", "financial", "medical", "safety",
    "contract", "launch", "deploy", "acquire", "merge", "terminate",
)


def _looks_consequential(user_request: str) -> bool:
    lowered = user_request.lower()
    return any(kw in lowered for kw in _CONSEQUENTIAL_KEYWORDS)


@dataclass
class CompiledPrompt:
    mode: str  # "lightweight" | "heavyweight"
    fields: dict = field(default_factory=dict)
    text: str = ""
    notes: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"mode": self.mode, "fields": self.fields, "text": self.text, "notes": self.notes}


class PromptCompiler:
    """Compiles user requests into structured prompts.

    `bridge`, if supplied, is a real lantern_harness.bridge.LanternBridge
    -- used only to read existing Evidence/Observation/Contradiction
    records for `concept` (if given). The compiler never writes to
    Lantern; it is read-only, same discipline as Compass.
    """

    def __init__(self, bridge=None):
        self.bridge = bridge

    def compile(
        self,
        user_request: str,
        *,
        concept: Optional[str] = None,
        consequential: Optional[bool] = None,
        constraints: Optional[list] = None,
        authorization: Optional[list] = None,
        assumptions: Optional[list] = None,
        uncertainties: Optional[list] = None,
        alternative_explanations: Optional[list] = None,
        alternatives_to_action: Optional[list] = None,
        validation_requirements: Optional[list] = None,
        desired_output: Optional[str] = None,
    ) -> CompiledPrompt:
        if not user_request or not user_request.strip():
            raise ValueError("user_request must be a non-empty string")

        notes = []

        task = user_request.strip()
        prove_match = _PROVE_PATTERN.search(user_request)
        if prove_match:
            task = (
                f"Determine whether the following is true (do not assume it going in): "
                f"{user_request.strip()}"
            )
            notes.append(
                "TASK reframed: input matched a truth-presupposing 'prove X' pattern; "
                "converted to an investigation request rather than assuming the "
                "requested conclusion. Original request preserved verbatim below."
            )

        if consequential is None:
            consequential = _looks_consequential(user_request)
            notes.append(
                f"consequential={consequential} determined by keyword heuristic "
                f"(INFERRED, not a validated classifier) -- pass consequential=True/False "
                f"explicitly to override."
            )
        mode = "heavyweight" if consequential else "lightweight"

        known_evidence, observations, contradictions, evidence_note = self._read_bridge_state(concept)
        if evidence_note:
            notes.append(evidence_note)

        fields = {
            "USER_INTENT": user_request.strip(),
            "TASK": task,
            "DESIRED_OUTPUT": desired_output or self._default_desired_output(mode),
            "EPISTEMIC_STATUS": self._epistemic_status(mode, bool(prove_match), concept),
        }

        if mode == "heavyweight":
            fields.update({
                "KNOWN_EVIDENCE": known_evidence,
                "OBSERVATIONS": observations,
                "ASSUMPTIONS": assumptions if assumptions else FieldStatus.NOT_PROVIDED,
                "UNCERTAINTIES": uncertainties if uncertainties else FieldStatus.NOT_PROVIDED,
                "CONTRADICTIONS": contradictions,
                "ALTERNATIVE_EXPLANATIONS": alternative_explanations if alternative_explanations else FieldStatus.NOT_PROVIDED,
                "ALTERNATIVES_TO_ACTION": alternatives_to_action if alternatives_to_action else FieldStatus.NOT_PROVIDED,
                "CONSTRAINTS": constraints if constraints else FieldStatus.NOT_PROVIDED,
                "AUTHORIZATION": authorization if authorization else FieldStatus.NOT_PROVIDED,
                "VALIDATION_REQUIREMENTS": validation_requirements if validation_requirements else FieldStatus.NOT_PROVIDED,
            })
        else:
            # Lightweight mode still surfaces evidence/contradictions if the
            # bridge actually had real data for this concept -- scaling down
            # means fewer *empty* fields shown, not hiding real data that exists.
            if known_evidence != FieldStatus.NOT_PROVIDED:
                fields["KNOWN_EVIDENCE"] = known_evidence
            if contradictions != FieldStatus.NOT_PROVIDED:
                fields["CONTRADICTIONS"] = contradictions
            if constraints:
                fields["CONSTRAINTS"] = constraints
            if authorization:
                fields["AUTHORIZATION"] = authorization

        text = self._render(mode, fields)
        return CompiledPrompt(mode=mode, fields=fields, text=text, notes=notes)

    def _read_bridge_state(self, concept: Optional[str]):
        if self.bridge is None or concept is None:
            return (
                FieldStatus.NOT_PROVIDED,
                FieldStatus.NOT_PROVIDED,
                FieldStatus.NOT_PROVIDED,
                "no bridge/concept supplied -- KNOWN_EVIDENCE/OBSERVATIONS/CONTRADICTIONS "
                "are NOT_PROVIDED, not fabricated.",
            )

        integrity = self.bridge.witness_integrity()
        if integrity.get("status") not in ("VALID", "NO_CHRONICLE"):
            return (
                FieldStatus.BLOCKED,
                FieldStatus.BLOCKED,
                FieldStatus.BLOCKED,
                f"witness_integrity()={integrity.get('status')!r} -- refusing to read "
                f"EvidenceKernel state through a chain that failed its own integrity "
                f"check. Fields marked BLOCKED, not silently trusted.",
            )

        kernel = self.bridge.lantern.kernel
        concept_evidence = [e for e in kernel.evidence if e.concept == concept]
        if not concept_evidence:
            return (
                FieldStatus.UNKNOWN,
                FieldStatus.UNKNOWN,
                FieldStatus.UNKNOWN,
                f"bridge/concept supplied (concept={concept!r}) but EvidenceKernel has no "
                f"evidence recorded for it yet -- fields marked UNKNOWN, not fabricated.",
            )

        known_evidence = [
            {
                "concept": e.concept,
                "weight": e.weight,
                "sign": e.sign,
                "step": e.step,
                "source_observation_id": e.observation_id,
            }
            for e in concept_evidence
        ]
        observations = [
            {
                "id": obs_id,
                "content": obs.content,
                "source": obs.source,
                "reliability": obs.reliability,
            }
            for obs_id, obs in kernel.observations.items()
            if any(e.observation_id == obs_id for e in concept_evidence)
        ]
        open_contradictions = [
            {
                "id": c.id,
                "concept": c.concept,
                "current_severity": c.current_severity,
                "status": c.status,
            }
            for c in kernel.contradictions
            if c.concept == concept
        ]
        contradictions = open_contradictions if open_contradictions else FieldStatus.UNKNOWN

        return (
            known_evidence,
            observations,
            contradictions,
            f"KNOWN_EVIDENCE/OBSERVATIONS read from live EvidenceKernel for concept={concept!r} "
            f"({len(concept_evidence)} evidence record(s)) -- real data, not simulated.",
        )

    @staticmethod
    def _default_desired_output(mode: str) -> str:
        if mode == "heavyweight":
            return (
                "Evidence Summary / Assumptions Made / Contradicting Evidence / "
                "Alternatives Considered / Conclusion / Confidence Level / "
                "What Would Change This Conclusion."
            )
        return "A direct answer, with any assumptions made stated explicitly."

    @staticmethod
    def _epistemic_status(mode: str, was_reframed: bool, concept: Optional[str]) -> list:
        status = [f"mode={mode}"]
        if was_reframed:
            status.append("task_reframed_from_truth_presupposing_request=true")
        status.append(
            f"evidence_source={'live EvidenceKernel concept=' + repr(concept) if concept else 'none (NOT_PROVIDED)'}"
        )
        status.append(
            "downstream model output is an OBSERVATION about what the model said, "
            "not verified truth, until independently validated"
        )
        return status

    @staticmethod
    def _render(mode: str, fields: dict) -> str:
        lines = ["INVESTIGATION REQUEST" if mode == "heavyweight" else "REQUEST"]
        for key, value in fields.items():
            lines.append("")
            lines.append(f"{key}:")
            if isinstance(value, list):
                if not value:
                    lines.append(f"  {FieldStatus.NOT_PROVIDED}")
                else:
                    for item in value:
                        lines.append(f"  - {item}")
            else:
                lines.append(f"  {value}")
        if mode == "heavyweight":
            lines.append("")
            lines.append("INSTRUCTIONS TO THE INVESTIGATING MODEL:")
            lines.append("  1. Separate evidence from interpretation from assumption from conclusion.")
            lines.append("  2. Actively look for what would disprove the leading hypothesis, not only what supports it.")
            lines.append("  3. Do not treat your own confidence, fluency, or agreement with yourself as evidence.")
            lines.append("  4. Do not treat semantic similarity between claims as equivalence.")
            lines.append("  5. Label any claim that cannot be independently verified as UNVERIFIED.")
            lines.append("  6. State a final confidence level and what would change it.")
        return "\n".join(lines)
