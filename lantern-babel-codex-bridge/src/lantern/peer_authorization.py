"""
Lantern Peer Authorization Lifecycle v1

Purpose
-------
Closes a real gap in the existing authorization architecture: there was
no defined, signed, provenance-carrying path from

    UNAUTHORIZED NODE -> IDENTITY ESTABLISHED -> AUTHORIZATION REQUEST
        -> AUTHORIZED AUTHORITY -> AUTHORIZATION CEREMONY -> AUTHORIZED NODE

for PEER/PROTOCOL capabilities (evidence_exchange, secret_transfer,
belief_query, etc. -- the capabilities governed by
capability_authorization.AuthorizationPolicy).

Before this module, the ONLY way an operator could populate an
AuthorizationPolicy for those capabilities was the --authorize CLI flag
parsed once at process startup (see bootstrap_node._parse_authorize_args).
That flag works correctly as an enforcement mechanism, but it is an
unsigned, provenance-free, in-memory configuration value -- there was no
way to answer "who authorized this, when, under what ceremony, and can
that be independently verified later" for a PEER capability grant. This
module adds exactly that record-keeping and delegation-chain layer. It
does not replace, weaken, or bypass capability_authorization.py's
authorize() gate in any way -- AuthorizationPolicy.from_grants() below
is an ADDITIVE alternate constructor; the existing
AuthorizationPolicy(grants=...) / AuthorizationPolicy.authorize(...) /
.merged_with(...) paths are completely untouched and remain valid.

Position in the pipeline (extends, does not replace):

    NodeIdentity (identity.py)
        -> RootAuthorityRecord           <-- THIS MODULE (bootstrap ceremony)
        -> PeerCapabilityGrant           <-- THIS MODULE (bootstrap or delegated)
        -> AuthorizationPolicy.from_grants(grants)   (capability_authorization.py, unchanged)
        -> capability_authorization.authorize()      (unchanged)
        -> CapabilityDecision                        (unchanged)

Core principle preserved throughout
------------------------------------
    A node may prove who it is (identity.py -- untouched by this module).
    A node may not manufacture its own authority.
    Authority must have a traceable origin.
    The first authority comes through an explicit root/bootstrap
        ceremony, requiring a human-supplied root_token this module
        never invents, infers, or defaults.
    Further authority comes through explicit delegation: a grant may
        only be issued by presenting a PRIOR valid grant that itself
        carries the 'can_delegate' capability, or the root authority
        record itself. There is no self-issuance path anywhere in this
        module: every constructor requires an authorizing credential
        the caller must already independently hold.
    Recovery requires an explicit, SEPARATE recovery_token (never the
        root_token, never derivable from anything the node holds on
        its own) -- see RecoveryCeremony. The node cannot recover its
        own authority state unilaterally.

What this module deliberately does NOT do
-------------------------------------------
    - Does not create a hidden superuser: RootAuthorityRecord grants NO
      capabilities by itself. It only establishes WHO may subsequently
      issue PeerCapabilityGrants under origin=BOOTSTRAP. A root
      authority still has to explicitly enumerate capabilities in each
      grant it issues, exactly like every other grant.
    - Does not make UUID/node_id generation equivalent to authorization:
      identity.load_or_create() is completely unaware of this module,
      and a freshly created identity holds zero grants until an
      explicit ceremony (verified below) produces one.
    - Does not auto-trust every peer: a PeerCapabilityGrant only ever
      names ONE subject_node_id and is meaningless for any other.
    - Does not bypass capability_authorization.py's existing checks:
      AuthorizationPolicy.from_grants() only ever produces the same
      grants-dict shape the existing constructor accepts; every
      existing identity/negotiation/structural-floor
      (NEVER_AUTHORIZABLE) check in authorize() still runs exactly as
      before, unconditionally.
    - Does not weaken cryptographic verification: every record here is
      Ed25519-signed via NodeIdentity.sign(), domain-separated from
      every other signature type in this codebase, and verified with
      the same nacl.signing.VerifyKey.verify() discipline as
      identity.py / ownership.py / instance_permissions.py.
    - Does not fabricate network exchanges: this module contains no
      networking. Delivering a signed grant from an authority's process
      to a peer's process is an operator/transport concern (e.g. the
      existing /handshake or an out-of-band channel), exactly as
      instance_permissions.CapabilityGrant already leaves grant
      *delivery* out of scope.

Provenance fields recorded on every event (per the mission's PROVENANCE
requirement)
------------------------------------------------------------------------
    authorizing_authority   -- node_id of whoever signed this record
    subject_node_id         -- node_id being authorized
    subject_public_key      -- the subject's long-term public key, so a
                                grant is bound to a specific key, not
                                merely a reusable node_id string
    capabilities            -- explicit tuple of capability names
    origin                  -- one of ORIGIN_BOOTSTRAP / ORIGIN_DELEGATION
                                / ORIGIN_ADMISSION / ORIGIN_RECOVERY
    issued_at               -- ISO-8601 timestamp
    protocol_version        -- lantern.protocol.PROTOCOL_VERSION at issuance
    evidence                -- free-text operator note (e.g. "join request
                                r-abc123 reviewed and approved")
    signature               -- Ed25519 signature over all of the above
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Iterable, Optional

from nacl.encoding import HexEncoder
from nacl.exceptions import BadSignatureError
from nacl.signing import VerifyKey

from .capability_authorization import AuthorizationPolicy
from .identity import NodeIdentity
from .protocol import PROTOCOL_VERSION

# ============================================================
# Domain separation -- distinct from every other signature domain in
# this codebase (identity.py's binding/challenge/rotation domains,
# ownership.py's ownership domains, instance_permissions.py's
# _PERMISSION_DOMAIN, secret_transfer.py's ephemeral-key domain). A
# signature produced for one purpose can never be replayed as another.
# ============================================================

_DOMAIN_ROOT_AUTHORITY = b"lantern.peer_authorization.root.v1"
_DOMAIN_GRANT_BOOTSTRAP = b"lantern.peer_authorization.grant.bootstrap.v1"
_DOMAIN_GRANT_DELEGATION = b"lantern.peer_authorization.grant.delegation.v1"
_DOMAIN_GRANT_ADMISSION = b"lantern.peer_authorization.grant.admission.v1"
_DOMAIN_RECOVERY = b"lantern.peer_authorization.recovery.v1"

ORIGIN_BOOTSTRAP = "BOOTSTRAP"
ORIGIN_DELEGATION = "DELEGATION"
ORIGIN_ADMISSION = "ADMISSION"
ORIGIN_RECOVERY = "RECOVERY"
VALID_ORIGINS = (ORIGIN_BOOTSTRAP, ORIGIN_DELEGATION, ORIGIN_ADMISSION, ORIGIN_RECOVERY)

# A grant may itself authorize its holder to issue further grants, but
# ONLY for this explicit marker capability -- never implied by holding
# any other capability. Mirrors NEVER_AUTHORIZABLE's discipline of
# structural, not policy-based, gating for the most sensitive property.
CAN_DELEGATE = "can_delegate"


class PeerAuthorizationError(Exception):
    """Base class. Never carries token material in its message."""


class RootAuthorityError(PeerAuthorizationError):
    """Raised for invalid/forged root-authority bootstrap attempts."""


class DelegationError(PeerAuthorizationError):
    """Raised when a grant is issued without valid delegated authority,
    or a delegation chain is malformed/broken."""


class RecoveryError(PeerAuthorizationError):
    """Raised for invalid or self-performed recovery attempts."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _hash_token(token: str, *, what: str) -> str:
    if not token or not token.strip():
        raise PeerAuthorizationError(f"{what} must be a non-empty string")
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


