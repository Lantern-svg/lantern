"""Tests for the pure NetworkContactPolicy gate.

These tests exist to prove the security boundary described in
`src/lantern/network_contact_policy.py`:

- The module performs ZERO network or filesystem I/O. We monkeypatch the
  primary I/O entry points (`socket.socket`, `socket.create_connection`,
  `socket.getaddrinfo`, `socket.gethostbyname`, `builtins.open`) to raise
  immediately if called, then exercise every branch of `evaluate()`. If any
  code path in the policy ever performs I/O, these tests fail loudly.
- Every documented rule (schemes, ports, localhost, private/reserved/
  link-local/loopback/multicast/unspecified ranges, IPv4-mapped IPv6,
  hostname handling, URL-credential rejection, fragment/query policy,
  malformed input) is covered.
- `evaluate()` is deterministic: the same input always produces the same
  verdict, proven by repeated-call equality checks.
"""

from __future__ import annotations

import socket

import pytest

from lantern.network_contact_policy import (
    ContactDecision,
    ContactVerdict,
    DenyReason,
    NetworkContactPolicy,
)


# ---------------------------------------------------------------------------
# Zero-I/O guarantee: monkeypatch every plausible I/O entry point to blow up
# if the policy module ever touches it.
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def forbid_all_io(monkeypatch):
    def _boom(*_args, **_kwargs):
        raise AssertionError(
            "NetworkContactPolicy performed I/O — this must never happen "
            "(zero-I/O guarantee violated)"
        )

    monkeypatch.setattr(socket, "socket", _boom)
    monkeypatch.setattr(socket, "create_connection", _boom)
    monkeypatch.setattr(socket, "getaddrinfo", _boom)
    monkeypatch.setattr(socket, "gethostbyname", _boom)
    monkeypatch.setattr(socket, "gethostbyname_ex", _boom)

    import builtins

    real_open = builtins.open

    def _guarded_open(*args, **kwargs):
        raise AssertionError(
            "NetworkContactPolicy touched the filesystem via open() — "
            "this must never happen (zero-I/O guarantee violated)"
        )

    monkeypatch.setattr(builtins, "open", _guarded_open)
    yield
    # restore handled automatically by monkeypatch fixture teardown
    assert builtins.open is _guarded_open  # sanity: nothing un-patched mid-test
    monkeypatch.setattr(builtins, "open", real_open)


def _policy(**kwargs) -> NetworkContactPolicy:
    return NetworkContactPolicy(**kwargs)


# ---------------------------------------------------------------------------
# Basic ALLOWED cases
# ---------------------------------------------------------------------------


def test_allows_https_default_port_hostname():
    verdict = _policy().evaluate("https://peer.example.com")
    assert verdict.decision is ContactDecision.ALLOWED
    assert verdict.allowed is True
    assert verdict.normalized_scheme == "https"
    assert verdict.normalized_host == "peer.example.com"
    assert verdict.normalized_port == 443


def test_allows_http_default_port_hostname():
    verdict = _policy().evaluate("http://peer.example.com")
    assert verdict.allowed
    assert verdict.normalized_port == 80


def test_allows_https_explicit_default_port():
    verdict = _policy().evaluate("https://peer.example.com:443")
    assert verdict.allowed
    assert verdict.normalized_port == 443


def test_allows_public_ipv4_literal():
    verdict = _policy().evaluate("https://93.184.216.34")
    assert verdict.allowed


def test_allows_public_ipv6_literal_bracketed():
    verdict = _policy().evaluate("https://[2606:2800:220:1:248:1893:25c8:1946]")
    assert verdict.allowed
    assert verdict.normalized_port == 443


def test_allows_subdomain_hostname():
    verdict = _policy().evaluate("https://node-b.rendezvous.example.org")
    assert verdict.allowed


def test_fragment_and_query_do_not_block_allow():
    """Fragment/query policy: presence of a query or fragment does not by
    itself cause denial — the policy gate only judges scheme/host/port.
    """
    verdict = _policy().evaluate("https://peer.example.com/path?x=1#frag")
    assert verdict.allowed
    assert verdict.normalized_host == "peer.example.com"


