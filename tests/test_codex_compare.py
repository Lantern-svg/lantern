from lantern.core import Lantern
from lantern.codex_compare import compare_beliefs, comparison_summary


def add_evidence(lantern, concept, weight, sign):
    obs = lantern.kernel.observe("content", "source", 1.0)
    lantern.kernel.add_evidence(concept, obs.id, weight, sign)


def test_agreement_when_beliefs_are_close():
    a, b = Lantern(), Lantern()
    add_evidence(a, "sky_blue", 1.0, 1)
    add_evidence(b, "sky_blue", 1.0, 1)

    result = compare_beliefs(a, b)

    assert len(result.comparisons) == 1
    assert result.comparisons[0].category == "agreement"


def test_contradiction_when_beliefs_diverge_across_midpoint():
    a, b = Lantern(), Lantern()
    add_evidence(a, "flat_earth", 1.0, 1)
    add_evidence(b, "flat_earth", 1.0, -1)

    result = compare_beliefs(a, b)

    assert result.comparisons[0].category == "contradiction"


def test_confidence_gap_when_same_lean_but_different_magnitude():
    a, b = Lantern(), Lantern()
    add_evidence(a, "rain_tomorrow", 1.0, 1)
    add_evidence(b, "rain_tomorrow", 0.2, 1)

    result = compare_beliefs(a, b)

    assert result.comparisons[0].category == "confidence_gap"


def test_missing_evidence_when_only_one_side_has_the_concept():
    a, b = Lantern(), Lantern()
    add_evidence(a, "only_in_a", 1.0, 1)

    result = compare_beliefs(a, b)

    assert result.comparisons[0].category == "missing_evidence"
    assert result.comparisons[0].belief_b is None
    assert result.comparisons[0].belief_a is not None


def test_missing_evidence_does_not_read_neutral_belief_as_agreement():
    # Regression guard: EvidenceKernel.belief() returns 0.5 for a concept
    # with zero evidence. If missing-evidence weren't checked explicitly
    # first, this would be misread as "agreement" against A's real belief
    # whenever A's belief happens to also be near 0.5.
    a, b = Lantern(), Lantern()
    obs = a.kernel.observe("weak", "source", 1.0)
    a.kernel.add_evidence("borderline", obs.id, 0.01, 1)

    result = compare_beliefs(a, b)

    assert result.comparisons[0].category == "missing_evidence"


def test_comparison_summary_counts_categories():
    a, b = Lantern(), Lantern()
    add_evidence(a, "sky_blue", 1.0, 1)
    add_evidence(b, "sky_blue", 1.0, 1)
    add_evidence(a, "flat_earth", 1.0, 1)
    add_evidence(b, "flat_earth", 1.0, -1)

    result = compare_beliefs(a, b)
    summary = comparison_summary(result)

    assert summary == {"agreement": 1, "contradiction": 1}


def test_by_category_filters_comparisons():
    a, b = Lantern(), Lantern()
    add_evidence(a, "sky_blue", 1.0, 1)
    add_evidence(b, "sky_blue", 1.0, 1)
    add_evidence(a, "only_in_a", 1.0, 1)

    result = compare_beliefs(a, b)

    assert len(result.by_category("agreement")) == 1
    assert len(result.by_category("missing_evidence")) == 1
    assert len(result.by_category("contradiction")) == 0


def test_explicit_concepts_list_restricts_comparison_scope():
    a, b = Lantern(), Lantern()
    add_evidence(a, "sky_blue", 1.0, 1)
    add_evidence(b, "sky_blue", 1.0, 1)
    add_evidence(a, "flat_earth", 1.0, 1)
    add_evidence(b, "flat_earth", 1.0, -1)

    result = compare_beliefs(a, b, concepts=["sky_blue"])

    assert len(result.comparisons) == 1
    assert result.comparisons[0].concept == "sky_blue"
