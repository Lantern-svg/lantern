"""Tests for the Discord -> Lantern observation bridge (Phase 1).

Covers:
- Valid Discord message -> Observation
- Missing author -> explicitly marked unknown, not rejected
- Missing timestamp -> handled explicitly (synthesized + flagged, not rejected)
- Empty content -> handled explicitly (accepted, flagged as explicitly empty)
- Malformed payload -> rejected without corrupting Lantern state
- Same message replay -> deterministic behavior
- Source metadata preserved
- Observation does not automatically become belief
- Contradictory observations can reach Lantern's contradiction detector
- Discord transport failure does not mutate Lantern state
"""

import pytest

from lantern.core import Lantern
from lantern.discord_bridge import (
    DiscordTransportError,
    discord_message_to_observation,
    fetch_discord_message,
    normalize_discord_message,
)


def make_valid_payload(**overrides):
    payload = {
        "id": "msg_001",
        "channel_id": "chan_001",
        "guild_id": "guild_001",
        "content": "PROTOCOL_SUPPORTED = TRUE",
        "author": {"id": "user_001", "username": "alice"},
        "timestamp": "2026-08-10T20:00:00+00:00",
    }
    payload.update(overrides)
    return payload


# ==================================================
# Valid message -> Observation
# ==================================================

def test_valid_discord_message_becomes_observation():
    lantern = Lantern()
    result = discord_message_to_observation(lantern, make_valid_payload())

    assert result.accepted is True
    assert result.observation_id is not None
    assert result.rejection_reason is None
    assert result.source == "discord:chan_001:user_001"

    obs = lantern.kernel.observations[result.observation_id]
    assert obs.content == "PROTOCOL_SUPPORTED = TRUE"
    assert obs.metadata["channel_id"] == "chan_001"
    assert obs.metadata["message_id"] == "msg_001"
    assert obs.metadata["guild_id"] == "guild_001"


# ==================================================
# Missing author -> explicitly marked unknown
# ==================================================

def test_missing_author_marked_unknown_not_rejected():
    lantern = Lantern()
    payload = make_valid_payload()
    del payload["author"]

    result = discord_message_to_observation(lantern, payload)

    assert result.accepted is True
    assert result.normalized.author == "unknown"
    assert result.normalized.author_known is False
    obs = lantern.kernel.observations[result.observation_id]
    assert obs.metadata["author"] == "unknown"
    assert obs.metadata["author_known"] is False


# ==================================================
# Missing timestamp -> handled explicitly
# ==================================================

def test_missing_timestamp_synthesized_and_flagged():
    lantern = Lantern()
    payload = make_valid_payload()
    del payload["timestamp"]

    result = discord_message_to_observation(lantern, payload)

    assert result.accepted is True
    assert result.normalized.timestamp_known is False
    assert result.normalized.timestamp  # synthesized, non-empty
    obs = lantern.kernel.observations[result.observation_id]
    assert obs.metadata["timestamp_known"] is False


# ==================================================
# Empty content -> handled explicitly
# ==================================================

def test_empty_content_accepted_and_flagged():
    lantern = Lantern()
    payload = make_valid_payload(content="")

    result = discord_message_to_observation(lantern, payload)

    assert result.accepted is True
    obs = lantern.kernel.observations[result.observation_id]
    assert obs.content == ""
    assert obs.metadata["content_explicitly_empty"] is True


def test_null_content_treated_as_empty_and_flagged():
    lantern = Lantern()
    payload = make_valid_payload(content=None)

    result = discord_message_to_observation(lantern, payload)

    assert result.accepted is True
    obs = lantern.kernel.observations[result.observation_id]
    assert obs.content == ""
    assert obs.metadata["content_explicitly_empty"] is True


# ==================================================
# Malformed payload -> rejected without corrupting Lantern state
# ==================================================

@pytest.mark.parametrize(
    "bad_payload",
    [
        None,
        "not a dict",
        42,
        [],
        {},
        {"content": "no id or channel"},
        {"id": "msg_x"},  # missing channel_id
        {"channel_id": "chan_x"},  # missing id
    ],
)
def test_malformed_payload_rejected_without_state_mutation(bad_payload):
    lantern = Lantern()
    step_before = lantern.kernel.step
    observation_count_before = len(lantern.kernel.observations)

    result = discord_message_to_observation(lantern, bad_payload)

    assert result.accepted is False
    assert result.observation_id is None
    assert result.rejection_reason is not None
    assert lantern.kernel.step == step_before
    assert len(lantern.kernel.observations) == observation_count_before


# ==================================================
# Same message replay -> deterministic behavior
# ==================================================

def test_same_message_replay_is_deterministic_in_shape():
    lantern = Lantern()
    payload = make_valid_payload()

    result_1 = discord_message_to_observation(lantern, payload)
    result_2 = discord_message_to_observation(lantern, payload)

    # Each call creates a new Observation (Lantern does not dedupe internally
    # today) but the *shape* of the result must be identical and deterministic.
    assert result_1.accepted is True
    assert result_2.accepted is True
    assert result_1.source == result_2.source
    assert result_1.normalized.content == result_2.normalized.content
    assert result_1.normalized.author == result_2.normalized.author
    assert result_1.normalized.message_id == result_2.normalized.message_id
    # Observation ids are expected to differ (two distinct observation events).
    assert result_1.observation_id != result_2.observation_id


