"""Decision gate tests: prove that unauthorized or low-confidence actions
CANNOT physically trigger tool execution, and that only the centralized
gate can reach a tool implementation.

Scenarios (per the integration directive):
  1) Denied decision blocks execution
  2) Low-confidence decision blocks execution
  3) Allowed + high-confidence executes, result flows back
  4) Scope violation blocks execution
  5) Regression tests against bypass paths (loop-level + source-level)
Plus contract and adapter-normalization coverage.
"""

from pathlib import Path
import shutil

import pytest

from lantern_harness.bridge import LanternBridge
from lantern_harness.decision_gate import (
    DEFAULT_REQUIRED_CONFIDENCE, authorize_tool_call, execute_tool_call, load_tool_policy,
)
from lantern_harness.operating_loop import OperatingLoop
from lantern_harness.reasoning.tool_calls import ToolCallParseError, parse_tool_calls
from lantern_harness.tool_contract import (
    Decision, Message, ToolCall, ToolCallResult, ToolSpec, blocked_message,
)
from lantern_harness.tools.boundary import ToolBoundary, ToolDescriptor


TMP = Path('/tmp/lantern_harness_decision_gate_tests')
REQUIRED = 0.8


class DangerousTool:
    """Fake consequential tool whose side effect (an append to calls)
    must NEVER happen unless the gate allows it."""

    def __init__(self):
        self.calls = []

    def __call__(self, **kwargs):
        self.calls.append(kwargs)
        return "wrote!"


def _boundary_with(dangerous, *, name='dangerous_write', scopes=('filesystem.write',)):
    tb = ToolBoundary()
    tb.register(ToolDescriptor(name=name, description='writes a file', handler=dangerous, scopes=scopes))
    tb.authorize(name)
    return tb


def _fresh_bridge(name):
    path = TMP / name
    if path.exists():
        shutil.rmtree(path)
    bridge = LanternBridge(data_dir=path)
    bridge.ensure_identity()
    bridge.startup()
    return bridge


# ---------------------------------------------------------------- scenario 1
def test_denied_decision_blocks_execution():
    dangerous = DangerousTool()
    tb = _boundary_with(dangerous)
    call = ToolCall(id='c1', tool_name='dangerous_write', arguments={'path': '/tmp/x'})
    decision = Decision(state='Denied', confidence=1.0, reason='operator policy forbids writes')
    tcr, tool_result = execute_tool_call(call, decision, REQUIRED, tb)
    assert dangerous.calls == []                      # implementation NEVER called
    assert tcr.executed is False
    assert tool_result.status == 'BLOCKED'
    assert 'blocked' in tcr.blocked_reason.lower()


# ---------------------------------------------------------------- scenario 2
def test_low_confidence_decision_blocks_execution():
    dangerous = DangerousTool()
    tb = _boundary_with(dangerous)
    call = ToolCall(id='c2', tool_name='dangerous_write', arguments={'path': '/tmp/x'})
    decision = Decision(state='Allowed', confidence=0.5, reason='scopes ok')
    tcr, tool_result = execute_tool_call(call, decision, REQUIRED, tb)
    assert dangerous.calls == []                      # NEVER called
    assert tcr.executed is False
    assert tool_result.status == 'BLOCKED'
    assert 'required: 0.80' in tcr.blocked_reason      # clarification surfaced


# ---------------------------------------------------------------- scenario 3
def test_allowed_high_confidence_executes_and_result_flows_back():
    dangerous = DangerousTool()
    tb = _boundary_with(dangerous)
    call = ToolCall(id='c3', tool_name='dangerous_write', arguments={'path': '/tmp/x'})
    decision = Decision(state='Allowed', confidence=0.9, reason='scopes ok')
    tcr, tool_result = execute_tool_call(call, decision, REQUIRED, tb)
    assert dangerous.calls == [{'path': '/tmp/x'}]    # called exactly once
    assert tcr.executed is True
    assert tcr.result == 'wrote!'
    assert tool_result.status == 'EXECUTED'


