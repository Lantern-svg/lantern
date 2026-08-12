import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

from lantern_harness.permission_authority import (
    PermissionAuthority,
    AlignmentResult,
    CAPABILITY_CATEGORIES,
    NEVER_INHERITS,
    RESULT_ACT,
    RESULT_STOP_AND_REASSESS,
    RESULT_ASK_OPERATOR,
    RESULT_REFUSE,
    GRANT_STATUS_ACTIVE,
    GRANT_STATUS_REVOKED,
)


def _passed(**overrides):
    defaults = dict(
        verdict="PASSED",
        considered=("stated objective", "established boundaries"),
        supporting_evidence=("matches prior authorized pattern",),
        contradictions=(),
        foreseeable_consequences=("local file changes only",),
        introduces_new_commitment=False,
        reasoning="within established scope and consistent with stated intent",
    )
    defaults.update(overrides)
    return AlignmentResult(**defaults)


def _failed(**overrides):
    defaults = dict(
        verdict="FAILED",
        considered=("stated objective",),
        supporting_evidence=(),
        contradictions=("contradicts standing boundary",),
        foreseeable_consequences=("could expose private data",),
        introduces_new_commitment=True,
        reasoning="contradicts a standing operator boundary",
    )
    defaults.update(overrides)
    return AlignmentResult(**defaults)


# ---- grant() / revoke() -----------------------------------------------

def test_grant_requires_explicit_granting_authority():
    authority = PermissionAuthority()
    with pytest.raises(ValueError):
        authority.grant(
            capability="local_file_modification",
            scope="lantern-harness/ project directory",
            boundary="read/write only inside lantern-harness/",
            granting_authority="",
            provenance="user directive 2026-08-12",
        )


def test_permission_authority_cannot_self_grant():
    """Nothing in this module can construct a PermissionGrant without a
    caller-supplied granting_authority -- grep-level guarantee: the only
    way to get a PermissionGrant into _grants is through grant(), and
    grant() raises on an empty/whitespace-only string, including values
    like 'self' would still be a caller choice, never a default."""
    authority = PermissionAuthority()
    with pytest.raises(ValueError):
        authority.grant(
            capability="local_file_modification",
            scope="x",
            boundary="",
            granting_authority="   ",
            provenance="x",
        )
    assert authority.all_grants() == ()


def test_grant_rejects_unknown_capability_category():
    authority = PermissionAuthority()
    with pytest.raises(ValueError):
        authority.grant(
            capability="not_a_real_category",
            scope="x",
            boundary="",
            granting_authority="operator",
            provenance="x",
        )


def test_grant_rejects_empty_scope():
    authority = PermissionAuthority()
    with pytest.raises(ValueError):
        authority.grant(
            capability="local_file_modification",
            scope="",
            boundary="",
            granting_authority="operator",
            provenance="x",
        )


def test_grant_and_active_grants_round_trip():
    authority = PermissionAuthority()
    grant = authority.grant(
        capability="local_file_modification",
        scope="lantern-harness/ project directory",
        boundary="read/write only inside lantern-harness/",
        granting_authority="operator",
        provenance="user directive 2026-08-12",
    )
    assert grant.status == GRANT_STATUS_ACTIVE
    active = authority.active_grants()
    assert len(active) == 1
    assert active[0].capability == "local_file_modification"


def test_revoke_requires_explicit_granting_authority():
    authority = PermissionAuthority()
    authority.grant(
        capability="run_tests", scope="lantern-harness/ test suite", boundary="",
        granting_authority="operator", provenance="x",
    )
    with pytest.raises(ValueError):
        authority.revoke("run_tests", "")


def test_revoke_marks_grant_revoked_and_it_stops_matching():
    authority = PermissionAuthority()
    authority.grant(
        capability="run_tests", scope="lantern-harness/ test suite", boundary="",
        granting_authority="operator", provenance="x",
    )
    count = authority.revoke("run_tests", "operator")
    assert count == 1
    assert authority.active_grants() == ()
    all_grants = authority.all_grants()
    assert len(all_grants) == 1
    assert all_grants[0].status == GRANT_STATUS_REVOKED


