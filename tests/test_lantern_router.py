"""
Lantern Message Router Tests

Locks:
- capability-gated delivery (granted vs missing)
- unregistered handler rejection
- version incompatibility blocks delivery even if capability name matches
- unmapped message types (no capability requirement) still need a handler
- register() overwrites a prior handler for the same message type
"""

from lantern.compatibility import negotiate
from lantern.protocol import (
    PROTOCOL_VERSION,
    create_evidence_request,
    create_message,
    create_observation_share,
)
from lantern.router import LanternRouter, RouteResult


def test_route_delivers_when_capability_granted():
    router = LanternRouter()
    received = []
    router.register("OBSERVATION_SHARE", received.append)

    compat = negotiate(PROTOCOL_VERSION, {"evidence_exchange": True})
    message = create_observation_share("lantern_a", {"content": "x"})

    result = router.route(message, compat)

    assert result == RouteResult(True, "OBSERVATION_SHARE", "Delivered")
    assert received == [message]


def test_route_rejects_when_capability_missing():
    router = LanternRouter()
    received = []
    router.register("OBSERVATION_SHARE", received.append)

    compat = negotiate(PROTOCOL_VERSION, {"codex_update": True})
    message = create_observation_share("lantern_a", {"content": "x"})

    result = router.route(message, compat)

    assert result.accepted is False
    assert result.reason == "Capability unavailable: evidence_exchange"
    assert received == []


def test_route_rejects_when_no_handler_registered():
    router = LanternRouter()
    compat = negotiate(PROTOCOL_VERSION, {"belief_query": True})
    message = create_evidence_request("lantern_a", "concept_x")

    result = router.route(message, compat)

    assert result.accepted is False
    assert result.reason == "No handler registered"


def test_route_unmapped_message_type_still_needs_handler():
    router = LanternRouter()
    compat = negotiate(PROTOCOL_VERSION, {})
    message = create_message("CUSTOM_TYPE", "lantern_a", {})

    result = router.route(message, compat)

    assert result.accepted is False
    assert result.reason == "No handler registered"


def test_route_unmapped_message_type_delivers_once_handler_registered():
    router = LanternRouter()
    received = []
    router.register("CUSTOM_TYPE", received.append)

    compat = negotiate(PROTOCOL_VERSION, {})
    message = create_message("CUSTOM_TYPE", "lantern_a", {})

    result = router.route(message, compat)

    assert result.accepted is True
    assert received == [message]


def test_route_blocked_by_major_version_incompatibility():
    router = LanternRouter()
    received = []
    router.register("OBSERVATION_SHARE", received.append)

    compat = negotiate("99.0", {"evidence_exchange": True})
    message = create_observation_share("lantern_a", {"content": "x"})

    result = router.route(message, compat)

    assert result.accepted is False
    assert received == []


def test_register_overwrites_previous_handler():
    router = LanternRouter()
    calls = []
    router.register("CUSTOM_TYPE", lambda m: calls.append("first"))
    router.register("CUSTOM_TYPE", lambda m: calls.append("second"))

    compat = negotiate(PROTOCOL_VERSION, {})
    message = create_message("CUSTOM_TYPE", "lantern_a", {})

    router.route(message, compat)

    assert calls == ["second"]
