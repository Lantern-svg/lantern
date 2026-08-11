from lantern.orchestration import (
    CORE_WORKERS,
    DELEGATION_STATUSES,
    NEVER_EXTERNALLY_EXPOSE,
    PROTECTED_AUTHORITIES,
    PROVENANCE_CLASSES,
    REMOTE_PROVENANCE_CLASSES,
    SELF_CHANGE_STATUSES,
    TERMINAL_DELEGATION_STATUSES,
    CapabilityDescriptor,
    CapabilityRegistry,
    DelegationRecord,
    OrchestrationPlanner,
    ProvenanceTag,
    SelfChangeProposal,
    VerificationPolicy,
    create_default_registry,
)


# ============================================================
# Capability registry (unchanged v0.1 behavior)
# ============================================================

def test_default_registry_contains_lantern_oriented_capabilities():
    registry = create_default_registry()
    summary = registry.summary()

    assert summary["count"] >= 10
    names = {item["name"] for item in summary["capabilities"]}
    assert "software_engineering" in names
    assert "memory_boundary" in names
    assert "lantern_interoperability" in names


def test_core_workers_remain_small_and_specialized_workers_are_not_core():
    assert CORE_WORKERS == (
        "OBSERVER",
        "EVALUATOR",
        "ORGANIZER",
        "AUDITOR",
    )
    assert "CODER" not in CORE_WORKERS
    assert "RESEARCHER" not in CORE_WORKERS


def test_registry_discovery_can_filter_by_worker_and_mcp_exposure():
    registry = create_default_registry()

    coder_caps = registry.discover(worker="CODER")
    assert {item.name for item in coder_caps} == {"software_engineering", "code_search"}

    non_mcp_caps = registry.discover(mcp_ready=False)
    assert {item.name for item in non_mcp_caps} >= {"memory_boundary", "lantern_interoperability", "core_governance"}


def test_sensitive_authority_capabilities_are_not_externally_exposable():
    registry = create_default_registry()

    memory_cap = registry.get("memory_boundary")
    interoperability_cap = registry.get("lantern_interoperability")
    governance_cap = registry.get("core_governance")

    assert memory_cap is not None
    assert interoperability_cap is not None
    assert governance_cap is not None

    assert memory_cap.externally_exposable is False
    assert governance_cap.externally_exposable is False
    assert memory_cap.requires_protected_authority is True
    assert governance_cap.requires_protected_authority is True
    assert "memory_mutation" in memory_cap.authority_requirements
    assert "core_rules" in governance_cap.authority_requirements


def test_messaging_and_device_interaction_require_protected_authority_even_if_discoverable():
    registry = create_default_registry()

    messaging = registry.get("messaging")
    device = registry.get("device_interaction")

    assert messaging is not None
    assert device is not None
    assert messaging.requires_protected_authority is True
    assert device.requires_protected_authority is True
    assert "permissions" in messaging.authority_requirements
    assert "sensitive_data_access" in device.authority_requirements


def test_custom_capability_can_be_registered_without_rewriting_core_logic():
    registry = CapabilityRegistry()
    registry.register(CapabilityDescriptor(
        name="custom_future_capability",
        purpose="future extension",
        kind="research",
        worker="RESEARCHER",
        local_only=False,
        trusted=False,
        exposes_via_mcp=True,
    ))

    item = registry.get("custom_future_capability")
    assert item is not None
    assert item.name == "custom_future_capability"
    assert item.externally_exposable is True


# ============================================================
# Verification policies (new in v0.2)
# ============================================================

def test_every_default_capability_has_a_verification_policy():
    registry = create_default_registry()
    for capability in registry.all():
        assert capability.verification_policy is not None, capability.name
        assert capability.verification_policy.evidence_required


