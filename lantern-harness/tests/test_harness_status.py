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


def test_status_report_labels_unimplemented_concepts_honestly():
    tmp = Path(tempfile.mkdtemp())
    bridge = LanternBridge(tmp, node_id="status-test-2")
    report = status_report(bridge, None, ToolBoundary())
    assert "NOT_IMPLEMENTED" in report["branching_status"]
    assert "NOT_IMPLEMENTED" in report["perspective_engine_status"]


def test_format_status_report_produces_readable_text():
    tmp = Path(tempfile.mkdtemp())
    bridge = LanternBridge(tmp, node_id="status-test-3")
    report = status_report(bridge, None, ToolBoundary())
    text = format_status_report(report)
    assert "LANTERN STATUS" in text
    assert "Reasoning Engine: NOT_CONFIGURED" in text
