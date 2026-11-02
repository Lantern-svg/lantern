"""Read-only contact workflow: card -> A2A -> board -> independent verification.

Every result enters the evidence pipeline with the provenance that was
actually established. This module has no write path: there is no posting
method, no key generation, no token access, and no way for a caller to
supply a URL, method, or credential.
"""

from __future__ import annotations

from typing import Any, Callable, Optional

from .agent_card import AGENT_CARD_URL, AgentCardEvidence, load_agent_card
from .a2a_client import A2A_ENDPOINT, A2AClient, A2AClientError
from .models import (
    BLOCKED,
    CORROBORATED,
    DISPROVEN,
    ERROR,
    NOT_CONFIGURED,
    NOT_CONNECTED,
    OBSERVED,
    UNKNOWN,
    VERIFIED,
    ContactReport,
    make_evidence,
    now_ms,
)

BOARD_READ_SOURCE = "board:read_board"
BOARD_VERIFY_SOURCE = "board:verify_entry"


class ContactService:
    """One long-lived read-only contact surface."""

    def __init__(
        self,
        *,
        bridge: Optional[Any] = None,
        board_client: Optional[Any] = None,
        a2a_client: Optional[A2AClient] = None,
        card_loader: Callable[..., AgentCardEvidence] = load_agent_card,
        card_url: str = AGENT_CARD_URL,
        enabled: bool = False,
    ):
        self.bridge = bridge
        self.board_client = board_client
        self.a2a = a2a_client
        self._card_loader = card_loader
        self.card_url = card_url
        self.enabled = enabled
        self.evidence: list[dict[str, Any]] = []
        self._last_card: Optional[AgentCardEvidence] = None
        self._last_verify: Optional[dict[str, Any]] = None

    # ---------------------------------------------------------------- evidence
    def _record(self, evidence) -> dict[str, Any]:
        record = evidence.to_dict()
        self.evidence.append(record)
        if self.bridge is not None:
            # The Observation is the real retrieval event. It never upgrades a
            # label: the label lives on the ContactEvidence record.
            try:
                self.bridge.observe(
                    f"[{evidence.label}] {evidence.operation}: {evidence.detail or 'retrieved'}",
                    source=evidence.source,
                    reliability=1.0 if evidence.label != BLOCKED else 0.0,
                    metadata={"contact_operation": evidence.operation, "contact_label": evidence.label},
                )
            except Exception:  # noqa: BLE001 - observation must never break contact
                pass
        return record

    # ------------------------------------------------------------------ card
    def agent_card(self) -> dict[str, Any]:
        if not self.enabled:
            return {
                "status": NOT_CONFIGURED,
                "detail": "contact is disabled; set contact.enabled true in config to expose read-only contact",
            }
        card_evidence = self._card_loader(self.card_url)
        self._last_card = card_evidence
        record = make_evidence(
            "agent_card",
            card_evidence.label,
            card_evidence.source,
            protocol_version=(card_evidence.card or {}).get("protocolVersion"),
            verification=card_evidence.checks,
            failures=list(card_evidence.failures),
            detail=card_evidence.detail,
            metadata={"name": (card_evidence.card or {}).get("name"),
                      "skills": [s.get("id") for s in (card_evidence.card or {}).get("skills", [])
                                 if isinstance(s, dict)]},
        )
        self._record(record)
        return {
            "status": card_evidence.label,
            "card": card_evidence.card,
            "checks": card_evidence.checks,
            "failures": card_evidence.failures,
            "evidence_label": card_evidence.label,
        }

    # ------------------------------------------------------------------- a2a
    def skill(self, text: str) -> dict[str, Any]:
        if not self.enabled:
            return {"status": NOT_CONFIGURED, "detail": "contact is disabled"}
        client = self.a2a
        if client is None:
            try:
                client = A2AClient()
            except A2AClientError as exc:
                return {"status": NOT_CONFIGURED, "detail": str(exc)}
        try:
            result = client.send(text)
        except A2AClientError as exc:
            record = make_evidence(
                "a2a_skill", BLOCKED, getattr(client, "endpoint", A2A_ENDPOINT),
                failures=[str(exc)], detail=str(exc),
            )
            self._record(record)
            return {"status": BLOCKED, "operation": text, "detail": str(exc), "evidence_label": BLOCKED}
        record = make_evidence(
            "a2a_skill", OBSERVED, result.endpoint,
            detail=result.text[:2000],
            metadata={"operation": result.operation, "elapsed_ms": result.elapsed_ms},
        )
        self._record(record)
        return {
            "status": OBSERVED,
            "operation": result.operation,
            "text": result.text,
            "endpoint": result.endpoint,
            "evidence_label": OBSERVED,
        }

    # ----------------------------------------------------------------- board
    def _board_unavailable(self, operation: str) -> dict[str, Any]:
        # Component states (NOT_CONFIGURED) are not evidence labels. The
        # honest evidence record for "could not establish" is BLOCKED; the
        # returned status still says NOT_CONFIGURED.
        record = make_evidence(operation, BLOCKED, BOARD_READ_SOURCE,
                               detail="no board client configured")
        self._record(record)
        return {"status": NOT_CONFIGURED, "detail": "board client is not configured"}

    def board_read(self, limit: int = 10) -> dict[str, Any]:
        if not self.enabled:
            return {"status": NOT_CONFIGURED, "detail": "contact is disabled"}
        if self.board_client is None:
            return self._board_unavailable("board_read")
        result = self.board_client.read_board(limit=limit)
        entries = result.get("entries") if isinstance(result, dict) else None
        # The BoardClient's model-visible projection names the full entry hash
        # `entry_id` (falling back to post_id/message_id); read that, never a
        # truncated display value.
        hashes = [e.get("entry_id") or e.get("hash") for e in entries or []
                  if isinstance(e, dict) and (e.get("entry_id") or e.get("hash"))]
        record = make_evidence(
            "board_read", OBSERVED, BOARD_READ_SOURCE,
            entry_hashes=hashes,
            detail=f"read {len(hashes)} entries",
            metadata={"limit": limit, "head": result.get("head") if isinstance(result, dict) else None},
        )
        self._record(record)
        return {
            "status": OBSERVED,
            "entries": entries or [],
            "count": len(hashes),
            "entry_hashes": hashes,
            "evidence_label": OBSERVED,
        }

    def board_verify(self) -> dict[str, Any]:
        if not self.enabled:
            return {"status": NOT_CONFIGURED, "detail": "contact is disabled"}
        if self.board_client is None:
            return self._board_unavailable("board_verify")
        result = self.board_client.verify_entry()
        # The existing verifier reports `status` for the board and per-entry
        # `status` values inside `entries`; `state` never existed here.
        state = (result or {}).get("status") if isinstance(result, dict) else None
        # The verifier's own state vocabulary is preserved. CORROBORATED and
        # VERIFIED both mean "independent checks passed"; everything else is
        # carried through unchanged -- no state is upgraded to success.
        if state in (VERIFIED, CORROBORATED):
            label = VERIFIED
        elif state in (DISPROVEN, BLOCKED, UNKNOWN):
            label = state
        else:
            label = UNKNOWN
        self._last_verify = result if isinstance(result, dict) else {}
        per_entry = self._last_verify.get("entries") if isinstance(self._last_verify, dict) else None
        histogram: dict[str, int] = {}
        failing: list[dict] = []
        for report in per_entry or []:
            if not isinstance(report, dict):
                continue
            entry_state = str(report.get("status"))
            histogram[entry_state] = histogram.get(entry_state, 0) + 1
            if entry_state not in (VERIFIED, CORROBORATED):
                failing.append({"entry_id": report.get("entry_id") or report.get("id"),
                                "status": entry_state,
                                "checks": {k: v.get("state") for k, v in (report.get("checks") or {}).items()
                                           if isinstance(v, dict)}})
        verification_summary = {
            "checked": self._last_verify.get("checked"),
            "states": histogram,
            "non_passing": failing[:10],
        }
        record = make_evidence(
            "board_verify", label, BOARD_VERIFY_SOURCE,
            verification=verification_summary,
            metadata={"summary": verification_summary},
            detail=f"board verification status: {state}; checked {verification_summary['checked']}",
        )
        self._record(record)
        return {"status": state or UNKNOWN, "checked": (result or {}).get("checked"),
                "summary": verification_summary, "verification": result,
                "evidence_label": record.label}

    # ---------------------------------------------------------------- status
    def status(self) -> dict[str, Any]:
        return {
            "enabled": bool(self.enabled),
            "agent_card": {
                "url": self.card_url,
                "state": (self._last_card.label if self._last_card else UNKNOWN),
            },
            "a2a": {
                "endpoint": getattr(self.a2a, "endpoint", A2A_ENDPOINT),
                "state": OBSERVED if any(e["operation"] == "a2a_skill" and e["label"] == OBSERVED
                                         for e in self.evidence) else UNKNOWN,
            },
            "board": {
                "configured": self.board_client is not None,
                "state": (self._last_verify or {}).get("state", UNKNOWN) if self.board_client else NOT_CONFIGURED,
            },
            "evidence_events": len(self.evidence),
            "authorization": "read-only: no post, no identity creation, no key access",
            "write_tools_registered": False,
        }

    # ---------------------------------------------------------------- report
    def contact_report(self, limit: int = 10) -> dict[str, Any]:
        report = ContactReport(status=UNKNOWN)
        if not self.enabled:
            report.status = NOT_CONFIGURED
            report.untested = ["agent card", "a2a verify", "board read", "board verification"]
            return report.to_dict()

        card = self.agent_card()
        report.agent_card = card
        if card["status"] not in (OBSERVED, VERIFIED):
            report.status = card["status"]
            report.untested = ["a2a verify", "board read", "board verification"]
            report.evidence = list(self.evidence)
            report.finished_at_ms = now_ms()
            return report.to_dict()

        verify = self.skill("verify board")
        report.a2a_verify = verify
        if verify["status"] != OBSERVED:
            report.status = NOT_CONNECTED
            report.untested = ["board read", "board verification"]
            report.evidence = list(self.evidence)
            report.finished_at_ms = now_ms()
            return report.to_dict()

        read = self.board_read(limit=limit)
        report.board_read = read
        verification = self.board_verify()
        report.board_verification = verification

        if verification["status"] in (VERIFIED, "CORROBORATED"):
            report.status = VERIFIED
        elif verification["status"] == NOT_CONFIGURED:
            report.status = NOT_CONFIGURED
        elif verification["status"] == UNKNOWN:
            report.status = UNKNOWN
        else:
            report.status = verification["status"] or UNKNOWN

        report.untested = [
            "independent corroboration by another participant (not performed here)",
            "personhood of any signer (signatures prove key possession only)",
        ]
        report.evidence = list(self.evidence)
        report.finished_at_ms = now_ms()
        return report.to_dict()

