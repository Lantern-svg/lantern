"""TransferManifest: describes a Lantern Harness instance so a receiving
operator or agent can decide whether to adopt it, without silently
inheriting any authority the sending operator held.

This module answers, honestly and only from real observed state:

    IDENTITY            -- which node this is (public key only, never
                            the private key -- see lantern.identity)
    PROTOCOL            -- Lantern core protocol version + harness
                            version, so compatibility can be checked
                            before state is trusted
                            (lantern.protocol.PROTOCOL_VERSION,
                            lantern.compatibility.negotiate -- reused,
                            not reinvented)
    CONFIGURATION       -- non-secret config only (reasoning engine
                            provider name and API-key *env var name*,
                            never the key value itself -- see
                            lantern_harness.config's existing rule)
    STATE_SUMMARY       -- counts, not raw content: observations,
                            evidence, contradictions, branches, spine
                            entries, scars. (Full state is transferred
                            by copying the data_dir itself, which this
                            manifest documents but does not perform --
                            see NOTES.)
    CAPABILITIES        -- reuses SelfModel.KNOWN_CAPABILITIES verbatim,
                            not a second capability list
    BOUNDARIES          -- reuses SelfModel.STANDING_OPERATOR_BOUNDARIES
                            verbatim, explicitly listed as
                            "does NOT transfer" items
    PROVENANCE          -- what commit of lantern-harness and lantern
                            core produced this manifest, when, and by
                            what Python version (best-effort; falls
                            back to UNKNOWN rather than guessing)
    INTEGRITY           -- real Chronicle.verify() result via
                            bridge.witness_integrity(), not assumed VALID
    REAUTHORIZATION_REQUIRED -- explicit list of things the receiving
                            operator must decide fresh; never inferred
                            from the sending operator's prior decisions

Hard rule, mirroring self_model.py: this module is read-only. It
authorizes nothing, grants nothing, and never embeds a credential,
key, or secret value. Verified by
test_transfer_manifest_never_contains_a_private_key_byte and
test_transfer_manifest_is_read_only.
"""

from __future__ import annotations

import importlib.metadata
import platform
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from .bridge import LanternBridge
from .harness_status import HARNESS_VERSION, lantern_version
from .self_model import KNOWN_CAPABILITIES, KNOWN_GAPS, STANDING_OPERATOR_BOUNDARIES


REAUTHORIZATION_REQUIRED = (
    "where this instance runs (host/network placement)",
    "what reasoning engine credentials it is given, if any",
    "what MCP hosts it may serve (e.g. registering it in Odysseus or any other agent environment)",
    "what external actions, if any, are authorized through a ToolBoundary",
    "whether any paid capability (e.g. the x402 reconciliation service) is activated",
    "whether network exposure beyond localhost stdio is permitted",
    "whether the transferred data_dir is trusted as-is or re-verified before use",
)


def _git_commit(repo_root: Path) -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        pass
    return "UNKNOWN (not a git checkout, or git unavailable)"


def _lantern_core_commit() -> str:
    try:
        import lantern

        core_file = Path(lantern.__file__).resolve()
        repo_root = core_file.parent.parent.parent
        return _git_commit(repo_root)
    except ImportError:
        return "UNKNOWN (lantern core not importable)"


def _protocol_info() -> dict:
    try:
        from lantern.protocol import PROTOCOL_VERSION

        return {"lantern_protocol_version": PROTOCOL_VERSION, "status": "READ_FROM_lantern.protocol"}
    except ImportError:
        return {"lantern_protocol_version": "UNKNOWN", "status": "lantern.protocol not importable"}


