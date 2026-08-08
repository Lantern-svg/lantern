"""Operator CLI for viewing rendezvous join requests.

Read-only. Never establishes a connection, never grants a capability,
never touches belief/evidence/Codex state -- it only prints what the
rendezvous Chronicle already recorded via JoinMonitor.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

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


def main(argv=None):
    parser = argparse.ArgumentParser(description="Show pending Lantern rendezvous join requests (lantern joins)")
    parser.add_argument("--data-dir", default=".lantern")
    parser.add_argument("--node-id", required=True, help="Same --node-id used to start the bootstrap node")
    parser.add_argument("--all", action="store_true", help="Show every request, including expired ones")
    parser.add_argument("--json", action="store_true", help="Print raw JSON instead of a formatted list")
    args = parser.parse_args(argv)

    chronicle_path = Path(args.data_dir) / f"{args.node_id}.joins.jsonl"
    monitor = JoinMonitor(chronicle_path)
    shown = monitor.all_requests() if args.all else monitor.pending()

    if args.json:
        print(json.dumps([request.to_dict() for request in shown], indent=2, sort_keys=True))
    else:
        print(_format(shown))


if __name__ == "__main__":
    main()
