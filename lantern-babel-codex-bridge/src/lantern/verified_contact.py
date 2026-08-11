"""Verified contact: bridge NetworkContactTransport -> Lantern handshake ->
cryptographic identity proof, producing a single structured, immutable
:class:`VerifiedContactResult`.

Position in the pipeline (see network_contact_policy.py / network_contact_
transport.py for the layers before this one):

    Discord announcement
        -> normalize Discord data
        -> JoinMonitor
        -> untrusted JoinRequest
        -> NetworkContactPolicy            (syntactic/policy gate; no I/O)
        -> NetworkContactTransport          (one bounded GET; DNS-pinned)
        -> CONTACT_SUCCEEDED
        -> VerifiedContact                  <-- THIS MODULE
              -> Lantern handshake (existing handshake.py)
              -> cryptographic identity proof (existing identity.py)
        -> VerifiedContactResult
        -> explicit trust decision           FUTURE PHASE, not here

What this module proves, and ONLY this:

    "The endpoint I contacted cryptographically controls the identity
    key corresponding to the node identity it claims."

It does NOT establish trust, does NOT grant authority, does NOT enable
evidence/belief/Codex exchange, and does NOT create a Chronicle event or
a Scar. See STATE MUTATION below.

============================================================
Why this module exists instead of extending NetworkContactTransport
============================================================

NetworkContactTransport.contact() is, by design, hardcoded to exactly one
bounded HTTP GET (see its module docstring and `_do_request`, which calls
`conn.putrequest("GET", ...)` unconditionally with no method/body
parameter). The Lantern handshake wire protocol implemented by
bootstrap_node.py requires POST requests carrying a JSON body
(HandshakeRequest, then a Challenge). This is a genuine, structural
incompatibility between the existing one-attempt-GET transport and what a
handshake needs -- not a bug, and not something this module works around
by relaxing NetworkContactTransport's invariants.

Per the brief for this phase, when this exact situation arises the
sanctioned path is a *narrowly scoped* new primitive, not a rewrite of
the existing transport and not a second independent HTTP client with
weaker protections. This module therefore implements a small, private
`_bounded_post()` helper, below, that:

    - Requires the SAME `ContactVerdict` that gated the original GET
      contact (never re-evaluates policy against a different endpoint).
    - Reuses `NetworkContactTransport._resolve_and_validate()` verbatim
      (the exact DNS-rebinding-safe resolution logic) -- not a
      reimplementation, a direct call into the existing instance method.
    - Reuses `NetworkContactTransport._PreconnectedHTTPConnection` and
      `_read_bounded` verbatim for HTTP/1.1 framing and the response-size
      cap -- the same objects the GET path uses.
    - Mirrors `_do_request`'s connect-timeout / TLS-verify-by-hostname /
      total-timeout structure exactly, parameterized for POST + a JSON
      body instead of GET with no body.
    - Never calls `urllib.request.urlopen()` or any other HTTP client.
    - Never follows redirects (a 3xx response is a hard failure here,
      exactly as in the GET path).
    - Is used for EXACTLY TWO requests per `verify_contact()` call, both
      against the identical validated endpoint (host/port/scheme) that
      passed `NetworkContactPolicy` -- see NETWORK_REQUEST_BUDGET in the
      final report. There is no retry loop and no path that issues a
      third request.

============================================================
Endpoint pinning
============================================================

The handshake and identity exchange are bound to the SAME endpoint that
passed NetworkContactPolicy for the original GET contact. Nothing in this
module ever reads a "contact me elsewhere" hint out of a handshake or
proof response body and uses it to pick a new host/port -- there is no
code path here that constructs a new `ContactVerdict` or endpoint string
from remote response data.

============================================================
State mutation
============================================================

This module does not import lantern.core, lantern.federation,
lantern.router, lantern.boundary, lantern.bridge, lantern.scars, or
lantern.agent, and calls none of add_evidence()/belief()/observe()/
resolve()/persist_scar(). The only "mutation" it performs is entirely
local and non-durable: creating a `ChallengeStore` (in-memory, per-call)
to issue and consume exactly one challenge nonce, exactly as
bootstrap_node.py's LanternNode already does per-process. Nothing is
written to any Chronicle.

If a caller wants to record `identity_status` on a `ParticipantView`
(lantern.participants), that remains the caller's explicit, separate
action -- `participants.inspect()` already accepts an `identity_status`
argument for exactly this purpose; this module does not call it and does
not import lantern.participants.
"""

