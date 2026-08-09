from lantern.core import Lantern
from lantern.agent import LanternAgent
from lantern.evaluation import EvidenceEvaluationGate


def make_gate():
    lantern = Lantern()
    agent = LanternAgent(lantern)
    gate = EvidenceEvaluationGate(agent)
    return gate, agent


def test_evaluate_creates_candidate_without_evidence():
    gate, agent = make_gate()
    obs = agent.observe("water boils at 100C", "sensor", 0.8)

    result = gate.evaluate(obs.id, "boiling_point", sign=1)

    assert result.accepted is True
    assert result.action == "CANDIDATE_CREATED"
    assert len(agent.lantern.kernel.evidence) == 0
    assert result.evidence_id in gate.candidates


def test_evaluate_rejects_unknown_observation():
    gate, agent = make_gate()

    result = gate.evaluate("nonexistent", "boiling_point", sign=1)

    assert result.accepted is False
    assert result.action == "REJECTED"
    assert result.reason == "Observation not found"


def test_promote_creates_evidence_with_default_weight_matching_reliability():
    gate, agent = make_gate()
    obs = agent.observe("water boils at 100C", "sensor", 0.8)

    candidate = gate.evaluate(obs.id, "boiling_point", sign=1)
    result = gate.promote(candidate.evidence_id)

    assert result.accepted is True
    assert result.action == "EVIDENCE_CREATED"
    evidence = agent.lantern.kernel.evidence[0]
    # Default weight must resolve to exactly the observation's reliability,
    # not reliability applied twice (0.8, not 0.64).
    assert evidence.weight == 0.8


def test_promote_honors_explicit_weight_applied_once():
    gate, agent = make_gate()
    obs = agent.observe("water boils at 100C", "sensor", 0.8)

    candidate = gate.evaluate(obs.id, "boiling_point", sign=1, weight=0.5)
    gate.promote(candidate.evidence_id)

    evidence = agent.lantern.kernel.evidence[0]
    # add_evidence() multiplies by reliability once: 0.5 * 0.8
    assert evidence.weight == 0.4


def test_promote_consumes_candidate_and_blocks_double_promotion():
    gate, agent = make_gate()
    obs = agent.observe("water boils at 100C", "sensor", 0.8)

    candidate = gate.evaluate(obs.id, "boiling_point", sign=1)
    first = gate.promote(candidate.evidence_id)
    second = gate.promote(candidate.evidence_id)

    assert first.accepted is True
    assert second.accepted is False
    assert second.reason == "Candidate not found"
    assert len(agent.lantern.kernel.evidence) == 1


def test_promote_rejects_unknown_candidate():
    gate, agent = make_gate()

    result = gate.promote("nonexistent")

    assert result.accepted is False
    assert result.action == "REJECTED"
    assert result.reason == "Candidate not found"


def test_reject_removes_candidate_and_blocks_promotion():
    gate, agent = make_gate()
    obs = agent.observe("water boils at 100C", "sensor", 0.8)

    candidate = gate.evaluate(obs.id, "boiling_point", sign=1)
    reject_result = gate.reject(candidate.evidence_id, "bad source")
    promote_result = gate.promote(candidate.evidence_id)

    assert reject_result.accepted is False
    assert reject_result.reason == "bad source"
    assert promote_result.accepted is False
    assert promote_result.reason == "Candidate not found"
    assert len(agent.lantern.kernel.evidence) == 0
