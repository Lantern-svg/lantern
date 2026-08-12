"""Generic HTTP API adapters (OpenAI, Anthropic, Google). Reads API keys
only from environment variables; never logs, prints, or persists them
anywhere Lantern would record (Chronicle, evidence, witness ledger,
project files)."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Optional

from .base import ReasoningEngine, ReasoningEngineUnavailable, ReasoningResponse


class OpenAIEngine(ReasoningEngine):
    provider_name = "openai"

    def __init__(self, model: str = "gpt-4o-mini", api_key_env: str = "OPENAI_API_KEY"):
        self.model = model
        self.api_key_env = api_key_env

    def _api_key(self) -> Optional[str]:
        return os.environ.get(self.api_key_env)

    def detect(self) -> tuple[bool, str]:
        if not self._api_key():
            return False, f"{self.api_key_env} not set"
        return True, f"{self.api_key_env} present"

    def respond(self, messages: list[dict], tools: Optional[list[dict]] = None) -> ReasoningResponse:
        api_key = self._api_key()
        if not api_key:
            raise ReasoningEngineUnavailable(f"{self.api_key_env} not set")

        payload = {"model": self.model, "messages": messages}
        body = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            "https://api.openai.com/v1/chat/completions",
            data=body,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except (urllib.error.URLError, OSError, TimeoutError) as exc:
            raise ReasoningEngineUnavailable(f"OpenAI request failed: {exc}") from exc

        text = data.get("choices", [{}])[0].get("message", {}).get("content", "")
        return ReasoningResponse(text=text, provider=self.provider_name, model=self.model, raw=data)

    def describe(self) -> dict:
        available, detail = self.detect()
        return {"provider": self.provider_name, "model": self.model, "available": available, "detail": detail}


class AnthropicEngine(ReasoningEngine):
    provider_name = "anthropic"

    def __init__(self, model: str = "claude-sonnet-5", api_key_env: str = "ANTHROPIC_API_KEY"):
        self.model = model
        self.api_key_env = api_key_env

    def _api_key(self) -> Optional[str]:
        return os.environ.get(self.api_key_env)

    def detect(self) -> tuple[bool, str]:
        if not self._api_key():
            return False, f"{self.api_key_env} not set"
        return True, f"{self.api_key_env} present"

    def respond(self, messages: list[dict], tools: Optional[list[dict]] = None) -> ReasoningResponse:
        api_key = self._api_key()
        if not api_key:
            raise ReasoningEngineUnavailable(f"{self.api_key_env} not set")

        system = "\n".join(m["content"] for m in messages if m.get("role") == "system")
        turns = [m for m in messages if m.get("role") != "system"]
        payload = {"model": self.model, "max_tokens": 1024, "messages": turns}
        if system:
            payload["system"] = system
        body = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            "https://api.anthropic.com/v1/messages",
            data=body,
            headers={
                "Content-Type": "application/json",
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except (urllib.error.URLError, OSError, TimeoutError) as exc:
            raise ReasoningEngineUnavailable(f"Anthropic request failed: {exc}") from exc

        blocks = data.get("content", [])
        text = "".join(b.get("text", "") for b in blocks if b.get("type") == "text")
        return ReasoningResponse(text=text, provider=self.provider_name, model=self.model, raw=data)

    def describe(self) -> dict:
        available, detail = self.detect()
        return {"provider": self.provider_name, "model": self.model, "available": available, "detail": detail}


class GoogleEngine(ReasoningEngine):
    provider_name = "google"

    def __init__(self, model: str = "gemini-2.0-flash", api_key_env: str = "GOOGLE_API_KEY"):
        self.model = model
        self.api_key_env = api_key_env

    def _api_key(self) -> Optional[str]:
        return os.environ.get(self.api_key_env)

    def detect(self) -> tuple[bool, str]:
        if not self._api_key():
            return False, f"{self.api_key_env} not set"
        return True, f"{self.api_key_env} present"

    def respond(self, messages: list[dict], tools: Optional[list[dict]] = None) -> ReasoningResponse:
        api_key = self._api_key()
        if not api_key:
            raise ReasoningEngineUnavailable(f"{self.api_key_env} not set")

        system_text = "\n".join(m["content"] for m in messages if m.get("role") == "system")
        contents = [
            {"role": "user" if m.get("role") != "assistant" else "model", "parts": [{"text": m["content"]}]}
            for m in messages
            if m.get("role") != "system"
        ]
        payload = {"contents": contents}
        if system_text:
            payload["systemInstruction"] = {"parts": [{"text": system_text}]}
        body = json.dumps(payload).encode("utf-8")
        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{self.model}:generateContent?key={api_key}"
        )
        req = urllib.request.Request(
            url, data=body, headers={"Content-Type": "application/json"}, method="POST"
        )
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except (urllib.error.URLError, OSError, TimeoutError) as exc:
            raise ReasoningEngineUnavailable(f"Google request failed: {exc}") from exc

        candidates = data.get("candidates", [])
        text = ""
        if candidates:
            parts = candidates[0].get("content", {}).get("parts", [])
            text = "".join(p.get("text", "") for p in parts)
        return ReasoningResponse(text=text, provider=self.provider_name, model=self.model, raw=data)

    def describe(self) -> dict:
        available, detail = self.detect()
        return {"provider": self.provider_name, "model": self.model, "available": available, "detail": detail}
