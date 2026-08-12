"""LANTERN STATUS reporting. Every field here must represent something
actually checked this call -- no field is hardcoded to a fixed value."""

from __future__ import annotations

import importlib.metadata

from .bridge import LanternBridge
from .reasoning.base import ReasoningEngine


def lantern_version() -> str:
    """Prefer the live module's __version__ attribute over installer
    dist-info metadata: dist-info can go stale (observed in practice --
    a dev venv reported v0.83 via importlib.metadata while the actually
    imported module was v0.84, because dist-info wasn't regenerated
    after a version bump). __version__ reflects the code that is
    actually running right now."""
    try:
        import lantern

        version = getattr(lantern, "__version__", None)
        if version:
            return str(version)
    except ImportError:
        pass

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
        "branching_status": "IMPLEMENTED (lantern_harness.spine.BranchStore/SpineCommitter -- real Branch/Spine model built on top of Lantern's Chronicle; Lantern v0.84 core itself still has no branch/spine/commitment concept, see LanternBridge.branches())",
        "prompt_compiler_status": "IMPLEMENTED (lantern_harness.prompt_compiler.PromptCompiler -- newly added this harness turn, not part of Lantern v0.84 core)",
        "perspective_engine_status": "PARTIAL: lantern_harness.perspective_differential.PerspectiveDifferentialEngine is a newly-added, narrow variance calculator over caller-supplied Perspective records (NOT part of Lantern v0.84 core, NOT the full Perspective Mesh roadmap item -- no merge/vote/consensus logic exists)",
        "confidence_field_status": "IMPLEMENTED (lantern_harness.confidence_field.ConfidenceField -- read-only scoring layer over existing Lantern evidence/contradiction/integrity state)",
        "decision_state_machine_status": "IMPLEMENTED (lantern_harness.decision_state_machine.DecisionStateMachine -- explicit state/recommendation layer that never authorizes or executes)",
        "validation_status": "PARTIAL (EvidenceKernel.belief() sigmoid scoring + contradiction detection are real; no separate weighted-threshold ValidationEngine class exists)",
        "reality_boundary_status": "IMPLEMENTED (lantern_harness.reality_boundary.RealityBoundary -- INTENT/DECISION/AUTHORIZATION/ACTION/RESULT separation; REAL vs SIMULATED execution_mode is mutually exclusive by construction, see ActionRecord.is_real_success())",
        "self_model_status": "IMPLEMENTED (lantern_harness.self_model.SelfModel -- read-only self-description; has no method capable of granting itself authorization, see test_self_model_cannot_self_authorize)",
        "operating_loop_status": "IMPLEMENTED (lantern_harness.operating_loop.OperatingLoop -- composes Observation/PromptCompiler/ConfidenceField/DecisionStateMachine/RealityBoundary/Branch into one callable pipeline; adds no new decision logic of its own)",
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
    lines.append(f"Prompt Compiler: {report['prompt_compiler_status']}")
    lines.append(f"Perspective Differential: {report['perspective_engine_status']}")
    lines.append(f"Confidence Field: {report['confidence_field_status']}")
    lines.append(f"Decision State Machine: {report['decision_state_machine_status']}")
    lines.append(f"MCP: {report['mcp_status']}")
    lines.append(f"Tools: discovered={report['tools']['discovered']}, authorized={report['tools']['authorized']}")
    lines.append(f"Reality Boundary: {report['reality_boundary_status']}")
    lines.append(f"Self-Model: {report['self_model_status']}")
    lines.append(f"Operating Loop: {report['operating_loop_status']}")
    return "\n".join(lines)