def test_expired_grant_does_not_match_at_or_after_expiry_step():
    authority = PermissionAuthority()
    authority.grant(
        capability="run_tests", scope="x", boundary="", granting_authority="operator",
        provenance="x", granted_at_step=1, expires_at_step=10,
    )
    assert len(authority.active_grants(current_step=5)) == 1
    assert len(authority.active_grants(current_step=10)) == 0
    assert len(authority.active_grants(current_step=15)) == 0


# ---- check() combination rule ------------------------------------------

def test_authorized_and_aligned_is_act():
    authority = PermissionAuthority()
    authority.grant(
        capability="local_file_modification", scope="lantern-harness/", boundary="",
        granting_authority="operator", provenance="x",
    )
    result = authority.check(
        action="edit README.md",
        capability="local_file_modification",
        alignment=_passed(),
    )
    assert result.result == RESULT_ACT
    assert result.authorized is True


def test_authorized_but_misaligned_is_stop_and_reassess():
    authority = PermissionAuthority()
    authority.grant(
        capability="local_file_modification", scope="lantern-harness/", boundary="",
        granting_authority="operator", provenance="x",
    )
    result = authority.check(
        action="edit README.md to remove a safety boundary",
        capability="local_file_modification",
        alignment=_failed(),
    )
    assert result.result == RESULT_STOP_AND_REASSESS
    assert result.authorized is True
    assert any("did not pass alignment" in n for n in result.notes)


def test_aligned_but_not_authorized_is_ask_operator():
    authority = PermissionAuthority()
    result = authority.check(
        action="publish lantern-harness to PyPI",
        capability="software_release_publication",
        alignment=_passed(reasoning="consistent with stated promotion objective"),
    )
    assert result.result == RESULT_ASK_OPERATOR
    assert result.authorized is False


def test_neither_authorized_nor_aligned_is_refuse():
    authority = PermissionAuthority()
    result = authority.check(
        action="send funds from an unconfigured wallet",
        capability="wallet_or_payment_authority",
        alignment=_failed(),
    )
    assert result.result == RESULT_REFUSE
    assert result.authorized is False


def test_unknown_capability_is_flagged_as_new_capability_and_cannot_be_authorized():
    authority = PermissionAuthority()
    result = authority.check(
        action="do something entirely unforeseen",
        capability="some_capability_never_defined",
        alignment=_passed(),
    )
    assert result.is_new_capability is True
    assert result.authorized is False
    assert result.result == RESULT_ASK_OPERATOR


# ---- non-inheritance across capability categories -----------------------

def test_file_modification_grant_does_not_authorize_external_communication():
    authority = PermissionAuthority()
    authority.grant(
        capability="local_file_modification", scope="lantern-harness/", boundary="",
        granting_authority="operator", provenance="x",
    )
    result = authority.check(
        action="message a third party about this project",
        capability="external_communication",
        alignment=_passed(),
    )
    assert result.authorized is False
    assert result.result == RESULT_ASK_OPERATOR


def test_release_publication_grant_does_not_authorize_wallet_or_payment_authority():
    authority = PermissionAuthority()
    authority.grant(
        capability="software_release_publication", scope="lantern-harness on PyPI", boundary="",
        granting_authority="operator", provenance="x",
    )
    result = authority.check(
        action="use a configured wallet to pay a facilitator fee",
        capability="wallet_or_payment_authority",
        alignment=_passed(),
    )
    assert result.authorized is False


def test_one_mcp_server_authorization_does_not_authorize_unrelated_external_service():
    authority = PermissionAuthority()
    authority.grant(
        capability="external_network_service", scope="register lantern-harness-mcp with Odysseus", boundary="",
        granting_authority="operator", provenance="x",
    )
    result = authority.check(
        action="connect to an unrelated external service X",
        capability="credential_use",
        alignment=_passed(),
    )
    assert result.authorized is False