# ---------------------------------------------------------------- scenario 4
def test_scope_violation_blocks_execution_at_the_authorization_layer():
    dangerous = DangerousTool()
    tb = _boundary_with(dangerous)
    call = ToolCall(id='c4', tool_name='dangerous_write', arguments={'path': '/tmp/x'})
    decision = authorize_tool_call(call, {'filesystem.read'}, tool_boundary=tb)
    assert decision.state == 'Denied'
    assert decision.confidence == 0.0
    tcr, tool_result = execute_tool_call(call, decision, REQUIRED, tb)
    assert dangerous.calls == []
    assert tool_result.status == 'BLOCKED'


def test_scope_violation_blocks_execution_through_the_loop():
    dangerous = DangerousTool()
    tb = _boundary_with(dangerous)
    bridge = _fresh_bridge('scope-violation')
    loop = OperatingLoop(bridge, tb, allowed_scopes={'filesystem.read'})
    result = loop.run('write the file', concept='scope_violation_case',
                      tool_name='dangerous_write', tool_kwargs={'path': '/tmp/x'})
    assert dangerous.calls == []                      # never executed
    assert result.action_record.is_real_success() is False
    assert result.action_record.result_status == 'NOT_EXECUTED'
    assert any('BLOCKED' in n for n in result.notes)


# ---------------------------------------------------------------- scenario 5
def test_loop_blocks_low_confidence_authorized_tool():
    """Regression for the observed defect: LOW decision + authorized tool
    used to execute a REAL action. The gate must now block it."""
    dangerous = DangerousTool()
    tb = _boundary_with(dangerous)
    bridge = _fresh_bridge('low-conf-block')
    loop = OperatingLoop(bridge, tb, allowed_scopes={'filesystem.write'})
    result = loop.run('write the file', concept='fresh_low_confidence_case',
                      tool_name='dangerous_write', tool_kwargs={'path': '/tmp/x'})
    assert dangerous.calls == []                      # physically never executed
    assert result.action_record.is_real_success() is False
    assert loop.decision_log[-1]['decision']['state'] == 'Allowed'  # scope allowed...
    assert result.confidence.confidence_score < loop.required_confidence  # ...but confidence gated it


def test_loop_executes_only_above_required_confidence():
    """Positive loop-level control: with evidence-backed high confidence
    and matching scopes, execution happens -- exactly once."""
    dangerous = DangerousTool()
    tb = _boundary_with(dangerous)
    bridge = _fresh_bridge('high-conf-exec')
    loop = OperatingLoop(bridge, tb, allowed_scopes={'filesystem.write'})
    concept = 'high_confidence_execution_case'
    # Build evidence-backed confidence the honest way: independent
    # verified observations supporting the concept.
    for i in range(12):
        # Independent sources: the evidence kernel deduplicates same-source
        # replays (Gate 2 hardening), so independence is the honest way up.
        obs = bridge.observe(f'verified reading {i}: the file write is safe and intended',
                             source=f'independent-verifier-{i}', reliability=1.0)
        bridge.add_evidence(concept, obs.id, weight=1.0, sign=1)
    # Cross the gate the honest way: independent evidence AND
    # caller-supplied independent verification (UNVERIFIED runs cap at
    # 0.75, below the default 0.8 threshold -- by design).
    verified = loop.run('probe', concept=concept, validation_status='VERIFIED')
    score = verified.confidence.confidence_score
    assert isinstance(score, (int, float)) and score >= loop.required_confidence, \
        f'evidence + verification could not cross the gate (got {score})'
    result = loop.run('write the file', concept=concept, validation_status='VERIFIED',
                      tool_name='dangerous_write', tool_kwargs={'path': '/tmp/x'})
    assert len(dangerous.calls) == 1                  # called exactly once
    assert result.action_record.is_real_success() is True
    assert result.action_record.result == 'wrote!'


def test_no_production_execution_path_bypasses_the_gate():
    """Source-level regression: OperatingLoop must not call
    RealityBoundary.act() or ToolBoundary.execute() directly; all
    production tool execution goes through decision_gate.execute_tool_call."""
    loop_src = Path('lantern_harness/operating_loop.py').read_text()
    assert '.act(' not in loop_src, 'OperatingLoop must not use the deprecated direct-execution path'
    assert 'execute_tool_call(' in loop_src
    rb_src = Path('lantern_harness/reality_boundary.py').read_text()
    assert 'DEPRECATED' in rb_src.split('def act(')[1][:600]


