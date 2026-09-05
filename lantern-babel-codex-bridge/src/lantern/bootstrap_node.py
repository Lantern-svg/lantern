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
import hashlib
import json
import os
import time
import urllib.parse
from datetime import datetime, timezone
from dataclasses import asdict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from .agent import LanternAgent
from .bridge import LanternAgentBridge
from . import capability_authorization
from .capability_authorization import AuthorizationPolicy, EMPTY_POLICY
from .deployment_config import resolve_config
from .compatibility import DEFAULT_CAPABILITIES, negotiate
from .continuity import local_watermark
from .core import Chronicle, Lantern

# Serialization boundary: converts frozen-dataclass fields that are
# immutable (MappingProxyType, tuple) into JSON-serializable native types.
# This is the ONLY place where immutable internal structures are unwrapped
# for external consumption. Internal code always sees the immutable forms.
from types import MappingProxyType as _MappingProxyType

def _serializable_dict(obj):
    """Convert a frozen dataclass to a JSON-safe dict.

    MappingProxyType → dict, tuple → list, everything else passes through.
    """
    result = {}
    for key, value in obj.__dict__.items():
        if isinstance(value, _MappingProxyType):
            result[key] = dict(value)
        elif isinstance(value, tuple):
            result[key] = list(value)
        else:
            result[key] = value
    return result
