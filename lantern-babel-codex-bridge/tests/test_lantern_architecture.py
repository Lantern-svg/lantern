from lantern.architecture import (
    ArchitectureRegistry,
    CANONICAL_CAPABILITIES,
    CANONICAL_MESSAGE_REQUIREMENTS,
    REGISTRY,
    architecture_status,
)
from lantern.compatibility import DEFAULT_CAPABILITIES
from lantern.router import MESSAGE_REQUIREMENTS


def test_clean_architecture_has_no_drift_errors():
    report = REGISTRY.validate()

    assert report.healthy
    assert report.errors() == []


def test_open_decisions_are_preserved_as_info_findings():
    report = REGISTRY.validate()

    assert report.by_category("open_decision")
    assert all(item.severity == "INFO" for item in report.by_category("open_decision"))


def test_independent_reference_is_not_live_capability_dict():
    assert CANONICAL_CAPABILITIES is not DEFAULT_CAPABILITIES
    assert dict(CANONICAL_CAPABILITIES) == dict(DEFAULT_CAPABILITIES)


def test_modifying_live_copy_does_not_mutate_reference_state():
    live_copy = dict(DEFAULT_CAPABILITIES)
    live_copy["codex_update"] = True

    assert CANONICAL_CAPABILITIES["codex_update"] is False
    assert REGISTRY.capabilities["codex_update"] is False


def test_compare_capabilities_clean_live_state_has_no_findings():
    findings = REGISTRY.compare_capabilities(DEFAULT_CAPABILITIES)

    assert findings == []


def test_capability_value_changed_is_detected():
    live = dict(DEFAULT_CAPABILITIES)
    live["codex_update"] = True

    findings = REGISTRY.compare_capabilities(live)

    assert any(
        f.category == "capability_drift"
        and f.name == "codex_update"
        and f.expected is False
        and f.actual is True
        for f in findings
    )


def test_capability_missing_is_detected():
    live = dict(DEFAULT_CAPABILITIES)
    del live["handshake"]

    findings = REGISTRY.compare_capabilities(live)

    assert any(
        f.category == "capability_drift"
        and f.name == "handshake"
        and f.actual == "<missing>"
        for f in findings
    )


def test_unexpected_capability_is_detected():
    live = dict(DEFAULT_CAPABILITIES)
    live["unexpected_capability"] = True

    findings = REGISTRY.compare_capabilities(live)

    assert any(
        f.category == "capability_drift"
        and f.name == "unexpected_capability"
        and f.expected == "<unexpected>"
        for f in findings
    )


def test_codex_update_true_is_trust_invariant_violation():
    registry = ArchitectureRegistry()
    registry.capabilities["codex_update"] = True

    findings = registry.validate_reference()

    assert any(
        f.category == "trust_invariant"
        and f.name == "codex_update"
        and f.expected is False
        and f.actual is True
        for f in findings
    )


def test_remote_confidence_mutation_enabled_is_trust_invariant_violation():
    registry = ArchitectureRegistry()
    registry.constants["remote_confidence_mutates_local_belief"] = True

    findings = registry.validate_reference()

    assert any(
        f.category == "trust_invariant"
        and f.name == "remote_confidence_mutates_local_belief"
        and f.expected is False
        and f.actual is True
        for f in findings
    )


def test_message_requirement_changed_is_detected():
    live = dict(MESSAGE_REQUIREMENTS)
    live["EVIDENCE_REQUEST"] = "evidence_exchange"

    findings = REGISTRY.compare_message_requirements(live)

    assert any(
        f.category == "message_requirement_drift"
        and f.name == "EVIDENCE_REQUEST"
        and f.expected == CANONICAL_MESSAGE_REQUIREMENTS["EVIDENCE_REQUEST"]
        and f.actual == "evidence_exchange"
        for f in findings
    )


def test_unexpected_message_requirement_is_detected():
    live = dict(MESSAGE_REQUIREMENTS)
    live["UNEXPECTED_MESSAGE"] = "belief_query"

    findings = REGISTRY.compare_message_requirements(live)

    assert any(
        f.category == "message_requirement_drift"
        and f.name == "UNEXPECTED_MESSAGE"
        and f.expected == "<unexpected>"
        for f in findings
    )


def test_architecture_referee_does_not_mutate_live_system():
    capabilities_before = dict(DEFAULT_CAPABILITIES)
    message_requirements_before = dict(MESSAGE_REQUIREMENTS)

    report = REGISTRY.validate()

    assert report.healthy
    assert dict(DEFAULT_CAPABILITIES) == capabilities_before
    assert dict(MESSAGE_REQUIREMENTS) == message_requirements_before


def test_reference_and_live_fingerprints_exist():
    report = REGISTRY.validate()

    assert report.reference_fingerprint
    assert report.live_fingerprint


def test_snapshot_contains_live_and_reference_fingerprints():
    snapshot = REGISTRY.snapshot()

    assert snapshot["fingerprint"] == REGISTRY.fingerprint()
    assert snapshot["live_fingerprint"]
    assert "live_state" in snapshot


def test_architecture_status_matches_registry_health():
    status = architecture_status()
    report = REGISTRY.validate()

    assert status["healthy"] == report.healthy
    assert status["reference_fingerprint"] == report.reference_fingerprint
    assert status["live_fingerprint"] == report.live_fingerprint


def test_message_allowed_reflects_reference_state():
    assert REGISTRY.message_allowed("OBSERVATION_SHARE") is True
    assert REGISTRY.message_allowed("CODEX_UPDATE") is False


def test_unknown_message_type_is_not_allowed():
    assert REGISTRY.message_allowed("NOT_A_REAL_MESSAGE") is False


def test_watermark_trust_invariants_present_in_frozen_constants():
    assert REGISTRY.constants["watermark_mutates_belief"] is False
    assert REGISTRY.constants["watermark_bypasses_capability_gate"] is False


def test_watermark_mutates_belief_true_is_trust_invariant_violation():
    registry = ArchitectureRegistry()
    registry.constants["watermark_mutates_belief"] = True

    findings = registry.validate_reference()

    assert any(
        f.category == "trust_invariant"
        and f.name == "watermark_mutates_belief"
        and f.expected is False
        and f.actual is True
        for f in findings
    )


def test_watermark_bypasses_capability_gate_true_is_trust_invariant_violation():
    registry = ArchitectureRegistry()
    registry.constants["watermark_bypasses_capability_gate"] = True

    findings = registry.validate_reference()

    assert any(
        f.category == "trust_invariant"
        and f.name == "watermark_bypasses_capability_gate"
        and f.expected is False
        and f.actual is True
        for f in findings
    )


def test_live_watermark_constants_match_reference_by_source_inspection():
    # The referee derives these two constants from the live
    # continuity module by source inspection (inspect_live_system),
    # not by importing the module's own claim about itself. A clean
    # live system must therefore report zero constant drift for
    # these two names.
    live_state, _ = REGISTRY.inspect_live_system()

    assert live_state["constants"]["watermark_mutates_belief"] is False
    assert live_state["constants"]["watermark_bypasses_capability_gate"] is False


def test_referee_does_not_import_continuity_as_its_own_expected_value():
    # Independence guarantee for the new module, mirroring the
    # existing capability-independence test: the referee's reference
    # constants dict must not be the live module's own state -- it's
    # a separate literal that inspect_live_system() checks against.
    from lantern import continuity as continuity_module

    assert REGISTRY.constants is not vars(continuity_module)

