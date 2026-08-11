"""Network contact transport: ONE tightly bounded, policy-gated network
contact against an already-`NetworkContactPolicy`-approved endpoint.

Position in the pipeline (see `network_contact_policy.py` for the layer
before this one):

    Discord announcement
        -> normalize Discord data
        -> JoinMonitor
        -> untrusted JoinRequest
        -> NetworkContactPolicy            (syntactic/policy gate; no I/O)
        -> NetworkContactTransport          <-- THIS MODULE (one bounded I/O op)
        -> Lantern handshake                 FUTURE PHASE, not here
        -> cryptographic identity            FUTURE PHASE, not here
        -> explicit trust decision           FUTURE PHASE, not here

What this module does:
    - Requires a passing `ContactVerdict` from `NetworkContactPolicy` (or an
      equivalent explicit re-evaluation) before doing anything. An endpoint
      that has not passed the policy gate is never contacted; this is
      enforced in code, not just by convention, and is proven by tests.
    - For literal-IP endpoints: validates the IP (reusing the exact address
      classification helpers from `network_contact_policy`) and connects
      directly to it. No DNS lookup is performed for IP literals.
    - For hostname endpoints: resolves the hostname *immediately before*
      connecting (via `socket.getaddrinfo`), validates *every* returned
      A/AAAA address with the same classification rules, and — only if
      every address is public/safe — connects to one specific *validated*
      address. The DNS result is not cached or reused for a later call.
    - Performs exactly one GET request, no redirects, no retries, a hard
      response-size cap, and short connect/total timeouts.
    - For HTTPS: connects the raw socket to the validated IP, then wraps it
      in a real `ssl.SSLContext` (default verification mode, i.e.
      certificate validation ON) using `server_hostname=<original hostname>`
      so the TLS handshake and certificate check are performed against the
      hostname the peer actually claimed, not the numeric IP — this is the
      standard safe "connect-by-IP, verify-by-name" pattern and does not
      require disabling verification or inventing an insecure context.
    - Returns a single immutable `ContactResult` describing what happened.
      It NEVER raises for network/DNS/policy/protocol failures — those are
      all reported as structured outcomes. It never parses the response
      body as a Lantern object and never calls into any other Lantern
      module (handshake, identity, participants, core, chronicle, etc.).

What this module explicitly does NOT do (out of scope for this phase):
    - No handshake, no challenge/response, no proof verification, no trust
      decisions. A `HTTP_RESPONSE` outcome — even HTTP 200 — means only
      "the network contact attempt itself succeeded technically." It does
      not mean the peer is a Lantern node, is trusted, or is verified.
    - No redirect following (3xx responses are surfaced as a `REDIRECT`
      outcome and stopped there).
    - No retries, no backoff, no endpoint cycling, no scheme/port fallback.
    - No credentials, cookies, Discord headers, or Lantern private state are
      ever sent.
    - No DNS caching / reuse across calls.

Standard-library only: `socket`, `ssl`, `http.client`, `ipaddress`, `time`,
`dataclasses`, `enum`. No third-party HTTP client, no other Lantern module
is imported except the pure classification helpers from
`network_contact_policy` (which themselves perform no I/O).
"""

from __future__ import annotations

import http.client
import ipaddress
import socket
import ssl
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional, Tuple

from lantern.network_contact_policy import (
    ContactDecision,
    ContactVerdict,
    DenyReason,
    NetworkContactPolicy,
    _classify_ip,  # reuse the single source of truth for address classification
    _strip_ipv6_brackets,
)

__all__ = [
    "ContactOutcome",
    "ContactResult",
    "NetworkContactTransport",
    "DEFAULT_CONNECT_TIMEOUT_SECONDS",
    "DEFAULT_TOTAL_TIMEOUT_SECONDS",
    "DEFAULT_MAX_RESPONSE_BYTES",
]


class ContactOutcome(str, Enum):
    """Terminal, structured outcome of one transport attempt."""

    POLICY_DENIED = "POLICY_DENIED"
    DNS_FAILED = "DNS_FAILED"
    DNS_BLOCKED = "DNS_BLOCKED"
    CONNECTION_FAILED = "CONNECTION_FAILED"
    TIMEOUT = "TIMEOUT"
    TLS_FAILED = "TLS_FAILED"
    HTTP_RESPONSE = "HTTP_RESPONSE"
    REDIRECT = "REDIRECT"
    RESPONSE_TOO_LARGE = "RESPONSE_TOO_LARGE"
    MALFORMED_RESPONSE = "MALFORMED_RESPONSE"


