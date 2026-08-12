"""RealityBoundary: separates INTENT -> DECISION -> AUTHORIZATION -> ACTION
-> RESULT for anything that touches the external world (a tool call, a
real network request, a real file write outside the harness's own data
directory).

This is a NEW component (not present in Lantern v0.84, not present in
prior harness turns). It does not duplicate lantern_harness.tools.boundary
.ToolBoundary (which owns discovery/authorization for registered tools) or
lantern_harness.decision_state_machine.DecisionStateMachine (which owns
state/recommendation). RealityBoundary sits downstream of both: it takes
an already-made DecisionReading and an already-authorized-or-not
ToolBoundary decision, and produces one single auditable record of what
was actually attempted and what actually happened.

Hard rule enforced by this module, not just documented: a simulated
action's ActionRecord can never have result_status="SUCCESS" with
execution_mode="REAL". Simulation and reality are mutually exclusive
fields on every record this module produces, so a simulated result can
never be silently read as "this really happened".
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from .decision_state_machine import DecisionReading


EXECUTION_MODE_REAL = "REAL"
EXECUTION_MODE_SIMULATED = "SIMULATED"
EXECUTION_MODE_NOT_EXECUTED = "NOT_EXECUTED"

RESULT_SUCCESS = "SUCCESS"
RESULT_ERROR = "ERROR"
RESULT_DENIED = "DENIED"
RESULT_NOT_EXECUTED = "NOT_EXECUTED"
RESULT_SIMULATED = "SIMULATED_ONLY"


@dataclass(frozen=True)
class ActionProposal:
    """INTENT + DECISION, before any authorization or action is attempted.

    Producing a proposal never touches the external world and never
    authorizes anything -- it is a record of what is being considered.
    """

    intent: str
    decision_state: str
    decision_action: str
    authorization_required: bool
    tool_name: Optional[str]
    inputs: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "intent": self.intent,
            "decision_state": self.decision_state,
            "decision_action": self.decision_action,
            "authorization_required": self.authorization_required,
            "tool_name": self.tool_name,
            "inputs": dict(self.inputs),
        }


@dataclass(frozen=True)
class ActionRecord:
    """What actually happened. This is the only object in this module
    that is allowed to describe a real or simulated outcome."""

    proposal: ActionProposal
    authorization_status: str  # "AUTHORIZED" | "DENIED" | "NOT_REQUESTED"
    execution_mode: str  # REAL | SIMULATED | NOT_EXECUTED
    result_status: str  # SUCCESS | ERROR | DENIED | NOT_EXECUTED | SIMULATED_ONLY
    result: Any = None
    error: Optional[str] = None
    notes: tuple = field(default_factory=tuple)

    def to_dict(self) -> dict:
        return {
            "proposal": self.proposal.to_dict(),
            "authorization_status": self.authorization_status,
            "execution_mode": self.execution_mode,
            "result_status": self.result_status,
            "result": self.result,
            "error": self.error,
            "notes": list(self.notes),
        }

    def is_real_success(self) -> bool:
        """The ONLY combination that means 'this actually happened in the
        external world and succeeded'. Callers deciding whether to treat
        a result as real should call this, not inspect result_status
        alone (a SIMULATED_ONLY record is never a real success, no
        matter what the simulated payload contains)."""
        return self.execution_mode == EXECUTION_MODE_REAL and self.result_status == RESULT_SUCCESS


class RealityBoundary:
    """Owns exactly one thing: the INTENT -> DECISION -> AUTHORIZATION ->
    ACTION -> RESULT sequence, and an honest record of it. It does not
    compute confidence (ConfidenceField), does not decide state
    (DecisionStateMachine), and does not own tool authorization
    (ToolBoundary) -- it calls into those and records what happened.
    """

    def propose(
        self,
        *,
        intent: str,
        decision: DecisionReading,
        tool_name: Optional[str] = None,
        inputs: Optional[dict] = None,
    ) -> ActionProposal:
        if not intent or not intent.strip():
            raise ValueError("intent must be a non-empty string")
        return ActionProposal(
            intent=intent.strip(),
            decision_state=decision.state,
            decision_action=decision.recommended_action,
            authorization_required=decision.authorization_required,
            tool_name=tool_name,
            inputs=dict(inputs or {}),
        )

    def act(self, proposal: ActionProposal, tool_boundary, **kwargs) -> ActionRecord:
        """Attempt the real action through the caller's ToolBoundary.
        Requires an explicit, already-authorized tool_name on the
        proposal -- this method never authorizes anything itself."""
        if proposal.tool_name is None:
            return ActionRecord(
                proposal=proposal,
                authorization_status="NOT_REQUESTED",
                execution_mode=EXECUTION_MODE_NOT_EXECUTED,
                result_status=RESULT_NOT_EXECUTED,
                notes=("no tool_name on proposal; nothing to execute",),
            )

        if not tool_boundary.is_authorized(proposal.tool_name):
            return ActionRecord(
                proposal=proposal,
                authorization_status="DENIED",
                execution_mode=EXECUTION_MODE_NOT_EXECUTED,
                result_status=RESULT_DENIED,
                notes=("tool %r is not authorized in ToolBoundary" % proposal.tool_name,),
            )

        tool_result = tool_boundary.execute(proposal.tool_name, **kwargs)
        if tool_result.status == "EXECUTED":
            return ActionRecord(
                proposal=proposal,
                authorization_status="AUTHORIZED",
                execution_mode=EXECUTION_MODE_REAL,
                result_status=RESULT_SUCCESS,
                result=tool_result.output,
            )
        return ActionRecord(
            proposal=proposal,
            authorization_status="AUTHORIZED",
            execution_mode=EXECUTION_MODE_REAL,
            result_status=RESULT_ERROR if tool_result.status == "ERROR" else RESULT_DENIED,
            error=tool_result.error,
        )

    def simulate(self, proposal: ActionProposal, hypothetical_result: Any, *, reason: str) -> ActionRecord:
        """Explicitly produce a labeled SIMULATED record -- e.g. for
        planning ('if this tool existed and were authorized, here is what
        the call would look like') without ever calling anything real.
        result_status is always SIMULATED_ONLY, never SUCCESS, so this
        can never be mistaken for a real external-world result."""
        if not reason or not reason.strip():
            raise ValueError("simulate() requires a non-empty reason")
        return ActionRecord(
            proposal=proposal,
            authorization_status="NOT_REQUESTED",
            execution_mode=EXECUTION_MODE_SIMULATED,
            result_status=RESULT_SIMULATED,
            result=hypothetical_result,
            notes=("SIMULATED_BY_ASSISTANT: " + reason.strip(),),
        )
