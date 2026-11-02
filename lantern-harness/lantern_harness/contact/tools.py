"""ToolBoundary registration for the read-only contact tools.

Mirrors board/tools.py: registration is separate from authorization, and
authorization is an operator-owned act. There is deliberately no contact
tool that writes, posts, creates identities, or touches keys.
"""

from __future__ import annotations

from typing import Optional

from ..tools.boundary import ToolBoundary, ToolDescriptor
from .contact_service import ContactService

CONTACT_AGENT_CARD = "lantern_contact_agent_card"
CONTACT_SKILL = "lantern_contact_skill"
CONTACT_BOARD_READ = "lantern_contact_board_read"
CONTACT_BOARD_VERIFY = "lantern_contact_board_verify"

SCOPE_CONTACT_READ = "contact.read"

CONTACT_TOOL_NAMES = (
    CONTACT_AGENT_CARD,
    CONTACT_SKILL,
    CONTACT_BOARD_READ,
    CONTACT_BOARD_VERIFY,
)


def register_contact_tools(tool_boundary: ToolBoundary, service: ContactService) -> list[str]:
    """Register the four read-only contact tools. Does NOT authorize them."""

    def agent_card() -> dict:
        return service.agent_card()

    def skill(text: str) -> dict:
        return service.skill(text)

    def board_read(limit: int = 10) -> dict:
        if not isinstance(limit, int) or isinstance(limit, bool) or limit < 1 or limit > 100:
            return {"status": "BLOCKED", "detail": "limit must be an integer in [1, 100]"}
        return service.board_read(limit=limit)

    def board_verify() -> dict:
        return service.board_verify()

    descriptors = [
        ToolDescriptor(
            name=CONTACT_AGENT_CARD,
            description=("Retrieve and validate the public Lantern Agent Card from its fixed "
                         "endpoint. Read-only; reports what was actually retrieved and which "
                         "required properties failed, if any."),
            handler=agent_card,
            scopes=(SCOPE_CONTACT_READ,),
            required_confidence=0.0,
        ),
        ToolDescriptor(
            name=CONTACT_SKILL,
            description=("Send ONE validated read-only A2A request. Accepted forms: "
                         "'verify board', 'hash <entry hash>', 'collatz <positive integer>'. "
                         "No URLs, methods, headers, or credentials are accepted."),
            handler=skill,
            scopes=(SCOPE_CONTACT_READ,),
            required_confidence=0.0,
        ),
        ToolDescriptor(
            name=CONTACT_BOARD_READ,
            description=("Read public board entries through the existing BoardClient. "
                         "Observational: returned labelled OBSERVED, not verified beliefs."),
            handler=board_read,
            scopes=(SCOPE_CONTACT_READ,),
            required_confidence=0.0,
        ),
        ToolDescriptor(
            name=CONTACT_BOARD_VERIFY,
            description=("Independently verify board records with the existing BoardClient "
                         "verifier: Ed25519 signature, entry-hash recomputation, chain linkage, "
                         "fingerprint. Never reports a bare 'verified=true'."),
            handler=board_verify,
            scopes=(SCOPE_CONTACT_READ,),
            required_confidence=0.0,
        ),
    ]
    for descriptor in descriptors:
        tool_boundary.register(descriptor)
    return [d.name for d in descriptors]


def contact_tool_specs() -> dict:
    """Static spec summary for documentation and tests (no live service)."""
    return {name: {"scopes": (SCOPE_CONTACT_READ,), "required_confidence": 0.0}
            for name in CONTACT_TOOL_NAMES}
