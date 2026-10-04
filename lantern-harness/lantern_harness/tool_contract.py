"""Tool-call contract: the ONLY types that cross the model-adapter and
harness boundaries when tools are involved.

Contracts guaranteed by these types:
    - Message / ToolSpec / ToolCall / Decision / ToolCallResult are
      provider-neutral. No provider-specific field ever appears here.
    - A ToolCall is a REQUEST. Constructing one authorizes nothing and
      executes nothing.
    - A Decision is a judgment record, not a capability: state="Allowed"
      only means the scoped-authorization step passed, never that a tool
      ran. Extensible states ("Escalate", ...) are permitted -- unknown
      states are treated as non-executable by the decision gate.

Invariants the harness enforces around these types (see decision_gate.py):
    - Tool implementation code runs ONLY through
      execute_tool_call(tool_call, decision, required_confidence, ...)
      when decision.state == "Allowed" AND decision.confidence >=
      required_confidence. There is no other production execution path.
    - Every decision is logged (state, confidence, reason) before any
      execution is attempted or refused.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


VALID_DECISION_STATES = ("Allowed", "Denied")


@dataclass(frozen=True)
class Message:
    """One conversation message, provider-neutral.

    content may later grow structured blocks; today it is text.
    tool_call_id is set only for role="tool" result messages."""

    role: str  # "system" | "user" | "assistant" | "tool"
    content: str
    tool_call_id: Optional[str] = None

    def __post_init__(self):
        if self.role not in ("system", "user", "assistant", "tool"):
            raise ValueError(f"Message.role must be system|user|assistant|tool, got {self.role!r}")
        if self.role == "tool" and not self.tool_call_id:
            raise ValueError("Message with role='tool' requires tool_call_id")


@dataclass(frozen=True)
class ToolSpec:
    """What the model is allowed to SEE about a tool. Showing a spec
    never registers, authorizes, or scopes the tool itself -- the
    harness owns all three."""

    name: str
    description: str
    parameters_schema: dict = field(default_factory=dict)
    scopes: tuple = ()  # e.g. ("filesystem.write",)

    def __post_init__(self):
        if not self.name or not self.name.strip():
            raise ValueError("ToolSpec.name must be a non-empty string")
        self.__dict__["scopes"] = tuple(self.scopes)
        self.__dict__["parameters_schema"] = dict(self.parameters_schema)


@dataclass(frozen=True)
class ToolCall:
    """A tool invocation REQUEST, whoever proposed it (model or operator).

    arguments must be a JSON-serializable dict. requested_scopes is what
    the caller believes this call needs; the harness re-derives scopes
    from the registered ToolDescriptor at authorization time and never
    trusts requested_scopes alone."""

    id: str
    tool_name: str
    arguments: dict = field(default_factory=dict)
    requested_scopes: tuple = ()

    def __post_init__(self):
        if not self.id or not self.id.strip():
            raise ValueError("ToolCall.id must be a non-empty correlation id")
        if not self.tool_name or not self.tool_name.strip():
            raise ValueError("ToolCall.tool_name must be a non-empty string")
        if not isinstance(self.arguments, dict):
            raise ValueError("ToolCall.arguments must be a dict of JSON arguments")
        self.__dict__["requested_scopes"] = tuple(self.requested_scopes)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "tool_name": self.tool_name,
            "arguments": dict(self.arguments),
            "requested_scopes": list(self.requested_scopes),
        }


@dataclass(frozen=True)
class Decision:
    """The scoped-authorization + confidence judgment for one ToolCall.

    state:  "Allowed" | "Denied" (extensible: unknown states never execute)
    confidence: 0.0-1.0. For scope violations it is 0.0; for scope-passing
    calls it carries the evidence-based confidence the harness measured.
    reason: human-readable, safe to surface to the operator.
    evidence: structured, non-secret metadata (missing_scopes, required,
    measured confidence source, ...)."""

    state: str
    confidence: float
    reason: str
    evidence: dict = field(default_factory=dict)

    def __post_init__(self):
        if self.state not in VALID_DECISION_STATES:
            # Extensibility contract: future states (e.g. "Escalate") may be
            # added to VALID_DECISION_STATES, but until then they are
            # constructed, not guessed, and the gate refuses them.
            raise ValueError(f"Decision.state must be one of {VALID_DECISION_STATES}, got {self.state!r}")
        try:
            c = float(self.confidence)
        except (TypeError, ValueError):
            raise ValueError("Decision.confidence must be numeric")
        if c < 0.0 or c > 1.0:
            raise ValueError("Decision.confidence must be within [0.0, 1.0]")

    def to_dict(self) -> dict:
        return {
            "state": self.state,
            "confidence": self.confidence,
            "reason": self.reason,
            "evidence": dict(self.evidence),
        }


@dataclass(frozen=True)
class ToolCallResult:
    """Outcome of one gated tool call: the ToolCall, the Decision that
    was made, and what the gate did with it. result is the tool's output
    when executed; None when blocked. blocked_reason carries the safe,
    operator-surfacing explanation."""

    tool_call: ToolCall
    decision: Decision
    executed: bool
    result: Any = None
    blocked_reason: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "tool_call": self.tool_call.to_dict(),
            "decision": self.decision.to_dict(),
            "executed": self.executed,
            "result": self.result,
            "blocked_reason": self.blocked_reason,
        }


def blocked_message(tool_call: ToolCall, decision: Decision, required_confidence: float) -> str:
    """Assistant-facing message describing a blocked action WITHOUT
    leaking internals: no scope sets, no provider detail, no stack."""
    return (
        f"Action blocked: {tool_call.tool_name} was not executed because the decision was "
        f"{decision.state!r} with confidence {decision.confidence:.2f} "
        f"(required: {required_confidence:.2f}). {decision.reason}"
    )
