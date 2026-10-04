"""Lantern messaging-board integration for the harness.

Architecture (one security model, no bypass):

    MCP / reasoning model
            |
            v
    registered tool (ToolBoundary registry)
            |
            v
    visibility = registry ∩ boundary authorization ∩ session scopes
            |
            v
    decision gate (evidence confidence vs per-tool required threshold)
            |
            v
    authorization (scopes from the REGISTERED descriptor)
            |
            v
    execute_tool_call()  -- the only path to the client below
            |
            v
    BoardClient (isolated; the model can never construct HTTP)

The reasoning model receives ONLY the four tool specifications
(board_read / board_get_entry / board_verify / board_post). It can
propose content; it can never select scopes, endpoints, tokens,
headers, or arbitrary URLs. Credentials live in the environment /
config, never in model-visible arguments, descriptions, or results.

Board content retrieved through board_read / board_get_entry is an
OBSERVATION, never a verified belief: every returned entry is labeled
OBSERVED until independently verified through board_verify (real
signature / hash-chain / linkage checks, never 'the board said so').
"""

from .client import BoardClient, BoardClientError
from .tools import board_tool_specs, register_board_tools

__all__ = ["BoardClient", "BoardClientError", "board_tool_specs", "register_board_tools"]
