"""Decision State Machine: explicit transitions over Confidence Field
bands. Recommends next action; never authorizes or executes anything.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from .confidence_field import ConfidenceFieldReading


ACTION_BY_STATE = {
    "HIGH": "INTEGRATE / PROCEED",
    "MEDIUM": "PRESERVE / GATHER",
    "LOW": "BRANCH / INVESTIGATE",
    "BLOCKED": "STOP / REPAIR",
}

ALLOWED_TRANSITIONS = {
    None: {"HIGH", "MEDIUM", "LOW", "BLOCKED"},
    "HIGH": {"HIGH", "MEDIUM", "BLOCKED"},
    "MEDIUM": {"HIGH", "MEDIUM", "LOW", "BLOCKED"},
    "LOW": {"MEDIUM", "LOW", "BLOCKED"},
    "BLOCKED": {"BLOCKED", "LOW", "MEDIUM", "HIGH"},
}


@dataclass(frozen=True)
class DecisionReading:
    state: str
    recommended_action: str
    reasons: tuple[str, ...]
    blockers: tuple[str, ...]
    what_would_change_state: tuple[str, ...]
    confidence_band: str
    confidence_score: float | str
    authorization_required: bool = True
    authorization_status: str = "NOT_EVALUATED"
    transition_from: Optional[str] = None
    transition_event: Optional[str] = None
    transition_allowed: bool = True
    explanation: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "state": self.state,
            "recommended_action": self.recommended_action,
            "reasons": list(self.reasons),
            "blockers": list(self.blockers),
            "what_would_change_state": list(self.what_would_change_state),
            "confidence_band": self.confidence_band,
            "confidence_score": self.confidence_score,
            "authorization_required": self.authorization_required,
            "authorization_status": self.authorization_status,
            "transition_from": self.transition_from,
            "transition_event": self.transition_event,
            "transition_allowed": self.transition_allowed,
            "explanation": dict(self.explanation),
        }


class DecisionStateMachine:
    """Maps current confidence into an explicit state + recommended
    action. This never calls tools, never mutates memory, never executes
    actions, and never substitutes for authorization."""

    def recommend(
        self,
        reading: ConfidenceFieldReading,
        *,
        previous_state: Optional[str] = None,
        transition_event: Optional[str] = None,
    ) -> DecisionReading:
        state = reading.confidence_band
        if state not in ACTION_BY_STATE:
            raise ValueError(f"unsupported confidence band: {state!r}")

        allowed = state in ALLOWED_TRANSITIONS.get(previous_state, set())
        if not allowed:
            raise ValueError(
                f"illegal state transition: {previous_state!r} -> {state!r}; allowed={sorted(ALLOWED_TRANSITIONS.get(previous_state, set()))}"
            )

        explanation = {
            "pipeline": "Evidence -> Confidence Field -> Decision State -> Capability Authorization -> Action Boundary",
            "decision_is_not_authorization": True,
            "integrity_status": reading.integrity_status,
            "validation_status": reading.validation_status,
        }
        if reading.compass_reading is not None:
            explanation["compass"] = reading.compass_reading

        return DecisionReading(
            state=state,
            recommended_action=ACTION_BY_STATE[state],
            reasons=reading.reasons,
            blockers=reading.blockers,
            what_would_change_state=reading.what_would_change_state,
            confidence_band=reading.confidence_band,
            confidence_score=reading.confidence_score,
            authorization_required=True,
            authorization_status="NOT_EVALUATED",
            transition_from=previous_state,
            transition_event=transition_event,
            transition_allowed=True,
            explanation=explanation,
        )
