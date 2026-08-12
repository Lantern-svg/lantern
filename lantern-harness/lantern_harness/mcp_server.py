"""MCP server: exposes Lantern Harness capabilities as MCP tools so any
MCP-compatible agent client (Claude Desktop, Claude Code, or any other
MCP host) can use Lantern directly, without a human copy-pasting through
the REPL.

This is a NEW module. Existing lantern.mcp_client / lantern.mcp_integration
are MCP *client* code (Lantern connecting OUT to other MCP servers). This
module is the reverse direction: Lantern acting AS an MCP server.

Design constraints carried over from the rest of this harness:
- Every tool function here is a thin wrapper around an already-existing,
  already-tested component (LanternBridge, PromptCompiler, ConfidenceField,
  DecisionStateMachine, SelfModel, BranchStore, SpineCommitter,
  OperatingLoop). No new decision/confidence/authorization logic is
  introduced here.
- Tools that could touch the outside world (there are none exposed here
  -- no tool in this module calls RealityBoundary.act or executes an
  arbitrary ToolBoundary-registered tool) are deliberately omitted. This
  server surfaces Lantern's epistemic primitives (observe, evidence,
  confidence, decision, self-model, spine) for other agents to use, not
  a generic remote-code-execution surface.
- Nothing here starts listening on a network port. run_stdio_async() is
  stdio-only, matching how Claude Desktop/Claude Code launch local MCP
  servers as a subprocess -- there is no bind/listen call in this file.
- `lantern_evaluate_intent` composes observe -> compile -> confidence ->
  decide (OperatingLoop.run() with no tool_name/tool_kwargs) for a host
  agent environment (e.g. Odysseus) that owns its own action/execution
  layer. It never accepts a tool_name/tool_kwargs argument from the
  remote caller and therefore can never reach RealityBoundary.act --
  the caller is expected to execute the recommended action in its own
  environment and report the real-world result back via
  lantern_observe, closing the loop without this server ever executing
  anything on the caller's behalf.

To run standalone (for local testing only, not a distribution action):
    python3 -m lantern_harness.mcp_server
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

try:
    from mcp.server.mcpserver import MCPServer
    MCP_SDK_AVAILABLE = True
except ImportError:  # pragma: no cover - exercised only when the mcp extra is absent
    MCPServer = None  # type: ignore[assignment,misc]
    MCP_SDK_AVAILABLE = False

from .bridge import LanternBridge
from .confidence_field import ConfidenceField
from .decision_state_machine import DecisionStateMachine
from .operating_loop import OperatingLoop
from .prompt_compiler import PromptCompiler
from .self_model import SelfModel
from .spine import BranchStore, SpineCommitter
from .transfer_manifest import build_manifest
from .tools.boundary import ToolBoundary


DEFAULT_DATA_DIR = Path(
    os.getenv("LANTERN_MCP_DATA_DIR", str(Path.home() / ".lantern_harness_mcp"))
)


class LanternMCPContext:
    """Holds the one long-lived bridge/loop/branch-store instance a
    server process uses across tool calls. Not a new epistemic
    component -- just the wiring a stateful MCP server needs."""

    def __init__(self, data_dir: Path = DEFAULT_DATA_DIR):
        self.bridge = LanternBridge(data_dir=data_dir)
        self.bridge.ensure_identity()
        self.bridge.startup()
        self.tool_boundary = ToolBoundary()
        self.compiler = PromptCompiler(bridge=self.bridge)
        self.confidence_field = ConfidenceField(bridge=self.bridge)
        self.decision_machine = DecisionStateMachine()
        self.branch_store = BranchStore()
        self.spine_committer = SpineCommitter(self.bridge)
        self.loop = OperatingLoop(self.bridge, self.tool_boundary)


def build_server(context: Optional[LanternMCPContext] = None) -> "MCPServer":
    if not MCP_SDK_AVAILABLE:
        raise RuntimeError(
            "the 'mcp' package is not installed. Install it with "
            "`pip install lantern-harness[mcp]` to run Lantern as an MCP server."
        )
    ctx = context or LanternMCPContext()
    server = MCPServer(
        name="lantern-harness",
        version="0.2.0",
        description=(
            "Auditable evidence/belief tools from the Lantern harness: "
            "observation, evidence linkage, confidence reading, decision "
            "recommendation, self-model, and exploratory branches. Never "
            "authorizes or executes external actions on its own."
        ),
    )

    @server.tool(description="Record a real Observation in the Lantern EvidenceKernel.")
    def lantern_observe(content: str, source: str, reliability: float = 1.0) -> dict:
        obs = ctx.bridge.observe(content, source=source, reliability=reliability)
        return {"observation_id": obs.id, "content": obs.content, "source": obs.source}

    @server.tool(description="Link an existing Observation as Evidence for a concept.")
    def lantern_add_evidence(concept: str, observation_id: str, weight: float = 1.0, sign: int = 1) -> dict:
        ctx.bridge.add_evidence(concept, observation_id, weight=weight, sign=sign)
        return {"concept": concept, "observation_id": observation_id, "weight": weight, "sign": sign}

    @server.tool(description="Compute a real, read-only Confidence Field reading for a concept. Never authorizes action.")
    def lantern_confidence(concept: str) -> dict:
        reading = ctx.confidence_field.evaluate(concept=concept)
        return reading.to_dict()

    @server.tool(description="Recommend (never authorize) a Decision State for a concept, based on its Confidence Field reading.")
    def lantern_decide(concept: str) -> dict:
        reading = ctx.confidence_field.evaluate(concept=concept)
        decision = ctx.decision_machine.recommend(reading)
        return decision.to_dict()

    @server.tool(description="Compile an ordinary request into a structured investigation prompt. Never fabricates missing information.")
    def lantern_compile(request: str, concept: Optional[str] = None) -> dict:
        compiled = ctx.compiler.compile(request, concept=concept)
        return compiled.to_dict()

    @server.tool(description="Report Lantern Harness's bounded self-model: what it knows, infers, can/cannot do, is authorized to do, and what requires operator action.")
    def lantern_self_model() -> dict:
        return SelfModel(ctx.bridge, ctx.tool_boundary).describe().to_dict()

    @server.tool(description="Open a new exploratory Branch. Branches never auto-commit to the Spine.")
    def lantern_branch_open(concept: str, hypothesis: str) -> dict:
        branch = ctx.branch_store.open_branch(concept=concept, hypothesis=hypothesis)
        return branch.to_dict()

    @server.tool(description="List all currently committed Spine entries, reconstructed from the real Chronicle.")
    def lantern_spine_read() -> dict:
        entries = ctx.spine_committer.read_spine()
        return {"entries": [e.to_dict() for e in entries]}

    @server.tool(description="Report real Chronicle integrity status (hash-chain verification). VALID does not mean claims are true, only that the record has not been silently altered.")
    def lantern_witness_integrity() -> dict:
        return ctx.bridge.witness_integrity()

    @server.tool(
        description=(
            "Run the read-only portion of Lantern's OperatingLoop for a host "
            "agent environment (observe -> compile -> confidence -> decide). "
            "Never accepts a tool name and never executes or authorizes any "
            "action -- the calling agent environment (e.g. Odysseus) owns "
            "its own action/execution layer and should call this before "
            "acting, then report the real result back via lantern_observe."
        )
    )
    def lantern_evaluate_intent(
        intent: str,
        concept: Optional[str] = None,
        source: str = "external-agent",
        reliability: float = 1.0,
    ) -> dict:
        result = ctx.loop.run(
            intent,
            concept=concept,
            source=source,
            reliability=reliability,
        )
        return result.to_dict()

    @server.tool(
        description=(
            "Report a Transfer Manifest describing this Lantern instance: "
            "identity (public key only), protocol/harness version, real "
            "state counts, real witness integrity status, capabilities, "
            "known gaps, and what a receiving operator must explicitly "
            "re-authorize (credentials, network exposure, MCP host "
            "registration, paid capabilities). Never includes a private "
            "key, API key value, or any other credential. Does not by "
            "itself transfer anything -- it only describes the instance."
        )
    )
    def lantern_transfer_manifest() -> dict:
        return build_manifest(ctx.bridge).to_dict()

    return server


def main():
    server = build_server()
    server.run()


if __name__ == "__main__":
    main()
