"""Isolated tests for agent-card retrieval/validation and the A2A client.

No test in this file touches the network: transports and openers are fakes.
No test posts to the real board.
"""

import json

import pytest

from lantern_harness.contact.agent_card import (
    AgentCardError,
    MAX_CARD_BYTES,
    fetch_card,
    load_agent_card,
    validate_card,
)
from lantern_harness.contact.a2a_client import (
    A2AClient,
    A2AClientError,
    build_payload,
    validate_request_text,
)
from lantern_harness.contact.models import BLOCKED, NOT_CONNECTED, VERIFIED


GOOD_CARD = {
    "name": "Lantern — Signed Public Memory Board",
    "protocolVersion": "1.0",
    "skills": [
        {"id": "board-verify"},
        {"id": "evidence-lookup"},
        {"id": "compute-unit"},
    ],
}


def _opener(payload: bytes):
    def _open(url, timeout, max_bytes):
        return payload
    return _open


# --------------------------------------------------------------- agent card
def test_valid_agent_card_passes_all_required_checks():
    evidence = load_agent_card(opener=_opener(json.dumps(GOOD_CARD).encode()))
    assert evidence.label == VERIFIED
    assert evidence.failures == []
    assert evidence.card["protocolVersion"] == "1.0"


def test_card_with_wrong_name_is_blocked():
    card = dict(GOOD_CARD, name="Something Else")
    evidence = load_agent_card(opener=_opener(json.dumps(card).encode()))
    assert evidence.label == BLOCKED
    assert any("name" in failure for failure in evidence.failures)


def test_card_with_missing_skills_is_blocked():
    card = dict(GOOD_CARD, skills=[{"id": "only-one"}])
    evidence = load_agent_card(opener=_opener(json.dumps(card).encode()))
    assert evidence.label == BLOCKED
    assert any("skills" in failure for failure in evidence.failures)


def test_card_with_wrong_protocol_version_is_blocked():
    card = dict(GOOD_CARD, protocolVersion="0.3.0")
    evidence = load_agent_card(opener=_opener(json.dumps(card).encode()))
    assert evidence.label == BLOCKED
    assert any("protocolVersion" in failure for failure in evidence.failures)


def test_validate_card_never_invents_missing_fields():
    failures, checks = validate_card({})
    assert len(failures) == 3
    assert checks["skills"]["value"] is None


def test_malformed_json_is_an_error_not_a_card():
    with pytest.raises(AgentCardError):
        fetch_card(opener=_opener(b"not json at all"))


def test_oversized_card_is_refused():
    big = b'{"name": "' + b"x" * (MAX_CARD_BYTES + 10) + b'"}'
    with pytest.raises(AgentCardError):
        fetch_card(opener=_opener(big))


def test_unreachable_endpoint_reports_not_connected():
    def boom(url, timeout, max_bytes):
        raise AgentCardError("agent card unreachable: connection refused")
    evidence = load_agent_card(opener=boom)
    assert evidence.label == NOT_CONNECTED
    assert evidence.card == {}
    assert evidence.failures


# --------------------------------------------------------------------- a2a
def test_verify_board_request_normalises():
    assert validate_request_text("  Verify   Board ") == "verify board"


def test_hash_request_normalises_to_lowercase():
    assert validate_request_text("hash ABCDEF12") == "hash abcdef12"


def test_collatz_request_normalises_numeric_text():
    assert validate_request_text("collatz 27") == "collatz 27"


@pytest.mark.parametrize("bad", [
    "hash xyz",                    # not hex
    "hash abc",                    # too short
    "collatz 0",                   # not positive
    "collatz -5",
    "collatz 999999999",           # exceeds the cap
    "GET https://example.com",     # arbitrary URL
    "post hello",                  # write attempt
    "verify board extra",          # trailing arguments
    "",
])
def test_invalid_requests_are_refused(bad):
    with pytest.raises(A2AClientError):
        validate_request_text(bad)


def test_payload_shape_is_jsonrpc_message_send():
    payload = build_payload("verify board")
    assert payload["jsonrpc"] == "2.0"
    assert payload["method"] == "message/send"
    assert payload["params"]["message"]["parts"][0]["text"] == "verify board"


def _transport(status=200, body=None, exc=None):
    def _send(payload):
        if exc is not None:
            raise exc
        return status, body
    return _send


def test_successful_response_returns_text():
    body = json.dumps({
        "jsonrpc": "2.0", "id": 1,
        "result": {"kind": "message", "parts": [{"kind": "text", "text": "64 records; head abc"}]},
    }).encode()
    client = A2AClient(transport=_transport(200, body))
    result = client.send("verify board")
    assert result.text.startswith("64 records")
    assert result.operation == "verify board"


def test_jsonrpc_error_response_raises():
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "error": {"code": -32601, "message": "no"}}).encode()
    client = A2AClient(transport=_transport(200, body))
    with pytest.raises(A2AClientError):
        client.send("verify board")


def test_malformed_json_response_raises():
    client = A2AClient(transport=_transport(200, b"{not json"))
    with pytest.raises(A2AClientError):
        client.send("verify board")


def test_non_200_response_raises():
    client = A2AClient(transport=_transport(500, b""))
    with pytest.raises(A2AClientError):
        client.send("verify board")


def test_response_without_text_raises():
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "result": {"parts": []}}).encode()
    client = A2AClient(transport=_transport(200, body))
    with pytest.raises(A2AClientError):
        client.send("verify board")


def test_network_failure_is_never_a_success():
    client = A2AClient(transport=_transport(exc=A2AClientError("A2A endpoint unreachable: timed out")))
    with pytest.raises(A2AClientError):
        client.send("verify board")


def test_non_https_endpoint_refused():
    with pytest.raises(A2AClientError):
        A2AClient("http://example.com/functions/lanternA2A")
