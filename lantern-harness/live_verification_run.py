#!/usr/bin/env python3
"""LIVE end-to-end verification of the Lantern harness.

Executes REAL components only (no stand-in reasoning engine is used at all:
the OperatingLoop path under test does not involve any reasoning provider).
Every verification item from the engineer's checklist is executed live and
marked VERIFIED or NOT VERIFIED with the console evidence right above it.
"""
from __future__ import annotations
import sys, time, json, pathlib

sys.path.insert(0, ".")
from main import handle_command, handle_stateful_command, bootstrap, load_system_prompt
from lantern_harness.operating_loop import OperatingLoop
from lantern_harness.permission_authority import (
    PermissionAuthority, AlignmentResult, CAPABILITY_CATEGORIES,
)
from lantern_harness.tools.boundary import ToolBoundary, ToolDescriptor
from lantern_harness.perspective_differential import Perspective

T0 = time.time()
def mark(item, ok, detail=""):
    status = "VERIFIED" if ok else "NOT VERIFIED"
    print(f"\n### ITEM {item}: {status} {('| ' + detail) if detail else ''}\n")
    return ok

print("=" * 78)
print("LANTERN HARNESS — LIVE END-TO-END VERIFICATION RUN")
print("=" * 78)

# ---------------------------------------------------------------- Phase 0
print("\n--- PHASE 0: real bootstrap (no mocking, real directories) ---")
result = bootstrap()
from main import format_bootstrap_report
print(format_bootstrap_report(result))
bridge = result["bridge"]
engine = result["engine"]

# ITEM: fail-closed reasoning engine behavior
engine_line = "reasoning_engine" in result.get("checks", {})
print(f"engine is None: {engine is None}; checks contain reasoning_engine: {engine_line}")
if engine is None:
    print("REASONING_ENGINE: NOT_CONFIGURED — no fabricated response possible (fail-closed observed)")
ITEM_engine = mark("0a (model failure path)", engine is None,
                   "no provider configured -> NOT_CONFIGURED, no fabricated response")

tool_boundary = ToolBoundary()
from lantern_harness.spine import BranchStore
branch_store = BranchStore()
loop = OperatingLoop(bridge, tool_boundary)
permission_authority = PermissionAuthority()

# ---------------------------------------------------------------- ITEM 1
print("\n--- ITEM 1: /run end-to-end (REPL path, no tool) ---")
out = handle_stateful_command("/run verify that the harness executes its loop", bridge, tool_boundary, branch_store, loop)
print(out)
ITEM_run_repl = mark("1a (/run REPL path)", "OPERATING LOOP RESULT" in (out or ""), "loop produced a full result")

print("\n--- ITEM 1b: /run full path WITH real external action (script path, real tool) ---")
# Real, harmless, observable external action: append a line to a local file.
TARGET = pathlib.Path("data/live_verification_target.txt").resolve()
TARGET.parent.mkdir(parents=True, exist_ok=True)
TARGET.write_text("pre-run state\n")

def write_note(text: str) -> str:
    with open(TARGET, "a") as fh:
        fh.write(text + "\n")
    return f"appended {text!r} to {TARGET.name}"

tool_boundary.register(ToolDescriptor(
    name="append_local_note",
    description="Append one line to the live-verification target file (local_file_modification)",
    handler=write_note,
    requires_authorization=True,
    scopes=("local_file_modification",),
))
print(f"registered tool append_local_note (scopes local_file_modification); authorized={tool_boundary.authorize('append_local_note')}")
gated_loop = OperatingLoop(bridge, tool_boundary,
                           required_confidence=0.8, allowed_scopes={"local_file_modification"})
print("gated loop: required_confidence=0.8, allowed_scopes={'local_file_modification'}")

p1 = Perspective(source="structural", conclusion="The loop must not fabricate downstream steps when prerequisites are missing.",
                  confidence=0.8, evidence_score=0.7, assumption_bias=0.2)
p2 = Perspective(source="pragmatic", conclusion="A tool action counts as real only if the external file actually changed.",
                  confidence=0.8, evidence_score=0.7, assumption_bias=0.2)

# Honest gate-crossing path: independent evidence + caller-supplied
# independent verification (an UNVERIFIED run caps below the threshold).
VC = f"live_verification_verified_{int(time.time())}"
for i in range(3):
    o = bridge.observe(f"verified reading {i}: the marker write is intended and safe",
                       source=f"independent-verifier-{i}", reliability=1.0)
    bridge.add_evidence(VC, o.id, weight=1.0, sign=1)
