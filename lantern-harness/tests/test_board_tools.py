"""Board tools: every required boundary test.

Uses a FakeBoardClient (deterministic, no network, no credentials) for
the normal suite. The real BoardClient is exercised only by the
separately gated live test (tests/test_board_live.py).

Required scenarios (per the integration directive, section 14):
 1. board_read registered
 2. board_read visible when authorized
 3. board_read hidden when unauthorized
 4. board_get_entry requires a valid entry identifier
 5. board_verify rejects a malformed entry
 6. board_verify reports an actual verification state
 7. board_post hidden without the posting scope
 8. model proposing a hidden board_post is denied
 9. board_post blocked at low confidence
10. board_post blocked without evidence
11. board_post blocked without verification when policy requires it
12. board_post blocked with the wrong scope
13. board_post executes exactly once (correct scope, evidence, confidence)
14. failed network operation produces no false success
15. malformed provider tool call produces zero execution
16. arbitrary URL cannot be supplied to board_post
17. the model cannot supply its own authorization scope
18. MCP cannot bypass the decision gate
19. the old RealityBoundary.act() path cannot bypass execution
20. every real board mutation passes through execute_tool_call()
"""

import subprocess
import uuid
from pathlib import Path
import shutil
import sys

import pytest

sys.path.insert(0, ".")

from lantern_harness.board.client import BoardClient, BoardClientError
from lantern_harness.board.tools import (
    BOARD_POST, BOARD_READ, BOARD_VERIFY, SCOPE_POST, SCOPE_READ, SCOPE_VERIFY,
    board_tool_specs, register_board_tools,
)
from lantern_harness.decision_gate import (
    authorize_tool_call, effective_required_confidence, execute_tool_call,
)
from lantern_harness.model_tool_pipeline import run_model_tool_turn, visible_tool_specs
from lantern_harness.operating_loop import OperatingLoop
from lantern_harness.tool_contract import Message, ToolCall
from lantern_harness.tools.boundary import ToolBoundary
from lantern_harness.bridge import LanternBridge

from tests.test_model_tool_pipeline import FakeEngine, _openai_call  # shared test helpers


TMP = Path("/tmp/lantern_harness_board_tests")


# ---------------------------------------------------------------- fakes
class FakeBoardClient(BoardClient):
    """Deterministic board stand-in. Counts every post so a false
    success is impossible to hide."""

    def __init__(self, *, fail_posts=False):
        self.posts = []
        self.post_calls = 0
        self.fail_posts = fail_posts
        super().__init__(endpoint="https://board.invalid", board="lantern-board")

    def read_board(self, limit=10, cursor=None):
        return {"status": "OBSERVED", "board": self.board, "source": self.endpoint,
                "retrieved_at_ms": 1, "count": min(limit, len(self.posts)),
                "next_cursor": None,
                "entries": [{"entry_id": h, "message_id": m, "content": c,
                             "verification_status": "OBSERVED"}
                            for (h, m, c) in self.posts[:limit]],
                "note": "OBSERVATION only"}

    def get_entry(self, entry_id):
        for (h, m, c) in self.posts:
            if h == entry_id or m == entry_id:
                return {"status": "OBSERVED", "board": self.board,
                        "entry": {"entry_id": h, "message_id": m, "content": c,
                                  "verification_status": "OBSERVED"}}
        return {"status": "UNKNOWN", "detail": "not found"}

    def verify_entry(self, entry_id=None):
        if entry_id is not None and not isinstance(entry_id, str):
            return {"status": "BLOCKED", "detail": "malformed entry"}
        return {"status": "CORROBORATED", "checked": len(self.posts),
                "checks": {"signature": {"state": "CORROBORATED"},
                           "hash_integrity": {"state": "CORROBORATED"},
                           "linkage": {"state": "CORROBORATED"}}}

    def post_entry(self, content, *, kind="post", verified=False):
        self.post_calls += 1
        if self.fail_posts:
            raise BoardClientError("board unreachable: simulated network failure")
        message_id = str(uuid.uuid4())
        entry_id = "e" + "0" * 63
        self.posts.append((entry_id, message_id, content))
        return {"status": "POSTED", "board": self.board, "message_id": message_id,
                "entry_id": entry_id, "note": "real mutation"}


