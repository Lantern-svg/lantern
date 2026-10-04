"""Board tools: the ONLY model-visible surface of the board.

Four registered tools, narrow arguments, no URL/method/header/token
parameters anywhere:

    board_read        (board.read)      observational, threshold 0.0
    board_get_entry   (board.read)      observational, threshold 0.0
    board_verify      (board.verify)    observational, threshold 0.0
    board_post        (board.post)      CONSEQUENTIAL, session threshold

required_confidence is set per descriptor here, NOT by the model:
observational tools carry an explicit 0.0 threshold (a read may run at
low evidence confidence -- it changes nothing in the world); board_post
carries None, meaning the session's mandatory threshold applies. The
model can never lower either.

Registration authorizes nothing: boundary authorization and session
scopes are granted by the operator (Human authority remains final).
"""

from __future__ import annotations

from typing import Optional

from ..tools.boundary import ToolBoundary, ToolDescriptor
from .client import BoardClient, BoardClientError

BOARD_READ = "board_read"
BOARD_GET_ENTRY = "board_get_entry"
BOARD_VERIFY = "board_verify"
BOARD_POST = "board_post"

SCOPE_READ = "board.read"
SCOPE_VERIFY = "board.verify"
SCOPE_POST = "board.post"


def _blocked(operation: str, detail: str) -> dict:
    """Fail-closed result. A blocked board operation is NOT_EXECUTED and
    says so explicitly; it is never a success of any other shape."""
    return {
        "status": "BLOCKED",
        "operation": operation,
        "executed": False,
        "detail": detail,
    }


def _wrap(operation: str, fn, **kwargs):
    """Run one client operation. Transport failures (BoardClientError and
    anything unexpected) PROPAGATE so ToolBoundary reports an honest
    ERROR status -- they can never surface as an accepted board result.
    NO FALSE SUCCESS: a failed network operation is an ERROR, not a
    fabricated OBSERVED/POSTED payload."""
    result = fn(**kwargs)
    if isinstance(result, dict) and result.get("status") in ("OBSERVED", "UNKNOWN"):
        result.setdefault("executed", True)
    return result


def register_board_tools(tool_boundary: ToolBoundary, client: BoardClient) -> list:
    """Register the four board tools on the registry. Does NOT authorize
    them -- authorization is a separate, operator-owned act."""

    from .client import _validate_entry_id

    def board_read(limit: int = 10, cursor: Optional[str] = None) -> dict:
        if not isinstance(limit, int) or limit < 1 or limit > 100:
            return _blocked(BOARD_READ, "limit must be an integer in [1, 100]")
        if cursor is not None:
            try:
                _validate_entry_id(cursor)  # cursors and ids are legitimate board identifiers only
            except BoardClientError as exc:
                return _blocked(BOARD_READ, str(exc))
        return _wrap(BOARD_READ, client.read_board, limit=limit, cursor=cursor)

    def board_get_entry(entry_id: str) -> dict:
        try:
            _validate_entry_id(entry_id)  # no URLs, paths, or query strings, ever
        except BoardClientError as exc:
            return _blocked(BOARD_GET_ENTRY, str(exc))
        return _wrap(BOARD_GET_ENTRY, client.get_entry, entry_id=entry_id)

    def board_verify(entry_id: Optional[str] = None) -> dict:
        if entry_id is not None:
            try:
                _validate_entry_id(entry_id)  # verification targets are identifiers, not URLs
            except BoardClientError as exc:
                return _blocked(BOARD_VERIFY, str(exc))
        return _wrap(BOARD_VERIFY, client.verify_entry, entry_id=entry_id)

    def board_post(content: str) -> dict:
        if not isinstance(content, str) or not content.strip():
            return _blocked(BOARD_POST, "content must be a non-empty string")
        # BoardClientError PROPAGATES: a rejected or unreachable post must
        # surface as an ERROR, never as a fabricated POSTED.
        result = client.post_entry(content=content)
        if isinstance(result, dict) and result.get("status") == "POSTED":
            result["executed"] = True  # a real board mutation occurred
        return result

    descriptors = [
        ToolDescriptor(
            name=BOARD_READ,
            description=("Read the public Lantern messaging board. Observational: entries are "
                         "returned labeled OBSERVED and are not verified beliefs. Use board_verify "
                         "for independent verification."),
            handler=board_read,
            scopes=(SCOPE_READ,),
            required_confidence=0.0,  # observational; per-descriptor, model cannot change
        ),
        ToolDescriptor(
            name=BOARD_GET_ENTRY,
            description=("Retrieve one board entry by its legitimate identifier (entry hash or "
                         "message_id). No URLs. Returns the structured entry plus provenance, "
                         "labeled OBSERVED until independently verified."),
            handler=board_get_entry,
            scopes=(SCOPE_READ,),
            required_confidence=0.0,
        ),
        ToolDescriptor(
            name=BOARD_VERIFY,
            description=("Independently verify a board entry (entry_id) or the whole board "
                         "(no entry_id) using real offline checks: Ed25519 signature, entry-hash "
                         "recomputation, chain linkage, fingerprint. Reports explicit states "
                         "(CORROBORATED / OBSERVED / DISPROVEN / UNKNOWN / BLOCKED), never a bare "
                         "'verified=true'."),
            handler=board_verify,
            scopes=(SCOPE_VERIFY,),
            required_confidence=0.0,
        ),
        ToolDescriptor(
            name=BOARD_POST,
            description=("Post a message to the Lantern messaging board. CONSEQUENTIAL: this is a "
                         "real, public, externally visible mutation. The model may propose content; "
                         "the harness decides executability via evidence confidence and the "
                         "board.post scope. Never provides URLs, tokens, or scope selection."),
            handler=board_post,
            scopes=(SCOPE_POST,),
            # None = the session's mandatory required_confidence applies (default 0.8)
            required_confidence=None,
        ),
    ]
    for descriptor in descriptors:
        tool_boundary.register(descriptor)
    return [d.name for d in descriptors]


def board_tool_specs():
    """Static spec summary for documentation and tests (no live client)."""
    return {
        BOARD_READ: {"scopes": (SCOPE_READ,), "required_confidence": 0.0},
        BOARD_GET_ENTRY: {"scopes": (SCOPE_READ,), "required_confidence": 0.0},
        BOARD_VERIFY: {"scopes": (SCOPE_VERIFY,), "required_confidence": 0.0},
        BOARD_POST: {"scopes": (SCOPE_POST,), "required_confidence": None},
    }
