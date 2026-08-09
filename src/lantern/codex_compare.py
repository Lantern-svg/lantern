"""
Lantern Codex Comparison v0.88

Purpose:
    Compare belief state between two Lantern instances and produce a
    perspective difference map.

Rule:
    A concept is only "compared" if both sides actually hold evidence
    for it. EvidenceKernel.belief() returns a neutral 0.5 for a concept
    with zero evidence, so evidence presence is checked explicitly
    first, before any belief values are read. Otherwise a genuinely
    missing concept on one side would be misread as false agreement
    or a false confidence gap against the other side's real 0.5 belief.

    Lantern A belief state
      +
    Lantern B belief state
      |
      v
    Perspective Difference Map
      |
      +--> agreement
      +--> contradiction
      +--> missing evidence
      +--> confidence gap
"""

from dataclasses import dataclass, field


@dataclass
class ConceptComparison:
    concept: str
    belief_a: float | None
    belief_b: float | None
    category: str
    detail: str


@dataclass
class ComparisonResult:
    comparisons: list = field(default_factory=list)

    def by_category(self, category):
        return [c for c in self.comparisons if c.category == category]


def _concepts_with_evidence(kernel):
    return {e.concept for e in kernel.evidence}


def compare_beliefs(
    lantern_a,
    lantern_b,
    concepts=None,
    agreement_threshold=0.1,
    contradiction_threshold=0.3,
):
    """
    Build a perspective difference map between two Lantern instances.

    agreement_threshold: max belief gap still counted as agreement.
    contradiction_threshold: min belief gap, on opposite sides of 0.5,
        required to call it a contradiction rather than a confidence gap.
    """
    kernel_a = lantern_a.kernel
    kernel_b = lantern_b.kernel

    concepts_a = _concepts_with_evidence(kernel_a)
    concepts_b = _concepts_with_evidence(kernel_b)

    if concepts is None:
        concepts = sorted(concepts_a | concepts_b)

    result = ComparisonResult()

    for concept in concepts:
        has_a = concept in concepts_a
        has_b = concept in concepts_b

        if not has_a or not has_b:
            belief_a = kernel_a.belief(concept) if has_a else None
            belief_b = kernel_b.belief(concept) if has_b else None
            missing_side = "A" if not has_a else "B"
            result.comparisons.append(
                ConceptComparison(
                    concept,
                    belief_a,
                    belief_b,
                    "missing_evidence",
                    f"No evidence for '{concept}' in Lantern {missing_side}",
                )
            )
            continue

        belief_a = kernel_a.belief(concept)
        belief_b = kernel_b.belief(concept)
        gap = abs(belief_a - belief_b)
        side_a = belief_a >= 0.5
        side_b = belief_b >= 0.5

        if side_a != side_b and gap >= contradiction_threshold:
            category = "contradiction"
            detail = (
                f"Beliefs diverge across 0.5: A={belief_a:.3f} B={belief_b:.3f}"
            )
        elif gap >= agreement_threshold:
            category = "confidence_gap"
            detail = f"Same lean, gap={gap:.3f}: A={belief_a:.3f} B={belief_b:.3f}"
        else:
            category = "agreement"
            detail = f"Beliefs align, gap={gap:.3f}: A={belief_a:.3f} B={belief_b:.3f}"

        result.comparisons.append(
            ConceptComparison(concept, belief_a, belief_b, category, detail)
        )

    return result


def comparison_summary(result):
    counts = {}
    for comparison in result.comparisons:
        counts[comparison.category] = counts.get(comparison.category, 0) + 1
    return counts
