import io
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

HARNESS_ROOT = Path(__file__).resolve().parent.parent


def _run_main(stdin_text: str, timeout: int = 30) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(HARNESS_ROOT / "main.py")],
        input=stdin_text,
        capture_output=True,
        text=True,
        cwd=str(HARNESS_ROOT),
        timeout=timeout,
    )


def test_first_launch_reaches_lantern_ready():
    result = _run_main("/exit\n")
    assert result.returncode == 0
    assert "🌱 LANTERN HARNESS" in result.stdout
    assert "Lantern is ready." in result.stdout


def test_message_without_reasoning_engine_reports_not_configured_not_fabricated():
    result = _run_main("hello\n/exit\n")
    assert "REASONING_ENGINE: NOT_CONFIGURED" in result.stdout
    assert "observation recorded" in result.stdout


def test_status_command_available_from_conversation_loop():
    result = _run_main("/status\n/exit\n")
    assert "LANTERN STATUS" in result.stdout


def test_graceful_shutdown_via_exit_command():
    result = _run_main("/exit\n")
    assert result.returncode == 0


def test_graceful_shutdown_via_eof():
    result = _run_main("")
    assert result.returncode == 0

def test_system_prompt_is_actually_sent_to_the_reasoning_engine(monkeypatch):
    """Regression test: prompts/system.md existed on disk but main.py
    never read it or passed it to the reasoning engine -- the file was
    inert. Verify run_repl() actually threads it through as a system
    message on the first call to engine.respond()."""
    import main as main_mod
    from lantern_harness.bridge import LanternBridge
    from lantern_harness.reasoning.base import ReasoningResponse

    tmp = Path(tempfile.mkdtemp())
    bridge = LanternBridge(tmp, node_id="repl-test")
    bridge.ensure_identity()
    bridge.startup()

    captured_messages = []

    class FakeEngine:
        provider_name = "fake"

        def respond(self, messages, tools=None):
            captured_messages.append(list(messages))
            return ReasoningResponse(text="fake reply", provider="fake", model="fake-model")

        def describe(self):
            return {"provider": "fake", "model": "fake-model", "available": True, "detail": "fake"}

    from lantern_harness.tools.boundary import ToolBoundary
    from lantern_harness.spine import BranchStore
    from lantern_harness.operating_loop import OperatingLoop

    monkeypatch.setattr(sys, "stdin", io.StringIO("hello there\n/exit\n"))
    tool_boundary = ToolBoundary()
    main_mod.run_repl(bridge, FakeEngine(), tool_boundary, BranchStore(), OperatingLoop(bridge, tool_boundary))

    assert len(captured_messages) == 1
    first_call = captured_messages[0]
    assert first_call[0]["role"] == "system"
    assert "NOT_IMPLEMENTED" in first_call[0]["content"]
    assert first_call[-1] == {"role": "user", "content": "hello there"}

def test_compile_command_produces_structured_prompt_not_fabricated():
    result = _run_main("/compile Should we delete the production backups?\n/exit\n")
    assert "[compiled, mode=heavyweight]" in result.stdout
    assert "NOT_PROVIDED" in result.stdout  # no fabricated evidence/assumptions
    assert "INVESTIGATION REQUEST" in result.stdout


def test_compile_command_with_no_request_shows_usage():
    result = _run_main("/compile\n/exit\n")
    assert "usage: /compile" in result.stdout


def test_compile_command_lightweight_for_ordinary_question():
    result = _run_main("/compile What is the boiling point of water?\n/exit\n")
    assert "[compiled, mode=lightweight]" in result.stdout

def test_self_command_reports_seven_sections():
    result = _run_main("/self\n/exit\n")
    assert "SELF-MODEL" in result.stdout
    assert "WHAT I KNOW" in result.stdout
    assert "WHAT I AM AUTHORIZED TO DO" in result.stdout
    assert "WHAT REQUIRES OPERATOR ACTION" in result.stdout


def test_branch_command_opens_a_real_branch():
    result = _run_main("/branch widgets :: widgets sell well\n/exit\n")
    assert "[branch opened]" in result.stdout
    assert "concept='widgets'" in result.stdout


def test_branch_command_without_double_colon_shows_usage():
    result = _run_main("/branch just some text\n/exit\n")
    assert "usage: /branch" in result.stdout


def test_spine_command_with_no_entries_reports_zero():
    result = _run_main("/spine\n/exit\n")
    assert "spine: 0 committed entries" in result.stdout


def test_spine_command_never_authorizes_a_commit_from_the_repl():
    result = _run_main("/branch widgets :: widgets sell well\n/spine fake-id widgets sell well\n/exit\n")
    assert "SPINE_NOT_COMMITTED" in result.stdout
    assert "cannot authorize a commit" in result.stdout


def test_run_command_executes_the_full_operating_loop():
    result = _run_main("/run should we trust this data?\n/exit\n")
    assert "OPERATING LOOP RESULT" in result.stdout
    assert "confidence:" in result.stdout
    assert "decision:" in result.stdout


def test_run_command_with_no_intent_shows_usage():
    result = _run_main("/run\n/exit\n")
    assert "usage: /run" in result.stdout