# ---------------------------------------------------------------------------
# Scheme handling
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "endpoint",
    [
        "ftp://peer.example.com",
        "ws://peer.example.com",
        "wss://peer.example.com",
        "file:///etc/passwd",
        "gopher://peer.example.com",
        "javascript:alert(1)",
        "data:text/plain;base64,AAAA",
        "HTTPS://peer.example.com".lower().replace("https", "chrome-extension"),
    ],
)
def test_denies_disallowed_schemes(endpoint):
    verdict = _policy().evaluate(endpoint)
    assert verdict.decision is ContactDecision.DENIED
    assert verdict.reason in (DenyReason.DISALLOWED_SCHEME, DenyReason.MISSING_HOST, DenyReason.MALFORMED_ENDPOINT)


def test_scheme_is_case_insensitive():
    verdict = _policy().evaluate("HTTPS://peer.example.com")
    assert verdict.allowed
    assert verdict.normalized_scheme == "https"


def test_caller_can_restrict_to_https_only():
    policy = _policy(allowed_schemes=frozenset({"https"}))
    denied = policy.evaluate("http://peer.example.com")
    assert denied.decision is ContactDecision.DENIED
    assert denied.reason is DenyReason.DISALLOWED_SCHEME
    allowed = policy.evaluate("https://peer.example.com")
    assert allowed.allowed


# ---------------------------------------------------------------------------
# Port handling
# ---------------------------------------------------------------------------


def test_denies_non_default_port_by_default():
    verdict = _policy().evaluate("https://peer.example.com:8443")
    assert verdict.decision is ContactDecision.DENIED
    assert verdict.reason is DenyReason.PORT_NOT_ALLOWED


def test_caller_supplied_port_allowlist_permits_custom_port():
    policy = _policy(allowed_ports=frozenset({8443}))
    verdict = policy.evaluate("https://peer.example.com:8443")
    assert verdict.allowed
    assert verdict.normalized_port == 8443


def test_caller_supplied_port_allowlist_still_blocks_others():
    policy = _policy(allowed_ports=frozenset({8443}))
    verdict = policy.evaluate("https://peer.example.com:443")
    assert verdict.decision is ContactDecision.DENIED
    assert verdict.reason is DenyReason.PORT_NOT_ALLOWED


def test_empty_port_allowlist_denies_everything_on_port_grounds():
    policy = _policy(allowed_ports=frozenset())
    verdict = policy.evaluate("https://peer.example.com")
    assert verdict.decision is ContactDecision.DENIED
    assert verdict.reason is DenyReason.PORT_NOT_ALLOWED


@pytest.mark.parametrize("port", [0, -1, 65536, 999999])
def test_out_of_range_port_is_denied(port):
    # Port 0 / negative / >65535 in a URL either fails urlsplit's own port
    # parsing (raising ValueError, handled internally) or is syntactically
    # excluded; either way this must come back DENIED, never raise.
    verdict = _policy().evaluate(f"https://peer.example.com:{port}")
    assert verdict.decision is ContactDecision.DENIED
    assert verdict.reason in (DenyReason.PORT_OUT_OF_RANGE, DenyReason.MALFORMED_ENDPOINT)


def test_scheme_with_no_default_port_and_no_explicit_port_denied():
    # ftp has no entry in _SCHEME_DEFAULT_PORT, but it's also not an allowed
    # scheme, so this should hit DISALLOWED_SCHEME before port logic — verify
    # scheme check happens first (defense in depth still yields DENIED).
    verdict = _policy().evaluate("ftp://peer.example.com")
    assert verdict.decision is ContactDecision.DENIED


# ---------------------------------------------------------------------------
# Localhost / loopback / private / reserved / link-local / multicast /
# unspecified rejection
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "endpoint",
    [
        "https://localhost",
        "https://localhost:443",
        "https://LOCALHOST",
        "https://localhost.localdomain",
    ],
)
def test_denies_localhost_hostnames(endpoint):
    verdict = _policy().evaluate(endpoint)
    assert verdict.decision is ContactDecision.DENIED
    assert verdict.reason is DenyReason.LOCALHOST_HOSTNAME


