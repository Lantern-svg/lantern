# lantern-harness Release Notes

Status document, like `RELEASE.md` in `lantern-babel-codex-bridge`.
Only records changes that actually happened and were actually tested.

## 0.3.0 (in progress -- not yet tagged/released)

Lantern x Odysseus integration + transfer readiness. Built and tested
this session on top of 0.2.0. `harness_version` in `harness_status.py`
has not been bumped for this yet -- these changes are additive and not
yet cut as a release.

**New tools on `mcp_server.py`** (now 11 total, up from 9):
- `lantern_evaluate_intent` -- runs the read-only portion of
  `OperatingLoop` (observe -> compile -> confidence -> decide) for a
  host agent environment that owns its own action/execution layer
  (e.g. Odysseus). Has no `tool_name`/`tool_kwargs` parameter in its
  registered MCP schema at all -- not merely defaulted to `None` --
  so it is structurally incapable of reaching `RealityBoundary.act`.
  See `ODYSSEUS_INTEGRATION.md`.
- `lantern_transfer_manifest` -- reports a `TransferManifest`
  (`lantern_harness/transfer_manifest.py`, new module): identity
  (public key only), `lantern.protocol.PROTOCOL_VERSION`,
  `lantern_version`/`harness_version`, real state counts, real
  `witness_integrity` status, capabilities/gaps reused verbatim from
  `SelfModel` (not duplicated), real provenance (git commit hashes of
  both repos, Python version, platform), and an explicit
  `reauthorization_required` list. Never includes a private key or API
  key value. Read-only; performs no transfer itself.

**New REPL command:** `/transfer`.

**New integration doc:** `ODYSSEUS_INTEGRATION.md` -- real
architecture investigation of `odysseus-dev/odysseus`, confirmed
AGPL-3.0-or-later license (Lantern is MIT), an engineering (not legal)
compatibility analysis for the external-MCP-server adapter pattern,
and a genuine boundary-level test using Odysseus's own real
`McpManager._connect_stdio`/`_do_call` code (copied verbatim,
never committed) against a real `mcp==1.29.0` client talking to a real
`lantern_harness.mcp_server` subprocess. States plainly what remains
`NOT_TESTED` (a full live Odysseus instance) and why (no Docker in
this environment; running one natively would mean starting a new
network-listening service, held for explicit operator authorization).

**New README section:** "Transfer an instance" -- what travels with a
copied `data_dir` (Chronicle, node identity incl. private key) versus
what must be decided fresh by the receiving operator (credentials,
network exposure, MCP host registration, paid capabilities, tool
authorization).

**Tests:** 149 -> 162 passing (13 new: 11 in `test_transfer_manifest.py`,
1 new assertion in `test_mcp_server.py`, plus 1 in
`test_harness_status.py`; `test_mcp_server_live_stdio.py`'s tool-list
test updated to expect all 11 current tools instead of the original 9).
Core Lantern suite re-verified 698/698 passing; fresh independent
install re-verified in a disposable venv (console scripts
`lantern-harness` and `lantern-harness-mcp` both present and working).

## 0.2.0

Built and tested this session, on top of the 0.1.0 foundation (Prompt
Compiler, Perspective Differential Engine, Confidence Field, Decision
State Machine, conversation loop, tool boundary, persistent Lantern
integration).

**New modules:**
- `spine.py` -- `Branch`/`SpineEntry`/`BranchStore`/`SpineCommitter`.
  Exploratory branches stay uncommitted until an explicit external
  `commit(..., authorized=True, authorized_by=...)` call; a branch
  cannot commit itself and confidence alone never authorizes a commit.
- `self_model.py` -- `SelfModel.describe()` reports what the harness
  knows/infers/can do/cannot do/is authorized to do/needs operator
  action for, read-only, with no method on the class capable of
  self-authorizing anything (enforced by inspecting the public method
  surface directly, not just behavior).
- `reality_boundary.py` -- separates a proposed action from its
  authorization from its actual execution from its recorded result; a
  simulated action is always labeled `SIMULATED_BY_ASSISTANT` and is
  never reported as a real result.
- `operating_loop.py` -- `OperatingLoop.run()`, the executable
  composition of observe -> compile -> confidence -> decide -> optional
  action -> optional branch. Adds no new decision/confidence/
  authorization logic; missing prerequisites (e.g. no tool_name)
  produce a skip-with-note, never a fabricated step.
- `mcp_server.py` -- exposes 9 Lantern harness tools over the MCP
  stdio protocol so any MCP-compatible agent host can use them
  directly. Verified against a real independent client
  (`tests/test_mcp_server_live_stdio.py`), not just in-process calls.
  Deliberately exposes no external-action tool.

**New REPL commands:** `/self`, `/branch`, `/spine`, `/run`.

**Packaging:** added `pyproject.toml` -- `lantern-harness` is now a
real `pip install`-able package (verified in a fresh, disposable venv,
including the `lantern-harness` and `lantern-harness-mcp` console
scripts and the full test suite running from that fresh install).
New optional extra: `mcp`.

**Docs:** `README.md` and `prompts/system.md` rewritten to describe
these components accurately (the prior `prompts/system.md` still told
the reasoning engine all six new components "do not exist" -- fixed,
since that file is threaded into every conversation as the first
system message).

**Tests:** 89 -> 147 passing (58 new tests across
`test_spine.py`, `test_reality_boundary.py`, `test_self_model.py`,
`test_operating_loop.py`, `test_mcp_server.py`,
`test_mcp_server_live_stdio.py`, plus additions to
`test_conversation_loop.py` and `test_harness_status.py`).

## 0.1.0

Initial harness release: `LanternBridge` adapter, provider-agnostic
reasoning engine abstraction (Ollama/OpenAI/Anthropic/Google, none
mandatory), `ToolBoundary`, conversation loop, `prompts/system.md`
wiring, Prompt Compiler, Perspective Differential Engine, Confidence
Field, Decision State Machine. 89 tests passing.
