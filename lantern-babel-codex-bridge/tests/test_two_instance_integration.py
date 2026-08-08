"""
Two-instance Lantern integration test (Basic Protocol bootstrap).

Demonstrates the actual live path shipped in this repo:

    ProtocolMessage
      -> compatibility (negotiate / compatible_versions)
      -> handshake (create_handshake / evaluate_handshake)
      -> capability negotiation (can_exchange)
      -> LanternBoundary
      -> LanternRouter
      -> LanternAgentBridge
      -> LanternAgent
      -> Lantern core (EvidenceKernel)
      -> Chronicle (audit chain)

This is the canonical "Lantern A talks to Lantern B" path: every
message is capability-gated end to end via LanternBoundary/
LanternRouter, matching the bootstrap requirement that two peers must
negotiate capabilities before anything reaches the receiving agent or
core.

Note on federation.py: lantern.federation.FederationAdapter is a
separate, NOT capability-gated remote-ingestion path (it calls
agent.observe() directly from a message, bypassing LanternBoundary/
LanternRouter entirely). It is exercised by its own dedicated test
file (test_lantern_federation.py) and is intentionally not used here.
bridge.py is the canonical two-instance route for this bootstrap
milestone because it is the one path that actually enforces
handshake -> compatibility -> capability negotiation before any
message reaches the agent, matching the required diagram exactly.
See BOOTSTRAP report for this as a flagged CORE open item (two
parallel remote-observation-ingestion paths with different trust
semantics for the reliability/confidence field).
"""

from lantern.core import Lantern
from lantern.agent import LanternAgent
from lantern.bridge import LanternAgentBridge
from lantern.handshake import evaluate_handshake
from lantern.protocol import create_observation_share, create_codex_update


def make_instance():
    lantern = Lantern()
    agent = LanternAgent(lantern)
    bridge = LanternAgentBridge(agent)
    return lantern, agent, bridge


# ==================================================
# 1. Valid handshake
# ==================================================

def test_valid_handshake_between_two_instances():
    _, _, bridge_a = make_instance()

    request = bridge_a.boundary.handshake()
    response = evaluate_handshake(request)

    assert response.accepted is True
    assert response.reason == "Compatible"


# ==================================================
# 2. Compatible versions + capability negotiation
# ==================================================

def test_compatible_versions_and_capability_negotiation():
    _, _, bridge_a = make_instance()
    _, _, bridge_b = make_instance()

    request = bridge_a.boundary.handshake()
    compat = bridge_b.connect(request.protocol_version, request.capabilities)

    assert compat.compatible is True
    assert compat.shared_capabilities.get("evidence_exchange") is True
    assert compat.shared_capabilities.get("belief_query") is True
    # codex_update is disabled on both sides -- never shared.
    assert "codex_update" not in compat.shared_capabilities


# ==================================================
# 3. Valid observation exchange reaches Lantern B's core
# ==================================================

def test_valid_observation_exchange_reaches_lantern_b_core():
    _, _, bridge_a = make_instance()
    _, agent_b, bridge_b = make_instance()

    handshake = bridge_a.boundary.handshake()
    compat = bridge_b.connect(handshake.protocol_version, handshake.capabilities)

    message = create_observation_share(
        "lantern_a",
        {"content": "water boils at 100C at sea level", "reliability": 0.9},
    )

    result = bridge_b.receive(message, compat)

    assert result.accepted is True
    assert result.action == "OBSERVATION_CREATED"
    assert len(agent_b.lantern.kernel.observations) == 1

    obs = next(iter(agent_b.lantern.kernel.observations.values()))
    assert obs.source == "lantern_a"  # provenance preserved
    assert obs.content == "water boils at 100C at sea level"


# ==================================================
# 4. Unsupported capability rejection
# ==================================================

def test_unsupported_capability_is_rejected():
    _, agent_b, bridge_b = make_instance()

    # Peer offered no capabilities during handshake.
    compat = bridge_b.connect("0.82", {})

    message = create_observation_share("lantern_a", {"content": "should be rejected"})
    result = bridge_b.receive(message, compat)

    assert result.accepted is False
    assert result.action == "REJECTED"
    assert len(agent_b.lantern.kernel.observations) == 0


# ==================================================
# 5. Incompatible major version rejection
# ==================================================

def test_incompatible_major_version_is_rejected():
    _, agent_b, bridge_b = make_instance()

    compat = bridge_b.connect("9.0.0", {"evidence_exchange": True})

    assert compat.compatible is False

    message = create_observation_share("lantern_a", {"content": "should be rejected"})
    result = bridge_b.receive(message, compat)

    assert result.accepted is False
    assert len(agent_b.lantern.kernel.observations) == 0


