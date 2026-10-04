"""Decision gate: MANDATORY scoped authorization + confidence gating of
all tool execution in the harness.

This module exists because the decision logic was previously advisory:
OperatingLoop computed a confidence reading and a decision state, but
RealityBoundary.act() executed an authorized tool regardless of that
reading (observed live 2026-10-04: a LOW-confidence "BRANCH / INVESTIGATE"
decision still performed a real file write). This module closes that gap.

Invariants enforced HERE, not in docstrings:
    1. Tool implementation code is only reachable through
       execute_tool_call(...), and only when decision.state == "Allowed"
       AND decision.confidence >= required_confidence.
    2. authorize_tool_call() derives scopes from the REGISTERED
       ToolDescriptor -- it never trusts the model-requested scopes.
    3. Every authorization and every gate outcome is logged before the
       implementation is invoked or refused.
    4. The harness (this module) is the only component allowed to call
       the tool implementation; tools never self-invoke on model output.

Where things live:
    - provider-specific raw shapes (OpenAI tool_calls, Anthropic
      tool_use blocks, Ollama responses) are normalized in
      lantern_harness/reasoning/tool_calls.py -- the adapter seam.
    - this module sees ONLY the provider-neutral types from
      lantern_harness/tool_contract.py.
"""

from __future__ import annotations

from typing import Iterable, Optional

from .tool_contract import Decision, ToolCall, ToolCallResult, blocked_message
from .tools.boundary import ToolBoundary, ToolResult

DEFAULT_REQUIRED_CONFIDENCE = 0.8


def derive_tool_scopes(tool_boundary: ToolBoundary, tool_name: str) -> tuple:
    """Scopes a tool call actually needs, from the registered descriptor.
    Undeclared scopes fall back to the conservative per-tool scope
    "tool:<name>" so every tool has at least one scope."""
    descriptor = tool_boundary.get(tool_name)
    if descriptor is None:
        return (f"tool:{tool_name}",)
    if descriptor.scopes:
        return tuple(descriptor.scopes)
    return (f"tool:{tool_name}",)


def authorize_tool_call(
    tool_call: ToolCall,
    allowed_scopes: Iterable,
    *,
    evidence_confidence: Optional[float] = None,
    tool_boundary: Optional[ToolBoundary] = None,
) -> Decision:
    """Scoped authorization for one ToolCall.

    Semantics:
      - Scope check uses the REGISTERED descriptor's scopes (or the
        derived "tool:<name>" scope), never tool_call.requested_scopes.
      - A scope violation -> Decision(state="Denied", confidence=0.0).
      - Scope-passing calls -> state="Allowed" with confidence taken from
        evidence_confidence (what the harness measured about the world,
        e.g. the ConfidenceField reading). When no evidence confidence is
        supplied, direct authorization calls default to 1.0 -- the caller
        is asserting scope-only authorization; the confidence gate still
        applies downstream via execute_tool_call.
      - A tool not registered in ToolBoundary -> Denied (cannot verify scopes).
    """
    allowed = set(allowed_scopes or ())
    if tool_boundary is not None and tool_boundary.get(tool_call.tool_name) is None:
        return Decision(
            state="Denied", confidence=0.0,
            reason=f"tool {tool_call.tool_name!r} is not registered in the harness tool boundary",
            evidence={"missing_scopes": [], "registered": False},
        )
    needed = derive_tool_scopes(tool_boundary, tool_call.tool_name) if tool_boundary is not None \
        else tuple(tool_call.requested_scopes or (f"tool:{tool_call.tool_name}",))
    missing = [s for s in needed if s not in allowed]
    if missing:
        return Decision(
            state="Denied", confidence=0.0,
            reason="this session is not authorized for one or more scopes the tool requires",
            evidence={"missing_scopes": missing, "required_scopes": list(needed)},
        )
    conf = 1.0 if evidence_confidence is None else max(0.0, min(1.0, float(evidence_confidence)))
    return Decision(
        state="Allowed", confidence=conf,
        reason="all required scopes are within the session's allowed scopes",
        evidence={"required_scopes": list(needed), "confidence_source": "evidence" if evidence_confidence is not None else "scope-only"},
    )


def execute_tool_call(
    tool_call: ToolCall,
    decision: Decision,
    required_confidence: float,
    tool_boundary: ToolBoundary,
    decision_log: Optional[list] = None,
) -> tuple:
    """THE single production path from a ToolCall to tool execution.

    Returns (ToolCallResult, ToolResult). The tool implementation is
    invoked -- through ToolBoundary.execute -- ONLY when:
        decision.state == "Allowed" AND decision.confidence >= required_confidence
    and the tool is registered and authorized in the ToolBoundary. Every
    other case returns a BLOCKED/DENIED ToolResult WITHOUT calling the
    implementation, and the decision is logged before anything runs.

    No other harness code may call ToolBoundary.execute() on a
    model-proposed call; RealityBoundary.act() is deprecated for
    production use in favor of this gate.
    """
    if decision_log is None:
        decision_log = []
    decision_log.append({"tool_call": tool_call.to_dict(), "decision": decision.to_dict()})

    if decision.state != "Allowed":
        reason = blocked_message(tool_call, decision, required_confidence)
        return (
            ToolCallResult(tool_call=tool_call, decision=decision, executed=False, blocked_reason=reason),
            ToolResult(tool_name=tool_call.tool_name, status="BLOCKED", error=reason),
        )
    if float(decision.confidence) < float(required_confidence):
        reason = blocked_message(tool_call, decision, required_confidence)
        return (
            ToolCallResult(tool_call=tool_call, decision=decision, executed=False, blocked_reason=reason),
            ToolResult(tool_name=tool_call.tool_name, status="BLOCKED", error=reason),
        )
    tool_result = tool_boundary.execute(tool_call.tool_name, **tool_call.arguments)
    executed = tool_result.status == "EXECUTED"
    return (
        ToolCallResult(
            tool_call=tool_call, decision=decision, executed=executed,
            result=tool_result.output if executed else None,
            blocked_reason=None if executed else (tool_result.error or "tool boundary refused the call"),
        ),
        tool_result,
    )


def load_tool_policy(config: dict) -> dict:
    """Read the tool policy from config. Single source of truth:
    config["tool_policy"] = {"required_confidence": 0.8, "allowed_scopes": [...]}
    Missing config falls back to safe defaults."""
    policy = (config or {}).get("tool_policy") or {}
    required = policy.get("required_confidence", DEFAULT_REQUIRED_CONFIDENCE)
    scopes = tuple(policy.get("allowed_scopes") or ())
    return {"required_confidence": float(required), "allowed_scopes": scopes}
