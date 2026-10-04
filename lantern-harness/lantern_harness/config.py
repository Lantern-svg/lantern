"""Config loading. Never reads or stores actual API key values here --
only the name of the environment variable to read at call time (see
config/config.json's "api_key_env" field). Actual keys are read
directly from os.environ inside the reasoning provider adapters and are
never written to Chronicle, evidence, witness ledger, or any project
file."""

from __future__ import annotations

import json
from pathlib import Path


DEFAULT_CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "config.json"


def load_config(path: Path | str = DEFAULT_CONFIG_PATH) -> dict:
    path = Path(path)
    if not path.exists():
        return {
            "reasoning_engine": {"provider": "none"},
            "node_id": "lantern-harness-node",
            "data_dir": "memory/lantern_data",
            "output_profile": "concise",
            # Single source of truth for tool-execution policy.
            "tool_policy": {
                "required_confidence": 0.8,
                "allowed_scopes": [],
            },
        }
    return json.loads(path.read_text(encoding="utf-8"))


def board_config(config: dict) -> dict | None:
    """Validated board configuration, or None when the board is not
    configured (tools then fail closed as BLOCKED). Never contains or
    reads the token value itself -- token_env names the environment
    variable read at call time."""
    section = (config or {}).get("board") or None
    if not section or not section.get("endpoint") or not section.get("board"):
        return None
    return section