def test_unregistered_tool_is_denied_and_never_executed():
    dangerous = DangerousTool()
    tb = _boundary_with(dangerous, name='other_tool')
    call = ToolCall(id='c5', tool_name='dangerous_write', arguments={})
    decision = authorize_tool_call(call, {'filesystem.write'}, tool_boundary=tb)
    assert decision.state == 'Denied'
    tcr, tool_result = execute_tool_call(call, decision, REQUIRED, tb)
    assert dangerous.calls == []
    assert tool_result.status == 'BLOCKED'


def test_decision_log_records_every_decision():
    dangerous = DangerousTool()
    tb = _boundary_with(dangerous)
    log = []
    call = ToolCall(id='c6', tool_name='dangerous_write', arguments={})
    execute_tool_call(call, Decision(state='Denied', confidence=1.0, reason='test'), REQUIRED, tb, decision_log=log)
    execute_tool_call(call, Decision(state='Allowed', confidence=0.9, reason='test'), REQUIRED, tb, decision_log=log)
    assert len(log) == 2
    assert log[0]['decision']['state'] == 'Denied'
    assert log[1]['decision']['state'] == 'Allowed'


# ---------------------------------------------------------------- contract
def test_decision_rejects_unknown_state_and_out_of_range_confidence():
    with pytest.raises(ValueError):
        Decision(state='Escalate', confidence=1.0, reason='future state')  # not yet a valid state
    with pytest.raises(ValueError):
        Decision(state='Allowed', confidence=1.5, reason='out of range')


def test_tool_call_rejects_bad_shapes():
    with pytest.raises(ValueError):
        ToolCall(id='', tool_name='x', arguments={})
    with pytest.raises(ValueError):
        ToolCall(id='x', tool_name='', arguments={})
    with pytest.raises(ValueError):
        ToolCall(id='x', tool_name='t', arguments=['not', 'a', 'dict'])


def test_message_contract():
    with pytest.raises(ValueError):
        Message(role='wizard', content='x')
    with pytest.raises(ValueError):
        Message(role='tool', content='x')  # missing tool_call_id


def test_policy_loading_defaults_and_overrides():
    assert load_tool_policy({})['required_confidence'] == DEFAULT_REQUIRED_CONFIDENCE
    policy = load_tool_policy({'tool_policy': {'required_confidence': 0.9, 'allowed_scopes': ['filesystem.read']}})
    assert policy['required_confidence'] == 0.9
    assert policy['allowed_scopes'] == ('filesystem.read',)


# ---------------------------------------------------------------- adapter
def test_parse_tool_calls_openai_shape():
    raw = {'choices': [{'message': {'tool_calls': [
        {'id': 'call_1', 'function': {'name': 'dangerous_write', 'arguments': '{"path": "/tmp/x"}'}}]}}]}
    calls = parse_tool_calls(raw)
    assert len(calls) == 1
    assert calls[0].tool_name == 'dangerous_write'
    assert calls[0].arguments == {'path': '/tmp/x'}
    assert calls[0].id == 'call_1'


def test_parse_tool_calls_anthropic_shape():
    raw = {'content': [{'type': 'text', 'text': 'hi'},
                       {'type': 'tool_use', 'id': 'tu_1', 'name': 'dangerous_write', 'input': {'path': '/tmp/x'}}]}
    calls = parse_tool_calls(raw)
    assert len(calls) == 1
    assert calls[0].tool_name == 'dangerous_write'


def test_parse_tool_calls_rejects_nonconforming():
    with pytest.raises(ToolCallParseError):
        parse_tool_calls({'tool_calls': 'not-a-list'})
    with pytest.raises(ToolCallParseError):
        parse_tool_calls({'choices': [{'message': {'tool_calls': [
            {'id': 'x', 'function': {'name': 't', 'arguments': 'not json'}}]}}]})


def test_parse_tool_calls_empty_payloads_return_no_calls():
    assert parse_tool_calls(None) == []
    assert parse_tool_calls({'choices': [{'message': {'content': 'just text'}}]}) == []


def test_blocked_message_hides_internals():
    call = ToolCall(id='c', tool_name='dangerous_write', arguments={})
    decision = Decision(state='Denied', confidence=0.0, reason='session lacks required scope')
    msg = blocked_message(call, decision, 0.8)
    assert 'filesystem' not in msg   # no scope internals leaked
    assert 'dangerous_write' in msg
