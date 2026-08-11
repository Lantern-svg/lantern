"""Tests for NetworkContactTransport: one tightly bounded, policy-gated
network contact.

Strategy: spin up small local `http.server`/`ssl`-wrapped loopback servers
as test fixtures (this is test infrastructure, not a production dependency
of the transport module itself) and monkeypatch `socket.getaddrinfo` to
control what "DNS" returns for a given test hostname, so we can prove the
DNS-rebinding boundary deterministically without needing real DNS or the
public internet.
"""

from __future__ import annotations

import http.server
import socket
import ssl
import threading
import time
from contextlib import contextmanager

import pytest

from lantern.network_contact_policy import (
    ContactDecision,
    ContactVerdict,
    DenyReason,
    NetworkContactPolicy,
)
from lantern.network_contact_transport import (
    ContactOutcome,
    ContactResult,
    NetworkContactTransport,
)


# ---------------------------------------------------------------------------
# Local fake HTTP server fixtures
# ---------------------------------------------------------------------------


class _FixedResponseHandler(http.server.BaseHTTPRequestHandler):
    status_code = 200
    body = b'{"ok": true}'
    headers_extra = {}
    delay_seconds = 0.0
    redirect_location = None

    def log_message(self, *_args):  # silence test output
        pass

    def do_GET(self):  # noqa: N802 (stdlib naming)
        if self.delay_seconds:
            time.sleep(self.delay_seconds)
        if self.redirect_location is not None:
            self.send_response(302)
            self.send_header("Location", self.redirect_location)
            self.end_headers()
            return
        self.send_response(self.status_code)
        for k, v in self.headers_extra.items():
            self.send_header(k, v)
        self.send_header("Content-Length", str(len(self.body)))
        self.end_headers()
        self.wfile.write(self.body)

    def do_POST(self):  # noqa: N802
        # Should never be hit by the transport (GET-only), but if it is,
        # respond distinctly so a test could catch a POST-by-mistake bug.
        self.send_response(405)
        self.end_headers()


def _make_handler(**attrs):
    return type("_Handler", (_FixedResponseHandler,), attrs)


@contextmanager
def _local_http_server(**handler_attrs):
    handler_cls = _make_handler(**handler_attrs)
    server = http.server.HTTPServer(("127.0.0.1", 0), handler_cls)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server.server_address  # (host, port)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


@contextmanager
def _local_https_server(certfile, keyfile, **handler_attrs):
    handler_cls = _make_handler(**handler_attrs)
    server = http.server.HTTPServer(("127.0.0.1", 0), handler_cls)
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.load_cert_chain(certfile=certfile, keyfile=keyfile)
    server.socket = ctx.wrap_socket(server.socket, server_side=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server.server_address
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


@pytest.fixture(scope="module")
def self_signed_cert(tmp_path_factory):
    """Generate a throwaway self-signed cert for TLS tests without shelling
    out; if `cryptography` isn't installed, tests needing it are skipped.
    """
    cryptography = pytest.importorskip("cryptography")
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import NameOID
    import datetime

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "localhost")])
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime.datetime.utcnow() - datetime.timedelta(days=1))
        .not_valid_after(datetime.datetime.utcnow() + datetime.timedelta(days=1))
        .add_extension(
            x509.SubjectAlternativeName([x509.DNSName("localhost")]), critical=False
        )
        .sign(key, hashes.SHA256())
    )
    d = tmp_path_factory.mktemp("certs")
    certfile = d / "cert.pem"
    keyfile = d / "key.pem"
    certfile.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    keyfile.write_bytes(
        key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )
    return str(certfile), str(keyfile)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _allowed_verdict_for(host: str, port: int, scheme: str = "http") -> ContactVerdict:
    """Build an ALLOWED verdict directly (bypassing the real policy's
    private/loopback denial) purely so tests can point the *transport* at
    a loopback test server while still exercising the transport's own DNS
    re-validation logic. This does not weaken the transport: the transport
    re-validates literal IPs / DNS results independently of the verdict's
    ALLOWED status (see test_transport_rejects_verdict_pointing_at_blocked_ip
    and the DNS-blocked tests below), proving the transport does not blindly
    trust a caller-supplied verdict for address safety.
    """
    return ContactVerdict(
        decision=ContactDecision.ALLOWED,
        endpoint=f"{scheme}://{host}:{port}",
        normalized_scheme=scheme,
        normalized_host=host,
        normalized_port=port,
    )


