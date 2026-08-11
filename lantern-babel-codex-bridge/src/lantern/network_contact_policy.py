"""Network contact policy: pure allow/deny gate for untrusted peer endpoints.

Design note (honesty about provenance): this module implements the
``NetworkContactPolicy`` sketched as Step 4 of the Phase 3 Discord-rendezvous
plan recorded in daily memory (2026-08-10): "explicit allow/deny function run
before any outbound socket open; deny private/loopback/link-local by default
with an explicit ``allow_loopback_for_testing`` escape hatch used only by the
two-node local simulation test; no redirects; bounded timeout; bounded max
response size; per-endpoint contact attempt counter/limit." No separate
"Phase 3E" specification document exists in this repository, in memory, or
anywhere else discoverable in the workspace. The detailed rule set below
(schemes, ports, IPv4-mapped IPv6, credentials-in-URL, fragment/query
handling, malformed-input handling) is this module's own design, built on
top of that memory note and standard SSRF-prevention practice, not a
recovered prior spec. It is scoped narrowly to stay compatible with that
memory note and with the rest of Phase 3 (which is still pending).

Position in the (future) pipeline:

    untrusted peer_endpoint
        -> NetworkContactPolicy.evaluate()
        -> ALLOWED / DENIED
        -> FUTURE networking layer (transport, DNS, sockets, handshake, trust)

Scope of THIS module only:
    - Parse and classify a caller-supplied endpoint string.
    - Decide ALLOWED or DENIED using static, deterministic rules.
    - Never perform DNS resolution, socket I/O, or filesystem I/O.
    - Never grant trust or perform identity verification. A decision of
      ALLOWED means only "this endpoint is not policy-excluded"; it says
      nothing about the remote party's identity or trustworthiness.

Explicitly out of scope (left for later phases / a future networking layer):
    - Opening sockets, DNS resolution/pinning, HTTP requests, redirects,
      retries, handshakes, identity verification, trust decisions.

The module is intentionally self-contained: it imports only the Python
standard library (``ipaddress``, ``urllib.parse``, ``dataclasses``, ``enum``)
and performs zero I/O of any kind. It does not import or modify any other
``lantern`` module, and no other module is required to change for this file
to exist and be tested in isolation.
"""

from __future__ import annotations

import ipaddress
from dataclasses import dataclass, field
from enum import Enum
from typing import FrozenSet, Optional
from urllib.parse import urlsplit


class ContactDecision(str, Enum):
    """Terminal decision produced by :meth:`NetworkContactPolicy.evaluate`."""

    ALLOWED = "ALLOWED"
    DENIED = "DENIED"


# Stable, machine-checkable reason codes. Callers/tests should match on these
# rather than on the free-text `detail` field, which may change wording.
class DenyReason(str, Enum):
    MALFORMED_ENDPOINT = "MALFORMED_ENDPOINT"
    EMPTY_ENDPOINT = "EMPTY_ENDPOINT"
    DISALLOWED_SCHEME = "DISALLOWED_SCHEME"
    MISSING_HOST = "MISSING_HOST"
    CREDENTIALS_IN_URL = "CREDENTIALS_IN_URL"
    MISSING_PORT_WITH_NO_DEFAULT = "MISSING_PORT_WITH_NO_DEFAULT"
    PORT_NOT_ALLOWED = "PORT_NOT_ALLOWED"
    PORT_OUT_OF_RANGE = "PORT_OUT_OF_RANGE"
    LOCALHOST_HOSTNAME = "LOCALHOST_HOSTNAME"
    LOOPBACK_ADDRESS = "LOOPBACK_ADDRESS"
    PRIVATE_ADDRESS = "PRIVATE_ADDRESS"
    LINK_LOCAL_ADDRESS = "LINK_LOCAL_ADDRESS"
    MULTICAST_ADDRESS = "MULTICAST_ADDRESS"
    RESERVED_ADDRESS = "RESERVED_ADDRESS"
    UNSPECIFIED_ADDRESS = "UNSPECIFIED_ADDRESS"
    EMPTY_HOSTNAME_LABEL = "EMPTY_HOSTNAME_LABEL"


