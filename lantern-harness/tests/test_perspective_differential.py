import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lantern_harness.perspective_differential import (
    DifferentialReading,
    Perspective,
    PerspectiveDifferentialEngine,
)


def test_none_input_rejected():
    engine = PerspectiveDifferentialEngine()
    import pytest
    with __import__("pytest").raises(ValueError):
        engine.compare(None)


def test_single_perspective_is_not_applicable_not_fabricated():
    engine = PerspectiveDifferentialEngine()
    p = Perspective("model-a", "yes", confidence=0.8, evidence_score=0.7, assumption_bias=0.2)
    result = engine.compare([p])
    assert result.status == "NOT_APPLICABLE"
    assert result.confidence_variance is None


def test_empty_list_is_not_applicable():
    engine = PerspectiveDifferentialEngine()
    result = engine.compare([])
    assert result.status == "NOT_APPLICABLE"


def test_two_identical_perspectives_have_zero_variance():
    engine = PerspectiveDifferentialEngine()
    p1 = Perspective("a", "yes", confidence=0.8, evidence_score=0.7, assumption_bias=0.2, novelty_score=0.1)
    p2 = Perspective("b", "yes", confidence=0.8, evidence_score=0.7, assumption_bias=0.2, novelty_score=0.1)
    result = engine.compare([p1, p2])
    assert result.status == "COMPUTED"
    assert result.confidence_variance == 0.0
    assert result.evidence_variance == 0.0


def test_diverging_perspectives_identify_primary_divergence_dimension():
    engine = PerspectiveDifferentialEngine()
    p1 = Perspective("a", "yes", confidence=0.9, evidence_score=0.5, assumption_bias=0.5, novelty_score=0.5)
    p2 = Perspective("b", "no", confidence=0.1, evidence_score=0.5, assumption_bias=0.5, novelty_score=0.5)
    result = engine.compare([p1, p2])
    assert result.status == "COMPUTED"
    assert result.primary_divergence_dimension == "confidence"
    assert result.confidence_variance > result.evidence_variance


def test_does_not_select_a_winner():
    """The engine reports variance only -- it must never add a field
    declaring one perspective correct or authoritative."""
    engine = PerspectiveDifferentialEngine()
    p1 = Perspective("a", "yes", confidence=0.99, evidence_score=0.99, assumption_bias=0.01)
    p2 = Perspective("b", "no", confidence=0.01, evidence_score=0.01, assumption_bias=0.99)
    result = engine.compare([p1, p2])
    d = result.to_dict()
    assert "winner" not in d
    assert "correct" not in d
    assert "truth" not in d


def test_three_perspectives_variance_computed():
    engine = PerspectiveDifferentialEngine()
    perspectives = [
        Perspective("a", "yes", confidence=0.9, evidence_score=0.8, assumption_bias=0.1),
        Perspective("b", "no", confidence=0.5, evidence_score=0.4, assumption_bias=0.6),
        Perspective("c", "unclear", confidence=0.3, evidence_score=0.9, assumption_bias=0.3),
    ]
    result = engine.compare(perspectives)
    assert result.status == "COMPUTED"
    assert len(result.perspectives) == 3


def test_to_dict_round_trips():
    engine = PerspectiveDifferentialEngine()
    p1 = Perspective("a", "yes", confidence=0.8, evidence_score=0.7, assumption_bias=0.2)
    p2 = Perspective("b", "no", confidence=0.3, evidence_score=0.4, assumption_bias=0.5)
    result = engine.compare([p1, p2])
    d = result.to_dict()
    assert d["status"] == "COMPUTED"
    assert len(d["perspectives"]) == 2
