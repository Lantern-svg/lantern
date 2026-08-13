# Lantern Harness

## What Lantern is

Lantern (`lantern-babel-codex-bridge`) is an auditable evidence/belief
engine and inter-instance exchange protocol. It gives an AI system
persistent, hash-chained evidence tracking, contradiction detection,
cryptographic node identity, and a capability-authorization boundary.
Lantern by itself is a Python **library** — it has no chat interface,
no reasoning engine, and no `main.py`.

## What this harness is

This harness (`lantern-harness`) is the missing human-facing layer: a
small, provider-agnostic conversation loop that connects a reasoning
engine of your choice (Ollama, OpenAI, Anthropic, Google, or a custom
adapter) to Lantern's evidence/identity/memory layer through a thin
`LanternBridge` adapter. It does not duplicate or reimplement any of
Lantern's internals.

A running instance of this harness -- with its own identity, evidence,
and history -- may be personally carried and transferred by one
operator; see [`PEACEMAKER.md`](./PEACEMAKER.md) for what that naming
means and does not mean, and "Transfer an instance" below for the
actual procedure.

## How they relate

```
USER -> LANTERN INTERFACE (this harness) -> REASONING ENGINE -> LANTERN CORE (real lantern package)
```

The harness never asserts model output as verified external fact, and
it never treats reasoning-engine availability as evidence about
Lantern's own state.

## Install

Requires Python >= 3.10. `lantern-harness` is a real, pip-installable
package (`pyproject.toml`) with a console entry point (`lantern-harness`);
this has been verified against a fresh throwaway venv, not just the
development checkout.

```bash
git clone <this-repo>
cd lantern-babel-codex-bridge
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
cd ../lantern-harness
../lantern-babel-codex-bridge/.venv/bin/pip install -e ".[dev]"
../lantern-babel-codex-bridge/.venv/bin/python -m pytest tests/ -q
```

If `lantern` is not importable, `main.py` will report exactly that and
stop — it will not fabricate a working session.

## Try the demo

`examples/demo_operating_loop.py` runs the full operating loop
end-to-end against a real, disposable Lantern node (a fresh temp
directory) -- every line it prints is produced by real code, nothing is
hardcoded:

```bash
../lantern-babel-codex-bridge/.venv/bin/python examples/demo_operating_loop.py
```

It walks through: an ordinary question with no evidence (LOW
confidence), adding two independent agreeing observations (confidence
rises to MEDIUM), opening an exploratory branch, a refused Spine commit
(no authorization) followed by a real authorized commit, and a final
Self-Model report.

## Choose a model

Edit `config/config.json`:

```json
{
  "reasoning_engine": {
    "provider": "ollama",
    "model": "llama3.1",
    "ollama_host": "http://localhost:11434"
  }
}
```

Supported `provider` values: `ollama`, `openai`, `anthropic`, `google`,
or `none` (default — the harness runs with no reasoning engine and
tells you so at every message).

For API providers, set the corresponding environment variable before
running (`OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GOOGLE_API_KEY`). Keys
are read directly from the environment at call time and are never
written to Lantern's Chronicle, evidence, witness ledger, or any file
in this repo.

## Start

```bash
../lantern-babel-codex-bridge/.venv/bin/python main.py
```

## Inspect status

Type `/status` at the `You:` prompt, or run the same check
non-interactively:

```bash
../lantern-babel-codex-bridge/.venv/bin/python -c "
from lantern_harness.bootstrap import bootstrap, format_bootstrap_report
print(format_bootstrap_report(bootstrap()))
"
```

## Commands

`/status` `/memory` `/identity` `/tools` `/branches` `/compile <request>`
`/decide <request>` `/self` `/branch <concept> :: <hypothesis>` `/spine`
`/run <intent>` `/transfer` `/permissions` `/grant <capability> :: <scope> :: <you>`
`/revoke <capability> :: <you>` `/exit`

- `/compile <request>` runs the Prompt Compiler
  (`lantern_harness.prompt_compiler`) and prints a structured
  investigation prompt -- it does not send the request anywhere itself.
  Missing information is marked `NOT_PROVIDED` / `UNKNOWN`, never invented.
