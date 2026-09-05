"""
Lantern Handshake Protocol v0.82

Purpose:
- Establish compatibility before exchange
- Exchange capabilities
- Prevent silent semantic mismatch

Handshake does not:
- share private memory
- modify beliefs
- alter Codex state

It only answers:
"Can these Lantern instances communicate safely?"
"""

from dataclasses import dataclass
from datetime import datetime, timezone
import uuid

from .protocol import PROTOCOL_VERSION
from .compatibility import compatible_versions

# ============================================================
# Capabilities
# ============================================================
#
# Canonical source: lantern.compatibility.DEFAULT_CAPABILITIES.
#
# Handshake used to keep its own copy of this dict. That let
# codex_update drift (True here vs False in compatibility.py)
# even though this is the dict actually advertised over the wire
# by LanternBoundary.handshake() -> create_handshake(). There must
# be exactly one capability registry; this import IS that
# consolidation, not a re-declaration.
from .compatibility import DEFAULT_CAPABILITIES


# ============================================================
# Handshake Messages
# ============================================================

@dataclass
class HandshakeRequest:
    node_id: str
    protocol_version: str
    capabilities: dict
    timestamp: str


@dataclass
class HandshakeResponse:
    node_id: str
    accepted: bool
    protocol_version: str
    shared_capabilities: dict
    reason: str
    timestamp: str


# ============================================================
# Create Handshake
# ============================================================

def create_handshake(capabilities=None):
    return HandshakeRequest(
        node_id=str(uuid.uuid4()),
        protocol_version=PROTOCOL_VERSION,
        capabilities=(
            capabilities
            if capabilities is not None
            else DEFAULT_CAPABILITIES.copy()
        ),
        timestamp=datetime.now(timezone.utc).isoformat(),
    )


# ============================================================
# Compatibility Check
# ============================================================

def evaluate_handshake(request: HandshakeRequest, supported_capabilities=None, responder_node_id=None):
    """Evaluate a peer's HandshakeRequest and build this node's response.

    responder_node_id: this node's own configured node_id, echoed back on
    the response exactly as-is. Prior to this parameter, every response
    generated a fresh uuid4() per call -- meaning the same physical node
    appeared to claim a different node_id on every handshake response,
    which is inconsistent with node_id being a stable identifier and
    breaks any attempt to bind identity to node_id downstream (see
    lantern.identity). Defaulting to None preserves the old standalone
    behavior (fresh uuid4()) for any caller that does not yet have a
    configured node_id to pass -- this keeps the function usable without
    forcing every existing call site to change, while every call site that
    represents a real, running node should pass its real node_id.
    """
    if supported_capabilities is None:
        supported_capabilities = DEFAULT_CAPABILITIES.copy()

    response_node_id = responder_node_id if responder_node_id is not None else str(uuid.uuid4())

    # Defense in depth: evaluate_handshake() may be called directly
    # (not only via the HTTP handler), so malformed fields must be
    # rejected here too, and must never raise an uncaught
    # AttributeError/TypeError from attribute access on untrusted input.
    if not isinstance(request.protocol_version, str) or not request.protocol_version.strip():
        return HandshakeResponse(
            node_id=response_node_id,
            accepted=False,
            protocol_version=PROTOCOL_VERSION,
            shared_capabilities={},
            reason="Malformed protocol version",
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

    if not isinstance(request.capabilities, dict):
        return HandshakeResponse(
            node_id=response_node_id,
            accepted=False,
            protocol_version=PROTOCOL_VERSION,
            shared_capabilities={},
            reason="Malformed capabilities",
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

    try:
        versions_compatible = compatible_versions(PROTOCOL_VERSION, request.protocol_version)
    except ValueError:
        return HandshakeResponse(
            node_id=response_node_id,
            accepted=False,
            protocol_version=PROTOCOL_VERSION,
            shared_capabilities={},
            reason="Malformed protocol version",
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

    if not versions_compatible:
        return HandshakeResponse(
            node_id=response_node_id,
            accepted=False,
            protocol_version=PROTOCOL_VERSION,
            shared_capabilities={},
            reason="Major protocol version mismatch",
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

    shared = {}

    for capability, enabled in request.capabilities.items():
        if enabled and supported_capabilities.get(capability, False):
            shared[capability] = True

    return HandshakeResponse(
        node_id=response_node_id,
        accepted=True,
        protocol_version=PROTOCOL_VERSION,
        shared_capabilities=shared,
        reason="Compatible",
        timestamp=datetime.now(timezone.utc).isoformat(),
    )


# ============================================================
# Utility
# ============================================================

def handshake_summary(response: HandshakeResponse):
    return {
        "accepted": response.accepted,
        "protocol": response.protocol_version,
        "capabilities": list(response.shared_capabilities.keys()),
        "reason": response.reason,
    }
