from pathlib import Path
import shutil

from lantern_harness.bridge import LanternBridge
from lantern_harness.self_model import SelfModel
from lantern_harness.tools.boundary import ToolBoundary, ToolDescriptor


TMP = Path('/tmp/lantern_harness_self_model_tests')


def _fresh_bridge(name='case'):
    path = TMP / name
    if path.exists():
        shutil.rmtree(path)
    bridge = LanternBridge(data_dir=path)
    bridge.ensure_identity()
    bridge.startup()
    return bridge


def test_describe_returns_all_seven_sections():
    bridge = _fresh_bridge('sections')
    tb = ToolBoundary()
    reading = SelfModel(bridge, tb).describe()
    d = reading.to_dict()
    for key in (
        'what_i_know', 'what_i_infer', 'what_i_do_not_know', 'what_i_can_do',
        'what_i_cannot_do', 'what_i_am_authorized_to_do', 'what_requires_operator_action',
    ):
        assert key in d
        assert isinstance(d[key], list)


def test_authorized_tools_reflect_real_tool_boundary_state():
    bridge = _fresh_bridge('auth-reflects')
    tb = ToolBoundary()
    tb.register(ToolDescriptor(name='echo', description='echo', handler=lambda **k: k))
    reading_before = SelfModel(bridge, tb).describe()
    assert reading_before.what_i_am_authorized_to_do == ('(no tools are currently authorized in ToolBoundary)',)

    tb.authorize('echo')
    reading_after = SelfModel(bridge, tb).describe()
    assert 'tool: echo' in reading_after.what_i_am_authorized_to_do


def test_self_model_is_read_only():
    """Calling describe() repeatedly must not change bridge or
    tool_boundary state."""
    bridge = _fresh_bridge('read-only')
    tb = ToolBoundary()
    tb.register(ToolDescriptor(name='echo', description='echo', handler=lambda **k: k))
    before_status = bridge.status()
    before_authorized = set(tb._authorized)
    SelfModel(bridge, tb).describe()
    SelfModel(bridge, tb).describe()
    after_status = bridge.status()
    after_authorized = set(tb._authorized)
    assert before_status == after_status
    assert before_authorized == after_authorized


def test_self_model_cannot_self_authorize():
    """SelfModel must have no method capable of authorizing a tool --
    this proves the class surface, not just behavior of describe()."""
    bridge = _fresh_bridge('no-self-auth')
    tb = ToolBoundary()
    model = SelfModel(bridge, tb)
    forbidden = {'authorize', 'grant', 'approve', 'enable', 'unlock'}
    public_methods = {name for name in dir(model) if not name.startswith('_')}
    assert not (public_methods & forbidden), f"SelfModel exposes authority-granting method(s): {public_methods & forbidden}"


def test_operator_boundaries_always_listed():
    bridge = _fresh_bridge('boundaries')
    tb = ToolBoundary()
    reading = SelfModel(bridge, tb).describe()
    joined = ' '.join(reading.what_requires_operator_action)
    assert 'push' in joined
    assert 'PyPI' in joined or 'package' in joined
    assert 'payment' in joined or 'wallet' in joined


def test_format_produces_readable_text_with_all_headers():
    bridge = _fresh_bridge('format')
    tb = ToolBoundary()
    reading = SelfModel(bridge, tb).describe()
    text = reading.format()
    for header in (
        'WHAT I KNOW', 'WHAT I INFER', 'WHAT I DO NOT KNOW', 'WHAT I CAN DO',
        'WHAT I CANNOT DO', 'WHAT I AM AUTHORIZED TO DO', 'WHAT REQUIRES OPERATOR ACTION',
    ):
        assert header in text
