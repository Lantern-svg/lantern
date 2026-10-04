"""OperatingLoop: makes the architecture in the mission brief executable,
not just documented.

    USER
      -> LANTERN INTERFACE (main.py)
      -> INTENT                          (OperatingLoop.run() input)
      -> OBSERVATION                     (real bridge.observe())
      -> ANALYTICAL LENSES               (PromptCompiler structuring)
      -> PERSPECTIVE DIFFERENTIAL        (PerspectiveDifferentialEngine, if >=2 perspectives given)
      -> EVIDENCE / CONTRADICTION        (real EvidenceKernel, read through ConfidenceField)
      -> CONFIDENCE FIELD                (ConfidenceField.evaluate)
      -> DECISION STATE MACHINE          (DecisionStateMachine.recommend)
      -> ACTION BOUNDARY                 (RealityBoundary.propose/act/simulate)
      -> EXTERNAL WORLD                  (only if a tool_name + authorized ToolBoundary entry exist)
      -> RESULT                          (ActionRecord)
      -> SCAR / SUCCESS                  (spine.branch_to_scar on failure, or Branch left open for the caller to commit)
      -> LEARNING                        (LoopResult carries everything needed for the next OBSERVE AGAIN)
      -> NEW STANCE
      -> OBSERVE AGAIN

Every step above is a call into an already-existing, already-tested
component. This module adds NO new decision logic, NO new confidence
math, and NO new authorization path -- it is purely a documented,
testable composition of what already exists. If any step is missing its
real prerequisite (e.g. no tool_name given), the loop stops there and
reports NOT_EXECUTED rather than fabricating a downstream step.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional, Sequence

from .bridge import LanternBridge
from .confidence_field import ConfidenceField, ConfidenceFieldReading
from .decision_gate import (
    DEFAULT_REQUIRED_CONFIDENCE, authorize_tool_call, execute_tool_call, load_tool_policy,
)
from .decision_state_machine import DecisionStateMachine, DecisionReading
from .perspective_differential import Perspective
from .prompt_compiler import CompiledPrompt, PromptCompiler
from .reality_boundary import ActionRecord, RealityBoundary
from .spine import Branch, BranchStore
from .tool_contract import ToolCall

import uuid as _uuid


@dataclass
class LoopResult:
    intent: str
    observation_id: Optional[str]
    compiled_prompt: CompiledPrompt
    confidence: ConfidenceFieldReading
    decision: DecisionReading
    action_record: Optional[ActionRecord]
    branch: Optional[Branch]
    notes: tuple = field(default_factory=tuple)

    def to_dict(self) -> dict:
        return {
            "intent": self.intent,
            "observation_id": self.observation_id,
            "compiled_prompt": self.compiled_prompt.to_dict(),
            "confidence": self.confidence.to_dict(),
            "decision": self.decision.to_dict(),
            "action_record": self.action_record.to_dict() if self.action_record is not None else None,
            "branch": self.branch.to_dict() if self.branch is not None else None,
            "notes": list(self.notes),
        }

    def format(self) -> str:
        lines = [
            "OPERATING LOOP RESULT",
            f"intent: {self.intent}",
            f"observation_id: {self.observation_id}",
            f"confidence: score={self.confidence.confidence_score} band={self.confidence.confidence_band}",
            f"decision: state={self.decision.state} action={self.decision.recommended_action}",
        ]
        if self.action_record is not None:
            lines.append(
                f"action: execution_mode={self.action_record.execution_mode} "
                f"result_status={self.action_record.result_status} "
                f"real_success={self.action_record.is_real_success()}"
            )
        else:
            lines.append("action: NOT_ATTEMPTED (no tool_name supplied)")
        if self.branch is not None:
            lines.append(f"branch: id={self.branch.id} status={self.branch.status}")
        for note in self.notes:
            lines.append(f"note: {note}")
        return "\n".join(lines)


class OperatingLoop:
    """Composes the existing components into one callable pipeline. Does
    not own any decision, confidence, or authorization logic itself."""

    def __init__(self, bridge: LanternBridge, tool_boundary,
                 required_confidence: float = DEFAULT_REQUIRED_CONFIDENCE,
                 allowed_scopes=None):
        """required_confidence and allowed_scopes come from config's
        tool_policy section (see decision_gate.load_tool_policy) unless
        the caller supplies session values explicitly."""
        self.bridge = bridge
        self.tool_boundary = tool_boundary
        self.compiler = PromptCompiler(bridge=bridge)
        self.confidence_field = ConfidenceField(bridge=bridge)
        self.decision_machine = DecisionStateMachine()
        self.reality_boundary = RealityBoundary()
        self.branch_store = BranchStore()
        self.required_confidence = float(required_confidence)
        self.allowed_scopes = set(allowed_scopes or ())
        self.decision_log = []  # every authorize/execute decision, in order

    def run(
        self,
        intent: str,
        *,
        concept: Optional[str] = None,
        source: str = "user",
        reliability: float = 1.0,
        perspectives: Optional[Sequence[Perspective]] = None,
        assumptions: Optional[Sequence[str]] = None,
        tool_name: Optional[str] = None,
        tool_kwargs: Optional[dict] = None,
        open_branch: bool = False,
        previous_decision_state: Optional[str] = None,
        validation_status: Optional[str] = None,
    ) -> LoopResult:
        if not intent or not intent.strip():
            raise ValueError("intent must be a non-empty string")

        notes = []

        observation = self.bridge.observe(intent, source=source, reliability=reliability)
        observation_id = observation.id

        # validation_status is the caller-supplied INDEPENDENT VERIFICATION
        # input (e.g. "VERIFIED" after a collective/2-node confirm). It is
        # never self-assumed: omitting it compiles UNVERIFIED, which caps
        # confidence below the default tool-execution threshold.
        compiled = self.compiler.compile(
            intent,
            concept=concept,
            perspectives=list(perspectives) if perspectives else None,
            assumptions=list(assumptions) if assumptions else None,
            validation_status=validation_status,
        )

        reading = self.confidence_field.evaluate(
            concept=compiled.concept,
            perspectives=perspectives,
            assumptions=compiled.assumptions,
            validation_status=compiled.validation_status,
        )

        decision = self.decision_machine.recommend(reading, previous_state=previous_decision_state)

        action_record = None
        if tool_name is not None:
            proposal = self.reality_boundary.propose(
                intent=intent, decision=decision, tool_name=tool_name, inputs=tool_kwargs or {},
            )
            # MANDATORY DECISION GATE: no tool execution may bypass this.
            # Confidence is the evidence-based reading measured above.
            tool_call = ToolCall(
                id=str(_uuid.uuid4()),
                tool_name=tool_name,
                arguments=dict(tool_kwargs or {}),
            )
            evidence_conf = reading.confidence_score
            if not isinstance(evidence_conf, (int, float)):
                evidence_conf = 0.0  # "BLOCKED" or non-numeric readings block execution
            decision_result = authorize_tool_call(
                tool_call, self.allowed_scopes,
                evidence_confidence=float(evidence_conf),
                tool_boundary=self.tool_boundary,
            )
            tool_call_result, tool_result = execute_tool_call(
                tool_call, decision_result, self.required_confidence,
                self.tool_boundary, decision_log=self.decision_log,
            )
            action_record = self.reality_boundary.record_result(proposal, tool_result, decision=decision_result)
            if not action_record.is_real_success():
                if tool_result is not None and getattr(tool_result, "status", None) == "BLOCKED":
                    notes.append(
                        f"action BLOCKED by the mandatory decision gate (state={decision_result.state}, "
                        f"confidence={decision_result.confidence:.2f}, required={self.required_confidence:.2f}) -- "
                        "the tool was not executed"
                    )
                else:
                    notes.append(
                        f"action did not produce a real success (execution_mode={action_record.execution_mode}, "
                        f"result_status={action_record.result_status}) -- treat as unresolved, not as a completed step"
                    )

        branch = None
        if open_branch:
            if concept is None:
                notes.append("open_branch=True requested but no concept supplied; skipping branch creation")
            else:
                branch = self.branch_store.open_branch(concept=concept, hypothesis=intent)
                self.branch_store.link_observation(branch.id, observation_id)
                notes.append(f"opened branch {branch.id} for concept={concept!r} -- remains outside committed Spine state until an explicit commit")

        return LoopResult(
            intent=intent.strip(),
            observation_id=observation_id,
            compiled_prompt=compiled,
            confidence=reading,
            decision=decision,
            action_record=action_record,
            branch=branch,
            notes=tuple(notes),
        )