def test_never_inherits_categories_are_flagged_even_when_unauthorized():
    authority = PermissionAuthority()
    for capability in NEVER_INHERITS:
        result = authority.check(
            action=f"attempt {capability}",
            capability=capability,
            alignment=_passed(),
        )
        assert result.authorized is False
        assert result.result == RESULT_ASK_OPERATOR
        assert any("never implied" in n for n in result.notes)


# ---- transfer / no persistence -------------------------------------------

def test_permission_authority_grants_do_not_persist_across_instances():
    """Simulates what a 'transferred' Peacemaker looks like: a brand new
    PermissionAuthority() (as a new process would construct) has zero
    grants, even though a previous instance in the same test run had
    some. This is the module-level guarantee that authority never
    silently travels with transferred state (directive section 9)."""
    first = PermissionAuthority()
    first.grant(
        capability="local_file_modification", scope="lantern-harness/", boundary="",
        granting_authority="operator", provenance="x",
    )
    assert len(first.active_grants()) == 1

    second = PermissionAuthority()
    assert second.active_grants() == ()
    assert second.all_grants() == ()


def test_a_previously_authorized_capability_in_one_authority_instance_is_unauthorized_in_a_fresh_one():
    first = PermissionAuthority()
    first.grant(
        capability="software_release_publication", scope="lantern-harness on PyPI", boundary="",
        granting_authority="previous-operator", provenance="prior session",
    )
    receiving_operator_authority = PermissionAuthority()
    result = receiving_operator_authority.check(
        action="publish lantern-harness to PyPI",
        capability="software_release_publication",
        alignment=_passed(),
    )
    assert result.authorized is False
    assert result.result == RESULT_ASK_OPERATOR


# ---- formatting matches the directive's specified shape ------------------

def test_new_authority_request_format_matches_directive_example_shape():
    authority = PermissionAuthority()
    result = authority.check(
        action="Publish Lantern/Peacemaker package to PyPI.",
        capability="software_release_publication",
        alignment=_passed(reasoning="Consistent with stated promotion objective"),
        external_effects=["public package index entry created"],
    )
    text = authority.format_new_authority_request(result, purpose="Public distribution.")
    assert text.startswith("NEW AUTHORITY REQUEST")
    assert "Action:" in text
    assert "Purpose:" in text
    assert "Existing authorization:" in text
    assert "Alignment:" in text
    assert "Required authority:" in text
    assert "External effects:" in text
    assert "Result:\n  ASK OPERATOR." in text


def test_action_complete_format_is_informational_not_a_request():
    authority = PermissionAuthority()
    authority.grant(
        capability="software_release_publication", scope="lantern-harness on PyPI", boundary="",
        granting_authority="operator", provenance="x",
    )
    result = authority.check(
        action="Published approved release.",
        capability="software_release_publication",
        alignment=_passed(),
        external_effects=["Public package updated."],
    )
    text = authority.format_action_complete(result, outcome="Success.")
    assert text.startswith("PEACEMAKER ACTION COMPLETE")
    assert "No new authority requested." in text
    assert "ASK OPERATOR" not in text


# ---- auditability (to_dict answers every question in directive section 10) --

def test_check_result_to_dict_answers_auditability_questions():
    authority = PermissionAuthority()
    authority.grant(
        capability="local_file_modification", scope="lantern-harness/", boundary="",
        granting_authority="operator", provenance="user directive 2026-08-12",
    )
    result = authority.check(
        action="edit README.md",
        capability="local_file_modification",
        alignment=_passed(),
        external_effects=[],
    )
    payload = result.to_dict()
    # what did it do / why
    assert payload["action"] == "edit README.md"
    assert payload["alignment"]["reasoning"]
    # what evidence supported it
    assert isinstance(payload["alignment"]["supporting_evidence"], list)
    # what alignment evaluation occurred
    assert payload["alignment"]["verdict"] == "PASSED"
    # what authorization permitted it / what scope
    assert payload["matched_grant"]["scope"] == "lantern-harness/"
    assert payload["matched_grant"]["granting_authority"] == "operator"
    # what external effect resulted
    assert payload["external_effects"] == []
    # did it introduce a new capability
    assert payload["is_new_capability"] is False
    # combined result
    assert payload["result"] == RESULT_ACT
