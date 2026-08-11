"""Verified session binding: the smallest possible server-side state that
lets a later ``POST /message`` prove "this request comes from the same
node identity I already cryptographically verified", without that fact
implying trust, authorization, or any Codex/belief/evidence mutation.

Position in the (future) secure /message pipeline:

    /identity/challenge -> /identity/respond -> /identity/verify
        -> identity_status == CRYPTOGRAPHICALLY_VERIFIED
        -> verified_session.create_session()          <-- THIS MODULE
        -> VerifiedSession (opaque session_id, bound to node_id, short TTL)
        -> POST /message {session_id, message}
        -> verified_session.resolve_session()          <-- THIS MODULE
        -> session.node_id used as the caller's identity for
           capability_authorization.authorize() and
           observation_exchange.receive_observation()

This module answers exactly one question:

    "Does this session_id currently correspond to a node identity this
    process recently, cryptographically verified?"

It does NOT answer, and never touches:

    - "Do I trust this node?"                (trust_status; not this module)
    - "What is this node authorized to do?"  (capability_authorization.py)
    - Any evidence/belief/Codex/Scar/snapshot state.

============================================================
Three things a VerifiedSession is explicitly NOT
============================================================

    NOT a trust grant.
        A session only records "identity verification recently
        succeeded for this node_id in this process". It carries no
        capability list, no trust_status, no authority_level.

    NOT a second identity system.
        Sessions are only ever created from an ALREADY-established
        CRYPTOGRAPHICALLY_VERIFIED result (see create_session()'s
        identity_status parameter, checked unconditionally). This
        module performs no cryptographic verification of its own --
        no signature checks, no challenge/response, no key handling.

    NOT persistent state.
        Sessions live only in a SessionStore instance the caller keeps
        in memory (mirrors bootstrap_node.LanternNode._known_public_keys'
        existing in-memory, per-process pattern). Nothing here writes to
        a Chronicle, a file, or any durable store. A process restart
        loses every session -- callers must re-verify identity and
        re-create a session, which is intentional, not a gap.

============================================================
Session identifier properties
============================================================

session_id is generated with secrets.token_urlsafe(32) (matching the
existing secrets.token_hex(32) convention already used for identity
challenge nonces in lantern.identity) -- cryptographically unpredictable,
never derived from node_id or any other public value, so knowledge of a
node_id alone never yields a valid session_id.

============================================================
Expiration
============================================================

Expiration is evaluated against time.monotonic(), the same clock
convention lantern.identity.Challenge/ChallengeStore already use for
their own short-lived state, so session TTL is immune to wall-clock
adjustments. An expired session is never implicitly renewed by a later
/message call -- resolve_session() treats it exactly like "no such
session"; a brand new identity verification is required to obtain a new
session_id (see module docstring "Session lifetime" in the design
report this module implements).
"""

from __future__ import annotations

import secrets
import time
from dataclasses import dataclass, field
from typing import Optional

from . import identity as identity_module

__all__ = [
    "DEFAULT_SESSION_TTL_SECONDS",
    "SessionCreationOutcome",
    "SessionLookupOutcome",
    "VerifiedSession",
    "SessionCreationResult",
    "SessionLookupResult",
    "SessionStore",
]


#: Conservative short default TTL. Explicit, configurable (see
#: SessionStore.ttl_seconds), bounded -- not unlimited, not "forever
#: until explicitly revoked". Chosen well under a typical operator
#: session/monitoring interval so a stale session cannot silently
#: persist across a long-running process's day.
DEFAULT_SESSION_TTL_SECONDS = 300


class SessionCreationOutcome:
    """String constants for SessionCreationResult.outcome."""

    CREATED = "created"
    IDENTITY_NOT_VERIFIED = "identity_not_verified"
    INVALID_NODE_ID = "invalid_node_id"


class SessionLookupOutcome:
    """String constants for SessionLookupResult.outcome."""

    VALID = "valid"
    UNKNOWN_SESSION = "unknown_session"
    EXPIRED = "expired"
    SOURCE_MISMATCH = "source_mismatch"


@dataclass(frozen=True)
class VerifiedSession:
    """Immutable record of one verified session.

    Contains no private key material, no signature/proof bytes, no
    capability list -- only what is needed to answer "who does this
    session_id currently speak for, and until when".
    """

    session_id: str
    node_id: str
    verified_at_monotonic: float
    expires_at_monotonic: float

    def is_expired(self, *, now_monotonic: Optional[float] = None) -> bool:
        now = now_monotonic if now_monotonic is not None else time.monotonic()
        return now >= self.expires_at_monotonic

    def to_dict(self) -> dict:
        """Safe to log/return: no session_id included by default, since
        the identifier itself is the bearer credential. Callers that
        genuinely need to display session_id (e.g. returning it to the
        node that just created it) must read .session_id directly."""
        return {
            "node_id": self.node_id,
            "verified_at_monotonic": self.verified_at_monotonic,
            "expires_at_monotonic": self.expires_at_monotonic,
        }


