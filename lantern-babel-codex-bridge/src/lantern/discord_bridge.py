"""Discord -> Lantern observation bridge (Phase 1).

Narrow, reversible, read-only bridge that turns one explicitly designated
Discord message into a Lantern Observation.

Design constraint (see ARCHITECTURE.md interoperability loop):

    Discord
      -> External Payload      (raw, untouched)
      -> Normalization         (this module, layer B)
      -> Lantern Observation   (this module, layer C, calls core.Lantern.observe)
      -> Evidence / Contradiction analysis   (caller's responsibility, NOT this module)
      -> Human-visible result

This module deliberately stops at Observation. It never calls
``add_evidence``, never calls ``resolve``, never creates a Scar, and never
sends anything back to Discord. Promoting an Observation to Evidence/Belief,
or reacting to it in any way, is a separate, explicit decision made by the
caller -- never automatic here.

Three layers are kept structurally separate so the Lantern-side logic can be
fully tested without Discord ever being reachable:

    A. Transport        -- fetch_discord_message()   (talks to the proxy)
    B. Normalization     -- normalize_discord_message() (pure function, no I/O)
    C. Observation entry -- discord_message_to_observation() (calls Lantern.observe)

Nothing in this module polls, listens, or schedules itself. Every call is a
single, explicit, caller-initiated fetch of one designated message.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Optional


DISCORD_SOURCE_PREFIX = "discord"


# ---------------------------------------------------------------------------
# Layer B result type
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class NormalizedDiscordMessage:
    """Result of normalizing a raw Discord payload.

    ``valid`` is False when the payload is too malformed to safely turn into
    an Observation at all (e.g. not a dict, or missing content entirely with
    no way to represent "empty"). Missing-but-recoverable fields (author,
    timestamp) are represented explicitly rather than causing rejection.
    """

    valid: bool
    content: str
    author: str
    author_known: bool
    timestamp: str
    timestamp_known: bool
    channel_id: str
    message_id: str
    guild_id: Optional[str]
    raw_payload: dict
    rejection_reason: Optional[str] = None
    metadata: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Layer A: Transport (talks to the existing host-capabilities proxy)
# ---------------------------------------------------------------------------

class DiscordTransportError(Exception):
    """Raised when the transport layer cannot obtain a message.

    Callers must treat this as a transport failure only -- it must never be
    allowed to reach into or mutate Lantern state. See
    ``discord_message_to_observation`` for how this is kept isolated.
    """


def fetch_discord_message(
    channel_id: str,
    message_id: str,
    proxy_call: Callable[[str, str, str, Optional[dict]], dict],
) -> dict:
    """Fetch exactly one explicitly designated Discord message.

    ``proxy_call`` is injected (integrationKey, method, endpoint, data) ->
    response dict, matching the host-capabilities proxy contract described in
    the host-capabilities skill. This function does not know or care *how*
    the proxy call is made (curl, http client, mock) -- that keeps transport
    fully swappable and fully mockable for tests.

    No polling. No retry loop. No caching. One explicit fetch, one message.
    """
    if not channel_id or not message_id:
        raise DiscordTransportError("channel_id and message_id are required for a designated fetch")

    endpoint = f"/channels/{channel_id}/messages/{message_id}"
    try:
        response = proxy_call("discord", "GET", endpoint, None)
    except Exception as exc:  # noqa: BLE001 - transport errors are intentionally broad here
        raise DiscordTransportError(f"discord proxy call failed: {exc}") from exc

    if not isinstance(response, dict):
        raise DiscordTransportError("discord proxy returned a non-dict response")

    return response


# ---------------------------------------------------------------------------
# Layer B: Normalization (pure function, no I/O, no Lantern dependency)
# ---------------------------------------------------------------------------

def normalize_discord_message(raw_payload: Any) -> NormalizedDiscordMessage:
    """Normalize a raw Discord message payload.

    Pure function: no network calls, no Lantern calls, no side effects.
    This is what makes layer C testable without Discord ever being reachable
    -- tests can hand this function a plain dict and check the result.
    """
    if not isinstance(raw_payload, dict):
        return NormalizedDiscordMessage(
            valid=False,
            content="",
            author="unknown",
            author_known=False,
            timestamp="",
            timestamp_known=False,
            channel_id="",
            message_id="",
            guild_id=None,
            raw_payload={"_unparseable": repr(raw_payload)},
            rejection_reason="payload is not a dict",
        )

    message_id = raw_payload.get("id")
    channel_id = raw_payload.get("channel_id")

    if not message_id or not channel_id:
        return NormalizedDiscordMessage(
            valid=False,
            content="",
            author="unknown",
            author_known=False,
            timestamp="",
            timestamp_known=False,
            channel_id=str(channel_id or ""),
            message_id=str(message_id or ""),
            guild_id=raw_payload.get("guild_id"),
            raw_payload=raw_payload,
            rejection_reason="missing required id or channel_id",
        )

    content = raw_payload.get("content")
    if content is None:
        content = ""
    content_explicitly_empty = content == ""

    author_obj = raw_payload.get("author")
    if isinstance(author_obj, dict) and author_obj.get("id"):
        author = str(author_obj.get("id"))
        author_known = True
    else:
        author = "unknown"
        author_known = False

    timestamp = raw_payload.get("timestamp")
    if timestamp:
        timestamp_known = True
    else:
        timestamp = datetime.now(timezone.utc).isoformat()
        timestamp_known = False

    return NormalizedDiscordMessage(
        valid=True,
        content=content,
        author=author,
        author_known=author_known,
        timestamp=str(timestamp),
        timestamp_known=timestamp_known,
        channel_id=str(channel_id),
        message_id=str(message_id),
        guild_id=raw_payload.get("guild_id"),
        raw_payload=raw_payload,
        metadata={"content_explicitly_empty": content_explicitly_empty},
    )


# ---------------------------------------------------------------------------
# Layer C: Lantern Observation entry
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class DiscordObservationResult:
    """Outcome of attempting to turn a normalized message into an Observation.

    ``observation`` is None when the message was rejected at normalization --
    rejection never raises into or mutates Lantern state, it is reported here
    instead, keeping the whole operation auditable.
    """

    observation_id: Optional[str]
    accepted: bool
    rejection_reason: Optional[str]
    source: str
    normalized: NormalizedDiscordMessage


def discord_message_to_observation(
    lantern,
    raw_payload: Any,
    *,
    reliability: float = 0.5,
) -> DiscordObservationResult:
    """Convert one raw Discord payload into a Lantern Observation.

    This is the ONLY function in this module that touches Lantern state, and
    it only ever calls ``lantern.observe(...)`` -- never ``add_evidence``,
    never ``resolve``, never ``create_scar``. Promotion to evidence/belief is
    the caller's explicit, separate decision.

    Deterministic: the same raw_payload always normalizes and observes the
    same way (aside from Lantern's own step counter advancing, which is
    Lantern's existing, already-tested behavior).

    A malformed/rejected payload never calls ``lantern.observe`` at all --
    Lantern's internal state is left completely untouched by an invalid
    input.
    """
    normalized = normalize_discord_message(raw_payload)

    if not normalized.valid:
        return DiscordObservationResult(
            observation_id=None,
            accepted=False,
            rejection_reason=normalized.rejection_reason,
            source=DISCORD_SOURCE_PREFIX,
            normalized=normalized,
        )

    source = f"{DISCORD_SOURCE_PREFIX}:{normalized.channel_id}:{normalized.author}"

    metadata = {
        "platform": "discord",
        "channel_id": normalized.channel_id,
        "message_id": normalized.message_id,
        "guild_id": normalized.guild_id,
        "author": normalized.author,
        "author_known": normalized.author_known,
        "timestamp": normalized.timestamp,
        "timestamp_known": normalized.timestamp_known,
        "content_explicitly_empty": normalized.metadata.get("content_explicitly_empty", False),
        "raw_payload": normalized.raw_payload,
    }

    observation = lantern.observe(
        content=normalized.content,
        source=source,
        reliability=reliability,
        metadata=metadata,
    )

    return DiscordObservationResult(
        observation_id=observation.id,
        accepted=True,
        rejection_reason=None,
        source=source,
        normalized=normalized,
    )
