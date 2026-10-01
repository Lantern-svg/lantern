"""Authorization ledger: the explicit, auditable origin of authority.

THE INVARIANT THIS MODULE ENFORCES
----------------------------------
    A node may prove who it is.                    (lantern.identity)
    A node may NOT manufacture its own authority.   (THIS MODULE)

Before this module, inbound capability authorization existed only as
operator-supplied static configuration (--authorize flags /
LANTERN_AUTHORIZE env): correct in spirit -- the human IS the root
authority -- but ephemeral. It was never recorded, never delegated,
never available at peer-join time, and indistinguishable after the
fact from any other process start. capability_authorization.py states
this explicitly: persistence of authorization was "an explicit,
separate, future-phase decision". This module is that decision.

THE MODEL (mirrors lantern.witness_ledger's LAR-1 discipline)
--------------------------------------------------------------
    IDENTITY          a node generates and proves its own key pair.
                      Identity != authorization (three independent
                      axes; see capability_authorization.py).
    ROOT BOOTSTRAP    the FIRST authority is the human operator. The
                      startup ceremony converts --authorize /
                      --grant-admission / --authorization-recovery into
                      append-only BOOTSTRAP/RECOVERY events signed by
                      the chain, not by the node's will.
    DELEGATION        the operator may delegate a bounded ADMISSION
                      SCOPE to the node (--grant-admission). Within
                      that scope -- and never beyond it, and never for
                      structurally unauthorizable capabilities -- the
                      node may admit verified peers at runtime.
    PEER JOIN         a peer proves identity (existing PoP flow),
                      opens an authenticated session, and REQUESTS
                      admission. The receiving node performs the
                      ceremony only if its delegated scope covers the
                      request. A peer can never declare itself
                      authorized: the runtime path is authority-gated,
                      and a node can never admit ITSELF.
    RECOVERY          lost/corrupted ledger state fails CLOSED (chain
                      verification -> no authority, no admissions).
                      Restoration requires a NEW operator ceremony
                      (RECOVERY events). There is no self-recovery
                      path, by construction.

PROVENANCE (every event records all of it)
------------------------------------------
    event_type         BOOTSTRAP | RECOVERY | ADMISSION | DELEGATION
    authority          "operator" (root ceremony) or the owning node's
                       node_id (runtime admission, only within its
                       delegated scope)
    subject_node       the node being authorized
    subject_fingerprint  SHA-256 of the subject's public key where it
                       was known at ceremony time ("" for static
                       startup grants made before first contact; the
                       binding is then enforced live by PoP)
    scope              the capability names granted
    delegable          whether this event delegates admission authority
    timestamp          UTC ISO-8601
    protocol_version   the protocol generation of the ceremony
    evidence          human-readable provenance (command, session,
                      request)
    prev_digest/digest SHA-256 hash chain (tamper-evident, like the
                       witness ledger and Chronicle)

FAIL-CLOSED RULES (enforced on append AND on every load)
--------------------------------------------------------
    1. digest chain must recompute exactly
    2. BOOTSTRAP/RECOVERY events must have authority == "operator"
    3. ADMISSION events must have authority == the ledger owner, a
       subject != authority, and a prior valid delegated scope that
       covers the granted capabilities
    4. no event may ever include a NEVER_AUTHORIZABLE capability
    5. any violation => chain_valid == False => zero admissions, zero
       admission authority. Nothing upgrades itself from a broken chain.

This module imports nothing from lantern.core/federation/router/
boundary/bridge/scars/agent and performs no Chronicle/Codex/trust
mutation. It is a pure, auditable record layer.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Optional

from .capability_authorization import (
    AuthorizationPolicy,
    EMPTY_POLICY,
    NEVER_AUTHORIZABLE,
)
from .protocol import PROTOCOL_VERSION

__all__ = [
    "AuthorizationLedgerError",
    "AuthorizationLedger",
    "GENESIS_DIGEST",
]

GENESIS_DIGEST = "0" * 64
OPERATOR_AUTHORITY = "operator"
EVENT_TYPES = frozenset({"BOOTSTRAP", "RECOVERY", "ADMISSION", "DELEGATION"})
#: Fields every event must carry -- the provenance contract.
PROVENANCE_FIELDS = (
    "event_type",
    "authority",
    "subject_node",
    "subject_fingerprint",
    "scope",
    "delegable",
    "timestamp",
    "protocol_version",
    "evidence",
    "prev_digest",
    "digest",
)


class AuthorizationLedgerError(Exception):
    """Raised on any attempt to append an event that would violate the
    authorization invariant. Fail-closed: the event is never written."""


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _canonical(body: dict) -> str:
    return json.dumps(body, sort_keys=True, separators=(",", ":"))


def _digest_of(prev_digest: str, body: dict) -> str:
    return hashlib.sha256(
        (prev_digest + _canonical(body)).encode("utf-8")
    ).hexdigest()


def _validate_scope(scope: Iterable[str]) -> frozenset:
    caps = frozenset(c for c in scope if c and isinstance(c, str))
    if not caps:
        raise AuthorizationLedgerError("scope must contain at least one capability")
    bad = caps & NEVER_AUTHORIZABLE
    if bad:
        raise AuthorizationLedgerError(
            f"structurally unauthorizable capabilities can never be granted: {sorted(bad)}"
        )
    return caps


class AuthorizationLedger:
    """Append-only, hash-chained record of how this node's authority
    came to exist. One ledger per node, stored beside the Chronicle.

    The ledger FILE is operator-controlled filesystem state, with the
    same trust basis as today's --authorize flags; the ledger's job is
    to make that trust explicit, bounded, delegable, and auditable --
    and to make the node's RUNTIME provably unable to mint authority.
    """

    def __init__(self, path: str | Path, owner_node_id: str):
        self.path = Path(path)
        self.owner_node_id = owner_node_id
        self._events: list[dict] = []
        self.chain_valid = True
        self._load()

    # ------------------------------------------------------------------
    # persistence
    # ------------------------------------------------------------------

    def _load(self) -> None:
        self._events = []
        self.chain_valid = True
        if not self.path.exists():
            return
        try:
            raw_lines = [
                json.loads(line)
                for line in self.path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
        except (OSError, ValueError):
            self.chain_valid = False
            return
        if not self._verify_events(raw_lines):
            self.chain_valid = False
            # Fail closed: keep NO events from a broken chain.
            return
        self._events = raw_lines

    def _verify_events(self, events: list[dict]) -> bool:
        prev = GENESIS_DIGEST
        delegated_scope: frozenset = frozenset()
        for event in events:
            if not isinstance(event, dict):
                return False
            for field_name in PROVENANCE_FIELDS:
                if field_name not in event:
                    return False
            body = {k: event[k] for k in PROVENANCE_FIELDS if k not in ("digest",)}
            if event["digest"] != _digest_of(prev, body):
                return False
            prev = event["digest"]
            if event["event_type"] not in EVENT_TYPES:
                return False
            if event["protocol_version"] != PROTOCOL_VERSION:
                return False
            try:
                scope = frozenset(event["scope"])
            except TypeError:
                return False
            if scope & NEVER_AUTHORIZABLE:
                return False
            if event["event_type"] in ("BOOTSTRAP", "RECOVERY"):
                # Root ceremony: only the human operator may appear as
                # the authorizing authority.
                if event["authority"] != OPERATOR_AUTHORITY:
                    return False
                if event["subject_node"] == self.owner_node_id and event["delegable"]:
                    delegated_scope = delegated_scope | scope
            elif event["event_type"] == "ADMISSION":
                # Runtime admission: must be this node acting within a
                # previously delegated scope; never self-admission.
                if event["authority"] != self.owner_node_id:
                    return False
                if event["subject_node"] in (self.owner_node_id, event["authority"]):
                    return False
                if not scope or not scope <= delegated_scope:
                    return False
            else:  # DELEGATION (future portable grants; reserved)
                return False
        return True

    # ------------------------------------------------------------------
    # append
    # ------------------------------------------------------------------

    def _append(self, event_type: str, *, authority: str, subject_node: str,
                subject_fingerprint: str, scope: frozenset, delegable: bool,
                evidence: str) -> dict:
        if event_type not in EVENT_TYPES:
            raise AuthorizationLedgerError(f"unknown event type {event_type!r}")
        if event_type == "DELEGATION":
            # Reserved: portable node-to-node delegation grants. Refused
            # until that protocol is defined -- refusing is fail-closed;
            # accepting undefined events is not.
            raise AuthorizationLedgerError(
                "portable DELEGATION grants are not yet defined; refusing"
            )
        caps = _validate_scope(scope)
        if event_type in ("BOOTSTRAP", "RECOVERY") and authority != OPERATOR_AUTHORITY:
            raise AuthorizationLedgerError(
                "root ceremony events may only be authored by the operator"
            )
        if event_type == "ADMISSION":
            if not self.chain_valid:
                raise AuthorizationLedgerError(
                    "ledger chain is not valid: no events may be appended"
                )
            if authority != self.owner_node_id:
                raise AuthorizationLedgerError(
                    "admission events are authored only by the ledger owner"
                )
            if subject_node == authority or subject_node == self.owner_node_id:
                raise AuthorizationLedgerError(
                    "a node may never admit itself (self-authorization)"
                )
            if not caps <= self.admission_authority():
                raise AuthorizationLedgerError(
                    "admission exceeds delegated authority scope"
                )
        prev = self._events[-1]["digest"] if self._events else GENESIS_DIGEST
        body = {
            "event_type": event_type,
            "authority": authority,
            "subject_node": subject_node,
            "subject_fingerprint": subject_fingerprint,
            "scope": sorted(caps),
            "delegable": bool(delegable),
            "timestamp": _now_iso(),
            "protocol_version": PROTOCOL_VERSION,
            "evidence": evidence,
            "prev_digest": prev,
        }
        event = dict(body)
        event["digest"] = _digest_of(prev, body)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, sort_keys=True) + "\n")
        self._events.append(event)
        return event

    # ------------------------------------------------------------------
    # operator ceremony (startup path only -- never the node runtime)
    # ------------------------------------------------------------------

    def record_operator_ceremony(
        self,
        *,
        authorize_entries: list[tuple[str, list[str]]],
        admission_scope: Iterable[str] = (),
        recovery_note: Optional[str] = None,
    ) -> list[dict]:
        """Convert this run's operator configuration into explicit,
        idempotent provenance events.

        BOOTSTRAP for a normal start; RECOVERY when the operator passes
        an explicit recovery note (documented LAR-1-style ceremony for
        authorization state). Re-running the same ceremony appends
        nothing -- provenance is a record, not an echo.
        """
        if not self.chain_valid:
            raise AuthorizationLedgerError(
                "ledger chain is not valid: operator must restore from a "
                "clean backup or start a new ledger; the node cannot "
                "self-recover"
            )
        event_type = "RECOVERY" if recovery_note else "BOOTSTRAP"
        recorded: list[dict] = []
        seen = {
            (
                e["event_type"],
                e["authority"],
                e["subject_node"],
                tuple(e["scope"]),
                e["delegable"],
                e["evidence"],
            )
            for e in self._events
        }

        def _dedup_key(subject: str, caps: frozenset, delegable: bool, evidence: str):
            return (
                event_type, OPERATOR_AUTHORITY, subject,
                tuple(sorted(caps)), delegable, evidence,
            )

        note = f"recovery: {recovery_note}" if recovery_note else ""
        base_evidence = "operator CLI ceremony"
        for peer_node, capabilities in authorize_entries:
            caps = frozenset(c for c in capabilities if c)
            if not caps:
                continue
            _validate_scope(caps)
            evidence = f"{base_evidence}: --authorize {peer_node}:{','.join(sorted(caps))}"
            if note:
                evidence = f"{evidence} ({note})"
            if _dedup_key(peer_node, caps, False, evidence) in seen:
                continue
            recorded.append(self._append(
                event_type, authority=OPERATOR_AUTHORITY, subject_node=peer_node,
                subject_fingerprint="", scope=caps, delegable=False,
                evidence=evidence,
            ))
        scope = frozenset(c for c in admission_scope if c)
        if scope:
            _validate_scope(scope)
            evidence = (
                f"{base_evidence}: --grant-admission {','.join(sorted(scope))}"
                + (f" ({note})" if note else "")
            )
            if _dedup_key(self.owner_node_id, scope, True, evidence) not in seen:
                recorded.append(self._append(
                    event_type, authority=OPERATOR_AUTHORITY,
                    subject_node=self.owner_node_id, subject_fingerprint="",
                    scope=scope, delegable=True, evidence=evidence,
                ))
        return recorded

    # ------------------------------------------------------------------
    # runtime admission (the node, within its delegated scope only)
    # ------------------------------------------------------------------

    def admit_peer(
        self,
        *,
        subject_node: str,
        subject_fingerprint: str,
        scope: Iterable[str],
        evidence: str,
    ) -> dict:
        return self._append(
            "ADMISSION",
            authority=self.owner_node_id,
            subject_node=subject_node,
            subject_fingerprint=subject_fingerprint,
            scope=frozenset(scope),
            delegable=False,
            evidence=evidence,
        )

    # ------------------------------------------------------------------
    # derived state (all fail-closed on an invalid chain)
    # ------------------------------------------------------------------

    def events(self) -> list[dict]:
        return list(self._events) if self.chain_valid else []

    def admission_authority(self) -> frozenset:
        """The capability scope this node may admit peers into. Only
        from valid operator-delegated events; NEVER_AUTHORIZABLE is
        structurally excluded."""
        if not self.chain_valid:
            return frozenset()
        scope: frozenset = frozenset()
        for event in self._events:
            if (
                event["event_type"] in ("BOOTSTRAP", "RECOVERY")
                and event["delegable"]
                and event["subject_node"] == self.owner_node_id
                and event["authority"] == OPERATOR_AUTHORITY
            ):
                scope = scope | frozenset(event["scope"])
        return scope - NEVER_AUTHORIZABLE

    def admissions_policy(self) -> AuthorizationPolicy:
        """Inbound policy derived from ADMISSION events only. Empty on
        an invalid chain -- a tampered ledger grants nothing."""
        policy = EMPTY_POLICY
        if not self.chain_valid:
            return policy
        for event in self._events:
            if event["event_type"] == "ADMISSION":
                policy = policy.merged_with(
                    event["subject_node"], frozenset(event["scope"])
                )
        return policy