@pytest.mark.parametrize(
    "endpoint,expected_reason",
    [
        ("https://127.0.0.1", DenyReason.LOOPBACK_ADDRESS),
        ("https://127.255.255.255", DenyReason.LOOPBACK_ADDRESS),
        ("https://[::1]", DenyReason.LOOPBACK_ADDRESS),
        ("https://0.0.0.0", DenyReason.UNSPECIFIED_ADDRESS),
        ("https://[::]", DenyReason.UNSPECIFIED_ADDRESS),
        ("https://10.0.0.5", DenyReason.PRIVATE_ADDRESS),
        ("https://172.16.0.5", DenyReason.PRIVATE_ADDRESS),
        ("https://172.31.255.255", DenyReason.PRIVATE_ADDRESS),
        ("https://192.168.1.1", DenyReason.PRIVATE_ADDRESS),
        ("https://169.254.1.1", DenyReason.LINK_LOCAL_ADDRESS),
        ("https://[fe80::1]", DenyReason.LINK_LOCAL_ADDRESS),
        ("https://224.0.0.1", DenyReason.MULTICAST_ADDRESS),
        ("https://[ff02::1]", DenyReason.MULTICAST_ADDRESS),
        ("https://[fc00::1]", DenyReason.PRIVATE_ADDRESS),
        ("https://[fd00::1]", DenyReason.PRIVATE_ADDRESS),
    ],
)
def test_denies_private_reserved_linklocal_multicast_unspecified_ranges(endpoint, expected_reason):
    verdict = _policy().evaluate(endpoint)
    assert verdict.decision is ContactDecision.DENIED, f"{endpoint} should be denied"
    assert verdict.reason is expected_reason, f"{endpoint}: expected {expected_reason}, got {verdict.reason}"


def test_denies_ipv4_mapped_ipv6_loopback():
    # ::ffff:127.0.0.1 must be treated exactly like 127.0.0.1.
    verdict = _policy().evaluate("https://[::ffff:127.0.0.1]")
    assert verdict.decision is ContactDecision.DENIED
    assert verdict.reason is DenyReason.LOOPBACK_ADDRESS


def test_denies_ipv4_mapped_ipv6_private():
    # ::ffff:10.0.0.1 unwraps to the private IPv4 address 10.0.0.1.
    verdict = _policy().evaluate("https://[::ffff:10.0.0.1]")
    assert verdict.decision is ContactDecision.DENIED
    assert verdict.reason is DenyReason.PRIVATE_ADDRESS


def test_allows_ipv4_mapped_ipv6_public():
    verdict = _policy().evaluate("https://[::ffff:93.184.216.34]")
    assert verdict.allowed


def test_allow_loopback_for_testing_escape_hatch():
    policy = _policy(allow_loopback_for_testing=True)
    verdict = policy.evaluate("https://127.0.0.1")
    assert verdict.allowed

    verdict_localhost = policy.evaluate("https://localhost")
    assert verdict_localhost.allowed


def test_allow_loopback_for_testing_does_not_relax_private_range():
    """The escape hatch is documented (and named) as loopback-only. Private
    RFC1918 ranges must remain denied even with the flag set, since a
    Discord-sourced announcement must never be able to reach internal infra
    via this flag (per the Phase 3 memory note this module is built from).
    """
    policy = _policy(allow_loopback_for_testing=True)
    verdict = policy.evaluate("https://10.0.0.5")
    assert verdict.decision is ContactDecision.DENIED
    assert verdict.reason is DenyReason.PRIVATE_ADDRESS


def test_allow_loopback_for_testing_does_not_relax_link_local():
    policy = _policy(allow_loopback_for_testing=True)
    verdict = policy.evaluate("https://169.254.1.1")
    assert verdict.decision is ContactDecision.DENIED
    assert verdict.reason is DenyReason.LINK_LOCAL_ADDRESS


# ---------------------------------------------------------------------------
# URL credential rejection
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "endpoint",
    [
        "https://user:pass@peer.example.com",
        "https://user@peer.example.com",
        "https://:pass@peer.example.com",
        "http://admin:hunter2@peer.example.com:80",
    ],
)
def test_denies_embedded_credentials(endpoint):
    verdict = _policy().evaluate(endpoint)
    assert verdict.decision is ContactDecision.DENIED
    assert verdict.reason is DenyReason.CREDENTIALS_IN_URL


