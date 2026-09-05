"""
Lantern Protocol Compatibility Layer v0.83

Purpose:
- Negotiate protocol compatibility
- Preserve semantic safety
- Allow future minor-version evolution

Rules:
- Major version mismatch = reject
- Same major + same/minor compatible = allow
- Capabilities decide feature availability

Does not:
- modify beliefs
- modify evidence
- modify Codex state
"""

from dataclasses import dataclass
from typing import Dict, List

from .protocol import PROTOCOL_VERSION


# ============================================================
# Version Parsing
# ============================================================

def parse_version(version):
    # Defense in depth: version comes from untrusted peers. It must be a
    # non-empty string; anything else previously reached .lstrip() and
    # raised an uncaught AttributeError in callers whose except tuples
    # only expect ValueError (e.g. the bootstrap node HTTP handler).
    if not isinstance(version, str) or not version.strip():
        raise ValueError(
            f"protocol version must be a non-empty string, got {version!r}"
        )
    parts = version.lstrip("v").split(".")
    return tuple(int(part) for part in parts)


def major_version(version):
    return parse_version(version)[0]


def compatible_versions(local, remote):
    return major_version(local) == major_version(remote)


# ============================================================
# Capability Negotiation
# ============================================================

DEFAULT_CAPABILITIES = {
    "evidence_exchange": True,
    # Disabled: remote Codex claims are observations, not authority.
    # Remains False until an explicit trust/evaluation protocol
    # exists for letting remote claims influence local state.
    "codex_update": False,
    "belief_query": True,
    "contradiction_tracking": True,
    "snapshot_exchange": True,
    "handshake": True,
    # Disabled by default: a node only advertises this once it has a
    # real lantern.identity.NodeIdentity loaded (private key generated
    # and persisted). Negotiating this capability is purely an
    # "I support challenge/response identity proof" signal -- it never
    # by itself changes trust_status or authority_level. See
    # lantern.identity module docstring.
    "identity_proof": False,
    # Confidential secret transfer over an authenticated session (see
    # lantern.secret_transfer module docstring for why this is a
    # separate capability from evidence_exchange/identity_proof: proof
    # of possession is not confidentiality, and this capability layers
    # an authenticated-encryption channel on top of an existing
    # session rather than replacing or weakening it). Supported by
    # default like evidence_exchange/belief_query -- but, exactly like
    # every other capability, negotiation alone never grants access: a
    # given peer session must still be explicitly authorized for
    # 'secret_transfer' via --authorize before any secret can actually
    # be sent or received.
    "secret_transfer": True,
}


@dataclass
class CompatibilityResult:
    compatible: bool
    reason: str
    shared_capabilities: Dict[str, bool]
    missing_capabilities: List[str]


def negotiate(
    remote_version,
    remote_capabilities,
    local_version=None,
    local_capabilities=None,
):
    local_version = local_version or PROTOCOL_VERSION
    local_capabilities = (
        local_capabilities
        if local_capabilities is not None
        else DEFAULT_CAPABILITIES
    )

    if not compatible_versions(local_version, remote_version):
        return CompatibilityResult(
            compatible=False,
            reason="Major protocol version mismatch",
            shared_capabilities={},
            missing_capabilities=list(remote_capabilities.keys()),
        )

    shared_capabilities = {
        name: value
        for name, value in remote_capabilities.items()
        if local_capabilities.get(name) and value
    }

    missing_capabilities = [
        name
        for name in local_capabilities
        if local_capabilities.get(name) and name not in shared_capabilities
    ]

    return CompatibilityResult(
        compatible=True,
        reason="Compatible",
        shared_capabilities=shared_capabilities,
        missing_capabilities=missing_capabilities,
    )


def can_exchange(result, capability):
    if not result.compatible:
        return False

    return bool(result.shared_capabilities.get(capability))
