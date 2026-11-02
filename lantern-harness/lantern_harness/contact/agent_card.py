"""Retrieve and validate the public Lantern Agent Card.

Fixed endpoint only. Nothing here is parameterised by the reasoning model:
no arbitrary URLs, no redirects to other hosts, no headers beyond the ones
this module sets.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from .models import BLOCKED, NOT_CONNECTED, OBSERVED, VERIFIED

AGENT_CARD_URL = (
    "https://raw.githubusercontent.com/Lantern-svg/lantern/master/"
    "agent/.well-known/agent-card.json"
)
USER_AGENT = "lantern-contact/1.0"
REQUIRED_PROTOCOL_VERSION = "1.0"
REQUIRED_SKILL_COUNT = 3
NAME_PREFIX = "Lantern"
DEFAULT_TIMEOUT = 15.0
MAX_CARD_BYTES = 256_000


class AgentCardError(Exception):
    """A card could not be retrieved or could not be parsed as JSON."""


@dataclass
class AgentCardEvidence:
    label: str
    source: str
    card: dict[str, Any] = field(default_factory=dict)
    failures: list[str] = field(default_factory=list)
    checks: dict[str, Any] = field(default_factory=dict)
    detail: Optional[str] = None
    retrieved_at_ms: Optional[int] = None

    @property
    def ok(self) -> bool:
        return self.label in (OBSERVED, VERIFIED) and not self.failures


def fetch_card(
    url: str = AGENT_CARD_URL,
    *,
    timeout: float = DEFAULT_TIMEOUT,
    max_bytes: int = MAX_CARD_BYTES,
    opener: Optional[Callable[[str, float, int], Any]] = None,
) -> dict[str, Any]:
    """Fetch the card and return parsed JSON. Raises AgentCardError on any
    transport, size, or parsing failure -- a failure is never returned as a
    card."""
    # opener(url, timeout, max_bytes) -> bytes, injectable for tests.
    raw = opener(url, timeout, max_bytes) if opener is not None else _read_url(url, timeout, max_bytes)
    if len(raw) > max_bytes:
        raise AgentCardError(f"agent card exceeds size limit ({len(raw)} > {max_bytes} bytes)")
    try:
        parsed = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AgentCardError(f"agent card is not valid JSON: {exc}") from exc
    if not isinstance(parsed, dict):
        raise AgentCardError("agent card JSON is not an object")
    return parsed


def _read_url(url: str, timeout: float, max_bytes: int) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            return response.read(max_bytes + 1)
    except urllib.error.HTTPError as exc:
        raise AgentCardError(f"agent card HTTP {exc.code}") from exc
    except urllib.error.URLError as exc:
        raise AgentCardError(f"agent card unreachable: {exc.reason}") from exc
    except TimeoutError as exc:
        raise AgentCardError("agent card request timed out") from exc


def validate_card(card: dict[str, Any]) -> tuple[list[str], dict[str, Any]]:
    """Check exactly the required properties. Returns (failures, checks).

    Only what is present in the document is evaluated; nothing is invented
    to fill a gap.
    """
    failures: list[str] = []
    checks: dict[str, Any] = {}

    name = card.get("name")
    name_ok = isinstance(name, str) and name.startswith(NAME_PREFIX)
    checks["name"] = {"value": name, "rule": f"must start with {NAME_PREFIX!r}", "ok": name_ok}
    if not name_ok:
        failures.append("name does not begin with 'Lantern'")

    protocol = card.get("protocolVersion")
    protocol_ok = protocol == REQUIRED_PROTOCOL_VERSION
    checks["protocol_version"] = {
        "value": protocol, "rule": f"must equal {REQUIRED_PROTOCOL_VERSION!r}", "ok": protocol_ok,
    }
    if not protocol_ok:
        failures.append(f"protocolVersion is {protocol!r}, expected {REQUIRED_PROTOCOL_VERSION!r}")

    skills = card.get("skills")
    skills_ok = isinstance(skills, list) and len(skills) == REQUIRED_SKILL_COUNT
    checks["skills"] = {
        "value": len(skills) if isinstance(skills, list) else None,
        "ids": [s.get("id") for s in skills if isinstance(s, dict)] if isinstance(skills, list) else [],
        "rule": f"exactly {REQUIRED_SKILL_COUNT} advertised skills",
        "ok": skills_ok,
    }
    if not skills_ok:
        count = len(skills) if isinstance(skills, list) else "missing"
        failures.append(f"expected exactly {REQUIRED_SKILL_COUNT} skills, found {count}")

    return failures, checks


def load_agent_card(
    url: str = AGENT_CARD_URL,
    *,
    timeout: float = DEFAULT_TIMEOUT,
    opener: Optional[Callable[[str, float, int], Any]] = None,
) -> AgentCardEvidence:
    """Fetch + validate, returning structured evidence either way."""
    from .models import now_ms

    try:
        card = fetch_card(url, timeout=timeout, opener=opener)
    except AgentCardError as exc:
        return AgentCardEvidence(
            label=NOT_CONNECTED, source=url, detail=str(exc),
            failures=[str(exc)], retrieved_at_ms=now_ms(),
        )

    failures, checks = validate_card(card)
    label = VERIFIED if not failures else BLOCKED
    return AgentCardEvidence(
        label=label,
        source=url,
        card=card,
        failures=failures,
        checks=checks,
        detail=None if not failures else "; ".join(failures),
        retrieved_at_ms=now_ms(),
    )