def test_normalize_is_pure_and_deterministic():
    payload = make_valid_payload()
    n1 = normalize_discord_message(payload)
    n2 = normalize_discord_message(payload)

    assert n1.valid == n2.valid
    assert n1.content == n2.content
    assert n1.author == n2.author
    assert n1.timestamp == n2.timestamp
    assert n1.channel_id == n2.channel_id
    assert n1.message_id == n2.message_id


# ==================================================
# Source metadata preserved
# ==================================================

def test_source_metadata_fully_preserved():
    lantern = Lantern()
    payload = make_valid_payload()

    result = discord_message_to_observation(lantern, payload)
    obs = lantern.kernel.observations[result.observation_id]

    assert obs.metadata["platform"] == "discord"
    assert obs.metadata["channel_id"] == payload["channel_id"]
    assert obs.metadata["message_id"] == payload["id"]
    assert obs.metadata["guild_id"] == payload["guild_id"]
    assert obs.metadata["author"] == payload["author"]["id"]
    assert obs.metadata["timestamp"] == payload["timestamp"]
    # Raw payload preserved untouched for audit purposes.
    assert obs.metadata["raw_payload"] == payload


# ==================================================
# Observation does not automatically become belief
# ==================================================

def test_observation_never_automatically_becomes_belief():
    lantern = Lantern()
    payload = make_valid_payload(content="the sky is green")

    result = discord_message_to_observation(lantern, payload)
    assert result.accepted is True

    # No add_evidence call was ever made by the bridge. Belief for any
    # concept touched by this content must remain neutral (0.5, i.e. no
    # evidence at all) unless the caller explicitly adds evidence.
    belief = lantern.belief("sky_color") if hasattr(lantern, "belief") else lantern.kernel.belief("sky_color")
    assert belief == 0.5  # sigmoid(0) - no evidence recorded, neutral belief
    assert len(lantern.kernel.evidence) == 0


# ==================================================
# Contradictory observations can reach Lantern's contradiction detector
# ==================================================

def test_contradictory_discord_observations_reach_contradiction_detector():
    lantern = Lantern()

    payload_a = make_valid_payload(
        id="msg_a", content="PROTOCOL_SUPPORTED = TRUE",
        author={"id": "agent_a"},
    )
    payload_b = make_valid_payload(
        id="msg_b", content="PROTOCOL_SUPPORTED = FALSE",
        author={"id": "agent_b"},
    )

    result_a = discord_message_to_observation(lantern, payload_a)
    result_b = discord_message_to_observation(lantern, payload_b)

    assert result_a.accepted and result_b.accepted

    # Caller (not the bridge) explicitly promotes both to evidence under the
    # same concept -- this is the deliberate, non-automatic step.
    lantern.add_evidence(
        "protocol_supported", result_a.observation_id, weight=1, sign=1
    )
    lantern.add_evidence(
        "protocol_supported", result_b.observation_id, weight=1, sign=-1
    )

    # The second, opposing piece of evidence must be detectable as a
    # contradiction by Lantern's existing detector.
    detected = lantern.kernel.detect_contradiction("protocol_supported")
    assert detected is not None
    assert detected.concept == "protocol_supported"


# ==================================================
# Discord transport failure does not mutate Lantern state
# ==================================================

def test_transport_failure_does_not_touch_lantern_state():
    lantern = Lantern()
    step_before = lantern.kernel.step
    observation_count_before = len(lantern.kernel.observations)

    def failing_proxy_call(integration_key, method, endpoint, data):
        raise RuntimeError("simulated network failure")

    with pytest.raises(DiscordTransportError):
        fetch_discord_message("chan_001", "msg_001", failing_proxy_call)

    # Transport layer never touches Lantern at all -- confirm no state moved.
    assert lantern.kernel.step == step_before
    assert len(lantern.kernel.observations) == observation_count_before


def test_transport_requires_explicit_channel_and_message_id():
    def unused_proxy_call(integration_key, method, endpoint, data):
        raise AssertionError("proxy_call should not be invoked without ids")

    with pytest.raises(DiscordTransportError):
        fetch_discord_message("", "", unused_proxy_call)


def test_transport_rejects_non_dict_response():
    def bad_proxy_call(integration_key, method, endpoint, data):
        return "not a dict"

    with pytest.raises(DiscordTransportError):
        fetch_discord_message("chan_001", "msg_001", bad_proxy_call)


def test_transport_success_returns_raw_payload_untouched():
    expected = make_valid_payload()

    def good_proxy_call(integration_key, method, endpoint, data):
        assert integration_key == "discord"
        assert method == "GET"
        assert endpoint == "/channels/chan_001/messages/msg_001"
        return expected

    result = fetch_discord_message("chan_001", "msg_001", good_proxy_call)
    assert result == expected
