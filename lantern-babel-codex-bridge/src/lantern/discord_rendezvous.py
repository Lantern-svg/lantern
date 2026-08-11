"""Discord -> Lantern rendezvous announcement adapter (Phase 3B).

Discord is an UNTRUSTED SIGNALING MEDIUM, never a trust anchor, never the
Lantern transport, never an authority mechanism. This module answers exactly
one question, structurally:

    "Given a raw Discord message payload that CLAIMS to announce a Lantern
    node seeking contact, what does a normalized, validated rendezvous
    announcement look like -- one that is safe to hand to the EXISTING
    rendezvous.JoinMonitor as an untrusted JoinRequest?"

It does not answer, and structurally cannot answer, any question involving
contact, verification, or trust. Those remain rendezvous.py / identity.py /
handshake.py's job, unchanged, exactly as Phase 2A left them.

Explicit non-goals (see PHASE 3B instruction -- this file must never do any
of the following):
    - network contact (no sockets, no urlopen, no requests)
    - DNS resolution
    - Discord API calls (posting, polling, fetching)
    - identity verification (no import of lantern.identity)
    - trust or authority decisions (no import of lantern.participants)
    - belief/Codex/Scar mutation (no import of lantern.core)
    - a second rendezvous database or participant registry

The normalization logic above (normalize_discord_announcement,
NormalizedAnnouncement, to_join_request_payload) has exactly zero
dependencies inside the package -- it is fully unit-testable with zero
Lantern state, zero Discord reachability, and zero network access,
mirroring the Layer A/B/C separation established by discord_bridge.py
(Phase 1).

============================================================
Phase 3C: JoinMonitor integration
============================================================

submit_discord_announcement() below is the ONLY addition in this phase. It
imports rendezvous.JoinMonitor (the sole owner of rendezvous persistence,
deduplication, TTL, and audit recording -- unmodified by this phase) purely
to call its existing submit() method with the dict
to_join_request_payload() already produces. It adds no new persistence, no
new dedup logic, no new TTL logic -- JoinMonitor's existing behavior for
all of those is reused verbatim.

This import is the only reason this module now depends on anything else in
the package. The core Lantern node (bootstrap_node.py, rendezvous.py,
identity.py, etc.) remains fully usable without this module ever being
imported -- nothing in rendezvous.py or bootstrap_node.py imports
discord_rendezvous.py. Conversely, normalize_discord_announcement() and
NormalizedAnnouncement remain usable, and are still fully tested, with zero
JoinMonitor/Chronicle/filesystem involvement -- only
submit_discord_announcement() touches JoinMonitor at all.

============================================================
Message content vs. structured fields
============================================================

A Discord message has two kinds of content once it reaches this module:

    1. Structured rendezvous fields (a JSON object, typically posted as a
       code block or an embed field, per the schema below). These are
       DATA: parsed, validated, normalized.
    2. Free-form message text/content (anything else in the payload, e.g.
       a `content` string wrapping the JSON, or additional message text).
       This is NEVER executed, evaluated, imported, or interpolated into
       any code path. It is either ignored, or -- for audit purposes only
       -- captured verbatim as an inert string inside `discord_metadata`.
       No f-string, eval, exec, or dynamic import ever touches it.

The rendezvous fields themselves remain untrusted CLAIMS regardless of how
well-formed they are. Passing validation here means only "this is a
syntactically coherent announcement", never "this identity is real". That
distinction is why every accepted output value below still carries the word
"claimed" (or is documented as such) and why identity_status is not, and
cannot be, produced by this module at all.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional


RENDEZVOUS_SOURCE = "discord"
SUPPORTED_RENDEZVOUS_VERSIONS = ("1",)

# Endpoint scheme allowlist used only for SYNTACTIC validation here. This
# module never contacts the endpoint; a later, separate network-contact-
# policy layer (not part of this file) is responsible for deciding whether
# an endpoint that passes this syntax check may actually be reached.
_ALLOWED_ENDPOINT_SCHEMES = ("http", "https")

_REQUIRED_ANNOUNCEMENT_FIELDS = (
    "rendezvous_version",
    "announcement_id",
    "node_id",
    "protocol_version",
    "public_key",
    "issued_at",
)


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class NormalizedAnnouncement:
    """Result of normalizing one raw Discord rendezvous announcement.

    Every field here is a CLAIM, not a verified fact -- see module
    docstring. ``valid`` is False when the announcement is too malformed,
    expired, or internally inconsistent to safely hand to JoinMonitor at
    all; ``rejection_reason`` explains why.

    ``to_join_request_payload()`` produces exactly the dict shape
    rendezvous.JoinMonitor.submit() already expects (request_id, node_id,
    protocol_version, capabilities, timestamp, peer_endpoint) -- this
    module does not construct a rendezvous.JoinRequest object directly and
    does not call JoinMonitor itself; wiring a valid NormalizedAnnouncement
    into an actual JoinMonitor is a separate, later integration step,
    explicitly out of scope for this file.
    """

    valid: bool
    announcement_id: str
    node_id: str
    protocol_version: str
    rendezvous_version: str
    claimed_public_key: str
    claimed_capabilities: dict[str, bool]
    claimed_endpoint: Optional[str]
    issued_at: str
    expires_at: Optional[str]
    discord_metadata: dict[str, Any]
    rejection_reason: Optional[str] = None
    raw_fields: dict[str, Any] = field(default_factory=dict)

    def to_join_request_payload(self) -> dict[str, Any]:
        """Shape this announcement as a rendezvous.JoinMonitor.submit() payload.

        Pure data transformation -- does not call JoinMonitor, does not
        import rendezvous.py, does not touch any Chronicle. Raises
        ValueError if called on an invalid announcement, since an invalid
        announcement must never be submitted anywhere.
        """
        if not self.valid:
            raise ValueError(
                f"Cannot build a JoinRequest payload from an invalid announcement: {self.rejection_reason}"
            )
        return {
            "request_id": self.announcement_id,
            "node_id": self.node_id,
            "protocol_version": self.protocol_version,
            "capabilities": dict(self.claimed_capabilities),
            "timestamp": self.issued_at,
            "peer_endpoint": self.claimed_endpoint,
        }


# ---------------------------------------------------------------------------
# Internal helpers (pure, no I/O)
# ---------------------------------------------------------------------------

def _reject(
    reason: str,
    *,
    announcement_id: str = "",
    node_id: str = "",
    protocol_version: str = "",
    rendezvous_version: str = "",
    public_key: str = "",
    capabilities: Optional[dict[str, bool]] = None,
    endpoint: Optional[str] = None,
    issued_at: str = "",
    discord_metadata: Optional[dict[str, Any]] = None,
    raw_fields: Optional[dict[str, Any]] = None,
) -> NormalizedAnnouncement:
    return NormalizedAnnouncement(
        valid=False,
        announcement_id=announcement_id,
        node_id=node_id,
        protocol_version=protocol_version,
        rendezvous_version=rendezvous_version,
        claimed_public_key=public_key,
        claimed_capabilities=dict(capabilities or {}),
        claimed_endpoint=endpoint,
        issued_at=issued_at,
        expires_at=None,
        discord_metadata=dict(discord_metadata or {}),
        rejection_reason=reason,
        raw_fields=dict(raw_fields or {}),
    )


def _parse_iso8601(value: Any) -> Optional[datetime]:
    """Parse a strict ISO-8601 timestamp. Returns None on any failure.

    Never raises -- a malformed timestamp is a validation outcome, not an
    exception a caller must catch.
    """
    if not isinstance(value, str) or not value:
        return None
    try:
        # datetime.fromisoformat handles "Z" only from Python 3.11+; this
        # module targets the same interpreter as the rest of the package
        # (see rendezvous.py's own _parse_timestamp for the analogous
        # pattern), but we defensively normalize a trailing "Z" ourselves
        # so behavior does not depend on interpreter minor version.
        normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
        parsed = datetime.fromisoformat(normalized)
    except (ValueError, TypeError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _looks_like_hex(value: str) -> bool:
    if not value:
        return False
    try:
        int(value, 16)
    except ValueError:
        return False
    return True


def _validate_endpoint_syntax(endpoint: Any) -> tuple[bool, Optional[str]]:
    """Syntactic-only endpoint validation. Never resolves DNS, never opens
    a socket, never imports urllib/http/socket. Returns (is_valid, reason)."""
    if endpoint is None:
        return True, None
    if not isinstance(endpoint, str) or not endpoint:
        return False, "peer_endpoint must be a non-empty string when present"

    # Minimal, dependency-free scheme + host check. Deliberately not using
    # urllib.parse.urlparse here to keep this module free of any module
    # that a future network layer might otherwise be tempted to reuse for
    # an actual outbound call from inside this file.
    scheme_split = endpoint.split("://", 1)
    if len(scheme_split) != 2:
        return False, "peer_endpoint must include an explicit scheme (e.g. http:// or https://)"
    scheme, rest = scheme_split
    if scheme.lower() not in _ALLOWED_ENDPOINT_SCHEMES:
        return False, f"peer_endpoint scheme {scheme!r} is not in the allowed set {_ALLOWED_ENDPOINT_SCHEMES}"
    if not rest or rest.startswith("/") or rest.startswith(":"):
        return False, "peer_endpoint is missing a host"
    host_part = rest.split("/", 1)[0]
    if not host_part or host_part in (":", "@"):
        return False, "peer_endpoint host is empty"
    return True, None


def _extract_discord_metadata(raw_payload: dict) -> dict[str, Any]:
    """Capture Discord-source context for audit purposes, verbatim and inert.

    Every value here is stored as a plain string/primitive and is NEVER
    evaluated, executed, imported, or used to build another code path. It
    exists purely so an operator (via joins_cli.py or /participants) can
    later see which Discord message/channel/author an announcement claims
    to have come from -- itself just another untrusted claim.
    """
    message_id = raw_payload.get("id")
    channel_id = raw_payload.get("channel_id")
    guild_id = raw_payload.get("guild_id")
    author_obj = raw_payload.get("author")
    author_id = None
    if isinstance(author_obj, dict):
        author_id = author_obj.get("id")

    return {
        "platform": RENDEZVOUS_SOURCE,
        "discord_message_id": str(message_id) if message_id is not None else None,
        "discord_channel_id": str(channel_id) if channel_id is not None else None,
        "discord_guild_id": str(guild_id) if guild_id is not None else None,
        "discord_author_id": str(author_id) if author_id is not None else None,
        # Free-form text preserved verbatim, inert -- never parsed as
        # anything other than a plain string. Truncated defensively so a
        # very large message body cannot be used to bloat this metadata
        # blob; the value itself is still never interpreted.
        "discord_content_excerpt": (
            str(raw_payload.get("content"))[:500] if raw_payload.get("content") is not None else None
        ),
    }


def _extract_rendezvous_fields(raw_payload: dict) -> Optional[dict[str, Any]]:
    """Locate the structured rendezvous JSON object inside a Discord payload.

    Supports two shapes, in priority order:
      1. raw_payload["rendezvous"] is already a dict -- e.g. an
         out-of-band/test harness that has already extracted the embed
         field, or a future structured-embed convention.
      2. raw_payload["content"] contains a fenced JSON code block
         (```json ... ``` or ``` ... ```) -- the natural way an operator
         posts a rendezvous announcement as a normal Discord message today.

    Returns None (not an exception) if no structured announcement can be
    located -- this is a normal, expected outcome for the vast majority of
    Discord messages, which are not rendezvous announcements at all.

    This function only ever calls json.loads on a substring it extracted
    itself via plain string search -- it never uses eval/exec, and a
    json.JSONDecodeError here is caught and treated as "no announcement
    found", never propagated as a crash.
    """
    import json
    import re

    embedded = raw_payload.get("rendezvous")
    if isinstance(embedded, dict):
        return embedded

    content = raw_payload.get("content")
    if not isinstance(content, str) or not content:
        return None

    match = re.search(r"```(?:json)?\s*\n?(.*?)```", content, re.DOTALL)
    candidate = match.group(1).strip() if match else content.strip()
    if not candidate:
        return None

    try:
        parsed = json.loads(candidate)
    except (json.JSONDecodeError, ValueError, TypeError):
        return None

    if not isinstance(parsed, dict):
        return None
    return parsed


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def normalize_discord_announcement(raw_payload: Any) -> NormalizedAnnouncement:
    """Normalize + validate one raw Discord message payload.

    Pure function: no network calls, no Discord API calls, no Lantern
    state, no identity verification, no side effects of any kind. Safe to
    call on arbitrary, possibly hostile, input -- a malformed or malicious
    payload only ever produces a NormalizedAnnouncement with
    valid=False, never an exception, never a partial mutation anywhere.

    Every returned field remains an UNTRUSTED CLAIM. Nothing in this
    function's return value should ever be treated as verified identity --
    that happens later, exclusively via lantern.identity's cryptographic
    challenge/response, which this module deliberately does not call.
    """
    if not isinstance(raw_payload, dict):
        return _reject("payload is not a dict")

    discord_metadata = _extract_discord_metadata(raw_payload)

    fields = _extract_rendezvous_fields(raw_payload)
    if fields is None:
        return _reject(
            "no structured rendezvous announcement found in payload "
            "(expected a 'rendezvous' object or a JSON code block in 'content')",
            discord_metadata=discord_metadata,
        )

    missing = [name for name in _REQUIRED_ANNOUNCEMENT_FIELDS if not fields.get(name)]
    if missing:
        return _reject(
            "missing required announcement fields: " + ", ".join(missing),
            discord_metadata=discord_metadata,
            raw_fields=fields,
        )

    rendezvous_version = fields.get("rendezvous_version")
    if not isinstance(rendezvous_version, str) or rendezvous_version not in SUPPORTED_RENDEZVOUS_VERSIONS:
        return _reject(
            f"unsupported or missing rendezvous_version (expected one of {SUPPORTED_RENDEZVOUS_VERSIONS})",
            discord_metadata=discord_metadata,
            raw_fields=fields,
        )

    announcement_id = fields.get("announcement_id")
    if not isinstance(announcement_id, str) or not announcement_id:
        return _reject(
            "announcement_id must be a non-empty string",
            rendezvous_version=rendezvous_version,
            discord_metadata=discord_metadata,
            raw_fields=fields,
        )

    node_id = fields.get("node_id")
    if not isinstance(node_id, str) or not node_id:
        return _reject(
            "node_id must be a non-empty string",
            announcement_id=announcement_id,
            rendezvous_version=rendezvous_version,
            discord_metadata=discord_metadata,
            raw_fields=fields,
        )

    protocol_version = fields.get("protocol_version")
    if not isinstance(protocol_version, str) or not protocol_version:
        return _reject(
            "protocol_version must be a non-empty string",
            announcement_id=announcement_id,
            node_id=node_id,
            rendezvous_version=rendezvous_version,
            discord_metadata=discord_metadata,
            raw_fields=fields,
        )

    public_key = fields.get("public_key")
    if not isinstance(public_key, str) or not _looks_like_hex(public_key) or len(public_key) not in (64,):
        # Ed25519 verify keys are 32 raw bytes -> 64 hex chars, matching
        # identity.NodeIdentity.public_key_hex's own encoding. This module
        # does not import identity.py (out of scope for this file) but the
        # length/format check keeps a structurally-impossible key from
        # ever reaching a later verification step disguised as plausible.
        return _reject(
            "public_key must be a 64-character hex string (32-byte Ed25519 key)",
            announcement_id=announcement_id,
            node_id=node_id,
            protocol_version=protocol_version,
            rendezvous_version=rendezvous_version,
            discord_metadata=discord_metadata,
            raw_fields=fields,
        )

    issued_at_raw = fields.get("issued_at")
    issued_at_parsed = _parse_iso8601(issued_at_raw)
    if issued_at_parsed is None:
        return _reject(
            "issued_at must be a valid ISO-8601 timestamp",
            announcement_id=announcement_id,
            node_id=node_id,
            protocol_version=protocol_version,
            rendezvous_version=rendezvous_version,
            public_key=public_key,
            discord_metadata=discord_metadata,
            raw_fields=fields,
        )

    expires_at_raw = fields.get("expires_at")
    expires_at_parsed = None
    if expires_at_raw is not None:
        expires_at_parsed = _parse_iso8601(expires_at_raw)
        if expires_at_parsed is None:
            return _reject(
                "expires_at is present but not a valid ISO-8601 timestamp",
                announcement_id=announcement_id,
                node_id=node_id,
                protocol_version=protocol_version,
                rendezvous_version=rendezvous_version,
                public_key=public_key,
                issued_at=issued_at_raw,
                discord_metadata=discord_metadata,
                raw_fields=fields,
            )
        if expires_at_parsed <= issued_at_parsed:
            return _reject(
                "expires_at must be after issued_at",
                announcement_id=announcement_id,
                node_id=node_id,
                protocol_version=protocol_version,
                rendezvous_version=rendezvous_version,
                public_key=public_key,
                issued_at=issued_at_raw,
                discord_metadata=discord_metadata,
                raw_fields=fields,
            )
        if expires_at_parsed <= datetime.now(timezone.utc):
            return _reject(
                "announcement has already expired (expires_at is in the past)",
                announcement_id=announcement_id,
                node_id=node_id,
                protocol_version=protocol_version,
                rendezvous_version=rendezvous_version,
                public_key=public_key,
                issued_at=issued_at_raw,
                discord_metadata=discord_metadata,
                raw_fields=fields,
            )

    capabilities = fields.get("capabilities", {})
    if not isinstance(capabilities, dict) or any(
        not isinstance(value, bool) for value in capabilities.values()
    ):
        return _reject(
            "capabilities, if present, must be an object of boolean values",
            announcement_id=announcement_id,
            node_id=node_id,
            protocol_version=protocol_version,
            rendezvous_version=rendezvous_version,
            public_key=public_key,
            issued_at=issued_at_raw,
            discord_metadata=discord_metadata,
            raw_fields=fields,
        )

    # Deliberately NOT `fields.get("endpoint") or fields.get("peer_endpoint")` --
    # an explicitly-present empty string ("endpoint": "") must be treated as a
    # malformed claim, not silently coalesced into "no endpoint supplied".
    endpoint = fields.get("endpoint")
    if endpoint is None:
        endpoint = fields.get("peer_endpoint")
    endpoint_ok, endpoint_reason = _validate_endpoint_syntax(endpoint)
    if not endpoint_ok:
        return _reject(
            f"invalid peer_endpoint: {endpoint_reason}",
            announcement_id=announcement_id,
            node_id=node_id,
            protocol_version=protocol_version,
            rendezvous_version=rendezvous_version,
            public_key=public_key,
            capabilities=capabilities,
            issued_at=issued_at_raw,
            discord_metadata=discord_metadata,
            raw_fields=fields,
        )

    return NormalizedAnnouncement(
        valid=True,
        announcement_id=announcement_id,
        node_id=node_id,
        protocol_version=protocol_version,
        rendezvous_version=rendezvous_version,
        claimed_public_key=public_key,
        claimed_capabilities=dict(capabilities),
        claimed_endpoint=endpoint if isinstance(endpoint, str) else None,
        issued_at=issued_at_raw,
        expires_at=expires_at_raw if isinstance(expires_at_raw, str) else None,
        discord_metadata=discord_metadata,
        rejection_reason=None,
        raw_fields=dict(fields),
    )


# ---------------------------------------------------------------------------
# Phase 3C: JoinMonitor integration (the only place this module touches
# anything outside itself)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class DiscordRendezvousResult:
    """Outcome of submit_discord_announcement().

    ``normalized`` is always present -- even a rejected announcement
    produces a NormalizedAnnouncement(valid=False, ...) so the caller can
    inspect why. ``submitted`` is True only when the payload was valid AND
    was handed to JoinMonitor.submit(); it is False for every rejection,
    in which case ``join_request``/``is_new``/``notification`` are all
    None and JoinMonitor.submit() was never called at all.

    ``join_request``/``is_new``/``notification`` are exactly the three
    values rendezvous.JoinMonitor.submit() already returns, passed through
    unchanged -- this module does not reinterpret, filter, or add meaning
    to them. Duplicate-detection, TTL, and persistence are entirely
    JoinMonitor's existing behavior.
    """

    submitted: bool
    normalized: "NormalizedAnnouncement"
    join_request: Optional[Any] = None
    is_new: Optional[bool] = None
    notification: Optional[str] = None


def submit_discord_announcement(raw_payload: Any, monitor: Any) -> DiscordRendezvousResult:
    """Normalize a raw Discord payload and, only if valid, submit it to an
    existing rendezvous.JoinMonitor instance.

    This is the ONLY function in this module that touches anything outside
    normalize_discord_announcement()/to_join_request_payload() -- it never
    contacts the advertised endpoint, never performs identity verification,
    never creates a ParticipantView, never grants trust or authority, never
    modifies beliefs/Codex, never creates a Scar, never calls Discord, and
    never creates a second persistence layer. It calls exactly one existing
    method: monitor.submit(payload).

    ``monitor`` is duck-typed (any object exposing ``.submit(payload_dict)
    -> (request, is_new, notification)``, matching
    rendezvous.JoinMonitor.submit()'s existing signature) rather than
    type-hinted to rendezvous.JoinMonitor specifically, so this module does
    not need a hard top-level import of rendezvous.py -- callers who never
    use this function (e.g. someone only calling
    normalize_discord_announcement() directly) do not need JoinMonitor, a
    Chronicle, or a filesystem path to import or use the rest of this
    module.

    Data flow, exactly as specified:
        raw Discord payload
          -> normalize_discord_announcement()   (untrusted normalization)
          -> [invalid: return here, JoinMonitor never touched]
          -> to_join_request_payload()
          -> monitor.submit(payload)             (existing JoinMonitor)
          -> untrusted rendezvous record (JoinRequest, status=AWAITING_HANDSHAKE)

    Nothing happens after JoinMonitor in this function. No identity proof,
    no trust decision, no ParticipantView is produced here.
    """
    normalized = normalize_discord_announcement(raw_payload)

    if not normalized.valid:
        return DiscordRendezvousResult(submitted=False, normalized=normalized)

    payload = normalized.to_join_request_payload()
    join_request, is_new, notification = monitor.submit(payload)

    return DiscordRendezvousResult(
        submitted=True,
        normalized=normalized,
        join_request=join_request,
        is_new=is_new,
        notification=notification,
    )