from .handshake import (
    HandshakeRequest,
    HandshakeResponse,
    create_handshake,
    evaluate_handshake,
)
from .heartbeat import create_heartbeat, evaluate_connection
from . import identity as identity_module
from .witness_ledger import IdentityWitness
from . import observation_exchange
from . import secret_transfer
from .participants import find as find_participant
from .participants import inspect_all, next_verification_step
from .protocol import PROTOCOL_VERSION, ProtocolMessage
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
        witness=None,
        allowed_protocol_versions: tuple[str, ...] = (),
    ):
        self.node_id = node_id
        # Operator-configured allowlist of peer protocol versions this
        # node will handshake with (deployment_config). Empty tuple means
        # the existing compatibility logic decides -- this gate only
        # narrows, never widens.
        self.allowed_protocol_versions = tuple(allowed_protocol_versions or ())
        # Peers that completed an ACCEPTED /handshake in this process
        # lifetime, with the version they declared. Consulted ONLY when
        # an operator protocol-version allowlist is configured: without
        # an accepted handshake, a peer cannot skip straight to
        # /session/open and thereby bypass the version gate. Empty
        # allowlist (the default) keeps the historical behavior.
        self._accepted_handshakes: dict[str, str] = {}
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

        # Secret-transfer replay-dedup table (see lantern.secret_transfer
        # module docstring): in-memory, per-process, non-persistent --
        # mirrors _observation_ledger/self.sessions exactly. Never
        # serialized, never written to the Chronicle, never holds
        # secret plaintext (only transfer_id strings once consumed).
        self._secret_transfer_store = secret_transfer.SecretTransferStore()

        # transfer_id -> nacl.public.PrivateKey (ephemeral, per-transfer).
        # In-memory only, per-process, never persisted or logged. Each
        # entry is single-use: written by offer_secret_transfer(), read
        # and popped exactly once by receive_secret_transfer() (success
        # or failure). A transfer_id absent from this dict at
        # receive_secret_transfer() time means this node never made a
        # matching offer, and the request is rejected outright.
        self._pending_secret_transfers: dict = {}

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
        self.crypto_identity = identity_module.load_or_create(node_id, identity_dir, witness=witness)
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

    def open_session(self, node_id: str, proof_data: dict | None = None) -> dict:
        # Operator protocol-version allowlist: a peer that never
        # completed an ACCEPTED /handshake (with an allowed version)
        # cannot open a session -- this closes the skip-the-handshake
        # bypass of the version gate. No allowlist configured -> the
        # historical behavior is unchanged.
        if self.allowed_protocol_versions and node_id not in self._accepted_handshakes:
            return {
                "created": False,
                "reason": (
                    "SESSION_HANDSHAKE_REQUIRED: no accepted /handshake "
                    "on record for this node_id with an allowed protocol "
                    "version"
                ),
            }
        """Issue a short-lived verified session for node_id, requiring
        per-request proof of private-key possession (Gate 2 Finding 9).

        Two-phase protocol:
        - proof_data is None: issue a challenge and return it. The caller
          must sign it and call again with proof_data.
        - proof_data is provided: verify the proof against the stored
          public key for node_id. Only if valid is a session created.

        Membership in _known_public_keys is necessary but not sufficient.
        The caller must prove they hold the private key *now*, not just
        that the node_id was verified at some point in the past.

        This does NOT grant trust or authorize any capability -- see
        verified_session.py module docstring. A session proves identity
        continuity for this process only; capability_authorization.py
        remains the sole authority for what a session's node_id may
        actually do.
        """
        if not isinstance(node_id, str) or not node_id:
            raise ValueError("node_id (string) is required")

        # Must be a previously-verified node_id. _known_public_keys is
        # populated ONLY on a successful CRYPTOGRAPHICALLY_VERIFIED proof
        # (see verify_identity_proof() above).
        if node_id not in self._known_public_keys:
            result = self.sessions.create_session(
                node_id=node_id, identity_status=identity_module.UNVERIFIED
            )
            return result.to_dict()

        expected_public_key = self._known_public_keys[node_id]

        if proof_data is None:
            # Phase 1: Issue a challenge for the caller to sign.
            challenge = self.challenge_store.issue(
                from_node_id=self.node_id, to_node_id=node_id
            )
            return {
                "outcome": "challenge_issued",
                "nonce": challenge.nonce,
                "from_node_id": challenge.from_node_id,
                "to_node_id": challenge.to_node_id,
                "protocol_version": challenge.protocol_version,
                "ttl_seconds": challenge.ttl_seconds,
            }

        # Phase 2: Verify the proof of private-key possession.
        proof = identity_module.IdentityProof(**proof_data)
        verify_result = self.challenge_store.consume(
            proof, expected_public_key=expected_public_key
        )
        if not verify_result.verified:
            return {
                "created": False,
                "outcome": "proof_rejected",
                "reason": verify_result.reason,
            }

        # Proof verified -- create the session.
        session_result = self.sessions.create_session(
            node_id=node_id,
            identity_status=identity_module.CRYPTOGRAPHICALLY_VERIFIED,
        )
        response = session_result.to_dict()
        if session_result.created:
            response["session_id"] = session_result.session.session_id
            response["expires_at_monotonic"] = session_result.session.expires_at_monotonic
        return response

    def _authorized_capability_decision(
        self, node_id: str, *, requested: list[str] | None = None
    ):
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

        requested: list of capability names to request authorization for.
        Defaults to [EvidenceExchangeCapability] for backward
        compatibility -- existing callers of receive_secure() are
        unchanged.
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
        if requested is None:
            requested = [observation_exchange.EvidenceExchangeCapability]
        return capability_authorization.authorize(
            verified,
            requested=requested,
            policy=self.authorization_policy,
        )

    def query_beliefs(self, session_id: str, source_node_id: str, concepts: list[str] | None = None) -> dict:
        """Read-only belief query: returns the current belief state of
        THIS node's EvidenceKernel without mutating any state.

        Requires a valid, non-expired session bound to source_node_id,
        AND explicit belief_query authorization from
        self.authorization_policy. Reuses the same session resolution
        and capability authorization path as receive_secure() -- never
        reimplemented here.

        Returns only: concept names, belief floats (0-1), evidence
        counts, and contradiction status. Never returns raw observation
        content, raw evidence items, private keys, or owner_instance
        fields. Never calls observe(), add_evidence(), resolve(),
        persist_scar(), or chronicle.append().
        """
        BeliefQueryCapability = "belief_query"

        # Session validation: same pattern as receive_secure()
        lookup = self.sessions.resolve_session(
            session_id=session_id, expected_source=source_node_id
        )
        if not lookup.valid:
            return {
                "accepted": False,
                "reason": f"{lookup.outcome}: {lookup.reason}",
                "data": {},
            }

        # Capability authorization: request belief_query specifically
        decision = self._authorized_capability_decision(
            lookup.node_id, requested=[BeliefQueryCapability]
        )
        if not decision.is_authorized(BeliefQueryCapability):
            return {
                "accepted": False,
                "reason": f"'{BeliefQueryCapability}' is not in authorized_capabilities for '{lookup.node_id}'",
                "denied": dict(decision.denied_capabilities),
                "data": {},
            }

        # Read-only belief state extraction
        kernel = self.lantern.kernel
        evidence_concepts = {e.concept for e in kernel.evidence}

        if concepts is not None:
            query_concepts = set(concepts)
        else:
            query_concepts = evidence_concepts

        concept_results = []
        for concept in sorted(query_concepts):
            belief_value = kernel.belief(concept)
            evidence_count = sum(1 for e in kernel.evidence if e.concept == concept)
            contradiction = kernel.latest_contradiction(concept)
            contradiction_status = None
            if contradiction is not None:
                contradiction_status = {
                    "status": contradiction.status,
                    "severity": round(contradiction.current_severity, 4),
                    "created_step": contradiction.created_step,
                }
            concept_results.append({
                "concept": concept,
                "belief": round(belief_value, 4),
                "evidence_count": evidence_count,
                "contradiction": contradiction_status,
            })

        watermark = local_watermark(self.lantern)

        return {
            "accepted": True,
            "queried_by": source_node_id,
            "responded_by": self.node_id,
            "concepts": concept_results,
            "step": kernel.step,
            "watermark": {
                "chain": watermark.chain,
                "step": watermark.step,
            },
            "total_concepts": len(concept_results),
        }

    def record_handshake(self, node_id: str, protocol_version: str) -> None:
        """Record an accepted /handshake for allowlist enforcement.
        Called only from the HTTP handler after an accepted handshake,
        and only meaningful when allowed_protocol_versions is set."""
        self._accepted_handshakes[node_id] = protocol_version

    def retrieve_observation(
        self, session_id: str, source_node_id: str, observation_id: str
    ) -> dict:
        """Authenticated observation retrieval.

        Requires a valid, non-expired session bound to source_node_id AND
        explicit evidence_exchange authorization -- the exact same session
        resolution and capability-authorization path as receive_secure(),
        never reimplemented here. Returns the persisted observation
        content plus its SHA-256 digest so the retriever can
        independently verify integrity (the Chronicle hash chain
        anchors the record; the digest anchors the content).

        Read-only: never calls observe(), add_evidence(), chronicle
        .append(), or any mutation. Fail-closed on Chronicle integrity
        failure. Returns only observation content/provenance fields --
        never private keys, owner_instance, or unrelated records.
        """
        EvidenceExchangeCapability = "evidence_exchange"

        lookup = self.sessions.resolve_session(
            session_id=session_id, expected_source=source_node_id
        )
        if not lookup.valid:
            return {
                "accepted": False,
                "reason": f"{lookup.outcome}: {lookup.reason}",
                "observation_id": observation_id,
            }

        decision = self._authorized_capability_decision(
            lookup.node_id, requested=[EvidenceExchangeCapability]
        )
        if not decision.is_authorized(EvidenceExchangeCapability):
            return {
                "accepted": False,
                "reason": (
                    f"'{EvidenceExchangeCapability}' is not in "
                    f"authorized_capabilities for '{lookup.node_id}'"
                ),
                "observation_id": observation_id,
            }

        chronicle = self.lantern.bus.chronicle
        if not chronicle.verify():
            return {
                "accepted": False,
                "reason": "CHRONICLE_INTEGRITY_FAILURE: refusing to serve records from an unverifiable chain",
                "observation_id": observation_id,
            }

        for record in chronicle.replay():
            if record.get("type") != "OBSERVATION_CREATED":
                continue
            payload = record.get("payload")
            if not isinstance(payload, dict):
                continue
            if payload.get("id") != observation_id:
                continue
            # Adversarial hardening (cross-peer read): an
            # evidence_exchange-authorized peer may only retrieve
            # observations IT sent to this node. Guessing another
            # peer's observation_id yields no data, even with a valid
            # session and authorization.
            if payload.get("source") != lookup.node_id:
                return {
                    "accepted": False,
                    "reason": (
                        "OBSERVATION_NOT_YOURS: observation_id exists but "
                        "was not sent by the requesting node"
                    ),
                    "observation_id": observation_id,
                }
            content = payload.get("content")
            if not isinstance(content, str):
                return {
                    "accepted": False,
                    "reason": "UNEXPECTED_CONTENT_TYPE: stored observation content is not a string",
                    "observation_id": observation_id,
                }
            stored_digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
            watermark = local_watermark(self.lantern)
            return {
                "accepted": True,
                "retrieved_by": source_node_id,
                "responded_by": self.node_id,
                "observation_id": observation_id,
                "content": content,
                "source": payload.get("source"),
                "step": payload.get("step"),
                "stored_digest": stored_digest,
                "record_hash": record.get("current_hash"),
                "record_timestamp": record.get("timestamp"),
                "chronicle": {
                    "chain": watermark.chain,
                    "step": watermark.step,
                },
            }

        return {
            "accepted": False,
            "reason": "OBSERVATION_NOT_FOUND: no OBSERVATION_CREATED record with that observation_id",
            "observation_id": observation_id,
        }

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

    def offer_secret_transfer(self, session_id: str, source_node_id: str, transfer_id: str) -> dict:
        """Phase 1 of a secret-transfer exchange: THIS node's half of the
        ephemeral X25519 key-agreement handshake.

        Requires a valid, non-expired VerifiedSession bound to
        source_node_id, AND explicit 'secret_transfer' authorization
        from self.authorization_policy -- an authenticated session
        alone is never sufficient, exactly like query_beliefs()/
        receive_secure(). Generates a FRESH ephemeral keypair for this
        transfer_id (never reused across transfer_ids), signs the
        public half with this node's existing long-term identity via
        secret_transfer.create_ephemeral_bundle(), and returns only the
        public bundle -- the ephemeral private key is held in-memory in
        self._pending_secret_transfers, never returned or logged.
        """
        lookup = self.sessions.resolve_session(
            session_id=session_id, expected_source=source_node_id
        )
        if not lookup.valid:
            return {
                "accepted": False,
                "reason": f"{lookup.outcome}: {lookup.reason}",
            }

        decision = self._authorized_capability_decision(
            lookup.node_id, requested=[secret_transfer.SECRET_TRANSFER_CAPABILITY]
        )
        if not decision.is_authorized(secret_transfer.SECRET_TRANSFER_CAPABILITY):
            return {
                "accepted": False,
                "reason": (
                    f"'{secret_transfer.SECRET_TRANSFER_CAPABILITY}' is not in "
                    f"authorized_capabilities for '{lookup.node_id}'"
                ),
                "denied": dict(decision.denied_capabilities),
            }

        if not isinstance(transfer_id, str) or not transfer_id:
            return {"accepted": False, "reason": "transfer_id (string) is required"}

        ephemeral_private, bundle = secret_transfer.create_ephemeral_bundle(
            transfer_id=transfer_id,
            session_id=session_id,
            from_node_id=self.node_id,
            to_node_id=lookup.node_id,
            identity=self.crypto_identity,
        )
        # Held only in-memory for this process, keyed by transfer_id;
        # never persisted, never logged, discarded after first use (see
        # receive_secret_transfer() and its cleanup below).
        self._pending_secret_transfers[transfer_id] = ephemeral_private

        return {"accepted": True, "bundle": bundle.to_dict()}

    def receive_secret_transfer(
        self,
        session_id: str,
        source_node_id: str,
        transfer_id: str,
        peer_bundle: dict,
        sealed: dict,
    ) -> dict:
        """Phase 2: accept the peer's ephemeral bundle + sealed secret,
        verify everything, decrypt, and return ONLY a digest-only
        receipt -- never the plaintext secret itself in the HTTP
        response, never logged.

        Requires: (a) a valid session bound to source_node_id with
        'secret_transfer' authorized (same gate as offer_secret_transfer
        above); (b) a matching in-flight ephemeral private key from a
        prior offer_secret_transfer() call for this exact transfer_id
        (this node must have been the one to initiate phase 1 -- a
        transfer_id this process never offered is rejected outright);
        (c) the peer's bundle's binding signature verifies against
        source_node_id's ALREADY-VERIFIED long-term public key from
        self._known_public_keys (never trusts an unauthenticated
        ephemeral key); (d) the sealed envelope's own session_id/
        transfer_id match what was claimed, checked inside
        secret_transfer.open_secret() itself; (e) transfer_id has not
        already been consumed (anti-replay, independent of ciphertext
        validity).
        """
        lookup = self.sessions.resolve_session(
            session_id=session_id, expected_source=source_node_id
        )
        if not lookup.valid:
            return {
                "accepted": False,
                "reason": f"{lookup.outcome}: {lookup.reason}",
            }

        decision = self._authorized_capability_decision(
            lookup.node_id, requested=[secret_transfer.SECRET_TRANSFER_CAPABILITY]
        )
        if not decision.is_authorized(secret_transfer.SECRET_TRANSFER_CAPABILITY):
            return {
                "accepted": False,
                "reason": (
                    f"'{secret_transfer.SECRET_TRANSFER_CAPABILITY}' is not in "
                    f"authorized_capabilities for '{lookup.node_id}'"
                ),
                "denied": dict(decision.denied_capabilities),
            }

        if not isinstance(transfer_id, str) or not transfer_id:
            return {"accepted": False, "reason": "transfer_id (string) is required"}

        if self._secret_transfer_store.is_consumed(transfer_id):
            return {
                "accepted": False,
                "reason": "SECRET_TRANSFER_REPLAYED: transfer_id has already been consumed once; rejecting replay",
            }

        ephemeral_private = self._pending_secret_transfers.get(transfer_id)
        if ephemeral_private is None:
            return {
                "accepted": False,
                "reason": (
                    "SECRET_TRANSFER_UNKNOWN_TRANSFER: no matching "
                    "offer_secret_transfer() was made for this transfer_id "
                    "by this node"
                ),
            }

        try:
            peer_ephemeral_bundle = secret_transfer.EphemeralKeyBundle(
                transfer_id=peer_bundle.get("transfer_id"),
                session_id=peer_bundle.get("session_id"),
                from_node_id=peer_bundle.get("from_node_id"),
                to_node_id=peer_bundle.get("to_node_id"),
                ephemeral_public_key_hex=peer_bundle.get("ephemeral_public_key"),
                binding_signature_hex=peer_bundle.get("binding_signature"),
            )
        except (TypeError, ValueError) as exc:
            return {"accepted": False, "reason": f"Malformed peer bundle: {exc}"}

        if peer_ephemeral_bundle.transfer_id != transfer_id or peer_ephemeral_bundle.session_id != session_id:
            return {
                "accepted": False,
                "reason": "Peer bundle transfer_id/session_id do not match the claimed context",
            }
        if peer_ephemeral_bundle.from_node_id != lookup.node_id:
            return {
                "accepted": False,
                "reason": "Peer bundle from_node_id does not match the authenticated session's node_id",
            }

        expected_public_key_hex = self._known_public_keys.get(lookup.node_id)
        if expected_public_key_hex is None:
            return {
                "accepted": False,
                "reason": "No previously-verified long-term public key on file for this node_id",
            }

        try:
            secret_transfer.verify_ephemeral_bundle(
                peer_ephemeral_bundle, expected_public_key_hex=expected_public_key_hex
            )
        except secret_transfer.EphemeralKeyBindingError as exc:
            return {"accepted": False, "reason": str(exc)}

        try:
            self._secret_transfer_store.mark_consumed_or_raise(transfer_id)
        except secret_transfer.SecretTransferReplayError as exc:
            return {"accepted": False, "reason": str(exc)}

        try:
            recovered_secret = secret_transfer.open_secret(
                my_ephemeral_private=ephemeral_private,
                their_ephemeral_public_hex=peer_ephemeral_bundle.ephemeral_public_key_hex,
                sealed=sealed,
                expected_session_id=session_id,
                expected_transfer_id=transfer_id,
            )
        except secret_transfer.SecretTransferIntegrityError as exc:
            return {"accepted": False, "reason": str(exc)}
        finally:
            # Ephemeral private key is single-use: discard immediately,
            # success or failure, regardless of outcome.
            self._pending_secret_transfers.pop(transfer_id, None)

        receipt = secret_transfer.SecretTransferReceipt(
            accepted=True,
            transfer_id=transfer_id,
            session_id=session_id,
            secret_length=len(recovered_secret),
            secret_sha256=hashlib.sha256(recovered_secret).hexdigest(),
            reason="Secret received and authenticated-decrypted successfully",
        )
        # recovered_secret intentionally goes out of scope here and is
        # never referenced again -- this method's return value carries
        # only the digest-only receipt, never the plaintext.
        return receipt.to_dict()

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
            data["observation"] = _serializable_dict(observation)

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
        if self.path.startswith("/observations/"):
            self._handle_get_observation(self.path[len("/observations/") :])
            return
        self._respond(404, {"error": "Not found"})

    def _handle_get_observation(self, raw_suffix: str) -> None:
        """GET /observations/<observation_id>?session_id=<session_id>

        STRICTLY SELF-ONLY. Restored on top of the candidate protocol as
        a DISTINCT operation from POST /observation/retrieve
        (node.retrieve_observation), which it does not replace or
        weaken:

          - POST /observation/retrieve answers "did the peer that SENT
            this observation get to re-read what it sent" (provenance
            check: payload.source == caller's own authenticated
            node_id via evidence_exchange capability). It exists only
            for the original sender.
          - GET /observations/<id> (this handler) answers "can the
            node that RECEIVED and stored this observation read its
            own local copy back over HTTP" (identity-equality check:
            caller's authenticated session node_id == this node's own
            node_id, self.node.node_id). It exists only for the local
            holder reading its own state, regardless of who originally
            sent it.

        These are different questions with different trust anchors, so
        they are kept as two distinct endpoints/names rather than
        force-fitting one into the other's authorization semantics.
        This handler deliberately does NOT use the observation's own
        `source` field for its decision (a hostile/malformed
        observation could claim any source) -- the only trust anchor
        is the already-verified session table, exactly as /message and
        POST /observation/retrieve both use it.

        Reuses existing primitives verbatim: verified_session's
        resolve_session() for auth and core.EvidenceKernel
        .get_observation() for the read. No new message type, no
        protocol change, no new capability name (this is an identity
        check, not a capability-authorization check).
        """
        parsed = urllib.parse.urlsplit(raw_suffix)
        observation_id = urllib.parse.unquote(parsed.path)
        query = urllib.parse.parse_qs(parsed.query)
        session_ids = query.get("session_id") or []
        session_id = session_ids[0] if session_ids else None

        if not observation_id:
            self._respond(404, {"error": "Not found"})
            return

        if not isinstance(session_id, str) or not session_id:
            self._respond(
                401,
                {"error": "session_id query parameter is required"},
            )
            return

        lookup = self.node.sessions.resolve_session(session_id=session_id)
        if not lookup.valid:
            self._respond(
                401,
                {"error": f"{lookup.outcome}: {lookup.reason}"},
            )
            return

        # Decisive self-only check: authenticated session's node_id must
        # equal THIS node's own node_id. A perfectly valid session for
        # some OTHER node_id (even one this node fully authorizes for
        # evidence_exchange) is rejected here -- this is not an
        # authorization/capability check, it is an identity-equality
        # check against this process's own node_id.
        if lookup.node_id != self.node.node_id:
            self._respond(
                403,
                {"error": "observation retrieval is restricted to this node's own authenticated session"},
            )
            return

        observation = self.node.agent.lantern.kernel.get_observation(observation_id)
        if observation is None:
            self._respond(404, {"error": "Unknown observation_id"})
            return

        self._respond(
            200,
            {
                "observation_id": observation.id,
                "content": observation.content,
                "source": observation.source,
                "metadata": dict(observation.metadata or {}),
            },
        )

    def do_POST(self):  # noqa: N802 - BaseHTTPRequestHandler API
        try:
            body = self._read_json()
            if self.path == "/handshake":
                # Malformed-input hardening: EVERY untrusted field must be
                # type-validated BEFORE HandshakeRequest construction or
                # evaluate_handshake(). An unvalidated field (e.g. a string
                # capabilities value, or a non-string protocol_version
                # reaching compatibility.parse_version()'s .lstrip) raised
                # AttributeError -- which this handler's except tuple does
                # not catch -- crashing the request thread and dropping the
                # connection with no HTTP response instead of a clean 400.
                for field in ("node_id", "protocol_version", "timestamp"):
                    value = body.get(field)
                    if not isinstance(value, str) or not value:
                        raise ValueError(f"{field} must be a non-empty string")
                if not isinstance(body.get("capabilities"), dict):
                    raise ValueError("capabilities must be an object")
                if (
                    self.node.allowed_protocol_versions
                    and body["protocol_version"]
                    not in self.node.allowed_protocol_versions
                ):
                    # Operator-configured version allowlist (deployment
                    # config): narrower than the built-in compatibility
                    # logic, never wider.
                    self._respond(
                        200,
                        asdict(
                            HandshakeResponse(
                                node_id=self.node.node_id,
                                accepted=False,
                                protocol_version=body["protocol_version"],
                                shared_capabilities={},
                                reason=(
                                    "PROTOCOL_VERSION_NOT_ALLOWED: peer "
                                    f"protocol_version {body['protocol_version']!r} "
                                    "is not in this node's allowed protocol "
                                    f"versions {sorted(self.node.allowed_protocol_versions)}"
                                ),
                                timestamp=datetime.now(timezone.utc).isoformat(),
                            )
                        ),
                    )
                    return
                request = HandshakeRequest(**body)
                response = self.node.evaluate_incoming_handshake(request)
                if response.accepted and self.node.allowed_protocol_versions:
                    self.node.record_handshake(
                        body["node_id"], body["protocol_version"]
                    )
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
                # Two-phase: issue a challenge, then verify proof of
                # private-key possession before creating a session.
                # (Gate 2 Finding 9: per-request proof, not just
                # _known_public_keys membership.)
                node_id = body.get("node_id")
                if not isinstance(node_id, str) or not node_id:
                    raise ValueError("node_id (string) is required")
                proof_data = body.get("proof")
                self._respond(200, self.node.open_session(node_id, proof_data=proof_data))
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

            if self.path == "/belief/query":
                session_id = body.get("session_id")
                source_node_id = body.get("node_id")
                concepts = body.get("concepts")
                if not isinstance(session_id, str) or not session_id:
                    raise ValueError("session_id (string) is required")
                if not isinstance(source_node_id, str) or not source_node_id:
                    raise ValueError("node_id (string) is required")
                if concepts is not None and not isinstance(concepts, list):
                    raise ValueError("concepts must be a list of strings when provided")
                self._respond(
                    200,
                    self.node.query_beliefs(session_id, source_node_id, concepts),
                )
                return

            if self.path == "/observation/retrieve":
                session_id = body.get("session_id")
                source_node_id = body.get("node_id")
                observation_id = body.get("observation_id")
                for name, value in (
                    ("session_id", session_id),
                    ("node_id", source_node_id),
                    ("observation_id", observation_id),
                ):
                    if not isinstance(value, str) or not value:
                        raise ValueError(f"{name} (string) is required")
                self._respond(
                    200,
                    self.node.retrieve_observation(
                        session_id, source_node_id, observation_id
                    ),
                )
                return

            if self.path == "/connection-state":
                peer_heartbeat = body.get("peer_heartbeat")
                if peer_heartbeat is not None and not isinstance(peer_heartbeat, dict):
                    raise ValueError("peer_heartbeat must be an object or omitted")
                self._respond(200, self.node.connection_state(peer_heartbeat))
                return

            if self.path == "/secret/offer":
                session_id = body.get("session_id")
                source_node_id = body.get("node_id")
                transfer_id = body.get("transfer_id")
                for name, value in (
                    ("session_id", session_id),
                    ("node_id", source_node_id),
                    ("transfer_id", transfer_id),
                ):
                    if not isinstance(value, str) or not value:
                        raise ValueError(f"{name} (string) is required")
                self._respond(
                    200,
                    self.node.offer_secret_transfer(session_id, source_node_id, transfer_id),
                )
                return

            if self.path == "/secret/send":
                session_id = body.get("session_id")
                source_node_id = body.get("node_id")
                transfer_id = body.get("transfer_id")
                peer_bundle = body.get("bundle")
                sealed = body.get("sealed")
                for name, value in (
                    ("session_id", session_id),
                    ("node_id", source_node_id),
                    ("transfer_id", transfer_id),
                ):
                    if not isinstance(value, str) or not value:
                        raise ValueError(f"{name} (string) is required")
                if not isinstance(peer_bundle, dict):
                    raise ValueError("bundle (object) is required")
                if not isinstance(sealed, dict):
                    raise ValueError("sealed (object) is required")
                self._respond(
                    200,
                    self.node.receive_secret_transfer(
                        session_id, source_node_id, transfer_id, peer_bundle, sealed
                    ),
                )
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
    witness=None,
    allowed_protocol_versions: tuple[str, ...] = (),
):
    node = LanternNode(
        node_id=node_id,
        chronicle_path=chronicle_path,
        allow_legacy_message_ingestion=allow_legacy_message_ingestion,
        authorization_policy=authorization_policy,
        session_ttl_seconds=session_ttl_seconds,
        witness=witness,
        allowed_protocol_versions=allowed_protocol_versions,
    )
    server = ThreadingHTTPServer((host, port), _Handler)
    server.node = node  # type: ignore[attr-defined]
    return server


