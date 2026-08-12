import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lantern_harness.bridge import LanternBridge
from lantern_harness.harness_status import format_status_report, status_report
from lantern_harness.tools.boundary import ToolBoundary


def test_status_report_reflects_actual_bridge_state():
    tmp = Path(tempfile.mkdtemp())
    bridge = LanternBridge(tmp, node_id="status-test")
    bridge.ensure_identity()
    bridge.startup()
    bridge.observe("fact", source="test", reliability=1.0)

    report = status_report(bridge, None, ToolBoundary())
    assert report["node_identity"]["status"] == "READY"
    assert report["memory"]["observations"] == 1
    assert report["reasoning_engine"]["provider"] is None


def test_status_report_labels_spine_and_reality_boundary_as_implemented_harness_additions():
    """Branch/Spine and RealityBoundary were added this harness turn as
    real, tested code (lantern_harness.spine, lantern_harness.reality_boundary).
    Lantern v0.84 core itself still has neither -- the report must say so
    without claiming the harness addition doesn't exist."""
    tmp = Path(tempfile.mkdtemp())
    bridge = LanternBridge(tmp, node_id="status-test-2")
    report = status_report(bridge, None, ToolBoundary())
    assert "IMPLEMENTED" in report["branching_status"]
    assert "Lantern v0.84 core itself still has no branch" in report["branching_status"]
    assert "IMPLEMENTED" in report["reality_boundary_status"]


def test_status_report_self_model_and_operating_loop_reported_as_implemented():
    tmp = Path(tempfile.mkdtemp())
    bridge = LanternBridge(tmp, node_id="status-test-2d")
    report = status_report(bridge, None, ToolBoundary())
    assert "IMPLEMENTED" in report["self_model_status"]
    assert "IMPLEMENTED" in report["operating_loop_status"]


def test_status_report_perspective_engine_is_labeled_partial_not_full_mesh():
    """PerspectiveDifferentialEngine was added this turn -- it is real,
    but it is not the Perspective Mesh / Decision State Machine roadmap
    item, and the status report must not claim it is."""
    tmp = Path(tempfile.mkdtemp())
    bridge = LanternBridge(tmp, node_id="status-test-2b")
    report = status_report(bridge, None, ToolBoundary())
    assert "PARTIAL" in report["perspective_engine_status"]
    assert "NOT the full Perspective Mesh" in report["perspective_engine_status"]


def test_status_report_prompt_compiler_reported_as_implemented():
    tmp = Path(tempfile.mkdtemp())
    bridge = LanternBridge(tmp, node_id="status-test-2c")
    report = status_report(bridge, None, ToolBoundary())
    assert "IMPLEMENTED" in report["prompt_compiler_status"]


def test_format_status_report_produces_readable_text():
    tmp = Path(tempfile.mkdtemp())
    bridge = LanternBridge(tmp, node_id="status-test-3")
    report = status_report(bridge, None, ToolBoundary())
    text = format_status_report(report)
    assert "LANTERN STATUS" in text
    assert "Reasoning Engine: NOT_CONFIGURED" in text
    assert "Self-Model:" in text
    assert "Operating Loop:" in text

def test_status_report_mcp_server_status_reflects_real_sdk_availability():
    tmp = Path(tempfile.mkdtemp())
    bridge = LanternBridge(tmp, node_id="status-test-mcp")
    report = status_report(bridge, None, ToolBoundary())
    try:
        import mcp  # noqa: F401
        assert "AVAILABLE" in report["mcp_server_status"]
        assert "NOT_AVAILABLE" not in report["mcp_server_status"]
    except ImportError:
        assert "NOT_AVAILABLE" in report["mcp_server_status"]