def test_verification_policy_is_capability_specific():
    registry = create_default_registry()

    software_policy = registry.get("software_engineering").verification_policy
    research_policy = registry.get("web_research").verification_policy
    messaging_policy = registry.get("messaging").verification_policy

    assert software_policy.method != research_policy.method
    assert research_policy.method != messaging_policy.method
    assert "test" in software_policy.method or "diff" in software_policy.method
    assert "provenance" in research_policy.method or "triangulation" in research_policy.method


def test_worker_claim_sufficient_can_never_be_true():
    try:
        VerificationPolicy(
            method="worker self-report",
            evidence_required=(),
            worker_claim_sufficient=True,
        )
        assert False, "expected ValueError"
    except ValueError as exc:
        assert "sufficient" in str(exc)


def test_verification_policy_defaults_to_not_worker_sufficient():
    policy = VerificationPolicy(method="independent check", evidence_required=("evidence",))
    assert policy.worker_claim_sufficient is False


# ============================================================
# Delegation lifecycle: RETURNED != VERIFIED, FAILED terminal
# ============================================================

def test_delegation_record_lifecycle_does_not_collapse_returned_into_verified():
    record = DelegationRecord(
        objective="Research, implement, and test a feature",
        capability="software_engineering",
        worker="CODER",
        authority_scope=frozenset({"capability_selection"}),
        allowed_information=frozenset({"repo_context"}),
    )

    assert record.status == "REQUESTED"

    delegated = record.transition("DELEGATED")
    executing = delegated.transition("EXECUTING")
    returned = executing.transition("RETURNED", result_summary="worker claims success")

    assert returned.status == "RETURNED"
    assert returned.result_summary == "worker claims success"
    assert returned.verification_summary is None

    verified = returned.transition("VERIFIED", verification_summary="tests passed independently")
    assert verified.status == "VERIFIED"
    assert verified.result_summary == "worker claims success"
    assert verified.verification_summary == "tests passed independently"


def test_delegation_can_require_human_confirmation():
    record = DelegationRecord(
        objective="Send a message to an external recipient",
        capability="messaging",
        worker="COMMUNICATOR",
    )

    gated = record.transition(
        "REQUIRES_HUMAN_CONFIRMATION",
        result_summary="draft ready",
        requires_human_confirmation=True,
    )

    assert gated.status == "REQUIRES_HUMAN_CONFIRMATION"
    assert gated.requires_human_confirmation is True
    assert gated.result_summary == "draft ready"


def test_unknown_delegation_status_is_rejected():
    record = DelegationRecord(
        objective="x",
        capability="testing",
        worker="TESTER",
    )

    try:
        record.transition("DONE")
        assert False, "expected ValueError"
    except ValueError as exc:
        assert "unknown delegation status" in str(exc)


def test_failed_is_terminal_unless_a_new_delegation_is_created():
    record = DelegationRecord(objective="x", capability="testing", worker="TESTER")
    failed = record.transition("DELEGATED").transition("EXECUTING").transition("FAILED", result_summary="crashed")

    assert failed.status == "FAILED"
    assert failed.status in TERMINAL_DELEGATION_STATUSES
    # There is no retry_from_failed() -- a retry must be a NEW DelegationRecord.
    assert not hasattr(failed, "retry_from_failed")
    # Nothing stops a caller from *creating a new record*, but that is a
    # distinct object with a distinct id, not a mutation of the failed one.
    retry = DelegationRecord(objective="x", capability="testing", worker="TESTER")
    assert retry.id != failed.id
    assert retry.status == "REQUESTED"


def test_verified_is_terminal_too():
    assert "VERIFIED" in TERMINAL_DELEGATION_STATUSES
    assert "RETURNED" not in TERMINAL_DELEGATION_STATUSES
    assert "REQUIRES_HUMAN_CONFIRMATION" not in TERMINAL_DELEGATION_STATUSES


# ============================================================
# Scoped delegation visibility
# ============================================================

def test_delegation_authority_scope_cannot_overlap_forbidden_authorities():
    try:
        DelegationRecord(
            objective="x",
            capability="messaging",
            worker="COMMUNICATOR",
            authority_scope=frozenset({"permissions"}),
            forbidden_authorities=frozenset({"permissions"}),
        )
        assert False, "expected ValueError"
    except ValueError as exc:
        assert "overlap" in str(exc)


