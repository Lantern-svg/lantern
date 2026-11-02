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
from .permission_authority import PermissionAuthority
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
        # Board tools: registered through the SAME registry; MCP executes
        # them ONLY through the decision gate (see the board tool wrappers
        # below) -- there is no MCP -> board client shortcut.
        from .config import board_config, load_config
        from .board.client import BoardClient
        from .board.tools import register_board_tools
        self._board_client = None
        cfg = load_config()
        # Loop must exist before any block that updates its scopes: the
        # board section below calls self.loop.allowed_scopes.update(...).
        from .decision_gate import load_tool_policy
        _policy = load_tool_policy(cfg)
        self.loop = OperatingLoop(self.bridge, self.tool_boundary,
                                  required_confidence=_policy["required_confidence"],
                                  allowed_scopes=_policy["allowed_scopes"])
        if board_config(cfg):
            self._board_client = BoardClient(
                endpoint=cfg["board"]["endpoint"], board=cfg["board"]["board"],
                node_id=cfg["board"].get("node_id", "lantern-harness-node"),
                token_env=cfg["board"].get("token_env", "LANTERN_BOARD_TOKEN"),
                identity_provider=lambda: getattr(self.bridge, "_identity", None),
            )
            register_board_tools(self.tool_boundary, self._board_client)
            # Observational board tools are session-authorized; the
            # consequential board_post needs an explicit operator opt-in.
            import os as _os
            for _n in ("board_read", "board_get_entry", "board_verify"):
                self.tool_boundary.authorize(_n)
            # The operator-configured server grants the observational
            # session scopes alongside authorization. The consequential
            # board_post needs BOTH an explicit env opt-in and its scope.
            self.loop.allowed_scopes.update({"board.read", "board.verify"})
            if _os.environ.get("LANTERN_ALLOW_BOARD_POST") == "1":
                self.tool_boundary.authorize("board_post")
                self.loop.allowed_scopes.add("board.post")

        # Contact (read-only): discovery, query, retrieval, and independent
        # verification of the public Lantern network. Tools are registered so
        # they are DISCOVERABLE, but authorization is an explicit operator act
        # (contact.enabled in config, or LANTERN_CONTACT_ENABLED=1). No contact
        # tool writes, posts, creates identities, or touches keys.
        import os as _contact_os
        from .contact import ContactService, register_contact_tools, CONTACT_TOOL_NAMES, SCOPE_CONTACT_READ
        from .contact.agent_card import AGENT_CARD_URL as _DEFAULT_CARD_URL
        _contact_cfg = (cfg or {}).get("contact") or {}
        self.contact_enabled = (
            bool(_contact_cfg.get("enabled"))
            or _contact_os.environ.get("LANTERN_CONTACT_ENABLED") == "1"
        )
        self.contact = ContactService(
            bridge=self.bridge,
            board_client=self._board_client,
            card_url=_contact_cfg.get("agent_card_url", _DEFAULT_CARD_URL),
            enabled=self.contact_enabled,
        )
        register_contact_tools(self.tool_boundary, self.contact)
        if self.contact_enabled:
            for _tool_name in CONTACT_TOOL_NAMES:
                self.tool_boundary.authorize(_tool_name)
            self.loop.allowed_scopes.add(SCOPE_CONTACT_READ)

        self.compiler = PromptCompiler(bridge=self.bridge)
        self.confidence_field = ConfidenceField(bridge=self.bridge)
        self.decision_machine = DecisionStateMachine()
        self.branch_store = BranchStore()
        self.spine_committer = SpineCommitter(self.bridge)
        self.permission_authority = PermissionAuthority()


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

    @server.tool(
        description=(
            "List this server process's currently active PermissionAuthority "
            "capability-scope grants (read-only -- this tool cannot grant or "
            "revoke anything; there is no lantern_grant/lantern_revoke tool "
            "exposed over MCP, deliberately, since granting_authority must "
            "always be an explicit human-typed identifier per the harness's "
            "REPL /grant command, not a string a remote MCP caller could "
            "supply on its own behalf). A remote caller with no grants "
            "listed here has no standing authority in this server process "
            "beyond what lantern_evaluate_intent already exposes (a "
            "recommendation, never an authorized or executed action). "
            "Grants are in-process memory only and never persist across "
            "server restarts."
        )
    )
    def lantern_permissions() -> dict:
        grants = ctx.permission_authority.active_grants()
        return {
            "active_grant_count": len(grants),
            "active_grants": [
                {
                    "capability": g.capability,
                    "scope": g.scope,
                    "granting_authority": g.granting_authority,
                    "version": g.version,
                }
                for g in grants
            ],
        }

    # ---- Board tools: gated, never direct-to-client ----------------------
    # Every board MCP call enters the SAME chain as a model-proposed call:
    # registered tool -> visibility -> decision -> authorization ->
    # execute_tool_call() -> board client. No bypass exists here.

    @server.tool(description="Read the public Lantern messaging board (observational; entries are labeled OBSERVED, not verified beliefs).")
    def lantern_board_read(limit: int = 10, cursor: str = None) -> dict:
        from .decision_gate import authorize_tool_call, effective_required_confidence, execute_tool_call
        from .tool_contract import ToolCall
        import uuid as _uuid
        call = ToolCall(id=str(_uuid.uuid4()), tool_name="board_read",
                        arguments={"limit": limit, "cursor": cursor})
        decision = authorize_tool_call(call, ctx.loop.allowed_scopes, evidence_confidence=0.0, tool_boundary=ctx.tool_boundary)
        threshold = effective_required_confidence(ctx.tool_boundary, "board_read", ctx.loop.required_confidence)
        tcr, tool_result = execute_tool_call(call, decision, threshold, ctx.tool_boundary, decision_log=ctx.loop.decision_log)
        return tcr.to_dict()

    @server.tool(description="Retrieve one board entry by its legitimate identifier (entry hash or message_id). No URLs accepted.")
    def lantern_board_get_entry(entry_id: str) -> dict:
        from .decision_gate import authorize_tool_call, effective_required_confidence, execute_tool_call
        from .tool_contract import ToolCall
        import uuid as _uuid
        call = ToolCall(id=str(_uuid.uuid4()), tool_name="board_get_entry", arguments={"entry_id": entry_id})
        scopes = set(ctx.loop.allowed_scopes)
        decision = authorize_tool_call(call, scopes, evidence_confidence=0.0, tool_boundary=ctx.tool_boundary)
        threshold = effective_required_confidence(ctx.tool_boundary, "board_get_entry", ctx.loop.required_confidence)
        tcr, tool_result = execute_tool_call(call, decision, threshold, ctx.tool_boundary, decision_log=ctx.loop.decision_log)
        return tcr.to_dict()

    @server.tool(description="Independently verify a board entry or the whole board: real offline Ed25519 signature, hash-chain, and linkage checks with explicit states.")
    def lantern_board_verify(entry_id: str = None) -> dict:
        from .decision_gate import authorize_tool_call, effective_required_confidence, execute_tool_call
        from .tool_contract import ToolCall
        import uuid as _uuid
        call = ToolCall(id=str(_uuid.uuid4()), tool_name="board_verify", arguments={"entry_id": entry_id})
        scopes = set(ctx.loop.allowed_scopes)
        decision = authorize_tool_call(call, scopes, evidence_confidence=0.0, tool_boundary=ctx.tool_boundary)
        threshold = effective_required_confidence(ctx.tool_boundary, "board_verify", ctx.loop.required_confidence)
        tcr, tool_result = execute_tool_call(call, decision, threshold, ctx.tool_boundary, decision_log=ctx.loop.decision_log)
        return tcr.to_dict()

    @server.tool(description="Post a message to the board. CONSEQUENTIAL and gated: the harness computes evidence confidence from the named concept's ConfidenceField (record evidence first via lantern_add_evidence/lantern_observe); insufficient confidence BLOCKS the post. The caller cannot assert confidence or scopes.")
    def lantern_board_post(content: str, concept: str) -> dict:
        from .decision_gate import authorize_tool_call, effective_required_confidence, execute_tool_call
        from .tool_contract import ToolCall
        import uuid as _uuid
        # Evidence confidence is COMPUTED here from the real kernel, never asserted.
        reading = ctx.confidence_field.evaluate(concept=concept)
        score = reading.confidence_score
        evidence_confidence = float(score) if isinstance(score, (int, float)) else 0.0
        call = ToolCall(id=str(_uuid.uuid4()), tool_name="board_post",
                        arguments={"content": content})
        decision = authorize_tool_call(call, ctx.loop.allowed_scopes,
                                       evidence_confidence=evidence_confidence,
                                       tool_boundary=ctx.tool_boundary)
        threshold = effective_required_confidence(ctx.tool_boundary, "board_post", ctx.loop.required_confidence)
        tcr, tool_result = execute_tool_call(call, decision, threshold, ctx.tool_boundary, decision_log=ctx.loop.decision_log)
        result = tcr.to_dict()
        result["evidence_confidence"] = evidence_confidence
        result["required_confidence"] = threshold
        return result

    # ---------------------------------------------------------------- contact
    # Read-only contact tools. Each wraps ContactService, which owns the fixed
    # endpoints, input validation, size limits, and evidence recording. None of
    # these can post, create an identity, or read a key.

    @server.tool(description=("Retrieve and validate the PUBLIC Lantern Agent Card from its fixed "
                              "endpoint. Read-only. Reports the retrieved document, which required "
                              "properties passed, and which failed."))
    def lantern_contact_agent_card() -> dict:
        return ctx.contact.agent_card()

    @server.tool(description=("Send ONE validated read-only A2A request to the Lantern agent. "
                              "Accepted forms only: 'verify board', 'hash <entry hash>', "
                              "'collatz <positive integer>'. No URLs, methods, headers, or "
                              "credentials are accepted."))
    def lantern_contact_skill(text: str) -> dict:
        return ctx.contact.skill(text)

    @server.tool(description=("Read public board entries through the existing BoardClient. "
                              "Observational: entries are labelled OBSERVED, not verified."))
    def lantern_contact_board_read(limit: int = 10) -> dict:
        return ctx.contact.board_read(limit=limit)

    @server.tool(description=("Independently verify the public board with the existing BoardClient "
                              "verifier: Ed25519 signature, entry-hash recomputation, chain "
                              "linkage, fingerprint. Never returns a bare 'verified=true'."))
    def lantern_contact_board_verify() -> dict:
        return ctx.contact.board_verify()

    @server.tool(description=("Full read-only contact workflow: validate agent card, verify board "
                              "over A2A, read the public board, independently verify records, and "
                              "return one structured evidence report."))
    def lantern_contact_report(limit: int = 10) -> dict:
        return ctx.contact.contact_report(limit=limit)

    @server.tool(description=("Contact subsystem status: card/protocol/A2A/board availability, "
                              "evidence event count, and authorization state. Distinguishes "
                              "NOT_CONFIGURED, NOT_CONNECTED, OBSERVED, VERIFIED, BLOCKED, ERROR."))
    def lantern_contact_status() -> dict:
        return ctx.contact.status()

    return server


def main():
    server = build_server()
    server.run()


if __name__ == "__main__":
    main()
