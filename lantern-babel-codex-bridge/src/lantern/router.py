"""
Lantern Message Router v0.84

Purpose:
- Route protocol messages safely
- Enforce negotiated capabilities
- Keep transport separate from reasoning

Router does not:
- modify evidence
- modify beliefs
- modify Codex state

It only decides:
"Can this message type enter this Lantern?"
"""

from dataclasses import dataclass
from typing import Callable, Dict

from .compatibility import CompatibilityResult, can_exchange
from .protocol import ProtocolMessage


# ============================================================
# Message Capability Map
# ============================================================

MESSAGE_REQUIREMENTS = {
    "OBSERVATION_SHARE": "evidence_exchange",
    "CODEX_UPDATE": "codex_update",
    "EVIDENCE_REQUEST": "belief_query",
}


# ============================================================
# Route Result
# ============================================================

@dataclass
class RouteResult:
    accepted: bool
    message_type: str
    reason: str


# ============================================================
# Router
# ============================================================

class LanternRouter:
    def __init__(self):
        self.handlers: Dict[str, Callable] = {}

    def register(self, message_type: str, handler: Callable):
        self.handlers[message_type] = handler

    def route(self, message: ProtocolMessage, compatibility: CompatibilityResult):
        required = MESSAGE_REQUIREMENTS.get(message.message_type)

        if required is not None:
            if not can_exchange(compatibility, required):
                return RouteResult(
                    False,
                    message.message_type,
                    "Capability unavailable: " + required,
                )

        handler = self.handlers.get(message.message_type)

        if handler is None:
            return RouteResult(
                False,
                message.message_type,
                "No handler registered",
            )

        handler(message)

        return RouteResult(
            True,
            message.message_type,
            "Delivered",
        )