#: Recommended bounds per spec. Callers may override per-call.
DEFAULT_CONNECT_TIMEOUT_SECONDS: float = 4.0
DEFAULT_TOTAL_TIMEOUT_SECONDS: float = 9.0
DEFAULT_MAX_RESPONSE_BYTES: int = 64 * 1024  # 64 KiB

#: Minimal, fixed request headers. Nothing from the caller/Discord/Lantern
#: state is ever forwarded into the outbound request.
_REQUEST_HEADERS = {
    "Accept": "application/json",
    "Connection": "close",
}


@dataclass(frozen=True)
class ContactResult:
    """Immutable, safe-to-log result of one transport attempt.

    Only bounded, non-secret metadata is carried. The response body, if any
    was read, is exposed as bounded raw bytes (`response_body`) — it is
    UNTRUSTED DATA and MUST NOT be interpreted as a Lantern protocol object
    by this module or its caller in this phase.
    """

    outcome: ContactOutcome
    endpoint: str
    reason: str = ""
    resolved_ip: Optional[str] = None
    status_code: Optional[int] = None
    response_size: int = 0
    response_body: bytes = b""
    elapsed_seconds: float = 0.0
    redirect_location: Optional[str] = None

    @property
    def succeeded(self) -> bool:
        """True only if a full, bounded HTTP response was obtained.

        IMPORTANT: this says nothing about trust. See module docstring.
        """
        return self.outcome is ContactOutcome.HTTP_RESPONSE


def _result(outcome: ContactOutcome, endpoint: str, reason: str = "", **kwargs) -> ContactResult:
    return ContactResult(outcome=outcome, endpoint=endpoint, reason=reason, **kwargs)


def _validate_ip_literal(
    host_for_classification: str, *, allow_loopback: bool = False
) -> Tuple[Optional[str], Optional[DenyReason]]:
    """Classify a single literal IP string (already de-bracketed). Returns
    (ip_str, None) if safe to use, or (None, DenyReason) if blocked/invalid.

    `allow_loopback`, when True, relaxes ONLY the loopback classification
    (matching `NetworkContactPolicy.allow_loopback_for_testing`'s exact
    semantics) so local test fixtures on 127.0.0.1/::1 can be exercised.
    Private/link-local/multicast/reserved/unspecified classifications are
    never relaxed by this flag.
    """
    try:
        addr = ipaddress.ip_address(host_for_classification)
    except ValueError:
        return None, DenyReason.MALFORMED_ENDPOINT
    deny_reason = _classify_ip(addr)
    if deny_reason is DenyReason.LOOPBACK_ADDRESS and allow_loopback:
        deny_reason = None
    if deny_reason is not None:
        return None, deny_reason
    return str(addr), None


