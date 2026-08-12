from pathlib import Path
import shutil

from lantern_harness.bridge import LanternBridge
from lantern_harness.confidence_field import ConfidenceField, HIGH_THRESHOLD, MEDIUM_THRESHOLD
from lantern_harness.perspective_differential import Perspective


TMP = Path('/tmp/lantern_harness_confidence_tests')


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


def test_high_state_with_strong_independent_support():
    bridge = _fresh_bridge('high')
    _add_evidence(bridge, 'x', 'supports x', source='a', reliability=1.0, weight=1.0, sign=1)
    _add_evidence(bridge, 'x', 'also supports x', source='b', reliability=0.95, weight=1.0, sign=1)
    field = ConfidenceField(bridge)
    reading = field.evaluate(concept='x', validation_status='SUPPORTED')
    assert reading.confidence_band == 'HIGH'
    assert reading.confidence_score >= HIGH_THRESHOLD


def test_medium_state_boundary_exact_threshold():
    bridge = _fresh_bridge('medium')
    _add_evidence(bridge, 'x', 'moderate support', source='a', reliability=0.8, weight=0.9, sign=1)
    field = ConfidenceField(bridge)
    reading = field.evaluate(concept='x', assumptions=['a1'], validation_status='PARTIAL')
    assert reading.confidence_band in {'MEDIUM', 'LOW'}


def test_low_state_with_empty_evidence():
    bridge = _fresh_bridge('low-empty')
    field = ConfidenceField(bridge)
    reading = field.evaluate(concept='x')
    assert reading.confidence_band == 'LOW'
    assert reading.confidence_score < MEDIUM_THRESHOLD
    assert 'supporting evidence for the concept' in reading.missing_information


def test_blocked_state_on_integrity_failure():
    bridge = _fresh_bridge('blocked')
    _add_evidence(bridge, 'x', 'strong but untrustworthy after tamper', source='a', reliability=1.0, weight=2.0, sign=1)
    with open(bridge.data_dir / 'chronicle.jsonl', 'a') as f:
        f.write('{"bad": true, this is not valid json}\n')
    field = ConfidenceField(bridge)
    reading = field.evaluate(concept='x')
    assert reading.confidence_band == 'BLOCKED'
    assert reading.confidence_score == 'BLOCKED'


def test_blocked_is_more_severe_than_low():
    bridge_ok = _fresh_bridge('ok')
    low = ConfidenceField(bridge_ok).evaluate(concept='missing')
    bridge_bad = _fresh_bridge('bad')
    _add_evidence(bridge_bad, 'x', 'anything', source='a')
    with open(bridge_bad.data_dir / 'chronicle.jsonl', 'a') as f:
        f.write('{"bad": true, this is not valid json}\n')
    blocked = ConfidenceField(bridge_bad).evaluate(concept='x')
    assert low.confidence_band == 'LOW'
    assert blocked.confidence_band == 'BLOCKED'
    assert blocked.interpretation != low.interpretation


def test_contradictory_evidence_increases_pressure_and_lowers_confidence():
    bridge = _fresh_bridge('contradiction')
    _add_evidence(bridge, 'x', 'supports x', source='a', reliability=1.0, weight=1.0, sign=1)
    _add_evidence(bridge, 'x', 'denies x', source='b', reliability=1.0, weight=1.0, sign=-1)
    reading = ConfidenceField(bridge).evaluate(concept='x', validation_status='CONTESTED')
    assert reading.contradiction_pressure > 0
    assert reading.confidence_band in {'LOW', 'MEDIUM'}


def test_assumption_pressure_raises_investigation_need():
    bridge = _fresh_bridge('assumptions')
    _add_evidence(bridge, 'x', 'supports x', source='a', reliability=0.9, weight=1.0, sign=1)
    reading = ConfidenceField(bridge).evaluate(concept='x', assumptions=['a', 'b', 'c', 'd'])
    assert reading.assumption_pressure > 0.5
    assert any('replace assumptions' in item for item in reading.what_would_change_state)


def test_perspective_divergence_is_signal_not_falsehood():
    bridge = _fresh_bridge('divergence')
    _add_evidence(bridge, 'x', 'supports x', source='a', reliability=1.0, weight=1.0, sign=1)
    _add_evidence(bridge, 'x', 'also supports x', source='b', reliability=1.0, weight=1.0, sign=1)
    perspectives = [
        Perspective(source='p1', conclusion='yes', confidence=0.9, evidence_score=0.9, assumption_bias=0.1),
        Perspective(source='p2', conclusion='no', confidence=0.3, evidence_score=0.8, assumption_bias=0.2),
        Perspective(source='p3', conclusion='maybe', confidence=0.6, evidence_score=0.85, assumption_bias=0.1),
    ]
    reading = ConfidenceField(bridge).evaluate(concept='x', perspectives=perspectives, validation_status='SUPPORTED')
    assert reading.evidence_strength > 0.5
    assert reading.perspective_divergence != 'UNKNOWN'
    assert any('divergence' in reason for reason in reading.reasons)


def test_repeated_observations_do_not_count_as_independent_sources():
    bridge = _fresh_bridge('repeated')
    _add_evidence(bridge, 'x', 'support 1', source='same', reliability=0.9, weight=1.0, sign=1)
    _add_evidence(bridge, 'x', 'support 2', source='same', reliability=0.9, weight=1.0, sign=1)
    reading = ConfidenceField(bridge).evaluate(concept='x', validation_status='PARTIAL')
    assert reading.inputs['independent_sources'] == ['same']
    assert 'more independent observation sources' in reading.missing_information


def test_integrity_recovery_reenables_non_blocked_reading():
    bridge_bad = _fresh_bridge('recover-bad')
    _add_evidence(bridge_bad, 'x', 'support x', source='a')
    with open(bridge_bad.data_dir / 'chronicle.jsonl', 'a') as f:
        f.write('{"bad": true, this is not valid json}\n')
    blocked = ConfidenceField(bridge_bad).evaluate(concept='x')
    assert blocked.confidence_band == 'BLOCKED'

    bridge_good = _fresh_bridge('recover-good')
    _add_evidence(bridge_good, 'x', 'support x', source='a')
    recovered = ConfidenceField(bridge_good).evaluate(concept='x', validation_status='PARTIAL')
    assert recovered.confidence_band != 'BLOCKED'


def test_scars_add_caution_but_not_permanent_punishment():
    bridge = _fresh_bridge('scar')
    _add_evidence(bridge, 'x', 'support x', source='a', reliability=0.9, weight=1.0, sign=1)
    scar = bridge.create_scar(
        source='test',
        trigger='failure',
        observation='something went wrong',
        outcome='INTEGRATION_ROLLBACK',
        severity='medium',
        lesson='validate before rollout',
    )
    reading = ConfidenceField(bridge).evaluate(concept='x', scars=[scar], validation_status='PARTIAL')
    assert any('scar lesson' in reason for reason in reading.reasons)
    assert reading.confidence_band in {'MEDIUM', 'LOW'}


def test_compass_reading_is_included_read_only():
    bridge = _fresh_bridge('compass')
    _add_evidence(bridge, 'x', 'support x', source='a', reliability=1.0, weight=1.0, sign=1)
    reading = ConfidenceField(bridge).evaluate(concept='x')
    assert reading.compass_reading is not None
    assert 'what_matters' in reading.compass_reading


def test_malformed_concept_rejected():
    bridge = _fresh_bridge('malformed')
    field = ConfidenceField(bridge)
    try:
        field.evaluate(concept=123)
    except ValueError as exc:
        assert 'concept' in str(exc)
    else:
        raise AssertionError('expected ValueError for malformed concept')
