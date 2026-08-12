from pathlib import Path
import shutil

from lantern_harness.bridge import LanternBridge
from lantern_harness.confidence_field import ConfidenceField
from lantern_harness.decision_state_machine import DecisionStateMachine
from lantern_harness.reality_boundary import RealityBoundary, EXECUTION_MODE_REAL, EXECUTION_MODE_SIMULATED
from lantern_harness.tools.boundary import ToolBoundary, ToolDescriptor


TMP = Path('/tmp/lantern_harness_reality_boundary_tests')


def _fresh_bridge(name='case'):
    path = TMP / name
    if path.exists():
        shutil.rmtree(path)
    bridge = LanternBridge(data_dir=path)
    bridge.ensure_identity()
    bridge.startup()
    return bridge


def _decision(bridge, concept='x'):
    reading = ConfidenceField(bridge).evaluate(concept=concept)
    return DecisionStateMachine().recommend(reading)


def test_propose_never_touches_external_world():
    bridge = _fresh_bridge('propose')
    decision = _decision(bridge)
    rb = RealityBoundary()
    proposal = rb.propose(intent='say hello', decision=decision, tool_name='echo', inputs={'msg': 'hi'})
    assert proposal.intent == 'say hello'
    assert proposal.tool_name == 'echo'
    assert proposal.decision_state == decision.state


def test_propose_requires_non_empty_intent():
    bridge = _fresh_bridge('empty-intent')
    decision = _decision(bridge)
    rb = RealityBoundary()
    try:
        rb.propose(intent='   ', decision=decision)
        raise AssertionError('expected ValueError')
    except ValueError:
        pass


def test_act_denied_when_tool_not_authorized():
    bridge = _fresh_bridge('denied')
    decision = _decision(bridge)
    tb = ToolBoundary()
    tb.register(ToolDescriptor(name='echo', description='echoes input', handler=lambda msg: msg))
    rb = RealityBoundary()
    proposal = rb.propose(intent='say hello', decision=decision, tool_name='echo')
    record = rb.act(proposal, tb, msg='hi')
    assert record.authorization_status == 'DENIED'
    assert record.execution_mode != EXECUTION_MODE_REAL
    assert record.is_real_success() is False


def test_act_real_success_only_after_explicit_authorization():
    bridge = _fresh_bridge('authorized')
    decision = _decision(bridge)
    tb = ToolBoundary()
    tb.register(ToolDescriptor(name='echo', description='echoes input', handler=lambda msg: msg))
    tb.authorize('echo')
    rb = RealityBoundary()
    proposal = rb.propose(intent='say hello', decision=decision, tool_name='echo')
    record = rb.act(proposal, tb, msg='hi')
    assert record.execution_mode == EXECUTION_MODE_REAL
    assert record.result_status == 'SUCCESS'
    assert record.is_real_success() is True
    assert record.result == 'hi'


def test_act_with_no_tool_name_is_not_executed():
    bridge = _fresh_bridge('no-tool')
    decision = _decision(bridge)
    tb = ToolBoundary()
    rb = RealityBoundary()
    proposal = rb.propose(intent='just thinking', decision=decision)
    record = rb.act(proposal, tb)
    assert record.execution_mode == 'NOT_EXECUTED'
    assert record.result_status == 'NOT_EXECUTED'
    assert record.is_real_success() is False


def test_simulate_can_never_report_success():
    bridge = _fresh_bridge('simulate')
    decision = _decision(bridge)
    rb = RealityBoundary()
    proposal = rb.propose(intent='pretend to deploy', decision=decision, tool_name='deploy')
    record = rb.simulate(proposal, {'would_deploy_to': 'prod'}, reason='deploy tool does not exist yet')
    assert record.execution_mode == EXECUTION_MODE_SIMULATED
    assert record.result_status == 'SIMULATED_ONLY'
    assert record.result_status != 'SUCCESS'
    assert record.is_real_success() is False
    assert any('SIMULATED_BY_ASSISTANT' in note for note in record.notes)


def test_simulate_requires_reason():
    bridge = _fresh_bridge('simulate-no-reason')
    decision = _decision(bridge)
    rb = RealityBoundary()
    proposal = rb.propose(intent='pretend', decision=decision, tool_name='x')
    try:
        rb.simulate(proposal, {}, reason='')
        raise AssertionError('expected ValueError')
    except ValueError:
        pass


def test_tool_error_is_never_reported_as_success():
    bridge = _fresh_bridge('error')
    decision = _decision(bridge)
    def boom(**kwargs):
        raise RuntimeError('network unreachable')
    tb = ToolBoundary()
    tb.register(ToolDescriptor(name='fetch', description='fetches something', handler=boom))
    tb.authorize('fetch')
    rb = RealityBoundary()
    proposal = rb.propose(intent='fetch data', decision=decision, tool_name='fetch')
    record = rb.act(proposal, tb)
    assert record.result_status == 'ERROR'
    assert record.is_real_success() is False
    assert 'network unreachable' in record.error