- `/decide <request>` computes a real `ConfidenceField` reading and a
  `DecisionStateMachine` recommendation. It recommends; it never
  authorizes or executes.
- `/self` prints a `SelfModel` report: WHAT I KNOW / INFER / DO NOT KNOW
  / CAN DO / CANNOT DO / AM AUTHORIZED TO DO / REQUIRES OPERATOR ACTION.
  It has no method capable of granting itself authority.
- `/branch <concept> :: <hypothesis>` opens a real exploratory `Branch`
  (`lantern_harness.spine.BranchStore`). Branches stay outside committed
  Spine state until an explicit commit succeeds.
- `/spine` lists currently committed Spine entries (reconstructed by
  replaying the real Chronicle). The REPL intentionally cannot commit a
  branch for you -- `SpineCommitter.commit()` requires an explicit
  `authorized=True` passed by a caller outside this module, so a branch
  can never authorize its own commitment and no confidence score alone
  can create one.
- `/run <intent>` executes the full `OperatingLoop`: records a real
  Observation, compiles a structured prompt, computes a Confidence Field
  reading, and gets a Decision State Machine recommendation, in one call.
- `/transfer` prints a `TransferManifest`: identity (public key only),
  protocol/harness version, real state counts, real witness integrity
  status, capabilities, known gaps, and an explicit list of what a
  receiving operator must decide fresh (credentials, network exposure,
  MCP host registration, paid capabilities). It never includes a
  private key or API key value, and it does not itself transfer
  anything -- to actually hand off an instance, copy its `data_dir`
  (see "Transfer an instance" below) and share this manifest's output
  alongside it.
- `/permissions` lists currently active capability-scope grants
  (`lantern_harness.permission_authority.PermissionAuthority`). A fresh
  session always starts with zero grants -- nothing is pre-authorized,
  and grants never travel with a transferred `data_dir` (they live in
  process memory only, on purpose; see "Permissions and alignment"
  below).
- `/grant <capability> :: <scope> :: <your name>` records a new
  capability-scope permission. `granting_authority` (your name/
  identifier) is required and never inferred -- omitting it refuses the
  grant. `<capability>` must be one of the defined categories (see
  `lantern_harness.permission_authority.CAPABILITY_CATEGORIES`);
  external-authority categories (credentials, wallets, payments,
  communications, legal/financial commitments, destructive operations,
  private-data disclosure, authority transfer to another agent) never
  inherit from any other grant, no matter how similar the wording.
- `/revoke <capability> :: <your name>` marks all active grants for
  that capability as revoked.

(`/history`, `/beliefs`, `/evidence`, `/projects` are recognized but
not yet implemented as formatted views in this version — see
`KNOWN_LIMITATIONS` in the harness status report.)

## Configure tools

Tools are registered programmatically via
`lantern_harness.tools.boundary.ToolBoundary` — none are registered by
default. Tool discovery never implies authorization; call
`boundary.authorize(name)` explicitly before a tool can execute.

## Use Lantern from another agent (MCP server)

`lantern_harness.mcp_server` exposes real Lantern harness capabilities
as MCP tools, so any MCP-compatible agent client (Claude Desktop,
Claude Code, or any other MCP host) can call them directly, without a
human relaying through this REPL. This is the reverse direction of
`lantern.mcp_client`/`lantern.mcp_integration` in the core package
(Lantern connecting *out* to other MCP servers) -- this module makes
Lantern *act as* an MCP server.

```bash
../lantern-babel-codex-bridge/.venv/bin/pip install -e ".[mcp]"
../lantern-babel-codex-bridge/.venv/bin/lantern-harness-mcp
```