from __future__ import annotations

import http.client
import socket
import ssl
import time
from dataclasses import dataclass
from enum import Enum
from typing import Optional

from . import identity as identity_module
from .compatibility import DEFAULT_CAPABILITIES, compatible_versions
from .handshake import (
    HandshakeRequest,
    HandshakeResponse,
    create_handshake,
)
from .network_contact_policy import ContactDecision, ContactVerdict
from .network_contact_transport import (
    ContactOutcome,
    ContactResult,
    NetworkContactTransport,
    _PreconnectedHTTPConnection,
    _read_bounded,
)

import json


__all__ = [
    "VerifiedContactOutcome",
    "VerifiedContactResult",
    "verify_contact",
    "HANDSHAKE_PATH",
    "IDENTITY_RESPOND_PATH",
    "REQUEST_BUDGET",
]


#: Fixed wire paths this module ever contacts, both on the SAME pinned
#: endpoint. No other path is ever requested by this module.
HANDSHAKE_PATH = "/handshake"
IDENTITY_RESPOND_PATH = "/identity/respond"

#: The exact, fixed number of network requests one verify_contact() call
#: may issue: one POST /handshake, one POST /identity/respond. No retry
#: loop exists; a failure at any stage returns immediately without
#: issuing further requests.
REQUEST_BUDGET = 2


class VerifiedContactOutcome(str, Enum):
    """Terminal outcome of :func:`verify_contact`. Every non-VERIFIED
    value is a fail-closed result -- none of them imply trust, authority,
    or a Codex/belief/evidence grant."""

    CONTACT_NOT_SUCCESSFUL = "CONTACT_NOT_SUCCESSFUL"
    HANDSHAKE_TRANSPORT_FAILED = "HANDSHAKE_TRANSPORT_FAILED"
    HANDSHAKE_MALFORMED_RESPONSE = "HANDSHAKE_MALFORMED_RESPONSE"
    HANDSHAKE_REJECTED = "HANDSHAKE_REJECTED"
    HANDSHAKE_INCOMPATIBLE = "HANDSHAKE_INCOMPATIBLE"
    IDENTITY_TRANSPORT_FAILED = "IDENTITY_TRANSPORT_FAILED"
    IDENTITY_MALFORMED_RESPONSE = "IDENTITY_MALFORMED_RESPONSE"
    IDENTITY_PROOF_INVALID = "IDENTITY_PROOF_INVALID"
    IDENTITY_UNVERIFIED = "IDENTITY_UNVERIFIED"
    IDENTITY_VERIFIED = "IDENTITY_VERIFIED"

    @property
    def verified(self) -> bool:
        return self is VerifiedContactOutcome.IDENTITY_VERIFIED