# ---------------------------------------------------------------------------
# Malformed / empty / non-string input handling
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "endpoint",
    [
        "",
        "   ",
        "not a url at all",
        "://missing-scheme",
        "https://",
        "https:///no-host-just-path",
        "https://peer example.com",  # embedded space
        "https://peer.example.com\n",  # embedded newline
        "https://peer.example.com\t/x",  # embedded tab
    ],
)
def test_denies_malformed_or_empty_endpoints(endpoint):
    verdict = _policy().evaluate(endpoint)
    assert verdict.decision is ContactDecision.DENIED
    assert verdict.reason is not None


def test_denies_non_string_input_without_raising():
    for bad in (None, 12345, 3.14, [], {}, object()):
        verdict = _policy().evaluate(bad)
        assert verdict.decision is ContactDecision.DENIED
        assert verdict.reason is DenyReason.MALFORMED_ENDPOINT


def test_evaluate_never_raises_on_adversarial_input():
    adversarial = [
        "https://" + "a" * 10000,
        "https://[" + "1" * 5000 + "]",
        "https://%00peer.example.com",
        "https://peer..example.com",
        "https://.peer.example.com",
        "https://peer.example.com.",
        "https://[::ffff:999.999.999.999]",
        "https://999.999.999.999",
        "https://peer.example.com:abc",
        "https://peer.example.com:99999999999999999999",
        "https:// ",
        "https://\x00",
    ]
    for endpoint in adversarial:
        verdict = _policy().evaluate(endpoint)  # must not raise
        assert isinstance(verdict, ContactVerdict)
        assert verdict.decision in (ContactDecision.ALLOWED, ContactDecision.DENIED)


def test_empty_hostname_labels_denied():
    for endpoint in ("https://peer..example.com", "https://.peer.example.com", "https://peer.example.com."):
        verdict = _policy().evaluate(endpoint)
        assert verdict.decision is ContactDecision.DENIED


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "endpoint",
    [
        "https://peer.example.com",
        "https://10.0.0.5",
        "not-a-url",
        "https://user:pass@peer.example.com",
        "https://[::ffff:127.0.0.1]",
    ],
)
def test_evaluate_is_deterministic(endpoint):
    policy = _policy()
    first = policy.evaluate(endpoint)
    second = policy.evaluate(endpoint)
    third = NetworkContactPolicy().evaluate(endpoint)  # fresh instance, defaults
    assert first == second == third


def test_policy_instance_is_frozen_dataclass():
    policy = _policy()
    with pytest.raises(Exception):
        policy.allowed_schemes = frozenset({"https"})  # type: ignore[misc]


def test_verdict_is_frozen_dataclass():
    verdict = _policy().evaluate("https://peer.example.com")
    with pytest.raises(Exception):
        verdict.decision = ContactDecision.DENIED  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Isolated module design: importing/using the module must not import or
# require any other lantern submodule that performs I/O, and must not touch
# global state.
# ---------------------------------------------------------------------------


def test_module_has_no_import_time_dependency_on_networking_modules():
    import sys

    mod = sys.modules["lantern.network_contact_policy"]
    src_globals = vars(mod)
    # only stdlib-derived names should be bound at module scope besides our
    # own definitions; explicitly assert socket/http/dns modules are not
    # imported into this module's namespace.
    forbidden_names = {"socket", "http", "httpx", "requests", "dns", "aiohttp", "urllib.request"}
    for name in forbidden_names:
        assert name not in src_globals, f"unexpected import of {name!r} in network_contact_policy module"


def test_repeated_evaluate_calls_do_not_mutate_policy_state():
    policy = _policy()
    before = (policy.allowed_schemes, policy.allowed_ports, policy.allow_loopback_for_testing)
    for endpoint in ["https://peer.example.com", "https://10.0.0.1", "garbage", "https://127.0.0.1"]:
        policy.evaluate(endpoint)
    after = (policy.allowed_schemes, policy.allowed_ports, policy.allow_loopback_for_testing)
    assert before == after
