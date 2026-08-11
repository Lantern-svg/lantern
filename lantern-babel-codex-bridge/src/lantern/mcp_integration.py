"""MCP integration boundary for Lantern.

CORE RULE:
    MCP provides hands. Lantern provides authority.

This module turns MCP into a real Lantern capability interface WITHOUT
letting MCP discovery become Lantern authorization.

What this module does:
    - represent discovered MCP tools/resources as DISCOVERED only
    - map discovered MCP surface area into the EXISTING canonical
      Lantern CapabilityRegistry (capability-level, not tool-level)
    - expose the smallest useful Compass-facing summary of MCP-backed
      capability availability
    - create scoped DelegationRecord values for MCP-backed execution only
      after a caller provides an explicit CapabilityDecision
    - preserve MCP provenance using orchestration.ProvenanceTag with
      source_class="MCP_ENDPOINT"
    - require the canonical capability's VerificationPolicy to remain in
      force even if an MCP tool reports success
    - optionally route through an adapter object if the caller has a real
      MCP client implementation available

What this module does NOT do:
    - perform live MCP discovery by itself
    - open sockets / stdio transports / SSE connections
    - import a third-party `mcp` package
    - grant authorization
    - replace CapabilityRegistry / Compass / MemoryBoundary /
      VerificationPolicy / ProvenanceTag

The Lantern repo currently lacks a real MCP client/transport. So this
module provides the integration layer that can be completed safely now,
with a deliberately explicit adapter boundary for the eventual live
connection.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, Optional, Protocol, Sequence

from .compass import AllowedAction
from .memory_boundary import MemoryBoundary, MemoryWriteResult
from .orchestration import (
    CapabilityDescriptor,
    CapabilityRegistry,
    DelegationRecord,
    ProvenanceTag,
)


MCP_INTEGRATION_VERSION = "0.1"
MCP_PROVENANCE_CLASS = "MCP_ENDPOINT"


@dataclass(frozen=True)
class MCPToolDescriptor:
    name: str
    description: str = ""
    input_schema: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": dict(self.input_schema),
        }


@dataclass(frozen=True)
class MCPResourceDescriptor:
    uri: str
    name: str = ""
    description: str = ""
    mime_type: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "uri": self.uri,
            "name": self.name,
            "description": self.description,
            "mime_type": self.mime_type,
        }


@dataclass(frozen=True)
class MCPServerDiscovery:
    """DISCOVERED only. Not authorization. Not execution."""

    server_id: str
    endpoint: str
    tools: tuple[MCPToolDescriptor, ...] = field(default_factory=tuple)
    resources: tuple[MCPResourceDescriptor, ...] = field(default_factory=tuple)
    notes: tuple[str, ...] = field(default_factory=tuple)

    def tool_names(self) -> frozenset[str]:
        return frozenset(tool.name for tool in self.tools)

    def resource_uris(self) -> frozenset[str]:
        return frozenset(resource.uri for resource in self.resources)

    def to_dict(self) -> dict[str, Any]:
        return {
            "server_id": self.server_id,
            "endpoint": self.endpoint,
            "tools": [tool.to_dict() for tool in self.tools],
            "resources": [resource.to_dict() for resource in self.resources],
            "notes": list(self.notes),
        }


@dataclass(frozen=True)
class MCPCapabilityBinding:
    """A mapping from discovered MCP surface area into the EXISTING
    canonical Lantern capability model.

    This never creates a new capability name. `capability_name` must
    already exist in the registry.
    """

    capability_name: str
    server_id: str
    tool_names: frozenset[str] = field(default_factory=frozenset)
    resource_uris: frozenset[str] = field(default_factory=frozenset)
    notes: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        return {
            "capability_name": self.capability_name,
            "server_id": self.server_id,
            "tool_names": sorted(self.tool_names),
            "resource_uris": sorted(self.resource_uris),
            "notes": list(self.notes),
        }


@dataclass(frozen=True)
class MCPDiscoverySnapshot:
    discoveries: tuple[MCPServerDiscovery, ...] = field(default_factory=tuple)
    bindings: tuple[MCPCapabilityBinding, ...] = field(default_factory=tuple)

    def bound_capabilities(self) -> frozenset[str]:
        return frozenset(binding.capability_name for binding in self.bindings)

    def bindings_for(self, capability_name: str) -> tuple[MCPCapabilityBinding, ...]:
        return tuple(
            binding for binding in self.bindings if binding.capability_name == capability_name
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "discoveries": [item.to_dict() for item in self.discoveries],
            "bindings": [item.to_dict() for item in self.bindings],
        }


@dataclass(frozen=True)
class MCPExecutionRequest:
    capability_name: str
    server_id: str
    tool_name: str
    arguments: Mapping[str, Any] = field(default_factory=dict)
    purpose: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "capability_name": self.capability_name,
            "server_id": self.server_id,
            "tool_name": self.tool_name,
            "arguments": dict(self.arguments),
            "purpose": self.purpose,
        }


@dataclass(frozen=True)
class MCPExecutionResult:
    status: str
    capability_name: str
    server_id: str
    tool_name: str
    raw_result: Optional[Mapping[str, Any]] = None
    raw_error: Optional[str] = None
    provenance: Optional[ProvenanceTag] = None
    verification_required: bool = True
    verification_policy: Optional[dict[str, Any]] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "capability_name": self.capability_name,
            "server_id": self.server_id,
            "tool_name": self.tool_name,
            "raw_result": dict(self.raw_result) if self.raw_result is not None else None,
            "raw_error": self.raw_error,
            "provenance": self.provenance.to_dict() if self.provenance else None,
            "verification_required": self.verification_required,
            "verification_policy": self.verification_policy,
        }


class MCPAdapter(Protocol):
    """Explicit boundary for a real MCP client implementation.

    This repo currently has no actual client/transport. A caller may
    supply one later without changing Lantern's authority model.
    """

    def execute(self, request: MCPExecutionRequest) -> Mapping[str, Any]: ...


class MCPUnavailable(RuntimeError):
    pass


class MCPIntegrationBoundary:
    def __init__(self, registry: CapabilityRegistry, *, adapter: Optional[MCPAdapter] = None):
        self.registry = registry
        self.adapter = adapter

    def summarize_for_compass(self, snapshot: MCPDiscoverySnapshot) -> tuple[AllowedAction, ...]:
        """Compress tool/resource detail into capability-level statements.

        This is intentionally capability-oriented: Compass should think
        in terms of capability names and constraints, not raw tool lists.
        Availability here means DISCOVERED implementation surface only.
        It does not mean authorized.
        """
        discovered = snapshot.bound_capabilities()
        out: list[AllowedAction] = []
        for descriptor in self.registry.all():
            if descriptor.name in discovered:
                out.append(AllowedAction(
                    capability=descriptor.name,
                    allowed=False,
                    reason="MCP implementation discovered; Lantern authorization still required",
                ))
        return tuple(out)

    def integrate_discovery(self, snapshot: MCPDiscoverySnapshot) -> dict[str, Any]:
        """Return a registry-centered view of which canonical Lantern
        capabilities have discovered MCP implementations.

        Does NOT mutate or replace the registry.
        """
        discovered = []
        for binding in snapshot.bindings:
            descriptor = self.registry.get(binding.capability_name)
            if descriptor is None:
                raise ValueError(
                    f"MCP binding references unknown canonical capability: {binding.capability_name}"
                )
            discovered.append({
                "capability": descriptor.to_dict(),
                "mcp_binding": binding.to_dict(),
                "discovered": True,
                "authorized": False,
                "executed": False,
                "verified": False,
            })
        return {
            "count": len(discovered),
            "capabilities": discovered,
        }

    def scoped_delegation_for_mcp(
        self,
        *,
        objective: str,
        capability_name: str,
        server_id: str,
        tool_name: str,
        allowed_arguments: Iterable[str] = (),
    ) -> DelegationRecord:
        descriptor = self._descriptor(capability_name)
        return DelegationRecord(
            objective=objective,
            capability=capability_name,
            worker=f"MCP::{server_id}",
            authority_scope=descriptor.authority_requirements,
            allowed_capabilities=frozenset({capability_name}),
            allowed_information=frozenset(allowed_arguments),
            expected_outputs=descriptor.returns,
            verification_policy=descriptor.verification_policy,
            provenance_requirements=(MCP_PROVENANCE_CLASS, tool_name),
            confirmation_requirements=(
                "human_confirmation_required"
                if descriptor.requires_protected_authority
                else "none"
            ,),
            requires_human_confirmation=descriptor.requires_protected_authority,
        )

    def execute(
        self,
        *,
        request: MCPExecutionRequest,
        delegation: DelegationRecord,
        capability_decision: Any,
    ) -> MCPExecutionResult:
        descriptor = self._descriptor(request.capability_name)
        if request.capability_name not in delegation.allowed_capabilities:
            raise ValueError("delegation does not allow the requested capability")
        if not hasattr(capability_decision, "is_authorized") or not capability_decision.is_authorized(request.capability_name):
            raise PermissionError(
                "MCP discovery/availability does not equal Lantern authorization"
            )

        provenance = ProvenanceTag(
            source_class=MCP_PROVENANCE_CLASS,
            identifier=f"{request.server_id}:{request.tool_name}",
            note=request.purpose,
        )

        if self.adapter is None:
            return MCPExecutionResult(
                status="UNAVAILABLE",
                capability_name=request.capability_name,
                server_id=request.server_id,
                tool_name=request.tool_name,
                raw_error="no MCP client adapter is configured in this Lantern environment",
                provenance=provenance,
                verification_required=True,
                verification_policy=(descriptor.verification_policy.to_dict() if descriptor.verification_policy else None),
            )

        result = self.adapter.execute(request)
        return MCPExecutionResult(
            status="RETURNED",
            capability_name=request.capability_name,
            server_id=request.server_id,
            tool_name=request.tool_name,
            raw_result=dict(result),
            provenance=provenance,
            verification_required=True,
            verification_policy=(descriptor.verification_policy.to_dict() if descriptor.verification_policy else None),
        )

    def memory_write(
        self,
        boundary: MemoryBoundary,
        *,
        path: str,
        content: str,
        authorize: bool = False,
    ) -> MemoryWriteResult:
        """Route memory mutation through the EXISTING MemoryBoundary.
        This module never writes around it.
        """
        return boundary.replace(path, content, authorize=authorize)

    def _descriptor(self, capability_name: str) -> CapabilityDescriptor:
        descriptor = self.registry.get(capability_name)
        if descriptor is None:
            raise ValueError(f"unknown capability: {capability_name}")
        return descriptor


def infer_bindings(
    registry: CapabilityRegistry,
    discoveries: Sequence[MCPServerDiscovery],
) -> MCPDiscoverySnapshot:
    """Very small discovery->capability compression layer.

    Lantern reasons at capability granularity, so this function maps raw
    tool names/resources into canonical capability names when there is a
    clear, conservative relationship.

    The mapping intentionally prefers *underclaiming* over magical
    inference. Unknown tools stay discovered-but-unbound.
    """
    bindings: list[MCPCapabilityBinding] = []
    registry_names = {item.name for item in registry.all()}

    tool_map = {
        "read": "software_engineering",
        "write": "software_engineering",
        "edit": "software_engineering",
        "apply_patch": "software_engineering",
        "exec": "testing",
        "process": "testing",
        "web_search": "web_research",
        "web_fetch": "web_research",
        "browser": "web_research",
        "message": "messaging",
        "canvas": "visualization",
        "file_fetch": "device_interaction",
        "file_write": "device_interaction",
    }

    for discovery in discoveries:
        by_capability: dict[str, dict[str, set[str]]] = {}
        for tool in discovery.tools:
            capability_name = tool_map.get(tool.name)
            if capability_name is None or capability_name not in registry_names:
                continue
            bucket = by_capability.setdefault(
                capability_name, {"tools": set(), "resources": set()}
            )
            bucket["tools"].add(tool.name)
        for capability_name, bucket in by_capability.items():
            bindings.append(MCPCapabilityBinding(
                capability_name=capability_name,
                server_id=discovery.server_id,
                tool_names=frozenset(bucket["tools"]),
                resource_uris=frozenset(bucket["resources"]),
                notes=("conservative inference from discovered MCP tool names",),
            ))

    return MCPDiscoverySnapshot(discoveries=tuple(discoveries), bindings=tuple(bindings))