@dataclass(frozen=True)
class VerifiedContactResult:
    """Immutable, structured result. Safe to log/return over an API --
    contains no private key material, no bearer tokens, no raw
    authorization headers, and no signature/proof bytes beyond the
    caller's own claimed node_id/public_key (which are, by definition,
    public information the remote already chose to present).

    identity_status mirrors lantern.identity's own vocabulary
    ("UNVERIFIED" / "CRYPTOGRAPHICALLY_VERIFIED") so a caller wiring this
    into lantern.participants.inspect(identity_status=...) does not need
    a translation step.
    """

    outcome: VerifiedContactOutcome
    local_node_id: str
    remote_node_id: Optional[str]
    identity_status: str
    protocol_version: Optional[str]
    shared_capabilities: dict
    contact_endpoint: str
    reason: str

    @property
    def verified(self) -> bool:
        return self.outcome.verified

    def to_dict(self) -> dict:
        return {
            "outcome": self.outcome.value,
            "local_node_id": self.local_node_id,
            "remote_node_id": self.remote_node_id,
            "identity_status": self.identity_status,
            "protocol_version": self.protocol_version,
            "shared_capabilities": dict(self.shared_capabilities),
            "contact_endpoint": self.contact_endpoint,
            "reason": self.reason,
        }


def _result(
    outcome: VerifiedContactOutcome,
    *,
    local_node_id: str,
    contact_endpoint: str,
    remote_node_id: Optional[str] = None,
    protocol_version: Optional[str] = None,
    shared_capabilities: Optional[dict] = None,
    reason: str = "",
    identity_status: Optional[str] = None,
) -> VerifiedContactResult:
    return VerifiedContactResult(
        outcome=outcome,
        local_node_id=local_node_id,
        remote_node_id=remote_node_id,
        identity_status=identity_status if identity_status is not None else identity_module.UNVERIFIED,
        protocol_version=protocol_version,
        shared_capabilities=dict(shared_capabilities or {}),
        contact_endpoint=contact_endpoint,
        reason=reason,
    )


# ============================================================
# Narrowly scoped bounded POST primitive.
#
# See module docstring "Why this module exists instead of extending
# NetworkContactTransport" for the justification. This function issues
# AT MOST ONE POST request per call, reusing the transport's own DNS
# resolution/validation and bounded-read machinery. It is not exported
# and not intended for any use beyond the two fixed calls in
# verify_contact() below.
# ============================================================

class _PostOutcome(str, Enum):
    OK = "OK"
    TRANSPORT_FAILED = "TRANSPORT_FAILED"
    MALFORMED_RESPONSE = "MALFORMED_RESPONSE"


@dataclass(frozen=True)
class _PostResult:
    outcome: _PostOutcome
    status_code: Optional[int] = None
    body_json: Optional[dict] = None
    reason: str = ""


