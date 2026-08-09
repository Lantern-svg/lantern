from lantern.core import Lantern
from lantern.codex_compare import compare_beliefs
from lantern.codex_explanation import explain_comparison, explain_comparisons


def add_evidence(lantern, concept, source, reliability, weight, sign):
    obs = lantern.kernel.observe("content", source, reliability)
    lantern.kernel.add_evidence(concept, obs.id, weight, sign)


def test_explanation_never_mutates_kernel_state():
    a, b = Lantern(), Lantern()
    add_evidence(a, "sky_blue", "sensor", 1.0, 1.0, 1)
    add_evidence(b, "sky_blue", "sensor", 1.0, 1.0, 1)

    result = compare_beliefs(a, b)
    before_evidence_a = len(a.kernel.evidence)
    before_evidence_b = len(b.kernel.evidence)
    before_contradictions_a = len(a.kernel.contradictions)

    explain_comparisons(result, a, b)

    assert len(a.kernel.evidence) == before_evidence_a
    assert len(b.kernel.evidence) == before_evidence_b
    assert len(a.kernel.contradictions) == before_contradictions_a


def test_missing_evidence_explanation_names_the_missing_side():
    a, b = Lantern(), Lantern()
    add_evidence(a, "only_in_a", "sensor", 1.0, 1.0, 1)

    result = compare_beliefs(a, b)
    explanation = explain_comparison(result.comparisons[0], a, b)

    assert explanation.category == "missing_evidence"
    assert "Lantern B" in explanation.cause
    assert any("Lantern B" in item for item in explanation.missing_information)
    assert len(explanation.supporting_factors) == 1


def test_contradiction_explanation_reports_both_sides():
    a, b = Lantern(), Lantern()
    add_evidence(a, "flat_earth", "sensor_a", 1.0, 1.0, 1)
    add_evidence(b, "flat_earth", "shaky_sensor", 0.3, 1.0, -1)

    result = compare_beliefs(a, b)
    explanation = explain_comparison(result.comparisons[0], a, b)

    assert explanation.category == "contradiction"
    assert len(explanation.supporting_factors) == 2
    assert any("Lantern B" in item for item in explanation.missing_information)


def test_confidence_gap_explanation_notes_evidence_count_difference():
    a, b = Lantern(), Lantern()
    add_evidence(a, "rain_tomorrow", "sensor_a", 1.0, 1.0, 1)
    add_evidence(a, "rain_tomorrow", "sensor_b", 1.0, 1.0, 1)
    add_evidence(b, "rain_tomorrow", "sensor_c", 1.0, 0.2, 1)

    result = compare_beliefs(a, b)
    explanation = explain_comparison(result.comparisons[0], a, b)

    assert explanation.category == "confidence_gap"
    assert any("Evidence counts differ" in item for item in explanation.missing_information)


def test_agreement_explanation_has_no_missing_information():
    a, b = Lantern(), Lantern()
    add_evidence(a, "sky_blue", "sensor", 1.0, 1.0, 1)
    add_evidence(b, "sky_blue", "sensor", 1.0, 1.0, 1)

    result = compare_beliefs(a, b)
    explanation = explain_comparison(result.comparisons[0], a, b)

    assert explanation.category == "agreement"
    assert explanation.missing_information == []


def test_explanation_preserves_belief_values_from_comparison():
    a, b = Lantern(), Lantern()
    add_evidence(a, "sky_blue", "sensor", 1.0, 1.0, 1)
    add_evidence(b, "sky_blue", "sensor", 1.0, 1.0, 1)

    result = compare_beliefs(a, b)
    comparison = result.comparisons[0]
    explanation = explain_comparison(comparison, a, b)

    assert explanation.belief_a == comparison.belief_a
    assert explanation.belief_b == comparison.belief_b
    assert explanation.concept == comparison.concept


def test_explain_comparisons_returns_one_explanation_per_comparison():
    a, b = Lantern(), Lantern()
    add_evidence(a, "sky_blue", "sensor", 1.0, 1.0, 1)
    add_evidence(b, "sky_blue", "sensor", 1.0, 1.0, 1)
    add_evidence(a, "only_in_a", "sensor", 1.0, 1.0, 1)

    result = compare_beliefs(a, b)
    explanations = explain_comparisons(result, a, b)

    assert len(explanations) == len(result.comparisons)
    categories = {e.category for e in explanations}
    assert categories == {"agreement", "missing_evidence"}
