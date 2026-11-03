"""Service, boundary, and security tests for the read-only contact module.

Fake board client and fake A2A transport: no network, no real board writes.
"""

import pytest

from lantern_harness.contact.agent_card import AgentCardEvidence
from lantern_harness.contact.a2a_client import A2AResult
from lantern_harness.contact.contact_service import ContactService
from lantern_harness.contact.models import (
    BLOCKED,
    DISPROVEN,
    NOT_CONFIGURED,
    OBSERVED,
    UNKNOWN,
    VERIFIED,
)
from lantern_harness.contact.tools import (
    CONTACT_TOOL_NAMES,
    register_contact_tools,
    contact_tool_specs,
)
from lantern_harness.tools.boundary import ToolBoundary

GOOD_CARD = {
    "name": "Lantern — Signed Public Memory Board",
    "protocolVersion": "1.0",
    "skills": [{"id": "a"}, {"id": "b"}, {"id": "c"}],
}


class FakeBoard:
    def __init__(self, verify_state=VERIFIED):
        self.verify_state = verify_state
        self.read_calls = 0

    def read_board(self, limit=10, cursor=None):
        self.read_calls += 1
        return {"entries": [
            {"hash": "a" * 64, "message_id": "m1"},
            {"hash": "b" * 64, "message_id": "m2"},
        ], "head": "b" * 64}

    def verify_entry(self, entry_id=None):
        # Real BoardClient contract: board-level `status`, `checked`, and a
        # per-entry report list carrying each entry's own `status` + `checks`.
        return {
            "status": self.verify_state,
            "checked": 2,
            "entries": [
                {"entry_id": "a" * 64, "status": self.verify_state,
                 "checks": {"signature": {"state": "CORROBORATED"},
                            "hash_integrity": {"state": "CORROBORATED"}}},
                {"entry_id": "b" * 64, "status": self.verify_state,
                 "checks": {"signature": {"state": "CORROBORATED"},
                            "hash_integrity": {"state": "CORROBORATED"}}},
            ],
        }


class FakeA2A:
    endpoint = "https://zelle-4457b476.base44.app/functions/lanternA2A"

    def send(self, text):
        return A2AResult(operation=text, text="64 records; head deadbeef",
                         raw={}, endpoint=self.endpoint, elapsed_ms=5)


def _card_loader_ok(url):
    return AgentCardEvidence(label=VERIFIED, source=url, card=GOOD_CARD,
                             checks={"name": {"ok": True}}, retrieved_at_ms=1)


# ------------------------------------------------------------------ service
def test_disabled_service_reports_not_configured():
    service = ContactService(enabled=False)
    assert service.agent_card()["status"] == NOT_CONFIGURED
    report = service.contact_report()
    assert report["status"] == NOT_CONFIGURED
    assert service.evidence == []


def test_agent_card_passes_through_validated_evidence():
    service = ContactService(enabled=True, card_loader=_card_loader_ok)
    result = service.agent_card()
    assert result["status"] == VERIFIED
    assert result["card"]["protocolVersion"] == "1.0"
    assert service.evidence[0]["label"] == VERIFIED


def test_board_read_is_labelled_observed_and_keeps_full_hashes():
    board = FakeBoard()
    service = ContactService(enabled=True, board_client=board)
    result = service.board_read(limit=5)
    assert result["status"] == OBSERVED
    assert result["count"] == 2
    assert result["entry_hashes"] == ["a" * 64, "b" * 64]
    assert all(len(h) == 64 for h in result["entry_hashes"])
    assert service.evidence[-1]["label"] == OBSERVED


def test_board_verify_carries_verifier_state_through():
    service = ContactService(enabled=True, board_client=FakeBoard(VERIFIED))
    assert service.board_verify()["status"] == VERIFIED


def test_board_verify_preserves_disproven_state():
    service = ContactService(enabled=True, board_client=FakeBoard(DISPROVEN))
    result = service.board_verify()
    assert result["status"] == DISPROVEN
    assert service.evidence[-1]["label"] == DISPROVEN


def test_board_without_client_is_not_configured():
    service = ContactService(enabled=True, board_client=None)
    assert service.board_read()["status"] == NOT_CONFIGURED


def test_skill_failure_is_blocked_never_success():
    class Broken:
        endpoint = "https://zelle-4457b476.base44.app/functions/lanternA2A"
        def send(self, text):
            from lantern_harness.contact.a2a_client import A2AClientError
            raise A2AClientError("A2A endpoint unreachable: timed out")
    service = ContactService(enabled=True, a2a_client=Broken())
    result = service.skill("verify board")
    assert result["status"] == BLOCKED
    assert service.evidence[-1]["label"] == BLOCKED