Exposed tools: `lantern_observe`, `lantern_add_evidence`,
`lantern_confidence`, `lantern_decide`, `lantern_compile`,
`lantern_self_model`, `lantern_branch_open`, `lantern_spine_read`,
`lantern_witness_integrity`, `lantern_evaluate_intent`,
`lantern_transfer_manifest`, `lantern_permissions`. Every tool is a
thin wrapper around an already-tested component -- no new
decision/confidence/authorization logic exists in this module.
Deliberately **not** exposed: anything that would let a remote MCP
client execute an arbitrary `ToolBoundary`-registered tool or
otherwise act on the external world -- this server surfaces Lantern's
epistemic primitives only
(`test_server_exposes_no_tool_capable_of_external_action` enforces
this). `lantern_permissions` is read-only (lists this process's active
`PermissionAuthority` grants); there is deliberately no
`lantern_grant`/`lantern_revoke` MCP tool, since `granting_authority`
must always be an explicit human-typed identifier (the REPL `/grant`
pattern), never a string a remote MCP caller could supply on its own
behalf (`test_server_exposes_no_grant_or_revoke_tool_over_mcp`
enforces this). It runs over stdio only (matches how MCP hosts launch
local servers as a subprocess); nothing in this module binds a network
port.

Verified end-to-end against a real independent MCP client (Lantern
core's own `StdioMCPClient`, launched as a genuine child process, not
called as a Python object in-process) — see
`tests/test_mcp_server_live_stdio.py`.

To connect this server to an MCP host that reads a JSON config (e.g.
Claude Desktop's `claude_desktop_config.json`, or Claude Code's
`.mcp.json`), add an entry like:

```json
{
  "mcpServers": {
    "lantern-harness": {
      "command": "/absolute/path/to/lantern-babel-codex-bridge/.venv/bin/lantern-harness-mcp",
      "env": {
        "LANTERN_MCP_DATA_DIR": "/absolute/path/to/wherever/you/want/this/node's/data"
      }
    }
  }
}
```

Use absolute paths — MCP hosts launch this as a subprocess and do not
inherit your shell's working directory or `PATH` by default.