def public_key_fingerprint(public_key_hex: str) -> str:
    """SHA-256 fingerprint of the raw Ed25519 public key bytes -- the same
    convention as the forensic identity reports. Public material only."""
    return hashlib.sha256(bytes.fromhex(public_key_hex)).hexdigest()


def build_diagnostics(
    node: LanternNode,
    *,
    listening: str | None = None,
    public_base_url: str | None = None,
    witness: IdentityWitness | None = None,
    config_source: dict[str, str] | None = None,
) -> dict:
    """Startup/self-test diagnostics. Reports only public material:
    node_id, public key + fingerprint, protocol version, capabilities,
    listeners, chronicle/witness health, and external-exchange readiness.
    NEVER private keys or credentials (there is no code path here that
    reads private_key.bin)."""
    chronicle = node.lantern.bus.chronicle
    chronicle_ok = chronicle.verify()
    witness_info: dict[str, Any] = {"enabled": False}
    if witness is not None:
        status, registered_key = witness.lookup(node.node_id)
        witness_info = {
            "enabled": True,
            "identity_status": status,
            "chain_valid": witness.verify_chain(),
        }
    identity_ok = True
    if witness is not None:
        identity_ok = witness_info["identity_status"] == "active"
    external_ready = bool(chronicle_ok and identity_ok)
    diagnostics: dict[str, Any] = {
        "event": "startup",
        "node_id": node.node_id,
        "public_key": node.crypto_identity.public_key_hex,
        "public_key_fingerprint": public_key_fingerprint(
            node.crypto_identity.public_key_hex
        ),
        "protocol_version": PROTOCOL_VERSION,
        "enabled_capabilities": node.identity_capabilities(),
        "listening": listening,
        "public_base_url": public_base_url,
        "legacy_message_ingestion": node.allow_legacy_message_ingestion,
        "chronicle": {
            "path": str(node.chronicle.path),
            "chain_valid": chronicle_ok,
            "chain_head": chronicle.chain,
            "step": node.lantern.kernel.step,
        },
        "witness_ledger": witness_info,
        "external_exchange_ready": external_ready,
    }
    if config_source is not None:
        diagnostics["config_source"] = config_source
    return diagnostics


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
    parser.add_argument("--host", default=None,
                        help="Internal bind address (default 127.0.0.1; env LANTERN_BIND_HOST)")
    parser.add_argument("--port", type=int, default=None,
                        help="Internal bind port (default 8765; env LANTERN_BIND_PORT)")
    parser.add_argument("--node-id", default=None,
                        help="This node's node_id (required; env LANTERN_NODE_ID)")
    parser.add_argument("--chronicle", default=None,
                        help="Chronicle/evidence location (default <data-dir>/<node-id>.jsonl; env LANTERN_CHRONICLE)")
    parser.add_argument("--data-dir", default=None,
                        help="Data directory (default .lantern; env LANTERN_DATA_DIR)")
    parser.add_argument(
        "--public-url",
        default=None,
        help=(
            "Operator-configured public base URL of THIS node "
            "(scheme://host[:port], no path). Used for diagnostics only; "
            "never hard-coded. env LANTERN_PUBLIC_URL"
        ),
    )
    parser.add_argument(
        "--witness-registry",
        default=None,
        help=(
            "Optional path to the LAR-1 Identity Witness Ledger (default: "
            "off -- identical pre-LAR-1 behavior). When set, identity "
            "continuity is reconciled against the ledger at node "
            "construction, BEFORE any socket binds or Chronicle writes. "
            "The ledger holds public material only. env LANTERN_WITNESS_REGISTRY"
        ),
    )
    parser.add_argument(
        "--allowed-protocol-versions",
        default=None,
        metavar="V[,V...]",
        help=(
            "Comma-separated allowlist of peer protocol versions this node "
            "will handshake with (default: existing compatibility logic; "
            "this gate only narrows). env LANTERN_ALLOWED_PROTOCOL_VERSIONS"
        ),
    )
    parser.add_argument(
        "--self-test",
        action="store_true",
        default=False,
        help=(
            "Run startup diagnostics and exit WITHOUT binding a socket: "
            "verify identity load, witness reconciliation, and Chronicle "
            "integrity, print the diagnostics JSON, exit 0 on ready / 1 "
            "otherwise. Never prints private keys."
        ),
    )
    parser.add_argument(
        "--allow-legacy-message-ingestion",
        action="store_true",
        default=None,
        help=(
            "Operator opt-in ONLY: accept unauthenticated /message "
            "OBSERVATION_SHARE requests with no verified session, exactly "
            "as the pre-migration protocol did. Default is OFF/secure. "
            "This must never be the default and is never inferred. "
            "env LANTERN_ALLOW_LEGACY_MESSAGE_INGESTION (true/1/yes/on)"
        ),
    )
    parser.add_argument(
        "--authorize",
        action="append",
        default=None,
        metavar="NODE_ID:CAPABILITY[,CAPABILITY...]",
        help=(
            "Explicitly authorize a cryptographically verified node_id for "
            "one or more capabilities on the secure paths (e.g. "
            "lantern-a:evidence_exchange). Repeatable. A verified session "
            "alone never grants this -- it must be stated explicitly by "
            "the operator. env LANTERN_AUTHORIZE (';'-separated entries)"
        ),
    )
    parser.add_argument(
        "--session-ttl-seconds",
        type=float,
        default=None,
        help=(
            "TTL, in seconds, for verified sessions issued by /session/open "
            "on this node. Defaults to verified_session.DEFAULT_SESSION_TTL_SECONDS. "
            "env LANTERN_SESSION_TTL_SECONDS"
        ),
    )
    args = parser.parse_args(argv)

    # Deployment-safe configuration resolution:
    # explicit CLI argument > LANTERN_* environment variable > default.
    # Nothing is hard-coded; the public URL only ever comes from the
    # operator's own configuration.
    cfg = resolve_config(
        {
            "bind_host": args.host,
            "bind_port": args.port,
            "node_id": args.node_id,
            "data_dir": args.data_dir,
            "chronicle_path": args.chronicle,
            "witness_registry": args.witness_registry,
            "public_base_url": args.public_url,
            "authorize": args.authorize,
            "session_ttl_seconds": args.session_ttl_seconds,
            "allowed_protocol_versions": args.allowed_protocol_versions,
            "allow_legacy_message_ingestion": (
                True if args.allow_legacy_message_ingestion else None
            ),
        },
        os.environ,
    )

    authorization_policy = _parse_authorize_args(list(cfg.authorize))
    witness = IdentityWitness(cfg.witness_registry) if cfg.witness_registry else None

    if args.self_test:
        # Full identity + evidence verification WITHOUT binding a socket.
        # LanternNode construction performs the fail-closed identity load
        # and (when a witness is configured) the LAR-1 reconciliation.
        # ANY failure here is reported as self_test FAIL and exit 1 --
        # never swallowed, never reported as ready.
        try:
            node = LanternNode(
                node_id=cfg.node_id,
                chronicle_path=cfg.chronicle_path,
                authorization_policy=authorization_policy,
                session_ttl_seconds=cfg.session_ttl_seconds,
                witness=witness,
                allowed_protocol_versions=cfg.allowed_protocol_versions,
            )
            diagnostics = build_diagnostics(
                node,
                public_base_url=cfg.public_base_url,
                witness=witness,
                config_source=cfg.source,
            )
        except Exception as exc:  # noqa: BLE001 -- fail-closed reporting
            diagnostics = {
                "event": "startup",
                "node_id": cfg.node_id,
                "self_test": "FAIL",
                "external_exchange_ready": False,
                "reason": f"{type(exc).__name__}: {exc}",
                "public_base_url": cfg.public_base_url,
            }
            print(json.dumps(diagnostics, indent=2, sort_keys=True))
            return 1
        diagnostics["self_test"] = (
            "PASS" if diagnostics["external_exchange_ready"] else "FAIL"
        )
        print(json.dumps(diagnostics, indent=2, sort_keys=True))
        return 0 if diagnostics["self_test"] == "PASS" else 1

    server = create_server(
        cfg.bind_host,
        cfg.bind_port,
        cfg.node_id,
        cfg.chronicle_path,
        allow_legacy_message_ingestion=cfg.allow_legacy_message_ingestion,
        authorization_policy=authorization_policy,
        session_ttl_seconds=cfg.session_ttl_seconds,
        witness=witness,
        allowed_protocol_versions=cfg.allowed_protocol_versions,
    )
    listening = f"http://{cfg.bind_host}:{cfg.bind_port}"
    banner = build_diagnostics(
        server.node,
        listening=listening,
        public_base_url=cfg.public_base_url,
        witness=witness,
        config_source=cfg.source,
    )
    banner["listening"] = listening
    banner["legacy_message_ingestion"] = (
        server.node.allow_legacy_message_ingestion
    )
    print(json.dumps(banner, indent=2, sort_keys=True))
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
