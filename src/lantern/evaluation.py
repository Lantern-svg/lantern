"""
Lantern Evidence Evaluation Gate v0.87

Purpose:
    Convert observations into evidence only after evaluation.

Rules:
    - Observations are not beliefs.
    - Remote confidence is never copied into evidence weight.
    - Promotion requires an explicit decision.
    - Every promotion keeps provenance.
"""

from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import uuid4


@dataclass
class EvaluationResult:
    accepted: bool
    action: str
    reason: str
    observation_id: str
    evidence_id: str | None = None


@dataclass
class EvidenceCandidate:
    id: str
    observation_id: str
    concept: str
    weight: float
    sign: int
    evaluator: str
    created_at: str


class EvidenceEvaluationGate:

    def __init__(self, agent):
        self.agent = agent
        self.candidates = {}

    def evaluate(self, observation_id, concept, sign, weight=None, evaluator="local"):
        """
        Evaluate an observation.

        Does NOT automatically create evidence.
        """
        observation = self.agent.lantern.kernel.observations.get(observation_id)

        if observation is None:
            return EvaluationResult(
                False,
                "REJECTED",
                "Observation not found",
                observation_id,
            )

        # add_evidence() multiplies weight by the observation's reliability
        # when it turns this into Evidence. Default to a neutral weight (1.0)
        # so, absent an explicit evaluator judgment, the final evidence weight
        # comes from reliability alone instead of reliability applied twice.
        if weight is None:
            weight = 1.0

        candidate = EvidenceCandidate(
            id=str(uuid4()),
            observation_id=observation_id,
            concept=concept,
            weight=weight,
            sign=sign,
            evaluator=evaluator,
            created_at=datetime.now(timezone.utc).isoformat(),
        )

        self.candidates[candidate.id] = candidate

        return EvaluationResult(
            True,
            "CANDIDATE_CREATED",
            "Awaiting promotion decision",
            observation_id,
            candidate.id,
        )

    def promote(self, candidate_id):
        """
        Explicitly convert candidate into Evidence.
        """
        candidate = self.candidates.get(candidate_id)

        if candidate is None:
            return EvaluationResult(
                False,
                "REJECTED",
                "Candidate not found",
                "",
            )

        # add_evidence() already multiplies weight by the observation's
        # reliability, so a candidate weight that *is* the observation's
        # reliability (the evaluate() default) must not be pre-multiplied
        # here or the weight gets applied twice.
        evidence = self.agent.add_evidence(
            concept=candidate.concept,
            observation_id=candidate.observation_id,
            weight=candidate.weight,
            sign=candidate.sign,
        )

        # Consume the candidate so promotion is a one-time decision;
        # re-promoting the same candidate id must not create duplicate
        # evidence from a single evaluation.
        del self.candidates[candidate_id]

        return EvaluationResult(
            True,
            "EVIDENCE_CREATED",
            "Observation promoted",
            candidate.observation_id,
            evidence.id,
        )

    def reject(self, candidate_id, reason):
        if candidate_id in self.candidates:
            del self.candidates[candidate_id]

        return EvaluationResult(
            False,
            "REJECTED",
            reason,
            "",
        )
