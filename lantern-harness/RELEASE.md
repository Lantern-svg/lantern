# lantern-harness Release Notes

Status document, like `RELEASE.md` in `lantern-babel-codex-bridge`.
Only records changes that actually happened and were actually tested.

## PyPI-readiness investigation: local build/install verification (no publish, no credentials touched)

Autonomous-operation pass, staying within local/reversible boundaries
(no network publish, no credential use -- neither exists nor was
sought). Actually built the package locally (`python -m build`) and
installed the resulting wheel into a disposable venv to test what a
real `pip install lantern-harness` would do, rather than assuming from
reading `pyproject.toml`.

**Confirmed working**: the wheel's `.py` file manifest exactly matches
the real `lantern_harness/`/`main.py` source tree -- no silent
omissions from `[tool.setuptools.packages.find]`.

**Found two real blockers**, both worse than the existing `KNOWN_GAPS`
entry ("no publishing credentials present") implied -- even with
credentials, this package would ship broken today:

1. `prompts/system.md` and `config/config.json` are runtime assets
   `main.py`/`lantern_harness/config.py` locate via
   `Path(__file__).resolve().parent`-relative lookups. Verified by
   installing the built wheel into a disposable venv: neither file is
   present anywhere reachable from the installed `main.py`. Config
   degrades gracefully (falls back to built-in defaults); the system
   prompt loader also degrades gracefully (`load_system_prompt()`
   returns `None`, `REASONING_ENGINE` reports `NOT_CONFIGURED` rather
   than crashing) -- so this is a silent-degradation bug, not a crash,
   which is arguably worse (fails quietly instead of loudly).
   - Attempted fix: `[tool.setuptools.data-files]` pointing at
     `prompts/` and `config/`. Verified this does NOT work --
     `data-files` installs relative to the venv's `sys.prefix`, not
     next to the package in `site-packages`, so `main.py`'s
     `Path(__file__).parent` lookup still misses it. Reverted the
     change (confirmed `git diff pyproject.toml` clean) rather than
     leave a non-functional config in the tree. A real fix would need
     `importlib.resources`-style package-data lookup instead of
     filesystem-relative paths -- an actual code change to `main.py`
     and `config.py`, not just a `pyproject.toml` edit, and not
     attempted here since it touches how those two files locate their
     inputs, deliberately left for a decision rather than a quiet
     autonomous rewrite.
2. `pyproject.toml` declares `dependencies = []` -- no dependency on
   Lantern core (`lantern-babel-codex-bridge`, PyPI name `lantern`) at
   all. Confirmed via `pip index versions lantern-babel-codex-bridge`:
   not published. So even a perfectly-packaged harness wheel would
   `ModuleNotFoundError: No module named 'lantern'` for anyone who
   actually ran `pip install lantern-harness` standalone, since the
   README's only documented install path (clone both repos, install
   into the `lantern-babel-codex-bridge` sibling venv) is not what a
   PyPI user would do.

Updated `KNOWN_GAPS` in `lantern_harness/self_model.py` to state the
real blocker instead of only "no credentials." No code behavior
changed -- `pyproject.toml` is back to its pre-investigation state.
Full harness suite: 194/194 passing (unchanged). No PyPI credentials
exist, were sought, or were used; nothing was published anywhere.

## Docs staleness fix: PEACEMAKER.md and ODYSSEUS_INTEGRATION.md sync with PermissionAuthority/lantern_permissions

Audit found PEACEMAKER.md's "carries" table and "sovereign" bullet
listed every implemented delegated-authority-relevant guarantee except
PermissionAuthority (it predates the module), and
ODYSSEUS_INTEGRATION.md's "What was built this session" and summary
table stopped at lantern_transfer_manifest, not mentioning
lantern_permissions -- a real gap for the exact audience
(Odysseus/MCP-host operators) that document exists for. Added a
PermissionAuthority row to PEACEMAKER.md's carries table and named it
explicitly in the "sovereign" bullet (grants held in process memory
only, never in data_dir, zero standing grants on every transferred
instance). Added a dated "Also added (PEACEMAKER delegated-authority
phase...)" section to ODYSSEUS_INTEGRATION.md, matching its existing
per-phase pattern, and updated its summary table's tool/test counts.
No code changes. Full harness suite: 194/194 passing (unchanged count,
docs only).

## Expose PermissionAuthority read-only over the MCP server (lantern_permissions)

