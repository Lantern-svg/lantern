# Lantern × Odysseus Integration

Status document. Records what was actually investigated, what was
actually built, and what was actually tested against real code from
both projects. Nothing here is aspirational.

## 1. What Odysseus actually is

[odysseus-dev/odysseus](https://github.com/odysseus-dev/odysseus)
(originally forked from `pewdiepie-archdaemon/odysseus`) is a
**self-hosted AI workspace**: a single FastAPI application (`app.py`)
with chat/agents, tool execution (shell, filesystem, subprocess), MCP
client integration, email, calendar, notes, deep research, and model
serving. It is designed to run as one process with an admin console
model of trust (see its own `THREAT_MODEL.md`: "treat it like an admin
console"). Investigated directly from the real `dev` branch source
(`specs/architecture-runtime-inventory.md`, `src/mcp_manager.py`,
`routes/mcp/mcp_routes.py`, `src/tool_policy.py`,
`src/tool_security.py`, `THREAT_MODEL.md`) -- not from marketing copy
or assumptions.

**License: AGPL-3.0-or-later.** Confirmed by reading the actual
`LICENSE` file in the repo. This matters -- see §4.

## 2. Odysseus's real agent/MCP/tool/memory interfaces

- **Agent tool execution**: `src/tool_implementations.py` (4,032
  lines, 33 `do_*` functions), gated by `src/tool_security.py` and
  `src/tool_policy.py`. Non-admin users are blocked from shell,
  filesystem, email, and **all** `mcp__`-prefixed tools by default
  (`THREAT_MODEL.md` role table; `tool_security.py` line ~234:
  `tool_name.startswith("mcp__")` is blocked for non-admins
  unconditionally).
- **MCP client**: `src/mcp_manager.py`'s `McpManager` class connects
  to external MCP servers over stdio, SSE, or Streamable HTTP
  (`_connect_stdio`/`_connect_sse`/`_connect_http`). Stdio uses the
  real MCP SDK: `mcp.client.stdio.stdio_client` +
  `mcp.ClientSession`, `session.initialize()`, `session.list_tools()`,
  `session.call_tool(name, arguments)`. This is the **standard MCP
  protocol** -- nothing Odysseus-specific about the wire format.
- **MCP server registration**: `routes/mcp/mcp_routes.py`'s
  `POST /api/mcp/servers` (admin-only, `require_admin`) accepts
  `name`, `transport` (`stdio`/`sse`/`http`), `command`, `args`, `env`,
  `url`. A registered stdio server is launched as a subprocess and its
  tools become callable as `mcp__{server_id}__{tool_name}`.
- **Memory**: `src/memory.py`, `src/memory_provider.py`,
  `src/memory_vector.py`, `mcp_servers/memory_server.py` -- Odysseus's
  own semantic/vector memory system, unrelated to Lantern's
  EvidenceKernel/Chronicle. Not touched or duplicated by this
  integration.
- **Extension model**: MCP is Odysseus's actual plugin boundary for
  third-party capabilities (its own built-in servers --
  `mcp_servers/email_server.py`, `memory_server.py`, `rag_server.py`,
  `image_gen_server.py` -- are registered the same way as any external
  one, just bundled in-repo).

## 3. Safest integration boundary (what was chosen and why)

**Chosen: register `lantern-harness-mcp` as an external stdio MCP
server in Odysseus.** No Odysseus code changes. No Lantern code
depends on Odysseus. Communication happens over the standard MCP
stdio JSON-RPC protocol between two separate OS processes -- the same
mechanism Odysseus already uses for every other external MCP server
it supports (arbitrary third-party tools of any license).

Rejected alternatives and why:
- **Embedding/copying Odysseus code into Lantern, or vice versa** --
  explicitly forbidden by the mission brief, and unnecessary: MCP
  already gives a clean process boundary.
- **A REST/webhook adapter instead of MCP** -- would duplicate a
  transport Odysseus already speaks natively; MCP is the interface
  Odysseus was built to consume external capabilities through.
- **Registering Lantern as a "builtin" server inside the Odysseus
  repo** (like `mcp_servers/email_server.py`) -- would require a PR
  into Odysseus and would put Lantern's code inside an AGPL
  repository. Registering it as an *external* server (exactly how
  Odysseus's docs describe adding any third-party MCP server) avoids
  that entirely and requires zero permission from the Odysseus
  maintainers.

## 4. License compatibility (read this before distributing anything)

**This is an engineering analysis of publicly stated license terms,
not legal advice.** If real revenue or a formal redistribution
decision ever depends on this, get it confirmed by counsel before
relying on it.

- Lantern core and Lantern Harness: **MIT** (permissive).
- Odysseus: **AGPL-3.0-or-later** (strong copyleft; its network-use
  clause, GPLv3 §13 as adopted by AGPL, requires that *modified
  versions of the AGPL-covered program itself*, when made available
  to users over a network, offer that program's corresponding source).

**Why this integration does not put Lantern under AGPL obligations:**
Lantern is not a modified version of Odysseus, is not statically or
dynamically linked into the Odysseus process, is not distributed
inside the Odysseus repository, and is not required for Odysseus to
run. It is an independent program in a separate repository that
Odysseus's own admin explicitly opts to launch as a subprocess and
talk to over the standard MCP wire protocol -- structurally identical
to Odysseus talking to any other third-party MCP server (which can be
and are proprietary/closed-source; MCP is a public protocol, not an
Odysseus-owned interface). This is the same boundary FSF guidance
describes as "mere aggregation" / separate-program interoperation via
a defined protocol, not "one combined program."

**What would change this analysis** (none of these are true today,
named so they aren't silently assumed later):
- Copying Odysseus source code into the Lantern repository (not done;
  the only Odysseus code touched this session was read directly from
  GitHub for inspection and, for one verification script, retyped
  verbatim into a disposable `/tmp` test file that was deleted after
  the test ran -- never committed to either repo).
- Statically bundling Lantern inside the Odysseus repo as a
  `mcp_servers/lantern_server.py`-style builtin (not done; Lantern
  stays in its own MIT-licensed repo, registered as an *external*
  server).
- Distributing a bundle that ships both projects together as one
  installable unit in a way that blurs the "separate program" line.

**PUBLISH_READY for this integration as documented (adapter pattern,
separate repos, MCP stdio boundary): YES, by this analysis.**
**PUBLISH_READY for any tighter coupling (embedding, bundling,
forking Odysseus): NOT EVALUATED -- would need a fresh license review
before doing so.**

## 5. What was actually tested (real, not simulated)

No local Odysseus instance could be run this session (no Docker
available in this environment; running the full Odysseus FastAPI app
natively would mean installing and starting a new network-listening
service, which this session holds for explicit operator authorization,
same as the x402 service -- see `REVENUE.md`). Instead of skipping
verification or claiming success without a real test, the actual
integration *boundary* was tested directly:

1. **Real dependency-version match check**: Odysseus's
   `requirements.txt` pins `mcp<2` (comment: "Built-in servers use the
   v1 low-level Server decorator API"). Lantern's harness MCP server
   (`lantern_harness/mcp_server.py`) was built and tested against
   `mcp==2.0.0`. This is a genuine cross-version question, not
   assumed away.
2. **Real client, real server, real subprocess, no mocks**: installed
   the actual `mcp==1.29.0` package (the version Odysseus's
   `requirements.txt` resolves to) into a disposable venv. Copied
   Odysseus's own `McpManager._connect_stdio` and `_do_call` methods
   **verbatim** from the real `dev` branch source (not reinterpreted)
   into a throwaway test script, and ran that exact logic against a
   real `lantern_harness.mcp_server` subprocess.
3. **Result**: connected successfully, listed all 10 real tools,
   called `lantern_observe` (recorded a real observation, real UUID
   returned) and `lantern_decide` (returned real
   `authorization_status: "NOT_EVALUATED"`) through the v1 client
   talking to the v2 server -- MCP's JSON-RPC wire protocol is stable
   across these SDK versions for the operations Odysseus's
   `McpManager` actually uses. Confirmed this is not a coincidence of
   overly-permissive test code by asserting on the real returned
   `observation_id` and `authorization_status` values, not just
   "did it not crash."
4. Re-ran with the new `lantern_evaluate_intent` tool (added this
   session, see §6) using a realistic Odysseus-shaped intent
   ("should Odysseus retry the failed email sync job?") -- produced a
   full, real, non-fabricated `LoopResult` (compiled prompt, confidence
   reading, decision recommendation) with `action_record: null`,
   proving the tool cannot itself trigger an action.
5. Test artifacts (disposable venv, throwaway scripts, temp data dirs)
   were deleted after verification; nothing from this step was
   committed to either repo.

**What was not tested**: the full live Odysseus app (chat UI, agent
loop, `POST /api/mcp/servers` admin form end-to-end, actual tool
dispatch through `McpManager.call_tool`'s `mcp__{server_id}__{name}`
qualified-name routing). This remains **NOT_TESTED** honestly --
distinct from the boundary-level verification above, which is real.
**CAPABILITY_REQUIRED to close this gap**: either Docker (for
`docker compose up`) or a native Python 3.10+ environment able to
install Odysseus's ~50 dependencies, plus explicit operator
authorization to install and run a new local service (same bar as the
x402 service).

## 6. What was built this session

**`lantern_evaluate_intent`**, a new MCP tool on
`lantern_harness.mcp_server` (alongside the 9 existing tools), added
specifically for host agent environments like Odysseus that own their
own action/execution layer and should not, and structurally cannot,
trigger action through Lantern:

- Composes `OperatingLoop.run()` with **no `tool_name` or
  `tool_kwargs` parameter exposed at all** -- not merely defaulted to
  `None` -- the tool's registered MCP schema has no such property
  (verified directly by inspecting `tool.input_schema`, not just
  behavior: `test_lantern_evaluate_intent_has_no_tool_name_parameter`).
  This makes it structurally impossible for this tool to reach
  `RealityBoundary.act`, regardless of what the calling agent passes.
- Runs observe -> compile -> confidence -> decide for real, returning
  a full `LoopResult` (real observation id, real confidence reading,
  real decision recommendation, `action_record: null`, `branch: null`).
- The intended flow for an Odysseus agent turn:
  `ODYSSEUS -> lantern_evaluate_intent -> (Odysseus decides whether/how
  to act, using its own tool_security/tool_policy gating) -> ODYSSEUS
  executes the real action in its own environment -> ODYSSEUS calls
  lantern_observe to record the real-world result back into Lantern's
  Chronicle -> next lantern_evaluate_intent call sees that new
  evidence`. This satisfies the mission's pipeline diagram
  (Evidence/Belief/Contradiction -> Compass/Confidence -> Decision
  State -> Capability Authorization -> ACTION -> real-world result ->
  learning) while keeping the ACTION step correctly owned by Odysseus,
  never by Lantern.

Tests added: `test_lantern_evaluate_intent_runs_the_real_operating_loop`,
`test_lantern_evaluate_intent_has_no_tool_name_parameter`, plus the
existing `test_server_exposes_no_tool_capable_of_external_action`
already covers the new tool name (`evaluate_intent` doesn't match any
forbidden substring, verified). Full harness suite: 149/149 passing
after this addition.

## 7. How to register Lantern with a real Odysseus instance

Once Odysseus is running (native or Docker) and you're logged in as
an admin, register Lantern the same way you'd register any external
MCP server (`Settings -> MCP Servers -> Add Server` in the UI, which
posts to `POST /api/mcp/servers`):

| Field | Value |
|---|---|
| `name` | `lantern-harness` |
| `transport` | `stdio` |
| `command` | absolute path to `.venv/bin/lantern-harness-mcp` (or `.venv/bin/python -m lantern_harness.mcp_server`) |
| `args` | `[]` |
| `env` | `{"LANTERN_MCP_DATA_DIR": "/absolute/path/to/this/node's/lantern/data"}` |

After connecting, Odysseus will list Lantern's 10 tools
(`mcp__lantern-harness__lantern_observe`, `..._evaluate_intent`, etc.)
-- admin-only by default per Odysseus's own `mcp__`-prefix blocking
for non-admins (§2). No Lantern-side change is required to respect
that; it's enforced entirely on Odysseus's side, consistent with
Lantern never assuming authorization it wasn't explicitly given.

## 8. Summary

| Item | Status |
|---|---|
| Odysseus architecture inspected | DONE (real `dev` branch source) |
| License verified | DONE -- AGPL-3.0-or-later |
| Agent/MCP/tool/memory interfaces identified | DONE |
| Safest integration boundary identified | DONE -- external MCP stdio server, adapter pattern |
| License compatibility analysis | DONE (engineering analysis, not legal advice -- see §4) |
| New capability built | `lantern_evaluate_intent` tool, 2 new tests, 149/149 harness suite passing |
| Real boundary-level test (real v1 client, real subprocess, real v2 server) | DONE, passed |
| Full live Odysseus instance test | NOT_TESTED -- blocked on Docker/native install + explicit run authorization |
| Distribution/promotion of this integration | Documented here; no announcement, PR, or outreach to the Odysseus project has occurred |

No code from either project was committed into the other's repository.
No Odysseus service was installed or started. No claim of success is
made beyond what was actually run and asserted on above.