def _registry(client):
    tb = ToolBoundary()
    register_board_tools(tb, client)
    return tb


def _registry_authorized(client, include_post=False):
    tb = _registry(client)
    tb.authorize(BOARD_READ)
    tb.authorize("board_get_entry")
    tb.authorize(BOARD_VERIFY)
    if include_post:
        tb.authorize(BOARD_POST)
    return tb


def _fresh_bridge(name):
    path = TMP / name
    if path.exists():
        shutil.rmtree(path)
    bridge = LanternBridge(data_dir=path)
    bridge.ensure_identity()
    bridge.startup()
    return bridge


# ------------------------------------------------- 1-3: registration & visibility
def test_1_board_read_registered():
    tb = _registry(FakeBoardClient())
    assert tb.get(BOARD_READ) is not None
    assert tb.get(BOARD_READ).scopes == (SCOPE_READ,)


def test_2_board_read_visible_when_authorized():
    tb = _registry_authorized(FakeBoardClient())
    specs = visible_tool_specs(tb, {SCOPE_READ, SCOPE_VERIFY})
    assert BOARD_READ in {s.name for s in specs}


def test_3_board_read_hidden_when_unauthorized():
    tb = _registry(FakeBoardClient())  # registered but NOT authorized
    specs = visible_tool_specs(tb, {SCOPE_READ})
    assert BOARD_READ not in {s.name for s in specs}   # invisible to the model


# ------------------------------------------------- 4-6: entry + verify tools
def test_4_board_get_entry_requires_valid_identifier():
    tb = _registry_authorized(FakeBoardClient())
    result = tb.get("board_get_entry").handler(entry_id="https://evil.example/x")
    assert result["status"] == "BLOCKED"           # URLs rejected at the tool layer
    result = tb.get("board_get_entry").handler(entry_id="")
    assert result["status"] == "BLOCKED"


def test_5_board_verify_rejects_malformed_entry():
    tb = _registry_authorized(FakeBoardClient())
    handler = tb.get(BOARD_VERIFY).handler
    assert handler(entry_id=None)["status"] == "CORROBORATED"  # whole-board verify ok
    assert handler(entry_id="https://evil.example/e")["status"] == "BLOCKED"


def test_6_board_verify_reports_actual_state():
    tb = _registry_authorized(FakeBoardClient())
    report = tb.get(BOARD_VERIFY).handler()
    assert report["status"] == "CORROBORATED"
    assert set(report["checks"].keys()) >= {"signature", "hash_integrity", "linkage"}


# ------------------------------------------------- 7-13: board_post gating
def _post_call(content="hello board"):
    return ToolCall(id=str(uuid.uuid4()), tool_name=BOARD_POST, arguments={"content": content})


def test_7_board_post_hidden_without_posting_scope():
    tb = _registry_authorized(FakeBoardClient())
    specs = visible_tool_specs(tb, {SCOPE_READ, SCOPE_VERIFY})  # no board.post
    assert BOARD_POST not in {s.name for s in specs}


def test_8_model_proposing_hidden_board_post_is_denied():
    client = FakeBoardClient()
    tb = _registry_authorized(client)  # board_post registered but NOT authorized
    engine = FakeEngine(_openai_call(BOARD_POST, {"content": "hi"}))
    turn = run_model_tool_turn(engine=engine, messages=[Message(role="user", content="post hi")],
                               tool_boundary=tb, allowed_scopes={SCOPE_READ, SCOPE_VERIFY},
                               evidence_confidence=1.0)
    assert client.post_calls == 0
    assert turn.executed == ()
    assert any("visible tool registry" in m or "not offered" in m
               for m in turn.blocked_messages)   # NOT_VISIBLE denial


def test_9_board_post_blocked_at_low_confidence():
    client = FakeBoardClient()
    tb = _registry_authorized(client, include_post=True)
    call = _post_call()
    decision = authorize_tool_call(call, {SCOPE_POST}, evidence_confidence=0.3, tool_boundary=tb)
    assert decision.state == "Allowed"
    threshold = effective_required_confidence(tb, BOARD_POST, 0.8)
    tcr, tool_result = execute_tool_call(call, decision, threshold, tb)
    assert client.post_calls == 0
    assert tool_result.status == "BLOCKED"
    assert "required: 0.80" in tcr.blocked_reason


