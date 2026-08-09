"""
Lantern Codex Explanation v0.89

Purpose:
    Explain WHY two Lantern perspectives differ on a concept.

Input:
    A ConceptComparison (from codex_compare.compare_beliefs) plus the
    two Lantern instances it was built from.

Rules:
    - Never change beliefs.
    - Never resolve contradictions automatically.
    - Only explain divergence.
    - Must preserve provenance (concept, beliefs, and evidence sources
      the explanation is based on are carried in the result).

This module is read-only: it inspects kernel.evidence/observations to
build a human-readable account of *why* a comparison category was
reached, but writes nothing back to either kernel.
"""

from dataclasses import dataclass, field


@dataclass
class Explanation:
    concept: str
    category: str
    belief_a: float | None
    belief_b: float | None
    cause: str
    supporting_factors: list = field(default_factory=list)
    missing_information: list = field(default_factory=list)


def _concept_stats(kernel, concept):
    related = [e for e in kernel.evidence if e.concept == concept]

    if not related:
        return None

    positive = [e for e in related if e.sign == 1]
    negative = [e for e in related if e.sign == -1]

    reliabilities = []
    sources = []
    for evidence in related:
        obs = kernel.observations.get(evidence.observation_id)
        if obs is not None:
            reliabilities.append(obs.reliability)
            sources.append(obs.source)

    avg_reliability = (
        sum(reliabilities) / len(reliabilities) if reliabilities else None
    )

    return {
        "evidence_count": len(related),
        "positive_count": len(positive),
        "negative_count": len(negative),
        "avg_reliability": avg_reliability,
        "sources": sources,
    }


def _describe_side(label, stats):
    if stats is None:
        return f"Lantern {label} has no evidence for this concept"

    reliability_text = (
        f"{stats['avg_reliability']:.2f}"
        if stats["avg_reliability"] is not None
        else "unknown"
    )
    return (
        f"Lantern {label}: {stats['evidence_count']} evidence entries "
        f"({stats['positive_count']} supporting, {stats['negative_count']} "
        f"opposing), avg source reliability {reliability_text}"
    )


def explain_comparison(comparison, lantern_a, lantern_b):
    """
    Build an Explanation for a single ConceptComparison.
    """
    stats_a = _concept_stats(lantern_a.kernel, comparison.concept)
    stats_b = _concept_stats(lantern_b.kernel, comparison.concept)

    supporting_factors = []
    missing_information = []

    if comparison.category == "missing_evidence":
        missing_side = "A" if comparison.belief_a is None else "B"
        present_stats = stats_b if missing_side == "A" else stats_a
        present_label = "B" if missing_side == "A" else "A"

        cause = (
            f"No evidence exists for '{comparison.concept}' in "
            f"Lantern {missing_side}"
        )
        if present_stats is not None:
            supporting_factors.append(_describe_side(present_label, present_stats))
        missing_information.append(
            f"No observations for '{comparison.concept}' in Lantern {missing_side}"
        )

    elif comparison.category == "contradiction":
        cause = "Conflicting observations support opposite conclusions"
        supporting_factors.append(_describe_side("A", stats_a))
        supporting_factors.append(_describe_side("B", stats_b))

        for label, stats in (("A", stats_a), ("B", stats_b)):
            if stats and stats["avg_reliability"] is not None and stats["avg_reliability"] < 0.5:
                missing_information.append(
                    f"Lantern {label}'s evidence relies on low-reliability sources"
                )

    elif comparison.category == "confidence_gap":
        cause = "Same directional lean, but different evidence strength"
        supporting_factors.append(_describe_side("A", stats_a))
        supporting_factors.append(_describe_side("B", stats_b))

        if stats_a and stats_b:
            if stats_a["evidence_count"] != stats_b["evidence_count"]:
                missing_information.append(
                    "Evidence counts differ between Lanterns; the side with "
                    "fewer observations may be under-informed rather than "
                    "genuinely less confident"
                )

    else:  # agreement
        cause = "Similar evidence-backed beliefs"
        supporting_factors.append(_describe_side("A", stats_a))
        supporting_factors.append(_describe_side("B", stats_b))

    return Explanation(
        concept=comparison.concept,
        category=comparison.category,
        belief_a=comparison.belief_a,
        belief_b=comparison.belief_b,
        cause=cause,
        supporting_factors=supporting_factors,
        missing_information=missing_information,
    )


def explain_comparisons(result, lantern_a, lantern_b):
    """
    Build an Explanation for every ConceptComparison in a ComparisonResult.
    """
    return [
        explain_comparison(comparison, lantern_a, lantern_b)
        for comparison in result.comparisons
    ]
