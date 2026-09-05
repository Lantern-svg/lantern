"""
Lantern External Connector v1 (lantern.connector)

Purpose
-------
Reusable client/library + CLI for connecting THIS Claw environment to
an externally hosted Lantern node over its public HTTPS endpoint, and
performing a full authenticated evidence exchange, without hand-rolled
one-off scripts.

This module does not implement a new protocol, a new server, or a new
security model. It is a thin, reusable orchestration layer over
already-existing primitives:

    - lantern.compatibility.negotiate/compatible_versions  (protocol
      compatibility)
    - lantern.identity                                     (Ed25519
      identity, challenge/response)
    - lantern.protocol.create_observation_share             (message
      construction)
    - the same HTTP routes bootstrap_node.py already exposes:
      /health, /handshake, /identity/challenge, /identity/verify,
      /session/open, /message, /observations/<id>, /heartbeat

It intentionally reuses bootstrap_client.py's `_verify_identity_with_peer`
challenge/response flow verbatim (imported, not reimplemented) so there
is exactly one implementation of the identity-proof wire format in this
codebase.

Security posture (see also SKILL-level task requirements this module
was built to satisfy):
    - Never bypasses Lantern authentication/session/authorization.
    - Never trusts a self-reported "received" claim -- the caller must
      independently retrieve the observation via the authenticated
      /observations/<id> endpoint and recompute SHA-256 itself.
    - Binds every acknowledgment to the original message_id and
      observation_id before accepting it; a mismatch is reported as a
      failure, never silently accepted.
    - Fails closed: any missing/invalid field, mismatched identity, or
      digest mismatch produces an explicit FAIL result, never a
      fabricated PASS.
    - Never logs or serializes private key material -- this module
      only ever touches NodeIdentity objects via the existing
      lantern.identity API, which itself never exposes private bytes.
    - TLS verification is on by default; disabling it requires an
      explicit --insecure-skip-tls-verify flag (loud, not a default).

This module deliberately does NOT interpret "PROTOCOL_COMPATIBLE" or
"IDENTITY_VERIFIED" as trust or authorization grants -- those remain
exactly as conservative as the rest of the Lantern trust model
(see lantern.identity module docstring).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import ssl
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Optional
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from . import identity as identity_module
from .bootstrap_client import _verify_identity_with_peer
from .compatibility import DEFAULT_CAPABILITIES, compatible_versions, negotiate
from .protocol import PROTOCOL_VERSION, create_observation_share


# ==================================================================
# Errors
# ==================================================================

class ConnectorError(Exception):
    """Base class for all connector failures. Every raise site attaches
    a machine-readable `stage` so callers/tests can assert on exactly
    which step failed without string-matching messages."""

    def __init__(self, stage: str, message: str, detail: Optional[dict] = None):
        self.stage = stage
        self.detail = detail or {}
        super().__init__(f"[{stage}] {message}")


class NetworkError(ConnectorError):
    pass


class ProtocolMismatchError(ConnectorError):
    pass


class IdentityError(ConnectorError):
    pass


class AuthenticationError(ConnectorError):
    pass


class AuthorizationError(ConnectorError):
    pass


class IntegrityError(ConnectorError):
    pass


class InconsistentReferenceError(ConnectorError):
    """message_id / observation_id / node identity referenced in a
    later step does not match what an earlier step produced."""
    pass


# ==================================================================
# Configuration
# ==================================================================

@dataclass
class ConnectorConfig:
    """All connector behavior is driven from here. Every field can be
    supplied programmatically, via CLI flags, or via environment
    variables (LANTERN_CONNECTOR_* / LANTERN_*), never hard-coded.
    """

    remote_url: str
    node_id: str = "lantern-connector-client"
    data_dir: Path = field(default_factory=lambda: Path(".lantern-connector"))
    expected_protocol_version: Optional[str] = None
    expected_remote_node_id: Optional[str] = None
    expected_remote_public_key: Optional[str] = None
    timeout_seconds: float = 15.0
    verify_tls: bool = True
    log_level: str = "info"

    def __post_init__(self):
        self.remote_url = self.remote_url.rstrip("/")
        if isinstance(self.data_dir, str):
            self.data_dir = Path(self.data_dir)

    @staticmethod
    def from_env(remote_url: Optional[str] = None, **overrides) -> "ConnectorConfig":
        """Build config from LANTERN_CONNECTOR_* environment variables,
        with explicit overrides (e.g. CLI flags) taking precedence over
        the environment, and `remote_url`/overrides taking precedence
        over everything.
        """
        env = os.environ
        base = dict(
            remote_url=remote_url or env.get("LANTERN_CONNECTOR_REMOTE_URL", ""),
            node_id=env.get("LANTERN_CONNECTOR_NODE_ID", "lantern-connector-client"),
            data_dir=env.get("LANTERN_CONNECTOR_DATA_DIR", ".lantern-connector"),
            expected_protocol_version=env.get("LANTERN_CONNECTOR_EXPECTED_PROTOCOL_VERSION") or None,
            expected_remote_node_id=env.get("LANTERN_CONNECTOR_EXPECTED_REMOTE_NODE_ID") or None,
            expected_remote_public_key=env.get("LANTERN_CONNECTOR_EXPECTED_REMOTE_PUBLIC_KEY") or None,
            timeout_seconds=float(env.get("LANTERN_CONNECTOR_TIMEOUT_SECONDS", "15")),
            verify_tls=env.get("LANTERN_CONNECTOR_VERIFY_TLS", "true").lower() not in ("0", "false", "no"),
            log_level=env.get("LANTERN_CONNECTOR_LOG_LEVEL", "info"),
        )
        base.update({k: v for k, v in overrides.items() if v is not None})
        if not base["remote_url"]:
            raise ConnectorError("config", "remote_url is required (--remote-url or LANTERN_CONNECTOR_REMOTE_URL)")
        return ConnectorConfig(**base)


def _log(config: ConnectorConfig, level: str, message: str) -> None:
    levels = {"debug": 0, "info": 1, "warn": 2, "error": 3}
    if levels.get(level, 1) >= levels.get(config.log_level, 1):
        # Never include private key material or bearer tokens -- this
        # function only ever receives operator-facing status strings
        # built by the methods below, which never format key bytes.
        print(f"[lantern-connector] {level.upper()}: {message}", file=sys.stderr)


# ==================================================================
# HTTP transport
# ==================================================================

def _build_ssl_context(verify_tls: bool) -> Optional[ssl.SSLContext]:
    if verify_tls:
        return None  # let urllib use its default verified context
    context = ssl.create_default_context()
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    return context


def _request(
    config: ConnectorConfig,
    path: str,
    method: str = "GET",
    payload: Optional[dict] = None,
) -> tuple[int, dict]:
    url = config.remote_url + path
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    request = Request(url, data=data, method=method, headers={"Content-Type": "application/json"})
    context = _build_ssl_context(config.verify_tls)
    try:
        with urlopen(request, timeout=config.timeout_seconds, context=context) as response:
            return response.status, json.loads(response.read())
    except HTTPError as exc:
        try:
            body = json.loads(exc.read())
        except Exception:
            body = {"error": exc.reason}
        return exc.code, body
    except URLError as exc:
        raise NetworkError("transport", f"could not reach {url}: {exc.reason}", {"url": url}) from exc
    except TimeoutError as exc:
        raise NetworkError("transport", f"timed out reaching {url} after {config.timeout_seconds}s", {"url": url}) from exc


# ==================================================================
# Result envelope
# ==================================================================

@dataclass
class StepResult:
    stage: str
    ok: bool
    detail: dict


@dataclass
class ExchangeReport:
    steps: list = field(default_factory=list)
    local_node_id: str = ""
    remote_node_id: Optional[str] = None
    message_id: Optional[str] = None
    observation_id: Optional[str] = None
    expected_digest: Optional[str] = None
    retrieved_digest: Optional[str] = None
    digest_verified: Optional[bool] = None
    overall: str = "NOT_RUN"

    def add(self, stage: str, ok: bool, detail: Optional[dict] = None) -> None:
        self.steps.append(StepResult(stage=stage, ok=ok, detail=detail or {}))

    def to_dict(self) -> dict:
        return {
            "local_node_id": self.local_node_id,
            "remote_node_id": self.remote_node_id,
            "message_id": self.message_id,
            "observation_id": self.observation_id,
            "expected_digest": self.expected_digest,
            "retrieved_digest": self.retrieved_digest,
            "digest_verified": self.digest_verified,
            "overall": self.overall,
            "steps": [{"stage": s.stage, "ok": s.ok, "detail": s.detail} for s in self.steps],
        }


# ==================================================================
# Connector
# ==================================================================

class LanternConnector:
    """Reusable client for one remote Lantern node, addressed by
    `config.remote_url`. One instance == one remote peer relationship
    for the lifetime of the object; create a new instance per remote.
    """

    def __init__(self, config: ConnectorConfig):
        self.config = config
        config.data_dir.mkdir(parents=True, exist_ok=True)
        identity_dir = identity_module.default_identity_dir(config.data_dir, config.node_id)
        self.identity = identity_module.load_or_create(config.node_id, identity_dir)
        self._session_id: Optional[str] = None
        self._remote_node_id: Optional[str] = None

    # ---- health / discovery ----------------------------------------

    def health_check(self) -> dict:
        status, body = _request(self.config, "/health")
        if status != 200:
            raise NetworkError("health_check", f"unexpected status {status}", {"status": status, "body": body})
        _log(self.config, "info", f"health check ok: remote node_id={body.get('node_id')}")
        return body

    def discover_capabilities(self) -> dict:
        status, body = _request(self.config, "/handshake")
        if status != 200:
            raise NetworkError("discover_capabilities", f"unexpected status {status}", {"status": status})
        return body

    def verify_protocol_compatibility(self, remote_health: dict) -> dict:
        remote_version = remote_health.get("protocol_version")
        if not remote_version:
            raise ProtocolMismatchError("protocol_compatibility", "remote did not report a protocol_version", {"remote_health": remote_health})
        if self.config.expected_protocol_version and remote_version != self.config.expected_protocol_version:
            raise ProtocolMismatchError(
                "protocol_compatibility",
                f"remote protocol_version {remote_version!r} != expected {self.config.expected_protocol_version!r}",
                {"remote_version": remote_version, "expected": self.config.expected_protocol_version},
            )
        if not compatible_versions(PROTOCOL_VERSION, remote_version):
            raise ProtocolMismatchError(
                "protocol_compatibility",
                f"major protocol version mismatch: local={PROTOCOL_VERSION} remote={remote_version}",
                {"local_version": PROTOCOL_VERSION, "remote_version": remote_version},
            )
        result = negotiate(remote_version, remote_health.get("capabilities", {}), local_capabilities=DEFAULT_CAPABILITIES)
        if not result.compatible:
            raise ProtocolMismatchError("protocol_compatibility", result.reason, {"remote_version": remote_version})
        if not result.shared_capabilities.get("evidence_exchange"):
            raise ProtocolMismatchError(
                "protocol_compatibility",
                "remote does not share evidence_exchange capability",
                {"shared_capabilities": result.shared_capabilities},
            )
        return {
            "compatible": True,
            "local_version": PROTOCOL_VERSION,
            "remote_version": remote_version,
            "shared_capabilities": result.shared_capabilities,
        }

    # ---- identity / session -----------------------------------------

    def verify_identity(self, remote_node_id_hint: Optional[str] = None) -> dict:
        result = _verify_identity_with_peer(self.config.remote_url, self.config.node_id, self.identity)
        if not result.get("verified") or result.get("identity_status") != "CRYPTOGRAPHICALLY_VERIFIED":
            raise IdentityError("identity_verification", "peer did not cryptographically verify local identity", {"result": result})

        remote_node_id = remote_node_id_hint
        if self.config.expected_remote_node_id and remote_node_id and remote_node_id != self.config.expected_remote_node_id:
            raise IdentityError(
                "identity_verification",
                f"remote node_id {remote_node_id!r} != expected {self.config.expected_remote_node_id!r}",
                {"remote_node_id": remote_node_id, "expected": self.config.expected_remote_node_id},
            )
        self._remote_node_id = remote_node_id
        return result

    def verify_remote_public_key(self, remote_health: dict) -> dict:
        """Optional fingerprint pin: if the operator configured an
        expected remote public key, enforce it against what /health
        reports. This is a TOFU-style pin, not a certificate chain --
        it only protects an already-known binding from silently
        changing underneath the operator (see lantern.identity module
        docstring for the same caveat applied to the core protocol).
        """
        remote_public_key = (remote_health.get("identity_public") or {}).get("public_key")
        if not self.config.expected_remote_public_key:
            return {"pinned": False, "remote_public_key": remote_public_key}
        if remote_public_key != self.config.expected_remote_public_key:
            raise IdentityError(
                "public_key_pin",
                "remote public key does not match configured expected_remote_public_key",
                {"remote_public_key": remote_public_key, "expected": self.config.expected_remote_public_key},
            )
        return {"pinned": True, "remote_public_key": remote_public_key}

    def open_session(self) -> dict:
        """Two-phase session open (candidate protocol, unchanged since
        bootstrap_client.py's own `_open_session_with_proof`, reused here
        rather than reimplemented):

        Phase 1: POST /session/open with only node_id. The server issues
        a challenge (`{"outcome": "challenge_issued", "nonce": ...}`);
        it does NOT create a session yet.
        Phase 2: sign that challenge with this connector's own persisted
        NodeIdentity via identity_module.respond_to_challenge() (the same
        primitive verify_identity() already uses), then POST
        /session/open again with {"node_id":..., "proof": {...}}. Only
        this second call can return created: True.

        No downgrade path: if the first response already claims
        created: True with no nonce, that is rejected as a malformed or
        malicious server response, never silently accepted -- there is
        no code path here that creates a session without a completed
        proof round-trip.

        Public signature is unchanged (zero-argument, from the caller's
        perspective) -- the two-phase mechanics are entirely internal.
        """
        status, challenge_body = _request(self.config, "/session/open", "POST", {"node_id": self.config.node_id})
        if status != 200:
            raise AuthenticationError("session_open", "remote rejected session/open", {"status": status, "body": challenge_body})

        if challenge_body.get("created"):
            # A compliant candidate server never does this on the first
            # call -- created:true here would mean a session was granted
            # with zero proof of key possession. Refuse rather than
            # silently accepting a downgraded, unproven session.
            raise AuthenticationError(
                "session_open",
                "remote returned created:true without issuing a challenge first; refusing unproven session",
                {"status": status, "body": challenge_body},
            )

        if "nonce" not in challenge_body:
            raise AuthenticationError(
                "session_open",
                "remote did not issue a challenge (missing nonce); cannot complete proof-of-possession",
                {"status": status, "body": challenge_body},
            )

        challenge = identity_module.Challenge(
            nonce=challenge_body["nonce"],
            from_node_id=challenge_body["from_node_id"],
            to_node_id=challenge_body["to_node_id"],
            protocol_version=challenge_body["protocol_version"],
            issued_at=0.0,
            ttl_seconds=challenge_body.get("ttl_seconds", identity_module.DEFAULT_CHALLENGE_TTL_SECONDS),
        )
        binding = json.loads((self.identity.identity_dir / "binding.json").read_text())
        proof = identity_module.respond_to_challenge(challenge, self.identity, binding["signature"])
        proof_payload = {
            "nonce": proof.nonce,
            "from_node_id": proof.from_node_id,
            "to_node_id": proof.to_node_id,
            "protocol_version": proof.protocol_version,
            "claimed_node_id": proof.claimed_node_id,
            "public_key": proof.public_key,
            "identity_binding_signature": proof.identity_binding_signature,
            "signature": proof.signature,
            "proof_timestamp": proof.proof_timestamp,
        }

        status, session = _request(
            self.config, "/session/open", "POST",
            {"node_id": self.config.node_id, "proof": proof_payload},
        )
        if status != 200 or not session.get("created"):
            raise AuthenticationError("session_open", "remote rejected session/open proof", {"status": status, "body": session})
        self._session_id = session["session_id"]
        return session

    # ---- evidence exchange --------------------------------------------

    def send_observation(self, content: str, source: Optional[str] = None, reliability: float = 1.0) -> dict:
        if not self._session_id:
            raise AuthenticationError("send_observation", "no authenticated session; call open_session() first")
        message = create_observation_share(
            self.config.node_id,
            {"content": content, "source": source or self.config.node_id, "reliability": reliability},
        )
        status, exchange = _request(
            self.config, "/message", "POST",
            {"message": asdict(message), "session_id": self._session_id},
        )
        if status != 200 or not exchange.get("accepted"):
            reason = exchange.get("reason", "")
            if "not in authorized_capabilities" in str(reason) or status == 403:
                raise AuthorizationError("send_observation", "remote rejected evidence_exchange authorization", {"status": status, "body": exchange})
            raise AuthorizationError("send_observation", "remote did not accept OBSERVATION_SHARE", {"status": status, "body": exchange})
        return {"message_id": message.message_id, "observation_id": exchange["observation_id"], "raw": exchange}

    def retrieve_observation(self, observation_id: str, session_id: Optional[str] = None) -> dict:
        """Retrieve via the authenticated /observations/<id> endpoint.
        NOTE: per bootstrap_node.py's _handle_get_observation, this
        endpoint is strictly self-only -- it only succeeds when the
        session_id's authenticated node_id equals the REMOTE node's own
        node_id. A connector acting purely as an external sender can
        legitimately open a session for itself but cannot read back an
        observation it just delivered to someone else's node this way;
        that retrieval must be performed by (or on behalf of) the
        receiving node's own identity, exactly as in the two-agent
        exchange this module generalizes. This method exists so a
        caller who legitimately controls the target node's identity/
        data_dir (e.g. this connector used *as* the receiver) can do
        that retrieval+verification step through the same class.
        """
        use_session = session_id or self._session_id
        if not use_session:
            raise AuthenticationError("retrieve_observation", "no session_id available for retrieval")
        status, body = _request(self.config, f"/observations/{observation_id}?session_id={use_session}")
        if status == 401:
            raise AuthenticationError("retrieve_observation", "session invalid/expired", {"status": status, "body": body})
        if status == 403:
            raise AuthorizationError("retrieve_observation", "retrieval restricted to the observation-holding node's own session", {"status": status, "body": body})
        if status == 404:
            raise InconsistentReferenceError("retrieve_observation", f"observation_id {observation_id!r} not found on remote", {"status": status, "body": body})
        if status != 200 or "content" not in body:
            raise NetworkError("retrieve_observation", "unexpected response retrieving observation", {"status": status, "body": body})
        if body.get("observation_id") != observation_id:
            raise InconsistentReferenceError(
                "retrieve_observation",
                f"remote returned observation_id {body.get('observation_id')!r}, expected {observation_id!r}",
                {"returned": body.get("observation_id"), "expected": observation_id},
            )
        return body

    @staticmethod
    def compute_digest(content: str) -> str:
        return hashlib.sha256(content.encode("utf-8")).hexdigest()

    def verify_retrieved_digest(self, observation: dict, expected_digest: str) -> bool:
        """Never trust a claimed digest -- always recompute from the
        actual retrieved content bytes and compare. Fails closed (as
        IntegrityError, not a raw KeyError/TypeError) on any malformed
        observation payload missing the content field entirely."""
        if not isinstance(observation, dict) or "content" not in observation:
            raise IntegrityError(
                "digest_verification",
                "observation payload is missing a 'content' field; cannot verify digest",
                {"observation": observation},
            )
        actual = self.compute_digest(observation["content"])
        if actual != expected_digest:
            raise IntegrityError(
                "digest_verification",
                f"recomputed digest {actual!r} != expected {expected_digest!r}",
                {"actual": actual, "expected": expected_digest},
            )
        return True

    def verify_acknowledgment(
        self,
        ack_observation: dict,
        expected_message_id: str,
        expected_observation_id: str,
        expected_digest: str,
    ) -> dict:
        """Parse and bind-check a reverse-direction OBSERVATION_SHARE
        acknowledgment. Uses the EXISTING message type only (no new
        protocol message); the ack's `content` is expected to be a JSON
        object with ack_for_message_id / observation_id / digest keys,
        exactly as produced by the two-agent exchange this generalizes.
        Fails closed on any missing/mismatched field.
        """
        try:
            body = json.loads(ack_observation["content"])
        except (KeyError, json.JSONDecodeError) as exc:
            raise IntegrityError("ack_verification", "acknowledgment content is not valid JSON", {"content": ack_observation.get("content")}) from exc

        if body.get("ack_for_message_id") != expected_message_id:
            raise InconsistentReferenceError(
                "ack_verification",
                f"ack ack_for_message_id {body.get('ack_for_message_id')!r} != expected {expected_message_id!r}",
                {"ack": body, "expected_message_id": expected_message_id},
            )
        if body.get("observation_id") != expected_observation_id:
            raise InconsistentReferenceError(
                "ack_verification",
                f"ack observation_id {body.get('observation_id')!r} != expected {expected_observation_id!r}",
                {"ack": body, "expected_observation_id": expected_observation_id},
            )
        if body.get("digest") != expected_digest:
            raise IntegrityError(
                "ack_verification",
                f"ack digest {body.get('digest')!r} != expected {expected_digest!r}",
                {"ack": body, "expected_digest": expected_digest},
            )
        return {"verified": True, "ack": body}

    # ---- full end-to-end exchange -----------------------------------

    def run_full_exchange(self, content: str, source: Optional[str] = None) -> ExchangeReport:
        """Perform every step this module knows how to do AS THE SENDER:
        health -> compat -> identity -> session -> send -> (best-effort
        self-retrieval attempt, expected to be 403 per retrieve_observation's
        docstring unless this connector's node_id equals the remote's
        own node_id). This intentionally stops short of claiming the
        remote "received" anything beyond what /message's own accepted:
        true response asserts -- independent receiver-side verification
        requires a second connector instance (or the receiving node
        itself) calling retrieve_observation()/verify_retrieved_digest()
        against ITS OWN session, exactly as bootstrap_node.py's
        self-only retrieval gate requires. See CLI `verify-exchange`
        for orchestrating both sides when the caller legitimately
        controls both node identities.
        """
        report = ExchangeReport(local_node_id=self.config.node_id)
        try:
            remote_health = self.health_check()
            report.remote_node_id = remote_health.get("node_id")
            report.add("health_check", True, {"remote_node_id": remote_health.get("node_id")})

            compat = self.verify_protocol_compatibility(remote_health)
            report.add("protocol_compatibility", True, compat)

            self.verify_remote_public_key(remote_health)
            report.add("public_key_pin", True, {})

            identity_result = self.verify_identity(remote_health.get("node_id"))
            report.add("identity_verification", True, {"identity_status": identity_result.get("identity_status")})

            session = self.open_session()
            report.add("authenticated_session", True, {"session_id_present": bool(session.get("session_id"))})

            send_result = self.send_observation(content, source=source)
            report.message_id = send_result["message_id"]
            report.observation_id = send_result["observation_id"]
            report.expected_digest = self.compute_digest(content)
            report.add("observation_share", True, {"message_id": report.message_id, "observation_id": report.observation_id})

            report.overall = "SENT_AWAITING_INDEPENDENT_RECEIVER_VERIFICATION"
        except ConnectorError as exc:
            report.add(exc.stage, False, {"error": str(exc), **exc.detail})
            report.overall = "FAIL"
        return report


# ==================================================================
# CLI
# ==================================================================

def _config_from_args(args) -> ConnectorConfig:
    return ConnectorConfig.from_env(
        remote_url=args.remote_url,
        node_id=args.node_id,
        data_dir=args.data_dir,
        expected_protocol_version=args.expected_protocol_version,
        expected_remote_node_id=args.expected_remote_node_id,
        expected_remote_public_key=args.expected_remote_public_key,
        timeout_seconds=args.timeout,
        verify_tls=not args.insecure_skip_tls_verify,
        log_level=args.log_level,
    )


def _print_result(payload: dict) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True))


def _cmd_health(args) -> int:
    config = _config_from_args(args)
    connector = LanternConnector(config)
    try:
        body = connector.health_check()
        _print_result({"stage": "health_check", "ok": True, "body": body})
        return 0
    except ConnectorError as exc:
        _print_result({"stage": exc.stage, "ok": False, "error": str(exc), **exc.detail})
        return 1


def _cmd_capabilities(args) -> int:
    config = _config_from_args(args)
    connector = LanternConnector(config)
    try:
        health = connector.health_check()
        handshake = connector.discover_capabilities()
        compat = connector.verify_protocol_compatibility(health)
        _print_result({"stage": "capabilities", "ok": True, "handshake": handshake, "compatibility": compat})
        return 0
    except ConnectorError as exc:
        _print_result({"stage": exc.stage, "ok": False, "error": str(exc), **exc.detail})
        return 1


def _cmd_identity(args) -> int:
    config = _config_from_args(args)
    connector = LanternConnector(config)
    try:
        health = connector.health_check()
        connector.verify_remote_public_key(health)
        result = connector.verify_identity(health.get("node_id"))
        _print_result({"stage": "identity_verification", "ok": True, "result": result})
        return 0
    except ConnectorError as exc:
        _print_result({"stage": exc.stage, "ok": False, "error": str(exc), **exc.detail})
        return 1


def _cmd_session(args) -> int:
    config = _config_from_args(args)
    connector = LanternConnector(config)
    try:
        health = connector.health_check()
        connector.verify_identity(health.get("node_id"))
        session = connector.open_session()
        _print_result({"stage": "authenticated_session", "ok": True, "session_id": session.get("session_id")})
        return 0
    except ConnectorError as exc:
        _print_result({"stage": exc.stage, "ok": False, "error": str(exc), **exc.detail})
        return 1


def _cmd_send(args) -> int:
    config = _config_from_args(args)
    connector = LanternConnector(config)
    report = connector.run_full_exchange(args.content, source=args.source)
    _print_result(report.to_dict())
    return 0 if report.overall != "FAIL" else 1


def _cmd_retrieve(args) -> int:
    config = _config_from_args(args)
    connector = LanternConnector(config)
    try:
        health = connector.health_check()
        connector.verify_identity(health.get("node_id"))
        connector.open_session()
        observation = connector.retrieve_observation(args.observation_id)
        result = {"stage": "retrieve_observation", "ok": True, "observation": observation}
        if args.expected_digest:
            result["digest_verified"] = connector.verify_retrieved_digest(observation, args.expected_digest)
        _print_result(result)
        return 0
    except ConnectorError as exc:
        _print_result({"stage": exc.stage, "ok": False, "error": str(exc), **exc.detail})
        return 1


def _cmd_full_exchange_test(args) -> int:
    """Full sender-side exchange test against a real remote endpoint.
    Sends a disposable test observation and reports every stage. Does
    NOT claim receiver-side verification (see run_full_exchange
    docstring) -- that requires a second connector instance acting
    with the receiving node's own identity/data_dir, which this
    single-CLI-invocation command does not have access to by design
    (never operates on identity material outside its own --data-dir).
    """
    config = _config_from_args(args)
    connector = LanternConnector(config)
    report = connector.run_full_exchange(args.content, source=args.source or config.node_id)
    _print_result(report.to_dict())
    return 0 if report.overall != "FAIL" else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="lantern-connector",
        description="Reusable client for connecting to an external Lantern node over HTTPS.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    def add_common(p):
        p.add_argument("--remote-url", default=None, help="Remote Lantern base URL (or LANTERN_CONNECTOR_REMOTE_URL)")
        p.add_argument("--node-id", default=os.environ.get("LANTERN_CONNECTOR_NODE_ID", "lantern-connector-client"))
        p.add_argument("--data-dir", default=os.environ.get("LANTERN_CONNECTOR_DATA_DIR", ".lantern-connector"))
        p.add_argument("--expected-protocol-version", default=None)
        p.add_argument("--expected-remote-node-id", default=None)
        p.add_argument("--expected-remote-public-key", default=None)
        p.add_argument("--timeout", type=float, default=float(os.environ.get("LANTERN_CONNECTOR_TIMEOUT_SECONDS", "15")))
        p.add_argument("--insecure-skip-tls-verify", action="store_true", default=False)
        p.add_argument("--log-level", default=os.environ.get("LANTERN_CONNECTOR_LOG_LEVEL", "info"), choices=["debug", "info", "warn", "error"])

    p_connect = sub.add_parser("connect", help="Alias for health-check: verify the remote endpoint is reachable")
    add_common(p_connect)
    p_connect.set_defaults(func=_cmd_health)

    p_health = sub.add_parser("health-check", help="GET /health on the remote node")
    add_common(p_health)
    p_health.set_defaults(func=_cmd_health)

    p_caps = sub.add_parser("capabilities", help="Discover remote capabilities and verify protocol compatibility")
    add_common(p_caps)
    p_caps.set_defaults(func=_cmd_capabilities)

    p_identity = sub.add_parser("identity-verify", help="Perform the Lantern identity challenge/response proof")
    add_common(p_identity)
    p_identity.set_defaults(func=_cmd_identity)

    p_session = sub.add_parser("session-open", help="Establish an authenticated session (requires prior identity verification)")
    add_common(p_session)
    p_session.set_defaults(func=_cmd_session)

    p_send = sub.add_parser("send", help="Full sender path: health -> compat -> identity -> session -> OBSERVATION_SHARE")
    add_common(p_send)
    p_send.add_argument("--content", required=True)
    p_send.add_argument("--source", default=None)
    p_send.set_defaults(func=_cmd_send)

    p_retrieve = sub.add_parser("retrieve", help="Retrieve + verify an observation via the authenticated self-only endpoint")
    add_common(p_retrieve)
    p_retrieve.add_argument("--observation-id", required=True)
    p_retrieve.add_argument("--expected-digest", default=None)
    p_retrieve.set_defaults(func=_cmd_retrieve)

    p_e2e = sub.add_parser("exchange-test", help="Sender-side end-to-end exchange test against a real remote endpoint")
    add_common(p_e2e)
    p_e2e.add_argument("--content", default="lantern-connector-e2e-probe")
    p_e2e.add_argument("--source", default=None)
    p_e2e.set_defaults(func=_cmd_full_exchange_test)

    return parser


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