res = gated_loop.run(
    "Append a live-verification marker line to the local target file",
    concept=VC,
    perspectives=[p1, p2],
    validation_status="VERIFIED",
    tool_name="append_local_note",
    tool_kwargs={"text": f"live-run {int(time.time())}"},
)
print(res.format())
file_after = TARGET.read_text()
real_change = "live-run" in file_after
print(f"file content after run: {file_after!r}")
print(f"action_record: mode={res.action_record.execution_mode} status={res.action_record.result_status} real_success={res.action_record.is_real_success()}")
ITEM_run_tool = mark("1b (/run -> Bridge -> Loop -> PermissionBoundary gate -> RealityBoundary -> tool -> file)",
                     real_change and res.action_record is not None and res.action_record.is_real_success(),
                     f"file changed on disk: {real_change}")

print("\n--- ITEM 1b2: the closed defect -- authorized tool + LOW confidence must BLOCK ---")
before_bytes = TARGET.read_text()
res_low = gated_loop.run(
    "Append a marker line WITHOUT verification evidence",
    concept=f"unverified_low_confidence_{int(time.time())}",
    tool_name="append_local_note",
    tool_kwargs={"text": "low-confidence-should-never-appear"},
)
print(res_low.format())
unchanged = TARGET.read_text() == before_bytes
print(f"file unchanged by low-confidence run: {unchanged}")
ITEM_low_block = mark("1b2 (LOW confidence + authorized tool BLOCKED by the gate)",
                      unchanged and "low-confidence-should-never-appear" not in TARGET.read_text()
                      and res_low.action_record is not None and not res_low.action_record.is_real_success())

print("\n--- ITEM 1c: /run with an UNAUTHORIZED tool must NOT execute ---")
def dangerous_dummy(payload: str = "boom") -> str:
    return "THIS MUST NEVER APPEAR IN THE FILE"
tool_boundary.register(ToolDescriptor(
    name="unauthorized_local_wipe", description="registered but never authorized",
    handler=dangerous_dummy, requires_authorization=True,
))
res_d = loop.run(
    "Try to run the unauthorized tool",
    concept="negative_control",
    tool_name="unauthorized_local_wipe",
    tool_kwargs={},
)
print(res_d.format())
print(f"file unchanged by negative control: {'THIS MUST NEVER APPEAR' not in TARGET.read_text()}")
ITEM_run_denied = mark("1c (unauthorized tool blocked)",
                       res_d.action_record is not None and not res_d.action_record.is_real_success()
                       and "THIS MUST NEVER APPEAR" not in TARGET.read_text(),
                       f"action result_status={res_d.action_record.result_status if res_d.action_record else 'none'}")

# ---------------------------------------------------------------- ITEM 2
print("\n--- ITEM 2: /self live ---")
out_self = handle_stateful_command("/self", bridge, tool_boundary, branch_store, loop)
print(out_self[:1500])
print("... (truncated for transcript)")
ITEM_self = mark("2 (/self)", bool(out_self) and "SELF-MODEL" in out_self, "self-model inspection returned live runtime state")

# ---------------------------------------------------------------- ITEM 3
print("\n--- ITEM 3: PermissionAuthority live — allowed / disallowed / ambiguous ---")

def align(verdict, reasoning, considered=("operator intent", "stated objective")):
    return AlignmentResult(verdict=verdict, considered=considered, supporting_evidence=(),
                           contradictions=(), foreseeable_consequences=(), introduces_new_commitment=False,
                           reasoning=reasoning)

# 3a: clearly allowed — operator grants run_tests, action aligned and in scope
g_out = handle_stateful_command("/grant run_tests :: pytest suite for lantern-harness :: operator-mikhail", bridge, tool_boundary, branch_store, loop, permission_authority=permission_authority)
print(g_out)
chk_a = permission_authority.check(
    action="run the harness pytest suite",
    capability="run_tests",
    alignment=align("PASSED", "action matches the granted scope exactly; no external effects"),
)
print(f"3a result={chk_a.result} authorized={chk_a.authorized}")
ITEM_3a = mark("3a (allowed -> ACT)", chk_a.result == "ACT")

# 3b: clearly disallowed — destructive op, no grant, alignment FAILED
chk_b = permission_authority.check(
    action="rm -rf the repository data directory",
    capability="destructive_system_operation",
    alignment=align("FAILED", "irreversible destruction, contradicts operator intent and any reasonable scope"),
    external_effects=["irreversible local data loss"],
)
print(f"3b result={chk_b.result} authorized={chk_b.authorized} notes={chk_b.notes}")
ITEM_3b = mark("3b (disallowed -> REFUSE)", chk_b.result == "REFUSE")

