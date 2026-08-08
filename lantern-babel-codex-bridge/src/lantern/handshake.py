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

def evaluate_handshake(request: HandshakeRequest, supported_capabilities=None):
    if supported_capabilities is None:
        supported_capabilities = DEFAULT_CAPABILITIES.copy()

    if not compatible_versions(PROTOCOL_VERSION, request.protocol_version):
        return HandshakeResponse(
            node_id=str(uuid.uuid4()),
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
        node_id=str(uuid.uuid4()),
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