@dataclass(frozen=True)
class TransferManifest:
    node_id: str
    public_key_hex: Optional[str]
    identity_status: str
    lantern_version: str
    harness_version: str
    protocol_version: str
    reasoning_engine_provider: Optional[str]
    reasoning_engine_api_key_env: Optional[str]
    state_summary: dict
    witness_integrity: dict
    capabilities: tuple
    known_gaps: tuple
    standing_operator_boundaries: tuple
    reauthorization_required: tuple
    harness_commit: str
    lantern_core_commit: str
    python_version: str
    platform_summary: str
    notes: tuple = field(default_factory=tuple)

    def to_dict(self) -> dict:
        return {
            "identity": {
                "node_id": self.node_id,
                "public_key": self.public_key_hex,
                "status": self.identity_status,
            },
            "protocol": {
                "lantern_version": self.lantern_version,
                "harness_version": self.harness_version,
                "lantern_protocol_version": self.protocol_version,
            },
            "configuration": {
                "reasoning_engine_provider": self.reasoning_engine_provider,
                "reasoning_engine_api_key_env": self.reasoning_engine_api_key_env,
                "note": "env var NAME only, never the key value -- see lantern_harness.config",
            },
            "state_summary": self.state_summary,
            "witness_integrity": self.witness_integrity,
            "capabilities": list(self.capabilities),
            "known_gaps": list(self.known_gaps),
            "standing_operator_boundaries_not_transferred": list(self.standing_operator_boundaries),
            "reauthorization_required": list(self.reauthorization_required),
            "provenance": {
                "harness_commit": self.harness_commit,
                "lantern_core_commit": self.lantern_core_commit,
                "python_version": self.python_version,
                "platform": self.platform_summary,
            },
            "notes": list(self.notes),
        }

    def format(self) -> str:
        lines = ["TRANSFER MANIFEST", "=================="]
        lines.append(f"node_id: {self.node_id}")
        lines.append(f"public_key: {self.public_key_hex}")
        lines.append(f"identity_status: {self.identity_status}")
        lines.append("")
        lines.append(f"lantern_version: {self.lantern_version}")
        lines.append(f"harness_version: {self.harness_version}")
        lines.append(f"lantern_protocol_version: {self.protocol_version}")
        lines.append("")
        lines.append(f"reasoning_engine: provider={self.reasoning_engine_provider}, api_key_env={self.reasoning_engine_api_key_env}")
        lines.append("")
        lines.append("STATE SUMMARY:")
        for key, value in self.state_summary.items():
            lines.append(f"  {key}: {value}")
        lines.append("")
        lines.append(f"witness_integrity: {self.witness_integrity.get('status')}")
        lines.append("")
        lines.append("CAPABILITIES (what this instance can actually do):")
        for item in self.capabilities:
            lines.append(f"  - {item}")
        lines.append("")
        lines.append("KNOWN GAPS (what it cannot do):")
        for item in self.known_gaps:
            lines.append(f"  - {item}")
        lines.append("")
        lines.append("DOES NOT TRANSFER -- receiving operator must decide fresh:")
        for item in self.reauthorization_required:
            lines.append(f"  - {item}")
        lines.append("")
        lines.append("PROVENANCE:")
        lines.append(f"  harness_commit: {self.harness_commit}")
        lines.append(f"  lantern_core_commit: {self.lantern_core_commit}")
        lines.append(f"  python_version: {self.python_version}")
        lines.append(f"  platform: {self.platform_summary}")
        if self.notes:
            lines.append("")
            lines.append("NOTES:")
            for note in self.notes:
                lines.append(f"  - {note}")
        return "\n".join(lines)


def build_manifest(bridge: LanternBridge, engine=None, harness_root: Optional[Path] = None) -> TransferManifest:
    """Reads real, current state only. Never infers state it has not
    actually observed this call. Never includes a private key, API key
    value, or any other credential."""
    identity = bridge.identity_status()
    status = bridge.status()
    integrity = bridge.witness_integrity()
    protocol = _protocol_info()

    notes = []
    try:
        branches = bridge.branches()
        branch_count = len(branches) if branches is not None else 0
    except NotImplementedError:
        branches = None
        branch_count = "N/A (Lantern core has no branch concept; harness spine.BranchStore is in-process only, not part of persisted state)"
        notes.append("branch_count is N/A because lantern_harness.spine.BranchStore does not persist across process restarts in this version")

    state_summary = {
        "step": status.get("step"),
        "observations": status.get("observations"),
        "evidence": status.get("evidence"),
        "contradictions": status.get("contradictions"),
        "chronicle_attached": status.get("chronicle"),
        "branches_in_process": branch_count,
    }

    engine_provider = None
    engine_key_env = None
    if engine is not None:
        described = engine.describe()
        engine_provider = described.get("provider")
        engine_key_env = getattr(engine, "api_key_env", None)

    root = harness_root or Path(__file__).resolve().parent.parent

    return TransferManifest(
        node_id=bridge.node_id,
        public_key_hex=identity.get("public_key"),
        identity_status=identity.get("status", "UNKNOWN"),
        lantern_version=lantern_version(),
        harness_version=HARNESS_VERSION,
        protocol_version=protocol["lantern_protocol_version"],
        reasoning_engine_provider=engine_provider,
        reasoning_engine_api_key_env=engine_key_env,
        state_summary=state_summary,
        witness_integrity=integrity,
        capabilities=KNOWN_CAPABILITIES,
        known_gaps=KNOWN_GAPS,
        standing_operator_boundaries=STANDING_OPERATOR_BOUNDARIES,
        reauthorization_required=REAUTHORIZATION_REQUIRED,
        harness_commit=_git_commit(root),
        lantern_core_commit=_lantern_core_commit(),
        python_version=platform.python_version(),
        platform_summary=platform.platform(),
        notes=tuple(notes),
    )
