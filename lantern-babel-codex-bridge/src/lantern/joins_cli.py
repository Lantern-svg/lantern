"""Operator CLI for viewing rendezvous join requests.

Read-only. Never establishes a connection, never grants a capability,
never touches belief/evidence/Codex state -- it only prints what the
rendezvous Chronicle already recorded via JoinMonitor.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .participants import find as find_participant
from .participants import inspect_all, next_verification_step
from .rendezvous import JoinMonitor, JoinRequest


def _format(requests: list[JoinRequest]) -> str:
    lines = ["\U0001f56f\ufe0f LANTERN RENDEZVOUS", "", f"Pending: {len(requests)}"]
    if not requests:
        return "\n".join(lines) + "\n"
    lines.append("")
    for index, request in enumerate(requests, start=1):
        lines.append(f"{index}. Node: {request.node_id}")
        lines.append(f"   Protocol: {request.protocol_version}")
        lines.append(f"   Request: {request.request_id}")
        lines.append(f"   Status: {request.status}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _format_participants(views) -> str:
    lines = ["\U0001f56f\ufe0f LANTERN PARTICIPANTS (claims as submitted, unverified)", "", f"Count: {len(views)}"]
    if not views:
        return "\n".join(lines) + "\n"
    lines.append("")
    for index, view in enumerate(views, start=1):
        lines.append(f"{index}. Node: {view.node_id}  Request: {view.request_id}")
        lines.append(f"   Protocol claimed: {view.protocol_version}")
        lines.append(f"   Capabilities claimed: {sorted(k for k, v in view.capabilities_claimed.items() if v)}")
        lines.append(f"   Join status: {view.join_status}")
        lines.append(f"   Compatibility (informational only): {view.compatibility_status}")
        lines.append(f"   Trust: {view.trust_status}  Authority: {view.authority_level}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def main(argv=None):
    parser = argparse.ArgumentParser(description="Show pending Lantern rendezvous join requests (lantern joins)")
    parser.add_argument("--data-dir", default=".lantern")
    parser.add_argument("--node-id", required=True, help="Same --node-id used to start the bootstrap node")
    parser.add_argument("--all", action="store_true", help="Show every request, including expired ones")
    parser.add_argument("--json", action="store_true", help="Print raw JSON instead of a formatted list")
    parser.add_argument(
        "--inspect",
        action="store_true",
        help="Show claimed protocol/capabilities and informational compatibility status per participant",
    )
    parser.add_argument(
        "--next-step",
        metavar="REQUEST_ID",
        help="Print the recommended next verification step for one request_id (never contacts the participant)",
    )
    args = parser.parse_args(argv)

    chronicle_path = Path(args.data_dir) / f"{args.node_id}.joins.jsonl"
    monitor = JoinMonitor(chronicle_path)

    if args.next_step:
        view = find_participant(monitor, args.next_step)
        if view is None:
            print(json.dumps({"error": "Unknown request_id", "request_id": args.next_step}))
            return
        result = {"participant": view.to_dict(), "next_step": next_verification_step(view)}
        if args.json:
            print(json.dumps(result, indent=2, sort_keys=True))
        else:
            print(f"Node: {view.node_id}\nCompatibility: {view.compatibility_status}\nNext step: {result['next_step']}")
        return

    if args.inspect:
        views = inspect_all(monitor, include_expired=args.all)
        if args.json:
            print(json.dumps([view.to_dict() for view in views], indent=2, sort_keys=True))
        else:
            print(_format_participants(views))
        return

    shown = monitor.all_requests() if args.all else monitor.pending()
    if args.json:
        print(json.dumps([request.to_dict() for request in shown], indent=2, sort_keys=True))
    else:
        print(_format(shown))


if __name__ == "__main__":
    main()
