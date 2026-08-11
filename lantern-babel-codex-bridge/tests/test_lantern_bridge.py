"""
Tests for lantern.bridge.LanternAgentBridge.

Verifies the full path:

    ProtocolMessage -> LanternBoundary (capability-gated routing)
                     -> LanternAgentBridge._process
                     -> LanternAgent -> Lantern core

using real Lantern/LanternAgent instances (not mocks), so a payload
shape mismatch between protocol.py and agent.py would fail here even
if each module's own unit tests pass in isolation.
"""

from lantern.core import Lantern
from lantern.agent import LanternAgent
from lantern.bridge import LanternAgentBridge, BridgeResult, LOCAL_DEFAULT_RELIABILITY
from lantern.protocol import create_observation_share, create_evidence_request, create_codex_update


def make_bridge():
    lantern = Lantern()
    agent = LanternAgent(lantern)
    return LanternAgentBridge(agent), agent


def test_observation_share_creates_real_observation():
    """v0.93: a remote-declared reliability is a CLAIM, never the
    Observation's trusted reliability. It is preserved verbatim in
    metadata["claimed_reliability"] for provenance, but the trusted
    reliability always resolves to the local default (see
    bridge.LOCAL_DEFAULT_RELIABILITY), regardless of what the peer sent.
    """
    bridge, agent = make_bridge()
    compat = bridge.connect("0.82", {"evidence_exchange": True})

    message = create_observation_share(
        "peer_a",
        {"content": "sky is blue", "reliability": 0.9},
    )

    result = bridge.receive(message, compat)

    assert isinstance(result, BridgeResult)
    assert result.accepted is True
    assert result.action == "OBSERVATION_CREATED"
    assert len(agent.lantern.kernel.observations) == 1

    obs = next(iter(agent.lantern.kernel.observations.values()))
    assert obs.content == "sky is blue"
    assert obs.source == "peer_a"
    assert obs.reliability == LOCAL_DEFAULT_RELIABILITY
    assert obs.metadata["claimed_reliability"] == 0.9


def test_observation_share_defaults_claimed_reliability_when_absent():
    bridge, agent = make_bridge()
    compat = bridge.connect("0.82", {"evidence_exchange": True})

    message = create_observation_share("peer_a", {"content": "no reliability given"})

    result = bridge.receive(message, compat)

    assert result.accepted is True
    obs = next(iter(agent.lantern.kernel.observations.values()))
    assert obs.reliability == LOCAL_DEFAULT_RELIABILITY
    assert obs.metadata["claimed_reliability"] == 1.0


def test_higher_claimed_reliability_does_not_increase_trusted_reliability():
    """Direct proof that a malicious peer cannot raise its own epistemic
    influence merely by declaring a higher reliability value: the two
    cases below differ only in the claimed field, and must produce an
    identical trusted Observation.reliability.
    """
    bridge, agent = make_bridge()
    compat = bridge.connect("0.82", {"evidence_exchange": True})

    low = bridge.receive(
        create_observation_share("peer_a", {"content": "claim", "reliability": 0.01}),
        compat,
    )
    high = bridge.receive(
        create_observation_share("peer_a", {"content": "claim", "reliability": 999.0}),
        compat,
    )

    obs_low = agent.lantern.kernel.observations[low.data["observation"].id]
    obs_high = agent.lantern.kernel.observations[high.data["observation"].id]

    assert obs_low.reliability == obs_high.reliability == LOCAL_DEFAULT_RELIABILITY
    assert obs_low.metadata["claimed_reliability"] == 0.01
    assert obs_high.metadata["claimed_reliability"] == 999.0


def test_evidence_request_returns_belief():
    bridge, agent = make_bridge()
    compat = bridge.connect("0.82", {"belief_query": True})

    message = create_evidence_request("peer_a", "gravity")

    result = bridge.receive(message, compat)

    assert result.accepted is True
    assert result.action == "BELIEF_RETURNED"
    assert "belief" in result.data


def test_missing_capability_rejects_before_reaching_agent():
    bridge, agent = make_bridge()
    compat = bridge.connect("0.82", {})  # no capabilities granted

    message = create_observation_share("peer_a", {"content": "should not land"})

    result = bridge.receive(message, compat)

    assert result.accepted is False
    assert result.action == "REJECTED"
    assert len(agent.lantern.kernel.observations) == 0


def test_codex_update_is_not_wired_to_belief_mutation():
    """CODEX_UPDATE is deliberately unhandled: no trust-model decision
    has been made yet about whether a remote peer's claimed confidence
    should be allowed to influence local belief state.

    v0.89.1: codex_update is now disabled by default in
    DEFAULT_CAPABILITIES, so the boundary rejects it on capability
    grounds before the message ever reaches the router's handler
    dispatch. Either way, it never reaches the agent.
    """
    bridge, agent = make_bridge()
    compat = bridge.connect("0.82", {"codex_update": True})

    message = create_codex_update("peer_a", "gravity", 0.95, ["ev1", "ev2"])

    result = bridge.receive(message, compat)

    assert result.accepted is False
    assert result.action == "REJECTED"
    assert "codex_update" in result.reason
    assert len(agent.lantern.kernel.evidence) == 0


def test_unregistered_bridges_do_not_share_handler_state():
    bridge_a, agent_a = make_bridge()
    bridge_b, agent_b = make_bridge()

    compat = bridge_a.connect("0.82", {"evidence_exchange": True})
    message = create_observation_share("peer_a", {"content": "only for a"})

    bridge_a.receive(message, compat)

    assert len(agent_a.lantern.kernel.observations) == 1
    assert len(agent_b.lantern.kernel.observations) == 0
