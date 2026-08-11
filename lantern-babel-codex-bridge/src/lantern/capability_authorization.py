"""Capability authorization: the explicit local decision layer between a
cryptographically verified identity and any application-level permission.

Position in the pipeline:

    NetworkContactPolicy -> NetworkContactTransport -> verified_contact.verify_contact()
        -> VerifiedContactResult (identity_status, shared_capabilities)
        -> capability_authorization.authorize()          <-- THIS MODULE
        -> CapabilityDecision
        -> UNTRUSTED PARTICIPANT WITH EXPLICITLY BOUNDED CAPABILITIES

This module answers exactly one question:

    "Given that I have cryptographically verified this node, which
    protocol capabilities am I explicitly willing to expose to it?"

It does NOT answer, and never touches:

    - "Do I trust this participant?"        (trust_status; not this module)
    - "What authority does it have?"        (authority_level; not this module)
    - Any actual evidence/belief/Codex/Scar/snapshot exchange.

============================================================
Three independent axes -- do not collapse them
============================================================

    identity_status
        WHO controls the key? Set exclusively by lantern.identity via
        verified_contact.verify_contact(). This module only reads it; it
        never computes or upgrades it.

    capability (shared vs authorized)
        WHAT protocol operation is on the table, and separately, WHAT
        protocol operation has this node explicitly agreed to expose?
        shared_capabilities (from the handshake) is a negotiation result,
        not a permission. authorized_capabilities is this module's output
        and is the only one of the two that means "may actually be used".

    trust_status / authority_level
        DO I trust this participant, and with what authority? This
        module never sets either. Every CapabilityDecision this module
        produces is compatible with trust_status="unverified" and
        authority_level="none" (lantern.participants' unconditional
        defaults) remaining exactly as they are -- authorization of a
        narrow capability is not, and must never become, trust.

============================================================
Why authorized_capabilities is never shared_capabilities
============================================================

compatibility.negotiate() / handshake.evaluate_handshake() already
compute a mutual intersection of what both sides claim to support --
that is a negotiation result, not a decision about what this operator
is willing to expose to *this specific, now-identity-verified* remote
node. Collapsing the two would mean any node that merely speaks the
same protocol dialect gets full access to every capability this node
happens to support, the moment its key is verified. That is exactly the
escalation this phase is required to prevent:

    identity verified  != trusted
    capability negotiated != capability authorized
    capability authorized != Codex authority

The default authorization policy below is maximally conservative:
nothing is authorized unless the caller passes an explicit policy that
says otherwise, and even then codex_update can never be granted.

============================================================
codex_update is structurally unauthorizable here
============================================================

`codex_update` is hard-excluded from authorization in this module,
independent of any policy input, independent of shared_capabilities,
independent of identity_status. This mirrors compatibility.py's own
comment ("Remains False until an explicit trust/evaluation protocol
exists") and architecture.py's CANONICAL_CAPABILITIES /
FROZEN_CONSTANTS, which this module does not modify or bypass. See
tests/test_lantern_capability_authorization.py for explicit proof that
no combination of verified identity + shared capability + policy input
can produce an authorized codex_update.

============================================================
No architecture-boundary access
============================================================

This module imports nothing from lantern.core, lantern.federation,
lantern.router, lantern.boundary, lantern.bridge, lantern.scars, or
lantern.agent, and calls none of add_evidence()/belief()/observe()/
resolve()/persist_scar(). authorize() is a pure function over its
arguments: same inputs always produce the same CapabilityDecision, with
no hidden state, no I/O, and no Chronicle/Codex/trust/authority
mutation of any kind.

============================================================
Persistence
============================================================

No persistent trust or authorization state is introduced here.
AuthorizationPolicy is an in-memory, caller-supplied mapping; nothing is
written to disk by this module. If a caller wants authorization
decisions to survive a restart, that is an explicit, separate,
future-phase decision -- not something this module does implicitly.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Iterable, Mapping, Optional

from . import identity as identity_module
from .compatibility import DEFAULT_CAPABILITIES
from .verified_contact import VerifiedContactResult

__all__ = [
    "CapabilityDecision",
    "AuthorizationPolicy",
    "DenialReason",
    "NEVER_AUTHORIZABLE",
    "authorize",
]


# Capabilities that this module will never place into
# authorized_capabilities, regardless of identity_status,
# shared_capabilities, or policy input. This is a structural floor, not
# a default that a policy can override -- see module docstring.
NEVER_AUTHORIZABLE = frozenset({"codex_update"})


class DenialReason:
    """String constants for CapabilityDecision.denied_capabilities values.

    Plain string constants (not an Enum) so denied_capabilities can be
    trivially serialized via to_dict() without an extra encoding step.
    """

    IDENTITY_NOT_VERIFIED = "identity_not_verified"
    NOT_SHARED = "not_mutually_negotiated"
    NOT_LOCALLY_SUPPORTED = "not_locally_supported"
    UNKNOWN_CAPABILITY = "unknown_capability"
    STRUCTURALLY_UNAUTHORIZABLE = "structurally_unauthorizable"
    NOT_REQUESTED = "not_requested"
    POLICY_DENIED = "policy_denied"


@dataclass(frozen=True)
class CapabilityDecision:
    """Immutable, inspectable, deterministic authorization decision.

    Contains no private key material, no secrets, no raw Discord
    credentials -- only node identifiers, capability names, and short
    human-readable reason strings.
    """

    node_id: str
    identity_status: str
    shared_capabilities: frozenset
    authorized_capabilities: frozenset
    denied_capabilities: Mapping[str, str]
    reason: str

    @property
    def authorized(self) -> bool:
        return len(self.authorized_capabilities) > 0

    def is_authorized(self, capability: str) -> bool:
        return capability in self.authorized_capabilities

    def to_dict(self) -> dict:
        return {
            "node_id": self.node_id,
            "identity_status": self.identity_status,
            "shared_capabilities": sorted(self.shared_capabilities),
            "authorized_capabilities": sorted(self.authorized_capabilities),
            "denied_capabilities": dict(self.denied_capabilities),
            "reason": self.reason,
        }


# A policy is any callable (node_id, capability) -> bool. AuthorizationPolicy
# is a small convenience wrapper around the common case of "an explicit
# per-node allow-set", but callers may pass any callable with this
# signature directly to authorize(policy=...).
PolicyFn = Callable[[str, str], bool]


@dataclass(frozen=True)
class AuthorizationPolicy:
    """A narrow, explicit, in-memory authorization allow-list.

    grants: node_id -> set of capability names the operator explicitly
    permits for that node. Nothing is inferred, nothing is persisted,
    and an empty/omitted policy authorizes nothing (the conservative
    default described in the module docstring).
    """

    grants: Mapping[str, frozenset] = field(default_factory=dict)

    @staticmethod
    def authorize(node_id: str, capabilities: Iterable[str]) -> "AuthorizationPolicy":
        """Convenience constructor: authorize(node_id="x", capabilities={"y"})."""
        return AuthorizationPolicy(grants={node_id: frozenset(capabilities)})

    def allows(self, node_id: str, capability: str) -> bool:
        return capability in self.grants.get(node_id, frozenset())

    def merged_with(self, node_id: str, capabilities: Iterable[str]) -> "AuthorizationPolicy":
        """Return a NEW policy with additional grants for node_id. Does not
        mutate self -- AuthorizationPolicy is treated as immutable."""
        existing = set(self.grants.get(node_id, frozenset()))
        existing.update(capabilities)
        new_grants = dict(self.grants)
        new_grants[node_id] = frozenset(existing)
        return AuthorizationPolicy(grants=new_grants)


#: The conservative default: authorizes nothing for anyone. Passing no
#: policy to authorize() is equivalent to passing this.
EMPTY_POLICY = AuthorizationPolicy()


def _as_policy_fn(policy) -> PolicyFn:
    if policy is None:
        return lambda node_id, capability: False
    if isinstance(policy, AuthorizationPolicy):
        return policy.allows
    if callable(policy):
        return policy
    raise TypeError(
        "policy must be None, an AuthorizationPolicy, or a callable "
        "(node_id, capability) -> bool"
    )


def authorize(
    verified: VerifiedContactResult,
    *,
    requested: Optional[Iterable[str]] = None,
    policy: Optional[object] = None,
    local_capabilities: Optional[Mapping[str, bool]] = None,
) -> CapabilityDecision:
    """Produce a CapabilityDecision. Pure function: same inputs -> same
    output, no I/O, no network activity, no Chronicle/Codex/trust/
    authority mutation.

    verified: a VerifiedContactResult from verified_contact.verify_contact().
        Only used for its node_id/identity_status/shared_capabilities
        fields -- this function never re-contacts the peer.

    requested: the capability names the caller wants evaluated for this
        node. Defaults to the full negotiated shared_capabilities set
        (i.e. "consider authorizing everything that was mutually
        negotiated") -- but "considered" is not "granted": each requested
        capability must still pass every check below, and with no policy
        supplied the result is an empty authorized_capabilities set
        (AUTHORIZED = {} is the conservative default described in the
        phase brief).

    policy: None, an AuthorizationPolicy, or a callable
        (node_id, capability) -> bool. Defaults to authorizing nothing.

    local_capabilities: what this node itself supports, defaults to
        compatibility.DEFAULT_CAPABILITIES (the single canonical
        registry -- this module does not maintain a second one).

    A capability is placed into authorized_capabilities only if ALL of:
        1. verified.identity_status == CRYPTOGRAPHICALLY_VERIFIED
        2. the capability is a known, locally supported capability name
           (present in local_capabilities and local_capabilities[name] truthy)
        3. the capability is in verified.shared_capabilities (i.e. was
           actually mutually negotiated at handshake time, not merely
           claimed unilaterally by either side)
        4. the capability was in `requested`
        5. policy_fn(node_id, capability) is True
        6. the capability is not in NEVER_AUTHORIZABLE (structural floor,
           checked first and unconditionally)

    Any capability failing any check lands in denied_capabilities with an
    explicit reason instead of being silently dropped.
    """
    local_capabilities = (
        dict(local_capabilities) if local_capabilities is not None else DEFAULT_CAPABILITIES
    )
    policy_fn = _as_policy_fn(policy)

    node_id = verified.remote_node_id or ""
    identity_status = verified.identity_status
    shared = frozenset(
        name for name, enabled in verified.shared_capabilities.items() if enabled
    )

    identity_verified = identity_status == identity_module.CRYPTOGRAPHICALLY_VERIFIED

    if requested is None:
        candidates = set(shared)
    else:
        candidates = set(requested)

    authorized: set[str] = set()
    denied: dict[str, str] = {}

    for capability in sorted(candidates):
        if capability in NEVER_AUTHORIZABLE:
            denied[capability] = DenialReason.STRUCTURALLY_UNAUTHORIZABLE
            continue

        if not identity_verified:
            denied[capability] = DenialReason.IDENTITY_NOT_VERIFIED
            continue

        if capability not in local_capabilities:
            denied[capability] = DenialReason.UNKNOWN_CAPABILITY
            continue

        if not local_capabilities.get(capability):
            denied[capability] = DenialReason.NOT_LOCALLY_SUPPORTED
            continue

        if capability not in shared:
            denied[capability] = DenialReason.NOT_SHARED
            continue

        if not policy_fn(node_id, capability):
            denied[capability] = DenialReason.POLICY_DENIED
            continue

        authorized.add(capability)

    # Any capability present in shared_capabilities but never actually
    # requested is recorded as explicitly not-requested rather than
    # silently omitted, so denied_capabilities + authorized_capabilities
    # together account for the full candidate surface a caller reasoned
    # about (requested ∪ shared), never leaving a capability unaccounted
    # for.
    for capability in sorted(shared - candidates):
        denied.setdefault(capability, DenialReason.NOT_REQUESTED)

    if not identity_verified:
        reason = f"identity_status={identity_status!r} is not CRYPTOGRAPHICALLY_VERIFIED; no capability can be authorized"
    elif not authorized:
        reason = "no requested capability was both mutually negotiated and explicitly authorized by policy"
    else:
        reason = "authorized capabilities are the subset of negotiated capabilities explicitly permitted by policy"

    return CapabilityDecision(
        node_id=node_id,
        identity_status=identity_status,
        shared_capabilities=shared,
        authorized_capabilities=frozenset(authorized),
        denied_capabilities=denied,
        reason=reason,
    )
