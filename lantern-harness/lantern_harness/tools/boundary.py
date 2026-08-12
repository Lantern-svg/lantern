"""Tool boundary: discovery -> capability evaluation -> authorization ->
execution -> result -> provenance/evidence.

Tool existence is never treated as authorization. This module owns the
gate; it does not perform the actual tool call itself (that stays with
whatever tool implementation is registered).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Optional


@dataclass
class ToolDescriptor:
    name: str
    description: str
    handler: Callable[..., Any]
    requires_authorization: bool = True


@dataclass
class ToolResult:
    tool_name: str
    status: str  # "EXECUTED" | "DENIED" | "ERROR"
    output: Any = None
    error: Optional[str] = None


class ToolBoundary:
    """A minimal, local capability gate for harness-registered tools.

    This is deliberately NOT lantern.capability_authorization -- that
    module governs Lantern's own protected authority floor and is not
    duplicated here. This boundary is a much smaller gate for harness
    convenience tools (Files/Git/Browser/Shell/etc.) that the harness
    author explicitly registers and explicitly authorizes -- it is the
    "harness tool boundary" referenced in the mission brief, not a
    second Lantern authorization system.
    """

    def __init__(self):
        self._tools: dict[str, ToolDescriptor] = {}
        self._authorized: set[str] = set()

    def register(self, descriptor: ToolDescriptor) -> None:
        self._tools[descriptor.name] = descriptor

    def discover(self) -> list[str]:
        return sorted(self._tools.keys())

    def authorize(self, tool_name: str) -> bool:
        """Explicit operator action. Discovery alone never does this."""
        if tool_name not in self._tools:
            return False
        self._authorized.add(tool_name)
        return True

    def is_authorized(self, tool_name: str) -> bool:
        return tool_name in self._authorized

    def execute(self, tool_name: str, **kwargs) -> ToolResult:
        descriptor = self._tools.get(tool_name)
        if descriptor is None:
            return ToolResult(tool_name=tool_name, status="ERROR", error="tool not registered")

        if descriptor.requires_authorization and not self.is_authorized(tool_name):
            return ToolResult(tool_name=tool_name, status="DENIED", error="not authorized")

        try:
            output = descriptor.handler(**kwargs)
            return ToolResult(tool_name=tool_name, status="EXECUTED", output=output)
        except Exception as exc:  # noqa: BLE001 - report, don't crash the loop
            return ToolResult(tool_name=tool_name, status="ERROR", error=str(exc))
