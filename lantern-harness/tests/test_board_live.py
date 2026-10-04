"""LIVE board integration test -- clearly separated from the normal suite.

Runs ONLY when the operator explicitly opts in:
    LANTERN_BOARD_LIVE=1  and  LANTERN_BOARD_TOKEN in the environment

Never prints credentials. The write test posts one harmless, clearly
labeled test message to a dedicated TEST board (never the public wall),
through the FULL chain: proposal -> normalization -> registry ->
visibility -> evidence -> decision -> authorization -> execute_tool_call()
-> real board operation -> real result.

The provider seam is exercised with a deterministic FakeEngine (no keys,
no network): every stage AFTER the provider is real harness code against
the REAL board.
"""

import os
import shutil
import sys
import time
import uuid
from pathlib import Path

import pytest

sys.path.insert(0, ".")

pytestmark = pytest.mark.skipif(
    os.environ.get("LANTERN_BOARD_LIVE") != "1" or not os.environ.get("LANTERN_BOARD_TOKEN"),
    reason="live board test requires LANTERN_BOARD_LIVE=1 and LANTERN_BOARD_TOKEN",
)

from lantern_harness.board.client import BoardClient
from lantern_harness.board.tools import register_board_tools
from lantern_harness.config import load_config
from lantern_harness.model_tool_pipeline import run_model_tool_turn
from lantern_harness.operating_loop import OperatingLoop
from lantern_harness.tool_contract import Message
from lantern_harness.tools.boundary import ToolBoundary
from lantern_harness.bridge import LanternBridge

from tests.test_model_tool_pipeline import FakeEngine, _openai_call

TMP = Path("/tmp/lantern_harness_board_live")
PUBLIC_BOARD = "lantern-board"
TEST_BOARD = "lantern-harness-live-test"   # dedicated; never the public wall


def _client(board, bridge=None):
    cfg = load_config()["board"]
    # Each live-test identity is FRESH, so its node_id must be unique per run:
    # the board globally binds node_id -> public_key (D4/D8), and reusing a
    # fixed name across fresh keys yields BINDING_MISMATCH 403. Identity is
    # the key, not the name.
    import uuid as _uuid
    node_id = f"lantern-harness-live-{_uuid.uuid4().hex[:8]}"
    return BoardClient(endpoint=cfg["endpoint"], board=board,
                       node_id=node_id,
                       token_env=cfg.get("token_env", "LANTERN_BOARD_TOKEN"),
                       identity_provider=(lambda: getattr(bridge, "_identity", None)) if bridge else None)


def _bridge(name):
    path = TMP / name
    if path.exists():
        shutil.rmtree(path)
    bridge = LanternBridge(data_dir=path)
    bridge.ensure_identity()
    bridge.startup()
    return bridge


def _gated_boundary(client, bridge, include_post):
    tb = ToolBoundary()
    register_board_tools(tb, client)
    for n in ("board_read", "board_get_entry", "board_verify"):
        tb.authorize(n)
    if include_post:
        tb.authorize("board_post")
    tb._board_bridge = bridge  # for the loop below
    return tb


def test_live_read_full_chain_returns_real_observations():
    client = _client(PUBLIC_BOARD)
    bridge = _bridge("live-read")
    tb = _gated_boundary(client, bridge, include_post=False)
    engine = FakeEngine(_openai_call("board_read", {"limit": 5}))
    turn = run_model_tool_turn(
        engine=engine,
        messages=[Message(role="user", content="read the board")],
        tool_boundary=tb,
        allowed_scopes={"board.read", "board.verify"},
        evidence_confidence=0.0,   # observational: threshold is per-descriptor 0.0
    )
    assert len(turn.executed) == 1
    result = turn.executed[0].result
    assert result["status"] == "OBSERVED"
    assert result["source"].startswith("https://")
    assert result["retrieved_at_ms"] > 0
    for entry in result["entries"]:
        assert entry["verification_status"] == "OBSERVED"   # never unquestioned belief
    assert client.last_retrieval_ms is not None


def test_live_verify_reports_real_states():
    client = _client(PUBLIC_BOARD)
    bridge = _bridge("live-verify")
    tb = _gated_boundary(client, bridge, include_post=False)
    # pick a real recent entry from the public board
    snapshot = tb.get("board_read").handler(limit=3)
    if not snapshot["entries"]:
        pytest.skip("public board returned no entries")
    entry_id = snapshot["entries"][-1]["entry_id"]
    report = tb.get("board_verify").handler(entry_id=entry_id)
    assert report["status"] in ("CORROBORATED", "OBSERVED", "DISPROVEN", "UNKNOWN")
    for check in report["checks"].values():
        assert check["state"] in ("CORROBORATED", "OBSERVED", "CLAIMED", "DISPROVEN", "UNKNOWN", "BLOCKED")


def test_live_post_full_chain_writes_real_test_board_entry():
    bridge = _bridge("live-post")
    client = _client(TEST_BOARD, bridge=bridge)
    tb = _gated_boundary(client, bridge, include_post=True)
    loop = OperatingLoop(bridge, tb, allowed_scopes={"board.read", "board.verify", "board.post"})
    concept = f"live_post_case_{int(time.time())}"
    for i in range(3):
        obs = bridge.observe(f"operator verified {i}: this live-gate test post is intended",
                             source=f"live-verifier-{i}", reliability=1.0)
        bridge.add_evidence(concept, obs.id, weight=1.0, sign=1)
    content = f"[harness live gate test {int(time.time())}] harmless integration probe; ignore."
    result = loop.run("post the harmless live-gate test message", concept=concept,
                      validation_status="VERIFIED",
                      tool_name="board_post", tool_kwargs={"content": content})
    assert result.action_record.is_real_success() is True, result.notes
    posted = result.action_record.result
    assert posted["status"] == "POSTED"           # the REAL board accepted it
    assert posted["executed"] is True
    # prove it is real: fetch the entry back and independently verify it
    fetched = tb.get("board_get_entry").handler(entry_id=posted["entry_id"])
    assert fetched["status"] == "OBSERVED"
    assert fetched["entry"]["content"] == content
    report = tb.get("board_verify").handler(entry_id=posted["entry_id"])
    assert report["status"] == "CORROBORATED", report
    assert report["checks"]["signature"]["state"] == "CORROBORATED"  # signed by the harness identity


def test_live_post_blocked_when_low_confidence():
    """Negative live control: without evidence/verification the same real
    chain refuses to post."""
    bridge = _bridge("live-post-blocked")
    client = _client(TEST_BOARD, bridge=bridge)
    tb = _gated_boundary(client, bridge, include_post=True)
    loop = OperatingLoop(bridge, tb, allowed_scopes={"board.read", "board.verify", "board.post"})
    result = loop.run("post without any evidence", concept=f"unverified_{uuid.uuid4().hex[:8]}",
                      tool_name="board_post", tool_kwargs={"content": "should never appear"})
    assert result.action_record.is_real_success() is False
    assert any("BLOCKED" in n for n in result.notes)
