from pathlib import Path
import shutil

from lantern_harness.bridge import LanternBridge
from lantern_harness.operating_loop import OperatingLoop
from lantern_harness.perspective_differential import Perspective
from lantern_harness.tools.boundary import ToolBoundary, ToolDescriptor


TMP = Path('/tmp/lantern_harness_operating_loop_tests')


def _fresh_bridge(name='case'):
    path = TMP / name
    if path.exists():
        shutil.rmtree(path)
    bridge = LanternBridge(data_dir=path)
    bridge.ensure_identity()
    bridge.startup()
    return bridge


def test_run_records_a_real_observation():
    bridge = _fresh_bridge('observe')
    tb = ToolBoundary()
    loop = OperatingLoop(bridge, tb)
    before = bridge.status()['observations']
    result = loop.run('is the sky blue today?', concept='sky_color')
    after = bridge.status()['observations']
    assert after == before + 1
    assert result.observation_id is not None


def test_run_without_tool_name_does_not_attempt_action():
    bridge = _fresh_bridge('no-tool')
    tb = ToolBoundary()
    loop = OperatingLoop(bridge, tb)
    result = loop.run('just thinking out loud', concept='x')
    assert result.action_record is None


def test_run_with_unauthorized_tool_never_reports_real_success():
    bridge = _fresh_bridge('unauth-tool')
    tb = ToolBoundary()
    tb.register(ToolDescriptor(name='deploy', description='deploys something', handler=lambda **k: 'deployed'))
    loop = OperatingLoop(bridge, tb)
    result = loop.run('deploy to production', concept='deploy_x', tool_name='deploy')
    assert result.action_record is not None
    assert result.action_record.is_real_success() is False
    assert result.action_record.authorization_status == 'DENIED'


def test_run_with_authorized_tool_produces_real_result():
    bridge = _fresh_bridge('auth-tool')
    tb = ToolBoundary()
    tb.register(ToolDescriptor(name='echo', description='echo', handler=lambda msg: msg))
    tb.authorize('echo')
    loop = OperatingLoop(bridge, tb)
    result = loop.run('say hi', concept='greeting', tool_name='echo', tool_kwargs={'msg': 'hi'})
    assert result.action_record.is_real_success() is True
    assert result.action_record.result == 'hi'


def test_run_produces_confidence_and_decision_for_every_call():
    bridge = _fresh_bridge('always-decision')
    tb = ToolBoundary()
    loop = OperatingLoop(bridge, tb)
    result = loop.run('what do we know about x?', concept='x')
    assert result.confidence.confidence_band in {'HIGH', 'MEDIUM', 'LOW', 'BLOCKED'}
    assert result.decision.state == result.confidence.confidence_band


def test_open_branch_creates_a_real_branch_linked_to_the_observation():
    bridge = _fresh_bridge('branch')
    tb = ToolBoundary()
    loop = OperatingLoop(bridge, tb)
    result = loop.run('investigate whether x holds', concept='x', open_branch=True)
    assert result.branch is not None
    assert result.branch.status == 'OPEN'
    assert result.observation_id in result.branch.observation_ids


def test_open_branch_without_concept_is_skipped_not_fabricated():
    bridge = _fresh_bridge('branch-no-concept')
    tb = ToolBoundary()
    loop = OperatingLoop(bridge, tb)
    result = loop.run('some vague thought', open_branch=True)
    assert result.branch is None
    assert any('no concept supplied' in note for note in result.notes)


def test_run_uses_perspective_differential_when_multiple_perspectives_given():
    bridge = _fresh_bridge('perspectives')
    tb = ToolBoundary()
    loop = OperatingLoop(bridge, tb)
    perspectives = [
        Perspective(source='model_a', conclusion='x is true', confidence=0.9, evidence_score=0.8, assumption_bias=0.1),
        Perspective(source='model_b', conclusion='x is false', confidence=0.6, evidence_score=0.3, assumption_bias=0.5),
    ]
    result = loop.run('is x true?', concept='x', perspectives=perspectives)
    assert result.confidence.perspective_divergence != 0.0
    assert result.confidence.inputs['differential'] is not None


def test_integrity_failure_propagates_to_blocked_decision_end_to_end():
    bridge = _fresh_bridge('blocked-e2e')
    bridge.observe('setup', source='a')
    with open(bridge.data_dir / 'chronicle.jsonl', 'a') as f:
        f.write('{"bad": true, this is not valid json}\n')
    tb = ToolBoundary()
    loop = OperatingLoop(bridge, tb)
    result = loop.run('should we trust this?', concept='x')
    assert result.confidence.confidence_band == 'BLOCKED'
    assert result.decision.state == 'BLOCKED'
    assert result.decision.recommended_action == 'STOP / REPAIR'


def test_empty_intent_rejected():
    bridge = _fresh_bridge('empty-intent')
    tb = ToolBoundary()
    loop = OperatingLoop(bridge, tb)
    try:
        loop.run('   ')
        raise AssertionError('expected ValueError')
    except ValueError:
        pass


def test_format_produces_readable_summary():
    bridge = _fresh_bridge('format')
    tb = ToolBoundary()
    loop = OperatingLoop(bridge, tb)
    result = loop.run('what is x?', concept='x')
    text = result.format()
    assert 'OPERATING LOOP RESULT' in text
    assert 'confidence:' in text
    assert 'decision:' in text
