# lantern-harness Release Notes

Status document, like `RELEASE.md` in `lantern-babel-codex-bridge`.
Only records changes that actually happened and were actually tested.

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
