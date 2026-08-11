"""Real MCP stdio client adapter.

This module is the ONLY place in Lantern that imports the third-party
`mcp` SDK and talks to a live MCP server process. Everything else
(capability registry, Compass, authorization, scoped delegation,
provenance, verification, memory boundary) stays exactly as defined in
`orchestration.py`, `capability_authorization.py`, `compass.py`, and
`mcp_integration.py`.

Position in the pipeline:

    REAL MCP SERVER (subprocess, stdio transport)
        -> StdioMCPClient (this module: real `mcp` SDK session)
        -> MCPIntegrationBoundary.execute()   (mcp_integration.py, unchanged)
        -> CapabilityDecision / DelegationRecord / ProvenanceTag / VerificationPolicy

What this module does:
    - launches a real MCP server as a local subprocess over stdio
      (the only transport the reference server documents as supported;
      see ~/self-improving/mcp_server.py's `run-stdio` mode and its own
      comment that it intentionally binds no network port)
    - performs a real MCP `initialize` handshake and real `list_tools`
    - implements `mcp_integration.MCPAdapter.execute()` by making a real
      `call_tool` request and returning the real result
    - never treats a remote MCP response as identity, trust, or Lantern
      authority; it only returns the tool result payload

What this module deliberately does NOT do:
    - open a network port or expose Lantern to inbound connections
    - decide authorization (that stays in capability_authorization.py)
    - decide verification sufficiency (that stays in the capability's
      VerificationPolicy; a returned MCP result is RETURNED, not VERIFIED)
    - treat the remote server's tool success claim as proof; the caller
      (MCPIntegrationBoundary + capability VerificationPolicy) is
      responsible for independent verification exactly as it already is
      for local workers

REMOTE != LOCAL: everything executed through this adapter is explicitly
tagged with the MCP server's subprocess identity (command/args), and
results are returned as plain dict payloads -- this adapter never writes
to Lantern's Chronicle, EvidenceKernel, or memory files directly.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any, Mapping, Optional

try:
    from mcp import ClientSession, StdioServerParameters, stdio_client
    from mcp import types as mcp_types
    MCP_SDK_AVAILABLE = True
except ImportError:  # pragma: no cover - exercised only when `mcp` extra is absent
    MCP_SDK_AVAILABLE = False

from .mcp_integration import (
    MCPExecutionRequest,
    MCPResourceDescriptor,
    MCPServerDiscovery,
    MCPToolDescriptor,
)


class MCPClientUnavailable(RuntimeError):
    """Raised when the real `mcp` SDK is not installed.

    Lantern's `mcp` extra (`pip install .[mcp]`) must be installed for
    this module to function. This is a deliberately loud, explicit
    failure -- never a silent fallback to fabricated success.
    """


class MCPRemoteError(RuntimeError):
    """Raised when the remote MCP server itself reports a tool error.

    This is surfaced as an explicit error, never translated into a
    fabricated successful result.
    """


@dataclass(frozen=True)
class StdioServerTarget:
    """Identifies a real local MCP server subprocess.

    This is process-launch configuration only -- it grants no authority
    and is not itself a capability, delegation, or provenance record.
    """

    server_id: str
    command: str
    args: tuple[str, ...] = field(default_factory=tuple)
    cwd: Optional[str] = None
    env: Optional[Mapping[str, str]] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "server_id": self.server_id,
            "command": self.command,
            "args": list(self.args),
            "cwd": self.cwd,
        }


def _require_sdk() -> None:
    if not MCP_SDK_AVAILABLE:
        raise MCPClientUnavailable(
            "the `mcp` package is not installed in this environment; "
            "install Lantern's optional 'mcp' extra to enable a real "
            "MCP client (pip install .[mcp])"
        )


async def _discover_async(target: StdioServerTarget) -> MCPServerDiscovery:
    _require_sdk()
    params = StdioServerParameters(
        command=target.command,
        args=list(target.args),
        cwd=target.cwd,
        env=dict(target.env) if target.env else None,
    )
    async with stdio_client(params) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            tools_result = await session.list_tools()
            tools = tuple(
                MCPToolDescriptor(
                    name=tool.name,
                    description=tool.description or "",
                    input_schema=tool.input_schema or {},
                )
                for tool in tools_result.tools
            )
            resources: tuple[MCPResourceDescriptor, ...] = ()
            try:
                resources_result = await session.list_resources()
                resources = tuple(
                    MCPResourceDescriptor(
                        uri=str(resource.uri),
                        name=resource.name or "",
                        description=resource.description or "",
                        mime_type=resource.mime_type,
                    )
                    for resource in resources_result.resources
                )
            except Exception:
                # Not every server implements resources/list; discovery
                # of tools is the part that matters for capability
                # binding, so a resource-listing failure does not block
                # reporting real, already-observed tool discovery.
                resources = ()

    return MCPServerDiscovery(
        server_id=target.server_id,
        endpoint=f"stdio:{target.command} {' '.join(target.args)}".strip(),
        tools=tools,
        resources=resources,
        notes=("real stdio subprocess discovery",),
    )


async def _call_tool_async(
    target: StdioServerTarget, request: MCPExecutionRequest
) -> dict[str, Any]:
    _require_sdk()
    params = StdioServerParameters(
        command=target.command,
        args=list(target.args),
        cwd=target.cwd,
        env=dict(target.env) if target.env else None,
    )
    async with stdio_client(params) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            result: "mcp_types.CallToolResult" = await session.call_tool(
                request.tool_name, dict(request.arguments)
            )

    if result.is_error:
        text_parts = [
            block.text for block in result.content
            if getattr(block, "type", None) == "text"
        ]
        raise MCPRemoteError(
            f"MCP server reported a tool error for '{request.tool_name}': "
            + ("; ".join(text_parts) if text_parts else "no error detail provided")
        )

    payload: dict[str, Any] = {}
    if result.structured_content is not None:
        payload["structured_content"] = result.structured_content
    text_parts = [
        block.text for block in result.content
        if getattr(block, "type", None) == "text"
    ]
    if text_parts:
        payload["text"] = "\n".join(text_parts)
    payload["raw_content_count"] = len(result.content)
    return payload


def _run(coro):
    """Run an async MCP round-trip from Lantern's synchronous call sites.

    Uses a fresh event loop per call rather than assuming the caller is
    already inside one. Each call is one bounded, complete stdio
    subprocess round-trip -- no persistent background connection is
    held open between calls, which keeps failure modes explicit rather
    than depending on hidden long-lived connection state.
    """
    return asyncio.run(coro)


class StdioMCPClient:
    """Real MCP client bound to one local server subprocess target.

    Implements `mcp_integration.MCPAdapter` (`execute(request) -> Mapping`)
    so it can be passed directly as `MCPIntegrationBoundary(adapter=...)`
    without any change to the existing boundary, capability, delegation,
    provenance, or verification code.
    """

    def __init__(self, target: StdioServerTarget):
        self.target = target

    def discover(self) -> MCPServerDiscovery:
        """Real DISCOVERY only: launches the server, lists tools/resources,
        and shuts the subprocess back down. Does not authorize or bind
        anything -- callers still pass results through
        mcp_integration.infer_bindings() and the existing registry."""
        return _run(_discover_async(self.target))

    def execute(self, request: MCPExecutionRequest) -> Mapping[str, Any]:
        """Satisfies mcp_integration.MCPAdapter. One real call_tool
        round-trip per invocation. Raises MCPRemoteError/MCPClientUnavailable
        rather than fabricating a result on failure."""
        return _run(_call_tool_async(self.target, request))
