"""Ollama adapter. Detects the local Ollama server; does not assume it's
installed or running."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Optional

from .base import ReasoningEngine, ReasoningEngineUnavailable, ReasoningResponse


class OllamaEngine(ReasoningEngine):
    provider_name = "ollama"

    def __init__(self, model: str = "llama3.1", host: str = "http://localhost:11434"):
        self.model = model
        self.host = host.rstrip("/")

    def detect(self) -> tuple[bool, str]:
        """Returns (available, detail). Never raises."""
        try:
            req = urllib.request.Request(f"{self.host}/api/tags")
            with urllib.request.urlopen(req, timeout=2) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                models = [m.get("name") for m in data.get("models", [])]
                if self.model not in models and not any(
                    m.startswith(self.model.split(":")[0]) for m in models if m
                ):
                    return True, f"Ollama reachable at {self.host}, but model '{self.model}' not pulled (available: {models})"
                return True, f"Ollama reachable at {self.host}, model '{self.model}' available"
        except (urllib.error.URLError, OSError, TimeoutError) as exc:
            return False, f"Ollama not reachable at {self.host}: {exc}"

    def respond(self, messages: list[dict], tools: Optional[list[dict]] = None) -> ReasoningResponse:
        available, detail = self.detect()
        if not available:
            raise ReasoningEngineUnavailable(detail)

        payload = {"model": self.model, "messages": messages, "stream": False}
        body = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            f"{self.host}/api/chat",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except (urllib.error.URLError, OSError, TimeoutError) as exc:
            raise ReasoningEngineUnavailable(f"Ollama request failed: {exc}") from exc

        text = data.get("message", {}).get("content", "")
        return ReasoningResponse(text=text, provider=self.provider_name, model=self.model, raw=data)

    def describe(self) -> dict:
        available, detail = self.detect()
        return {
            "provider": self.provider_name,
            "model": self.model,
            "host": self.host,
            "available": available,
            "detail": detail,
        }
