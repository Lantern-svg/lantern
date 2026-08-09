"""
Lantern Protocol Compatibility Tests

Locks:
- version parsing
- major-version compatibility rule
- capability negotiation (shared / missing)
- rejection on major version mismatch
- can_exchange() helper
"""

from lantern.compatibility import (
    CompatibilityResult,
    can_exchange,
    compatible_versions,
    major_version,
    negotiate,
    parse_version,
)
from lantern.protocol import PROTOCOL_VERSION


def test_parse_version():
    assert parse_version("0.82") == (0, 82)
    assert parse_version("v1.2.3") == (1, 2, 3)


def test_codex_update_is_disabled_by_default():
    # V0.89.1 -- Trust Boundary Alignment.
    # Remote Codex claims are observations, not authority.
    # codex_update remains disabled until an explicit trust/
    # evaluation protocol exists for allowing remote claims to
    # influence local state.
    from lantern.compatibility import DEFAULT_CAPABILITIES

    assert DEFAULT_CAPABILITIES["codex_update"] is False


def test_major_version():
    assert major_version("0.82") == 0
    assert major_version("1.0") == 1


def test_compatible_versions_same_major():
    assert compatible_versions("0.82", "0.1") is True
    assert compatible_versions("0.82", "0.99") is True


def test_compatible_versions_different_major():
    assert compatible_versions("0.82", "1.0") is False


def test_compatible_versions_worked_examples_from_v092_policy():
    # 0.89 <-> 0.90: same major -> version-compatible
    assert compatible_versions("0.89", "0.90") is True
    # 0.90 <-> 0.91: same major -> version-compatible
    assert compatible_versions("0.90", "0.91") is True
    # 1.0 <-> 0.90: different major -> incompatible
    assert compatible_versions("1.0", "0.90") is False


def test_malformed_remote_version_raises_rather_than_silently_accepting():
    # An explicit policy means a malformed version must not be
    # treated as "looks similar enough". parse_version() raises on
    # non-numeric parts; compatible_versions() propagates that
    # rather than swallowing it into a false-positive match.
    import pytest

    with pytest.raises(ValueError):
        compatible_versions("0.82", "not-a-version")


def test_negotiate_compatible_returns_shared_and_missing():
    result = negotiate(
        remote_version=PROTOCOL_VERSION,
        remote_capabilities={"evidence_exchange": True, "codex_update": True},
    )

    assert isinstance(result, CompatibilityResult)
    assert result.compatible is True
    assert result.reason == "Compatible"
    # codex_update is disabled locally (v0.89.1 trust boundary), so
    # even though the remote offers it, it never becomes shared.
    assert result.shared_capabilities == {
        "evidence_exchange": True,
    }
    assert "belief_query" in result.missing_capabilities
    assert "evidence_exchange" not in result.missing_capabilities


def test_negotiate_rejects_major_version_mismatch():
    result = negotiate(
        remote_version="2.0",
        remote_capabilities={"evidence_exchange": True},
    )

    assert result.compatible is False
    assert result.shared_capabilities == {}
    assert result.missing_capabilities == ["evidence_exchange"]
    assert result.reason == "Major protocol version mismatch"


def test_negotiate_respects_local_capabilities_override():
    result = negotiate(
        remote_version=PROTOCOL_VERSION,
        remote_capabilities={"evidence_exchange": True, "codex_update": True},
        local_capabilities={"evidence_exchange": True},
    )

    assert result.shared_capabilities == {"evidence_exchange": True}
    assert result.missing_capabilities == []


def test_can_exchange_true_when_shared_and_compatible():
    result = negotiate(
        remote_version=PROTOCOL_VERSION,
        remote_capabilities={"evidence_exchange": True},
    )

    assert can_exchange(result, "evidence_exchange") is True


def test_can_exchange_false_when_not_shared():
    result = negotiate(
        remote_version=PROTOCOL_VERSION,
        remote_capabilities={"evidence_exchange": True},
    )

    assert can_exchange(result, "belief_query") is False


def test_can_exchange_false_when_incompatible():
    result = negotiate(
        remote_version="2.0",
        remote_capabilities={"evidence_exchange": True},
    )

    assert can_exchange(result, "evidence_exchange") is False
