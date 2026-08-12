"""LANTERN STATUS reporting. Every field here must represent something
actually checked this call -- no field is hardcoded to a fixed value."""

from __future__ import annotations

import importlib.metadata

from .bridge import LanternBridge
from .reasoning.base import ReasoningEngine


def lantern_version() -> str:
    try:
        return importlib.metadata.version("lantern")
    except importlib.metadata.PackageNotFoundError:
        return "UNKNOWN (lantern package not installed in this environment)"


HARNESS_VERSION = "0.1.0"


def status_report(bridge: LanternBridge, engine: ReasoningEngine | None, tool_boundary) -> dict:
    lantern_status = bridge.status()
    identity_status = bridge.identity_status()
    witness = bridge.witness_integrity()

    engine_status = engine.describe() if engine is not None else {"provider": None, "available": False, "detail": "REASONING_ENGINE: NOT_CONFIGURED"}

    return {
        "lantern_version": lantern_version(),
        "harness_version": HARNESS_VERSION,
        "node_identity": identity_status,
        "reasoning_engine": engine_status,
        "memory": {
            "chronicle_attached": lantern_status.get("chronicle", False),
            "step": lantern_status.get("step"),
            "observations": lantern_status.get("observations"),
            "evidence": lantern_status.get("evidence"),
            "contradictions": lantern_status.get("contradictions"),
        },
        "witness_integrity": witness,
        "tools": {
            "discovered": tool_boundary.discover(),
            "authorized": sorted(tool_boundary._authorized),  # noqa: SLF001 - status reporting only
        },
        "mcp_status": "NOT_CONNECTED (harness does not auto-connect an MCP server; see EXTERNAL_BOOTSTRAP.md in lantern-babel-codex-bridge for lantern.mcp_client usage)",
        "branching_status": "NOT_IMPLEMENTED (Lantern v0.84 has no branch/spine/commitment model)",
        "perspective_engine_status": "NOT_IMPLEMENTED (no perspective differential engine exists in Lantern v0.84)",
        "validation_status": "PARTIAL (EvidenceKernel.belief() sigmoid scoring + contradiction detection are real; no separate weighted-threshold ValidationEngine class exists)",
        "reality_boundary_status": "NOT_IMPLEMENTED (no dedicated RealityBoundary class in Lantern v0.84; this harness does not fabricate one)",
    }


def format_status_report(report: dict) -> str:
    lines = [
        "LANTERN STATUS",
        "----------------------------",
        f"Lantern Version: {report['lantern_version']}",
        f"Harness Version: {report['harness_version']}",
        f"Node Identity: {report['node_identity'].get('status')}",
    ]
    engine = report["reasoning_engine"]
    if engine.get("provider"):
        lines.append(f"Reasoning Engine: {engine['provider']} ({'available' if engine.get('available') else 'NOT AVAILABLE'})")
        lines.append(f"Model: {engine.get('model', 'n/a')}")
    else:
        lines.append("Reasoning Engine: NOT_CONFIGURED")
        lines.append("Model: n/a")
    mem = report["memory"]
    lines.append(f"Memory: chronicle_attached={mem['chronicle_attached']}, step={mem['step']}, observations={mem['observations']}, evidence={mem['evidence']}, contradictions={mem['contradictions']}")
    lines.append(f"Witness Integrity: {report['witness_integrity'].get('status')}")
    lines.append(f"Validation: {report['validation_status']}")
    lines.append(f"Branches / Spine: {report['branching_status']}")
    lines.append(f"MCP: {report['mcp_status']}")
    lines.append(f"Tools: discovered={report['tools']['discovered']}, authorized={report['tools']['authorized']}")
    lines.append(f"Reality Boundary: {report['reality_boundary_status']}")
    return "\n".join(lines)
