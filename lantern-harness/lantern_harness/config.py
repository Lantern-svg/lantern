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
        }
    return json.loads(path.read_text(encoding="utf-8"))