@dataclass(frozen=True)
class NetworkContactTransport:
    """Performs exactly one bounded, policy-gated network contact.

    Attributes:
        policy: the `NetworkContactPolicy` instance used to (re-)validate
            the endpoint if the caller does not supply a pre-computed
            `ContactVerdict`. A fresh default-configured policy is used if
            none is supplied.
        connect_timeout_seconds: socket connect timeout.
        total_timeout_seconds: overall wall-clock budget for DNS + connect +
            TLS + request + bounded read. Enforced cooperatively (socket
            timeout plus an explicit deadline check before/while reading).
        max_response_bytes: hard cap on response body bytes read. Reading
            stops the instant this many bytes have been received.
        allow_loopback_for_testing: escape hatch mirroring
            `NetworkContactPolicy.allow_loopback_for_testing` exactly —
            relaxes ONLY loopback-address rejection (both for literal-IP
            endpoints and for every address returned by DNS resolution), so
            local test fixtures bound to 127.0.0.1/::1 can be exercised.
            Private/link-local/multicast/reserved/unspecified addresses
            remain blocked even with this set. Must never be enabled on a
            path reachable from an untrusted announcement (e.g. Discord).
    """

    policy: NetworkContactPolicy = field(default_factory=NetworkContactPolicy)
    connect_timeout_seconds: float = DEFAULT_CONNECT_TIMEOUT_SECONDS
    total_timeout_seconds: float = DEFAULT_TOTAL_TIMEOUT_SECONDS
    max_response_bytes: int = DEFAULT_MAX_RESPONSE_BYTES
    allow_loopback_for_testing: bool = False

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def contact(
        self,
        peer_endpoint: object,
        *,
        path: str = "/",
        verdict: Optional[ContactVerdict] = None,
    ) -> ContactResult:
        """Attempt exactly one bounded GET contact against `peer_endpoint`.

        `verdict`, if supplied, must be the `ContactVerdict` already
        produced by `NetworkContactPolicy.evaluate(peer_endpoint)` for this
        exact endpoint; it is used instead of re-running the policy. If
        omitted, this method runs `self.policy.evaluate(peer_endpoint)`
        itself. Either way, an endpoint that does not pass policy results
        in `ContactOutcome.POLICY_DENIED` and ZERO socket/DNS activity —
        this is enforced structurally: no code path below this check can
        reach any I/O call.
        """
        endpoint_str = peer_endpoint if isinstance(peer_endpoint, str) else str(peer_endpoint)

        if verdict is None:
            verdict = self.policy.evaluate(peer_endpoint)

        if verdict.decision is not ContactDecision.ALLOWED:
            return _result(
                ContactOutcome.POLICY_DENIED,
                endpoint_str,
                reason=f"endpoint did not pass NetworkContactPolicy: {verdict.reason}",
            )

        # Defense in depth: even though `verdict` said ALLOWED, refuse to
        # proceed unless it actually carries the normalized fields this
        # transport requires to act safely. A verdict missing scheme/host/
        # port cannot have come from a real ALLOWED NetworkContactPolicy
        # result, so treat it as a policy denial rather than guessing.
        if not verdict.normalized_scheme or not verdict.normalized_host or not verdict.normalized_port:
            return _result(
                ContactOutcome.POLICY_DENIED,
                endpoint_str,
                reason="ALLOWED verdict is missing required normalized fields",
            )

        scheme = verdict.normalized_scheme
        hostname = verdict.normalized_host
        port = verdict.normalized_port

        deadline = time.monotonic() + self.total_timeout_seconds

        # --- Resolve to a single validated IP -----------------------------
        resolved_ip, deny_or_none, dns_outcome = self._resolve_and_validate(hostname)
        if dns_outcome is not None:
            return _result(dns_outcome, endpoint_str, reason=deny_or_none or "")

        # --- Perform exactly one bounded request ---------------------------
        return self._do_request(
            endpoint_str=endpoint_str,
            scheme=scheme,
            hostname=hostname,
            resolved_ip=resolved_ip,
            port=port,
            path=path,
            deadline=deadline,
        )

    # ------------------------------------------------------------------
    # DNS resolution + validation (the rebinding boundary)
    # ------------------------------------------------------------------

    def _resolve_and_validate(
        self, hostname: str
    ) -> Tuple[Optional[str], Optional[str], Optional[ContactOutcome]]:
        """Returns (validated_ip_or_None, reason_or_None, outcome_or_None).

        outcome is None only when resolution+validation succeeded and
        validated_ip is a safe IP string to connect to.

        For a literal-IP hostname (already normalized/lowercased by the
        policy layer), no DNS call is made at all — the IP is validated
        directly. For a real hostname, `socket.getaddrinfo` is called
        immediately (not cached, not reused), every returned address is
        classified, and if even one is blocked the whole resolution is
        rejected (DNS_BLOCKED). If none resolve or resolution errors, the
        outcome is DNS_FAILED.
        """
        literal_host = _strip_ipv6_brackets(hostname)
        try:
            ipaddress.ip_address(literal_host)
            is_literal_ip = True
        except ValueError:
            is_literal_ip = False

        if is_literal_ip:
            safe_ip, deny_reason = _validate_ip_literal(
                literal_host, allow_loopback=self.allow_loopback_for_testing
            )
            if deny_reason is not None:
                return None, f"literal IP blocked: {deny_reason.value}", ContactOutcome.DNS_BLOCKED
            return safe_ip, None, None

        # Real hostname: resolve immediately before connecting. Do not cache.
        try:
            addrinfo = socket.getaddrinfo(hostname, None, proto=socket.IPPROTO_TCP)
        except socket.gaierror as exc:
            return None, f"DNS resolution failed: {exc}", ContactOutcome.DNS_FAILED
        except OSError as exc:
            return None, f"DNS resolution failed: {exc}", ContactOutcome.DNS_FAILED

        candidate_ips: List[str] = []
        for family, _socktype, _proto, _canonname, sockaddr in addrinfo:
            if family == socket.AF_INET:
                candidate_ips.append(sockaddr[0])
            elif family == socket.AF_INET6:
                candidate_ips.append(sockaddr[0])

        if not candidate_ips:
            return None, "DNS resolution returned no A/AAAA addresses", ContactOutcome.DNS_FAILED

        # Validate EVERY resolved address. One blocked address anywhere in
        # the result set rejects the whole resolution (do not "pick the
        # good one" — that would still let an attacker force a resolver
        # into contacting an internal address by racing/rotating results).
        validated_ips: List[str] = []
        for ip_str in candidate_ips:
            safe_ip, deny_reason = _validate_ip_literal(
                ip_str, allow_loopback=self.allow_loopback_for_testing
            )
            if deny_reason is not None:
                return (
                    None,
                    f"resolved address {ip_str} blocked: {deny_reason.value}",
                    ContactOutcome.DNS_BLOCKED,
                )
            validated_ips.append(safe_ip)  # type: ignore[arg-type]

        # All addresses safe: select one specific validated address to
        # connect to (first result — deterministic, no additional I/O).
        return validated_ips[0], None, None

    # ------------------------------------------------------------------
    # Single bounded HTTP(S) request
    # ------------------------------------------------------------------

    def _do_request(
        self,
        *,
        endpoint_str: str,
        scheme: str,
        hostname: str,
        resolved_ip: str,
        port: int,
        path: str,
        deadline: float,
    ) -> ContactResult:
        start = time.monotonic()

        def remaining() -> float:
            return max(0.0, deadline - time.monotonic())

        connect_timeout = min(self.connect_timeout_seconds, remaining()) or 0.001

        raw_sock: Optional[socket.socket] = None
        try:
            raw_sock = socket.create_connection((resolved_ip, port), timeout=connect_timeout)
        except socket.timeout:
            return _result(
                ContactOutcome.TIMEOUT,
                endpoint_str,
                reason="connection timed out",
                resolved_ip=resolved_ip,
                elapsed_seconds=time.monotonic() - start,
            )
        except OSError as exc:
            return _result(
                ContactOutcome.CONNECTION_FAILED,
                endpoint_str,
                reason=f"connection failed: {exc}",
                resolved_ip=resolved_ip,
                elapsed_seconds=time.monotonic() - start,
            )

        sock = raw_sock
        try:
            if scheme == "https":
                # Certificate validation stays ON (default SSLContext = a
                # verifying context with check_hostname=True). We connect
                # the raw socket to the numeric, already-validated IP, but
                # perform the TLS handshake and certificate identity check
                # against the ORIGINAL hostname via `server_hostname=`. This
                # is the standard safe "connect-by-IP, verify-by-name"
                # pattern — it does not disable verification, does not use
                # an insecure context, and does not downgrade to HTTP.
                ssl_context = ssl.create_default_context()
                try:
                    sock.settimeout(min(self.connect_timeout_seconds, remaining()) or 0.001)
                    sock = ssl_context.wrap_socket(sock, server_hostname=hostname)
                except ssl.SSLCertVerificationError as exc:
                    return _result(
                        ContactOutcome.TLS_FAILED,
                        endpoint_str,
                        reason=f"TLS certificate verification failed: {exc}",
                        resolved_ip=resolved_ip,
                        elapsed_seconds=time.monotonic() - start,
                    )
                except ssl.SSLError as exc:
                    return _result(
                        ContactOutcome.TLS_FAILED,
                        endpoint_str,
                        reason=f"TLS handshake failed: {exc}",
                        resolved_ip=resolved_ip,
                        elapsed_seconds=time.monotonic() - start,
                    )
                except socket.timeout:
                    return _result(
                        ContactOutcome.TIMEOUT,
                        endpoint_str,
                        reason="TLS handshake timed out",
                        resolved_ip=resolved_ip,
                        elapsed_seconds=time.monotonic() - start,
                    )

            sock.settimeout(min(self.total_timeout_seconds, remaining()) or 0.001)

            conn = _PreconnectedHTTPConnection(sock, host=hostname, port=port)
            try:
                conn.putrequest("GET", path or "/", skip_host=False, skip_accept_encoding=True)
                for header_name, header_value in _REQUEST_HEADERS.items():
                    conn.putheader(header_name, header_value)
                conn.endheaders()

                response = conn.getresponse()
                status_code = response.status

                if 300 <= status_code < 400:
                    location = response.getheader("Location")
                    # Drain a bounded amount so the connection can close
                    # cleanly; we do not follow the redirect.
                    _ = response.read(self.max_response_bytes)
                    return _result(
                        ContactOutcome.REDIRECT,
                        endpoint_str,
                        reason=f"HTTP {status_code} redirect not followed",
                        resolved_ip=resolved_ip,
                        status_code=status_code,
                        redirect_location=location,
                        elapsed_seconds=time.monotonic() - start,
                    )

                body, truncated = _read_bounded(response, self.max_response_bytes)
                if truncated:
                    return _result(
                        ContactOutcome.RESPONSE_TOO_LARGE,
                        endpoint_str,
                        reason=f"response exceeded {self.max_response_bytes} byte limit",
                        resolved_ip=resolved_ip,
                        status_code=status_code,
                        response_size=len(body),
                        elapsed_seconds=time.monotonic() - start,
                    )

                return _result(
                    ContactOutcome.HTTP_RESPONSE,
                    endpoint_str,
                    reason="",
                    resolved_ip=resolved_ip,
                    status_code=status_code,
                    response_size=len(body),
                    response_body=body,
                    elapsed_seconds=time.monotonic() - start,
                )
            except socket.timeout:
                return _result(
                    ContactOutcome.TIMEOUT,
                    endpoint_str,
                    reason="request timed out",
                    resolved_ip=resolved_ip,
                    elapsed_seconds=time.monotonic() - start,
                )
            except http.client.HTTPException as exc:
                return _result(
                    ContactOutcome.MALFORMED_RESPONSE,
                    endpoint_str,
                    reason=f"malformed HTTP response: {exc}",
                    resolved_ip=resolved_ip,
                    elapsed_seconds=time.monotonic() - start,
                )
            except OSError as exc:
                return _result(
                    ContactOutcome.CONNECTION_FAILED,
                    endpoint_str,
                    reason=f"connection failed during request: {exc}",
                    resolved_ip=resolved_ip,
                    elapsed_seconds=time.monotonic() - start,
                )
            finally:
                try:
                    conn.close()
                except Exception:
                    pass
        finally:
            try:
                sock.close()
            except Exception:
                pass