# 3b-NEVER_INHERITS: lookalike grant must not imply credential_use
g2 = handle_stateful_command("/grant external_communication :: status posts to the wall :: operator-mikhail", bridge, tool_boundary, branch_store, loop, permission_authority=permission_authority)
print(g2)
chk_b2 = permission_authority.check(
    action="use the stored VPS ssh credential to deploy",
    capability="credential_use",
    alignment=align("PASSED", "alignment passes on its own terms; question is scope"),
)
print(f"3b2 result={chk_b2.result} authorized={chk_b2.authorized}")
print("never-inherits note present:", any("never implied" in n for n in chk_b2.notes))
ITEM_3b2 = mark("3b2 (lookalike capability NOT inherited)", chk_b2.result == "ASK_OPERATOR"
                and any("never implied" in n for n in chk_b2.notes))

# 3c: ambiguous — granted capability, but alignment UNCERTAIN -> cautious stop
chk_c = permission_authority.check(
    action="run_tests, but pointed at the production config instead of the test config",
    capability="run_tests",
    alignment=align("UNCERTAIN", "capability matches, but the specific action may have unintended effects outside the tested surface"),
)
print(f"3c result={chk_c.result} authorized={chk_c.authorized}")
ITEM_3c = mark("3c (ambiguous -> STOP_AND_REASSESS)", chk_c.result == "STOP_AND_REASSESS")

# self-grant refusal (bonus, from the 'no cell authorizes itself' law)
print("\n--- bonus: grants cannot be created without an explicit granting authority ---")
try:
    permission_authority.grant(capability="run_tests", scope="self-granted scope", boundary="",
                              granting_authority="", provenance="self")
    print("SELF GRANT ACCEPTED — DEFECT")
    ITEM_selfgrant = False
except ValueError as exc:
    print(f"grant refused: {exc}")
    ITEM_selfgrant = True
mark("3d (self-grant refused)", ITEM_selfgrant)

# ---------------------------------------------------------------- ITEM 4
print("\n--- ITEM 4: RealityBoundary — claims vs evidence, live ---")

# 4a: three model outputs enter as observations with different reliability;
#     confidence must weight them differently (claim vs corroboration).
# The loop READS the EvidenceKernel; evidence is linked explicitly via
# bridge.add_evidence(concept, observation_id, weight, sign). Claims vs
# evidence is therefore a LIVE question of how weights/signs propagate.
C = f"claims_vs_evidence_live_{int(time.time())}"
obs_claim = bridge.observe("model output claims the config value is 5", source="model-alpha", reliability=0.3)
obs_verified = bridge.observe("operator read the config file directly, value is 5", source="human-operator", reliability=1.0)
obs_contra = bridge.observe("a second file read returned the value 4", source="human-operator", reliability=1.0)
# 1. claim alone: low weight
bridge.add_evidence(C, obs_claim.id, weight=0.3, sign=1)
r1 = loop.run("assess claim state", concept=C)
print(f"claim alone (w=0.3, sign+): score={r1.confidence.confidence_score} band={r1.confidence.confidence_band} evidence_strength={r1.confidence.evidence_strength}")
# 2. independent verification added
bridge.add_evidence(C, obs_verified.id, weight=1.0, sign=1)
r2 = loop.run("assess claim state", concept=C)
print(f"claim + independent verification (w=1.0, sign+): score={r2.confidence.confidence_score} band={r2.confidence.confidence_band} evidence_strength={r2.confidence.evidence_strength} contradiction_pressure={r2.confidence.contradiction_pressure}")
# 3. contradiction added (sign -)
bridge.add_evidence(C, obs_contra.id, weight=0.8, sign=-1)
r3 = loop.run("assess claim state", concept=C)
contradiction_now = bridge.latest_contradiction(C) if hasattr(bridge, "latest_contradiction") else None
print(f"with contradiction (w=0.8, sign-): score={r3.confidence.confidence_score} band={r3.confidence.confidence_band} contradiction_pressure={r3.confidence.contradiction_pressure}")
print(f"kernel contradiction record: {contradiction_now}")
try:
    ITEM_4a = mark("4a (claims vs evidence: weights/signs change live readings, contradiction detected)",
                  float(r2.confidence.confidence_score) > float(r1.confidence.confidence_score)
                  and float(r3.confidence.contradiction_pressure) > 0
                  and contradiction_now is not None)
except (TypeError, ValueError):
    ITEM_4a = mark("4a (claims vs evidence separation)", False, "scores BLOCKED or non-numeric")

# 4b: simulate vs act — hypothetical result is a CLAIM, executed result is EVIDENCE
from lantern_harness.reality_boundary import RealityBoundary
rb = RealityBoundary()
prop = rb.propose(intent="append marker via append_local_note",
                  decision=res.decision, tool_name="append_local_note",
                  inputs={"text": "simulated-only"})
