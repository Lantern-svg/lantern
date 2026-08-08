"""Minimal rendezvous state for independent Lantern join requests.

The rendezvous is a door and an audit view, not a trust or capability
authority. It accepts only contact metadata, records lifecycle events in the
existing Chronicle format, and leaves handshake and message authorization to
the existing bootstrap transport.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
import json

from .core import Chronicle, KernelEvent


AWAITING_HANDSHAKE = "awaiting_handshake"
EXPIRED = "expired"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _timestamp(value: datetime | None = None) -> str:
    return (value or _now()).isoformat()


def _parse_timestamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


@dataclass(frozen=True)
class JoinRequest:
    request_id: str
    node_id: str
    protocol_version: str
    capabilities: dict[str, bool]
    timestamp: str
    peer_endpoint: str | None = None
    expires_at: str | None = None
    status: str = AWAITING_HANDSHAKE

    def to_dict(self) -> dict[str, Any]:
        return {
            "request_id": self.request_id,
            "node_id": self.node_id,
            "protocol_version": self.protocol_version,
            "capabilities": dict(self.capabilities),
            "timestamp": self.timestamp,
            "peer_endpoint": self.peer_endpoint,
            "expires_at": self.expires_at,
            "status": self.status,
        }


class JoinMonitor:
    """Track only nodes that explicitly contact this rendezvous endpoint."""

    def __init__(self, chronicle_path: str | Path, ttl_seconds: float = 900.0):
        self.chronicle = Chronicle(chronicle_path)
        self.ttl_seconds = float(ttl_seconds)
        self.requests: dict[str, JoinRequest] = {}
        self.notifications: list[str] = []
        self._rebuild()

    def _append(self, event_type: str, request: JoinRequest, status: str) -> None:
        payload = request.to_dict()
        payload["status"] = status
        self.chronicle.append(
            KernelEvent(
                event_type=event_type,
                source=request.node_id,
                payload=payload,
            )
        )

    def _rebuild(self) -> None:
        for record in self.chronicle.replay() or []:
            if record.get("type") not in {
                "JOIN_REQUESTED",
                "JOIN_DUPLICATE",
                "JOIN_EXPIRED",
            }:
                continue
            payload = record.get("payload", {})
            request_id = payload.get("request_id")
            if not request_id:
                continue
            request = JoinRequest(
                request_id=request_id,
                node_id=payload["node_id"],
                protocol_version=payload["protocol_version"],
                capabilities=dict(payload.get("capabilities", {})),
                timestamp=payload["timestamp"],
                peer_endpoint=payload.get("peer_endpoint"),
                expires_at=payload.get("expires_at"),
                status=payload.get("status", AWAITING_HANDSHAKE),
            )
            self.requests[request_id] = request

    @property
    def path(self) -> Path:
        return self.chronicle.path

    def _validate(self, payload: dict[str, Any]) -> JoinRequest:
        required = ("request_id", "node_id", "protocol_version", "capabilities", "timestamp")
        missing = [name for name in required if name not in payload]
        if missing:
            raise ValueError("Missing join fields: " + ", ".join(missing))
        if not all(
            isinstance(payload[name], str) and payload[name]
            for name in required
            if name != "capabilities"
        ):
            raise ValueError(
                "request_id, node_id, protocol_version, and timestamp must be non-empty strings"
            )
        if not isinstance(payload["capabilities"], dict):
            raise ValueError("capabilities must be an object")
        if any(not isinstance(value, bool) for value in payload["capabilities"].values()):
            raise ValueError("capabilities values must be boolean")
        endpoint = payload.get("peer_endpoint")
        if endpoint is not None and (not isinstance(endpoint, str) or not endpoint):
            raise ValueError("peer_endpoint must be a non-empty string when supplied")
        try:
            requested_at = _parse_timestamp(payload["timestamp"])
        except (TypeError, ValueError) as exc:
            raise ValueError("timestamp must be an ISO-8601 timestamp") from exc
        expires_at = _timestamp(requested_at + timedelta(seconds=self.ttl_seconds))
        return JoinRequest(
            request_id=payload["request_id"],
            node_id=payload["node_id"],
            protocol_version=payload["protocol_version"],
            capabilities=dict(payload["capabilities"]),
            timestamp=payload["timestamp"],
            peer_endpoint=endpoint,
            expires_at=expires_at,
        )

    def expire(self) -> list[JoinRequest]:
        expired: list[JoinRequest] = []
        now = _now()
        for request_id, request in list(self.requests.items()):
            if request.status != AWAITING_HANDSHAKE or not request.expires_at:
                continue
            if _parse_timestamp(request.expires_at) > now:
                continue
            updated = JoinRequest(**{**request.to_dict(), "status": EXPIRED})
            self.requests[request_id] = updated
            self._append("JOIN_EXPIRED", updated, EXPIRED)
            expired.append(updated)
        return expired

    def submit(self, payload: dict[str, Any]) -> tuple[JoinRequest, bool, str | None]:
        self.expire()
        request = self._validate(payload)
        existing = self.requests.get(request.request_id)
        if existing is not None:
            if existing.status == AWAITING_HANDSHAKE:
                self._append("JOIN_DUPLICATE", existing, existing.status)
            return existing, False, None

        self.requests[request.request_id] = request
        self._append("JOIN_REQUESTED", request, AWAITING_HANDSHAKE)
        notification = self.notification(request)
        self.notifications.append(notification)
        return request, True, notification

    def pending(self) -> list[JoinRequest]:
        self.expire()
        return [request for request in self.requests.values() if request.status == AWAITING_HANDSHAKE]

    def all_requests(self) -> list[JoinRequest]:
        self.expire()
        return list(self.requests.values())

    @staticmethod
    def notification(request: JoinRequest) -> str:
        return (
            "\U0001f56f\ufe0f LANTERN JOIN REQUEST\n\n"
            f"Node: {request.node_id}\n"
            f"Protocol: {request.protocol_version}\n"
            f"Capabilities: {sum(1 for enabled in request.capabilities.values() if enabled)}\n"
            f"Request: {request.request_id}\n"
            f"Status: {request.status}\n\n"
            "New Lantern is requesting connection."
        )

    def health(self) -> dict[str, Any]:
        return {
            "pending": len(self.pending()),
            "total": len(self.requests),
            "chronicle": str(self.path),
        }


def _format_pending(requests: list[JoinRequest]) -> str:
    lines = ["\U0001f56f\ufe0f LANTERN RENDEZVOUS", "", f"Pending: {len(requests)}", ""]
    for index, request in enumerate(requests, start=1):
        lines.append(f"{index}. Node: {request.node_id}")
        lines.append(f"   Protocol: {request.protocol_version}")
        lines.append(f"   Request: {request.request_id}")
        lines.append(f"   Status: {request.status}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Show Lantern rendezvous join requests")
    parser.add_argument("--chronicle", required=True)
    parser.add_argument("--all", action="store_true", help="Show every request, including expired ones")
    parser.add_argument("--json", action="store_true", help="Print raw JSON instead of a formatted list")
    args = parser.parse_args()
    monitor = JoinMonitor(args.chronicle)
    shown = monitor.all_requests() if args.all else monitor.pending()
    if args.json:
        print(json.dumps([request.to_dict() for request in shown], indent=2, sort_keys=True))
    else:
        print(_format_pending(shown))