def test_delegation_record_exposes_full_scope_via_to_dict():
    policy = VerificationPolicy(method="check", evidence_required=("evidence",))
    record = DelegationRecord(
        objective="do a bounded thing",
        capability="testing",
        worker="TESTER",
        authority_scope=frozenset({"capability_selection"}),
        allowed_capabilities=frozenset({"testing"}),
        forbidden_authorities=frozenset({"memory_mutation"}),
        expected_outputs=("test results",),
        verification_policy=policy,
        provenance_requirements=("provenance_tag",),
        confirmation_requirements=(),
    )

    payload = record.to_dict()
    assert payload["allowed_capabilities"] == ["testing"]
    assert payload["forbidden_authorities"] == ["memory_mutation"]
    assert payload["expected_outputs"] == ["test results"]
    assert payload["verification_policy"]["method"] == "check"
    assert payload["provenance_requirements"] == ["provenance_tag"]


def test_capability_discovery_does_not_imply_authorization_for_delegation():
    registry = create_default_registry()
    # Discovering a capability exists says nothing about whether a given
    # delegation is allowed to use it -- allowed_capabilities is set
    # explicitly and independently.
    discovered = registry.discover(kind="communication")
    assert any(item.name == "messaging" for item in discovered)

    record = DelegationRecord(
        objective="research only, no messaging",
        capability="web_research",
        worker="RESEARCHER",
        allowed_capabilities=frozenset({"web_research"}),
    )
    assert "messaging" not in record.allowed_capabilities


# ============================================================
# Conservative planner
# ============================================================

def test_planner_never_produces_more_authority_than_the_capability_declares():
    registry = create_default_registry()
    planner = OrchestrationPlanner(registry)

    plan = planner.plan("please research the topic and then message me the summary")
    capabilities_used = {record.capability for record in plan}
    assert "web_research" in capabilities_used
    assert "messaging" in capabilities_used

    for record in plan:
        descriptor = registry.get(record.capability)
        assert record.authority_scope == descriptor.authority_requirements
        assert record.status == "REQUESTED"


def test_planner_flags_confirmation_for_never_externally_exposed_or_untrusted_capabilities():
    registry = create_default_registry()
    planner = OrchestrationPlanner(registry)

    plan = planner.plan("please remember this and also message the team")
    by_capability = {record.capability: record for record in plan}

    assert by_capability["memory_boundary"].requires_human_confirmation is True
    assert by_capability["messaging"].requires_human_confirmation is True


def test_planner_produces_no_steps_for_unmatched_objective():
    registry = create_default_registry()
    planner = OrchestrationPlanner(registry)

    plan = planner.plan("xyzzy plugh nothing matches this")
    assert plan == []


def test_planner_never_executes_a_tool_directly():
    import inspect
    from lantern import orchestration as module

    source = inspect.getsource(module.OrchestrationPlanner)
    for forbidden in ("subprocess", "os.system", "exec(", "importlib.import_module"):
        assert forbidden not in source


def test_planner_deduplicates_repeated_keyword_matches():
    registry = create_default_registry()
    planner = OrchestrationPlanner(registry)

    plan = planner.plan("write code, build code, implement code")
    capabilities_used = [record.capability for record in plan]
    assert capabilities_used.count("software_engineering") == 1


# ============================================================
# Provenance
# ============================================================

def test_remote_observation_provenance_is_retained_not_rewritten():
    tag = ProvenanceTag(source_class="REMOTE_LANTERN", identifier="peer-node-1")
    assert tag.is_remote is True

    record = DelegationRecord(objective="x", capability="lantern_interoperability", worker="NETWORK_INTEROPERABILITY")
    returned = record.transition("DELEGATED").transition("EXECUTING").transition(
        "RETURNED", result_provenance=tag, result_summary="peer responded"
    )

    # Nothing here converts REMOTE_LANTERN into a LOCAL_* class.
    assert returned.result_provenance.source_class == "REMOTE_LANTERN"
    assert returned.result_provenance.is_remote is True


