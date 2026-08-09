"""Command-line client for the minimal external Lantern bootstrap."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path
from urllib.request import Request, urlopen

from .compatibility import DEFAULT_CAPABILITIES
from .continuity import local_watermark
from .core import Chronicle, Lantern
from .handshake import create_handshake
from .heartbeat import evaluate_connection
from .protocol import create_observation_share, PROTOCOL_VERSION


def _request(url: str, method: str = "GET", payload: dict | None = None) -> dict:
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    request = Request(url, data=data, method=method, headers={"Content-Type": "application/json"})
    with urlopen(request, timeout=10) as response:
        return json.loads(response.read())


def main(argv=None):
    parser = argparse.ArgumentParser(description="Send one observation to a Lantern node")
    parser.add_argument("--peer", required=True, help="Peer base URL, e.g. http://127.0.0.1:8766")
    parser.add_argument("--source", required=True)
    parser.add_argument("--content", required=True)
    parser.add_argument("--reliability", type=float, default=1.0)
    parser.add_argument("--node-id", default="lantern-a")
    parser.add_argument("--data-dir", default=".lantern")
    args = parser.parse_args(argv)

    data_dir = Path(args.data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)
    local_chronicle = data_dir / f"{args.node_id}.jsonl"
    local_lantern = Lantern(chronicle_filename=local_chronicle)
    local_lantern.startup()

    peer = args.peer.rstrip("/")
    remote = _request(peer + "/health")
    local_handshake = create_handshake(dict(DEFAULT_CAPABILITIES))
    local_handshake.node_id = args.node_id
    handshake_response = _request(peer + "/handshake", "POST", asdict(local_handshake))
    if not handshake_response["accepted"]:
        raise SystemExit(json.dumps({"status": "rejected", "handshake": handshake_response}))

    message = create_observation_share(
        local_handshake.node_id,
        {"content": args.content, "source": args.source, "reliability": args.reliability},
    )
    result = _request(
        peer + "/message",
        "POST",
        {
            "message": asdict(message),
            "peer_capabilities": local_handshake.capabilities,
        },
    )

    # Heartbeat/connection-state check: liveness + identity + Chronicle
    # position reporting only. This never grants trust or capabilities
    # and never changes local belief -- it is purely operator-facing
    # information, produced by the existing continuity/compatibility
    # comparison logic (lantern.heartbeat.evaluate_connection()).
    peer_heartbeat = _request(peer + "/heartbeat")
    connection_state = evaluate_connection(
        PROTOCOL_VERSION,
        local_watermark(local_lantern),
        peer_heartbeat,
    ).to_dict()

    print(json.dumps({
        "local_node_id": args.node_id,
        "peer": remote,
        "handshake": handshake_response,
        "exchange": result,
        "connection_state": connection_state,
        "local_watermark": {
            "step": local_lantern.kernel.step,
            "chain": local_lantern.bus.chronicle.chain,
        },
    }, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