sim = rb.simulate(prop, hypothetical_result="appended (hypothetical)", reason="what-if analysis, no external effect intended")
print(f"simulate: execution_mode={sim.execution_mode} result_status={sim.result_status} is_real_success={sim.is_real_success()}")
print(f"file untouched by simulation: {'simulated-only' not in TARGET.read_text()}")
prop2 = rb.propose(intent="append marker via append_local_note",
                   decision=res.decision, tool_name="append_local_note",
                   inputs={"text": "actually-executed"})
# act() now refuses consequential tools; the executed leg goes through the gate
from lantern_harness.decision_gate import authorize_tool_call, execute_tool_call as _exec
from lantern_harness.tool_contract import ToolCall as _TC
_call2 = _TC(id="live-act-leg", tool_name="append_local_note", arguments={"text": "actually-executed"})
_dec2 = authorize_tool_call(_call2, gated_loop.allowed_scopes, evidence_confidence=0.95, tool_boundary=tool_boundary)
_tcr2, _tr2 = _exec(_call2, _dec2, 0.8, tool_boundary)
act_rec = rb.record_result(prop2, _tr2, decision=_dec2)
print(f"act:      execution_mode={act_rec.execution_mode} result_status={act_rec.result_status} is_real_success={act_rec.is_real_success()}")
print(f"file contains executed marker: {'actually-executed' in TARGET.read_text()}")
ITEM_4b = mark("4b (simulate != act: hypothetical marked simulated, real marked real)",
               sim.execution_mode != act_rec.execution_mode
               and not sim.is_real_success() and act_rec.is_real_success()
               and "actually-executed" in TARGET.read_text()
               and "simulated-only" not in TARGET.read_text())

# 4c: downstream exposure — the separation is visible in structured output
loop_rec = res.to_dict()
print("downstream exposure (LoopResult.to_dict keys):", sorted(loop_rec.keys()))
print("action_record exposure:", json.dumps(loop_rec["action_record"], default=str)[:300])
em = str((loop_rec.get("action_record") or {}).get("execution_mode", "")).upper()
ITEM_4c = mark("4c (separation exposed downstream in structures)", "action_record" in loop_rec
               and em in ("REAL", "SIMULATED"))

# ---------------------------------------------------------------- ITEM 5 (bonus)
print("\n--- bonus: /spine REPL cannot authorize a commit ---")
out_spine = handle_stateful_command("/spine commit something", bridge, tool_boundary, branch_store, loop)
print(out_spine[:400])
ITEM_spine = mark("5 (/spine refuses self-authorization)", "SPINE_NOT_COMMITTED" in (out_spine or ""))

# ---------------------------------------------------------------- summary
print("\n" + "=" * 78)
print("VERIFICATION SUMMARY")
print("=" * 78)
items = [
    ("0a  reasoning model absent -> NOT_CONFIGURED (fail-closed)", ITEM_engine),
    ("1a  /run REPL end-to-end (observe->compile->confidence->decision)", ITEM_run_repl),
    ("1b  /run full path with real authorized tool + real file change", ITEM_run_tool),
    ("1c  /run with unauthorized tool -> blocked, file unchanged", ITEM_run_denied),
    ("1b2 authorized tool + LOW confidence -> BLOCKED (defect closed)", ITEM_low_block),
    ("2   /self live self-inspection", ITEM_self),
    ("3a  PermissionAuthority: allowed -> ACT", ITEM_3a),
    ("3b  PermissionAuthority: disallowed -> REFUSE", ITEM_3b),
    ("3b2 NEVER_INHERITS: lookalike grant does not imply credential_use", ITEM_3b2),
    ("3c  PermissionAuthority: ambiguous -> STOP_AND_REASSESS", ITEM_3c),
    ("3d  self-grant refused (no cell authorizes itself)", ITEM_selfgrant),
    ("4a  claims vs evidence: reliability weighting separates them", ITEM_4a),
    ("4b  simulate (claim) vs act (evidence), live file proof", ITEM_4b),
    ("4c  separation exposed downstream in ActionRecord/LoopResult", ITEM_4c),
    ("5   /spine refuses self-authorized commitment", ITEM_spine),
]
for name, ok in items:
    print(f"  [{'VERIFIED' if ok else 'NOT VERIFIED':12}] {name}")
n_ok = sum(1 for _, ok in items if ok)
print(f"\n{n_ok}/{len(items)} items VERIFIED in {time.time()-T0:.1f}s, all via real executed components")