# ==================================================
# 6. Remote confidence does NOT mutate local belief
# ==================================================

def test_remote_confidence_does_not_mutate_local_belief():
    _, _, bridge_a = make_instance()
    _, agent_b, bridge_b = make_instance()

    handshake = bridge_a.boundary.handshake()
    compat = bridge_b.connect(handshake.protocol_version, handshake.capabilities)

    baseline = agent_b.ask_belief("gravity")

    # A claims very high reliability. The bridge path only ever
    # creates an Observation from this message -- it never calls
    # add_evidence() -- so belief on B cannot move as a side effect
    # of receiving it, no matter what A claims.
    message = create_observation_share(
        "lantern_a",
        {"content": "gravity pulls objects down", "reliability": 1.0},
    )
    bridge_b.receive(message, compat)

    assert agent_b.ask_belief("gravity") == baseline
    assert len(agent_b.lantern.kernel.evidence) == 0


# ==================================================
# 7. codex_update is rejected end to end
# ==================================================

def test_codex_update_is_rejected_end_to_end():
    _, _, bridge_a = make_instance()
    _, agent_b, bridge_b = make_instance()

    handshake = bridge_a.boundary.handshake()
    # Even if A claims it wants to send codex_update, B's own
    # DEFAULT_CAPABILITIES has codex_update=False, so it is never in
    # the shared set regardless of what A advertises.
    compat = bridge_b.connect(handshake.protocol_version, {"codex_update": True})

    assert "codex_update" not in compat.shared_capabilities

    message = create_codex_update("lantern_a", "gravity", 0.99, ["ev1"])
    result = bridge_b.receive(message, compat)

    assert result.accepted is False
    assert result.action == "REJECTED"
    assert "codex_update" in result.reason
    assert len(agent_b.lantern.kernel.evidence) == 0


# ==================================================
# 8. History remains auditable after exchange
# ==================================================

def test_history_remains_auditable_after_exchange(tmp_path):
    chronicle_path = tmp_path / "instance_b.jsonl"

    _, _, bridge_a = make_instance()

    lantern_b = Lantern(chronicle_filename=chronicle_path)
    agent_b = LanternAgent(lantern_b, chronicle=lantern_b.bus.chronicle)
    bridge_b = LanternAgentBridge(agent_b)

    handshake = bridge_a.boundary.handshake()
    compat = bridge_b.connect(handshake.protocol_version, handshake.capabilities)

    message = create_observation_share(
        "lantern_a", {"content": "auditable claim", "reliability": 0.8}
    )
    bridge_b.receive(message, compat)

    assert lantern_b.bus.chronicle.verify() is True

    records = list(lantern_b.bus.chronicle.replay())
    assert any(r["type"] == "OBSERVATION_CREATED" for r in records)
    assert any(r["payload"].get("source") == "lantern_a" for r in records)


# ==================================================
# 9. Persistence: protocol-received data survives restart
# ==================================================

def test_persistence_after_receiving_observation_via_protocol(tmp_path):
    chronicle_path = tmp_path / "instance_b_persist.jsonl"

    _, _, bridge_a = make_instance()

    lantern_b = Lantern(chronicle_filename=chronicle_path)
    agent_b = LanternAgent(lantern_b, chronicle=lantern_b.bus.chronicle)
    bridge_b = LanternAgentBridge(agent_b)

    handshake = bridge_a.boundary.handshake()
    compat = bridge_b.connect(handshake.protocol_version, handshake.capabilities)

    message = create_observation_share(
        "lantern_a", {"content": "persisted claim", "reliability": 0.7}
    )
    bridge_b.receive(message, compat)

    # Locally decided: B chooses to link the received observation to
    # a concept. This is a local act (add_evidence), not something A
    # triggered -- consistent with "only new Evidence changes belief."
    received_obs = next(iter(lantern_b.kernel.observations.values()))
    agent_b.add_evidence("persisted_concept", received_obs.id, 1, 1)

    expected_belief = lantern_b.kernel.belief("persisted_concept")
    expected_obs_count = len(lantern_b.kernel.observations)
    expected_evidence_count = len(lantern_b.kernel.evidence)

    lantern_b.save_snapshot()

    # Simulate process termination + restart: a brand-new Lantern
    # instance pointed at the same Chronicle file, with no in-memory
    # state carried over from lantern_b.
    restarted = Lantern(chronicle_filename=chronicle_path)
    restarted.startup()

    assert len(restarted.kernel.observations) == expected_obs_count
    assert len(restarted.kernel.evidence) == expected_evidence_count
    assert abs(restarted.kernel.belief("persisted_concept") - expected_belief) < 0.0001
    assert restarted.bus.chronicle.verify() is True
