from pathlib import Path
import shutil

from lantern_harness.bridge import LanternBridge
from lantern_harness.confidence_field import ConfidenceField
from lantern_harness.decision_state_machine import DecisionStateMachine


TMP = Path('/tmp/lantern_harness_decision_tests')


def _fresh_bridge(name='case'):
    path = TMP / name
    if path.exists():
        shutil.rmtree(path)
    bridge = LanternBridge(data_dir=path)
    bridge.ensure_identity()
    bridge.startup()
    return bridge


def _add_evidence(bridge, concept, content, source='src', reliability=1.0, weight=1.0, sign=1):
    obs = bridge.observe(content, source=source, reliability=reliability)
    return bridge.add_evidence(concept, obs.id, weight=weight, sign=sign)


def test_high_maps_to_proceed():
    bridge = _fresh_bridge('high')
    _add_evidence(bridge, 'x', 'supports', source='a', reliability=1.0, weight=1.0, sign=1)
    _add_evidence(bridge, 'x', 'supports2', source='b', reliability=1.0, weight=1.0, sign=1)
    reading = ConfidenceField(bridge).evaluate(concept='x', validation_status='SUPPORTED')
    decision = DecisionStateMachine().recommend(reading)
    assert decision.state == 'HIGH'
    assert decision.recommended_action == 'INTEGRATE / PROCEED'


def test_medium_maps_to_preserve_gather():
    bridge = _fresh_bridge('medium')
    _add_evidence(bridge, 'x', 'supports', source='a', reliability=0.7, weight=0.8, sign=1)
    reading = ConfidenceField(bridge).evaluate(concept='x', assumptions=['a1'], validation_status='PARTIAL')
    decision = DecisionStateMachine().recommend(reading)
    assert decision.state in {'MEDIUM', 'LOW'}
    if decision.state == 'MEDIUM':
        assert decision.recommended_action == 'PRESERVE / GATHER'


def test_low_maps_to_branch_investigate():
    bridge = _fresh_bridge('low')
    reading = ConfidenceField(bridge).evaluate(concept='x')
    decision = DecisionStateMachine().recommend(reading)
    assert decision.state == 'LOW'
    assert decision.recommended_action == 'BRANCH / INVESTIGATE'


def test_blocked_maps_to_stop_repair():
    bridge = _fresh_bridge('blocked')
    _add_evidence(bridge, 'x', 'supports', source='a')
    with open(bridge.data_dir / 'chronicle.jsonl', 'a') as f:
        f.write('{"bad": true, this is not valid json}\n')
    reading = ConfidenceField(bridge).evaluate(concept='x')
    decision = DecisionStateMachine().recommend(reading)
    assert decision.state == 'BLOCKED'
    assert decision.recommended_action == 'STOP / REPAIR'


def test_illegal_transition_rejected():
    bridge = _fresh_bridge('illegal')
    reading = ConfidenceField(bridge).evaluate(concept='x')
    machine = DecisionStateMachine()
    try:
        machine.recommend(reading, previous_state='HIGH', transition_event='uncertainty rises')
    except ValueError as exc:
        assert 'illegal state transition' in str(exc)
    else:
        raise AssertionError('expected illegal transition to fail')


def test_blocked_to_high_allowed_only_after_explicit_recovery_event():
    bridge = _fresh_bridge('recover')
    _add_evidence(bridge, 'x', 'supports', source='a', reliability=1.0, weight=1.0, sign=1)
    reading = ConfidenceField(bridge).evaluate(concept='x', validation_status='SUPPORTED')
    machine = DecisionStateMachine()
    decision = machine.recommend(reading, previous_state='BLOCKED', transition_event='integrity restored and reverified')
    assert decision.transition_from == 'BLOCKED'
    assert decision.state in {'MEDIUM', 'HIGH'}


def test_authorization_boundary_explicitly_preserved():
    bridge = _fresh_bridge('auth')
    _add_evidence(bridge, 'x', 'supports', source='a', reliability=1.0, weight=1.0, sign=1)
    reading = ConfidenceField(bridge).evaluate(concept='x', validation_status='SUPPORTED')
    decision = DecisionStateMachine().recommend(reading)
    assert decision.authorization_required is True
    assert decision.authorization_status == 'NOT_EVALUATED'
    assert decision.explanation['decision_is_not_authorization'] is True


def test_decision_explanation_contains_pipeline():
    bridge = _fresh_bridge('explanation')
    reading = ConfidenceField(bridge).evaluate(concept='x')
    decision = DecisionStateMachine().recommend(reading)
    assert 'Capability Authorization' in decision.explanation['pipeline']


def test_prompt_compiler_compatibility_path():
    from lantern_harness.prompt_compiler import PromptCompiler
    bridge = _fresh_bridge('compiler')
    compiled = PromptCompiler(bridge=bridge).compile('Should we deploy x to production?', concept='x', assumptions=['a1'])
    reading = ConfidenceField(bridge).evaluate(concept=compiled.concept, assumptions=compiled.assumptions, validation_status=compiled.validation_status)
    decision = DecisionStateMachine().recommend(reading)
    assert decision.state in {'LOW', 'MEDIUM', 'HIGH'}


def test_blocked_never_silently_becomes_low():
    bridge = _fresh_bridge('blocked-vs-low')
    _add_evidence(bridge, 'x', 'supports', source='a')
    with open(bridge.data_dir / 'chronicle.jsonl', 'a') as f:
        f.write('{"bad": true, this is not valid json}\n')
    blocked = ConfidenceField(bridge).evaluate(concept='x')
    assert blocked.confidence_band == 'BLOCKED'
    decision = DecisionStateMachine().recommend(blocked)
    assert decision.state == 'BLOCKED'
