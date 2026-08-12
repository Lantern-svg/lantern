import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lantern_harness.reasoning import build_engine
from lantern_harness.reasoning.api_provider import AnthropicEngine, OpenAIEngine
from lantern_harness.reasoning.ollama_provider import OllamaEngine


def test_build_engine_returns_none_when_no_provider():
    assert build_engine({"provider": "none"}) is None
    assert build_engine({}) is None


def test_build_engine_returns_none_for_unknown_provider():
    assert build_engine({"provider": "not_a_real_provider"}) is None


def test_build_engine_returns_ollama_instance():
    engine = build_engine({"provider": "ollama", "model": "llama3.1"})
    assert isinstance(engine, OllamaEngine)
    assert engine.model == "llama3.1"


def test_ollama_detect_reports_absence_honestly():
    engine = OllamaEngine(host="http://localhost:1")  # unreachable port
    available, detail = engine.detect()
    assert available is False
    assert "not reachable" in detail


def test_openai_detect_reports_missing_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    engine = OpenAIEngine()
    available, detail = engine.detect()
    assert available is False
    assert "not set" in detail


def test_anthropic_detect_never_exposes_key_value(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-secret-value-should-never-appear")
    engine = AnthropicEngine()
    available, detail = engine.detect()
    assert available is True
    assert "sk-secret-value-should-never-appear" not in detail
