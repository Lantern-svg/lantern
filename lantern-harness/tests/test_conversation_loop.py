import subprocess
import sys
from pathlib import Path

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
