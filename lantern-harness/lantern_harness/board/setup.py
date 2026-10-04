"""Board session setup: harness-owned wiring that registers board tools
and (only when the operator configures it) authorizes them for a
session. The reasoning model has no say in any of this.

Defaults are fail-closed: registration alone; NO authorization. Tools
become visible only when the operator's session setup authorizes them
AND the session's allowed_scopes include the tool's scope.
"""

from __future__ import annotations

import os

from ..config import board_config
from ..tools.boundary import ToolBoundary
from .client import BoardClient
from .tools import SCOPE_POST, SCOPE_READ, SCOPE_VERIFY, register_board_tools


def build_board_client(config: dict, identity_provider=None):
    """BoardClient from config, or None when the board is not configured.
    The token is NEVER taken from config -- only its env var NAME."""
    section = board_config(config)
    if section is None:
        return None
    return BoardClient(
        endpoint=section["endpoint"],
        board=section["board"],
        node_id=section.get("node_id", "lantern-harness-node"),
        token_env=section.get("token_env", "LANTERN_BOARD_TOKEN"),
        identity_provider=identity_provider,
    )


def setup_board_tools(tool_boundary: ToolBoundary, client, *, authorize: bool = False) -> list:
    """Register the board tools; authorize only what the operator's
    session policy grants. board_post requires an explicit, separate
    opt-in (authorize_post=True) -- read/verify never imply posting."""
    names = register_board_tools(tool_boundary, client)
    if authorize:
        for name, scope in ((n, s) for n, s in [
            ("board_read", SCOPE_READ), ("board_get_entry", SCOPE_READ), ("board_verify", SCOPE_VERIFY)]):
            tool_boundary.authorize(name)
    return names


def authorize_board_post(tool_boundary: ToolBoundary) -> bool:
    """Separate, explicit operator act for the consequential tool."""
    return tool_boundary.authorize("board_post")
