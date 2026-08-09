"""
Lantern Protocol Tests

Locks:
- message creation
- encode/decode stability
- factory formats
- validation behavior
- version handling
"""

from lantern.protocol import (
    PROTOCOL_VERSION,
    ProtocolMessage,
    create_codex_update,
    create_evidence_request,
    create_message,
    create_observation_share,
    validate_message,
)


# ==================================================
# Message Core
# ==================================================

def test_message_round_trip():
    original = create_message("TEST", "lantern_a", {"value": 123})

    encoded = original.encode()
    decoded = ProtocolMessage.decode(encoded)

    assert decoded.message_id == original.message_id
    assert decoded.protocol == PROTOCOL_VERSION
    assert decoded.payload["value"] == 123


# ==================================================
# Factories
# ==================================================

def test_observation_share():
    message = create_observation_share(
        "lantern_a",
        {"content": "water freezes", "source": "experiment"},
    )

    assert message.message_type == "OBSERVATION_SHARE"
    assert "observation" in message.payload


def test_evidence_request():
    message = create_evidence_request("lantern_a", "water_freezing")

    assert message.message_type == "EVIDENCE_REQUEST"
    assert message.payload["concept"] == "water_freezing"


def test_codex_update():
    message = create_codex_update(
        "lantern_a",
        "water_freezing",
        0.82,
        ["e1", "e2"],
    )

    assert message.message_type == "CODEX_UPDATE"
    assert message.payload["confidence"] == 0.82


# ==================================================
# Validation
# ==================================================

def test_valid_message_passes():
    message = create_message("TEST", "source", {})

    assert validate_message(message) is True


def test_invalid_version_fails():
    message = create_message("TEST", "source", {})
    message.protocol = "999.0"

    assert validate_message(message) is False


def test_missing_field_fails_without_raising():
    # A ProtocolMessage instance that is missing a required attribute
    # (e.g. reconstructed from a truncated/corrupted wire payload).
    # validate_message() must reject this, not crash: asdict() raises
    # AttributeError on a dataclass instance with an unset field, so
    # validate_message() has to guard against that explicitly.
    message = object.__new__(ProtocolMessage)
    message.message_id = "x"
    message.protocol = PROTOCOL_VERSION
    message.message_type = "TEST"
    message.source = "source"
    message.timestamp = "now"
    # payload intentionally left unset

    assert validate_message(message) is False


def test_non_dataclass_input_fails_without_raising():
    assert validate_message({"not": "a protocol message"}) is False


# ==================================================
# Contract Stability
# ==================================================

def test_protocol_version_exists():
    assert isinstance(PROTOCOL_VERSION, str)
    assert len(PROTOCOL_VERSION) > 0