**Integrating with an agent environment that owns its own action
layer** (e.g. [Odysseus](https://github.com/odysseus-dev/odysseus)):
use `lantern_evaluate_intent` instead of the individual
observe/confidence/decide tools. It runs the full read-only
observe→compile→confidence→decide pipeline in one call and has no
`tool_name`/`tool_kwargs` parameter at all, so it cannot trigger an
action — the calling environment executes the recommended action
itself (under its own authorization/tool-security gating) and reports
the real result back via `lantern_observe`. See
`ODYSSEUS_INTEGRATION.md` for a concrete, tested example: architecture
investigation, license-compatibility analysis (Odysseus is
AGPL-3.0-or-later; Lantern is MIT), and a real boundary-level test
against Odysseus's actual (unmodified) MCP client code and its pinned
`mcp<2` SDK version.

## Create a project

`projects/` is a plain workspace directory for your own files. It is
not a replacement for Lantern's evidence history — it holds no
epistemic state of its own.

## Understand evidence / validation

Decision pipeline:

Evidence -> Confidence Field -> Decision State Machine -> Capability Authorization -> Action Boundary

The Confidence Field and Decision State Machine are real, testable layers in this harness. They recommend; they do not authorize or execute.


- **Observation** -> **Evidence** -> **belief()** is real and
  implemented (`lantern.core.EvidenceKernel`), reachable through
  `LanternBridge.observe()` / `.add_evidence()` / `.belief()`.
- **Witness Integrity** reports the real Chronicle hash-chain
  verification (`Chronicle.verify()`). `VALID` means the recorded
  sequence has not been silently altered — it does **not** mean the
  underlying claims are true.
- **Branches / Spine / Commitment** (`lantern_harness.spine`) is a real,
  tested layer built on Lantern's Chronicle. `BranchStore` manages
  exploratory `Branch` objects (concept, hypothesis, linked
  observations/evidence, OPEN/COMMITTED/ABANDONED status).
  `SpineCommitter.commit()` enforces every invariant the mission
  requires: refuses unless `authorized=True` is explicitly passed by an
  external caller (a branch can never commit itself, and no confidence
  score alone creates commitment), refuses if the branch is not OPEN,
  refuses on Chronicle integrity failure, and refuses on unresolved
  contradictions for the branch's concept unless the caller explicitly
  acknowledges them. Committed entries are immutable (no re-commit, no
  abandon after commit) and are reconstructed by replaying the real
  Chronicle (`SpineCommitter.read_spine()`), the same pattern Lantern
  uses for Scars. Abandoned or never-committed branches can be converted
  into real Scars (`spine.branch_to_scar`) so failed hypotheses are
  preserved as learning artifacts rather than discarded. **Lantern v0.84
  core itself still has no branch/spine concept** -- see
  `LanternBridge.branches()`, which still honestly raises
  `NotImplementedError`.
- **Self-Model** (`lantern_harness.self_model.SelfModel`) is a real,
  read-only reporting layer. `describe()` returns the seven sections the
  mission specifies (WHAT I KNOW / INFER / DO NOT KNOW / CAN DO / CANNOT
  DO / AM AUTHORIZED TO DO / REQUIRES OPERATOR ACTION), sourced from the
  real bridge/Chronicle/ToolBoundary state. It exposes no method capable
  of granting itself or anything else authorization -- enforced by
  `test_self_model_cannot_self_authorize`, which asserts the class has
  no `authorize`/`grant`/`approve`/`enable`/`unlock` method at all.
- **Reality Boundary** (`lantern_harness.reality_boundary.RealityBoundary`)
  separates INTENT -> DECISION -> AUTHORIZATION -> ACTION -> RESULT.
  `propose()` never touches the external world. `act()` only executes
  through an already-authorized `ToolBoundary` entry. `simulate()` can
  never report `SUCCESS` -- its result is always `SIMULATED_ONLY` and
  its notes are always prefixed `SIMULATED_BY_ASSISTANT:`. An
  `ActionRecord.is_real_success()` requires both
  `execution_mode == REAL` and `result_status == SUCCESS`; a simulated
  result can never read as real by construction, not just by convention.
- **Operating Loop** (`lantern_harness.operating_loop.OperatingLoop`)
  composes the above into one callable pipeline (Observation ->
  PromptCompiler -> ConfidenceField -> DecisionStateMachine ->
  RealityBoundary -> optional Branch), matching the architecture in the
  mission brief. It adds no new decision, confidence, or authorization
  logic of its own -- it only calls the existing, separately-tested
  components in sequence. Reachable from the REPL via `/run <intent>`.
- A full **Perspective Mesh** (merge/vote/consensus across perspectives)
  still does not exist -- only the variance-only
  `PerspectiveDifferentialEngine` described below.
- **Confidence Field** (`lantern_harness.confidence_field.ConfidenceField`)
  is a verified read-only layer over Lantern evidence, contradictions,
  integrity, scars, and optional perspective divergence. It produces a
  confidence band plus reasons/blockers/missing information.
- **Decision State Machine**
  (`lantern_harness.decision_state_machine.DecisionStateMachine`) is a
  verified recommendation layer over the Confidence Field. It maps
  confidence into a state and action recommendation, but it does not
  authorize or execute anything.
- **Prompt Compiler** (`lantern_harness.prompt_compiler.PromptCompiler`)
  is newly added in this harness (not part of Lantern v0.84 core). It
  turns a request into a structured prompt, scaling between a light and
  a heavyweight template, and reads real Evidence/Contradiction records
  through `LanternBridge` when a `concept` is supplied -- it never
  invents evidence, assumptions, or contradictions it wasn't given.
- **Perspective Differential Engine**
  (`lantern_harness.perspective_differential.PerspectiveDifferentialEngine`)
  is also newly added. Given two or more independently-produced
  `Perspective` records, it computes variance across confidence,
  evidence, assumption bias, and novelty, and reports which dimension
  diverges most. It is **not** the full Perspective Mesh / Decision
  State Machine from the architecture roadmap -- it does not merge,
  vote, or select a winner. Variance is a diagnostic signal, not proof.

## Transfer an instance

A Lantern Harness instance is more than a package name -- it has real
identity, real accumulated evidence, and a real integrity chain. To
hand an instance to another operator or agent:

1. Run `/transfer` (or call the `lantern_transfer_manifest` MCP tool)
   and save its output. This is the receiving side's answer to "what
   am I being given?" -- identity, protocol version, real state
   counts, real witness integrity status, capabilities, known gaps.
2. Copy the instance's `data_dir` (default `memory/lantern_data/`) to
   the new location. This directory holds the real Chronicle
   (`chronicle.jsonl`) and the real node identity (`identity/`,
   including the private key file, mode `0600`). Copy it the same way
   you'd copy any credential-bearing directory -- outside version
   control, over a channel you trust.
3. On the receiving side, re-run `/transfer` (or `lantern_witness_integrity`)
   against the copied `data_dir` and confirm `witness_integrity: VALID`
   before trusting the transferred state. A copy that fails integrity
   verification should not be adopted silently.

**What does NOT travel with the data_dir, and must be decided fresh by
the receiving operator** (this is exactly the `TransferManifest`'s
`reauthorization_required` list, not a separate policy):

- reasoning engine credentials (API keys are never stored in `data_dir`
  or in any Chronicle/evidence record -- see `lantern_harness.config`)
- any x402 payment/wallet credentials
- authorization to push commits, publish packages, or contact external
  parties on the new operator's behalf
- registration with any MCP host (e.g. adding this instance to an
  Odysseus deployment) -- the private key proves *which* instance this
  is, it does not imply the new operator has decided to expose it
  anywhere
- authorization for any `ToolBoundary`-registered tool -- `ToolBoundary`
  state itself is in-process only and does not persist in `data_dir`,
  so a receiving process starts with zero tools authorized regardless
  of what the sending instance had authorized
- any `PermissionAuthority` capability-scope grant (see "Permissions
  and alignment" below) -- like `ToolBoundary`, its state is in-process
  memory only, so a receiving operator always starts with zero grants,
  never the sending operator's

The identity's public key travels (it is not a secret and is exactly
what lets a third party verify this is the *same* instance across a
transfer); the private key travels only because it lives in the copied
`data_dir` -- treat that copy step as a credential handoff, not a
routine file copy.

## Permissions and alignment

A running instance does not require the operator to approve every
ordinary action one at a time. The operator may grant standing
authority over a defined **capability category** -- for example,
"modify files inside this project directory" -- and the instance may
then act within that scope without asking again for each individual
file. This is `lantern_harness.permission_authority.PermissionAuthority`.

Two things stay separate, and both are required before an action
proceeds:

- **Authorization** -- is this capability category in scope, per an
  active `PermissionGrant`?
- **Alignment** -- does this specific action actually fit the
  operator's stated objective, current task, and known boundaries?

Authorization is not alignment, and alignment is not authorization.
Combining them gives four outcomes:

| Authorized? | Aligned? | Result |
|---|---|---|
| yes | yes | **ACT** -- proceed, and notify the operator afterward if the action was consequential |
| yes | no | **STOP_AND_REASSESS** -- an existing grant does not override a failed or uncertain alignment check |
| no | yes | **ASK_OPERATOR** -- a `NEW AUTHORITY REQUEST` is raised, stating the action, why, the capability required, foreseeable external effects, and what (if any) existing authorization applies |
| no | no | **REFUSE** |

`PermissionAuthority` owns the scope memory and the combination rule
above; it does not itself judge alignment (`AlignmentResult` is
produced by whatever is reasoning about the request -- the operator or
the reasoning engine -- and passed in, the same way `RealityBoundary`
takes an already-made `DecisionReading` as input rather than computing
one itself).

Grants are `capability` + `scope` + `boundary` + `granting_authority` +
`provenance` + `version` + `status` (+ optional `expires_at_step` /
`conditions`) -- never a single opaque yes/no. `granting_authority`
must always be an explicit, non-empty string; there is no code path
that lets this module default it to something like `"self"` (see
`test_permission_authority_cannot_self_grant`). Certain capability
categories -- credential use, wallet/payment authority, external
communication, legal/financial commitments, destructive operations,
private-data disclosure, and authority transfer to another agent --
never inherit from any other grant, no matter how similar the wording
(e.g. authorization to modify local files never implies authorization
to send an external message).

Grants are held in this process's memory only, never written to
`data_dir`, Chronicle, or any file. This is deliberate: per "Transfer
an instance" above, authority must never silently travel with
transferred state. Every new process -- including a freshly transferred
instance -- starts with zero grants and must be re-authorized by
whoever is actually operating it now.

Use `/permissions`, `/grant`, and `/revoke` from the REPL (see
"Commands" above) to inspect and manage grants interactively.

## Known limitations

See `KNOWN_LIMITATIONS` in the mission report delivered alongside this
harness for the full, honest list.