@dataclass(frozen=True)
class SessionCreationResult:
    outcome: str
    reason: str
    session: Optional[VerifiedSession] = None

    @property
    def created(self) -> bool:
        return self.outcome == SessionCreationOutcome.CREATED

    def to_dict(self) -> dict:
        return {
            "outcome": self.outcome,
            "reason": self.reason,
            "created": self.created,
        }


@dataclass(frozen=True)
class SessionLookupResult:
    outcome: str
    reason: str
    session: Optional[VerifiedSession] = None

    @property
    def valid(self) -> bool:
        return self.outcome == SessionLookupOutcome.VALID

    @property
    def node_id(self) -> Optional[str]:
        return self.session.node_id if self.session is not None else None

    def to_dict(self) -> dict:
        return {
            "outcome": self.outcome,
            "reason": self.reason,
            "valid": self.valid,
        }


@dataclass
class SessionStore:
    """In-memory, per-process, non-persistent session table.

    One SessionStore is meant to live as long as a single LanternNode
    process -- mirrors bootstrap_node.LanternNode._known_public_keys'
    existing in-memory, per-process pattern exactly. Never serialized,
    never written to a Chronicle or any file.
    """

    ttl_seconds: float = DEFAULT_SESSION_TTL_SECONDS
    _sessions: "dict[str, VerifiedSession]" = field(default_factory=dict)

    def create_session(
        self,
        *,
        node_id: str,
        identity_status: str,
        now_monotonic: Optional[float] = None,
    ) -> SessionCreationResult:
        """Create a new VerifiedSession bound to node_id.

        May be called ONLY with an identity_status the caller obtained
        from an already-successful cryptographic identity verification
        (e.g. bootstrap_node.LanternNode.verify_identity_proof()). This
        function performs no verification itself -- it only refuses to
        create a session when identity_status is not the exact
        CRYPTOGRAPHICALLY_VERIFIED value, so a caller cannot accidentally
        (or maliciously) mint a session from a lesser status by passing
        a falsy-but-truthy string.
        """
        if not isinstance(node_id, str) or not node_id:
            return SessionCreationResult(
                outcome=SessionCreationOutcome.INVALID_NODE_ID,
                reason="node_id must be a non-empty string",
            )

        if identity_status != identity_module.CRYPTOGRAPHICALLY_VERIFIED:
            return SessionCreationResult(
                outcome=SessionCreationOutcome.IDENTITY_NOT_VERIFIED,
                reason=(
                    f"identity_status={identity_status!r} is not "
                    f"{identity_module.CRYPTOGRAPHICALLY_VERIFIED!r}; "
                    "a session may only be created after successful "
                    "cryptographic identity verification"
                ),
            )

        now = now_monotonic if now_monotonic is not None else time.monotonic()
        session_id = secrets.token_urlsafe(32)
        session = VerifiedSession(
            session_id=session_id,
            node_id=node_id,
            verified_at_monotonic=now,
            expires_at_monotonic=now + self.ttl_seconds,
        )
        self._sessions[session_id] = session
        return SessionCreationResult(
            outcome=SessionCreationOutcome.CREATED,
            reason="session created",
            session=session,
        )

    def resolve_session(
        self,
        *,
        session_id: str,
        expected_source: Optional[str] = None,
        now_monotonic: Optional[float] = None,
    ) -> SessionLookupResult:
        """Look up session_id and validate it.

        expected_source, if provided, must equal the session's bound
        node_id -- this is the source/node binding check (a caller who
        holds a valid session for node A must not be able to submit a
        message claiming to be from node B). A mismatch is reported as
        SOURCE_MISMATCH distinctly from UNKNOWN_SESSION/EXPIRED so a
        caller can log/react to impersonation attempts distinctly, but
        no internal state (session table contents, other node_ids) is
        ever revealed in the reason text.

        An expired session is treated identically to an absent one for
        the purpose of denying access, and is never implicitly renewed
        by this call -- it is not removed from the table here either
        (removal, if ever added, would be a separate explicit sweep, not
        implied by a failed lookup) but expires_at_monotonic alone
        governs validity, not presence in the dict.
        """
        if not isinstance(session_id, str) or not session_id:
            return SessionLookupResult(
                outcome=SessionLookupOutcome.UNKNOWN_SESSION,
                reason="no such session",
            )

        session = self._sessions.get(session_id)
        if session is None:
            return SessionLookupResult(
                outcome=SessionLookupOutcome.UNKNOWN_SESSION,
                reason="no such session",
            )

        now = now_monotonic if now_monotonic is not None else time.monotonic()
        if session.is_expired(now_monotonic=now):
            return SessionLookupResult(
                outcome=SessionLookupOutcome.EXPIRED,
                reason="session has expired; a new identity verification is required",
            )

        if expected_source is not None and expected_source != session.node_id:
            return SessionLookupResult(
                outcome=SessionLookupOutcome.SOURCE_MISMATCH,
                reason="message.source does not match the verified session's node_id",
            )

        return SessionLookupResult(
            outcome=SessionLookupOutcome.VALID,
            reason="session valid",
            session=session,
        )

    def __len__(self) -> int:
        return len(self._sessions)
