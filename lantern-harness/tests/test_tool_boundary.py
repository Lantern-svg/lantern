import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lantern_harness.tools.boundary import ToolBoundary, ToolDescriptor


def test_discovery_does_not_imply_authorization():
    boundary = ToolBoundary()
    boundary.register(ToolDescriptor(name="echo", description="echoes input", handler=lambda text: text))

    assert "echo" in boundary.discover()
    assert boundary.is_authorized("echo") is False

    result = boundary.execute("echo", text="hi")
    assert result.status == "DENIED"


def test_authorized_tool_executes():
    boundary = ToolBoundary()
    boundary.register(ToolDescriptor(name="echo", description="echoes input", handler=lambda text: text))
    boundary.authorize("echo")

    result = boundary.execute("echo", text="hi")
    assert result.status == "EXECUTED"
    assert result.output == "hi"


def test_unregistered_tool_execution_errors():
    boundary = ToolBoundary()
    result = boundary.execute("nonexistent")
    assert result.status == "ERROR"


def test_handler_exception_becomes_error_result_not_crash():
    boundary = ToolBoundary()

    def bad_handler():
        raise ValueError("boom")

    boundary.register(ToolDescriptor(name="bad", description="always fails", handler=bad_handler))
    boundary.authorize("bad")

    result = boundary.execute("bad")
    assert result.status == "ERROR"
    assert "boom" in result.error


def test_authorize_unknown_tool_returns_false():
    boundary = ToolBoundary()
    assert boundary.authorize("nonexistent") is False
