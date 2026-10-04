"""Model-driven tool pipeline: the full path from a reasoning provider's
response to a REAL tool, exactly one composition:

    reasoning provider
          |
          v
    tool call normalization      (reasoning/tool_calls.py -- adapter seam)
          |
          v
    tool registry                 (ToolBoundary -- registered + authorized)
          |
          v
    decision                      (evidence-based confidence vs required)
          |
          v
    authorization                 (authorize_tool_call -- scopes)
          |
          v
    execute_tool_call()           (decision_gate -- the ONLY execution path)
          |
          v
    REAL TOOL

Invariants enforced here (not in docstrings):
    - The provider NEVER sees tools outside the session's allowed scopes
      AND the registry: the visible ToolSpec list is the intersection of
      registered, boundary-authorized, and scope-permitted tools. If the
      model cannot see a tool, there is no spec to misuse.
    - Every model-proposed call is normalized through the adapter seam and
      must survive the strict ToolCall contract, or nothing executes.
    - A call for a tool the model was never shown is DENIED at the
      registry stage even if it parses.
    - evidence_confidence defaults to 0.0 (fail-closed): a session that
      brings no evidence cannot execute model-proposed tools.
    - Execution still goes through decision_gate.execute_tool_call(); this
      module adds NO new execution path.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Sequence

from .decision_gate import DEFAULT_REQUIRED_CONFIDENCE, authorize_tool_call, execute_tool_call
from .reasoning.tool_calls import ToolCallParseError, parse_tool_calls
from .tool_contract import Decision, ToolCall, ToolCallResult, ToolSpec, blocked_message
from .tools.boundary import ToolBoundary


def visible_tool_specs(tool_boundary: ToolBoundary, allowed_scopes) -> list:
    """ToolSpecs the model is allowed to SEE: the intersection of the
    registry (registered), the boundary (authorized), and the session's
    allowed scopes. Scope metadata is included per the contract so the
    model knows what each tool touches -- seeing a spec authorizes
    nothing."""
    allowed = set(allowed_scopes or ())
    specs = []
    for name in tool_boundary.discover():
        descriptor = tool_boundary.get(name)
        if descriptor is None or not tool_boundary.is_authorized(name):
            continue
        scopes = descriptor.scopes or (f"tool:{name}",)
        if any(s not in allowed for s in scopes):
            continue
        specs.append(ToolSpec(
            name=name,
            description=descriptor.description,
            parameters_schema=getattr(descriptor, "parameters_schema", {}) or {},
            scopes=tuple(scopes),
        ))
    return specs


@dataclass
class ModelToolTurn:
    """Everything one model turn produced, stage by stage. If any stage
    failed or blocked, `executed` stays empty and `assistant_message`
    explains what happened WITHOUT leaking internals."""

    response_text: str = ""
    proposed_calls: tuple = ()
    decisions: tuple = ()
    results: tuple = ()
    blocked_messages: tuple = ()
    parse_error: Optional[str] = None

    @property
    def executed(self) -> tuple:
        return tuple(r for r in self.results if r.executed)


def run_model_tool_turn(
    *,
    engine,
    messages: Sequence,
    tool_boundary: ToolBoundary,
    allowed_scopes,
    required_confidence: float = DEFAULT_REQUIRED_CONFIDENCE,
    evidence_confidence: float = 0.0,
    decision_log: Optional[list] = None,
) -> ModelToolTurn:
    """One full turn: provider -> normalize -> registry -> decision ->
    authorization -> execute_tool_call -> REAL TOOL.

    messages follow the provider-neutral Message contract
    (lantern_harness.tool_contract); they are mapped to the common
    chat shape the ReasoningEngine adapters already accept
    ({"role": ..., "content": ...}).
    """
    turn = ModelToolTurn()
    if decision_log is None:
        decision_log = []

    visible = visible_tool_specs(tool_boundary, allowed_scopes)
    chat_messages = [
        {"role": m.role, "content": m.content} if not getattr(m, "tool_call_id", None)
        else {"role": m.role, "content": m.content, "tool_call_id": m.tool_call_id}
        for m in messages
    ]
    tools_payload = [
        {"name": s.name, "description": s.description,
         "parameters_schema": s.parameters_schema, "scopes": list(s.scopes)}
        for s in visible
    ]

    response = engine.respond(chat_messages, tools=tools_payload or None)
    turn.response_text = response.text

    # ---- stage: normalization (adapter seam; provider shapes end here) ----
    try:
        calls = parse_tool_calls(response.raw)
    except ToolCallParseError as exc:
        turn.parse_error = str(exc)
        turn.blocked_messages = (
            "Action blocked: the model response could not be normalized into "
            "the tool-call contract, so nothing was executed.",
        )
        return turn
    turn.proposed_calls = tuple(calls)
    if not calls:
        return turn

    visible_names = {s.name for s in visible}
    for call in calls:
        # ---- stage: registry -------------------------------------------
        descriptor = tool_boundary.get(call.tool_name)
        if descriptor is None or not tool_boundary.is_authorized(call.tool_name):
            reason = f"tool {call.tool_name!r} is not in this session's visible tool registry"
            turn.blocked_messages += (reason + " Nothing was executed.",)
            turn.decisions += (Decision(state="Denied", confidence=0.0, reason=reason,
                                         evidence={"registry": False}),)
            decision_log.append({"tool_call": call.to_dict(),
                                 "decision": turn.decisions[-1].to_dict()})
            continue
        if call.tool_name not in visible_names:
            reason = f"tool {call.tool_name!r} was not offered to the model in this session"
            turn.blocked_messages += (reason + " Nothing was executed.",)
            turn.decisions += (Decision(state="Denied", confidence=0.0, reason=reason,
                                         evidence={"visible": False}),)
            decision_log.append({"tool_call": call.to_dict(),
                                 "decision": turn.decisions[-1].to_dict()})
            continue

        # ---- stage: decision + authorization ----------------------------
        decision = authorize_tool_call(
            call, allowed_scopes,
            evidence_confidence=float(evidence_confidence),
            tool_boundary=tool_boundary,
        )
        turn.decisions += (decision,)
        # ---- stage: execute_tool_call (the single execution path) -------
        tool_call_result, tool_result = execute_tool_call(
            call, decision, required_confidence, tool_boundary, decision_log=decision_log,
        )
        turn.results += (tool_call_result,)
        if not tool_call_result.executed:
            turn.blocked_messages += (blocked_message(call, decision, required_confidence),)
    return turn
