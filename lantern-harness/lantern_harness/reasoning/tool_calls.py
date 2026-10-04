"""Provider-side tool-call normalization -- the ADAPTER SEAM.

This is the ONLY module in the harness that understands provider-specific
response shapes (OpenAI `tool_calls`, Anthropic `tool_use` content blocks,
Ollama/OpenAI-compatible `tool_calls` under `message`). It normalizes them
into the provider-neutral ToolCall contract (lantern_harness/tool_contract)
and rejects anything nonconforming.

Adapter target choice (documented per the integration directive): the
best supported model API for this harness is the Ollama local HTTP API
(open, keyless, already wired in lantern_harness/reasoning/ollama_provider.py
and default in config/config.json's reasoning_engine section); OpenAI- and
Anthropic-compatible adapters already exist alongside it. This module
normalizes all three because the shapes are what providers emit, not what
the harness believes.

Contract guaranteed by parse_tool_calls():
    - returns ONLY validated ToolCall objects (contract-enforced types)
    - provider field names never leak past this function
    - a nonconforming provider payload raises ToolCallParseError --
      it is never silently coerced into a call
"""

from __future__ import annotations

import json
from typing import Any, Optional

from ..tool_contract import ToolCall


class ToolCallParseError(ValueError):
    """Raised when a provider payload cannot be normalized into the
    strict ToolCall contract. Callers must surface this, not retry-blind."""


def _mk(call_id: Any, name: Any, arguments: Any) -> ToolCall:
    if not isinstance(name, str) or not name.strip():
        raise ToolCallParseError(f"tool call has no usable name: {name!r}")
    call_id = str(call_id) if call_id not in (None, "") else f"provider-{name}-{id(arguments):x}"
    if isinstance(arguments, dict):
        args = dict(arguments)
    elif isinstance(arguments, str):
        try:
            args = json.loads(arguments) if arguments.strip() else {}
        except json.JSONDecodeError as exc:
            raise ToolCallParseError(f"tool call {name!r} arguments are not valid JSON: {exc}")
        if not isinstance(args, dict):
            raise ToolCallParseError(f"tool call {name!r} arguments must decode to a JSON object")
    elif arguments is None:
        args = {}
    else:
        raise ToolCallParseError(f"tool call {name!r} arguments have unsupported type {type(arguments).__name__}")
    return ToolCall(id=call_id, tool_name=name.strip(), arguments=args)


def parse_tool_calls(raw: Any) -> list:
    """Normalize a provider response into ToolCall objects.

    Supported raw shapes (first match wins):
      - OpenAI / Ollama (OpenAI-compatible):
        {"choices": [{"message": {"tool_calls": [{"id","function":{"name","arguments"}}]}}]}
        or a bare message dict {"tool_calls": [...]}.
      - Anthropic: {"content": [{"type": "tool_use", "id", "name", "input"}]}
      - Anthropic-style inside a provider envelope:
        {"content": [...]}, {"output": [...]} or {"response": {"content": [...]}}

    Empty/None -> []. Anything that looks like a tool call but fails the
    contract raises ToolCallParseError (fail-closed, never coerced).
    """
    if raw is None:
        return []

    # OpenAI / Ollama style
    envelope = raw
    if isinstance(envelope, dict):
        choices = envelope.get("choices")
        if isinstance(choices, list) and choices:
            msg = choices[0].get("message") if isinstance(choices[0], dict) else None
            if isinstance(msg, dict) and "tool_calls" in msg:
                return _parse_openai_list(msg["tool_calls"])
        if "tool_calls" in envelope:
            return _parse_openai_list(envelope["tool_calls"])

    # Anthropic style: content blocks anywhere reasonable
    blocks = None
    if isinstance(envelope, dict):
        for key in ("content",):
            if isinstance(envelope.get(key), list):
                blocks = envelope[key]
                break
        if blocks is None and isinstance(envelope.get("response"), dict):
            blocks = envelope["response"].get("content")
        if blocks is None and isinstance(envelope.get("output"), list):
            blocks = envelope["output"]
    if isinstance(blocks, list):
        calls = []
        for block in blocks:
            if isinstance(block, dict) and block.get("type") == "tool_use":
                calls.append(_mk(block.get("id"), block.get("name"), block.get("input")))
        return calls

    # A structurally valid payload that simply carries no tool calls (e.g. a
    # plain OpenAI completion with content only) is an EMPTY call list, not
    # an error. Malformed tool-bearing shapes raise inside the branches above.
    return []


def _parse_openai_list(tool_calls: Any) -> list:
    if not isinstance(tool_calls, list):
        raise ToolCallParseError("tool_calls must be a list")
    calls = []
    for tc in tool_calls:
        if not isinstance(tc, dict):
            raise ToolCallParseError(f"tool call entry must be an object, got {type(tc).__name__}")
        fn = tc.get("function")
        if isinstance(fn, dict):
            calls.append(_mk(tc.get("id"), fn.get("name"), fn.get("arguments")))
        elif tc.get("name") is not None:
            calls.append(_mk(tc.get("id"), tc.get("name"), tc.get("arguments") or tc.get("input")))
        else:
            raise ToolCallParseError("tool call entry has neither function.name nor name")
    return calls