def test_full_report_walks_every_stage():
    service = ContactService(enabled=True, board_client=FakeBoard(),
                             a2a_client=FakeA2A(), card_loader=_card_loader_ok)
    report = service.contact_report()
    assert report["status"] == VERIFIED
    assert report["agent_card"]["status"] == VERIFIED
    assert report["a2a_verify"]["status"] == OBSERVED
    assert report["board_read"]["count"] == 2
    assert report["board_verification"]["status"] == VERIFIED
    assert len(report["evidence"]) == 4
    assert report["untested"]  # honest: corroboration/personhood not established


def test_report_stops_honestly_when_card_fails():
    def bad_loader(url):
        return AgentCardEvidence(label=BLOCKED, source=url, failures=["skills"],
                                 retrieved_at_ms=1)
    board = FakeBoard()
    service = ContactService(enabled=True, board_client=board, card_loader=bad_loader)
    report = service.contact_report()
    assert report["status"] == BLOCKED
    assert board.read_calls == 0  # no invented downstream work
    assert report["untested"]


def test_status_is_honest_before_any_contact():
    service = ContactService(enabled=True, board_client=FakeBoard())
    status = service.status()
    # Pre-probe state is NOT_PROBED, never UNKNOWN: UNKNOWN is reserved for
    # a check that ran and could not decide.
    assert status["agent_card"]["state"] == "NOT_PROBED"
    assert status["a2a"]["state"] == "NOT_PROBED"
    assert status["board"]["state"] == "NOT_PROBED"
    assert status["board"]["configured"] is True
    assert status["write_tools_registered"] is False
    # Named access_mode (not "authorization") so host-side redaction of
    # auth-named fields cannot hide it from any caller.
    assert "read-only" in status["access_mode"]
    assert "authorization" not in status


def test_bridge_observation_records_label_not_belief():
    class FakeBridge:
        def __init__(self):
            self.calls = []
        def observe(self, content, source, reliability=1.0, metadata=None):
            self.calls.append((content, source, reliability, metadata))
    bridge = FakeBridge()
    service = ContactService(enabled=True, board_client=FakeBoard(), bridge=bridge)
    service.board_read()
    assert bridge.calls and bridge.calls[0][3]["contact_label"] == OBSERVED


# ------------------------------------------------------------ tool boundary
def test_contact_tools_register_but_are_not_authorized():
    boundary = ToolBoundary()
    service = ContactService(enabled=False)
    names = register_contact_tools(boundary, service)
    assert set(names) == set(CONTACT_TOOL_NAMES)
    for name in names:
        assert not boundary.is_authorized(name)
        result = boundary.execute(name)
        assert result.status == "DENIED"  # discovery is not authorization


def test_authorized_contact_tool_executes_read_only():
    boundary = ToolBoundary()
    service = ContactService(enabled=True, board_client=FakeBoard())
    register_contact_tools(boundary, service)
    for name in CONTACT_TOOL_NAMES:
        boundary.authorize(name)
    result = boundary.execute("lantern_contact_board_read", limit=5)
    assert result.status == "EXECUTED"
    assert result.output["status"] == OBSERVED


def test_no_contact_tool_can_post_or_create_identity():
    specs = contact_tool_specs()
    joined = " ".join(specs).lower()
    for forbidden in ("post", "create", "keygen", "identity", "token", "grant"):
        assert forbidden not in joined
    service = ContactService(enabled=True)
    for attribute in ("post", "post_entry", "create_identity", "generate_key",
                      "grant", "authorize", "execute"):
        assert not hasattr(service, attribute), f"ContactService must not expose {attribute}"


def test_self_authorization_is_impossible_through_tools():
    """A caller cannot authorize a tool by calling it, and registering a tool
    never authorizes it."""
    boundary = ToolBoundary()
    service = ContactService(enabled=True, board_client=FakeBoard())
    register_contact_tools(boundary, service)
    boundary.execute("lantern_contact_agent_card")  # DENIED, and must not self-authorize
    assert not boundary.is_authorized("lantern_contact_agent_card")


def test_board_read_limit_validation():
    boundary = ToolBoundary()
    service = ContactService(enabled=True, board_client=FakeBoard())
    register_contact_tools(boundary, service)
    boundary.authorize("lantern_contact_board_read")
    assert boundary.execute("lantern_contact_board_read", limit=0).output["status"] == BLOCKED
    assert boundary.execute("lantern_contact_board_read", limit=1000).output["status"] == BLOCKED
    assert boundary.execute("lantern_contact_board_read", limit=True).output["status"] == BLOCKED
