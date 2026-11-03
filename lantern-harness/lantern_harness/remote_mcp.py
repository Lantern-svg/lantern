"""Remote MCP transport for the Lantern contact tools (Streamable HTTP).

Design constraints, enforced here rather than documented hopefully:

* Read-only surface: the remote server exposes ONLY the six contact tools,
  built by the same registration function the stdio server uses. There is no
  posting, no key creation, no key export, no identity rotation, and no
  configuration mutation tool. Authentication never implies authority.
* Off by default. `remote_mcp.enabled` must be true and a token must be
  supplied through an environment variable. No token is ever read from the
  config file, committed, or logged.
* Loopback by default. Binding to a non-loopback interface requires
  `allow_network_bind` AND `require_https`; the process refuses otherwise.
* Every request is authenticated (constant-time compare), rate limited,
  size limited, and host/origin checked. Failures are logged without secrets.

Nothing here deploys, tunnels, or opens a public port on its own.
"""

from __future__ import annotations

import json
import logging
import os
import secrets
import time
from collections import deque
from dataclasses import dataclass, field

logger = logging.getLogger("lantern.remote_mcp")

DEFAULT_PATH = "/mcp"
DEFAULT_TOKEN_ENV = "LANTERN_REMOTE_MCP_TOKEN"
LOOPBACK_HOSTS = {"127.0.0.1", "::1", "localhost"}


class RemoteMCPConfigError(RuntimeError):
    """Configuration is unsafe or incomplete; the server must not start."""


@dataclass
class RemoteMCPConfig:
    enabled: bool = False
    host: str = "127.0.0.1"
    port: int = 8765
    path: str = DEFAULT_PATH
    token_env: str = DEFAULT_TOKEN_ENV
    no_auth: bool = False  # explicit operator choice; loopback only, warns loudly
    allow_network_bind: bool = False
    require_https: bool = False
    allowed_hosts: list = field(default_factory=list)
    allowed_origins: list = field(default_factory=list)
    max_body_bytes: int = 262_144
    rate_limit_per_minute: int = 60
    stateless: bool = True

    @classmethod
    def from_config(cls, cfg: dict | None) -> "RemoteMCPConfig":
        section = (cfg or {}).get("remote_mcp") or {}
        conf = cls(
            enabled=bool(section.get("enabled", False)),
            host=str(section.get("host", "127.0.0.1")),
            port=int(section.get("port", 8765)),
            path=str(section.get("path", DEFAULT_PATH)),
            token_env=str(section.get("token_env", DEFAULT_TOKEN_ENV)),
            no_auth=bool(section.get("no_auth", False)),
            allow_network_bind=bool(section.get("allow_network_bind", False)),
            require_https=bool(section.get("require_https", False)),
            allowed_hosts=list(section.get("allowed_hosts") or []),
            allowed_origins=list(section.get("allowed_origins") or []),
            max_body_bytes=int(section.get("max_body_bytes", 262_144)),
            rate_limit_per_minute=int(section.get("rate_limit_per_minute", 60)),
            stateless=bool(section.get("stateless", True)),
        )
        if os.environ.get("LANTERN_REMOTE_MCP_ENABLED") == "1":
            conf.enabled = True
        return conf

    def validate(self) -> None:
        if not self.path.startswith("/"):
            raise RemoteMCPConfigError("remote_mcp.path must start with '/'")
        if self.port < 1 or self.port > 65535:
            raise RemoteMCPConfigError("remote_mcp.port out of range")
        if self.max_body_bytes < 1024 or self.max_body_bytes > 8_388_608:
            raise RemoteMCPConfigError("remote_mcp.max_body_bytes must be 1KB..8MB")
        if self.rate_limit_per_minute < 1:
            raise RemoteMCPConfigError("remote_mcp.rate_limit_per_minute must be >= 1")
        if self.host not in LOOPBACK_HOSTS:
            if not self.allow_network_bind:
                raise RemoteMCPConfigError(
                    "refusing to bind %r: set remote_mcp.allow_network_bind=true only "
                    "after an explicit operator decision" % self.host)
            if not self.require_https:
                raise RemoteMCPConfigError(
                    "non-loopback bind requires remote_mcp.require_https=true "
                    "(terminate TLS at a reverse proxy and forward X-Forwarded-Proto)")
        if not self.token_env:
            raise RemoteMCPConfigError("remote_mcp.token_env must name an environment variable")
        if self.no_auth and self.host not in LOOPBACK_HOSTS:
            raise RemoteMCPConfigError(
                "no-auth mode is loopback-only; refusing to disable authentication on %r" % self.host)


# --------------------------------------------------------------------- auth

