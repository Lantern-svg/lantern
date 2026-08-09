"""
Lantern Unified Protocol Boundary v0.83

Migration bridge.

Keeps existing tested:
- handshake.py
- compatibility.py
- router.py

Adds one public entry point without duplicating logic.
"""

from .router import LanternRouter, RouteResult
from .compatibility import (
    CompatibilityResult,
    negotiate,
)
from .handshake import (
    create_handshake,
)


class LanternBoundary:
    """
    Single gateway into Lantern communication.

    Does not replace existing modules yet.
    It composes them.
    """

    def __init__(self):
        self.router = LanternRouter()

    def connect(self, remote_version, remote_capabilities):
        return negotiate(remote_version, remote_capabilities)

    def receive(self, message, compatibility):
        return self.router.route(message, compatibility)

    def handshake(self):
        return create_handshake()

    def register(self, message_type, handler):
        self.router.register(message_type, handler)
