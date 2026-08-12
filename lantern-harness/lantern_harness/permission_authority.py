"""Permission Authority: capability-scope permission memory + alignment
checking, per the PEACEMAKER DELEGATED AUTHORITY, ALIGNMENT, AND
PERMISSION MEMORY directive.

This is a NEW component. It composes with, and never replaces:

    lantern_harness.tools.boundary.ToolBoundary
        -- owns per-tool registration/authorization/execution for
           harness-registered convenience tools. PermissionAuthority
           answers a broader question ("is this whole CAPABILITY
           CATEGORY in scope, and is this specific action aligned
           with it") that a caller can use before ever reaching a
           ToolBoundary.execute() call.
    lantern_harness.decision_state_machine.DecisionStateMachine
        -- recommends a confidence-based state/action. Alignment here
           is a different axis (does this action fit operator intent,
           stated objective, and boundaries) and is evaluated
           separately; a PermissionGrant is not a DecisionReading and
           an AlignmentResult is not a confidence score.
    lantern_harness.reality_boundary.RealityBoundary
        -- owns INTENT -> DECISION -> AUTHORIZATION -> ACTION -> RESULT
           for anything touching the external world. PermissionAuthority
           is upstream of that: it answers "may this be attempted at
           all, per the operator's standing grants", not "did it
           actually happen".

Hard rule enforced by this module, not just documented (directive
section 11, the Core Behavioral Rule):

    AUTHORIZED_SCOPE and ALIGNMENT_CHECK together determine ACTIONABLE

    - authorized AND aligned          -> ACT
    - authorized BUT misaligned       -> STOP_AND_REASSESS
    - aligned BUT NOT authorized      -> ASK_OPERATOR
    - NEITHER authorized NOR aligned  -> REFUSE

No method in this module can set its own grant. Every PermissionGrant
must be constructed with an explicit granting_authority string supplied
by the caller (the operator, via main.py/a script -- never inferred,
never defaulted to "self"). See test_permission_authority.py's
test_grant_requires_explicit_granting_authority and
test_permission_authority_cannot_self_grant.

Grants are held ONLY in this process's memory (a plain Python list on
the PermissionAuthority instance). They are deliberately NOT persisted
to data_dir, Chronicle, or any file this harness writes -- because per
the directive's Transfer Behavior (section 9), authority must never
travel with transferred state. A transferred Peacemaker instance (see
transfer_manifest.py) carries identity/evidence/history; it does not
carry, and this module cannot cause it to carry, a previous operator's
permission grants. Every new process starts with zero grants and must
be re-authorized by whoever is operating it now. See
test_permission_authority_grants_do_not_persist_across_instances.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


# ---- Capability categories -------------------------------------------
#
# These are the *names* a grant can reference, not grants themselves.
# Defining a category here does not authorize it -- see module docstring.
# External-authority categories (credentials, wallets, payments, network
# exposure, publication, communications, legal/financial commitments,
# destructive operations, private-data disclosure) never inherit from
# one another; each is its own category by design (directive section 8).

CAPABILITY_CATEGORIES = (
    "local_file_modification",
    "run_tests",
    "local_git_commit",
    "software_release_publication",
    "external_network_service",
    "credential_use",
    "wallet_or_payment_authority",
    "external_communication",
    "legal_or_financial_commitment",
    "destructive_system_operation",
    "private_data_disclosure",
    "authority_transfer_to_another_agent",
)

# Categories that, per the directive's section 8, must NEVER be implied
# by authorization of any other category, no matter how similar the
# wording. Enforced in PermissionAuthority.check(), not just documented.
NEVER_INHERITS = (
    "credential_use",
    "wallet_or_payment_authority",
    "external_communication",
    "legal_or_financial_commitment",
    "destructive_system_operation",
    "private_data_disclosure",
    "authority_transfer_to_another_agent",
)

RESULT_ACT = "ACT"
RESULT_STOP_AND_REASSESS = "STOP_AND_REASSESS"
RESULT_ASK_OPERATOR = "ASK_OPERATOR"
RESULT_REFUSE = "REFUSE"

GRANT_STATUS_ACTIVE = "ACTIVE"
GRANT_STATUS_REVOKED = "REVOKED"
GRANT_STATUS_EXPIRED = "EXPIRED"


@dataclass(frozen=True)
class PermissionGrant:
    """One capability-scope permission, as remembered state. Never
    constructed by this module on its own initiative -- always the
    result of an explicit PermissionAuthority.grant() call carrying a
    real, non-empty granting_authority string."""

    capability: str
    scope: str
    boundary: str
    granting_authority: str
    provenance: str
    version: int
    granted_at_step: int
    status: str = GRANT_STATUS_ACTIVE
    expires_at_step: Optional[int] = None
    conditions: tuple = field(default_factory=tuple)

    def to_dict(self) -> dict:
        return {
            "capability": self.capability,
            "scope": self.scope,
            "boundary": self.boundary,
            "granting_authority": self.granting_authority,
            "provenance": self.provenance,
            "version": self.version,
            "granted_at_step": self.granted_at_step,
            "status": self.status,
            "expires_at_step": self.expires_at_step,
            "conditions": list(self.conditions),
        }

    def is_active(self, current_step: Optional[int] = None) -> bool:
        if self.status != GRANT_STATUS_ACTIVE:
            return False
        if self.expires_at_step is not None and current_step is not None:
            if current_step >= self.expires_at_step:
                return False
        return True


@dataclass(frozen=True)
class AlignmentResult:
    """The result of evaluating one proposed action against known
    operating principles and current operator intent. This is a
    judgment record, not an authorization -- a PASSED AlignmentResult
    never grants anything by itself (see PermissionAuthority.check)."""

    verdict: str  # "PASSED" | "FAILED" | "UNCERTAIN"
    considered: tuple
    supporting_evidence: tuple
    contradictions: tuple
    foreseeable_consequences: tuple
    introduces_new_commitment: bool
    reasoning: str

    def to_dict(self) -> dict:
        return {
            "verdict": self.verdict,
            "considered": list(self.considered),
            "supporting_evidence": list(self.supporting_evidence),
            "contradictions": list(self.contradictions),
            "foreseeable_consequences": list(self.foreseeable_consequences),
            "introduces_new_commitment": self.introduces_new_commitment,
            "reasoning": self.reasoning,
        }


@dataclass(frozen=True)
class PermissionCheckResult:
    """The full auditable record required by the directive's section
    10: what was proposed, whether it was in scope, what alignment
    found, and what the combined result was. This is the object
    main.py/a script should log and, when consequential, show the
    operator -- it answers every question section 10 lists."""

    action: str
    capability: str
    authorized: bool
    matched_grant: Optional[PermissionGrant]
    alignment: AlignmentResult
    result: str  # ACT | STOP_AND_REASSESS | ASK_OPERATOR | REFUSE
    is_new_capability: bool
    external_effects: tuple
    notes: tuple = field(default_factory=tuple)

    def to_dict(self) -> dict:
        return {
            "action": self.action,
            "capability": self.capability,
            "authorized": self.authorized,
            "matched_grant": self.matched_grant.to_dict() if self.matched_grant else None,
            "alignment": self.alignment.to_dict(),
            "result": self.result,
            "is_new_capability": self.is_new_capability,
            "external_effects": list(self.external_effects),
            "notes": list(self.notes),
        }

    def format(self) -> str:
        lines = [f"[permission check: {self.result}]"]
        lines.append(f"action: {self.action}")
        lines.append(f"capability: {self.capability}")
        lines.append(f"authorized: {self.authorized}")
        if self.matched_grant:
            lines.append(
                f"matched_grant: scope={self.matched_grant.scope!r} "
                f"granted_by={self.matched_grant.granting_authority!r} "
                f"status={self.matched_grant.status}"
            )
        lines.append(f"alignment: {self.alignment.verdict} -- {self.alignment.reasoning}")
        if self.alignment.contradictions:
            lines.append("alignment contradictions: " + "; ".join(self.alignment.contradictions))
        lines.append(f"is_new_capability: {self.is_new_capability}")
        lines.append("external_effects: " + (", ".join(self.external_effects) or "none"))
        for note in self.notes:
            lines.append(f"note: {note}")
        return "\n".join(lines)


class PermissionAuthority:
    """Holds capability-scope grants (in-process memory only -- see
    module docstring) and combines them with an AlignmentResult per
    action, per the directive's Core Behavioral Rule (section 11).

    This class never produces its own AlignmentResult judgment -- that
    requires reasoning about operator intent, which is the caller's
    (the reasoning engine / operator script's) job, not this module's.
    PermissionAuthority.check() takes an already-produced AlignmentResult
    as input, exactly like RealityBoundary.act() takes an
    already-authorized ToolBoundary decision as input. This keeps the
    same separation of concerns as the rest of the harness: this module
    owns the SCOPE MEMORY and the COMBINATION RULE, not the judgment
    itself.
    """

    def __init__(self):
        self._grants = []
        self._next_version = 1

    def grant(
        self,
        *,
        capability: str,
        scope: str,
        boundary: str,
        granting_authority: str,
        provenance: str,
        granted_at_step: int = 0,
        expires_at_step: Optional[int] = None,
        conditions: Optional[list] = None,
    ) -> PermissionGrant:
        """Records a new capability-scope grant. This method itself
        performs no judgment about whether the grant is wise -- it
        records what an external granting_authority (the operator)
        explicitly stated. A caller in this codebase is never allowed
        to invoke this with granting_authority defaulted to something
        like "self" or "harness" -- see test coverage."""
        if capability not in CAPABILITY_CATEGORIES:
            raise ValueError(
                f"unknown capability category {capability!r}; must be one of {CAPABILITY_CATEGORIES}"
            )
        if not granting_authority or not granting_authority.strip():
            raise ValueError("granting_authority must be a non-empty, explicit string (e.g. the operator's identifier)")
        if not scope or not scope.strip():
            raise ValueError("scope must be a non-empty string describing what the grant actually covers")

        record = PermissionGrant(
            capability=capability,
            scope=scope.strip(),
            boundary=boundary.strip() if boundary else "",
            granting_authority=granting_authority.strip(),
            provenance=provenance.strip() if provenance else "unspecified",
            version=self._next_version,
            granted_at_step=granted_at_step,
            expires_at_step=expires_at_step,
            conditions=tuple(conditions or ()),
        )
        self._next_version += 1
        self._grants.append(record)
        return record

    def revoke(self, capability: str, granting_authority: str) -> int:
        """Marks all ACTIVE grants for a capability as REVOKED. Returns
        the count revoked. Revocation, like granting, requires an
        explicit granting_authority -- this module never revokes its
        own grants on its own initiative."""
        if not granting_authority or not granting_authority.strip():
            raise ValueError("granting_authority must be a non-empty string to revoke a grant")
        count = 0
        updated = []
        for grant in self._grants:
            if grant.capability == capability and grant.status == GRANT_STATUS_ACTIVE:
                updated.append(
                    PermissionGrant(
                        capability=grant.capability,
                        scope=grant.scope,
                        boundary=grant.boundary,
                        granting_authority=grant.granting_authority,
                        provenance=grant.provenance,
                        version=grant.version,
                        granted_at_step=grant.granted_at_step,
                        status=GRANT_STATUS_REVOKED,
                        expires_at_step=grant.expires_at_step,
                        conditions=grant.conditions,
                    )
                )
                count += 1
            else:
                updated.append(grant)
        self._grants = updated
        return count

    def active_grants(self, current_step: Optional[int] = None) -> tuple:
        return tuple(g for g in self._grants if g.is_active(current_step))

    def all_grants(self) -> tuple:
        """Full history including revoked/expired grants -- for
        auditability (directive section 10), not for authorization
        decisions (use active_grants/check for those)."""
        return tuple(self._grants)

    def _find_active_grant(self, capability: str, current_step: Optional[int]) -> Optional[PermissionGrant]:
        for grant in reversed(self._grants):
            if grant.capability == capability and grant.is_active(current_step):
                return grant
        return None

    def check(
        self,
        *,
        action: str,
        capability: str,
        alignment: AlignmentResult,
        external_effects: Optional[list] = None,
        current_step: Optional[int] = None,
    ) -> PermissionCheckResult:
        """Combines standing scope + alignment per the directive's
        Core Behavioral Rule. This is the single decision point every
        consequential action in this harness should pass through
        before RealityBoundary.act() is ever called."""
        if not action or not action.strip():
            raise ValueError("action must be a non-empty description of the proposed action")

        is_new_capability = capability not in CAPABILITY_CATEGORIES
        matched_grant = None if is_new_capability else self._find_active_grant(capability, current_step)
        authorized = matched_grant is not None

        notes = []
        if capability in NEVER_INHERITS and matched_grant is None:
            notes.append(
                f"capability {capability!r} is an external-authority category and is never implied "
                "by any other grant, even a superficially similar one (directive section 8)"
            )

        if alignment.verdict == "PASSED" and authorized:
            result = RESULT_ACT
        elif alignment.verdict != "PASSED" and authorized:
            result = RESULT_STOP_AND_REASSESS
            notes.append("action is within an existing authorized scope but did not pass alignment; a similar-looking grant does not override a failed/uncertain alignment result")
        elif alignment.verdict == "PASSED" and not authorized:
            result = RESULT_ASK_OPERATOR
        else:
            result = RESULT_REFUSE

        return PermissionCheckResult(
            action=action.strip(),
            capability=capability,
            authorized=authorized,
            matched_grant=matched_grant,
            alignment=alignment,
            result=result,
            is_new_capability=is_new_capability,
            external_effects=tuple(external_effects or ()),
            notes=tuple(notes),
        )

    def format_new_authority_request(self, check_result: PermissionCheckResult, *, purpose: str) -> str:
        """Formats the ASK_OPERATOR question exactly as specified in
        the directive's section 3: what action, why, what capability,
        what external effects, what alignment produced, what existing
        authorization (if any) applies, what new authority approval
        would grant."""
        lines = [
            "NEW AUTHORITY REQUEST",
            "",
            "Action:",
            f"  {check_result.action}",
            "",
            "Purpose:",
            f"  {purpose}",
            "",
            "Existing authorization:",
            f"  {check_result.matched_grant.to_dict() if check_result.matched_grant else 'None'}",
            "",
            "Alignment:",
            f"  {check_result.alignment.verdict} -- {check_result.alignment.reasoning}",
            "",
            "Required authority:",
            f"  {check_result.capability}",
            "",
            "External effects:",
            f"  {', '.join(check_result.external_effects) or 'none identified'}",
            "",
            "Result:",
            "  ASK OPERATOR.",
        ]
        return "\n".join(lines)

    def format_action_complete(self, check_result: PermissionCheckResult, *, outcome: str) -> str:
        """Formats the after-the-fact notification specified in the
        directive's section 5: informational, not a retroactive
        permission request."""
        lines = [
            "PEACEMAKER ACTION COMPLETE",
            "",
            "Action:",
            f"  {check_result.action}",
            "",
            "Authorization:",
            f"  Previously granted -- {check_result.capability}"
            + (f" (scope: {check_result.matched_grant.scope})" if check_result.matched_grant else ""),
            "",
            "Alignment:",
            f"  {check_result.alignment.verdict}",
            "",
            "Result:",
            f"  {outcome}",
            "",
            "External effects:",
            f"  {', '.join(check_result.external_effects) or 'none identified'}",
            "",
            "No new authority requested.",
        ]
        return "\n".join(lines)
