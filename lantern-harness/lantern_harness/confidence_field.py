"""Confidence Field: read-only interpretation layer over existing Lantern
state. This is NOT a second evidence system, NOT a second contradiction
system, NOT truth, and NOT authorization.

It reads the real EvidenceKernel / Chronicle integrity / Scars / Compass
/ optional PerspectiveDifferential signal and produces an interpretable
current confidence snapshot for one concept. If integrity fails, the
result is HARD BLOCKED rather than merely low confidence.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional, Sequence

from lantern import compass

from .bridge import LanternBridge
from .perspective_differential import Perspective, PerspectiveDifferentialEngine


HIGH_THRESHOLD = 0.55
MEDIUM_THRESHOLD = 0.30


@dataclass(frozen=True)
class ConfidenceFieldReading:
    concept: Optional[str]
    confidence_score: float | str
    evidence_strength: float | str
    contradiction_pressure: float | str
    uncertainty_pressure: float | str
    assumption_pressure: float | str
    perspective_divergence: float | str
    integrity_status: str
    validation_status: str
    confidence_band: str
    reasons: tuple[str, ...] = field(default_factory=tuple)
    blockers: tuple[str, ...] = field(default_factory=tuple)
    missing_information: tuple[str, ...] = field(default_factory=tuple)
    what_would_change_state: tuple[str, ...] = field(default_factory=tuple)
    inputs: dict[str, Any] = field(default_factory=dict)
    calculation: str = ""
    interpretation: str = ""
    limitations: tuple[str, ...] = field(default_factory=tuple)
    compass_reading: Optional[dict[str, Any]] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "concept": self.concept,
            "confidence_score": self.confidence_score,
            "evidence_strength": self.evidence_strength,
            "contradiction_pressure": self.contradiction_pressure,
            "uncertainty_pressure": self.uncertainty_pressure,
            "assumption_pressure": self.assumption_pressure,
            "perspective_divergence": self.perspective_divergence,
            "integrity_status": self.integrity_status,
            "validation_status": self.validation_status,
            "confidence_band": self.confidence_band,
            "reasons": list(self.reasons),
            "blockers": list(self.blockers),
            "missing_information": list(self.missing_information),
            "what_would_change_state": list(self.what_would_change_state),
            "inputs": dict(self.inputs),
            "calculation": self.calculation,
            "interpretation": self.interpretation,
            "limitations": list(self.limitations),
            "compass_reading": self.compass_reading,
        }


class ConfidenceField:
    """Read-only calculation layer over existing Lantern state.

    Score definition (only when integrity is valid/no-chronicle):
        confidence_score = clamp(
            0.45 * evidence_strength
          - 0.20 * contradiction_pressure
          - 0.15 * uncertainty_pressure
          - 0.10 * assumption_pressure
          - 0.10 * perspective_divergence
        )

    All sub-signals are 0.0-1.0 and correspond to concrete, explainable
    inputs derived from existing Lantern records or caller-supplied
    context. No false precision beyond this simple linear combination is
    claimed; the formula is included in every reading.
    """

    def __init__(
        self,
        bridge: LanternBridge,
        perspective_engine: Optional[PerspectiveDifferentialEngine] = None,
    ):
        self.bridge = bridge
        self.perspective_engine = perspective_engine or PerspectiveDifferentialEngine()

    def evaluate(
        self,
        *,
        concept: Optional[str],
        perspectives: Optional[Sequence[Perspective]] = None,
        assumptions: Optional[Sequence[str]] = None,
        validation_status: Optional[str] = None,
        scars: Optional[Sequence[Any]] = None,
        include_compass: bool = True,
    ) -> ConfidenceFieldReading:
        if concept is not None and not isinstance(concept, str):
            raise ValueError("concept must be a string or None")
        if perspectives is None:
            perspectives = ()
        if assumptions is None:
            assumptions = ()
        if scars is None:
            scars = ()

        integrity = self.bridge.witness_integrity()
        integrity_status = integrity.get("status", "UNKNOWN")

        if integrity_status not in ("VALID", "NO_CHRONICLE"):
            return ConfidenceFieldReading(
                concept=concept,
                confidence_score="BLOCKED",
                evidence_strength="BLOCKED",
                contradiction_pressure="BLOCKED",
                uncertainty_pressure="BLOCKED",
                assumption_pressure="BLOCKED",
                perspective_divergence="BLOCKED",
                integrity_status=integrity_status,
                validation_status="BLOCKED",
                confidence_band="BLOCKED",
                reasons=(
                    "Chronicle integrity is not established; current evidence state cannot be trusted for decision support.",
                ),
                blockers=(
                    f"witness_integrity() returned {integrity_status}",
                ),
                missing_information=(
                    "restore Chronicle integrity before relying on evidence-derived confidence",
                ),
                what_would_change_state=(
                    "repair or restore the Chronicle and re-run integrity verification",
                ),
                inputs={"integrity": integrity},
                calculation="hard boundary: integrity failure => confidence_band BLOCKED",
                interpretation="BLOCKED is more severe than LOW: the system is refusing to trust the underlying state, not merely expressing weak support.",
                limitations=(
                    "No confidence score is produced while integrity is failed or errored.",
                ),
                compass_reading=None,
            )

        kernel = self.bridge.lantern.kernel
        current_step = kernel.step
        concept_evidence = [e for e in kernel.evidence if concept is None or e.concept == concept]
        related_observation_ids = {e.observation_id for e in concept_evidence}
        related_observations = [kernel.observations[oid] for oid in related_observation_ids if oid in kernel.observations]
        open_contradictions = [
            c for c in kernel.contradictions
            if c.status == "OPEN" and (concept is None or c.concept == concept)
        ]
        resolved_contradictions = [
            c for c in kernel.contradictions
            if c.status == "RESOLVED" and (concept is None or c.concept == concept)
        ]

        positive_support = sum(
            e.decayed_weight(current_step)
            for e in concept_evidence
            if e.sign == 1
        )
        negative_support = sum(
            e.decayed_weight(current_step)
            for e in concept_evidence
            if e.sign == -1
        )
        total_support = positive_support + negative_support
        evidence_strength = min(1.0, positive_support / max(1.0, total_support)) if total_support > 0 else 0.0

        contradiction_pressure = min(
            1.0,
            sum(c.current_severity for c in open_contradictions) / max(1.0, total_support),
        ) if total_support > 0 else (1.0 if open_contradictions else 0.0)

        reliability_values = [obs.reliability for obs in related_observations]
        avg_reliability = sum(reliability_values) / len(reliability_values) if reliability_values else 0.0
        independent_sources = {obs.source for obs in related_observations}
        independence_bonus = min(1.0, len(independent_sources) / 3.0)

        # uncertainty increases when there is little evidence, weak reliability,
        # few independent observations, or explicit contradiction pressure.
        uncertainty_pressure = min(
            1.0,
            max(
                0.0,
                0.45 * (1.0 - min(1.0, total_support))
                + 0.30 * (1.0 - avg_reliability)
                + 0.15 * (1.0 - independence_bonus)
                + 0.10 * contradiction_pressure,
            ),
        )

        assumption_pressure = min(1.0, len(assumptions) / 5.0)

        differential = None
        if len(perspectives) >= 2:
            differential = self.perspective_engine.compare(list(perspectives))
            perspective_divergence = min(
                1.0,
                max(
                    differential.confidence_variance or 0.0,
                    differential.evidence_variance or 0.0,
                    differential.assumption_variance or 0.0,
                    differential.novelty_variance or 0.0,
                ) * 4.0,
            )
        else:
            perspective_divergence = 0.0 if len(perspectives) == 0 else "UNKNOWN"

        if validation_status is None:
            if total_support == 0:
                validation_status = "UNVERIFIED"
            elif open_contradictions:
                validation_status = "CONTESTED"
            elif avg_reliability >= 0.8 and len(independent_sources) >= 2:
                validation_status = "SUPPORTED"
            else:
                validation_status = "PARTIAL"

        scar_caution = 0.0
        scar_reasons: list[str] = []
        for scar in scars:
            outcome = getattr(getattr(scar, "scar", scar), "outcome", None)
            lesson = getattr(getattr(scar, "scar", scar), "lesson", None)
            if outcome in {"FAILED_HANDSHAKE", "CONTRADICTORY_OBSERVATION", "INTEGRATION_ROLLBACK", "INVALID_PROVENANCE"}:
                scar_caution = min(0.2, scar_caution + 0.1)
                if lesson:
                    scar_reasons.append(f"scar lesson: {lesson}")
                else:
                    scar_reasons.append(f"scar outcome noted: {outcome}")
        uncertainty_pressure = min(1.0, uncertainty_pressure + scar_caution)

        if perspective_divergence == "UNKNOWN":
            divergence_penalty = 0.05
        else:
            divergence_penalty = 0.10 * perspective_divergence

        confidence_score = max(
            0.0,
            min(
                1.0,
                0.55 * evidence_strength
                + 0.20 * avg_reliability
                + 0.10 * independence_bonus
                - 0.20 * contradiction_pressure
                - 0.10 * uncertainty_pressure
                - 0.05 * assumption_pressure
                - divergence_penalty,
            ),
        )

        if validation_status in {"UNVERIFIED", "CONTESTED"}:
            confidence_score = max(0.0, confidence_score - 0.10)

        if (
            confidence_score >= HIGH_THRESHOLD
            and validation_status in {"SUPPORTED", "PARTIAL"}
            and contradiction_pressure < 0.25
            and len(independent_sources) >= 2
            and uncertainty_pressure <= 0.35
            and assumption_pressure <= 0.20
        ):
            band = "HIGH"
        elif confidence_score >= MEDIUM_THRESHOLD:
            band = "MEDIUM"
        else:
            band = "LOW"

        reasons: list[str] = []
        blockers: list[str] = []
        missing_information: list[str] = []
        what_would_change_state: list[str] = []

        if positive_support > 0:
            reasons.append(
                f"positive evidence support={positive_support:.3f} across {len(concept_evidence)} evidence record(s)"
            )
        else:
            reasons.append("no supporting evidence is currently recorded")
            missing_information.append("supporting evidence for the concept")
            what_would_change_state.append("record one or more relevant supporting observations/evidence links")

        if related_observations:
            reasons.append(
                f"{len(related_observations)} linked observation(s) from {len(independent_sources)} independent source(s); average reliability={avg_reliability:.2f}"
            )
            if len(independent_sources) < 2:
                missing_information.append("more independent observation sources")
                what_would_change_state.append("obtain independent corroboration from a distinct source")
        else:
            missing_information.append("observations linked to evidence")
            blockers.append("evidence exists without retrievable linked observations")
            what_would_change_state.append("repair or restore linked observations for the evidence")

        if open_contradictions:
            reasons.append(f"{len(open_contradictions)} unresolved contradiction(s) remain open")
            blockers.append("unresolved contradiction pressure is present")
            what_would_change_state.append("resolve or supersede open contradictions with better evidence")
        elif resolved_contradictions:
            reasons.append(f"{len(resolved_contradictions)} contradiction(s) were resolved historically")

        if assumptions:
            reasons.append(f"assumption load={len(assumptions)} explicit assumption(s)")
            what_would_change_state.append("replace assumptions with directly observed or externally validated evidence")

        if perspective_divergence == "UNKNOWN":
            missing_information.append("at least one more independent perspective to compute divergence")
        elif perspective_divergence > 0.35:
            reasons.append(f"perspective divergence is elevated ({perspective_divergence:.2f})")
            what_would_change_state.append("explain why perspectives diverge or gather adjudicating evidence")
        elif len(perspectives) >= 2:
            reasons.append(f"perspective divergence is limited ({perspective_divergence:.2f})")

        if validation_status == "UNVERIFIED":
            blockers.append("validation is UNVERIFIED")
            what_would_change_state.append("add externally checkable validation or stronger independent evidence")
        elif validation_status == "CONTESTED":
            blockers.append("validation is CONTESTED by unresolved contradiction")
        else:
            reasons.append(f"validation status={validation_status}")

        reasons.extend(scar_reasons)

        compass_reading = None
        if include_compass:
            compass_reading = compass.orient(
                kernel=kernel,
                concepts_of_interest=(concept,) if concept else (),
            ).to_dict()

        return ConfidenceFieldReading(
            concept=concept,
            confidence_score=round(confidence_score, 3),
            evidence_strength=round(evidence_strength, 3),
            contradiction_pressure=round(contradiction_pressure, 3),
            uncertainty_pressure=round(uncertainty_pressure, 3),
            assumption_pressure=round(assumption_pressure, 3),
            perspective_divergence=perspective_divergence if perspective_divergence == "UNKNOWN" else round(perspective_divergence, 3),
            integrity_status=integrity_status,
            validation_status=validation_status,
            confidence_band=band,
            reasons=tuple(reasons),
            blockers=tuple(dict.fromkeys(blockers)),
            missing_information=tuple(dict.fromkeys(missing_information)),
            what_would_change_state=tuple(dict.fromkeys(what_would_change_state)),
            inputs={
                "current_step": current_step,
                "positive_support": round(positive_support, 6),
                "negative_support": round(negative_support, 6),
                "total_support": round(total_support, 6),
                "observations": len(related_observations),
                "independent_sources": sorted(independent_sources),
                "avg_reliability": round(avg_reliability, 6),
                "assumptions": list(assumptions),
                "open_contradictions": len(open_contradictions),
                "perspectives": len(perspectives),
                "differential": differential.to_dict() if differential is not None else None,
            },
            calculation=(
                "confidence_score = clamp(0.55*evidence_strength + 0.20*avg_reliability "
                "+ 0.10*independence_bonus - 0.20*contradiction_pressure "
                "- 0.10*uncertainty_pressure - 0.05*assumption_pressure "
                "- perspective_penalty); perspective_penalty = 0.10*perspective_divergence "
                "when known, else 0.05; validation_status UNVERIFIED/CONTESTED subtracts 0.05."
            ),
            interpretation=(
                f"{band} means the currently available validated information supports proceeding at a {band.lower()} confidence level under present conditions; it does not assert truth."
            ),
            limitations=(
                "Confidence is an interpretable summary over current signals, not proof.",
                "Perspective divergence raises investigation pressure but is not treated as falsehood.",
                "Assumption pressure is caller-supplied and therefore only as good as the caller's explicit assumption list.",
            ),
            compass_reading=compass_reading,
        )
