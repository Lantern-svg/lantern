"""Model-driven tool pipeline tests: the diagram path
provider -> normalize -> registry -> decision -> authorization ->
execute_tool_call -> REAL TOOL.

The provider seam is exercised with a deterministic FakeEngine (same
pattern as the repo's own test FakeEngine -- no network, no keys).
EVERY stage after the provider is real harness code.
"""

import pytest

from lantern_harness.model_tool_pipeline import (
    ModelToolTurn, run_model_tool_turn, visible_tool_specs,
)
from lantern_harness.reasoning.base import ReasoningResponse
from lantern_harness.tool_contract import Message, ToolSpec
from lantern_harness.tools.boundary import ToolBoundary, ToolDescriptor
from lantern_harness.reasoning.tool_calls import ToolCallParseError


class DangerousTool:
    def __init__(self):
        self.calls = []

    def __call__(self, **kwargs):
        self.calls.append(kwargs)
        return "wrote!"


class FakeEngine:
    """Deterministic provider stand-in. raw carries an OpenAI-shaped
    tool_calls payload, exactly as a real provider adapter would return
    it through ReasoningResponse.raw."""

    provider_name = "fake"

    def __init__(self, raw):
        self.raw = raw
        self.saw_tools = None

    def respond(self, messages, tools=None):
        self.saw_tools = tools
        return ReasoningResponse(text="proposing a tool", provider="fake", model="fake-1", raw=self.raw)

    def describe(self):
        return {"provider": "fake"}


def _openai_call(name, args):
    import json
    return {'choices': [{'message': {'tool_calls': [
        {'id': f'call_{name}', 'function': {'name': name, 'arguments': json.dumps(args)}}]}}]}


def _boundary(dangerous):
    tb = ToolBoundary()
    tb.register(ToolDescriptor(name='dangerous_write', description='writes a file',
                              handler=dangerous, scopes=('filesystem.write',)))
    tb.register(ToolDescriptor(name='hidden_read', description='reads secrets',
                              handler=lambda **k: 'secret', scopes=('secrets.read',)))
    tb.authorize('dangerous_write')
    tb.authorize('hidden_read')
    return tb


MSGS = [Message(role='user', content='please write the file')]


def test_visible_specs_are_the_scope_intersection():
    tb = _boundary(DangerousTool())
    specs = visible_tool_specs(tb, {'filesystem.write'})
    names = {s.name for s in specs}
    assert names == {'dangerous_write'}          # out-of-scope tool invisible
    assert specs[0].scopes == ('filesystem.write',)


def test_scope_violation_blocks_real_tool():
    dangerous = DangerousTool()
    tb = _boundary(dangerous)
    engine = FakeEngine(_openai_call('dangerous_write', {'path': '/tmp/x'}))
    turn = run_model_tool_turn(engine=engine, messages=MSGS, tool_boundary=tb,
                               allowed_scopes={'filesystem.read'}, evidence_confidence=1.0)
    assert dangerous.calls == []                  # REAL TOOL never touched
    assert turn.executed == ()
    assert turn.decisions[0].state == 'Denied'
    # The tool was out of scope, so it was filtered from the visible list
    # BEFORE the model ever saw a spec; proposing it is denied as not-visible.
    assert turn.decisions[0].evidence.get('visible') is False
    assert any('not offered' in m for m in turn.blocked_messages)


def test_low_confidence_blocks_real_tool():
    dangerous = DangerousTool()
    tb = _boundary(dangerous)
    engine = FakeEngine(_openai_call('dangerous_write', {'path': '/tmp/x'}))
    turn = run_model_tool_turn(engine=engine, messages=MSGS, tool_boundary=tb,
                               allowed_scopes={'filesystem.write'}, evidence_confidence=0.4)
    assert dangerous.calls == []
    assert turn.decisions[0].state == 'Allowed'   # scope passed...
    assert turn.results[0].executed is False      # ...but the gate blocked
    assert 'required: 0.80' in turn.blocked_messages[0]


