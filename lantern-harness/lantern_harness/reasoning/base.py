"""Provider-neutral reasoning engine interface.

No provider is mandatory. If none is configured, callers must see
REASONING_ENGINE: NOT_CONFIGURED rather than a fabricated response.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional


@dataclass
class ReasoningResponse:
    text: str
    provider: str
    model: str
    raw: Any = None


class ReasoningEngineUnavailable(RuntimeError):
    """Raised when a provider is selected but cannot actually respond
    (e.g. Ollama not installed, API key missing, network error)."""


class ReasoningEngine:
    """Base class every provider adapter implements.

    messages: list[dict] with "role" ("user"/"assistant"/"system") and
    "content" (str), mirroring the common chat-message shape so adapters
    stay interchangeable.
    """

    provider_name: str = "base"

    def respond(self, messages: list[dict], tools: Optional[list[dict]] = None) -> ReasoningResponse:
        raise NotImplementedError

    def describe(self) -> dict:
        raise NotImplementedError
