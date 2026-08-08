"""
Lantern Handshake Protocol Tests

Locks:
- handshake request creation defaults
- compatible handshake acceptance + capability intersection
- major version mismatch rejection (v0.92: delegated to
  compatibility.compatible_versions, not strict string equality)
- same-major, different-minor requests proceed to capability
  negotiation (v0.92)
- capabilities the responder doesn't support are dropped
- capabilities the requester disabled are dropped
- handshake_summary() shape
- single capability authority (v0.90): handshake.DEFAULT_CAPABILITIES
  is compatibility.DEFAULT_CAPABILITIES, not an independent copy
"""

from lantern.compatibility import compatible_versions
from lantern.handshake import (
    DEFAULT_CAPABILITIES,
    create_handshake,
    evaluate_handshake,
    handshake_summary,
)
from lantern.protocol import PROTOCOL_VERSION


def test_handshake_capabilities_are_the_canonical_compatibility_dict():
    # v0.90 -- Single Capability Authority.
    # handshake.py must not maintain its own capability dict.
    # It imports the one defined in compatibility.py, so the two
    # can never silently drift again.
    from lantern.compatibility import DEFAULT_CAPABILITIES as COMPAT_CAPABILITIES

    assert DEFAULT_CAPABILITIES is COMPAT_CAPABILITIES


def test_codex_update_is_disabled_in_handshake_capabilities():
    assert DEFAULT_CAPABILITIES["codex_update"] is False


def test_create_handshake_defaults():
    request = create_handshake()

    assert request.protocol_version == PROTOCOL_VERSION
    assert request.capabilities == DEFAULT_CAPABILITIES
    assert request.node_id
    assert request.timestamp


def test_create_handshake_custom_capabilities():
    request = create_handshake(capabilities={"evidence_exchange": True})

    assert request.capabilities == {"evidence_exchange": True}


def test_evaluate_handshake_accepts_compatible_request():
    request = create_handshake()

    response = evaluate_handshake(request)

    assert response.accepted is True
    assert response.protocol_version == PROTOCOL_VERSION
    # codex_update is disabled in DEFAULT_CAPABILITIES (v0.90 single
    # capability authority: handshake now imports compatibility's
    # dict directly), so it is never advertised as shared even
    # though the requester's own capabilities dict contains the key.
    assert response.shared_capabilities == {
        name: value
        for name, value in DEFAULT_CAPABILITIES.items()
        if value
    }
    assert "codex_update" not in response.shared_capabilities
    assert response.reason == "Compatible"


def test_evaluate_handshake_rejects_major_version_mismatch():
    request = create_handshake()
    request.protocol_version = "1.0"

    response = evaluate_handshake(request)

    assert response.accepted is False
    assert response.shared_capabilities == {}
    assert response.reason == "Major protocol version mismatch"


def test_evaluate_handshake_accepts_same_major_different_minor():
    request = create_handshake()
    request.protocol_version = "0.1"

    assert compatible_versions(PROTOCOL_VERSION, "0.1") is True

    response = evaluate_handshake(request)

    assert response.accepted is True
    assert response.reason == "Compatible"


def test_evaluate_handshake_delegates_to_compatibility_layer():
    import inspect
    from lantern import handshake as handshake_module

    source = inspect.getsource(handshake_module.evaluate_handshake)
    assert "compatible_versions(" in source
    assert "protocol_version != PROTOCOL_VERSION" not in source


def test_evaluate_handshake_drops_unsupported_capabilities():
    request = create_handshake(
        capabilities={"evidence_exchange": True, "made_up_capability": True}
    )

    response = evaluate_handshake(request)

    assert response.accepted is True
    assert response.shared_capabilities == {"evidence_exchange": True}
    assert "made_up_capability" not in response.shared_capabilities


def test_evaluate_handshake_drops_requester_disabled_capabilities():
    request = create_handshake(
        capabilities={"evidence_exchange": True, "codex_update": False}
    )

    response = evaluate_handshake(request)

    assert response.shared_capabilities == {"evidence_exchange": True}
    assert "codex_update" not in response.shared_capabilities


def test_evaluate_handshake_respects_supported_capabilities_override():
    request = create_handshake()

    response = evaluate_handshake(
        request, supported_capabilities={"evidence_exchange": True}
    )

    assert response.shared_capabilities == {"evidence_exchange": True}


def test_handshake_summary_shape():
    request = create_handshake()
    response = evaluate_handshake(request)

    summary = handshake_summary(response)

    assert summary["accepted"] is True
    assert summary["protocol"] == PROTOCOL_VERSION
    # codex_update is disabled, so it never reaches shared_capabilities
    # and therefore never appears in the summary.
    assert set(summary["capabilities"]) == {
        name for name, value in DEFAULT_CAPABILITIES.items() if value
    }
    assert "codex_update" not in summary["capabilities"]
    assert summary["reason"] == "Compatible"