`lantern_harness/mcp_server.py` exposed `lantern_transfer_manifest` but
had no `PermissionAuthority` surface at all -- a real gap found during
a routine audit, not manufactured work: any MCP host connected to this
server (e.g. Odysseus) had no way to see this process's active
capability-scope grants. Added `lantern_permissions`, a read-only tool
listing active grants (capability/scope/granting_authority/version),
following the exact same shape/rationale as `lantern_transfer_manifest`.
Deliberately did **not** add `lantern_grant`/`lantern_revoke` MCP
tools -- that would let a remote, non-human MCP caller supply its own
`granting_authority` string and grant itself permissions, which
directly contradicts the REPL `/grant` design (a human must type their
own name at the keyboard). This is treated as a distinct, genuinely
new authority boundary, not routine work, and was not built without
being asked. `test_server_exposes_no_grant_or_revoke_tool_over_mcp`
enforces the absence structurally, the same way
`test_lantern_evaluate_intent_has_no_tool_name_parameter` already
enforces `lantern_evaluate_intent`'s missing action parameter. 3 new
tests (`tests/test_mcp_server.py`): zero-grants-by-default, reflects a
real in-process grant, and the grant/revoke-tool-absence check. Full
harness suite: 194/194 passing (up from 191).

## Docs staleness fix: system.md and tool_use.md sync with PermissionAuthority

Audit found two real gaps, not just missing polish: (1) `prompts/system.md`
-- the file `main.py` actually loads as the reasoning engine's system
prompt -- listed every implemented component except `TransferManifest`
and the newly-added `PermissionAuthority`, so a configured reasoning
engine would have had no visibility into the permission/alignment model
it's meant to reason under. (2) `prompts/tool_use.md` predated
`ToolBoundary`-only tool gating and was never updated for
`PermissionAuthority`; it also turned out to be dead weight -- no code
path loads it, only `system.md` is wired into `main.py`. Fixed both:
added `TransferManifest` and `PermissionAuthority` sections to
`system.md` (kept `Harness v0.2.0` version strings as-is, matching the
actual unbumped `HARNESS_VERSION`/`pyproject.toml` value -- caught and
reverted an over-eager v0.3.0 edit before committing it), and rewrote
`tool_use.md` to state the authorization-is-not-alignment rule
correctly and to note plainly that it is documentation only, not
currently loaded by any code. No code changes. Full harness suite:
191/191 passing (unchanged count, docs only).

## Peacemaker delegated authority: permission memory + alignment checking

Added `lantern_harness/permission_authority.py`
(`PermissionAuthority`/`PermissionGrant`/`AlignmentResult`/
`PermissionCheckResult`), per the PEACEMAKER DELEGATED AUTHORITY,
ALIGNMENT, AND PERMISSION MEMORY directive: capability-scope permission
memory (not per-command approval) combined with a separately-produced
alignment judgment, using the directive's own rule -- authorized AND
aligned -> ACT; authorized but misaligned -> STOP_AND_REASSESS; aligned
but not authorized -> ASK_OPERATOR; neither -> REFUSE. Grants require
an explicit, non-empty `granting_authority` (no self-grant code path
exists) and are held in process memory only, never persisted to
`data_dir`/Chronicle/any file, so authority never silently travels with
a transferred instance (consistent with "Transfer an instance" and the
directive's own Transfer Behavior section). External-authority
categories (credentials, wallets, payments, communications,
legal/financial commitments, destructive operations, private-data
disclosure, authority transfer to another agent) never inherit from
any other grant. Wired into `main.py` as `/permissions`, `/grant`,
`/revoke`, matching the existing `/branch`/`/spine` REPL patterns; new
`permission_authority_status` field in `harness_status.py`; new
capability line added to `SelfModel.KNOWN_CAPABILITIES` (reused by
`TransferManifest`, not duplicated); new README "Permissions and
alignment" section. 22 new unit tests
(`tests/test_permission_authority.py`) + 5 new REPL subprocess tests
(`tests/test_conversation_loop.py`) + 1 new status test
(`tests/test_harness_status.py`). Full harness suite: 191/191 passing.
Real REPL smoke test performed against a disposable `data_dir`: zero
grants by default, `/grant` records with the typed name as
`granting_authority`, unknown capability categories are refused,
`/revoke` removes the active grant. This milestone stops here per the
directive's explicit stop condition -- no PyPI publish, no push, no
outreach, no new alignment-judgment engine (that remains the caller's
responsibility, same separation of concerns as `RealityBoundary`
taking an already-made `DecisionReading`).

## Peacemaker identity naming (same 0.3.0 session, after transfer readiness)

Added `PEACEMAKER.md`: names the personal, transferable *instance*
built on the Lantern architecture "Peacemaker," per explicit operator
directive. This is a naming/documentation change, not a rewrite of
history -- no package, module, class, or prior commit was renamed;
`git log` remains unedited. `TransferManifest` gained one new field,
`lineage` (`{"architecture": "Lantern", "instance_model": "Peacemaker"}`),
so the distinction is reportable as data by any receiving operator or
agent, not just asserted in prose. 1 new test
(`test_manifest_lineage_names_lantern_as_architecture_and_peacemaker_as_instance_model`).
Full harness suite: 163/163 passing.

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
