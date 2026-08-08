"""
Lantern Peer Heartbeat v0.93

Purpose:
- Report that a node is alive right now (liveness)
- Report protocol identity and node identity
- Report Chronicle position (via the existing continuity watermark)
- Let a node compare its own position against a peer's self-report

Heartbeat does not:
- grant trust or capabilities
- change belief, evidence, or Codex state
- discover peers or maintain a peer registry
- create a new persistence, counting, or hashing mechanism (it wraps
  lantern.continuity.Watermark, which already wraps
  EvidenceKernel.step + Chronicle.chain)

A Heartbeat is a read-only self-report. A ConnectionState is a
read-only, non-authoritative comparison of one heartbeat against
another -- it reuses compatibility.compatible_versions() and
continuity.compare_watermarks() exactly as they already exist,
rather than introducing a second version/continuity policy.
"""

from dataclasses import dataclass
from datetime import datetime, timezone
import time

from .compatibility import compatible_versions
from .continuity import compare_watermarks, parse_remote_watermark


# ============================================================
# Heartbeat (self-report)
# ============================================================

@dataclass(frozen=True)
class Heartbeat:
    node_id: str
    protocol_version: str
    timestamp: str
    uptime_seconds: float
    watermark: dict

    def to_dict(self):
        return {
            "node_id": self.node_id,
            "protocol_version": self.protocol_version,
            "timestamp": self.timestamp,
            "uptime_seconds": self.uptime_seconds,
            "watermark": self.watermark,
        }


def create_heartbeat(node_id, protocol_version, started_monotonic, watermark):
    """Build a liveness/identity/position self-report.

    started_monotonic must come from time.monotonic() taken at node
    startup, so uptime_seconds is immune to wall-clock adjustments.
    watermark is an existing continuity.Watermark (read-only; not
    recomputed here).
    """
    return Heartbeat(
        node_id=node_id,
        protocol_version=protocol_version,
        timestamp=datetime.now(timezone.utc).isoformat(),
        uptime_seconds=max(0.0, time.monotonic() - started_monotonic),
        watermark=watermark.to_dict(),
    )


# ============================================================
# Connection state (non-authoritative comparison)
# ============================================================

UNREACHABLE = "UNREACHABLE"


@dataclass(frozen=True)
class ConnectionState:
    peer_node_id: str
    reachable: bool
    protocol_compatible: bool
    continuity_status: str
    continuity_reason: str
    checked_at: str

    def to_dict(self):
        return {
            "peer_node_id": self.peer_node_id,
            "reachable": self.reachable,
            "protocol_compatible": self.protocol_compatible,
            "continuity_status": self.continuity_status,
            "continuity_reason": self.continuity_reason,
            "checked_at": self.checked_at,
        }


def evaluate_connection(local_protocol_version, local_watermark, peer_heartbeat):
    """Classify a peer's self-reported heartbeat relative to local state.

    peer_heartbeat is a plain dict as produced by Heartbeat.to_dict()
    (e.g. decoded from a /health response), or None if the peer could
    not be reached at all.

    This never grants a capability and never mutates belief, evidence,
    or Codex state. It only reports: was the peer reachable, is its
    protocol major version compatible, and how does its claimed
    Chronicle position compare to ours (via the existing, unmodified
    continuity.compare_watermarks()). A DIVERGED/AHEAD/BEHIND/
    INCOMPATIBLE result is information for the operator, not a trust
    decision -- exactly the posture continuity.py already documents
    for watermark comparison in general.
    """
    checked_at = datetime.now(timezone.utc).isoformat()

    if peer_heartbeat is None:
        return ConnectionState(
            peer_node_id="unknown",
            reachable=False,
            protocol_compatible=False,
            continuity_status=UNREACHABLE,
            continuity_reason="No heartbeat received",
            checked_at=checked_at,
        )

    remote_version = peer_heartbeat["protocol_version"]
    remote_watermark = parse_remote_watermark(peer_heartbeat["watermark"])

    result = compare_watermarks(
        local_protocol_version, remote_version, local_watermark, remote_watermark
    )

    return ConnectionState(
        peer_node_id=peer_heartbeat["node_id"],
        reachable=True,
        protocol_compatible=compatible_versions(local_protocol_version, remote_version),
        continuity_status=result.status,
        continuity_reason=result.reason,
        checked_at=checked_at,
    )