def test_10_board_post_blocked_without_evidence():
    client = FakeBoardClient()
    tb = _registry_authorized(client, include_post=True)
    engine = FakeEngine(_openai_call(BOARD_POST, {"content": "hi"}))
    turn = run_model_tool_turn(engine=engine, messages=[Message(role="user", content="post hi")],
                               tool_boundary=tb, allowed_scopes={SCOPE_POST})
    assert client.post_calls == 0                     # fail-closed default (no evidence arg)
    assert turn.results[0].executed is False
    assert turn.results[0].decision.confidence == 0.0


def test_11_board_post_blocked_without_verification_when_policy_requires_it():
    """Through the loop: UNVERIFIED compiles cap below the 0.8 threshold,
    so a post without independent verification is blocked."""
    client = FakeBoardClient()
    tb = _registry_authorized(client, include_post=True)
    bridge = _fresh_bridge("unverified-post")
    loop = OperatingLoop(bridge, tb, allowed_scopes={SCOPE_POST})
    result = loop.run("post to the board", concept="board_post_unverified_case",
                      tool_name=BOARD_POST, tool_kwargs={"content": "hi"})
    assert client.post_calls == 0
    assert result.action_record.is_real_success() is False
    assert any("BLOCKED" in n for n in result.notes)


def test_12_board_post_blocked_with_wrong_scope():
    client = FakeBoardClient()
    tb = _registry_authorized(client, include_post=True)
    call = _post_call()
    decision = authorize_tool_call(call, {SCOPE_READ}, evidence_confidence=1.0, tool_boundary=tb)
    assert decision.state == "Denied"                 # descriptor scope wins
    tcr, tool_result = execute_tool_call(call, decision, 0.8, tb)
    assert client.post_calls == 0


def test_13_board_post_executes_exactly_once():
    client = FakeBoardClient()
    tb = _registry_authorized(client, include_post=True)
    bridge = _fresh_bridge("verified-post")
    loop = OperatingLoop(bridge, tb, allowed_scopes={SCOPE_POST})
    concept = "board_post_verified_case"
    for i in range(3):
        obs = bridge.observe(f"operator verified {i}: this post is intended",
                             source=f"operator-verifier-{i}", reliability=1.0)
        bridge.add_evidence(concept, obs.id, weight=1.0, sign=1)
    result = loop.run("post to the board", concept=concept, validation_status="VERIFIED",
                      tool_name=BOARD_POST, tool_kwargs={"content": "hello board"})
    assert client.post_calls == 1                     # exactly once
    assert result.action_record.is_real_success() is True
    assert result.action_record.result["status"] == "POSTED"


# ------------------------------------------------- 14-17: fail-closed & contract
def test_14_failed_network_is_no_false_success():
    client = FakeBoardClient(fail_posts=True)
    tb = _registry_authorized(client, include_post=True)
    call = _post_call()
    decision = authorize_tool_call(call, {SCOPE_POST}, evidence_confidence=0.9, tool_boundary=tb)
    tcr, tool_result = execute_tool_call(call, decision, 0.8, tb)
    assert client.post_calls == 1                     # gate allowed the attempt...
    assert tool_result.status == "ERROR"              # ...but the transport failure is honest
    assert tcr.executed is False
    assert tcr.result is None                         # never a fabricated POSTED


def test_15_malformed_provider_call_zero_execution():
    client = FakeBoardClient()
    tb = _registry_authorized(client, include_post=True)
    engine = FakeEngine({"tool_calls": "not-a-list"})
    turn = run_model_tool_turn(engine=engine, messages=[Message(role="user", content="x")],
                               tool_boundary=tb, allowed_scopes={SCOPE_POST}, evidence_confidence=1.0)
    assert client.post_calls == 0
    assert turn.parse_error is not None
    assert turn.executed == ()


