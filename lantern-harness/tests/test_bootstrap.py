import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lantern_harness.bootstrap import bootstrap, check_python, ensure_directories


def test_check_python_reports_actual_version():
    ok, detail = check_python()
    assert ok is True
    assert "Python 3." in detail


def test_bootstrap_returns_bridge_when_lantern_importable():
    result = bootstrap()
    assert result["checks"]["lantern"]["ok"] is True
    assert result["bridge"] is not None


def test_bootstrap_reasoning_engine_not_configured_by_default():
    result = bootstrap()
    assert result["engine"] is None
    assert result["checks"]["reasoning_engine"]["ok"] is False
    assert "NOT_CONFIGURED" in result["checks"]["reasoning_engine"]["detail"]


def test_ensure_directories_creates_all_required(tmp_path, monkeypatch):
    import lantern_harness.bootstrap as bootstrap_mod

    monkeypatch.setattr(bootstrap_mod, "HARNESS_ROOT", tmp_path)
    created = ensure_directories()
    for name in bootstrap_mod.REQUIRED_DIRS:
        assert (tmp_path / name).exists()
