"""Lantern Peer Heartbeat tests.

Locks in: heartbeat is a read-only self-report (liveness + identity +
Chronicle position via the existing continuity watermark); connection-state
evaluation never grants trust/capabilities and never mutates belief,
evidence, or Codex state; it only reuses compatibility.compatible_versions()
and continuity.compare_watermarks() exactly as they already exist.
"""

import time

from lantern.compatibility import DEFAULT_CAPABILITIES
from lantern.continuity import AHEAD, BEHIND, COMPATIBLE, DIVERGED, INCOMPATIBLE, Watermark
from lantern.core import Lantern
from lantern.heartbeat import (
    ConnectionState,
    Heartbeat,
    UNREACHABLE,
    create_heartbeat,
    evaluate_connection,
)


def test_heartbeat_reports_liveness_identity_and_watermark_without_mutation():
    lantern = Lantern()
    lantern.observe("hello", "test", 1.0)
    watermark = Watermark(step=lantern.kernel.step, chain="GENESIS")

    before_step = lantern.kernel.step
    before_observations = len(lantern.kernel.observations)

    heartbeat = create_heartbeat(
        node_id="lantern-b",
        protocol_version="0.82",
        started_monotonic=time.monotonic() - 5,
        watermark=watermark,
    )

    assert isinstance(heartbeat, Heartbeat)
    assert heartbeat.node_id == "lantern-b"
    assert heartbeat.protocol_version == "0.82"
    assert heartbeat.uptime_seconds >= 5
    assert heartbeat.watermark == {"step": before_step, "chain": "GENESIS"}

    # Building a heartbeat must not have touched kernel state.
    assert lantern.kernel.step == before_step
    assert len(lantern.kernel.observations) == before_observations


def test_heartbeat_to_dict_round_trips_for_wire_transport():
    watermark = Watermark(step=3, chain="abc123")
    heartbeat = create_heartbeat("lantern-a", "0.82", time.monotonic(), watermark)
    data = heartbeat.to_dict()

    assert data["node_id"] == "lantern-a"
    assert data["protocol_version"] == "0.82"
    assert data["watermark"] == {"step": 3, "chain": "abc123"}
    assert "timestamp" in data
    assert "uptime_seconds" in data


def test_connection_state_unreachable_when_no_heartbeat_received():
    local_watermark = Watermark(step=0, chain="GENESIS")
    state = evaluate_connection("0.82", local_watermark, None)

    assert isinstance(state, ConnectionState)
    assert state.reachable is False
    assert state.protocol_compatible is False
    assert state.continuity_status == UNREACHABLE


def test_connection_state_compatible_when_same_step_and_chain():
    local_watermark = Watermark(step=2, chain="hash-x")
    peer_heartbeat = {
        "node_id": "lantern-b",
        "protocol_version": "0.82",
        "watermark": {"step": 2, "chain": "hash-x"},
    }

    state = evaluate_connection("0.82", local_watermark, peer_heartbeat)

    assert state.reachable is True
    assert state.protocol_compatible is True
    assert state.continuity_status == COMPATIBLE
    assert state.peer_node_id == "lantern-b"


def test_connection_state_behind_ahead_and_diverged_are_information_only():
    local_watermark = Watermark(step=5, chain="hash-local")

    behind = evaluate_connection(
        "0.82", local_watermark,
        {"node_id": "b", "protocol_version": "0.82", "watermark": {"step": 2, "chain": "x"}},
    )
    assert behind.continuity_status == BEHIND

    ahead = evaluate_connection(
        "0.82", local_watermark,
        {"node_id": "b", "protocol_version": "0.82", "watermark": {"step": 9, "chain": "x"}},
    )
    assert ahead.continuity_status == AHEAD

    diverged = evaluate_connection(
        "0.82", local_watermark,
        {"node_id": "b", "protocol_version": "0.82", "watermark": {"step": 5, "chain": "hash-other"}},
    )
    assert diverged.continuity_status == DIVERGED


def test_connection_state_incompatible_major_version_overrides_watermark():
    local_watermark = Watermark(step=1, chain="x")
    peer_heartbeat = {
        "node_id": "b",
        "protocol_version": "9.0",
        "watermark": {"step": 1, "chain": "x"},
    }

    state = evaluate_connection("0.82", local_watermark, peer_heartbeat)

    assert state.reachable is True
    assert state.protocol_compatible is False
    assert state.continuity_status == INCOMPATIBLE


def test_connection_state_never_grants_capabilities_or_mutates_belief():
    """A ConnectionState is pure reporting: it must never look like a
    capability grant. codex_update must stay False regardless of what a
    peer's heartbeat reports, and evaluate_connection() must take no
    Lantern/agent object at all -- it has nothing to mutate.
    """
    lantern = Lantern()
    before_step = lantern.kernel.step
    before_evidence = len(lantern.kernel.evidence)

    local_watermark = Watermark(step=lantern.kernel.step, chain="GENESIS")
    peer_heartbeat = {
        "node_id": "b",
        "protocol_version": "0.82",
        "watermark": {"step": 999, "chain": "claims-to-be-way-ahead"},
    }

    evaluate_connection("0.82", local_watermark, peer_heartbeat)

    assert lantern.kernel.step == before_step
    assert len(lantern.kernel.evidence) == before_evidence
    assert DEFAULT_CAPABILITIES["codex_update"] is False