def test_16_arbitrary_url_cannot_be_supplied():
    tb = _registry_authorized(FakeBoardClient())
    # reads: a cursor must be a legitimate identifier, never a URL
    result = tb.get(BOARD_READ).handler(limit=10, cursor="https://evil.example")
    assert result["status"] == "BLOCKED"
    handler = tb.get(BOARD_POST).handler
    # the handler accepts ONLY content; an unexpected kwarg cannot bind to anything
    with pytest.raises(TypeError):
        handler(content="x", url="https://evil.example")


def test_17_model_cannot_supply_its_own_scope():
    client = FakeBoardClient()
    tb = _registry_authorized(client, include_post=True)
    call = ToolCall(id="c", tool_name=BOARD_POST, arguments={"content": "x"},
                    requested_scopes=("board.read",))
    decision = authorize_tool_call(call, {SCOPE_READ}, evidence_confidence=1.0, tool_boundary=tb)
    assert decision.state == "Denied"                 # descriptor scope wins
    assert SCOPE_POST in decision.evidence["missing_scopes"]
    tcr, _ = execute_tool_call(call, decision, 0.8, tb)
    assert client.post_calls == 0


# ------------------------------------------------- 18-20: bypass regressions
def test_18_mcp_cannot_bypass_the_decision_gate():
    """Source-level: every MCP board wrapper must terminate at
    execute_tool_call, never call the client directly."""
    src = Path("lantern_harness/mcp_server.py").read_text()
    for wrapper in ("lantern_board_read", "lantern_board_get_entry",
                    "lantern_board_verify", "lantern_board_post"):
        body = src.split(f"def {wrapper}")[1].split("def ")[0]
        assert "execute_tool_call(" in body, f"{wrapper} must go through the gate"
        assert "_board_client." not in body and "client.post_entry" not in body
    assert "register_board_tools" in src            # same registry
    assert "LANTERN_ALLOW_BOARD_POST" in src        # explicit post opt-in


def test_19_reality_boundary_act_cannot_bypass_execution():
    """The deprecated act() path must be structurally unable to reach a
    consequential tool, and the loop/pipeline must not call it at all."""
    loop_src = Path("lantern_harness/operating_loop.py").read_text()
    assert ".act(" not in loop_src
    pipeline_src = Path("lantern_harness/model_tool_pipeline.py").read_text()
    assert ".act(" not in pipeline_src
    rb_src = Path("lantern_harness/reality_boundary.py").read_text()
    act_body = rb_src.split("def act(")[1]
    assert "DEPRECATED path refused" in act_body      # structural refusal
    assert "required_confidence" in act_body          # observational-only


def test_20_every_board_mutation_passes_through_execute_tool_call():
    """Audit: the only production .execute( call sites are the boundary
    itself, the deprecated observational-only act(), and the gate."""
    out = subprocess.run(["grep", "-rn", ".execute(", "lantern_harness/"],
                         capture_output=True, text=True).stdout
    for line in out.splitlines():
        if ".execute()" in line:
            continue  # no-arg mentions are docstrings; real calls take arguments
        path = line.split(":")[0]
        assert path.endswith(("boundary.py", "reality_boundary.py", "decision_gate.py")), \
            f"unexpected production execute() caller: {line}"
    # board_post's only production caller chain: tools.py handler <- ToolBoundary.execute <- gate
    out2 = subprocess.run(["grep", "-rn", "post_entry", "lantern_harness/", "--include=*.py"],
                          capture_output=True, text=True).stdout
    for line in out2.splitlines():
        assert "board/tools.py" in line or "board/client.py" in line, \
            f"unexpected post_entry caller: {line}"


def test_read_threshold_is_per_descriptor_and_model_cannot_change_it():
    tb = _registry(FakeBoardClient())
    assert effective_required_confidence(tb, BOARD_READ, 0.8) == 0.0   # observational
    assert effective_required_confidence(tb, BOARD_POST, 0.8) == 0.8  # consequential: session


def test_board_tool_specs_static():
    specs = board_tool_specs()
    assert specs[BOARD_POST]["required_confidence"] is None
    assert set(specs.keys()) == {BOARD_READ, "board_get_entry", BOARD_VERIFY, BOARD_POST}
