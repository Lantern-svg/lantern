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
import time
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
from .heartbeat import create_heartbeat, evaluate_connection
from .participants import find as find_participant
from .participants import inspect_all, next_verification_step
from .protocol import ProtocolMessage
from .rendezvous import JoinMonitor


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

    def __init__(self, node_id: str, chronicle_path: str | Path, join_chronicle_path: str | Path | None = None):
        self.node_id = node_id
        self.chronicle = Chronicle(chronicle_path)
        self.lantern = Lantern(chronicle_filename=chronicle_path)
        self.agent = LanternAgent(self.lantern, chronicle=self.chronicle)
        self.bridge = LanternAgentBridge(self.agent)
        self.started_monotonic = time.monotonic()

        # The rendezvous join monitor is deliberately a separate Chronicle
        # from the belief/evidence Chronicle above. A join announcement is
        # an audit event about contact, never an input to the kernel --
        # keeping it in its own log makes that separation structural, not
        # just a convention someone could forget.
        if join_chronicle_path is None:
            join_chronicle_path = Path(str(chronicle_path)).with_name(
                Path(str(chronicle_path)).stem + ".joins.jsonl"
            )
        self.rendezvous = JoinMonitor(join_chronicle_path)

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

    def heartbeat(self) -> dict:
        """Liveness + identity + Chronicle position, read-only.

        Wraps heartbeat.create_heartbeat() over the same
        continuity.local_watermark() the rest of the adapter already
        uses. Does not grant capabilities and does not touch belief,
        evidence, or Codex state.
        """
        watermark = local_watermark(self.lantern)
        return create_heartbeat(
            node_id=self.node_id,
            protocol_version=create_handshake().protocol_version,
            started_monotonic=self.started_monotonic,
            watermark=watermark,
        ).to_dict()

    def connection_state(self, peer_heartbeat: dict | None) -> dict:
        """Compare a peer's self-reported heartbeat against local state.

        Non-authoritative: this is operator-facing information about
        reachability/version/continuity, never a trust or capability
        decision.
        """
        watermark = local_watermark(self.lantern)
        return evaluate_connection(
            create_handshake().protocol_version, watermark, peer_heartbeat
        ).to_dict()

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
            self._respond(
                200,
                {
                    "status": "ok",
                    **self.node.identity(),
                    "heartbeat": self.node.heartbeat(),
                    "rendezvous": self.node.rendezvous.health(),
                },
            )
            return
        if self.path == "/heartbeat":
            self._respond(200, self.node.heartbeat())
            return
        if self.path == "/handshake":
            self._respond(200, asdict(self.node.handshake()))
            return
        if self.path == "/participants":
            # Read-only inspection: claims as recorded, never re-verified
            # here and never treated as authorization. See participants.py.
            views = [view.to_dict() for view in inspect_all(self.node.rendezvous)]
            self._respond(200, {"participants": views})
            return
        if self.path.startswith("/participants/") and self.path.endswith("/next-step"):
            request_id = self.path[len("/participants/") : -len("/next-step")]
            view = find_participant(self.node.rendezvous, request_id)
            if view is None:
                self._respond(404, {"error": "Unknown request_id"})
                return
            # Advice text only -- does not contact the participant.
            self._respond(
                200,
                {
                    "request_id": request_id,
                    "participant": view.to_dict(),
                    "next_step": next_verification_step(view),
                },
            )
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

            if self.path == "/join":
                # An announcement, not authorization. submit() only ever
                # writes to the rendezvous Chronicle above -- it has no
                # access to self.node.lantern/self.node.agent/self.node.
                # bridge, so it cannot reach belief, evidence, or Codex
                # state even if it wanted to.
                request, is_new, notification = self.node.rendezvous.submit(body)
                if notification:
                    print(notification, flush=True)
                self._respond(
                    200,
                    {
                        "accepted": True,
                        "request_id": request.request_id,
                        "status": request.status,
                        "is_new": is_new,
                        "note": "Join request received. This is not a trust or capability grant.",
                    },
                )
                return

            if self.path == "/message":
                message = body.get("message")
                peer_capabilities = body.get("peer_capabilities")
                if not isinstance(message, dict) or not isinstance(peer_capabilities, dict):
                    raise ValueError("message and peer_capabilities objects are required")
                self._respond(200, self.node.receive(message, peer_capabilities))
                return

            if self.path == "/connection-state":
                peer_heartbeat = body.get("peer_heartbeat")
                if peer_heartbeat is not None and not isinstance(peer_heartbeat, dict):
                    raise ValueError("peer_heartbeat must be an object or omitted")
                self._respond(200, self.node.connection_state(peer_heartbeat))
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
