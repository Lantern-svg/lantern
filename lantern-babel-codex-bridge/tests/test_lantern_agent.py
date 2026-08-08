"""
Test: lantern.agent wiring Chronicle + startup

Verifies:
- LanternAgent wraps lantern.core correctly
- startup() delegates to Lantern.startup() (snapshot-first recovery)
- kernel state DOES reconstruct now, via self-sufficient event payloads
"""

from lantern.core import Lantern, Chronicle
from lantern.agent import LanternAgent


def test_agent_wraps_core(tmp_path):
    chronicle_path = tmp_path / "test.jsonl"
    chronicle = Chronicle(chronicle_path)
    lantern = Lantern()
    agent = LanternAgent(lantern, chronicle)

    obs = agent.observe("Water freezes", "experiment", 1.0)
    agent.add_evidence("water", obs.id, 1, 1)

    status = agent.status()
    assert status["step"] == 1
    assert status["observations"] == 1
    assert status["evidence"] == 1
    assert status["chronicle"] is True


def test_agent_startup_reconstructs_bus_state(tmp_path):
    chronicle_path = tmp_path / "test.jsonl"
    chronicle = Chronicle(chronicle_path)

    writer_lantern = Lantern()
    writer_lantern.bus.chronicle = chronicle
    writer = LanternAgent(writer_lantern, chronicle)

    obs = writer.observe("Water freezes", "experiment", 1.0)
    writer.add_evidence("water", obs.id, 1, 1)

    written_chain = writer.lantern.bus.chain
    written_history_count = len(writer.lantern.bus.history)

    reader_lantern = Lantern()
    reader_lantern.bus.chronicle = chronicle
    reader = LanternAgent(reader_lantern, chronicle)

    startup_result = reader.startup()

    assert startup_result["status"] == "READY"
    assert startup_result["events_replayed"] == written_history_count
    assert reader.lantern.bus.chain == written_chain


def test_agent_startup_reconstructs_kernel_via_delegated_lantern_startup(tmp_path):
    """LanternAgent.startup() delegates to Lantern.startup(), which now
    does snapshot-first fast recovery and rebuilds kernel state from
    self-sufficient event payloads (not just bus/module/audit history).
    """
    chronicle_path = tmp_path / "test.jsonl"
    chronicle = Chronicle(chronicle_path)

    writer_lantern = Lantern()
    writer_lantern.bus.chronicle = chronicle
    writer = LanternAgent(writer_lantern, chronicle)

    obs = writer.observe("Water freezes", "experiment", 1.0)
    writer.add_evidence("water", obs.id, 1, 1)

    expected_belief = writer.ask_belief("water")

    reader_lantern = Lantern()
    reader_lantern.bus.chronicle = chronicle
    reader = LanternAgent(reader_lantern, chronicle)

    reader.startup()

    assert expected_belief > 0.5
    assert reader.lantern.kernel.step == writer.lantern.kernel.step
    assert len(reader.lantern.kernel.observations) == 1
    assert len(reader.lantern.kernel.evidence) == 1
    assert reader.ask_belief("water") == expected_belief


def test_agent_without_chronicle():
    lantern = Lantern()
    agent = LanternAgent(lantern, chronicle=None)

    startup_result = agent.startup()

    assert startup_result["status"] == "NO_CHRONICLE"
    assert agent.status()["chronicle"] is False