def _bounded_post(
    transport: NetworkContactTransport,
    verdict: ContactVerdict,
    path: str,
    payload: dict,
) -> _PostResult:
    """Exactly one bounded POST against the endpoint `verdict` approved.

    Structurally mirrors NetworkContactTransport._do_request(): same
    connect-timeout / TLS-verify-by-original-hostname / total-timeout
    handling, same `_PreconnectedHTTPConnection` + `_read_bounded` size
    cap, same "3xx is a hard failure, never followed" rule. The only
    difference is the HTTP method and the presence of a JSON request
    body. `verdict` must already be ALLOWED (callers below only ever
    pass the verdict recovered from a prior successful ContactResult);
    a non-ALLOWED verdict is refused defensively even so.
    """
    if verdict.decision is not ContactDecision.ALLOWED:
        return _PostResult(_PostOutcome.TRANSPORT_FAILED, reason="endpoint verdict is not ALLOWED")
    if not verdict.normalized_scheme or not verdict.normalized_host or not verdict.normalized_port:
        return _PostResult(_PostOutcome.TRANSPORT_FAILED, reason="verdict missing normalized fields")

    scheme = verdict.normalized_scheme
    hostname = verdict.normalized_host
    port = verdict.normalized_port

    deadline = time.monotonic() + transport.total_timeout_seconds

    resolved_ip, deny_or_none, dns_outcome = transport._resolve_and_validate(hostname)
    if dns_outcome is not None:
        return _PostResult(
            _PostOutcome.TRANSPORT_FAILED,
            reason=f"DNS validation failed: {deny_or_none or dns_outcome.value}",
        )

    def remaining() -> float:
        return max(0.0, deadline - time.monotonic())

    start = time.monotonic()
    connect_timeout = min(transport.connect_timeout_seconds, remaining()) or 0.001

    body_bytes = json.dumps(payload, sort_keys=True).encode("utf-8")

    raw_sock: Optional[socket.socket] = None
    try:
        raw_sock = socket.create_connection((resolved_ip, port), timeout=connect_timeout)
    except socket.timeout:
        return _PostResult(_PostOutcome.TRANSPORT_FAILED, reason="connection timed out")
    except OSError as exc:
        return _PostResult(_PostOutcome.TRANSPORT_FAILED, reason=f"connection failed: {exc}")

    sock = raw_sock
    try:
        if scheme == "https":
            ssl_context = ssl.create_default_context()
            try:
                sock.settimeout(min(transport.connect_timeout_seconds, remaining()) or 0.001)
                sock = ssl_context.wrap_socket(sock, server_hostname=hostname)
            except ssl.SSLCertVerificationError as exc:
                return _PostResult(_PostOutcome.TRANSPORT_FAILED, reason=f"TLS certificate verification failed: {exc}")
            except ssl.SSLError as exc:
                return _PostResult(_PostOutcome.TRANSPORT_FAILED, reason=f"TLS handshake failed: {exc}")
            except socket.timeout:
                return _PostResult(_PostOutcome.TRANSPORT_FAILED, reason="TLS handshake timed out")

        sock.settimeout(min(transport.total_timeout_seconds, remaining()) or 0.001)

        conn = _PreconnectedHTTPConnection(sock, host=hostname, port=port)
        try:
            conn.putrequest("POST", path, skip_host=False, skip_accept_encoding=True)
            conn.putheader("Content-Type", "application/json")
            conn.putheader("Content-Length", str(len(body_bytes)))
            conn.putheader("User-Agent", "lantern-verified-contact/1")
            conn.putheader("Accept", "application/json")
            conn.endheaders(message_body=body_bytes)

            response = conn.getresponse()
            status_code = response.status

            if 300 <= status_code < 400:
                # Never follow a redirect. Drain a bounded amount so the
                # connection can close cleanly, exactly as the GET path
                # does, then report failure -- no new endpoint is ever
                # derived from a Location header here.
                _ = response.read(transport.max_response_bytes)
                return _PostResult(
                    _PostOutcome.TRANSPORT_FAILED,
                    status_code=status_code,
                    reason=f"HTTP {status_code} redirect not followed",
                )

            raw_body, truncated = _read_bounded(response, transport.max_response_bytes)
            if truncated:
                return _PostResult(
                    _PostOutcome.TRANSPORT_FAILED,
                    status_code=status_code,
                    reason=f"response exceeded {transport.max_response_bytes} byte limit",
                )

            if status_code != 200:
                return _PostResult(
                    _PostOutcome.TRANSPORT_FAILED,
                    status_code=status_code,
                    reason=f"unexpected HTTP status {status_code}",
                )

            try:
                parsed = json.loads(raw_body.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                return _PostResult(
                    _PostOutcome.MALFORMED_RESPONSE,
                    status_code=status_code,
                    reason=f"response body is not valid JSON: {exc}",
                )
            if not isinstance(parsed, dict):
                return _PostResult(
                    _PostOutcome.MALFORMED_RESPONSE,
                    status_code=status_code,
                    reason="response body is not a JSON object",
                )

            return _PostResult(_PostOutcome.OK, status_code=status_code, body_json=parsed)
        except socket.timeout:
            return _PostResult(_PostOutcome.TRANSPORT_FAILED, reason="request timed out")
        except http.client.HTTPException as exc:
            return _PostResult(_PostOutcome.TRANSPORT_FAILED, reason=f"malformed HTTP response: {exc}")
        except OSError as exc:
            return _PostResult(_PostOutcome.TRANSPORT_FAILED, reason=f"connection failed during request: {exc}")
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


# ============================================================
# Public entry point
# ============================================================

def verify_contact(
    contact_result: ContactResult,
    *,
    transport: NetworkContactTransport,
    verdict: Optional[ContactVerdict] = None,
    local_node_id: str,
    local_identity: identity_module.NodeIdentity,
    local_capabilities: Optional[dict] = None,
    challenge_ttl_seconds: int = identity_module.DEFAULT_CHALLENGE_TTL_SECONDS,
) -> VerifiedContactResult:
    """Bridge a successful ContactResult -> Lantern handshake -> identity
    proof, producing exactly one VerifiedContactResult.

    Parameters:
        contact_result: the ContactResult already produced by
            `NetworkContactTransport.contact()` for this endpoint. A
            `contact_result.succeeded` of False (or any outcome other
            than HTTP_RESPONSE) short-circuits immediately with
            CONTACT_NOT_SUCCESSFUL -- an HTTP 200 GET response body is
            NEVER treated as sufficient for anything beyond "the
            endpoint answered the GET"; this function still performs its
            own independent handshake + identity exchange regardless of
            what that GET body contained.
        transport: the NetworkContactTransport instance whose DNS
            validation / timeout / size-cap configuration should also
            govern the two POST requests this function issues.
        verdict: optionally, the SAME ContactVerdict that was passed to
            (or produced by) the original `transport.contact()` call for
            this endpoint. If omitted, this function re-evaluates
            `transport.policy.evaluate(contact_result.endpoint)` and uses
            that result. Supplying the original verdict is preferable for
            audit clarity, but not required for safety because the same
            transport policy instance is used either way.
            validation / timeout / size-cap configuration should also
            govern the two POST requests this function issues.
        local_node_id: this node's own configured node_id (echoed into
            the outgoing HandshakeRequest and the identity Challenge's
            from_node_id).
        local_identity: this node's own `NodeIdentity` -- used only to
            read its public binding.json (for including in log-safe
            local context); no private key material is ever read from
            it beyond calling into lantern.identity's own signing
            (which happens on the RESPONDER side, not here -- as the
            initiator, this function never signs anything with a
            private key, it only issues a challenge and verifies a
            signature the remote produced with ITS key).
        local_capabilities: capabilities to advertise in the handshake;
            defaults to a copy of DEFAULT_CAPABILITIES with
            identity_proof=True (this function inherently requires
            identity_proof support to do anything useful).

    Exactly two network requests are issued in the successful path (see
    REQUEST_BUDGET): one POST HANDSHAKE_PATH, one POST
    IDENTITY_RESPOND_PATH. Any failure before or during either request
    returns immediately -- no retry, no additional request.
    """
    if verdict is None:
        verdict = transport.policy.evaluate(contact_result.endpoint)

    endpoint_str = verdict.endpoint or contact_result.endpoint

    # --- Step 0: a successful GET contact is a precondition, not proof of
    # anything about identity. HTTP 200 (or any other GET outcome) is
    # never treated as sufficient by itself.
    if not contact_result.succeeded:
        return _result(
            VerifiedContactOutcome.CONTACT_NOT_SUCCESSFUL,
            local_node_id=local_node_id,
            contact_endpoint=endpoint_str,
            reason=f"prior contact did not succeed: {contact_result.outcome.value}",
        )

    if verdict.decision is not ContactDecision.ALLOWED:
        return _result(
            VerifiedContactOutcome.CONTACT_NOT_SUCCESSFUL,
            local_node_id=local_node_id,
            contact_endpoint=endpoint_str,
            reason="supplied verdict is not ALLOWED; refusing to proceed",
        )

    capabilities = (
        dict(local_capabilities)
        if local_capabilities is not None
        else {**DEFAULT_CAPABILITIES, "identity_proof": True}
    )

    # --- Step 1 of 2: POST /handshake -----------------------------------
    local_handshake: HandshakeRequest = create_handshake(capabilities)
    local_handshake.node_id = local_node_id

    handshake_payload = {
        "node_id": local_handshake.node_id,
        "protocol_version": local_handshake.protocol_version,
        "capabilities": local_handshake.capabilities,
        "timestamp": local_handshake.timestamp,
    }

    handshake_post = _bounded_post(transport, verdict, HANDSHAKE_PATH, handshake_payload)
    if handshake_post.outcome is _PostOutcome.TRANSPORT_FAILED:
        return _result(
            VerifiedContactOutcome.HANDSHAKE_TRANSPORT_FAILED,
            local_node_id=local_node_id,
            contact_endpoint=endpoint_str,
            reason=handshake_post.reason,
        )
    if handshake_post.outcome is _PostOutcome.MALFORMED_RESPONSE:
        return _result(
            VerifiedContactOutcome.HANDSHAKE_MALFORMED_RESPONSE,
            local_node_id=local_node_id,
            contact_endpoint=endpoint_str,
            reason=handshake_post.reason,
        )

    try:
        remote_handshake = HandshakeResponse(**handshake_post.body_json)
    except TypeError as exc:
        return _result(
            VerifiedContactOutcome.HANDSHAKE_MALFORMED_RESPONSE,
            local_node_id=local_node_id,
            contact_endpoint=endpoint_str,
            reason=f"handshake response missing required fields: {exc}",
        )

    remote_node_id = remote_handshake.node_id

    # Independently re-check protocol compatibility locally -- never trust
    # `accepted` alone, since a malicious/buggy peer could claim accepted
    # while being genuinely incompatible.
    try:
        major_compatible = compatible_versions(local_handshake.protocol_version, remote_handshake.protocol_version)
    except (ValueError, AttributeError, IndexError):
        major_compatible = False

    if not major_compatible:
        return _result(
            VerifiedContactOutcome.HANDSHAKE_INCOMPATIBLE,
            local_node_id=local_node_id,
            contact_endpoint=endpoint_str,
            remote_node_id=remote_node_id,
            protocol_version=remote_handshake.protocol_version,
            reason="remote protocol_version is not major-compatible with local protocol_version",
        )

    if not remote_handshake.accepted:
        return _result(
            VerifiedContactOutcome.HANDSHAKE_REJECTED,
            local_node_id=local_node_id,
            contact_endpoint=endpoint_str,
            remote_node_id=remote_node_id,
            protocol_version=remote_handshake.protocol_version,
            reason=remote_handshake.reason or "remote handshake rejected",
        )

    shared_capabilities = dict(remote_handshake.shared_capabilities)
    if not shared_capabilities.get("identity_proof"):
        # Remote did not advertise identity_proof as a shared capability;
        # this function's entire purpose requires it. Fail closed rather
        # than attempting a challenge the remote never agreed to support.
        return _result(
            VerifiedContactOutcome.IDENTITY_UNVERIFIED,
            local_node_id=local_node_id,
            contact_endpoint=endpoint_str,
            remote_node_id=remote_node_id,
            protocol_version=remote_handshake.protocol_version,
            shared_capabilities=shared_capabilities,
            reason="remote did not advertise a shared identity_proof capability",
        )

    # --- Step 2 of 2: POST /identity/respond -----------------------------
    # We (A) issue our own challenge locally -- no network round trip is
    # needed to "ask" the remote for one; we address it directly to the
    # remote_node_id the handshake just gave us, and send it to the SAME
    # pinned endpoint for the remote (B) to sign.
    challenge_store = identity_module.ChallengeStore()
    challenge = challenge_store.issue(
        from_node_id=local_node_id,
        to_node_id=remote_node_id,
        ttl_seconds=challenge_ttl_seconds,
    )
    challenge_payload = {
        "nonce": challenge.nonce,
        "from_node_id": challenge.from_node_id,
        "to_node_id": challenge.to_node_id,
        "protocol_version": challenge.protocol_version,
        "ttl_seconds": challenge.ttl_seconds,
    }

    proof_post = _bounded_post(transport, verdict, IDENTITY_RESPOND_PATH, challenge_payload)
    if proof_post.outcome is _PostOutcome.TRANSPORT_FAILED:
        return _result(
            VerifiedContactOutcome.IDENTITY_TRANSPORT_FAILED,
            local_node_id=local_node_id,
            contact_endpoint=endpoint_str,
            remote_node_id=remote_node_id,
            protocol_version=remote_handshake.protocol_version,
            shared_capabilities=shared_capabilities,
            reason=proof_post.reason,
        )
    if proof_post.outcome is _PostOutcome.MALFORMED_RESPONSE:
        return _result(
            VerifiedContactOutcome.IDENTITY_MALFORMED_RESPONSE,
            local_node_id=local_node_id,
            contact_endpoint=endpoint_str,
            remote_node_id=remote_node_id,
            protocol_version=remote_handshake.protocol_version,
            shared_capabilities=shared_capabilities,
            reason=proof_post.reason,
        )

    try:
        proof = identity_module.IdentityProof(**proof_post.body_json)
    except TypeError as exc:
        return _result(
            VerifiedContactOutcome.IDENTITY_MALFORMED_RESPONSE,
            local_node_id=local_node_id,
            contact_endpoint=endpoint_str,
            remote_node_id=remote_node_id,
            protocol_version=remote_handshake.protocol_version,
            shared_capabilities=shared_capabilities,
            reason=f"identity proof response missing required fields: {exc}",
        )

    # consume() performs every check called for by this phase's spec in
    # one call: nonce matches an issued (not-yet-consumed) challenge,
    # context binding (from/to/protocol_version), expiry, node_id<->
    # public_key binding signature validity, and the challenge-proof
    # signature itself. It also marks the nonce consumed unconditionally
    # (success or failure) -- see identity.ChallengeStore docstring --
    # so this exact proof object can never be replayed through this
    # challenge_store even if verify_contact() were called again with
    # the same captured proof.
    verification = challenge_store.consume(proof)

    if not verification.verified:
        return _result(
            VerifiedContactOutcome.IDENTITY_PROOF_INVALID,
            local_node_id=local_node_id,
            contact_endpoint=endpoint_str,
            remote_node_id=remote_node_id,
            protocol_version=remote_handshake.protocol_version,
            shared_capabilities=shared_capabilities,
            reason=verification.reason,
        )

    if proof.claimed_node_id != remote_node_id:
        # Defense in depth beyond what verify_proof() already checks
        # (claimed_node_id must equal challenge.to_node_id, which IS
        # remote_node_id by construction above) -- kept as an explicit,
        # independent assertion so a future refactor of the challenge
        # payload construction cannot silently drop this property.
        return _result(
            VerifiedContactOutcome.IDENTITY_PROOF_INVALID,
            local_node_id=local_node_id,
            contact_endpoint=endpoint_str,
            remote_node_id=remote_node_id,
            protocol_version=remote_handshake.protocol_version,
            shared_capabilities=shared_capabilities,
            reason="proof claimed_node_id does not match the handshake-reported remote_node_id",
        )

    # --- IDENTITY_VERIFIED -------------------------------------------
    # This is the ONLY state this function ever reaches that means
    # "cryptographic identity verified". It does not set, imply, or
    # touch trust_status, authority_level, or codex_update -- those
    # remain entirely the caller's separate, explicit decision (see
    # module docstring "Important identity boundary").
    return _result(
        VerifiedContactOutcome.IDENTITY_VERIFIED,
        local_node_id=local_node_id,
        contact_endpoint=endpoint_str,
        remote_node_id=remote_node_id,
        protocol_version=remote_handshake.protocol_version,
        shared_capabilities=shared_capabilities,
        reason=verification.reason,
        identity_status=verification.identity_status,
    )
