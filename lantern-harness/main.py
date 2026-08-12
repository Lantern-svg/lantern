#!/usr/bin/env python3
"""Lantern Harness entrypoint.

USER -> LANTERN INTERFACE (this file) -> REASONING ENGINE -> LANTERN CORE

This does not duplicate Lantern's internals. It calls the real
lantern-babel-codex-bridge package through lantern_harness.bridge.LanternBridge.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from lantern_harness.bootstrap import bootstrap, format_bootstrap_report
from lantern_harness.harness_status import format_status_report, status_report
from lantern_harness.prompt_compiler import PromptCompiler
from lantern_harness.confidence_field import ConfidenceField
from lantern_harness.decision_state_machine import DecisionStateMachine
from lantern_harness.reasoning.base import ReasoningEngineUnavailable
from lantern_harness.tools.boundary import ToolBoundary
from lantern_harness.self_model import SelfModel
from lantern_harness.spine import BranchStore, SpineCommitter
from lantern_harness.operating_loop import OperatingLoop
from lantern_harness.transfer_manifest import build_manifest

COMMANDS = ("/memory", "/history", "/beliefs", "/evidence", "/branches", "/identity", "/tools", "/projects", "/status", "/compile", "/decide", "/self", "/branch", "/spine", "/run", "/transfer", "/new", "/exit")

SYSTEM_PROMPT_PATH = Path(__file__).resolve().parent / "prompts" / "system.md"


def load_system_prompt():
    if not SYSTEM_PROMPT_PATH.exists():
        return None
    return SYSTEM_PROMPT_PATH.read_text(encoding="utf-8")


def handle_command(command: str, bridge, engine, tool_boundary) -> str:
    if command == "/status":
        report = status_report(bridge, engine, tool_boundary)
        return format_status_report(report)
    if command.startswith("/decide"):
        request = command[len("/decide"):].strip()
        if not request:
            return "usage: /decide <your request> -- evaluates confidence and recommends a state, but does not authorize or execute"
        compiler = PromptCompiler(bridge=bridge)
        field = ConfidenceField(bridge=bridge)
        machine = DecisionStateMachine()
        compiled = compiler.compile(request)
        reading = field.evaluate(concept=compiled.concept, perspectives=compiled.perspectives, assumptions=compiled.assumptions, validation_status=compiled.validation_status)
        decision = machine.recommend(reading)
        reason_lines = [f"- {reason}" for reason in decision.reasons] or ["- none"]
        blocker_lines = [f"- {blocker}" for blocker in decision.blockers] or ["- none"]
        change_lines = [f"- {item}" for item in decision.what_would_change_state] or ["- none"]
        return "\n".join([
            f"[decision, state={decision.state}, action={decision.recommended_action}]",
            f"confidence={decision.confidence_score} band={decision.confidence_band}",
            "reasons:",
            *reason_lines,
            "blockers:",
            *blocker_lines,
            "what_would_change_state:",
            *change_lines,
        ])
    if command.startswith("/compile"):
        request = command[len("/compile"):].strip()
        if not request:
            return "usage: /compile <your request> -- compiles a structured prompt, does not send it anywhere"
        compiler = PromptCompiler(bridge=bridge)
        try:
            result = compiler.compile(request)
        except ValueError as exc:
            return f"COMPILE_ERROR: {exc}"
        header = f"[compiled, mode={result.mode}]"
        if result.notes:
            header += "\nnotes: " + "; ".join(result.notes)
        return f"{header}\n\n{result.text}"
    if command == "/identity":
        return str(bridge.identity_status())
    if command == "/tools":
        return f"discovered: {tool_boundary.discover()}, authorized: {sorted(tool_boundary._authorized)}"
    if command == "/memory":
        s = bridge.status()
        return f"step={s['step']} observations={s['observations']} evidence={s['evidence']} contradictions={s['contradictions']}"
    if command in ("/branches",):
        try:
            bridge.branches()
        except NotImplementedError as exc:
            return f"NOT_IMPLEMENTED: {exc}"
    if command in ("/history", "/beliefs", "/evidence", "/projects"):
        return f"{command}: not yet implemented as a formatted view in this harness version (raw data is available via LanternBridge)"
    if command == "/exit":
        return "__EXIT__"
    return f"unknown command: {command}"


def handle_stateful_command(command: str, bridge, tool_boundary, branch_store, loop, engine=None) -> str | None:
    """Commands that need state that persists across turns (open
    branches, the OperatingLoop's compiled components). Kept separate
    from handle_command so that function stays a pure per-call dispatch.
    Returns None if the command is not one of these."""
    if command == "/self":
        model = SelfModel(bridge, tool_boundary)
        return model.describe().format()

    if command.startswith("/branch"):
        request = command[len("/branch"):].strip()
        if not request:
            open_ids = [b.id for b in branch_store.all() if b.status == "OPEN"]
            return f"usage: /branch <concept> :: <hypothesis>  |  open branches: {open_ids or 'none'}"
        if "::" not in request:
            return "usage: /branch <concept> :: <hypothesis>"
        concept, hypothesis = (part.strip() for part in request.split("::", 1))
        branch = branch_store.open_branch(concept=concept, hypothesis=hypothesis)
        return f"[branch opened] id={branch.id} concept={branch.concept!r} status={branch.status} -- outside committed Spine state until an explicit /spine commit"

    if command.startswith("/spine"):
        request = command[len("/spine"):].strip()
        if not request:
            committer = SpineCommitter(bridge)
            entries = committer.read_spine()
            if not entries:
                return "spine: 0 committed entries"
            lines = [f"spine: {len(entries)} committed entries"]
            for entry in entries:
                lines.append(f"  - [{entry.id}] concept={entry.concept!r} statement={entry.statement!r}")
            return "\n".join(lines)
        return (
            "SPINE_NOT_COMMITTED: this REPL command intentionally cannot authorize a commit on your behalf. "
            "A branch cannot commit itself and no confidence score alone may create commitment "
            "(see lantern_harness.spine.SpineCommitter.commit's required authorized=True parameter). "
            "Use SpineCommitter directly from a script where you, the operator, explicitly pass authorized=True."
        )

    if command.startswith("/run"):
        intent = command[len("/run"):].strip()
        if not intent:
            return "usage: /run <intent> -- runs the full operating loop (observe -> compile -> confidence -> decision), never executes a tool without prior ToolBoundary authorization"
        result = loop.run(intent)
        return result.format()

    if command == "/transfer":
        manifest = build_manifest(bridge, engine=engine)
        return manifest.format()

    return None


def run_repl(bridge, engine, tool_boundary, branch_store, loop):
    system_prompt = load_system_prompt()
    history = [{"role": "system", "content": system_prompt}] if system_prompt else []

    print("You:", end=" ", flush=True)
    for line in sys.stdin:
        line = line.strip()
        if not line:
            print("You:", end=" ", flush=True)
            continue

        if line.startswith("/"):
            stateful_result = handle_stateful_command(line, bridge, tool_boundary, branch_store, loop, engine=engine)
            if stateful_result is not None:
                print(stateful_result)
                print("You:", end=" ", flush=True)
                continue
            result = handle_command(line, bridge, engine, tool_boundary)
            if result == "__EXIT__":
                return
            print(result)
            print("You:", end=" ", flush=True)
            continue

        obs = bridge.observe(line, source="user", reliability=1.0)

        if engine is None:
            print("REASONING_ENGINE: NOT_CONFIGURED -- observation recorded (id=%s) but no reasoning engine is configured to respond. Edit config/config.json to set a provider." % obs.id)
            print("You:", end=" ", flush=True)
            continue

        history.append({"role": "user", "content": line})
        try:
            response = engine.respond(history)
            print(response.text)
            history.append({"role": "assistant", "content": response.text})
        except ReasoningEngineUnavailable as exc:
            print(f"REASONING_ENGINE_ERROR: {exc}")
            history.pop()  # do not retain a turn the engine never actually answered

        print("You:", end=" ", flush=True)


def main():
    result = bootstrap()
    print(format_bootstrap_report(result))

    bridge = result["bridge"]
    if bridge is None:
        print("\nCannot start conversation loop: Lantern is not importable in this environment.")
        return 1

    engine = result["engine"]
    tool_boundary = ToolBoundary()
    branch_store = BranchStore()
    loop = OperatingLoop(bridge, tool_boundary)

    print()
    run_repl(bridge, engine, tool_boundary, branch_store, loop)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
