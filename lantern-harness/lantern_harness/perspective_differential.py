"""PerspectiveDifferentialEngine: NEWLY ADDED in this harness turn. Not
part of Lantern v0.84, not a Perspective Mesh (no mesh/consensus/merge
logic exists here), not a Confidence Field, not a Decision State Machine.

This is a narrow, genuinely-implemented extension point: given two or
more independent Perspective records (each an observation about what a
distinct source/model/reasoner concluded, with its own confidence,
evidence, assumptions, and novelty), it computes variance across those
dimensions and reports where they diverge most. It does not resolve the
divergence, does not vote, does not average toward a "correct" answer,
and does not claim the highest-confidence or majority perspective is
right. Divergence is returned as a diagnostic signal for a human or a
future component to investigate -- never as proof.

If given fewer than two perspectives, this reports NOT_APPLICABLE rather
than fabricating a differential from a single data point.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from statistics import pvariance
from typing import Optional


@dataclass(frozen=True)
class Perspective:
    """One independent, already-produced conclusion. This module does
    not generate these -- callers supply them from wherever the actual
    reasoning happened (could be a real model call, a human, another
    Lantern node). Supplying a Perspective here does not validate it."""

    source: str
    conclusion: str
    confidence: float  # 0.0-1.0, as reported by the source -- a signal, not proof
    evidence_score: float  # 0.0-1.0, caller's own assessment of evidence strength
    assumption_bias: float  # 0.0-1.0, caller's own assessment of assumption reliance
    novelty_score: float = 0.0  # 0.0-1.0

    def to_dict(self) -> dict:
        return {
            "source": self.source,
            "conclusion": self.conclusion,
            "confidence": self.confidence,
            "evidence_score": self.evidence_score,
            "assumption_bias": self.assumption_bias,
            "novelty_score": self.novelty_score,
        }


@dataclass(frozen=True)
class DifferentialReading:
    status: str  # "NOT_APPLICABLE" | "COMPUTED"
    confidence_variance: Optional[float] = None
    evidence_variance: Optional[float] = None
    assumption_variance: Optional[float] = None
    novelty_variance: Optional[float] = None
    primary_divergence_dimension: Optional[str] = None
    perspectives: tuple = field(default_factory=tuple)
    note: str = ""

    def to_dict(self) -> dict:
        return {
            "status": self.status,
            "confidence_variance": self.confidence_variance,
            "evidence_variance": self.evidence_variance,
            "assumption_variance": self.assumption_variance,
            "novelty_variance": self.novelty_variance,
            "primary_divergence_dimension": self.primary_divergence_dimension,
            "perspectives": [p.to_dict() for p in self.perspectives],
            "note": self.note,
        }


class PerspectiveDifferentialEngine:
    """Computes variance across independent Perspectives. Does not
    merge, vote, or select a winner -- see module docstring."""

    def compare(self, perspectives: list) -> DifferentialReading:
        if perspectives is None:
            raise ValueError("perspectives must be a list, not None")
        if len(perspectives) < 2:
            return DifferentialReading(
                status="NOT_APPLICABLE",
                perspectives=tuple(perspectives),
                note=(
                    f"{len(perspectives)} perspective(s) supplied; a differential "
                    "requires at least 2 independent perspectives to compute variance "
                    "against. This is not a failure -- it is an honest report that "
                    "there is nothing to compare yet."
                ),
            )

        confidences = [p.confidence for p in perspectives]
        evidences = [p.evidence_score for p in perspectives]
        assumptions = [p.assumption_bias for p in perspectives]
        novelties = [p.novelty_score for p in perspectives]

        variances = {
            "confidence": pvariance(confidences),
            "evidence": pvariance(evidences),
            "assumption": pvariance(assumptions),
            "novelty": pvariance(novelties),
        }
        primary = max(variances, key=variances.get)

        return DifferentialReading(
            status="COMPUTED",
            confidence_variance=variances["confidence"],
            evidence_variance=variances["evidence"],
            assumption_variance=variances["assumption"],
            novelty_variance=variances["novelty"],
            primary_divergence_dimension=primary,
            perspectives=tuple(perspectives),
            note=(
                "Variance across supplied perspectives is a diagnostic signal for "
                "where further investigation may help. It does not determine which "
                "perspective (if any) is correct, and majority/highest-confidence "
                "is never auto-selected as truth."
            ),
        )