def test_local_provenance_classes_are_not_remote():
    for local_class in ("LOCAL_TOOL", "LOCAL_WORKER", "LOCAL_LANTERN"):
        tag = ProvenanceTag(source_class=local_class, identifier="x")
        assert tag.is_remote is False
        assert local_class not in REMOTE_PROVENANCE_CLASSES


def test_unknown_provenance_class_is_rejected():
    try:
        ProvenanceTag(source_class="NOT_A_REAL_CLASS", identifier="x")
        assert False, "expected ValueError"
    except ValueError as exc:
        assert "unknown provenance class" in str(exc)


def test_all_provenance_classes_are_covered_by_remote_or_local_semantics():
    for provenance_class in PROVENANCE_CLASSES:
        tag = ProvenanceTag(source_class=provenance_class, identifier="x")
        expected_remote = provenance_class in REMOTE_PROVENANCE_CLASSES
        assert tag.is_remote == expected_remote


# ============================================================
# Self-modification stays proposal/review territory
# ============================================================

def test_self_change_proposal_has_no_apply_method():
    proposal = SelfChangeProposal(
        reason="orchestration planner keyword table is incomplete",
        evidence=("objective X produced an empty plan",),
        proposed_change="add keyword mapping for X",
        expected_effect="planner recognizes X-shaped objectives",
        risks=("keyword collision with existing mapping",),
        verification_plan="add a regression test for the new keyword",
        authority_required=frozenset({"self_modification"}),
    )

    assert proposal.status == "PROPOSED"
    assert not hasattr(proposal, "apply")
    assert not hasattr(proposal, "apply_change")


def test_self_change_proposal_status_transitions_are_explicit():
    proposal = SelfChangeProposal(
        reason="r", evidence=(), proposed_change="c", expected_effect="e",
        risks=(), verification_plan="v",
    )
    reviewed = proposal.with_status("REVIEWED")
    approved = reviewed.with_status("APPROVED")

    assert proposal.status == "PROPOSED"
    assert reviewed.status == "REVIEWED"
    assert approved.status == "APPROVED"


def test_self_change_proposal_rejects_unknown_status():
    proposal = SelfChangeProposal(
        reason="r", evidence=(), proposed_change="c", expected_effect="e",
        risks=(), verification_plan="v",
    )
    try:
        proposal.with_status("DONE")
        assert False, "expected ValueError"
    except ValueError as exc:
        assert "unknown self-change status" in str(exc)


# ============================================================
# Frozen authority / lifecycle vocabulary
# ============================================================

def test_frozen_authority_sets_capture_sovereign_boundaries():
    assert "memory_mutation" in PROTECTED_AUTHORITIES
    assert "self_modification" in PROTECTED_AUTHORITIES
    assert "core_rules" in NEVER_EXTERNALLY_EXPOSE
    assert "delegation_policy" in NEVER_EXTERNALLY_EXPOSE
    assert set(NEVER_EXTERNALLY_EXPOSE).issubset(set(PROTECTED_AUTHORITIES))


def test_delegation_statuses_include_verification_and_human_gate_states():
    assert DELEGATION_STATUSES == (
        "REQUESTED",
        "DELEGATED",
        "EXECUTING",
        "RETURNED",
        "VERIFIED",
        "FAILED",
        "REQUIRES_HUMAN_CONFIRMATION",
    )


def test_self_change_statuses_never_include_an_applied_state():
    # There is deliberately no "APPLIED" status -- self-change remains
    # proposal/review territory; an actual code change is a separate,
    # explicitly authorized act outside this module's vocabulary.
    assert "APPLIED" not in SELF_CHANGE_STATUSES
    assert SELF_CHANGE_STATUSES == ("PROPOSED", "REVIEWED", "APPROVED", "REJECTED")
