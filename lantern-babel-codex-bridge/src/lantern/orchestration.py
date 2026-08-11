"""Sovereign orchestration scaffold for Lantern.

This module adds a local-first capability/delegation layer without
changing Lantern's existing authority model.

Design constraints:
- Lantern remains the decision layer.
- Capabilities are discoverable and classifiable, but discovery is not
  authorization.
- Workers can perform tasks, but worker return values are not treated as
  verified success automatically.
- Memory mutation, identity, permissions, provenance, contradictions,
  self-modification, and delegation policy remain protected concerns that
  are described here but not delegated away.
- This module is intentionally local and in-memory. It does not expose a
  public server, does not persist authority state, and does not call MCP
  itself. It creates the contract Lantern can later use above MCP or any
  other interface.

v0.2 adds, on top of the v0.1 capability registry / delegation lifecycle:
  - verification policies attached to capability descriptors
  - explicit scoped-delegation fields (allowed_capabilities,
    forbidden_authorities, expected_outputs, provenance_requirements,
    confirmation_requirements)
  - a conservative planner/decomposer that never executes tools directly
  - a provenance tag model (LOCAL_* vs REMOTE_* classes)
  - a self-change proposal model (proposal/review only, never
    self-applying)

None of this weakens the v0.1 invariants: capability existence, capability
availability, capability authorization, execution, RETURNED, VERIFIED,
ACCEPTED, and memory-may-change remain separate states that are never
collapsed into each other by this module.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any, Iterable, Optional
import uuid


ORCHESTRATION_VERSION = "0.2"


# ==========================================================
# Frozen orchestration constants
# ==========================================================

CORE_WORKERS = (
    "OBSERVER",
    "EVALUATOR",
    "ORGANIZER",
    "AUDITOR",
)

SPECIALIZED_WORKERS = (
    "CODER",
    "RESEARCHER",
    "COMMUNICATOR",
    "SCHEDULER",
    "DEVICE_OPERATOR",
    "VISUALIZER",
    "TESTER",
    "NETWORK_INTEROPERABILITY",
)

DELEGATION_STATUSES = (
    "REQUESTED",
    "DELEGATED",
    "EXECUTING",
    "RETURNED",
    "VERIFIED",
    "FAILED",
    "REQUIRES_HUMAN_CONFIRMATION",
)

#: Statuses a delegation may terminate in without further work. FAILED is
#: terminal unless a NEW delegation is explicitly created for a retry --
#: there is no retry_from_failed() on DelegationRecord itself, on purpose.
TERMINAL_DELEGATION_STATUSES = frozenset({"VERIFIED", "FAILED"})

PROTECTED_AUTHORITIES = frozenset({
    "memory_mutation",
    "identity",
    "permissions",
    "capability_selection",
    "sensitive_data_access",
    "provenance",
    "contradictions",
    "confirmation_requirements",
    "retractions",
    "core_rules",
    "self_modification",
    "delegation_policy",
})

NEVER_EXTERNALLY_EXPOSE = frozenset({
    "memory_mutation",
    "identity",
    "permissions",
    "core_rules",
    "self_modification",
    "delegation_policy",
})

#: Provenance classes for any result Lantern receives, local or remote.
#: A result's provenance class is retained through evaluation; nothing in
#: this module rewrites a remote provenance to look local.
PROVENANCE_CLASSES = (
    "LOCAL_TOOL",
    "LOCAL_WORKER",
    "LOCAL_LANTERN",
    "REMOTE_AGENT",
    "REMOTE_LANTERN",
    "MCP_ENDPOINT",
    "A2A_ENDPOINT",
    "HUMAN",
    "PUBLIC_SOURCE",
    "UNKNOWN",
)

#: Classes whose output is remote by construction. A remote result stays
#: an observation -- it does not become local truth just by arriving.
REMOTE_PROVENANCE_CLASSES = frozenset({
    "REMOTE_AGENT",
    "REMOTE_LANTERN",
    "MCP_ENDPOINT",
    "A2A_ENDPOINT",
    "PUBLIC_SOURCE",
})

SELF_CHANGE_STATUSES = (
    "PROPOSED",
    "REVIEWED",
    "APPROVED",
    "REJECTED",
)


# ==========================================================
# Provenance
# ==========================================================

@dataclass(frozen=True)
class ProvenanceTag:
    """Where a result actually came from.

    A remote observation never gets rewritten as a local one. Nothing in
    this module converts a REMOTE_* provenance into LOCAL_* provenance --
    that would be exactly the silent-truth-conversion this architecture
    forbids.
    """

    source_class: str
    identifier: str
    note: str = ""

    def __post_init__(self) -> None:
        if self.source_class not in PROVENANCE_CLASSES:
            raise ValueError(f"unknown provenance class: {self.source_class}")

    @property
    def is_remote(self) -> bool:
        return self.source_class in REMOTE_PROVENANCE_CLASSES

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_class": self.source_class,
            "identifier": self.identifier,
            "note": self.note,
            "is_remote": self.is_remote,
        }


# ==========================================================
# Self-change proposals
# ==========================================================

@dataclass(frozen=True)
class SelfChangeProposal:
    """A proposal to change Lantern's own orchestration architecture.

    This is proposal/review territory. Nothing in this module applies a
    SelfChangeProposal automatically. There is no code path from
    "proposal created" to "core logic changed" -- that step, if it ever
    happens, is a separate, explicitly authorized, human-reviewed action
    outside this module.
    """

    reason: str
    evidence: tuple[str, ...]
    proposed_change: str
    expected_effect: str
    risks: tuple[str, ...]
    verification_plan: str
    authority_required: frozenset[str] = field(default_factory=frozenset)
    status: str = "PROPOSED"
    id: str = field(default_factory=lambda: str(uuid.uuid4()))

    def __post_init__(self) -> None:
        if self.status not in SELF_CHANGE_STATUSES:
            raise ValueError(f"unknown self-change status: {self.status}")

    def with_status(self, status: str) -> "SelfChangeProposal":
        if status not in SELF_CHANGE_STATUSES:
            raise ValueError(f"unknown self-change status: {status}")
        return replace(self, status=status)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "reason": self.reason,
            "evidence": list(self.evidence),
            "proposed_change": self.proposed_change,
            "expected_effect": self.expected_effect,
            "risks": list(self.risks),
            "verification_plan": self.verification_plan,
            "authority_required": sorted(self.authority_required),
            "status": self.status,
        }


# ==========================================================
# Verification policy
# ==========================================================

@dataclass(frozen=True)
class VerificationPolicy:
    """How Lantern independently checks a capability's claimed result.

    A worker reporting success is an input to verification, never a
    substitute for it. `worker_claim_sufficient` exists only so that
    invariant is checkable in tests -- it must always be False.
    """

    method: str
    evidence_required: tuple[str, ...]
    worker_claim_sufficient: bool = False

    def __post_init__(self) -> None:
        if self.worker_claim_sufficient:
            raise ValueError(
                "a worker's own claim can never be sufficient verification"
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "method": self.method,
            "evidence_required": list(self.evidence_required),
            "worker_claim_sufficient": self.worker_claim_sufficient,
        }


# ==========================================================
# Capability model
# ==========================================================

@dataclass(frozen=True)
class CapabilityDescriptor:
    name: str
    purpose: str
    kind: str
    worker: str
    local_only: bool
    trusted: bool
    exposes_via_mcp: bool
    authority_requirements: frozenset[str] = field(default_factory=frozenset)
    sensitive_inputs: frozenset[str] = field(default_factory=frozenset)
    returns: tuple[str, ...] = field(default_factory=tuple)
    limitations: tuple[str, ...] = field(default_factory=tuple)
    underlying_tools: tuple[str, ...] = field(default_factory=tuple)
    verification_policy: Optional[VerificationPolicy] = None

    @property
    def externally_exposable(self) -> bool:
        return not bool(self.authority_requirements & NEVER_EXTERNALLY_EXPOSE)

    @property
    def requires_protected_authority(self) -> bool:
        return bool(self.authority_requirements & PROTECTED_AUTHORITIES)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "purpose": self.purpose,
            "kind": self.kind,
            "worker": self.worker,
            "local_only": self.local_only,
            "trusted": self.trusted,
            "exposes_via_mcp": self.exposes_via_mcp,
            "externally_exposable": self.externally_exposable,
            "requires_protected_authority": self.requires_protected_authority,
            "authority_requirements": sorted(self.authority_requirements),
            "sensitive_inputs": sorted(self.sensitive_inputs),
            "returns": list(self.returns),
            "limitations": list(self.limitations),
            "underlying_tools": list(self.underlying_tools),
            "verification_policy": (
                self.verification_policy.to_dict()
                if self.verification_policy is not None
                else None
            ),
        }


class CapabilityRegistry:
    """Local registry of capabilities Lantern may reason about.

    This registry is descriptive, not permissive. Registering or
    discovering a capability does not authorize its use. The registry is
    meant to let Lantern ask:
      - what exists?
      - what kind of hand is this?
      - what worker would typically use it?
      - what authority would be touched if I used it?
      - how would a claimed result from it actually be verified?
    """

    def __init__(self, capabilities: Optional[Iterable[CapabilityDescriptor]] = None):
        self._capabilities: dict[str, CapabilityDescriptor] = {}
        for capability in capabilities or []:
            self.register(capability)

    def register(self, capability: CapabilityDescriptor) -> None:
        self._capabilities[capability.name] = capability

    def get(self, name: str) -> Optional[CapabilityDescriptor]:
        return self._capabilities.get(name)

    def all(self) -> list[CapabilityDescriptor]:
        return [self._capabilities[name] for name in sorted(self._capabilities)]

    def discover(
        self,
        *,
        worker: Optional[str] = None,
        kind: Optional[str] = None,
        mcp_ready: Optional[bool] = None,
        externally_exposable: Optional[bool] = None,
    ) -> list[CapabilityDescriptor]:
        out = self.all()
        if worker is not None:
            out = [item for item in out if item.worker == worker]
        if kind is not None:
            out = [item for item in out if item.kind == kind]
        if mcp_ready is not None:
            out = [item for item in out if item.exposes_via_mcp == mcp_ready]
        if externally_exposable is not None:
            out = [item for item in out if item.externally_exposable == externally_exposable]
        return out

    def summary(self) -> dict[str, Any]:
        items = self.all()
        return {
            "count": len(items),
            "core_workers": list(CORE_WORKERS),
            "specialized_workers": list(SPECIALIZED_WORKERS),
            "capabilities": [item.to_dict() for item in items],
        }


# ==========================================================
# Delegation model
# ==========================================================

@dataclass(frozen=True)
class DelegationRecord:
    """A bounded assignment. A worker receives THIS, never "Lantern access".

    authority_scope / allowed_information are the original (v0.1) field
    names and remain the primary scoping fields for backward
    compatibility. The newer fields below make the same bounded-scope
    contract explicit and machine-checkable:

      allowed_capabilities      -- capability names this delegation may use
      forbidden_authorities     -- authorities this delegation must NOT touch
      expected_outputs          -- what a valid RETURNED result looks like
      verification_policy       -- how Lantern will check the result
      provenance_requirements   -- what provenance must be attached to results
      confirmation_requirements -- reasons this delegation needs human confirmation
    """

    objective: str
    capability: str
    worker: str
    status: str = "REQUESTED"
    authority_scope: frozenset[str] = field(default_factory=frozenset)
    allowed_information: frozenset[str] = field(default_factory=frozenset)
    allowed_capabilities: frozenset[str] = field(default_factory=frozenset)
    forbidden_authorities: frozenset[str] = field(default_factory=frozenset)
    expected_outputs: tuple[str, ...] = field(default_factory=tuple)
    verification_policy: Optional[VerificationPolicy] = None
    provenance_requirements: tuple[str, ...] = field(default_factory=tuple)
    confirmation_requirements: tuple[str, ...] = field(default_factory=tuple)
    result_summary: Optional[str] = None
    result_provenance: Optional[ProvenanceTag] = None
    verification_summary: Optional[str] = None
    requires_human_confirmation: bool = False
    id: str = field(default_factory=lambda: str(uuid.uuid4()))

    def __post_init__(self) -> None:
        if self.status not in DELEGATION_STATUSES:
            raise ValueError(f"unknown delegation status: {self.status}")
        overlap = self.authority_scope & self.forbidden_authorities
        if overlap:
            raise ValueError(
                f"authority_scope and forbidden_authorities overlap: {sorted(overlap)}"
            )

    def transition(
        self,
        status: str,
        *,
        result_summary: Optional[str] = None,
        result_provenance: Optional[ProvenanceTag] = None,
        verification_summary: Optional[str] = None,
        requires_human_confirmation: Optional[bool] = None,
    ) -> "DelegationRecord":
        if status not in DELEGATION_STATUSES:
            raise ValueError(f"unknown delegation status: {status}")
        return replace(
            self,
            status=status,
            result_summary=(self.result_summary if result_summary is None else result_summary),
            result_provenance=(
                self.result_provenance if result_provenance is None else result_provenance
            ),
            verification_summary=(
                self.verification_summary if verification_summary is None else verification_summary
            ),
            requires_human_confirmation=(
                self.requires_human_confirmation
                if requires_human_confirmation is None
                else requires_human_confirmation
            ),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "objective": self.objective,
            "capability": self.capability,
            "worker": self.worker,
            "status": self.status,
            "authority_scope": sorted(self.authority_scope),
            "allowed_information": sorted(self.allowed_information),
            "allowed_capabilities": sorted(self.allowed_capabilities),
            "forbidden_authorities": sorted(self.forbidden_authorities),
            "expected_outputs": list(self.expected_outputs),
            "verification_policy": (
                self.verification_policy.to_dict() if self.verification_policy else None
            ),
            "provenance_requirements": list(self.provenance_requirements),
            "confirmation_requirements": list(self.confirmation_requirements),
            "result_summary": self.result_summary,
            "result_provenance": (
                self.result_provenance.to_dict() if self.result_provenance else None
            ),
            "verification_summary": self.verification_summary,
            "requires_human_confirmation": self.requires_human_confirmation,
        }


# ==========================================================
# Conservative planner
# ==========================================================

@dataclass(frozen=True)
class PlanStep:
    """One step of a delegation plan. Describes a bounded delegation to
    be created -- it does not itself run anything."""

    capability: str
    worker: str
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {"capability": self.capability, "worker": self.worker, "reason": self.reason}


class OrchestrationPlanner:
    """Turns an objective into an ordered, bounded delegation plan.

    Lifecycle this planner exists to support:

        OBSERVATION -> DECOMPOSITION -> CAPABILITY SELECTION ->
        WORKER SELECTION -> AUTHORITY SCOPING -> DELEGATION ->
        EXECUTION -> RETURNED -> LANTERN VERIFICATION ->
        VERIFIED / FAILED / RETRY / ESCALATE -> AUTHORIZED MEMORY PATH

    The planner only performs the first five steps (through AUTHORITY
    SCOPING) and produces DelegationRecord objects in REQUESTED status.
    It never calls a worker, never calls an underlying OpenClaw tool, and
    never marks anything RETURNED or VERIFIED itself -- those transitions
    belong to whatever actually executes the delegation and to Lantern's
    separate evaluation step, respectively.
    """

    #: keyword -> capability name, in priority order. This is intentionally
    #: a small, explicit, auditable table rather than a model call --
    #: "conservative" means predictable, not clever.
    _KEYWORD_CAPABILITIES: tuple[tuple[str, str], ...] = (
        ("test", "testing"),
        ("debug", "debugging"),
        ("fix", "debugging"),
        ("research", "web_research"),
        ("search the web", "web_research"),
        ("look up", "web_research"),
        ("message", "messaging"),
        ("send", "messaging"),
        ("notify", "messaging"),
        ("remind", "scheduling"),
        ("schedule", "scheduling"),
        ("cron", "scheduling"),
        ("memory", "memory_boundary"),
        ("remember", "memory_boundary"),
        ("device", "device_interaction"),
        ("camera", "device_interaction"),
        ("screen", "device_interaction"),
        ("diagram", "visualization"),
        ("visualize", "visualization"),
        ("chart", "visualization"),
        ("peer", "lantern_interoperability"),
        ("handshake", "lantern_interoperability"),
        ("another lantern", "lantern_interoperability"),
        ("governance", "core_governance"),
        ("self-modify", "core_governance"),
        ("architecture", "core_governance"),
        ("search", "code_search"),
        ("find", "code_search"),
        ("code", "software_engineering"),
        ("implement", "software_engineering"),
        ("build", "software_engineering"),
        ("write", "software_engineering"),
    )

    def __init__(self, registry: CapabilityRegistry):
        self._registry = registry

    def decompose(self, objective: str) -> list[PlanStep]:
        """Best-effort, deterministic decomposition of an objective into
        capability/worker steps. Order of matches in _KEYWORD_CAPABILITIES
        is preserved; duplicate capabilities are collapsed to their first
        match. An objective matching nothing yields an empty plan rather
        than guessing."""
        lowered = objective.lower()
        seen: set[str] = set()
        steps: list[PlanStep] = []
        for keyword, capability_name in self._KEYWORD_CAPABILITIES:
            if keyword not in lowered:
                continue
            if capability_name in seen:
                continue
            descriptor = self._registry.get(capability_name)
            if descriptor is None:
                continue
            seen.add(capability_name)
            steps.append(PlanStep(
                capability=capability_name,
                worker=descriptor.worker,
                reason=f"objective mentions '{keyword}'",
            ))
        return steps

    def plan(self, objective: str) -> list[DelegationRecord]:
        """Produce bounded DelegationRecords, each in REQUESTED status.

        Every produced record's authority_scope/allowed_capabilities are
        derived strictly from the matched capability's own
        authority_requirements -- the planner never grants more than the
        capability descriptor itself declares, and never grants any
        NEVER_EXTERNALLY_EXPOSE authority without also setting
        requires_human_confirmation.
        """
        records: list[DelegationRecord] = []
        for step in self.decompose(objective):
            descriptor = self._registry.get(step.capability)
            if descriptor is None:
                continue
            forbidden = NEVER_EXTERNALLY_EXPOSE - descriptor.authority_requirements
            needs_confirmation = bool(
                descriptor.authority_requirements & NEVER_EXTERNALLY_EXPOSE
            ) or not descriptor.trusted
            records.append(DelegationRecord(
                objective=objective,
                capability=step.capability,
                worker=step.worker,
                authority_scope=descriptor.authority_requirements,
                allowed_capabilities=frozenset({step.capability}),
                forbidden_authorities=forbidden,
                expected_outputs=descriptor.returns,
                verification_policy=descriptor.verification_policy,
                provenance_requirements=(
                    ("provenance_tag",) if not descriptor.local_only else ()
                ),
                confirmation_requirements=(
                    (step.reason,) if needs_confirmation else ()
                ),
                requires_human_confirmation=needs_confirmation,
            ))
        return records


# ==========================================================
# Default capability registry
# ==========================================================

def create_default_registry() -> CapabilityRegistry:
    """Map currently available local hands into Lantern-oriented capabilities.

    This is intentionally a classification layer over existing tools and
    local interfaces, not a runtime tool invoker.
    """
    registry = CapabilityRegistry()

    registry.register(CapabilityDescriptor(
        name="software_engineering",
        purpose="read, edit, and shape code locally",
        kind="execution",
        worker="CODER",
        local_only=True,
        trusted=True,
        exposes_via_mcp=True,
        authority_requirements=frozenset({"capability_selection"}),
        returns=("code changes", "diffs", "artifacts"),
        limitations=("does not verify correctness by itself",),
        underlying_tools=("read", "write", "edit", "apply_patch"),
        verification_policy=VerificationPolicy(
            method="tests / lint / build / diff inspection",
            evidence_required=("test_result", "diff", "build_status"),
        ),
    ))

    registry.register(CapabilityDescriptor(
        name="code_search",
        purpose="inspect codebases and locate implementation points",
        kind="analysis",
        worker="CODER",
        local_only=True,
        trusted=True,
        exposes_via_mcp=True,
        authority_requirements=frozenset({"capability_selection"}),
        returns=("matches", "locations", "inventory"),
        limitations=("findings still need evaluation",),
        underlying_tools=("read", "exec"),
        verification_policy=VerificationPolicy(
            method="source inspection / location verification",
            evidence_required=("file_path", "line_range"),
        ),
    ))

    registry.register(CapabilityDescriptor(
        name="testing",
        purpose="run checks to verify claimed implementation results",
        kind="verification",
        worker="TESTER",
        local_only=True,
        trusted=True,
        exposes_via_mcp=True,
        authority_requirements=frozenset({"capability_selection"}),
        returns=("test results", "pass/fail evidence"),
        limitations=("passing tests do not prove global correctness",),
        underlying_tools=("exec", "process"),
        verification_policy=VerificationPolicy(
            method="independent re-run of the test/build command",
            evidence_required=("exit_code", "test_output"),
        ),
    ))

    registry.register(CapabilityDescriptor(
        name="debugging",
        purpose="inspect failures and runtime behavior",
        kind="analysis",
        worker="TESTER",
        local_only=True,
        trusted=True,
        exposes_via_mcp=True,
        authority_requirements=frozenset({"capability_selection"}),
        returns=("failure analysis", "trace evidence"),
        limitations=("may require separate reproduction/verification",),
        underlying_tools=("exec", "process", "read"),
        verification_policy=VerificationPolicy(
            method="reproduction of the failure plus post-fix re-run",
            evidence_required=("reproduction_steps", "post_fix_result"),
        ),
    ))

    registry.register(CapabilityDescriptor(
        name="web_research",
        purpose="gather external information for comparison and evaluation",
        kind="research",
        worker="RESEARCHER",
        local_only=False,
        trusted=False,
        exposes_via_mcp=True,
        authority_requirements=frozenset({"capability_selection", "provenance"}),
        sensitive_inputs=frozenset({"query_context"}),
        returns=("sources", "summaries", "extracted pages"),
        limitations=("external claims are not automatically true",),
        underlying_tools=("web_search", "web_fetch", "browser"),
        verification_policy=VerificationPolicy(
            method="provenance / source triangulation",
            evidence_required=("source_url", "independent_corroboration"),
        ),
    ))

    registry.register(CapabilityDescriptor(
        name="messaging",
        purpose="send or relay communications",
        kind="communication",
        worker="COMMUNICATOR",
        local_only=False,
        trusted=False,
        exposes_via_mcp=True,
        authority_requirements=frozenset({"permissions", "sensitive_data_access", "capability_selection"}),
        sensitive_inputs=frozenset({"recipient", "message_body"}),
        returns=("delivery result",),
        limitations=("external side effect; often requires human confirmation",),
        underlying_tools=("message", "sessions_send"),
        verification_policy=VerificationPolicy(
            method="authorization plus delivery evidence",
            evidence_required=("send_confirmation", "delivery_status"),
        ),
    ))

    registry.register(CapabilityDescriptor(
        name="scheduling",
        purpose="set reminders and recurring work",
        kind="automation",
        worker="SCHEDULER",
        local_only=True,
        trusted=True,
        exposes_via_mcp=True,
        authority_requirements=frozenset({"permissions", "delegation_policy", "capability_selection"}),
        returns=("job definitions", "run history"),
        limitations=("scheduled action is not immediate completion",),
        underlying_tools=("cron",),
        verification_policy=VerificationPolicy(
            method="created-job verification / readable schedule",
            evidence_required=("job_id", "schedule_definition"),
        ),
    ))

    registry.register(CapabilityDescriptor(
        name="memory_boundary",
        purpose="propose, confirm, retract, and audit Lantern's separate self-improving memory",
        kind="memory",
        worker="ORGANIZER",
        local_only=True,
        trusted=True,
        exposes_via_mcp=False,
        authority_requirements=frozenset({"memory_mutation", "confirmation_requirements", "retractions", "provenance"}),
        returns=("pending decisions", "memory records", "audit summaries"),
        limitations=("no caller can self-authorize mutation",),
        underlying_tools=("internal:self_improving_interface_boundary",),
        verification_policy=VerificationPolicy(
            method="Primary Lantern authorization record inspection",
            evidence_required=("authorization_record_id", "pending_ledger_state"),
        ),
    ))

    registry.register(CapabilityDescriptor(
        name="device_interaction",
        purpose="inspect or operate paired devices and nodes",
        kind="device",
        worker="DEVICE_OPERATOR",
        local_only=False,
        trusted=False,
        exposes_via_mcp=True,
        authority_requirements=frozenset({"permissions", "sensitive_data_access", "capability_selection"}),
        sensitive_inputs=frozenset({"camera", "screen", "location", "notifications"}),
        returns=("snapshots", "device state", "notification actions"),
        limitations=("touches real devices and potentially private data",),
        underlying_tools=("nodes", "file_fetch", "file_write"),
        verification_policy=VerificationPolicy(
            method="resulting state / artifact verification",
            evidence_required=("artifact_reference", "device_state_snapshot"),
        ),
    ))

    registry.register(CapabilityDescriptor(
        name="visualization",
        purpose="render diagrams, canvas views, or other structured visual outputs",
        kind="visualization",
        worker="VISUALIZER",
        local_only=True,
        trusted=True,
        exposes_via_mcp=True,
        authority_requirements=frozenset({"capability_selection"}),
        returns=("diagrams", "canvas snapshots", "visual artifacts"),
        limitations=("representation is not verification",),
        underlying_tools=("canvas",),
        verification_policy=VerificationPolicy(
            method="rendered artifact inspection",
            evidence_required=("artifact_reference",),
        ),
    ))

    registry.register(CapabilityDescriptor(
        name="lantern_interoperability",
        purpose="discover, verify, and authorize bounded collaboration with other Lantern instances",
        kind="interoperability",
        worker="NETWORK_INTEROPERABILITY",
        local_only=False,
        trusted=False,
        exposes_via_mcp=False,
        authority_requirements=frozenset({"identity", "permissions", "provenance", "delegation_policy"}),
        returns=("contact verification", "capability negotiation", "authorization decisions"),
        limitations=("shared capability is not trust or authority",),
        underlying_tools=(
            "lantern.handshake",
            "lantern.verified_contact",
            "lantern.capability_authorization",
        ),
        verification_policy=VerificationPolicy(
            method="handshake / identity / authorization / provenance verification",
            evidence_required=(
                "handshake_response",
                "identity_verification_result",
                "authorization_decision",
            ),
        ),
    ))

    registry.register(CapabilityDescriptor(
        name="core_governance",
        purpose="describe protected sovereign boundaries Lantern must keep",
        kind="governance",
        worker="AUDITOR",
        local_only=True,
        trusted=True,
        exposes_via_mcp=False,
        authority_requirements=frozenset({
            "core_rules",
            "self_modification",
            "identity",
            "permissions",
            "memory_mutation",
        }),
        returns=("governance findings", "boundary violations"),
        limitations=("proposal may describe change, but cannot self-apply it",),
        underlying_tools=("lantern.architecture", "lantern.capability_authorization"),
        verification_policy=VerificationPolicy(
            method="architecture referee comparison (observe/compare/report only)",
            evidence_required=("architecture_report", "drift_findings"),
        ),
    ))

    return registry
