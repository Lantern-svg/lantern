"""Lantern contact: read-only discovery, query, retrieval, and independent
verification of the public Lantern network.

There is no write path in this package. No posting, no identity creation, no
key generation, no key access, no token disclosure, no automatic
authorization, and no caller-supplied URLs, methods, headers, or credentials.
"""

from .agent_card import (
    AGENT_CARD_URL,
    AgentCardError,
    AgentCardEvidence,
    fetch_card,
    load_agent_card,
    validate_card,
)
from .a2a_client import (
    A2A_ENDPOINT,
    A2AClient,
    A2AClientError,
    A2AResult,
    ALLOWED_OPERATIONS,
    validate_request_text,
)
from .contact_service import ContactService
from .models import (
    BLOCKED,
    CLAIMED,
    CORROBORATED,
    DISPROVEN,
    ERROR,
    NOT_CONFIGURED,
    NOT_CONNECTED,
    OBSERVED,
    UNKNOWN,
    VERIFIED,
    ContactEvidence,
    ContactReport,
    make_evidence,
)
from .tools import (
    CONTACT_TOOL_NAMES,
    SCOPE_CONTACT_READ,
    contact_tool_specs,
    register_contact_tools,
)

__all__ = [
    "AGENT_CARD_URL",
    "A2A_ENDPOINT",
    "ALLOWED_OPERATIONS",
    "A2AClient",
    "A2AClientError",
    "A2AResult",
    "AgentCardError",
    "AgentCardEvidence",
    "BLOCKED",
    "CLAIMED",
    "CORROBORATED",
    "CONTACT_TOOL_NAMES",
    "ContactEvidence",
    "ContactReport",
    "ContactService",
    "DISPROVEN",
    "ERROR",
    "NOT_CONFIGURED",
    "NOT_CONNECTED",
    "OBSERVED",
    "SCOPE_CONTACT_READ",
    "UNKNOWN",
    "VERIFIED",
    "contact_tool_specs",
    "fetch_card",
    "load_agent_card",
    "make_evidence",
    "register_contact_tools",
    "validate_card",
    "validate_request_text",
]