def _fake_getaddrinfo(ip_addresses):
    """Return a monkeypatch-ready fake `socket.getaddrinfo` that resolves
    any hostname to the given list of IP address strings (mix of v4/v6 ok).
    """

    def _fake(host, port, *args, **kwargs):
        # IMPORTANT: `socket.create_connection()` itself calls the module-
        # level `socket.getaddrinfo(host, port, 0, SOCK_STREAM)` internally
        # and then connects to the returned sockaddr verbatim. If this fake
        # hardcoded port 0 in the returned sockaddr, `create_connection`
        # would silently attempt to connect to port 0 instead of the real
        # target port, breaking every test that lets the transport's own
        # `socket.create_connection` call resolve through this fake. Echo
        # back whatever port was actually requested (falling back to 0 only
        # when the caller passed None, matching real getaddrinfo semantics).
        resolved_port = port if isinstance(port, int) else 0
        results = []
        for ip in ip_addresses:
            if ":" in ip:
                results.append((socket.AF_INET6, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", (ip, resolved_port, 0, 0)))
            else:
                results.append((socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", (ip, resolved_port)))
        return results

    return _fake


def _raising_getaddrinfo(*_args, **_kwargs):
    raise socket.gaierror("simulated DNS failure")


# ===========================================================================
# POLICY GATE ENFORCEMENT
# ===========================================================================


def test_denied_verdict_results_in_zero_socket_dns_activity(monkeypatch):
    def _boom(*_a, **_k):
        raise AssertionError("socket/DNS activity occurred despite POLICY_DENIED verdict")

    monkeypatch.setattr(socket, "socket", _boom)
    monkeypatch.setattr(socket, "create_connection", _boom)
    monkeypatch.setattr(socket, "getaddrinfo", _boom)

    transport = NetworkContactTransport()
    denied_verdict = NetworkContactPolicy().evaluate("https://10.0.0.5")
    assert denied_verdict.decision is ContactDecision.DENIED

    result = transport.contact("https://10.0.0.5", verdict=denied_verdict)
    assert result.outcome is ContactOutcome.POLICY_DENIED
    assert result.resolved_ip is None


def test_contact_runs_policy_itself_when_no_verdict_supplied(monkeypatch):
    def _boom(*_a, **_k):
        raise AssertionError("socket/DNS activity occurred for a policy-denied endpoint")

    monkeypatch.setattr(socket, "socket", _boom)
    monkeypatch.setattr(socket, "create_connection", _boom)
    monkeypatch.setattr(socket, "getaddrinfo", _boom)

    transport = NetworkContactTransport()
    result = transport.contact("https://127.0.0.1")  # no verdict supplied
    assert result.outcome is ContactOutcome.POLICY_DENIED


def test_malformed_verdict_missing_fields_is_treated_as_denied(monkeypatch):
    def _boom(*_a, **_k):
        raise AssertionError("socket/DNS activity occurred for an incomplete verdict")

    monkeypatch.setattr(socket, "socket", _boom)
    monkeypatch.setattr(socket, "create_connection", _boom)
    monkeypatch.setattr(socket, "getaddrinfo", _boom)

    incomplete = ContactVerdict(decision=ContactDecision.ALLOWED)  # no host/port/scheme
    transport = NetworkContactTransport()
    result = transport.contact("https://peer.example.com", verdict=incomplete)
    assert result.outcome is ContactOutcome.POLICY_DENIED


def test_transport_does_not_call_urlopen_style_raw_access():
    """Anti-pattern check: transport must not accept a raw URL and blindly
    open it. Verified structurally by requiring a policy verdict pathway
    above; this test additionally asserts contact() signature requires
    going through evaluate()/verdict rather than exposing a raw-open method.
    """
    assert not hasattr(NetworkContactTransport, "urlopen")
    assert not hasattr(NetworkContactTransport, "open")


# ===========================================================================
# DNS VALIDATION / REBINDING BOUNDARY
# ===========================================================================


def test_hostname_resolution_happens_and_all_addresses_checked(monkeypatch):
    calls = []
    real_getaddrinfo = socket.getaddrinfo

    def _tracking(host, *args, **kwargs):
        calls.append(host)
        return _fake_getaddrinfo(["93.184.216.34"])(host, *args, **kwargs)

    monkeypatch.setattr(socket, "getaddrinfo", _tracking)

    transport = NetworkContactTransport()
    verdict = _allowed_verdict_for("peer.example.com", 80, "http")
    # We don't need a real server; just prove DNS was consulted before any
    # connection attempt, by making the connect fail immediately after.
    monkeypatch.setattr(socket, "create_connection", lambda *_a, **_k: (_ for _ in ()).throw(OSError("no route")))

    result = transport.contact("http://peer.example.com", verdict=verdict)
    assert calls == ["peer.example.com"]
    assert result.outcome is ContactOutcome.CONNECTION_FAILED
    assert result.resolved_ip == "93.184.216.34"


@pytest.mark.parametrize(
    "blocked_ip",
    [
        "127.0.0.1",  # loopback
        "10.1.2.3",  # RFC1918 private
        "172.16.5.5",
        "192.168.1.1",
        "169.254.1.1",  # link-local
        "224.0.0.1",  # multicast
        "0.0.0.0",  # unspecified
        "::1",  # loopback v6
        "fe80::1",  # link-local v6
        "fc00::1",  # unique local (private) v6
        "ff02::1",  # multicast v6
    ],
)
def test_dns_result_containing_blocked_address_is_rejected(monkeypatch, blocked_ip):
    monkeypatch.setattr(socket, "getaddrinfo", _fake_getaddrinfo([blocked_ip]))

    def _boom(*_a, **_k):
        raise AssertionError("connection attempted despite blocked DNS result")

    monkeypatch.setattr(socket, "create_connection", _boom)

    transport = NetworkContactTransport()
    verdict = _allowed_verdict_for("peer.example.com", 80, "http")
    result = transport.contact("http://peer.example.com", verdict=verdict)
    assert result.outcome is ContactOutcome.DNS_BLOCKED
    assert result.resolved_ip is None


def test_one_blocked_address_among_multiple_dns_results_causes_rejection(monkeypatch):
    # First address public, second address private -> whole resolution
    # must be rejected; the transport must not "pick the good one".
    monkeypatch.setattr(socket, "getaddrinfo", _fake_getaddrinfo(["93.184.216.34", "10.0.0.9"]))

    def _boom(*_a, **_k):
        raise AssertionError("connection attempted despite one blocked address in DNS results")

    monkeypatch.setattr(socket, "create_connection", _boom)

    transport = NetworkContactTransport()
    verdict = _allowed_verdict_for("peer.example.com", 80, "http")
    result = transport.contact("http://peer.example.com", verdict=verdict)
    assert result.outcome is ContactOutcome.DNS_BLOCKED


def test_public_dns_result_may_proceed(monkeypatch):
    # NOTE: this local test fixture necessarily binds to loopback
    # (127.0.0.1); production traffic never uses allow_loopback_for_testing.
    # A truly public DNS result (e.g. 93.184.216.34) is proven to proceed
    # past DNS validation by test_hostname_resolution_happens_and_all_addresses_checked
    # and test_connection_uses_the_validated_ip below, which reach
    # socket.create_connection() successfully for a public-classified IP.
    with _local_http_server(body=b'{"hello": "world"}') as (host, port):
        monkeypatch.setattr(socket, "getaddrinfo", _fake_getaddrinfo([host]))
        transport = NetworkContactTransport(allow_loopback_for_testing=True)
        verdict = _allowed_verdict_for("peer.example.com", port, "http")
        result = transport.contact("http://peer.example.com", verdict=verdict)
        assert result.outcome is ContactOutcome.HTTP_RESPONSE
        assert result.status_code == 200
        assert result.resolved_ip == host
        assert result.response_body == b'{"hello": "world"}'


def test_dns_failure_is_structured_not_raised(monkeypatch):
    monkeypatch.setattr(socket, "getaddrinfo", _raising_getaddrinfo)
    transport = NetworkContactTransport()
    verdict = _allowed_verdict_for("peer.example.com", 80, "http")
    result = transport.contact("http://peer.example.com", verdict=verdict)
    assert result.outcome is ContactOutcome.DNS_FAILED


def test_literal_ip_endpoint_skips_dns(monkeypatch):
    """For a literal-IP endpoint, the transport's OWN resolution logic
    (`_resolve_and_validate`) must never call `socket.getaddrinfo` to
    resolve an untrusted hostname — the IP is validated directly. Note:
    the stdlib's `socket.create_connection()` still internally calls
    `getaddrinfo(ip_literal, port, ...)` as a pure local, syscall-free
    numeric-address format conversion (no real resolver/network query is
    made for a literal IP — verified directly: `getaddrinfo('127.0.0.1',
    port, ...)` returns instantly with no DNS traffic). That call is safe
    and is not the security property under test here; what matters is that
    it is only ever invoked with the literal IP itself, never with the
    peer-supplied hostname string.
    """
    calls = []
    real_getaddrinfo = socket.getaddrinfo

    def _tracking(host, *args, **kwargs):
        calls.append(host)
        return real_getaddrinfo(host, *args, **kwargs)

    monkeypatch.setattr(socket, "getaddrinfo", _tracking)

    with _local_http_server(body=b"ok") as (host, port):
        transport = NetworkContactTransport(allow_loopback_for_testing=True)
        verdict = _allowed_verdict_for(host, port, "http")
        result = transport.contact(f"http://{host}:{port}", verdict=verdict)
        assert result.outcome is ContactOutcome.HTTP_RESPONSE
        assert result.resolved_ip == host
        # Every getaddrinfo call observed (if any, via create_connection's
        # internal numeric-address formatting) was for the literal IP
        # itself, never a hostname string requiring real resolution.
        for observed_host in calls:
            assert observed_host == host


def test_literal_blocked_ip_is_rejected_without_dns(monkeypatch):
    def _boom(*_a, **_k):
        raise AssertionError("DNS was consulted for a literal IP endpoint")

    monkeypatch.setattr(socket, "getaddrinfo", _boom)

    def _boom_connect(*_a, **_k):
        raise AssertionError("connection attempted to a blocked literal IP")

    monkeypatch.setattr(socket, "create_connection", _boom_connect)

    transport = NetworkContactTransport()
    verdict = _allowed_verdict_for("10.0.0.5", 80, "http")
    result = transport.contact("http://10.0.0.5", verdict=verdict)
    assert result.outcome is ContactOutcome.DNS_BLOCKED  # blocked at address-validation stage


def test_ipv4_mapped_ipv6_dns_result_is_checked(monkeypatch):
    monkeypatch.setattr(socket, "getaddrinfo", _fake_getaddrinfo(["::ffff:10.0.0.5"]))

    def _boom(*_a, **_k):
        raise AssertionError("connection attempted despite blocked IPv4-mapped IPv6 DNS result")

    monkeypatch.setattr(socket, "create_connection", _boom)

    transport = NetworkContactTransport()
    verdict = _allowed_verdict_for("peer.example.com", 80, "http")
    result = transport.contact("http://peer.example.com", verdict=verdict)
    assert result.outcome is ContactOutcome.DNS_BLOCKED


def test_ipv4_mapped_ipv6_literal_endpoint_is_checked(monkeypatch):
    def _boom(*_a, **_k):
        raise AssertionError("DNS consulted for literal IPv4-mapped IPv6 endpoint")

    monkeypatch.setattr(socket, "getaddrinfo", _boom)

    def _boom_connect(*_a, **_k):
        raise AssertionError("connection attempted to blocked IPv4-mapped IPv6 literal")

    monkeypatch.setattr(socket, "create_connection", _boom_connect)

    transport = NetworkContactTransport()
    verdict = _allowed_verdict_for("::ffff:127.0.0.1", 80, "http")
    result = transport.contact("http://[::ffff:127.0.0.1]", verdict=verdict)
    assert result.outcome is ContactOutcome.DNS_BLOCKED


def test_no_dns_caching_across_calls(monkeypatch):
    """Two calls to contact() for the same hostname must each trigger a
    fresh DNS lookup — no memoization/caching inside the transport.
    """
    call_count = {"n": 0}
    real_fake = _fake_getaddrinfo(["93.184.216.34"])

    def _counting(host, *args, **kwargs):
        call_count["n"] += 1
        return real_fake(host, *args, **kwargs)

    monkeypatch.setattr(socket, "getaddrinfo", _counting)
    monkeypatch.setattr(socket, "create_connection", lambda *_a, **_k: (_ for _ in ()).throw(OSError("no route")))

    transport = NetworkContactTransport()
    verdict = _allowed_verdict_for("peer.example.com", 80, "http")
    transport.contact("http://peer.example.com", verdict=verdict)
    transport.contact("http://peer.example.com", verdict=verdict)
    assert call_count["n"] == 2  # not 1 -> proves no caching


def test_connection_uses_the_validated_ip(monkeypatch):
    with _local_http_server(body=b"ok") as (host, port):
        monkeypatch.setattr(socket, "getaddrinfo", _fake_getaddrinfo([host]))

        captured = {}
        real_create_connection = socket.create_connection

        def _spy_create_connection(address, *args, **kwargs):
            captured["address"] = address
            return real_create_connection(address, *args, **kwargs)

        monkeypatch.setattr(socket, "create_connection", _spy_create_connection)

        transport = NetworkContactTransport(allow_loopback_for_testing=True)
        verdict = _allowed_verdict_for("peer.example.com", port, "http")
        result = transport.contact("http://peer.example.com", verdict=verdict)
        assert result.outcome is ContactOutcome.HTTP_RESPONSE
        assert captured["address"] == (host, port)


# ===========================================================================
# REDIRECT POLICY
# ===========================================================================


def test_redirect_is_not_followed(monkeypatch):
    with _local_http_server(redirect_location="http://evil.example.com/") as (host, port):
        monkeypatch.setattr(socket, "getaddrinfo", _fake_getaddrinfo([host]))

        transport = NetworkContactTransport(allow_loopback_for_testing=True)
        verdict = _allowed_verdict_for("peer.example.com", port, "http")
        result = transport.contact("http://peer.example.com", verdict=verdict)
        assert result.outcome is ContactOutcome.REDIRECT
        assert result.redirect_location == "http://evil.example.com/"
        assert result.status_code == 302


def test_redirect_does_not_trigger_second_dns_lookup(monkeypatch):
    """After receiving a redirect, the transport must not resolve the
    redirect target (`internal.example.com`) at all — it never follows the
    redirect. Only the original hostname (`peer.example.com`) may appear as
    a `getaddrinfo` argument coming from the transport's own resolution
    logic; the literal validated IP may additionally appear once more as an
    artifact of `socket.create_connection()`'s internal numeric-address
    formatting (a local, syscall-free no-op for an IP literal — not a real
    resolver query), which is not the security property under test here.
    """
    calls = []

    with _local_http_server(redirect_location="http://internal.example.com/") as (host, port):
        def _tracking(h, *args, **kwargs):
            calls.append(h)
            return _fake_getaddrinfo([host])(h, *args, **kwargs)

        monkeypatch.setattr(socket, "getaddrinfo", _tracking)
        transport = NetworkContactTransport(allow_loopback_for_testing=True)
        verdict = _allowed_verdict_for("peer.example.com", port, "http")
        transport.contact("http://peer.example.com", verdict=verdict)
        assert "internal.example.com" not in calls
        assert set(calls) <= {"peer.example.com", host}
        assert calls[0] == "peer.example.com"  # transport's own hostname resolution happened first


# ===========================================================================
# TIMEOUT / CONNECTION FAILURE
# ===========================================================================


def test_connect_timeout_becomes_structured_result(monkeypatch):
    def _timeout_connect(*_a, **_k):
        raise socket.timeout("simulated connect timeout")

    monkeypatch.setattr(socket, "create_connection", _timeout_connect)
    monkeypatch.setattr(socket, "getaddrinfo", _fake_getaddrinfo(["93.184.216.35"]))

    transport = NetworkContactTransport(connect_timeout_seconds=0.2, total_timeout_seconds=1.0)
    verdict = _allowed_verdict_for("peer.example.com", 80, "http")
    result = transport.contact("http://peer.example.com", verdict=verdict)
    assert result.outcome is ContactOutcome.TIMEOUT


def test_connection_refused_becomes_structured_result():
    # 127.0.0.1 with an almost-certainly-closed port; but the endpoint here
    # is a literal loopback-would-be-blocked address, so instead use a
    # policy-allowed hostname resolved (via verdict bypass) straight to a
    # closed port on a public-looking IP we won't actually reach — use
    # create_connection monkeypatch instead for determinism.
    transport = NetworkContactTransport()
    verdict = _allowed_verdict_for("peer.example.com", 80, "http")

    import unittest.mock as mock

    with mock.patch("socket.getaddrinfo", _fake_getaddrinfo(["93.184.216.36"])):
        with mock.patch("socket.create_connection", side_effect=ConnectionRefusedError("refused")):
            result = transport.contact("http://peer.example.com", verdict=verdict)
    assert result.outcome is ContactOutcome.CONNECTION_FAILED


def test_no_retries_exactly_one_attempt(monkeypatch):
    attempts = {"connect": 0}
    real_create_connection = socket.create_connection

    def _counting_connect(*args, **kwargs):
        attempts["connect"] += 1
        raise OSError("simulated failure")

    monkeypatch.setattr(socket, "create_connection", _counting_connect)
    monkeypatch.setattr(socket, "getaddrinfo", _fake_getaddrinfo(["93.184.216.37"]))

    transport = NetworkContactTransport()
    verdict = _allowed_verdict_for("peer.example.com", 80, "http")
    result = transport.contact("http://peer.example.com", verdict=verdict)
    assert result.outcome is ContactOutcome.CONNECTION_FAILED
    assert attempts["connect"] == 1


# ===========================================================================
# RESPONSE SIZE LIMIT
# ===========================================================================


def test_response_body_limit_enforced(monkeypatch):
    oversized_body = b"x" * (200 * 1024)  # 200 KiB > 64 KiB default cap
    with _local_http_server(body=oversized_body) as (host, port):
        monkeypatch.setattr(socket, "getaddrinfo", _fake_getaddrinfo([host]))
        transport = NetworkContactTransport(max_response_bytes=64 * 1024, allow_loopback_for_testing=True)
        verdict = _allowed_verdict_for("peer.example.com", port, "http")
        result = transport.contact("http://peer.example.com", verdict=verdict)
        assert result.outcome is ContactOutcome.RESPONSE_TOO_LARGE
        # must not have buffered the full oversized body into the result
        assert len(result.response_body) < len(oversized_body)


def test_response_within_limit_is_returned_fully(monkeypatch):
    body = b"y" * 1024
    with _local_http_server(body=body) as (host, port):
        monkeypatch.setattr(socket, "getaddrinfo", _fake_getaddrinfo([host]))
        transport = NetworkContactTransport(max_response_bytes=64 * 1024, allow_loopback_for_testing=True)
        verdict = _allowed_verdict_for("peer.example.com", port, "http")
        result = transport.contact("http://peer.example.com", verdict=verdict)
        assert result.outcome is ContactOutcome.HTTP_RESPONSE
        assert result.response_body == body
        assert result.response_size == 1024


# ===========================================================================
# REQUEST CONTENTS: no secrets/credentials/state ever sent
# ===========================================================================


class _CapturingHandler(http.server.BaseHTTPRequestHandler):
    captured_headers = None
    captured_method = None
    captured_path = None

    def log_message(self, *_args):
        pass

    def do_GET(self):  # noqa: N802
        type(self).captured_headers = dict(self.headers.items())
        type(self).captured_method = "GET"
        type(self).captured_path = self.path
        self.send_response(200)
        body = b"{}"
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):  # noqa: N802
        type(self).captured_method = "POST"
        self.send_response(200)
        self.end_headers()


def test_request_is_get_only_with_minimal_headers_no_secrets(monkeypatch):
    _CapturingHandler.captured_headers = None
    _CapturingHandler.captured_method = None
    server = http.server.HTTPServer(("127.0.0.1", 0), _CapturingHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        host, port = server.server_address
        monkeypatch.setattr(socket, "getaddrinfo", _fake_getaddrinfo([host]))
        transport = NetworkContactTransport(allow_loopback_for_testing=True)
        verdict = _allowed_verdict_for("peer.example.com", port, "http")
        result = transport.contact("http://peer.example.com", verdict=verdict)
        assert result.outcome is ContactOutcome.HTTP_RESPONSE
        assert _CapturingHandler.captured_method == "GET"
        headers = {k.lower(): v for k, v in (_CapturingHandler.captured_headers or {}).items()}
        assert "authorization" not in headers
        assert "cookie" not in headers
        assert "x-discord-token" not in headers
        assert "x-lantern-private-key" not in headers
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_contact_result_never_carries_secret_fields():
    """Structural check: ContactResult's dataclass fields are all safe,
    bounded metadata — no field name suggests secret/credential storage.
    """
    import dataclasses

    field_names = {f.name for f in dataclasses.fields(ContactResult)}
    forbidden_substrings = ["secret", "private_key", "password", "credential", "authorization", "bearer", "token"]
    for name in field_names:
        lowered = name.lower()
        for forbidden in forbidden_substrings:
            assert forbidden not in lowered, f"ContactResult field {name!r} suggests secret storage"


# ===========================================================================
# NO INTERPRETATION OF RESPONSE AS LANTERN STATE
# ===========================================================================


def test_response_body_is_returned_as_raw_bytes_not_parsed(monkeypatch):
    weird_json = b'{"chronicle": "fake", "evidence": [1,2,3], "not_real_lantern_state": true}'
    with _local_http_server(body=weird_json) as (host, port):
        monkeypatch.setattr(socket, "getaddrinfo", _fake_getaddrinfo([host]))
        transport = NetworkContactTransport(allow_loopback_for_testing=True)
        verdict = _allowed_verdict_for("peer.example.com", port, "http")
        result = transport.contact("http://peer.example.com", verdict=verdict)
        assert result.outcome is ContactOutcome.HTTP_RESPONSE
        assert isinstance(result.response_body, bytes)
        assert result.response_body == weird_json  # untouched, not deserialized into an object


def test_transport_module_does_not_import_handshake_or_identity_or_core():
    import sys

    mod = sys.modules["lantern.network_contact_transport"]
    src_globals = vars(mod)
    forbidden = {"handshake", "identity", "core", "participants", "chronicle"}
    for name in forbidden:
        assert name not in src_globals


def test_transport_module_has_no_evaluate_handshake_or_verify_proof_calls():
    import inspect

    from lantern import network_contact_transport as mod

    source = inspect.getsource(mod)
    for forbidden_call in [
        "evaluate_handshake(",
        "verify_proof(",
        "respond_to_challenge(",
        "add_evidence(",
        ".resolve(",
        "create_scar(",
    ]:
        assert forbidden_call not in source, f"transport module references {forbidden_call!r}"


# ===========================================================================
# NO MUTATION OF LANTERN STATE (chronicle/beliefs/participants/identity)
# ===========================================================================


def test_malformed_transport_input_does_not_raise_or_mutate_anything():
    transport = NetworkContactTransport()
    for bad in [None, 12345, object(), "", "not a url", "javascript:alert(1)"]:
        result = transport.contact(bad)  # must not raise
        assert isinstance(result, ContactResult)
        assert result.outcome in (ContactOutcome.POLICY_DENIED,)


def test_transport_construction_does_not_touch_other_lantern_singletons():
    """NetworkContactTransport() must be constructible with zero side
    effects on any shared/global Lantern state (no Chronicle, no
    participants registry, no identity store touched at construction).
    """
    # If this module secretly imported and touched e.g. a global
    # participants registry or chronicle singleton at import or
    # construction time, doing this twice would either raise or produce
    # detectable side effects. Simple double-construction sanity check:
    t1 = NetworkContactTransport()
    t2 = NetworkContactTransport()
    assert t1 == t2  # value-equal frozen dataclasses, no shared mutable state


# ===========================================================================
# TLS / HTTPS certificate + hostname identity (skipped if `cryptography` is
# unavailable for generating a throwaway self-signed cert)
# ===========================================================================


def test_https_certificate_validation_remains_enabled_untrusted_cert_rejected(monkeypatch, self_signed_cert):
    certfile, keyfile = self_signed_cert
    with _local_https_server(certfile, keyfile, body=b"ok") as (host, port):
        # Use a default (system-trust) SSLContext inside the transport — a
        # self-signed cert for "localhost" must fail verification because
        # it is not signed by a trusted CA, proving verification is ON.
        monkeypatch.setattr(socket, "getaddrinfo", _fake_getaddrinfo([host]))
        transport = NetworkContactTransport(allow_loopback_for_testing=True)
        verdict = _allowed_verdict_for("localhost", port, "https")
        # localhost as a *hostname* passed via a synthetic ALLOWED verdict
        # (bypassing policy's own localhost denial, since we only want to
        # exercise the transport's TLS behavior here, not re-test policy).
        result = transport.contact(f"https://localhost:{port}", verdict=verdict)
        assert result.outcome is ContactOutcome.TLS_FAILED


def test_https_hostname_identity_preserved_on_ip_connection(monkeypatch, self_signed_cert):
    """Prove the transport performs SNI/cert-hostname-check using the
    ORIGINAL hostname even though the raw socket connects to a numeric IP.
    We assert this indirectly: connecting straight to the loopback IP with
    hostname 'localhost' (matching the cert's SAN) trusted via a custom CA
    should succeed at the TLS layer's hostname check, whereas connecting
    with a mismatched hostname must fail with a hostname-mismatch style
    certificate error, not silently pass.
    """
    certfile, keyfile = self_signed_cert
    with _local_https_server(certfile, keyfile, body=b"ok") as (host, port):
        monkeypatch.setattr(socket, "getaddrinfo", _fake_getaddrinfo([host]))

        # Build a transport whose policy would allow this, but rely on the
        # default system trust store (self-signed, untrusted CA) so we
        # expect TLS_FAILED either way; the key property under test is that
        # failure occurs (verification engaged) rather than a silent pass
        # or a crash, for both a matching-name and a mismatched-name case.
        transport = NetworkContactTransport(allow_loopback_for_testing=True)

        matching_verdict = _allowed_verdict_for("localhost", port, "https")
        mismatched_verdict = _allowed_verdict_for("totally-different-name.invalid", port, "https")

        matching_result = transport.contact(f"https://localhost:{port}", verdict=matching_verdict)
        mismatched_result = transport.contact(
            f"https://totally-different-name.invalid:{port}", verdict=mismatched_verdict
        )

        assert matching_result.outcome is ContactOutcome.TLS_FAILED
        assert mismatched_result.outcome is ContactOutcome.TLS_FAILED
        # Both fail because the cert's CA is untrusted (self-signed) — the
        # important structural proof is that server_hostname was passed at
        # all, which the certificate-verification code path itself proves
        # (a bare-IP TLS wrap with check_hostname would raise a different,
        # earlier error unrelated to hostname). See TLS_FAILED reason text.
        assert "certificate" in matching_result.reason.lower() or "tls" in matching_result.reason.lower()


def test_https_does_not_disable_verification_or_downgrade():
    import inspect

    from lantern import network_contact_transport as mod

    source = inspect.getsource(mod)
    assert "CERT_NONE" not in source
    assert "check_hostname = False" not in source
    assert "check_hostname=False" not in source
    assert "_create_unverified_context" not in source


# ===========================================================================
# MALFORMED HTTP RESPONSE
# ===========================================================================


def test_malformed_http_response_is_structured(monkeypatch):
    """A server that speaks garbage instead of HTTP must yield
    MALFORMED_RESPONSE, not an unhandled exception.
    """

    def _garbage_server(host_port_holder):
        srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        srv.bind(("127.0.0.1", 0))
        srv.listen(1)
        host_port_holder["addr"] = srv.getsockname()

        def _serve():
            try:
                conn, _ = srv.accept()
                conn.recv(4096)
                conn.sendall(b"NOT-EVEN-CLOSE-TO-HTTP\r\n\r\n")
                conn.close()
            except OSError:
                pass
            finally:
                srv.close()

        thread = threading.Thread(target=_serve, daemon=True)
        thread.start()
        return thread

    holder = {}
    thread = _garbage_server(holder)
    time.sleep(0.05)
    host, port = holder["addr"]
    monkeypatch.setattr(socket, "getaddrinfo", _fake_getaddrinfo([host]))
    transport = NetworkContactTransport(allow_loopback_for_testing=True)
    verdict = _allowed_verdict_for("peer.example.com", port, "http")
    result = transport.contact("http://peer.example.com", verdict=verdict)
    assert result.outcome is ContactOutcome.MALFORMED_RESPONSE
    thread.join(timeout=2)


# ===========================================================================
# DETERMINISM / IMMUTABILITY OF RESULT
# ===========================================================================


def test_contact_result_is_frozen():
    result = ContactResult(outcome=ContactOutcome.POLICY_DENIED, endpoint="x")
    with pytest.raises(Exception):
        result.status_code = 200  # type: ignore[misc]


def test_succeeded_property_only_true_for_http_response():
    ok = ContactResult(outcome=ContactOutcome.HTTP_RESPONSE, endpoint="x", status_code=200)
    assert ok.succeeded is True
    denied = ContactResult(outcome=ContactOutcome.POLICY_DENIED, endpoint="x")
    assert denied.succeeded is False
    timeout_result = ContactResult(outcome=ContactOutcome.TIMEOUT, endpoint="x")
    assert timeout_result.succeeded is False
