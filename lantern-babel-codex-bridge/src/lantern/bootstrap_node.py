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
from . import capability_authorization
from .capability_authorization import AuthorizationPolicy, EMPTY_POLICY
from .compatibility import DEFAULT_CAPABILITIES, negotiate
from .continuity import local_watermark
from .core import Chronicle, Lantern
from .handshake import HandshakeRequest, create_handshake, evaluate_handshake
from .heartbeat import create_heartbeat, evaluate_connection
from . import identity as identity_module
from . import observation_exchange
from .participants import find as find_participant
from .participants import inspect_all, next_verification_step
from .protocol import ProtocolMessage
from .rendezvous import JoinMonitor
from . import verified_session
from .verified_contact import VerifiedContactOutcome, VerifiedContactResult


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

    def __init__(
        self,
        node_id: str,
        chronicle_path: str | Path,
        join_chronicle_path: str | Path | None = None,
        identity_dir: str | Path | None = None,
        *,
        allow_legacy_message_ingestion: bool = False,
        authorization_policy: AuthorizationPolicy | None = None,
        session_ttl_seconds: float = verified_session.DEFAULT_SESSION_TTL_SECONDS,
    ):
        self.node_id = node_id
        self.chronicle = Chronicle(chronicle_path)
        self.lantern = Lantern(chronicle_filename=chronicle_path)
        self.agent = LanternAgent(self.lantern, chronicle=self.chronicle)
        self.bridge = LanternAgentBridge(self.agent)
        self.started_monotonic = time.monotonic()

        # ------------------------------------------------------------
        # Secure /message migration state (Phase 4 slice).
        #
        # allow_legacy_message_ingestion: operator-controlled, explicit,
        # default OFF. When False (the default for any newly constructed
        # node), POST /message OBSERVATION_SHARE requests that do not
        # carry a valid verified session_id are rejected with
        # LEGACY_MODE_DISABLED -- self-declared peer_capabilities alone
        # is never sufficient to create a local Observation. When True,
        # the untouched legacy negotiated-capability behavior applies
        # exactly as before, and legacy traffic is never marked as
        # cryptographically verified, never gets a session, and never
        # gains trust/authority/Codex permission -- see receive().
        self.allow_legacy_message_ingestion = allow_legacy_message_ingestion

        # authorization_policy: what capabilities this operator is
        # explicitly willing to grant to which verified node_ids, for the
        # SECURE /message path only. Reused verbatim from
        # capability_authorization.py -- never reimplemented here. The
        # conservative default (EMPTY_POLICY) authorizes nothing, so a
        # freshly verified session is never automatically authorized for
        # evidence_exchange merely by existing.
        self.authorization_policy = (
            authorization_policy if authorization_policy is not None else EMPTY_POLICY
        )

        # sessions: in-memory, per-process, non-persistent verified
        # session table -- mirrors _known_public_keys below exactly (see
        # verified_session.py module docstring). A session only proves
        # "this process recently cryptographically verified this
        # node_id"; it carries no capability list and implies no trust.
        self.sessions = verified_session.SessionStore(ttl_seconds=session_ttl_seconds)

        # Replay-dedup ledger for the secure /message path, reused across
        # calls (see observation_exchange.py's ObservationExchangeLedger
        # docstring: replay protection is only meaningful when the same
        # ledger instance persists across calls for this process).
        self._observation_ledger = observation_exchange.ObservationExchangeLedger()

        # Cryptographic node identity: a dedicated directory, never the
        # Chronicle path or a subdirectory of it. This is a structural
        # choice (see lantern.identity module docstring) so "the private
        # key never enters the Chronicle" does not depend on anyone
        # remembering a convention -- the identity store and the belief/
        # evidence Chronicle are simply never the same file or directory.
        if identity_dir is None:
            identity_dir = identity_module.default_identity_dir(
                Path(str(chronicle_path)).parent, node_id
            )
        self.crypto_identity = identity_module.load_or_create(node_id, identity_dir)
        self.challenge_store = identity_module.ChallengeStore()
        # node_id -> public_key_hex, recorded the first time this process
        # sees a CRYPTOGRAPHICALLY_VERIFIED proof for that node_id. Used
        # for trust-on-first-use pinning: a later proof for the same
        # node_id presenting a DIFFERENT key is rejected as a possible
        # public-key substitution. In-memory only, per-process -- not a
        # durable trust store and not a Chronicle-backed record.
        self._known_public_keys: dict[str, str] = {}

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

    def identity_capabilities(self) -> dict:
        """DEFAULT_CAPABILITIES with identity_proof enabled, since this
        node has a loaded NodeIdentity. Does not mutate the module-level
        default dict."""
        capabilities = dict(DEFAULT_CAPABILITIES)
        capabilities["identity_proof"] = True
        return capabilities

    def identity_public(self) -> dict:
        """Everything about this node's identity that is safe to share:
        node_id, public key, and the self-signed binding. Never includes
        private key material -- there is no code path in this method (or
        anywhere in lantern.identity) that reads private_key.bin or the
        in-memory SigningKey's raw bytes.
        """
        binding_path = self.crypto_identity.identity_dir / "binding.json"
        binding = json.loads(binding_path.read_text())
        return {
            "node_id": self.crypto_identity.node_id,
            "public_key": self.crypto_identity.public_key_hex,
            "binding_signature": binding["signature"],
        }

    def identity(self) -> dict:
        watermark = local_watermark(self.lantern)
        return {
            "node_id": self.node_id,
            "protocol_version": create_handshake().protocol_version,
            "capabilities": self.identity_capabilities(),
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
        request = create_handshake(self.identity_capabilities())
        request.node_id = self.node_id
        return request

    def evaluate_incoming_handshake(self, request: HandshakeRequest):
        # Responder must return ITS OWN configured node_id, not a fresh
        # uuid4() per call -- see handshake.py module docstring "Prior to
        # this parameter" note. This is the fix for the responder
        # identity inconsistency found during Phase 2 research.
        return evaluate_handshake(
            request,
            supported_capabilities=self.identity_capabilities(),
            responder_node_id=self.node_id,
        )

    # ==================================================
    # Identity challenge / proof (optional extension,
    # gated by the identity_proof capability -- never
    # required for a legacy handshake to succeed)
    # ==================================================

    def issue_identity_challenge(self, requester_node_id: str) -> dict:
        """This node (as initiator A) issues a challenge to a peer it
        wants to verify. Pure bookkeeping -- no belief/evidence/Codex
        state touched."""
        challenge = self.challenge_store.issue(
            from_node_id=self.node_id, to_node_id=requester_node_id
        )
        return {
            "nonce": challenge.nonce,
            "from_node_id": challenge.from_node_id,
            "to_node_id": challenge.to_node_id,
            "protocol_version": challenge.protocol_version,
            "ttl_seconds": challenge.ttl_seconds,
        }

    def respond_identity_challenge(self, challenge_data: dict) -> dict:
        """This node (as responder B) answers a challenge issued by a
        peer, using its own persisted NodeIdentity. Never sees or needs
        the peer's private key -- only signs with its own."""
        challenge = identity_module.Challenge(
            nonce=challenge_data["nonce"],
            from_node_id=challenge_data["from_node_id"],
            to_node_id=challenge_data["to_node_id"],
            protocol_version=challenge_data["protocol_version"],
            issued_at=time.monotonic(),
            ttl_seconds=challenge_data.get("ttl_seconds", identity_module.DEFAULT_CHALLENGE_TTL_SECONDS),
        )
        binding = json.loads((self.crypto_identity.identity_dir / "binding.json").read_text())
        proof = identity_module.respond_to_challenge(challenge, self.crypto_identity, binding["signature"])
        return {
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

    def verify_identity_proof(self, proof_data: dict) -> dict:
        """This node (as initiator A) verifies a proof it received back.
        Pure verification -- never mutates trust_status or
        authority_level, which remain a completely separate decision.
        Trust-on-first-use pinning: if this process has already recorded
        a public key for this node_id, a different key is rejected.
        """
        proof = identity_module.IdentityProof(**proof_data)
        expected_key = self._known_public_keys.get(proof.claimed_node_id)
        result = self.challenge_store.consume(proof, expected_public_key=expected_key)
        if result.verified:
            self._known_public_keys[proof.claimed_node_id] = proof.public_key
        return {
            "verified": result.verified,
            "reason": result.reason,
            "identity_status": result.identity_status,
        }

    # ==================================================
    # Verified session (secure /message path, Phase 4 slice)
    # ==================================================

    def open_session(self, node_id: str) -> dict:
        """Issue a short-lived verified session for node_id.

        May only succeed if THIS process has already recorded a
        CRYPTOGRAPHICALLY_VERIFIED public key for node_id via
        verify_identity_proof() -- i.e. this node (as initiator A)
        already completed a real challenge/response proof for the
        caller. There is no other way to reach CREATED: this method
        performs no cryptographic verification itself, it only checks
        that verification already happened and was recorded.

        This does NOT grant trust or authorize any capability -- see
        verified_session.py module docstring. A session proves identity
        continuity for this process only; capability_authorization.py
        remains the sole authority for what a session's node_id may
        actually do.
        """
        if not isinstance(node_id, str) or not node_id:
            raise ValueError("node_id (string) is required")

        # _known_public_keys is populated ONLY on a successful
        # CRYPTOGRAPHICALLY_VERIFIED proof (see verify_identity_proof()
        # above) -- presence here is exactly "this process has already
        # cryptographically verified this node_id", the one precondition
        # verified_session.create_session() requires.
        if node_id in self._known_public_keys:
            identity_status = identity_module.CRYPTOGRAPHICALLY_VERIFIED
        else:
            identity_status = identity_module.UNVERIFIED

        result = self.sessions.create_session(node_id=node_id, identity_status=identity_status)
        response = result.to_dict()
        if result.created:
            response["session_id"] = result.session.session_id
            response["expires_at_monotonic"] = result.session.expires_at_monotonic
        return response

    def _authorized_capability_decision(self, node_id: str):
        """Build a CapabilityDecision for an already-verified session's
        node_id, using THIS node's own authorization_policy. Reuses
        capability_authorization.authorize() verbatim -- never
        reimplemented here (see module docstring).

        A minimal VerifiedContactResult is constructed in-memory purely
        to satisfy authorize()'s existing signature; it is not obtained
        via verified_contact.verify_contact() because bootstrap_node's
        identity flow (challenge/respond/verify over /identity/*) is a
        separate, already-established path to the same
        CRYPTOGRAPHICALLY_VERIFIED fact -- the session's existence IS
        the proof, re-derived from _known_public_keys exactly as
        open_session() does, never assumed.
        """
        identity_status = (
            identity_module.CRYPTOGRAPHICALLY_VERIFIED
            if node_id in self._known_public_keys
            else identity_module.UNVERIFIED
        )
        verified = VerifiedContactResult(
            outcome=(
                VerifiedContactOutcome.IDENTITY_VERIFIED
                if identity_status == identity_module.CRYPTOGRAPHICALLY_VERIFIED
                else VerifiedContactOutcome.IDENTITY_UNVERIFIED
            ),
            local_node_id=self.node_id,
            remote_node_id=node_id,
            identity_status=identity_status,
            protocol_version=create_handshake().protocol_version,
            shared_capabilities=dict(self.identity_capabilities()),
            contact_endpoint="",
            reason="derived from bootstrap_node verified session",
        )
        return capability_authorization.authorize(
            verified,
            requested=[observation_exchange.EvidenceExchangeCapability],
            policy=self.authorization_policy,
        )

    def receive_secure(self, message_data: dict, session_id: str) -> dict:
        """Secure /message path: requires a valid, non-expired
        VerifiedSession whose node_id matches message.source, AND
        explicit evidence_exchange authorization from
        self.authorization_policy. Delegates the actual accept/reject
        decision to observation_exchange.receive_observation() --
        reused verbatim, never reimplemented.
        """
        try:
            message = ProtocolMessage.decode(json.dumps(message_data))
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise ValueError(f"Malformed ProtocolMessage: {exc}") from exc

        if not _validate_wire_shape(message):
            raise ValueError("Invalid ProtocolMessage")

        source = message.source if isinstance(message.source, str) else None
        lookup = self.sessions.resolve_session(session_id=session_id, expected_source=source)

        if not lookup.valid:
            return {
                "accepted": False,
                "action": "reject",
                "reason": f"{lookup.outcome}: {lookup.reason}",
                "data": {},
                "protocol": message.protocol,
                "message_type": message.message_type,
                "source": message.source,
                "watermark": local_watermark(self.lantern).to_dict(),
            }

        if message.message_type != "OBSERVATION_SHARE":
            return {
                "accepted": False,
                "action": "reject",
                "reason": (
                    "secure /message currently only accepts OBSERVATION_SHARE; "
                    f"got {message.message_type!r}"
                ),
                "data": {},
                "protocol": message.protocol,
                "message_type": message.message_type,
                "source": message.source,
                "watermark": local_watermark(self.lantern).to_dict(),
            }

        decision = self._authorized_capability_decision(lookup.node_id)
        result = observation_exchange.receive_observation(
            message,
            identity_status=identity_module.CRYPTOGRAPHICALLY_VERIFIED,
            decision=decision,
            agent=self.agent,
            ledger=self._observation_ledger,
        )

        data = {}
        return {
            "accepted": result.accepted,
            "action": "accept" if result.accepted else "reject",
            "reason": result.reason,
            "data": data,
            "observation_id": result.observation_id,
            "protocol": message.protocol,
            "message_type": message.message_type,
            "source": message.source,
            "watermark": local_watermark(self.lantern).to_dict(),
        }

    def receive(self, message_data: dict, peer_capabilities: dict, session_id: str | None = None) -> dict:
        """POST /message entry point.

        If session_id is provided, the SECURE path is used
        unconditionally (see receive_secure()) -- a caller presenting a
        session_id is always held to the stricter contract, regardless
        of allow_legacy_message_ingestion.

        If session_id is omitted, the caller gets the LEGACY path only
        when this node was explicitly started with
        allow_legacy_message_ingestion=True; otherwise the request is
        rejected with LEGACY_MODE_DISABLED, self-declared
        peer_capabilities alone is never sufficient authorization, and
        no Observation is created and no Lantern state is touched.
        """
        if session_id is not None:
            return self.receive_secure(message_data, session_id)

        if not self.allow_legacy_message_ingestion:
            try:
                message = ProtocolMessage.decode(json.dumps(message_data))
                protocol = message.protocol
                message_type = message.message_type
                source = message.source
            except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
                raise ValueError(f"Malformed ProtocolMessage: {exc}") from exc
            if not _validate_wire_shape(message):
                raise ValueError("Invalid ProtocolMessage")
            return {
                "accepted": False,
                "action": "reject",
                "reason": (
                    "LEGACY_MODE_DISABLED: unauthenticated /message ingestion is "
                    "disabled by default; obtain a verified session via "
                    "/identity/* + POST /session/open, or ask the operator to "
                    "enable --allow-legacy-message-ingestion"
                ),
                "data": {},
                "protocol": protocol,
                "message_type": message_type,
                "source": source,
                "watermark": local_watermark(self.lantern).to_dict(),
            }

        return self._receive_legacy(message_data, peer_capabilities)

    def _receive_legacy(self, message_data: dict, peer_capabilities: dict) -> dict:
        """Unmodified legacy behavior, byte-for-byte identical to the
        original receive() implementation, only reachable when an
        operator explicitly set allow_legacy_message_ingestion=True.
        Legacy traffic is never marked as cryptographically verified,
        never receives a session, and never gains trust, authority, or
        Codex permission -- it is exactly the same negotiated-capability
        bridge path that existed before this phase, unchanged.
        """
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
                    "legacy_message_ingestion": self.node.allow_legacy_message_ingestion,
                    "identity_public": self.node.identity_public(),
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
                # Validate field types before constructing HandshakeRequest.
                # Dataclasses do not enforce their type hints at runtime, so
                # HandshakeRequest(**body) with a malformed body (e.g.
                # capabilities as a string instead of a dict) previously
                # constructed successfully and only failed later, inside
                # evaluate_handshake()'s capabilities.items() call, as an
                # uncaught AttributeError -- outside the (TypeError, ValueError,
                # KeyError, ...) tuple this handler already catches below, so
                # it propagated as an unhandled exception instead of a clean
                # 400. Every other endpoint in this handler (/identity/challenge,
                # /session/open, /message, /connection-state) already validates
                # field types explicitly with isinstance() before use; this
                # closes the one endpoint that skipped that convention.
                node_id = body.get("node_id")
                protocol_version = body.get("protocol_version")
                capabilities = body.get("capabilities")
                timestamp = body.get("timestamp")
                if not isinstance(node_id, str) or not node_id:
                    raise ValueError("node_id (string) is required")
                if not isinstance(protocol_version, str) or not protocol_version:
                    raise ValueError("protocol_version (string) is required")
                if not isinstance(capabilities, dict):
                    raise ValueError("capabilities (object) is required")
                if not isinstance(timestamp, str) or not timestamp:
                    raise ValueError("timestamp (string) is required")
                request = HandshakeRequest(
                    node_id=node_id,
                    protocol_version=protocol_version,
                    capabilities=capabilities,
                    timestamp=timestamp,
                )
                response = self.node.evaluate_incoming_handshake(request)
                self._respond(200, asdict(response))
                return

            if self.path == "/identity/challenge":
                # Peer asks THIS node to issue it a challenge to prove
                # requester_node_id's identity to the peer. This node acts
                # as initiator (A) in that exchange.
                requester_node_id = body.get("requester_node_id")
                if not isinstance(requester_node_id, str) or not requester_node_id:
                    raise ValueError("requester_node_id (string) is required")
                self._respond(200, self.node.issue_identity_challenge(requester_node_id))
                return

            if self.path == "/identity/respond":
                # Peer sends THIS node a challenge it issued; this node
                # answers as responder (B), signing with its own identity.
                self._respond(200, self.node.respond_identity_challenge(body))
                return

            if self.path == "/identity/verify":
                # Peer sends THIS node a proof for a challenge this node
                # (as initiator A) previously issued. Verification only --
                # never mutates trust_status or authority_level.
                self._respond(200, self.node.verify_identity_proof(body))
                return

            if self.path == "/session/open":
                # Issue a short-lived verified session for node_id, ONLY
                # if this process already holds a CRYPTOGRAPHICALLY_
                # VERIFIED public key for it (see LanternNode.open_session
                # docstring). This never grants trust or authorizes any
                # capability -- it only binds a session_id to node_id for
                # a bounded TTL, for use as the secure /message identity
                # credential.
                node_id = body.get("node_id")
                if not isinstance(node_id, str) or not node_id:
                    raise ValueError("node_id (string) is required")
                self._respond(200, self.node.open_session(node_id))
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

                # Do not report "accepted" as a synonym for "durably
                # persisted". submit() returning means the in-process
                # write call completed; independently re-read storage
                # (verify_persisted() re-parses the Chronicle file, not
                # the in-memory cache) before claiming persistence.
                persisted = self.node.rendezvous.verify_persisted(request.request_id)
                self._respond(
                    200,
                    {
                        "accepted": True,
                        "request_id": request.request_id,
                        "status": request.status,
                        "is_new": is_new,
                        "persisted": persisted,
                        "note": "Join request received. This is not a trust or capability grant.",
                    },
                )
                return

            if self.path == "/message":
                message = body.get("message")
                peer_capabilities = body.get("peer_capabilities")
                session_id = body.get("session_id")
                if not isinstance(message, dict):
                    raise ValueError("message object is required")
                if session_id is not None and not isinstance(session_id, str):
                    raise ValueError("session_id must be a string when provided")
                # peer_capabilities is only meaningful on the legacy path;
                # a caller presenting session_id uses the secure path
                # unconditionally (see LanternNode.receive()), so it is
                # not required in that case.
                if session_id is None and not isinstance(peer_capabilities, dict):
                    raise ValueError("peer_capabilities object is required when session_id is omitted")
                self._respond(
                    200,
                    self.node.receive(message, peer_capabilities or {}, session_id=session_id),
                )
                return

            if self.path == "/connection-state":
                peer_heartbeat = body.get("peer_heartbeat")
                if peer_heartbeat is not None and not isinstance(peer_heartbeat, dict):
                    raise ValueError("peer_heartbeat must be an object or omitted")
                self._respond(200, self.node.connection_state(peer_heartbeat))
                return

            self._respond(404, {"error": "Not found"})
        except (TypeError, ValueError, KeyError, json.JSONDecodeError, identity_module.IdentityError) as exc:
            self._respond(400, {"error": str(exc)})
        except OSError as exc:
            # A durable write (Chronicle.append) failed. This must never be
            # reported as success -- Chronicle.append() raises rather than
            # swallowing a write failure, so the caller gets a clear,
            # explicit failure instead of a false "accepted" response.
            self._respond(
                500,
                {"error": "Durable write failed", "detail": str(exc), "persisted": False},
            )

    def log_message(self, format, *args):
        print(f"[{self.node.node_id}] {format % args}")


def create_server(
    host: str,
    port: int,
    node_id: str,
    chronicle_path: str | Path,
    *,
    allow_legacy_message_ingestion: bool = False,
    authorization_policy: AuthorizationPolicy | None = None,
    session_ttl_seconds: float = verified_session.DEFAULT_SESSION_TTL_SECONDS,
):
    node = LanternNode(
        node_id=node_id,
        chronicle_path=chronicle_path,
        allow_legacy_message_ingestion=allow_legacy_message_ingestion,
        authorization_policy=authorization_policy,
        session_ttl_seconds=session_ttl_seconds,
    )
    server = ThreadingHTTPServer((host, port), _Handler)
    server.node = node  # type: ignore[attr-defined]
    return server


def _parse_authorize_args(values: list[str] | None) -> AuthorizationPolicy | None:
    """Parse repeated --authorize node_id:capability[,capability...]
    arguments into an AuthorizationPolicy. This is the ONLY way an
    operator can grant a verified node_id evidence_exchange on the
    secure /message path -- there is no default grant, and a session
    alone (see verified_session.py) never implies authorization.
    """
    if not values:
        return None
    policy = EMPTY_POLICY
    for raw in values:
        if ":" not in raw:
            raise ValueError(
                f"--authorize value {raw!r} must be node_id:capability[,capability...]"
            )
        node_id, _, caps = raw.partition(":")
        capabilities = [c.strip() for c in caps.split(",") if c.strip()]
        if not node_id or not capabilities:
            raise ValueError(
                f"--authorize value {raw!r} must be node_id:capability[,capability...]"
            )
        policy = policy.merged_with(node_id, capabilities)
    return policy


def main(argv=None):
    parser = argparse.ArgumentParser(description="Run a minimal Lantern HTTP node")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--node-id", required=True)
    parser.add_argument("--chronicle", default=None)
    parser.add_argument("--data-dir", default=".lantern")
    parser.add_argument(
        "--allow-legacy-message-ingestion",
        action="store_true",
        default=False,
        help=(
            "Operator opt-in ONLY: accept unauthenticated /message "
            "OBSERVATION_SHARE requests with no verified session, exactly "
            "as the pre-migration protocol did. Default is OFF/secure. "
            "This must never be the default and is never inferred."
        ),
    )
    parser.add_argument(
        "--authorize",
        action="append",
        default=None,
        metavar="NODE_ID:CAPABILITY[,CAPABILITY...]",
        help=(
            "Explicitly authorize a cryptographically verified node_id for "
            "one or more capabilities on the secure /message path (e.g. "
            "lantern-a:evidence_exchange). Repeatable. A verified session "
            "alone never grants this -- it must be stated explicitly by "
            "the operator."
        ),
    )
    parser.add_argument(
        "--session-ttl-seconds",
        type=float,
        default=verified_session.DEFAULT_SESSION_TTL_SECONDS,
        help=(
            "TTL, in seconds, for verified sessions issued by /session/open "
            "on this node. Defaults to verified_session.DEFAULT_SESSION_TTL_SECONDS."
        ),
    )
    args = parser.parse_args(argv)

    if not args.chronicle:
        data_dir = Path(args.data_dir)
        data_dir.mkdir(parents=True, exist_ok=True)
        args.chronicle = data_dir / f"{args.node_id}.jsonl"

    authorization_policy = _parse_authorize_args(args.authorize)
    server = create_server(
        args.host,
        args.port,
        args.node_id,
        args.chronicle,
        allow_legacy_message_ingestion=args.allow_legacy_message_ingestion,
        authorization_policy=authorization_policy,
        session_ttl_seconds=args.session_ttl_seconds,
    )
    print(json.dumps({
        "listening": f"http://{args.host}:{args.port}",
        "legacy_message_ingestion": server.node.allow_legacy_message_ingestion,
        **server.node.identity(),
    }))
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
