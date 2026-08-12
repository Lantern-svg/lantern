"""First-run bootstrap: detect environment, initialize directories,
identity, config, memory workspace. Reports exactly what is missing;
never silently installs software or configures credentials."""

from __future__ import annotations

import sys
from pathlib import Path

from .bridge import LanternBridge
from .config import load_config
from .reasoning import build_engine

HARNESS_ROOT = Path(__file__).resolve().parent.parent

REQUIRED_DIRS = ["memory", "identity", "tools", "agents", "projects", "prompts", "logs", "models", "logs"]


def check_python() -> tuple[bool, str]:
    ok = sys.version_info >= (3, 10)
    return ok, f"Python {sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"


def check_lantern_importable() -> tuple[bool, str]:
    try:
        import lantern  # noqa: F401
        return True, "lantern package importable"
    except ImportError as exc:
        return False, f"lantern package not importable: {exc}"


def ensure_directories() -> list[str]:
    created = []
    for name in REQUIRED_DIRS:
        d = HARNESS_ROOT / name
        if not d.exists():
            d.mkdir(parents=True, exist_ok=True)
            created.append(name)
    return created


def bootstrap() -> dict:
    checks = {}

    py_ok, py_detail = check_python()
    checks["python"] = {"ok": py_ok, "detail": py_detail}

    lantern_ok, lantern_detail = check_lantern_importable()
    checks["lantern"] = {"ok": lantern_ok, "detail": lantern_detail}

    created_dirs = ensure_directories()
    checks["directories"] = {"ok": True, "created": created_dirs}

    config = load_config()
    checks["config"] = {"ok": True, "detail": "loaded"}

    if not lantern_ok:
        checks["identity"] = {"ok": False, "detail": "skipped -- lantern not importable"}
        checks["memory"] = {"ok": False, "detail": "skipped -- lantern not importable"}
        return {"checks": checks, "bridge": None, "engine": None, "config": config}

    data_dir = HARNESS_ROOT / config.get("data_dir", "memory/lantern_data")
    bridge = LanternBridge(data_dir, node_id=config.get("node_id", "lantern-harness-node"))

    identity_result = bridge.ensure_identity()
    checks["identity"] = {"ok": identity_result.get("status") == "READY", "detail": identity_result}

    startup_result = bridge.startup()
    checks["memory"] = {"ok": startup_result.get("status") in ("READY", "NO_CHRONICLE"), "detail": startup_result}

    engine = build_engine(config.get("reasoning_engine", {}))
    if engine is not None:
        engine_ok, engine_detail = engine.detect()
        checks["reasoning_engine"] = {"ok": engine_ok, "detail": engine_detail}
    else:
        checks["reasoning_engine"] = {"ok": False, "detail": "REASONING_ENGINE: NOT_CONFIGURED"}

    checks["tool_boundary"] = {"ok": True, "detail": "0 tools registered by default"}

    return {"checks": checks, "bridge": bridge, "engine": engine, "config": config}


def format_bootstrap_report(result: dict) -> str:
    checks = result["checks"]
    lines = ["🌱 LANTERN HARNESS", "", "First launch detected. Checking:"]
    label_map = {
        "python": "Python",
        "lantern": "Lantern",
        "identity": "Identity",
        "memory": "Memory",
        "reasoning_engine": "Reasoning Engine",
        "tool_boundary": "Tool Boundary",
    }
    for key in ["python", "lantern", "identity", "memory", "reasoning_engine", "tool_boundary"]:
        c = checks.get(key, {"ok": False, "detail": "not checked"})
        mark = "✓" if c["ok"] else "✗"
        lines.append(f"{mark} {label_map[key]}")

    lines.append("")
    bridge = result.get("bridge")
    engine = result.get("engine")
    from .harness_status import lantern_version

    lines.append(f"Lantern: v{lantern_version()}")
    if engine is not None:
        ok, detail = engine.detect()
        lines.append(f"Reasoning Engine: {engine.provider_name} ({'ready' if ok else 'NOT AVAILABLE: ' + detail})")
    else:
        lines.append("Reasoning Engine: NOT_CONFIGURED")
    lines.append(f"Identity: {checks['identity']['detail'].get('status') if bridge else 'UNAVAILABLE'}")
    lines.append(f"Memory: {checks['memory']['detail'].get('status') if bridge else 'UNAVAILABLE'}")
    lines.append("Tools: 0 configured")
    lines.append("----------------------------")
    if bridge is not None:
        lines.append("Lantern is ready.")
    else:
        lines.append("Lantern is NOT ready -- see checks above.")
    return "\n".join(lines)
