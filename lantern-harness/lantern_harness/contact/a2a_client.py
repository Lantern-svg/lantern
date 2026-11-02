"""Read-only A2A (JSON-RPC 2.0) client for the Lantern agent endpoint.

The reasoning model may choose WHICH allowed read to perform. It may never
choose a URL, method, header, or credential. Every failure surfaces as an
exception -- a network failure is never converted into a successful answer.
"""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Optional

A2A_ENDPOINT = "https://zelle-4457b476.base44.app/functions/lanternA2A"
USER_AGENT = "lantern-contact/1.0"
DEFAULT_TIMEOUT = 30.0
MAX_RESPONSE_BYTES = 512_000
MAX_COLLATZ_INPUT = 1_000_000

_VERIFY = re.compile(r"^verify\s+board$", re.IGNORECASE)
_HASH = re.compile(r"^hash\s+([0-9a-fA-F]{8,64})$", re.IGNORECASE)
_COLLATZ = re.compile(r"^collatz\s+([1-9][0-9]{0,8})$", re.IGNORECASE)

ALLOWED_OPERATIONS = ("verify board", "hash <entry hash>", "collatz <positive integer>")


class A2AClientError(Exception):
    """Transport, protocol, or validation failure. Never swallowed."""


@dataclass
class A2AResult:
    operation: str
    text: str
    raw: dict[str, Any]
    endpoint: str
    elapsed_ms: int


def validate_request_text(text: str) -> str:
    """Normalise and validate an allowed read-only request. Raises on
    anything else: URLs, arbitrary verbs, extra arguments."""
    if not isinstance(text, str):
        raise A2AClientError("request text must be a string")
    cleaned = " ".join(text.strip().split())
    if len(cleaned) > 120:
        raise A2AClientError("request text is too long")
    if _VERIFY.match(cleaned):
        return "verify board"
    match = _HASH.match(cleaned)
    if match:
        return f"hash {match.group(1).lower()}"
    match = _COLLATZ.match(cleaned)
    if match:
        value = int(match.group(1))
        if value < 1 or value > MAX_COLLATZ_INPUT:
            raise A2AClientError(f"collatz input must be 1..{MAX_COLLATZ_INPUT}")
        return f"collatz {value}"
    raise A2AClientError(
        "unsupported request; allowed: " + "; ".join(ALLOWED_OPERATIONS)
    )


def build_payload(normalised_text: str, request_id: int = 1) -> dict[str, Any]:
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "method": "message/send",
        "params": {"message": {"parts": [{"kind": "text", "text": normalised_text}]}},
    }


class A2AClient:
    """Fixed-endpoint client. Constructed by the harness, never by the model."""

    def __init__(
        self,
        endpoint: str = A2A_ENDPOINT,
        *,
        timeout: float = DEFAULT_TIMEOUT,
        max_bytes: int = MAX_RESPONSE_BYTES,
        transport: Optional[Any] = None,
    ):
        if not endpoint.startswith("https://"):
            raise A2AClientError("A2A endpoint must be https")
        self.endpoint = endpoint
        self.timeout = timeout
        self.max_bytes = max_bytes
        self._transport = transport  # injectable for tests; callable(payload) -> (status, bytes)

    def send(self, text: str) -> A2AResult:
        import time

        operation = validate_request_text(text)
        payload = build_payload(operation)
        started = time.monotonic()

        if self._transport is not None:
            status, body = self._transport(payload)
        else:
            status, body = self._post(payload)

        if status != 200:
            raise A2AClientError(f"A2A endpoint returned HTTP {status}")
        if len(body) > self.max_bytes:
            raise A2AClientError(f"A2A response exceeds size limit ({len(body)} bytes)")
        try:
            parsed = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise A2AClientError(f"A2A response is not valid JSON: {exc}") from exc
        if not isinstance(parsed, dict):
            raise A2AClientError("A2A response is not a JSON object")
        if parsed.get("jsonrpc") != "2.0":
            raise A2AClientError("A2A response is not JSON-RPC 2.0")
        if "error" in parsed:
            raise A2AClientError(f"A2A JSON-RPC error: {json.dumps(parsed['error'])[:300]}")

        text_out = _extract_text(parsed)
        if not text_out:
            raise A2AClientError("A2A response carried no text result")
        return A2AResult(
            operation=operation, text=text_out, raw=parsed, endpoint=self.endpoint,
            elapsed_ms=int((time.monotonic() - started) * 1000),
        )

    def _post(self, payload: dict[str, Any]) -> tuple[int, bytes]:
        req = urllib.request.Request(
            self.endpoint,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json", "User-Agent": USER_AGENT},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as response:
                return response.status, response.read(self.max_bytes + 1)
        except urllib.error.HTTPError as exc:
            return exc.code, b""
        except urllib.error.URLError as exc:
            raise A2AClientError(f"A2A endpoint unreachable: {exc.reason}") from exc
        except TimeoutError as exc:
            raise A2AClientError("A2A request timed out") from exc


def _extract_text(parsed: dict[str, Any]) -> str:
    result = parsed.get("result")
    if isinstance(result, dict):
        parts = result.get("parts")
        if isinstance(parts, list):
            for part in parts:
                if isinstance(part, dict) and isinstance(part.get("text"), str):
                    return part["text"]
        if isinstance(result.get("content"), list):
            for item in result["content"]:
                if isinstance(item, dict) and isinstance(item.get("text"), str):
                    return item["text"]
    return ""