#: Schemes this policy will ever ALLOW. Nothing else is considered.
DEFAULT_ALLOWED_SCHEMES: FrozenSet[str] = frozenset({"https", "http"})

#: Default allowed ports when the caller does not supply an explicit
#: port allow-list. 443 (https) and 80 (http) only — least-privilege
#: default appropriate for a policy gate that has no knowledge yet of what
#: the future networking layer actually needs.
DEFAULT_ALLOWED_PORTS: FrozenSet[int] = frozenset({80, 443})

_MIN_PORT = 1
_MAX_PORT = 65535

#: Scheme -> implicit default port, used only when the endpoint omits an
#: explicit port. Standard well-known mapping; nothing implementation-magic.
_SCHEME_DEFAULT_PORT = {
    "http": 80,
    "https": 443,
}

#: Hostnames that are always denied regardless of scheme/port, because they
#: resolve (by convention, OS hosts file, or common practice) to the local
#: machine. Matched case-insensitively.
_LOCALHOST_HOSTNAMES: FrozenSet[str] = frozenset({"localhost", "localhost.localdomain"})


@dataclass(frozen=True)
class ContactVerdict:
    """Immutable result of evaluating one endpoint.

    ``decision`` is the only field callers should branch on for control
    flow. ``reason`` (present only when denied) is a stable enum for
    programmatic checks. ``detail`` is a human-readable explanation for
    logs/audits. ``normalized_host`` / ``normalized_port`` /
    ``normalized_scheme`` are included, when available, purely for
    observability (e.g. audit logging) — the future networking layer must
    still perform its own independent validation and MUST NOT skip DNS
    resolution or connection-time checks just because this dataclass
    carries a parsed host/port.
    """

    decision: ContactDecision
    reason: Optional[DenyReason] = None
    detail: str = ""
    endpoint: str = ""
    normalized_scheme: Optional[str] = None
    normalized_host: Optional[str] = None
    normalized_port: Optional[int] = None

    @property
    def allowed(self) -> bool:
        return self.decision is ContactDecision.ALLOWED


def _deny(
    endpoint: str,
    reason: DenyReason,
    detail: str,
    *,
    scheme: Optional[str] = None,
    host: Optional[str] = None,
    port: Optional[int] = None,
) -> ContactVerdict:
    return ContactVerdict(
        decision=ContactDecision.DENIED,
        reason=reason,
        detail=detail,
        endpoint=endpoint,
        normalized_scheme=scheme,
        normalized_host=host,
        normalized_port=port,
    )


def _allow(endpoint: str, scheme: str, host: str, port: int) -> ContactVerdict:
    return ContactVerdict(
        decision=ContactDecision.ALLOWED,
        reason=None,
        detail="endpoint passed all policy checks",
        endpoint=endpoint,
        normalized_scheme=scheme,
        normalized_host=host,
        normalized_port=port,
    )


def _strip_ipv6_brackets(host: str) -> str:
    if len(host) >= 2 and host[0] == "[" and host[-1] == "]":
        return host[1:-1]
    return host


def _classify_ip(addr: "ipaddress._BaseAddress") -> Optional[DenyReason]:
    """Return the DenyReason for a parsed IP address, or None if not denied
    on address-classification grounds. IPv4-mapped IPv6 addresses
    (``::ffff:a.b.c.d``) are unwrapped to their embedded IPv4 form first,
    so e.g. ``::ffff:127.0.0.1`` is treated exactly like ``127.0.0.1``.
    """
    if isinstance(addr, ipaddress.IPv6Address) and addr.ipv4_mapped is not None:
        addr = addr.ipv4_mapped

    if addr.is_loopback:
        return DenyReason.LOOPBACK_ADDRESS
    if addr.is_unspecified:
        return DenyReason.UNSPECIFIED_ADDRESS
    if addr.is_link_local:
        return DenyReason.LINK_LOCAL_ADDRESS
    if addr.is_multicast:
        return DenyReason.MULTICAST_ADDRESS
    if addr.is_private:
        return DenyReason.PRIVATE_ADDRESS
    if addr.is_reserved:
        return DenyReason.RESERVED_ADDRESS
    return None


