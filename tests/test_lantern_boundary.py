"""
Tests for lantern.boundary.LanternBoundary.

LanternBoundary is a thin composition wrapper over the already-tested
router/compatibility/handshake modules. These tests check the wiring
(that it delegates correctly and returns the real, package-level
RouteResult/CompatibilityResult/HandshakeRequest types) rather than
re-testing negotiation/routing logic already covered in
test_lantern_router.py, test_lantern_compatibility.py, and
test_lantern_handshake.py.
"""

from lantern import RouteResult, CompatibilityResult
from lantern.boundary import LanternBoundary
from lantern.handshake import HandshakeRequest
from lantern.protocol import create_message


def test_connect_returns_compatibility_result():
    boundary = LanternBoundary()

    compat = boundary.connect("0.82", {"evidence_exchange": True})

    assert isinstance(compat, CompatibilityResult)
    assert compat.compatible is True


def test_connect_rejects_major_version_mismatch():
    boundary = LanternBoundary()

    compat = boundary.connect("9.0.0", {})

    assert compat.compatible is False


def test_receive_delivers_to_registered_handler():
    boundary = LanternBoundary()
    received = []
    boundary.register("OBSERVATION_SHARE", lambda msg: received.append(msg))

    compat = boundary.connect("0.82", {"evidence_exchange": True})
    message = create_message("OBSERVATION_SHARE", "lantern_a", {"x": 1})
    result = boundary.receive(message, compat)

    assert isinstance(result, RouteResult)
    assert result.accepted is True
    assert len(received) == 1


def test_receive_blocks_when_capability_missing():
    boundary = LanternBoundary()
    boundary.register("OBSERVATION_SHARE", lambda msg: None)

    compat = boundary.connect("0.82", {})
    message = create_message("OBSERVATION_SHARE", "lantern_a", {})
    result = boundary.receive(message, compat)

    assert result.accepted is False


def test_handshake_returns_real_handshake_request():
    boundary = LanternBoundary()

    handshake = boundary.handshake()

    assert isinstance(handshake, HandshakeRequest)
    assert handshake.protocol_version == "0.82"
    assert handshake.node_id


def test_boundary_uses_a_fresh_router_per_instance():
    a = LanternBoundary()
    b = LanternBoundary()

    a.register("OBSERVATION_SHARE", lambda msg: None)

    assert "OBSERVATION_SHARE" not in b.router.handlers