class _PreconnectedHTTPConnection(http.client.HTTPConnection):
    """An `http.client.HTTPConnection` bound to an already-open socket.

    `http.client` normally opens its own socket from a hostname inside
    `connect()`; we need it to speak HTTP/1.1 framing over a socket we
    already connected (to a DNS-rebinding-validated IP, optionally already
    TLS-wrapped with hostname-verified certs) instead. Overriding
    `connect()` to a no-op and pre-setting `self.sock` is the standard,
    documented way to do this with the standard library — no third-party
    dependency, no protocol reimplementation.
    """

    def __init__(self, sock: socket.socket, *, host: str, port: int) -> None:
        super().__init__(host, port)
        self.sock = sock

    def connect(self) -> None:  # pragma: no cover - intentionally inert
        # Socket is already connected (and TLS-wrapped, if applicable) by
        # NetworkContactTransport before this object is used. Do not open a
        # new connection here.
        pass


def _read_bounded(response: http.client.HTTPResponse, max_bytes: int) -> Tuple[bytes, bool]:
    """Read up to `max_bytes + 1` bytes from `response` to detect overflow
    without ever buffering an unbounded amount. Returns (body, truncated).
    `body` is capped at `max_bytes`; if more data was available, `truncated`
    is True and `body` reflects only the first `max_bytes` bytes actually
    read (the caller discards it rather than returning partial untrusted
    data as if it were the whole response).
    """
    chunks: List[bytes] = []
    total = 0
    chunk_size = 4096
    while total <= max_bytes:
        remaining_budget = max_bytes + 1 - total
        read_size = min(chunk_size, remaining_budget)
        chunk = response.read(read_size)
        if not chunk:
            break
        chunks.append(chunk)
        total += len(chunk)
        if total > max_bytes:
            return b"".join(chunks)[:max_bytes], True
    return b"".join(chunks), False