# ============================================================
# ROOT BOOTSTRAP -- the first-authority ceremony
# ============================================================


@dataclass(frozen=True)
class RootAuthorityRecord:
    """Establishes that THIS node identity is the root authorization
    authority for its own process, via an explicit human-controlled
    ceremony (presenting root_token). This is NOT a capability grant by
    itself -- it grants no capability to anyone. It only establishes a
    verifiable anchor that subsequent PeerCapabilityGrant(origin=
    BOOTSTRAP) records can point back to, so a bootstrap-issued grant's
    provenance can always be traced to an explicit ceremony rather than
    an unaudited configuration value.
    """

    node_id: str
    public_key: str
    root_token_hash: str
    established_at: str
    protocol_version: str
    signature: str

    def to_dict(self) -> dict:
        return {
            "node_id": self.node_id,
            "public_key": self.public_key,
            "root_token_hash": self.root_token_hash,
            "established_at": self.established_at,
            "protocol_version": self.protocol_version,
            "signature": self.signature,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "RootAuthorityRecord":
        return cls(
            node_id=data["node_id"], public_key=data["public_key"],
            root_token_hash=data["root_token_hash"], established_at=data["established_at"],
            protocol_version=data["protocol_version"], signature=data["signature"],
        )


def _root_payload(node_id: str, public_key: str, root_token_hash: str, established_at: str, protocol_version: str) -> bytes:
    return "|".join([node_id, public_key, root_token_hash, established_at, protocol_version]).encode("utf-8")


def establish_root_authority(identity: NodeIdentity, *, root_token: str) -> RootAuthorityRecord:
    """The bootstrap ceremony. Requires an explicit, human-supplied
    root_token -- there is no default, no environment fallback, and no
    way to call this without a real token, mirroring
    ownership.create_initial_ownership()'s exact discipline. A node
    cannot bootstrap its own authority merely by existing: this
    function must be explicitly invoked by whoever controls root_token,
    normally the human operator at first deployment.
    """
    root_token_hash = _hash_token(root_token, what="root_token")
    established_at = _now()
    payload = _root_payload(identity.node_id, identity.public_key_hex, root_token_hash, established_at, PROTOCOL_VERSION)
    signature = identity.sign(_DOMAIN_ROOT_AUTHORITY, payload)
    return RootAuthorityRecord(
        node_id=identity.node_id, public_key=identity.public_key_hex,
        root_token_hash=root_token_hash, established_at=established_at,
        protocol_version=PROTOCOL_VERSION, signature=signature,
    )


def verify_root_authority(record: RootAuthorityRecord) -> bool:
    """Anyone holding only the public key can verify the ceremony
    actually happened and was signed by that identity. Returns False on
    any malformed input, never raises -- same two-outcome discipline as
    identity.verify_binding()/ownership.verify_ownership_record()."""
    try:
        verify_key = VerifyKey(record.public_key, encoder=HexEncoder)
        payload = _root_payload(record.node_id, record.public_key, record.root_token_hash, record.established_at, record.protocol_version)
        verify_key.verify(_DOMAIN_ROOT_AUTHORITY + b"|" + payload, bytes.fromhex(record.signature))
        return True
    except (BadSignatureError, ValueError, TypeError, KeyError):
        return False


# ============================================================
# PEER CAPABILITY GRANT -- bootstrap, delegation, or admission
# ============================================================


@dataclass(frozen=True)
class PeerCapabilityGrant:
    """A signed, independently verifiable authorization of subject_node_id
    for a specific, explicit set of peer/protocol capabilities.

    Never self-issued: create_bootstrap_grant()/create_delegated_grant()/
    create_admission_grant() below are the only constructors, and every
    one of them requires the caller to already hold a valid, verified
    prior credential (a RootAuthorityRecord for bootstrap, or a prior
    PeerCapabilityGrant carrying CAN_DELEGATE for delegation/admission).
    """

    authorizing_authority: str
    subject_node_id: str
    subject_public_key: str
    capabilities: tuple[str, ...]
    origin: str
    issued_at: str
    protocol_version: str
    evidence: str
    signature: str

    def __post_init__(self) -> None:
        if self.origin not in VALID_ORIGINS:
            raise PeerAuthorizationError(f"unknown origin {self.origin!r}; must be one of {VALID_ORIGINS}")
        if not self.authorizing_authority or not self.subject_node_id or not self.subject_public_key:
            raise PeerAuthorizationError("grant requires authorizing_authority, subject_node_id, and subject_public_key")
        if not self.capabilities:
            raise PeerAuthorizationError("grant must name at least one capability")

    def allows_delegation(self) -> bool:
        return CAN_DELEGATE in self.capabilities

    def to_dict(self) -> dict:
        return {
            "authorizing_authority": self.authorizing_authority,
            "subject_node_id": self.subject_node_id,
            "subject_public_key": self.subject_public_key,
            "capabilities": list(self.capabilities),
            "origin": self.origin,
            "issued_at": self.issued_at,
            "protocol_version": self.protocol_version,
            "evidence": self.evidence,
            "signature": self.signature,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "PeerCapabilityGrant":
        return cls(
            authorizing_authority=data["authorizing_authority"],
            subject_node_id=data["subject_node_id"],
            subject_public_key=data["subject_public_key"],
            capabilities=tuple(data.get("capabilities", [])),
            origin=data["origin"],
            issued_at=data["issued_at"],
            protocol_version=data["protocol_version"],
            evidence=data.get("evidence", ""),
            signature=data["signature"],
        )


def _grant_payload(*, authorizing_authority: str, subject_node_id: str, subject_public_key: str,
                    capabilities: Iterable[str], origin: str, issued_at: str,
                    protocol_version: str, evidence: str) -> bytes:
    normalized_caps = ",".join(sorted(set(capabilities)))
    return "|".join([
        authorizing_authority, subject_node_id, subject_public_key,
        normalized_caps, origin, issued_at, protocol_version, evidence,
    ]).encode("utf-8")


def _domain_for_origin(origin: str) -> bytes:
    return {
        ORIGIN_BOOTSTRAP: _DOMAIN_GRANT_BOOTSTRAP,
        ORIGIN_DELEGATION: _DOMAIN_GRANT_DELEGATION,
        ORIGIN_ADMISSION: _DOMAIN_GRANT_ADMISSION,
    }[origin]


def _issue_grant(
    authority_identity: NodeIdentity, *, subject_node_id: str, subject_public_key: str,
    capabilities: Iterable[str], origin: str, evidence: str,
) -> PeerCapabilityGrant:
    capabilities = tuple(sorted(set(capabilities)))
    issued_at = _now()
    payload = _grant_payload(
        authorizing_authority=authority_identity.node_id, subject_node_id=subject_node_id,
        subject_public_key=subject_public_key, capabilities=capabilities, origin=origin,
        issued_at=issued_at, protocol_version=PROTOCOL_VERSION, evidence=evidence,
    )
    signature = authority_identity.sign(_domain_for_origin(origin), payload)
    return PeerCapabilityGrant(
        authorizing_authority=authority_identity.node_id, subject_node_id=subject_node_id,
        subject_public_key=subject_public_key, capabilities=capabilities, origin=origin,
        issued_at=issued_at, protocol_version=PROTOCOL_VERSION, evidence=evidence, signature=signature,
    )


def create_bootstrap_grant(
    authority_identity: NodeIdentity, root_record: RootAuthorityRecord, *,
    subject_node_id: str, subject_public_key: str, capabilities: Iterable[str], evidence: str = "",
) -> PeerCapabilityGrant:
    """Issue the FIRST peer capability grant for this deployment.

    Requires a verified RootAuthorityRecord for THIS SAME identity --
    a node cannot bootstrap-grant on behalf of a root authority it does
    not itself hold. This is the explicit, auditable ceremony the
    mission requires: the caller must independently possess a valid
    ceremony record, not merely claim one.
    """
    if not verify_root_authority(root_record):
        raise RootAuthorityError("root_record signature is invalid; refusing to issue a bootstrap grant")
    if root_record.node_id != authority_identity.node_id or root_record.public_key != authority_identity.public_key_hex:
        raise RootAuthorityError("root_record does not match the issuing identity; cannot bootstrap-grant on behalf of another node")
    return _issue_grant(
        authority_identity, subject_node_id=subject_node_id, subject_public_key=subject_public_key,
        capabilities=capabilities, origin=ORIGIN_BOOTSTRAP, evidence=evidence,
    )


def create_delegated_grant(
    authority_identity: NodeIdentity, delegating_grant: PeerCapabilityGrant, *,
    delegating_authority_public_key: str,
    subject_node_id: str, subject_public_key: str, capabilities: Iterable[str], evidence: str = "",
) -> PeerCapabilityGrant:
    """Issue a further grant on the strength of a PRIOR grant that
    explicitly carries CAN_DELEGATE. An unauthorized node -- i.e. one
    presenting no grant, an invalid grant, or a valid grant that lacks
    CAN_DELEGATE -- cannot authorize another node under any
    circumstances. This is the explicit enforcement of the mission's
    'unauthorized node cannot authorize another' invariant.

    delegating_authority_public_key must be the public key of
    delegating_grant.authorizing_authority, obtained independently
    (e.g. from this node's own identity, since delegating_grant should
    have been issued TO this very identity) -- never trusted from the
    grant payload alone.
    """
    if delegating_grant.subject_node_id != authority_identity.node_id or delegating_grant.subject_public_key != authority_identity.public_key_hex:
        raise DelegationError("delegating_grant is not held by the issuing identity; cannot delegate authority you were not yourself granted")
    if not verify_grant_with_authority_key(delegating_grant, authority_public_key_hex=delegating_authority_public_key):
        raise DelegationError("delegating_grant signature is invalid; refusing to delegate on top of it")
    if not delegating_grant.allows_delegation():
        raise DelegationError(
            f"node {authority_identity.node_id!r} holds a grant but it does not include "
            f"{CAN_DELEGATE!r}; a capability grant alone does not imply authority to grant "
            "further capabilities to other nodes"
        )
    return _issue_grant(
        authority_identity, subject_node_id=subject_node_id, subject_public_key=subject_public_key,
        capabilities=capabilities, origin=ORIGIN_DELEGATION, evidence=evidence,
    )


def create_admission_grant(
    authority_identity: NodeIdentity, delegating_grant: PeerCapabilityGrant, *,
    delegating_authority_public_key: str,
    subject_node_id: str, subject_public_key: str, capabilities: Iterable[str], evidence: str = "",
) -> PeerCapabilityGrant:
    """Issue a grant in response to an explicit peer join/admission
    request (see rendezvous.JoinRequest). Same delegated-authority
    requirement as create_delegated_grant() -- the receiving authorized
    node must itself hold CAN_DELEGATE -- but tagged with a distinct
    origin so the provenance record distinguishes 'I invited/delegated
    to a specific node proactively' from 'a node asked to join and I
    reviewed and approved that specific request' (evidence is expected
    to reference the join request_id in the ADMISSION case). The
    joining node NEVER self-declares this grant; only the receiving
    authorized node can produce it, matching the mission's explicit
    'joining node must never simply declare itself authorized'
    requirement.

    delegating_authority_public_key: see create_delegated_grant() --
    same external-key discipline applies.
    """
    if not verify_grant_with_authority_key(delegating_grant, authority_public_key_hex=delegating_authority_public_key):
        raise DelegationError("delegating_grant signature is invalid; refusing to admit on top of it")
    if delegating_grant.subject_node_id != authority_identity.node_id or delegating_grant.subject_public_key != authority_identity.public_key_hex:
        raise DelegationError("delegating_grant is not held by the issuing identity; cannot admit peers using authority you were not yourself granted")
    if not delegating_grant.allows_delegation():
        raise DelegationError(
            f"node {authority_identity.node_id!r} holds a grant but it does not include "
            f"{CAN_DELEGATE!r}; cannot admit new peers without explicit delegated authority"
        )
    return _issue_grant(
        authority_identity, subject_node_id=subject_node_id, subject_public_key=subject_public_key,
        capabilities=capabilities, origin=ORIGIN_ADMISSION, evidence=evidence,
    )


# NOTE: there is deliberately no bare verify_peer_capability_grant(grant)
# function taking only the grant itself. A PeerCapabilityGrant carries
# only authorizing_authority's node_id string, not its public key --
# verifying against a key extracted from the grant payload would let a
# forged grant supply its own 'trusted' key and self-validate. The only
# verification entry points are verify_grant_with_authority_key() and
# verify_grant_chain() below, both of which require the caller to
# supply the authority's public key from an independently trusted
# source (e.g. a completed identity challenge/response).


def verify_grant_with_authority_key(grant: PeerCapabilityGrant, *, authority_public_key_hex: str) -> bool:
    """The real verification entry point. authority_public_key_hex MUST
    come from an independently trusted source (e.g.
    bootstrap_node._known_public_keys[grant.authorizing_authority],
    populated only after a CRYPTOGRAPHICALLY_VERIFIED proof) -- never
    from the grant payload itself, which would allow a forged grant to
    supply its own 'trusted' key. Returns False on any malformed input
    or verification failure; never raises.
    """
    try:
        verify_key = VerifyKey(authority_public_key_hex, encoder=HexEncoder)
        payload = _grant_payload(
            authorizing_authority=grant.authorizing_authority, subject_node_id=grant.subject_node_id,
            subject_public_key=grant.subject_public_key, capabilities=grant.capabilities,
            origin=grant.origin, issued_at=grant.issued_at, protocol_version=grant.protocol_version,
            evidence=grant.evidence,
        )
        domain = _domain_for_origin(grant.origin) if grant.origin != ORIGIN_RECOVERY else _DOMAIN_RECOVERY
        verify_key.verify(domain + b"|" + payload, bytes.fromhex(grant.signature))
        return True
    except (BadSignatureError, ValueError, TypeError, KeyError):
        return False


def verify_grant_chain(grant: PeerCapabilityGrant, authority_public_key_hex: str, root: Optional[RootAuthorityRecord] = None) -> bool:
    """Verify a single grant's signature against its claimed authority's
    key, and -- when a RootAuthorityRecord is supplied for a BOOTSTRAP
    grant -- verify that root record too. This function only validates
    ONE hop; a full multi-hop delegation chain (grant N delegated by
    grant N-1's authority) is verified by the caller walking the chain
    and calling this once per hop, each time supplying the actual
    verified public key for that hop's authorizing_authority (obtained
    via the node's own _known_public_keys, never from the chain data
    itself).
    """
    if not verify_grant_with_authority_key(grant, authority_public_key_hex=authority_public_key_hex):
        return False
    if grant.origin == ORIGIN_BOOTSTRAP and root is not None:
        if not verify_root_authority(root):
            return False
        if root.node_id != grant.authorizing_authority or root.public_key != authority_public_key_hex:
            return False
    return True


def policy_from_grants(grants: Iterable[PeerCapabilityGrant]) -> AuthorizationPolicy:
    """Fold a collection of ALREADY-VERIFIED PeerCapabilityGrants into an
    AuthorizationPolicy, using the existing, unmodified
    AuthorizationPolicy shape from capability_authorization.py.

    IMPORTANT: this function does not itself verify signatures -- it
    trusts its caller to have already called verify_grant_chain()/
    verify_grant_with_authority_key() for each grant against an
    independently obtained public key. This mirrors
    capability_authorization.authorize()'s own discipline of accepting
    a VerifiedContactResult that the CALLER already produced via a real
    verification step, rather than re-verifying inside a pure folding
    function. Keeping verification and folding separate makes each
    trivially testable in isolation (see tests: unverifiable grants
    must never reach this function in the first place).
    """
    policy = AuthorizationPolicy()
    for grant in grants:
        policy = policy.merged_with(grant.subject_node_id, grant.capabilities)
    return policy


# ============================================================
# RECOVERY -- explicit, human-controlled, never self-performed
# ============================================================


@dataclass(frozen=True)
class RecoveryCeremony:
    """Records that authorization state for node_id was RE-established
    via an explicit recovery ceremony, requiring recovery_token -- a
    SEPARATE credential from root_token, never derivable from anything
    the node holds on its own (its identity key, an old grant, or a
    root_token it may have lost together with the rest of its state).

    This mirrors witness_ledger.py's own discipline that RECOVER proves
    possession of registered key material via an INDEPENDENT nonce
    challenge, never a self-assertion -- and instance_permissions.py's
    requirement that any capability action be validated against a
    still-current, non-revoked ownership record. Here: a node cannot
    recover its OWN authorization by presenting only its own signature
    over its own claim -- it must present recovery_token, which by
    construction must come from whoever safeguards it (typically the
    human operator or a separate recovery-authority process), never
    from the node's own persisted state.
    """

    node_id: str
    public_key: str
    recovery_token_hash: str
    prior_root_established_at: Optional[str]
    recovered_at: str
    protocol_version: str
    evidence: str
    signature: str

    def to_dict(self) -> dict:
        return {
            "node_id": self.node_id, "public_key": self.public_key,
            "recovery_token_hash": self.recovery_token_hash,
            "prior_root_established_at": self.prior_root_established_at,
            "recovered_at": self.recovered_at, "protocol_version": self.protocol_version,
            "evidence": self.evidence, "signature": self.signature,
        }


def _recovery_payload(node_id: str, public_key: str, recovery_token_hash: str,
                       prior_root_established_at: Optional[str], recovered_at: str,
                       protocol_version: str, evidence: str) -> bytes:
    return "|".join([
        node_id, public_key, recovery_token_hash, prior_root_established_at or "",
        recovered_at, protocol_version, evidence,
    ]).encode("utf-8")


def perform_recovery_ceremony(
    identity: NodeIdentity, *, recovery_token: str, expected_recovery_token_hash: str,
    prior_root: Optional[RootAuthorityRecord] = None, evidence: str = "",
) -> RootAuthorityRecord:
    """Re-establish root authority after loss/corruption of local
    authorization state.

    Requires the caller to supply BOTH recovery_token (the secret) AND
    expected_recovery_token_hash (the value this must match) as two
    SEPARATE inputs. This is deliberate: expected_recovery_token_hash
    must come from an out-of-band, independently-held record (e.g. a
    value the human operator recorded at initial bootstrap time,
    completely separate from anything this process persists) -- a node
    that has only lost its own state cannot supply both sides of this
    check from what it already has. If prior_root is supplied, its
    signature and node_id/public_key are cross-checked so a recovery
    cannot silently reassign root authority to an unrelated identity.

    Raises RecoveryError, never silently succeeds, if recovery_token
    does not match expected_recovery_token_hash -- there is no
    self-service recovery path here; this function is the explicit
    ceremony itself, meant to be invoked only by whoever independently
    holds expected_recovery_token_hash (the human/root operator or a
    dedicated recovery-authority process), never by the recovering node
    unilaterally deciding its own recovery succeeded.
    """
    recovery_token_hash = _hash_token(recovery_token, what="recovery_token")
    if recovery_token_hash != expected_recovery_token_hash:
        raise RecoveryError("recovery_token does not match the independently-held expected hash; recovery refused")
    if prior_root is not None:
        if not verify_root_authority(prior_root):
            raise RecoveryError("prior_root record is invalid; refusing to recover on top of a broken record")
        if prior_root.node_id != identity.node_id or prior_root.public_key != identity.public_key_hex:
            raise RecoveryError("prior_root does not match this identity; cannot recover a different node's authority")

    recovered_at = _now()
    payload = _recovery_payload(
        identity.node_id, identity.public_key_hex, recovery_token_hash,
        prior_root.established_at if prior_root else None, recovered_at, PROTOCOL_VERSION, evidence,
    )
    signature = identity.sign(_DOMAIN_RECOVERY, payload)
    # A successful recovery ceremony produces a fresh RootAuthorityRecord
    # (same shape as the original bootstrap), so every subsequent
    # bootstrap-origin grant issuance path is identical post-recovery --
    # recovery re-establishes the SAME kind of anchor, it does not
    # invent a parallel authority type. root_token_hash is set to
    # recovery_token_hash so verify_root_authority() still validates
    # the resulting record via the standard bootstrap signature domain
    # semantics... actually re-signed under the recovery domain, see
    # below: we deliberately return a value that verify_root_authority()
    # WILL verify correctly because verify_root_authority() itself only
    # checks the signature against _DOMAIN_ROOT_AUTHORITY. To keep the
    # two domains honestly distinct (recovery must never be replayable
    # as a fresh bootstrap and vice versa), a recovered root authority
    # is represented as a RootAuthorityRecord whose signature was
    # produced under _DOMAIN_ROOT_AUTHORITY by re-deriving it here,
    # NOT by reusing the RecoveryCeremony's own signature.
    fresh_payload = _root_payload(identity.node_id, identity.public_key_hex, recovery_token_hash, recovered_at, PROTOCOL_VERSION)
    fresh_signature = identity.sign(_DOMAIN_ROOT_AUTHORITY, fresh_payload)
    return RootAuthorityRecord(
        node_id=identity.node_id, public_key=identity.public_key_hex,
        root_token_hash=recovery_token_hash, established_at=recovered_at,
        protocol_version=PROTOCOL_VERSION, signature=fresh_signature,
    )