def test_full_pipeline_executes_the_real_tool():
    dangerous = DangerousTool()
    tb = _boundary(dangerous)
    engine = FakeEngine(_openai_call('dangerous_write', {'path': '/tmp/x'}))
    turn = run_model_tool_turn(engine=engine, messages=MSGS, tool_boundary=tb,
                               allowed_scopes={'filesystem.write'}, evidence_confidence=0.9)
    assert len(dangerous.calls) == 1              # the REAL tool ran, exactly once
    assert dangerous.calls[0] == {'path': '/tmp/x'}
    assert len(turn.executed) == 1
    assert turn.executed[0].result == 'wrote!'


def test_default_evidence_confidence_is_fail_closed():
    dangerous = DangerousTool()
    tb = _boundary(dangerous)
    engine = FakeEngine(_openai_call('dangerous_write', {'path': '/tmp/x'}))
    turn = run_model_tool_turn(engine=engine, messages=MSGS, tool_boundary=tb,
                               allowed_scopes={'filesystem.write'})  # no evidence
    assert dangerous.calls == []
    assert turn.results[0].executed is False


def test_unregistered_tool_denied_at_registry():
    dangerous = DangerousTool()
    tb = _boundary(dangerous)
    engine = FakeEngine(_openai_call('ghost_tool', {}))
    turn = run_model_tool_turn(engine=engine, messages=MSGS, tool_boundary=tb,
                               allowed_scopes={'filesystem.write'}, evidence_confidence=1.0)
    assert dangerous.calls == []
    assert turn.decisions[0].state == 'Denied'
    assert turn.decisions[0].evidence == {'registry': False}


def test_hidden_tool_not_offered_is_denied_even_if_in_scope_names():
    """The model proposes a tool that exists in the registry but was
    filtered OUT of the visible list (out-of-scope): denied, not executed."""
    dangerous = DangerousTool()
    tb = _boundary(dangerous)
    engine = FakeEngine(_openai_call('hidden_read', {}))
    turn = run_model_tool_turn(engine=engine, messages=MSGS, tool_boundary=tb,
                               allowed_scopes={'filesystem.write'}, evidence_confidence=1.0)
    assert dangerous.calls == []
    assert turn.decisions[0].evidence.get('visible') is False


def test_malformed_provider_payload_blocks_everything():
    dangerous = DangerousTool()
    tb = _boundary(dangerous)
    engine = FakeEngine({'tool_calls': 'not-a-list'})
    turn = run_model_tool_turn(engine=engine, messages=MSGS, tool_boundary=tb,
                               allowed_scopes={'filesystem.write'}, evidence_confidence=1.0)
    assert dangerous.calls == []
    assert turn.parse_error is not None
    assert turn.executed == ()
    assert turn.proposed_calls == ()


def test_no_tool_calls_returns_text_only():
    dangerous = DangerousTool()
    tb = _boundary(dangerous)
    engine = FakeEngine({'choices': [{'message': {'content': 'just chatting'}}]})
    turn = run_model_tool_turn(engine=engine, messages=MSGS, tool_boundary=tb,
                               allowed_scopes={'filesystem.write'}, evidence_confidence=1.0)
    assert turn.response_text == 'proposing a tool'
    assert turn.proposed_calls == ()
    assert dangerous.calls == []


def test_engine_receives_only_visible_specs():
    tb = _boundary(DangerousTool())
    engine = FakeEngine({'choices': [{'message': {'content': 'hi'}}]})
    run_model_tool_turn(engine=engine, messages=MSGS, tool_boundary=tb,
                        allowed_scopes={'filesystem.write'})
    assert engine.saw_tools is not None
    assert [t['name'] for t in engine.saw_tools] == ['dangerous_write']
    assert engine.saw_tools[0]['scopes'] == ['filesystem.write']  # scope metadata included


def test_every_decision_is_logged():
    dangerous = DangerousTool()
    tb = _boundary(dangerous)
    engine = FakeEngine(_openai_call('dangerous_write', {'path': '/tmp/x'}))
    log = []
    run_model_tool_turn(engine=engine, messages=MSGS, tool_boundary=tb,
                        allowed_scopes={'filesystem.write'}, evidence_confidence=0.9,
                        decision_log=log)
    assert len(log) >= 1
    assert log[-1]['decision']['state'] == 'Allowed'
    assert log[-1]['decision']['confidence'] == 0.9
