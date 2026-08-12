from pathlib import Path
import shutil

from lantern_harness.bridge import LanternBridge
from lantern_harness.spine import BranchStore, SpineCommitter, branch_to_scar


TMP = Path('/tmp/lantern_harness_spine_tests')


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
    ev = bridge.add_evidence(concept, obs.id, weight=weight, sign=sign)
    return obs, ev


def test_open_branch_requires_concept_and_hypothesis():
    store = BranchStore()
    branch = store.open_branch(concept='x', hypothesis='x is true')
    assert branch.status == 'OPEN'
    assert branch.concept == 'x'
    try:
        store.open_branch(concept='', hypothesis='y')
        raise AssertionError('expected ValueError for empty concept')
    except ValueError:
        pass


def test_branch_cannot_commit_itself_without_explicit_authorization():
    bridge = _fresh_bridge('no-auth')
    store = BranchStore()
    branch = store.open_branch(concept='x', hypothesis='x is true')
    committer = SpineCommitter(bridge)
    result = committer.commit(branch, statement='x is true', authorized=False, authorized_by='nobody')
    assert result.status == 'REFUSED'
    assert 'cannot commit itself' in result.reason
    assert branch.status == 'OPEN'


def test_commit_succeeds_with_explicit_authorization_and_no_contradictions():
    bridge = _fresh_bridge('happy')
    obs, ev = _add_evidence(bridge, 'x', 'supports x', source='a')
    store = BranchStore()
    branch = store.open_branch(concept='x', hypothesis='x is true')
    store.link_observation(branch.id, obs.id)
    store.link_evidence(branch.id, ev.id)
    committer = SpineCommitter(bridge)
    result = committer.commit(branch, statement='x is true', authorized=True, authorized_by='operator')
    assert result.status == 'COMMITTED'
    assert branch.status == 'COMMITTED'
    assert result.entry is not None
    assert result.entry.concept == 'x'
    assert result.entry.chronicle_hash is not None


def test_commit_refused_on_open_contradiction_unless_acknowledged():
    bridge = _fresh_bridge('contradiction')
    _add_evidence(bridge, 'x', 'supports x', source='a', sign=1, weight=1.0)
    _add_evidence(bridge, 'x', 'refutes x', source='b', sign=-1, weight=1.0)
    contradictions = bridge.lantern.kernel.contradictions
    assert len(contradictions) >= 1, 'test setup requires a real detected contradiction'

    store = BranchStore()
    branch = store.open_branch(concept='x', hypothesis='x is true')
    committer = SpineCommitter(bridge)

    refused = committer.commit(branch, statement='x is true', authorized=True, authorized_by='operator')
    assert refused.status == 'REFUSED'
    assert 'unresolved contradiction' in refused.reason

    acked = committer.commit(
        branch, statement='x is true', authorized=True, authorized_by='operator',
        acknowledge_open_contradictions=True,
    )
    assert acked.status == 'COMMITTED'
    assert acked.entry.contradiction_acknowledgement is not None


def test_commit_refused_when_integrity_fails():
    bridge = _fresh_bridge('blocked')
    _add_evidence(bridge, 'x', 'supports x', source='a')
    with open(bridge.data_dir / 'chronicle.jsonl', 'a') as f:
        f.write('{"bad": true, this is not valid json}\n')
    store = BranchStore()
    branch = store.open_branch(concept='x', hypothesis='x is true')
    committer = SpineCommitter(bridge)
    result = committer.commit(branch, statement='x is true', authorized=True, authorized_by='operator')
    assert result.status == 'REFUSED'
    assert 'integrity' in result.reason.lower()
    assert branch.status == 'OPEN'


def test_committed_branch_cannot_be_recommitted_or_abandoned():
    bridge = _fresh_bridge('immutable')
    _add_evidence(bridge, 'x', 'supports x', source='a')
    store = BranchStore()
    branch = store.open_branch(concept='x', hypothesis='x is true')
    committer = SpineCommitter(bridge)
    first = committer.commit(branch, statement='x is true', authorized=True, authorized_by='operator')
    assert first.status == 'COMMITTED'

    second = committer.commit(branch, statement='x is true again', authorized=True, authorized_by='operator')
    assert second.status == 'REFUSED'

    try:
        store.abandon(branch.id)
        raise AssertionError('expected ValueError abandoning a COMMITTED branch')
    except ValueError:
        pass


def test_read_spine_reconstructs_from_real_chronicle_replay():
    bridge = _fresh_bridge('replay')
    _add_evidence(bridge, 'x', 'supports x', source='a')
    store = BranchStore()
    branch = store.open_branch(concept='x', hypothesis='x is true')
    committer = SpineCommitter(bridge)
    committer.commit(branch, statement='x is true', authorized=True, authorized_by='operator')

    fresh_bridge = LanternBridge(data_dir=TMP / 'replay')
    entries = SpineCommitter(fresh_bridge).read_spine()
    assert len(entries) == 1
    assert entries[0].concept == 'x'
    assert entries[0].statement == 'x is true'


def test_abandoned_branch_becomes_a_real_scar_not_discarded():
    bridge = _fresh_bridge('scar')
    obs, ev = _add_evidence(bridge, 'y', 'weak support', source='a')
    store = BranchStore()
    branch = store.open_branch(concept='y', hypothesis='y might be true')
    store.link_evidence(branch.id, ev.id)
    store.abandon(branch.id)
    assert branch.status == 'ABANDONED'

    record = branch_to_scar(bridge, branch, outcome='BRANCH_ABANDONED', lesson='insufficient evidence for y')
    assert record.persisted is True
    assert record.scar.lesson == 'insufficient evidence for y'


def test_child_branch_requires_known_parent():
    store = BranchStore()
    parent = store.open_branch(concept='x', hypothesis='x is true')
    child = store.open_branch(concept='x', hypothesis='x is true because of z', parent_branch_id=parent.id)
    assert child.parent_branch_id == parent.id
    try:
        store.open_branch(concept='x', hypothesis='orphan', parent_branch_id='not-a-real-id')
        raise AssertionError('expected ValueError for unknown parent_branch_id')
    except ValueError:
        pass


def test_confidence_score_alone_never_authorizes_commit():
    """Even a HIGH-confidence reading must not bypass the explicit
    authorized=True requirement -- SpineCommitter.commit() does not
    accept or consult a ConfidenceFieldReading at all, by design."""
    bridge = _fresh_bridge('confidence-not-authority')
    _add_evidence(bridge, 'x', 'supports x', source='a', reliability=1.0)
    _add_evidence(bridge, 'x', 'supports x too', source='b', reliability=1.0)
    from lantern_harness.confidence_field import ConfidenceField
    reading = ConfidenceField(bridge).evaluate(concept='x', validation_status='SUPPORTED')

    store = BranchStore()
    branch = store.open_branch(concept='x', hypothesis='x is true')
    committer = SpineCommitter(bridge)
    result = committer.commit(branch, statement='x is true', authorized=False, authorized_by='confidence-engine')
    assert result.status == 'REFUSED'
    assert reading.confidence_band in {'HIGH', 'MEDIUM', 'LOW', 'BLOCKED'}
