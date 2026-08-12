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
    from lantern_harness.permission_authority import PermissionAuthority

    monkeypatch.setattr(sys, "stdin", io.StringIO("hello there\n/exit\n"))
    tool_boundary = ToolBoundary()
    main_mod.run_repl(bridge, FakeEngine(), tool_boundary, BranchStore(), OperatingLoop(bridge, tool_boundary), PermissionAuthority())

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



def test_permissions_command_reports_zero_active_grants_by_default():
    """A fresh process must start with no standing authority -- per
    the PEACEMAKER directive's Transfer Behavior, permission memory is
    never assumed, never inherited, never pre-populated."""
    result = _run_main("/permissions\n/exit\n")
    assert "permissions: 0 active grants" in result.stdout


def test_grant_command_requires_explicit_granting_authority():
    result = _run_main("/grant local_file_modification :: lantern-harness/ ::\n/exit\n")
    assert "usage: /grant" in result.stdout or "GRANT_REFUSED" in result.stdout


def test_grant_then_permissions_shows_the_new_grant():
    result = _run_main(
        "/grant local_file_modification :: lantern-harness project directory :: test-operator\n"
        "/permissions\n/exit\n"
    )
    assert "[granted]" in result.stdout
    assert "capability='local_file_modification'" in result.stdout
    assert "permissions: 1 active grant(s)" in result.stdout
    assert "granted_by='test-operator'" in result.stdout


def test_grant_rejects_unknown_capability_from_the_repl():
    result = _run_main("/grant not_a_real_capability :: some scope :: test-operator\n/exit\n")
    assert "GRANT_REFUSED" in result.stdout


def test_revoke_command_removes_an_active_grant():
    result = _run_main(
        "/grant run_tests :: lantern-harness test suite :: test-operator\n"
        "/revoke run_tests :: test-operator\n"
        "/permissions\n/exit\n"
    )
    assert "[revoked]" in result.stdout
    assert "count=1" in result.stdout
    assert "permissions: 0 active grants" in result.stdout
