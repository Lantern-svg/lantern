import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lantern_harness.config import load_config


def test_load_config_defaults_when_missing(tmp_path):
    config = load_config(tmp_path / "nonexistent.json")
    assert config["reasoning_engine"]["provider"] == "none"


def test_load_real_config_file():
    config = load_config()
    assert "reasoning_engine" in config
    assert "node_id" in config


def test_config_never_stores_raw_api_key():
    config = load_config()
    assert config["reasoning_engine"].get("api_key_env") is None or "API_KEY" in str(config["reasoning_engine"].get("api_key_env", ""))
    for value in config["reasoning_engine"].values():
        if isinstance(value, str):
            assert not value.startswith("sk-")
            assert "://" not in value or "localhost" in value or "http" in value