def _json_response(status: int, body: dict, extra_headers=None):
    from starlette.responses import JSONResponse
    return JSONResponse(body, status_code=status, headers=extra_headers or {})


class RemoteAuth:
    """Bearer-token authentication. The expected token lives only in the
    environment; it is compared in constant time and never logged."""

    def __init__(self, token_env: str):
        self.token_env = token_env

    def expected(self) -> str:
        value = os.environ.get(self.token_env, "")
        if len(value) < 24:
            raise RemoteMCPConfigError(
                "environment variable %s must hold a token of at least 24 characters"
                % self.token_env)
        return value

    def check(self, scope) -> bool:
        headers = dict(scope.get("headers") or [])
        raw = headers.get(b"authorization", b"").decode("latin-1")
        if not raw.startswith("Bearer "):
            return False
        presented = raw[len("Bearer "):].strip()
        return secrets.compare_digest(presented, self.expected())


class AuthMiddleware:
    def __init__(self, app, auth: RemoteAuth, require_https: bool = False):
        self.app = app
        self.auth = auth
        self.require_https = require_https

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)

        if self.require_https:
            headers = dict(scope.get("headers") or [])
            forwarded = headers.get(b"x-forwarded-proto", b"").decode("latin-1")
            scheme = forwarded.split(",")[0].strip() if forwarded else scope.get("scheme", "http")
            if scheme != "https":
                return await _json_response(400, {"error": "HTTPS_REQUIRED"})(scope, receive, send)

        try:
            ok = self.auth.check(scope)
        except RemoteMCPConfigError as exc:
            logger.error("remote MCP misconfigured: %s", exc)
            return await _json_response(500, {"error": "SERVER_MISCONFIGURED"})(scope, receive, send)

        if not ok:
            client = scope.get("client") or ("unknown", 0)
            # Log the failure, never the credential.
            logger.warning("remote MCP authentication failed from %s", client[0])
            return await _json_response(
                401, {"error": "UNAUTHORIZED"},
                {"WWW-Authenticate": 'Bearer realm="lantern-contact"'})(scope, receive, send)

        return await self.app(scope, receive, send)


class RateLimitMiddleware:
    def __init__(self, app, per_minute: int):
        self.app = app
        self.per_minute = per_minute
        self._hits: dict = {}

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        client = (scope.get("client") or ("unknown", 0))[0]
        now = time.time()
        window = self._hits.setdefault(client, deque())
        while window and now - window[0] > 60.0:
            window.popleft()
        if len(window) >= self.per_minute:
            retry = max(1, int(60 - (now - window[0])))
            return await _json_response(
                429, {"error": "RATE_LIMITED"},
                {"Retry-After": str(retry)})(scope, receive, send)
        window.append(now)
        return await self.app(scope, receive, send)


class BodyLimitMiddleware:
    def __init__(self, app, max_bytes: int):
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        headers = dict(scope.get("headers") or [])
        declared = headers.get(b"content-length")
        if declared:
            try:
                if int(declared) > self.max_bytes:
                    return await _json_response(413, {"error": "REQUEST_TOO_LARGE"})(scope, receive, send)
            except ValueError:
                return await _json_response(400, {"error": "BAD_CONTENT_LENGTH"})(scope, receive, send)

        received = {"n": 0}

        async def limited_receive():
            message = await receive()
            if message["type"] == "http.request":
                received["n"] += len(message.get("body", b""))
                if received["n"] > self.max_bytes:
                    raise RequestTooLarge()
            return message

        try:
            return await self.app(scope, limited_receive, send)
        except RequestTooLarge:
            return await _json_response(413, {"error": "REQUEST_TOO_LARGE"})(scope, receive, send)


class RequestTooLarge(Exception):
    pass


# --------------------------------------------------------------------- app


# The public contract of the remote surface. If anything else is ever
# registered, the remote app refuses to build.
CONTACT_MCP_TOOL_NAMES = (
    "lantern_contact_agent_card",
    "lantern_contact_skill",
    "lantern_contact_board_read",
    "lantern_contact_board_verify",
    "lantern_contact_report",
    "lantern_contact_status",
)


def _assert_only_contact_tools(server) -> None:
    """Refuse to serve anything other than the six read-only contact tools."""
    import asyncio

    tools = asyncio.run(server.list_tools())
    names = tuple(sorted(t.name for t in tools))
    expected = tuple(sorted(CONTACT_MCP_TOOL_NAMES))
    if names != expected:
        extra = sorted(set(names) - set(expected))
        missing = sorted(set(expected) - set(names))
        raise RemoteMCPConfigError(
            "remote surface must expose exactly the six contact tools; "
            "extra=%s missing=%s" % (extra, missing))


