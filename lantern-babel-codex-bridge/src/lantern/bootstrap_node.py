"""Minimal HTTP transport for an independently operated Lantern node.

This module is deliberately an adapter, not a protocol implementation. It
uses the existing ProtocolMessage, handshake, compatibility, boundary,
router, bridge, agent, core, Chronicle, and snapshot APIs. The HTTP envelope
only carries the handshake result needed by a stateless request; the message
itself remains the existing ProtocolMessage JSON.

The server binds to localhost by default. Binding to 0.0.0.0 is suitable for
a controlled development network, but production exposure needs the
operator's normal TLS, authentication, and firewall controls.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from .agent import LanternAgent
from .bridge import LanternAgentBridge
from .compatibility import DEFAULT_CAPABILITIES, negotiate
from .continuity import local_watermark
from .core import Chronicle, Lantern
from .handshake import HandshakeRequest, create_handshake, evaluate_handshake
from .protocol import ProtocolMessage


def _json_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True).encode("utf-8")


def _message_dict(message: ProtocolMessage) -> dict:
    return asdict(message)


def _validate_wire_shape(message: ProtocolMessage) -> bool:
    """Check only transport shape; leave version policy to compatibility.

    protocol.validate_message() deliberately requires the exact local
    protocol version. The external connection path must instead parse a
    peer message structurally, then let compatibility.negotiate() apply the
    documented same-major/different-major policy. The raw validator remains
    unchanged and conservative.
    """
    data = asdict(message)
    required = ("message_id", "protocol", "message_type", "source", "timestamp", "payload")
    return all(data.get(name) is not None for name in required) and isinstance(message.payload, dict)


class LanternNode:
    """One process-local Lantern instance behind the HTTP adapter."""

    def __init__(self, node_id: str, chronicle_path: str | Path):
        self.node_id = node_id
        self.chronicle = Chronicle(chronicle_path)
        self.lantern = Lantern(chronicle_filename=chronicle_path)
        self.agent = LanternAgent(self.lantern, chronicle=self.chronicle)
        self.bridge = LanternAgentBridge(self.agent)

        # Existing persistence is authoritative. A restart restores the
        # kernel and module/audit history from the Chronicle/snapshot pair.
        self.lantern.startup()

    def identity(self) -> dict:
        watermark = local_watermark(self.lantern)
        return {
            "node_id": self.node_id,
            "protocol_version": create_handshake().protocol_version,
            "capabilities": dict(DEFAULT_CAPABILITIES),
            "watermark": watermark.to_dict(),
        }

    def handshake(self) -> HandshakeRequest:
        request = create_handshake(dict(DEFAULT_CAPABILITIES))
        request.node_id = self.node_id
        return request

    def receive(self, message_data: dict, peer_capabilities: dict) -> dict:
        try:
            message = ProtocolMessage.decode(json.dumps(message_data))
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise ValueError(f"Malformed ProtocolMessage: {exc}") from exc

        if not _validate_wire_shape(message):
            raise ValueError("Invalid ProtocolMessage")

        compatibility = negotiate(
            remote_version=message.protocol,
            remote_capabilities=peer_capabilities,
        )
        result = self.bridge.receive(message, compatibility)

        data = dict(result.data)
        observation = data.get("observation")
        if observation is not None:
            data["observation"] = asdict(observation)

        return {
            "accepted": result.accepted,
            "action": result.action,
            "reason": result.reason,
            "data": data,
            "protocol": message.protocol,
            "message_type": message.message_type,
            "source": message.source,
            "watermark": local_watermark(self.lantern).to_dict(),
        }


class _Handler(BaseHTTPRequestHandler):
    server_version = "LanternBootstrap/0.1"

    @property
    def node(self) -> LanternNode:
        return self.server.node  # type: ignore[attr-defined]

    def _respond(self, status: int, payload: dict):
        body = _json_bytes(payload)
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self) -> dict:
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0:
            raise ValueError("Request body is required")
        value = json.loads(self.rfile.read(length))
        if not isinstance(value, dict):
            raise ValueError("JSON object is required")
        return value

    def do_GET(self):  # noqa: N802 - BaseHTTPRequestHandler API
        if self.path == "/health":
            self._respond(200, {"status": "ok", **self.node.identity()})
            return
        if self.path == "/handshake":
            self._respond(200, asdict(self.node.handshake()))
            return
        self._respond(404, {"error": "Not found"})

    def do_POST(self):  # noqa: N802 - BaseHTTPRequestHandler API
        try:
            body = self._read_json()
            if self.path == "/handshake":
                request = HandshakeRequest(**body)
                response = evaluate_handshake(request)
                self._respond(200, asdict(response))
                return

            if self.path == "/message":
                message = body.get("message")
                peer_capabilities = body.get("peer_capabilities")
                if not isinstance(message, dict) or not isinstance(peer_capabilities, dict):
                    raise ValueError("message and peer_capabilities objects are required")
                self._respond(200, self.node.receive(message, peer_capabilities))
                return

            self._respond(404, {"error": "Not found"})
        except (TypeError, ValueError, KeyError, json.JSONDecodeError) as exc:
            self._respond(400, {"error": str(exc)})

    def log_message(self, format, *args):
        print(f"[{self.node.node_id}] {format % args}")


def create_server(host: str, port: int, node_id: str, chronicle_path: str | Path):
    node = LanternNode(node_id=node_id, chronicle_path=chronicle_path)
    server = ThreadingHTTPServer((host, port), _Handler)
    server.node = node  # type: ignore[attr-defined]
    return server


def main(argv=None):
    parser = argparse.ArgumentParser(description="Run a minimal Lantern HTTP node")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--node-id", required=True)
    parser.add_argument("--chronicle", default=None)
    parser.add_argument("--data-dir", default=".lantern")
    args = parser.parse_args(argv)

    if not args.chronicle:
        data_dir = Path(args.data_dir)
        data_dir.mkdir(parents=True, exist_ok=True)
        args.chronicle = data_dir / f"{args.node_id}.jsonl"

    server = create_server(args.host, args.port, args.node_id, args.chronicle)
    print(json.dumps({"listening": f"http://{args.host}:{args.port}", **server.node.identity()}))
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