@dataclass(frozen=True)
class NetworkContactPolicy:
    """Pure, deterministic, zero-I/O allow/deny gate for peer endpoints.

    This class performs no DNS resolution: a bare hostname (e.g.
    ``https://peer.example.com``) is validated syntactically only (scheme,
    port, credential absence, hostname well-formedness) and, if it passes
    those checks, is ALLOWED at the policy layer. It is NOT resolved to an
    IP address here, so it cannot be checked against private/loopback IP
    ranges at this stage — that is why the future networking layer MUST
    re-validate the resolved address before connecting (DNS rebinding /
    "TOCTOU" protection is explicitly out of scope for this pure policy
    module; see KNOWN_LIMITATIONS in the implementation report). Endpoints
    that are themselves literal IP addresses (IPv4, IPv6, bracketed IPv6,
    or IPv4-mapped IPv6) ARE checked against private/loopback/link-local/
    multicast/reserved/unspecified ranges here, since that requires no I/O.

    Attributes:
        allowed_schemes: schemes this policy instance will ever ALLOW.
        allowed_ports: caller-supplied port allow-list. If ``None``, the
            module default (:data:`DEFAULT_ALLOWED_PORTS`) is used. Pass an
            explicit (possibly empty) frozenset to override.
        allow_loopback_for_testing: escape hatch matching the Phase 3
            memory note, for local two-node simulation tests only. Must
            never be set true in a path that can be reached from an
            untrusted announcement (e.g. a Discord-sourced endpoint).
    """

    allowed_schemes: FrozenSet[str] = field(default_factory=lambda: DEFAULT_ALLOWED_SCHEMES)
    allowed_ports: Optional[FrozenSet[int]] = None
    allow_loopback_for_testing: bool = False

    def _effective_allowed_ports(self) -> FrozenSet[int]:
        if self.allowed_ports is None:
            return DEFAULT_ALLOWED_PORTS
        return self.allowed_ports

    def evaluate(self, peer_endpoint: object) -> ContactVerdict:
        """Evaluate one untrusted endpoint. Never raises for malformed
        input; malformed input is reported as a DENIED verdict. Performs
        zero network, DNS, or filesystem I/O; purely string/data parsing.
        """
        # --- Type / emptiness guards -----------------------------------
        if not isinstance(peer_endpoint, str):
            return _deny(
                str(peer_endpoint),
                DenyReason.MALFORMED_ENDPOINT,
                "peer_endpoint must be a string",
            )

        endpoint = peer_endpoint
        stripped = endpoint.strip()
        if stripped == "":
            return _deny(endpoint, DenyReason.EMPTY_ENDPOINT, "peer_endpoint is empty")

        # Reject ANY whitespace or control characters, including ones at the
        # very start/end that `.strip()` would otherwise silently remove —
        # we scan the ORIGINAL string, not the stripped one, so a trailing
        # "\n" or leading "\t" cannot smuggle a hostname past this check.
        # These are never valid in a URL authority and are a common
        # smuggling vector (e.g. CRLF/header injection, lookalike hosts).
        if any(ch.isspace() for ch in endpoint) or any(ord(ch) < 0x20 for ch in endpoint):
            return _deny(
                endpoint,
                DenyReason.MALFORMED_ENDPOINT,
                "peer_endpoint contains whitespace or control characters",
            )

        try:
            parts = urlsplit(stripped)
        except ValueError as exc:
            return _deny(endpoint, DenyReason.MALFORMED_ENDPOINT, f"unparsable endpoint: {exc}")

        scheme = (parts.scheme or "").lower()
        if scheme == "":
            return _deny(endpoint, DenyReason.MALFORMED_ENDPOINT, "endpoint has no scheme")
        if scheme not in self.allowed_schemes:
            return _deny(
                endpoint,
                DenyReason.DISALLOWED_SCHEME,
                f"scheme {scheme!r} is not in the allowed set",
                scheme=scheme,
            )

        # --- Credential rejection ---------------------------------------
        # urlsplit never raises on a malformed authority for http(s); userinfo
        # (user:pass@) is only detected via `.username`/`.password`, which
        # itself can raise ValueError on structurally invalid authorities
        # (e.g. an invalid port). Guard both paths explicitly.
        try:
            has_credentials = bool(parts.username) or bool(parts.password)
        except ValueError:
            return _deny(
                endpoint,
                DenyReason.MALFORMED_ENDPOINT,
                "endpoint authority component is malformed",
                scheme=scheme,
            )
        if has_credentials:
            return _deny(
                endpoint,
                DenyReason.CREDENTIALS_IN_URL,
                "embedded credentials (user:pass@) are not permitted",
                scheme=scheme,
            )
        # Also reject the raw '@' form defensively even if username/password
        # parsing above didn't flag it (belt-and-suspenders against parser
        # quirks across Python versions).
        if "@" in (parts.netloc or ""):
            return _deny(
                endpoint,
                DenyReason.CREDENTIALS_IN_URL,
                "embedded credentials (user:pass@) are not permitted",
                scheme=scheme,
            )

        try:
            hostname = parts.hostname
        except ValueError:
            return _deny(
                endpoint,
                DenyReason.MALFORMED_ENDPOINT,
                "endpoint authority component is malformed",
                scheme=scheme,
            )

        if not hostname:
            return _deny(endpoint, DenyReason.MISSING_HOST, "endpoint has no host", scheme=scheme)

        hostname = hostname.lower()

        # --- Port resolution ----------------------------------------------
        try:
            explicit_port = parts.port
        except ValueError:
            return _deny(
                endpoint,
                DenyReason.PORT_OUT_OF_RANGE,
                "port is not a valid integer in range",
                scheme=scheme,
                host=hostname,
            )

        if explicit_port is None:
            default_port = _SCHEME_DEFAULT_PORT.get(scheme)
            if default_port is None:
                return _deny(
                    endpoint,
                    DenyReason.MISSING_PORT_WITH_NO_DEFAULT,
                    f"no port supplied and scheme {scheme!r} has no default port",
                    scheme=scheme,
                    host=hostname,
                )
            port = default_port
        else:
            port = explicit_port

        if not (_MIN_PORT <= port <= _MAX_PORT):
            return _deny(
                endpoint,
                DenyReason.PORT_OUT_OF_RANGE,
                f"port {port} is out of the valid 1-65535 range",
                scheme=scheme,
                host=hostname,
            )

        allowed_ports = self._effective_allowed_ports()
        if port not in allowed_ports:
            return _deny(
                endpoint,
                DenyReason.PORT_NOT_ALLOWED,
                f"port {port} is not in the allowed port set",
                scheme=scheme,
                host=hostname,
                port=port,
            )

        # --- Localhost hostname rejection ---------------------------------
        if hostname in _LOCALHOST_HOSTNAMES and not self.allow_loopback_for_testing:
            return _deny(
                endpoint,
                DenyReason.LOCALHOST_HOSTNAME,
                "localhost hostnames are denied by default",
                scheme=scheme,
                host=hostname,
                port=port,
            )

        # --- Literal-IP classification (no DNS) ----------------------------
        raw_host = _strip_ipv6_brackets(hostname)
        try:
            addr = ipaddress.ip_address(raw_host)
        except ValueError:
            addr = None

        if addr is not None:
            deny_reason = _classify_ip(addr)
            if deny_reason == DenyReason.LOOPBACK_ADDRESS and self.allow_loopback_for_testing:
                deny_reason = None
            if deny_reason is not None:
                return _deny(
                    endpoint,
                    deny_reason,
                    f"literal IP address {raw_host} is disallowed ({deny_reason.value})",
                    scheme=scheme,
                    host=hostname,
                    port=port,
                )
            return _allow(endpoint, scheme, hostname, port)

        # --- Hostname (non-literal-IP) well-formedness ----------------------
        # Not resolved here (no DNS I/O). Only syntactic sanity is checked:
        # non-empty labels, no leading/trailing dot artifacts producing an
        # empty label, and total length sanity is left to the future
        # networking layer's own resolver.
        labels = hostname.split(".")
        if any(label == "" for label in labels):
            return _deny(
                endpoint,
                DenyReason.EMPTY_HOSTNAME_LABEL,
                "hostname contains an empty label (e.g. leading/trailing/doubled dot)",
                scheme=scheme,
                host=hostname,
                port=port,
            )

        return _allow(endpoint, scheme, hostname, port)
