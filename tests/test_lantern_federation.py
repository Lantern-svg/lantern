"""
Tests for lantern.federation.FederationAdapter.

Locks in the core federation rule: remote claims become local
Observations only. Remote confidence is inert metadata and must never
directly create Evidence or move local belief.
"""

from lantern.core import Lantern
from lantern.agent import LanternAgent
from lantern.federation import FederationAdapter, FederationResult
from lantern.protocol import create_observation_share


def make_adapter():
    lantern = Lantern()
    agent = LanternAgent(lantern)
    return FederationAdapter(agent), agent


def test_remote_observation_is_stored_as_local_observation():
    adapter, agent = make_adapter()

    message = create_observation_share(
        "peer_x",
        {"concept": "gravity", "content": "objects fall down", "confidence": 0.99},
    )

    result = adapter.receive_observation(message)

    assert isinstance(result, FederationResult)
    assert result.accepted is True
    assert result.observation_id in agent.lantern.kernel.observations

    obs = agent.lantern.kernel.observations[result.observation_id]
    assert obs.source == "remote:peer_x"
    assert obs.content == "objects fall down"


def test_remote_confidence_never_creates_evidence():
    adapter, agent = make_adapter()

    message = create_observation_share(
        "peer_x",
        {"concept": "gravity", "content": "objects fall down", "confidence": 0.99},
    )

    adapter.receive_observation(message)

    assert len(agent.lantern.kernel.evidence) == 0


def test_remote_observations_get_reduced_default_reliability():
    adapter, agent = make_adapter()

    message = create_observation_share(
        "peer_x",
        {"concept": "gravity", "content": "objects fall down", "confidence": 0.99},
    )

    result = adapter.receive_observation(message)

    obs = agent.lantern.kernel.observations[result.observation_id]
    assert obs.reliability == 0.5


def test_remote_confidence_never_moves_local_belief():
    adapter, agent = make_adapter()

    baseline = agent.ask_belief("gravity")

    message = create_observation_share(
        "peer_x",
        {"concept": "gravity", "content": "objects fall down", "confidence": 0.99},
    )

    adapter.receive_observation(message)

    assert agent.ask_belief("gravity") == baseline


def test_missing_confidence_defaults_to_zero():
    adapter, agent = make_adapter()

    message = create_observation_share(
        "peer_x",
        {"concept": "gravity", "content": "objects fall down"},
    )

    result = adapter.receive_observation(message)

    assert result.accepted is True
    assert len(agent.lantern.kernel.evidence) == 0


def test_remote_confidence_is_preserved_as_structured_metadata():
    adapter, agent = make_adapter()

    message = create_observation_share(
        "peer_x",
        {"concept": "gravity", "content": "objects fall down", "confidence": 0.9},
    )

    result = adapter.receive_observation(message)

    obs = agent.lantern.kernel.observations[result.observation_id]
    assert obs.metadata["claimed_concept"] == "gravity"
    assert obs.metadata["claimed_confidence"] == 0.9
    assert obs.metadata["remote_instance"] == "peer_x"
    assert obs.metadata["origin_type"] == "remote_lantern"
    assert len(agent.lantern.kernel.evidence) == 0


def test_multiple_remote_sources_create_separate_observations():
    adapter, agent = make_adapter()

    msg_a = create_observation_share(
        "peer_a", {"concept": "gravity", "content": "claim A", "confidence": 0.5}
    )
    msg_b = create_observation_share(
        "peer_b", {"concept": "gravity", "content": "claim B", "confidence": 0.5}
    )

    result_a = adapter.receive_observation(msg_a)
    result_b = adapter.receive_observation(msg_b)

    assert result_a.observation_id != result_b.observation_id
    assert len(agent.lantern.kernel.observations) == 2
