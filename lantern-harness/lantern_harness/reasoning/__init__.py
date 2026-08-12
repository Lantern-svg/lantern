"""Provider-neutral reasoning engine registry.

No provider is mandatory. build_engine() returns None (not a fake
engine) when nothing is configured, so callers must handle
REASONING_ENGINE: NOT_CONFIGURED explicitly rather than silently
fabricating a response.
"""

from __future__ import annotations

from typing import Optional

from .api_provider import AnthropicEngine, GoogleEngine, OpenAIEngine
from .base import ReasoningEngine, ReasoningEngineUnavailable, ReasoningResponse
from .ollama_provider import OllamaEngine

_PROVIDERS = {
    "ollama": OllamaEngine,
    "openai": OpenAIEngine,
    "anthropic": AnthropicEngine,
    "google": GoogleEngine,
}


def build_engine(config: dict) -> Optional[ReasoningEngine]:
    """config is the "reasoning_engine" section of config.json.

    Returns None if no provider is configured or the named provider is
    unknown -- never returns a stub that fakes a response.
    """
    provider = config.get("provider")
    if not provider or provider == "none":
        return None
    cls = _PROVIDERS.get(provider)
    if cls is None:
        return None

    kwargs = {}
    if "model" in config:
        kwargs["model"] = config["model"]
    if provider == "ollama" and "ollama_host" in config:
        kwargs["host"] = config["ollama_host"]
    if provider in ("openai", "anthropic", "google") and "api_key_env" in config:
        kwargs["api_key_env"] = config["api_key_env"]

    return cls(**kwargs)


__all__ = [
    "ReasoningEngine",
    "ReasoningEngineUnavailable",
    "ReasoningResponse",
    "OllamaEngine",
    "OpenAIEngine",
    "AnthropicEngine",
    "GoogleEngine",
    "build_engine",
]