def build_remote_app(context=None, cfg: RemoteMCPConfig | None = None):
    """Return the ASGI app for the remote contact surface.

    Reuses build_contact_server(), which registers the six contact tools and
    nothing else. No write-capable tool exists anywhere in this graph.
    """
    from mcp.server.transport_security import TransportSecuritySettings

    from .mcp_server import build_contact_server

    cfg = cfg or RemoteMCPConfig.from_config(None)
    cfg.validate()
    if not cfg.enabled:
        raise RemoteMCPConfigError("remote_mcp.enabled is false; refusing to build the remote app")
    if cfg.no_auth:
        # Owner's explicit choice (two-step, per decision B). Loud, and only ever
        # legal on loopback because validate() refuses anything else.
        print(json.dumps({
            "WARNING": "AUTHENTICATION DISABLED (no_auth)",
            "detail": ("read-only contact surface exposed without credentials; "
                       "loopback only; suitable for a temporary tunnel test only"),
            "host": cfg.host, "port": cfg.port, "path": cfg.path}), flush=True)
        auth = None
    else:
        if not os.environ.get(cfg.token_env):
            raise RemoteMCPConfigError(
                "environment variable %s is not set; refusing to start unauthenticated" % cfg.token_env)
        auth = RemoteAuth(cfg.token_env)
        auth.expected()  # fail fast on a weak/missing token

    # The remote surface exists only after an explicit operator decision plus a
    # token. Enabling the contact read path here is therefore not an implicit
    # grant of capability: it permits the six read-only tools to answer instead
    # of returning NOT_CONFIGURED. No write path exists in this graph at all.
    if context is None:
        from .mcp_server import LanternMCPContext
        context = LanternMCPContext()
        context.contact.enabled = True
        # Remote reads must not append Observations to the local evidence store:
        # the remote surface formats and returns, it does not store. (Directive
        # condition 2: contact_report must never write, post, send, or store.)
        context.contact.bridge = None
    server = build_contact_server(context)
    _assert_only_contact_tools(server)
    security = TransportSecuritySettings(
        enable_dns_rebinding_protection=bool(cfg.allowed_hosts or cfg.allowed_origins),
        allowed_hosts=cfg.allowed_hosts or [],
        allowed_origins=cfg.allowed_origins or [],
    )
    app = server.streamable_http_app(
        streamable_http_path=cfg.path,
        json_response=True,
        stateless_http=cfg.stateless,
        max_request_body_size=cfg.max_body_bytes,
        transport_security=security,
        host=cfg.host,
    )

    # Outermost first: rate limit -> auth -> body limit -> MCP app.
    app = BodyLimitMiddleware(app, cfg.max_body_bytes)
    if auth is not None:
        app = AuthMiddleware(app, auth, require_https=cfg.require_https)
    app = RateLimitMiddleware(app, cfg.rate_limit_per_minute)
    return app


def main(argv=None) -> int:
    """Entry point. Refuses unsafe configuration; never opens a port on its own."""
    import argparse

    from .config import load_config

    parser = argparse.ArgumentParser(prog="lantern-harness-mcp-remote")
    parser.add_argument("--check", action="store_true", help="validate configuration and exit")
    parser.add_argument(
        "--no-auth", action="store_true",
        help="DISABLE authentication for this run (operator decision; loopback only; "
             "prints a warning). Off by default and never persisted to config.")
    args = parser.parse_args(argv)

    cfg = RemoteMCPConfig.from_config(load_config())
    if args.no_auth:
        cfg.no_auth = True
    try:
        cfg.validate()
        if not cfg.enabled:
            raise RemoteMCPConfigError(
                "remote_mcp.enabled is false. Remote exposure is an explicit operator decision.")
    except RemoteMCPConfigError as exc:
        print(json.dumps({"status": "NOT_CONFIGURED", "detail": str(exc)}))
        return 2

    if args.check:
        print(json.dumps({"status": "CONFIGURED", "host": cfg.host, "port": cfg.port,
                          "path": cfg.path, "https_required": cfg.require_https,
                          "tools": "contact (read-only, six)"}))
        return 0

    try:
        app = build_remote_app(cfg=cfg)
    except RemoteMCPConfigError as exc:
        print(json.dumps({"status": "BLOCKED", "detail": str(exc)}))
        return 2

    import uvicorn

    if cfg.host not in LOOPBACK_HOSTS:
        print(json.dumps({"warning": "binding non-loopback; TLS must terminate at a reverse proxy",
                          "host": cfg.host, "port": cfg.port}))
    uvicorn.run(app, host=cfg.host, port=cfg.port, log_level="info")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
