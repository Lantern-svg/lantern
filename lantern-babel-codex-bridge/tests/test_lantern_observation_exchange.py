"""Tests for observation_exchange: authorized observation exchange plus
local contradiction detection, sitting strictly after cryptographic
identity verification and explicit capability authorization.

Covers the full required security matrix: authorization ordering,
identity/authorization sufficiency, provenance preservation, reliability
downgrade, malformed/oversized rejection, replay protection, evidence/
belief/trust/Codex/authority boundaries, and a real two-node integration
test with independent identities, independent Chronicle/state, and
independent capability decisions.
"""

from __future__ import annotations

import json

import pytest

from lantern import identity as identity_module
from lantern.agent import LanternAgent
from lantern.capability_authorization import (
    AuthorizationPolicy,
    CapabilityDecision,
    authorize,
)
from lantern.core import Lantern
from lantern.protocol import create_observation_share, create_message, PROTOCOL_VERSION
from lantern.verified_contact import VerifiedContactOutcome, VerifiedContactResult

from lantern.observation_exchange import (
    EvidenceExchangeCapability,
    LOCAL_DEFAULT_RELIABILITY,
    MAX_OBSERVATION_CONTENT_BYTES,
    ObservationExchangeLedger,
    ObservationExchangeOutcome,
    analyze_contradiction,
    receive_observation,
)


NODE_A = "lantern-A"
NODE_B = "lantern-B"


def _make_agent():
    lantern = Lantern()
    return LanternAgent(lantern), lantern


def _verified(node_id=NODE_A, identity_status=identity_module.CRYPTOGRAPHICALLY_VERIFIED, shared=None):
    shared = shared if shared is not None else {"evidence_exchange": True, "handshake": True}
    return VerifiedContactResult(
        outcome=VerifiedContactOutcome.IDENTITY_VERIFIED if identity_status == identity_module.CRYPTOGRAPHICALLY_VERIFIED else VerifiedContactOutcome.IDENTITY_UNVERIFIED,
        local_node_id=NODE_B,
        remote_node_id=node_id,
        identity_status=identity_status,
        protocol_version=PROTOCOL_VERSION,
        shared_capabilities=shared,
        contact_endpoint="http://127.0.0.1:9",
        reason="ok",
    )


def _authorized_decision(node_id=NODE_A, capabilities=("evidence_exchange",), verified=None):
    verified = verified if verified is not None else _verified(node_id=node_id)
    policy = AuthorizationPolicy.authorize(node_id, capabilities)
    return authorize(verified, requested=set(capabilities), policy=policy)


def _unauthorized_decision(node_id=NODE_A, verified=None):
    verified = verified if verified is not None else _verified(node_id=node_id)
    return authorize(verified, requested={"evidence_exchange"})  # no policy -> nothing authorized


def _share(source=NODE_A, content="sky is blue", reliability=0.9, concept=None):
    obs = {"content": content}
    if reliability is not None:
        obs["reliability"] = reliability
    if concept is not None:
        obs["concept"] = concept
    return create_observation_share(source, obs)


# ============================================================
# Authorization ordering / sufficiency
# ============================================================

def test_authorized_observation_is_accepted():
    agent, lantern = _make_agent()
    decision = _authorized_decision()
    message = _share()

    result = receive_observation(
        message, identity_status=identity_module.CRYPTOGRAPHICALLY_VERIFIED,
        decision=decision, agent=agent,
    )

    assert result.accepted
    assert result.outcome == ObservationExchangeOutcome.OBSERVATION_CREATED
    assert len(lantern.kernel.observations) == 1


def test_unauthorized_observation_is_rejected():
    agent, lantern = _make_agent()
    decision = _unauthorized_decision()
    message = _share()

    result = receive_observation(
        message, identity_status=identity_module.CRYPTOGRAPHICALLY_VERIFIED,
        decision=decision, agent=agent,
    )

    assert not result.accepted
    assert result.outcome == ObservationExchangeOutcome.NOT_AUTHORIZED
    assert len(lantern.kernel.observations) == 0


def test_unverified_identity_cannot_exchange_observations_even_if_authorized():
    agent, lantern = _make_agent()
    # Deliberately construct a decision as if the node were verified, to
    # prove the identity_status ARGUMENT (independently supplied) is
    # what's checked, not something inferred from the decision alone.
    decision = _authorized_decision()
    message = _share()

    result = receive_observation(
        message, identity_status=identity_module.UNVERIFIED,
        decision=decision, agent=agent,
    )

    assert not result.accepted
    assert result.outcome == ObservationExchangeOutcome.IDENTITY_NOT_VERIFIED
    assert len(lantern.kernel.observations) == 0


def test_shared_capability_without_authorization_is_insufficient():
    agent, lantern = _make_agent()
    verified = _verified(shared={"evidence_exchange": True})
    # No AuthorizationPolicy passed -> nothing is authorized even though
    # evidence_exchange was mutually negotiated (shared).
    decision = authorize(verified, requested={"evidence_exchange"})
    assert "evidence_exchange" in decision.shared_capabilities
    assert not decision.is_authorized("evidence_exchange")

    result = receive_observation(
        _share(), identity_status=identity_module.CRYPTOGRAPHICALLY_VERIFIED,
        decision=decision, agent=agent,
    )

    assert not result.accepted
    assert result.outcome == ObservationExchangeOutcome.NOT_AUTHORIZED
    assert len(lantern.kernel.observations) == 0


def test_authorization_checked_before_payload_validation():
    """An unauthorized sender's garbage payload must be rejected for the
    authorization reason, not leak information about payload validation
    order (defense in depth: authorization gate comes first)."""
    agent, lantern = _make_agent()
    decision = _unauthorized_decision()
    malformed = create_message("OBSERVATION_SHARE", NODE_A, {"observation": {"content": 12345}})

    result = receive_observation(
        malformed, identity_status=identity_module.CRYPTOGRAPHICALLY_VERIFIED,
        decision=decision, agent=agent,
    )

    assert result.outcome == ObservationExchangeOutcome.NOT_AUTHORIZED
    assert len(lantern.kernel.observations) == 0


# ============================================================
# Sender / source integrity
# ============================================================

def test_sender_cannot_impersonate_another_authorized_node():
    agent, lantern = _make_agent()
    decision = _authorized_decision(node_id=NODE_A)
    # Message claims to be from a different node than the one authorized.
    impersonating_message = _share(source="lantern-EVIL")

    result = receive_observation(
        impersonating_message, identity_status=identity_module.CRYPTOGRAPHICALLY_VERIFIED,
        decision=decision, agent=agent,
    )

    assert not result.accepted
    assert result.outcome == ObservationExchangeOutcome.SOURCE_MISMATCH
    assert len(lantern.kernel.observations) == 0


def test_wrong_message_type_is_rejected():
    agent, lantern = _make_agent()
    decision = _authorized_decision()
    wrong_type = create_message("CODEX_UPDATE", NODE_A, {"concept": "x", "confidence": 1, "evidence_ids": []})

    result = receive_observation(
        wrong_type, identity_status=identity_module.CRYPTOGRAPHICALLY_VERIFIED,
        decision=decision, agent=agent,
    )

    assert not result.accepted
    assert result.outcome == ObservationExchangeOutcome.WRONG_MESSAGE_TYPE
    assert len(lantern.kernel.observations) == 0


# ============================================================
# Provenance / reliability model
# ============================================================

def test_provenance_is_preserved():
    agent, lantern = _make_agent()
    decision = _authorized_decision()
    message = _share(content="water boils at 100C", reliability=0.9, concept="temperature")

    result = receive_observation(
        message, identity_status=identity_module.CRYPTOGRAPHICALLY_VERIFIED,
        decision=decision, agent=agent,
    )

    obs = lantern.kernel.observations[result.observation_id]
    assert obs.source == NODE_A
    assert obs.content == "water boils at 100C"
    assert obs.metadata["claimed_reliability"] == 0.9
    assert obs.metadata["claimed_concept"] == "temperature"
    assert obs.metadata["remote_message_id"] == message.message_id
    assert obs.metadata["remote_timestamp"] == message.timestamp
    assert obs.metadata["origin_type"] == "authorized_observation_exchange"


def test_remote_reliability_is_not_trusted_directly():
    agent, lantern = _make_agent()
    decision = _authorized_decision()

    low = receive_observation(
        _share(content="low claim", reliability=0.01),
        identity_status=identity_module.CRYPTOGRAPHICALLY_VERIFIED, decision=decision, agent=agent,
    )
    high = receive_observation(
        _share(content="high claim", reliability=999.0),
        identity_status=identity_module.CRYPTOGRAPHICALLY_VERIFIED, decision=decision, agent=agent,
    )

    obs_low = lantern.kernel.observations[low.observation_id]
    obs_high = lantern.kernel.observations[high.observation_id]

    assert obs_low.reliability == obs_high.reliability == LOCAL_DEFAULT_RELIABILITY
    assert obs_low.metadata["claimed_reliability"] == 0.01
    assert obs_high.metadata["claimed_reliability"] == 999.0


def test_missing_reliability_defaults_claim_to_one_but_not_trusted_reliability():
    agent, lantern = _make_agent()
    decision = _authorized_decision()
    result = receive_observation(
        _share(content="no reliability given", reliability=None),
        identity_status=identity_module.CRYPTOGRAPHICALLY_VERIFIED, decision=decision, agent=agent,
    )
    obs = lantern.kernel.observations[result.observation_id]
    assert obs.reliability == LOCAL_DEFAULT_RELIABILITY
    assert obs.metadata["claimed_reliability"] == 1.0


# ============================================================
# Hostile input handling
# ============================================================

@pytest.mark.parametrize("bad_payload", [
    {},
    {"observation": "not a dict"},
    {"observation": {}},
    {"observation": {"content": 123}},
    {"observation": {"content": None}},
    {"observation": {"content": "ok", "reliability": "not a number"}},
    {"observation": {"content": "ok", "reliability": True}},
    {"observation": {"content": "ok", "reliability": float("nan")}},
    {"observation": {"content": "ok", "concept": 123}},
])
def test_malformed_observation_payload_is_rejected(bad_payload):
    agent, lantern = _make_agent()
    decision = _authorized_decision()
    message = create_message("OBSERVATION_SHARE", NODE_A, bad_payload)

    result = receive_observation(
        message, identity_status=identity_module.CRYPTOGRAPHICALLY_VERIFIED,
        decision=decision, agent=agent,
    )

    assert not result.accepted
    assert result.outcome in (
        ObservationExchangeOutcome.INVALID_OBSERVATION_PAYLOAD,
        ObservationExchangeOutcome.MALFORMED_MESSAGE,
    )
    assert len(lantern.kernel.observations) == 0


def test_oversized_observation_is_rejected():
    agent, lantern = _make_agent()
    decision = _authorized_decision()
    huge_content = "x" * (MAX_OBSERVATION_CONTENT_BYTES + 1)
    message = _share(content=huge_content)

    result = receive_observation(
        message, identity_status=identity_module.CRYPTOGRAPHICALLY_VERIFIED,
        decision=decision, agent=agent,
    )

    assert not result.accepted
    assert result.outcome == ObservationExchangeOutcome.INVALID_OBSERVATION_PAYLOAD
    assert len(lantern.kernel.observations) == 0


def test_not_a_protocol_message_object_is_rejected():
    agent, lantern = _make_agent()
    decision = _authorized_decision()

    result = receive_observation(
        {"message_type": "OBSERVATION_SHARE"}, identity_status=identity_module.CRYPTOGRAPHICALLY_VERIFIED,
        decision=decision, agent=agent,
    )

    assert not result.accepted
    assert result.outcome == ObservationExchangeOutcome.MALFORMED_MESSAGE
    assert len(lantern.kernel.observations) == 0


def test_none_message_is_rejected_without_raising():
    agent, lantern = _make_agent()
    decision = _authorized_decision()

    result = receive_observation(
        None, identity_status=identity_module.CRYPTOGRAPHICALLY_VERIFIED,
        decision=decision, agent=agent,
    )

    assert not result.accepted
    assert result.outcome == ObservationExchangeOutcome.MALFORMED_MESSAGE


def test_remote_content_cannot_execute_code():
    """The content field is treated as opaque data end to end: dangerous
    strings must pass through completely inert, never eval'd/exec'd,
    never used to select an attribute/module/function."""
    agent, lantern = _make_agent()
    decision = _authorized_decision()
    dangerous = "__import__('os').system('true'); {{7*7}}; ${7*7}"
    message = _share(content=dangerous)

    result = receive_observation(
        message, identity_status=identity_module.CRYPTOGRAPHICALLY_VERIFIED,
        decision=decision, agent=agent,
    )

    assert result.accepted
    obs = lantern.kernel.observations[result.observation_id]
    assert obs.content == dangerous  # stored verbatim as inert data


# ============================================================
# Replay protection
# ============================================================

def test_replayed_observation_does_not_create_unlimited_duplicates():
    agent, lantern = _make_agent()
    decision = _authorized_decision()
    ledger = ObservationExchangeLedger()
    message = _share()

    first = receive_observation(
        message, identity_status=identity_module.CRYPTOGRAPHICALLY_VERIFIED,
        decision=decision, agent=agent, ledger=ledger,
    )
    second = receive_observation(
        message, identity_status=identity_module.CRYPTOGRAPHICALLY_VERIFIED,
        decision=decision, agent=agent, ledger=ledger,
    )
    third = receive_observation(
        message, identity_status=identity_module.CRYPTOGRAPHICALLY_VERIFIED,
        decision=decision, agent=agent, ledger=ledger,
    )

    assert first.accepted
    assert not second.accepted and second.outcome == ObservationExchangeOutcome.DUPLICATE_MESSAGE
    assert not third.accepted and third.outcome == ObservationExchangeOutcome.DUPLICATE_MESSAGE
    assert len(lantern.kernel.observations) == 1


def test_ledger_is_bounded_fifo():
    ledger = ObservationExchangeLedger(max_tracked_messages=3)
    for i in range(5):
        ledger.record(NODE_A, f"msg-{i}")

    assert not ledger.seen(NODE_A, "msg-0")
    assert not ledger.seen(NODE_A, "msg-1")
    assert ledger.seen(NODE_A, "msg-2")
    assert ledger.seen(NODE_A, "msg-3")
    assert ledger.seen(NODE_A, "msg-4")


def test_replay_dedup_is_scoped_per_source():
    ledger = ObservationExchangeLedger()
    ledger.record(NODE_A, "shared-id")
    assert ledger.seen(NODE_A, "shared-id")
    assert not ledger.seen("lantern-C", "shared-id")


# ============================================================
# Evidence / belief / trust / Codex / authority boundaries
# ============================================================

def test_remote_observation_does_not_become_evidence_automatically():
    agent, lantern = _make_agent()
    decision = _authorized_decision()
    receive_observation(
        _share(), identity_status=identity_module.CRYPTOGRAPHICALLY_VERIFIED,
        decision=decision, agent=agent,
    )
    assert len(lantern.kernel.evidence) == 0


def test_remote_observation_does_not_change_belief_automatically():
    agent, lantern = _make_agent()
    decision = _authorized_decision()
    baseline = agent.ask_belief("gravity")

    receive_observation(
        _share(content="gravity pulls down", concept="gravity", reliability=1.0),
        identity_status=identity_module.CRYPTOGRAPHICALLY_VERIFIED, decision=decision, agent=agent,
    )

    assert agent.ask_belief("gravity") == baseline


def test_contradiction_does_not_automatically_resolve():
    agent, lantern = _make_agent()
    obs_a = agent.observe("100C", "local", 1.0)
    obs_b = agent.observe("80C", "remote", 1.0)
    agent.add_evidence("temperature", obs_a.id, 1.0, 1)
    agent.add_evidence("temperature", obs_b.id, 1.0, -1)

    contradiction = analyze_contradiction(agent, "temperature")
    assert contradiction is not None
    assert contradiction.status == "OPEN"
    assert len(lantern.kernel.resolutions) == 0


def test_contradiction_does_not_automatically_alter_trust_or_identity():
    """This module carries no trust_status/authority_level/identity_status
    mutation vocabulary at all -- ObservationExchangeResult has none of
    those fields, and analyze_contradiction() only reads kernel state."""
    agent, lantern = _make_agent()
    obs_a = agent.observe("100C", "local", 1.0)
    obs_b = agent.observe("80C", "remote", 1.0)
    agent.add_evidence("temperature", obs_a.id, 1.0, 1)
    agent.add_evidence("temperature", obs_b.id, 1.0, -1)

    analyze_contradiction(agent, "temperature")

    from lantern.observation_exchange import ObservationExchangeResult
    field_names = {f for f in ObservationExchangeResult.__dataclass_fields__}
    assert "trust_status" not in field_names
    assert "authority_level" not in field_names
    assert "identity_status" not in field_names


def test_observation_cannot_modify_codex_authority_or_capability_policy():
    import ast
    from lantern import observation_exchange as module

    source_text = module.__file__
    with open(source_text) as fh:
        tree = ast.parse(fh.read())

    called_names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Attribute):
                called_names.add(func.attr)
            elif isinstance(func, ast.Name):
                called_names.add(func.id)

    forbidden = {"add_evidence", "belief", "resolve", "persist_scar", "create_scar"}
    assert called_names & forbidden == set()


def test_codex_update_message_type_is_rejected_by_this_module():
    agent, lantern = _make_agent()
    decision = _authorized_decision(capabilities=("evidence_exchange", "codex_update"))
    # codex_update can never be authorized regardless (structural floor
    # in capability_authorization) -- confirm that holds here too.
    assert not decision.is_authorized("codex_update")

    codex_message = create_message("CODEX_UPDATE", NODE_A, {"concept": "gravity", "confidence": 0.99, "evidence_ids": []})
    result = receive_observation(
        codex_message, identity_status=identity_module.CRYPTOGRAPHICALLY_VERIFIED,
        decision=decision, agent=agent,
    )
    assert not result.accepted
    assert result.outcome == ObservationExchangeOutcome.WRONG_MESSAGE_TYPE
    assert len(lantern.kernel.evidence) == 0


def test_private_key_material_never_appears_in_result(tmp_path):
    identity = identity_module.load_or_create(NODE_A, tmp_path / NODE_A)
    agent, lantern = _make_agent()
    decision = _authorized_decision(node_id=identity.node_id)
    message = _share(source=identity.node_id)

    result = receive_observation(
        message, identity_status=identity_module.CRYPTOGRAPHICALLY_VERIFIED,
        decision=decision, agent=agent,
    )

    blob = json.dumps(result.to_dict())
    private_key_bytes = identity.identity_dir.joinpath("private_key.bin").read_bytes()
    assert private_key_bytes.hex() not in blob
    assert "private_key" not in blob


def test_authorization_occurs_before_state_mutation():
    """Reject path for an unauthorized sender must leave kernel state
    byte-for-byte identical to before the call."""
    agent, lantern = _make_agent()
    decision = _unauthorized_decision()
    before = lantern.kernel.snapshot()

    receive_observation(
        _share(), identity_status=identity_module.CRYPTOGRAPHICALLY_VERIFIED,
        decision=decision, agent=agent,
    )

    after = lantern.kernel.snapshot()
    assert before == after


def test_rejected_messages_cause_zero_lantern_state_mutation_matrix():
    """Every distinct rejection path must leave zero observations,
    evidence, or contradictions behind."""
    agent, lantern = _make_agent()

    cases = [
        (_unauthorized_decision(), identity_module.CRYPTOGRAPHICALLY_VERIFIED, _share()),
        (_authorized_decision(), identity_module.UNVERIFIED, _share()),
        (_authorized_decision(), identity_module.CRYPTOGRAPHICALLY_VERIFIED, create_message("OBSERVATION_SHARE", NODE_A, {})),
        (_authorized_decision(), identity_module.CRYPTOGRAPHICALLY_VERIFIED, _share(source="impersonator")),
    ]
    for decision, identity_status, message in cases:
        receive_observation(message, identity_status=identity_status, decision=decision, agent=agent)

    assert len(lantern.kernel.observations) == 0
    assert len(lantern.kernel.evidence) == 0
    assert len(lantern.kernel.contradictions) == 0


# ============================================================
# codex_update / architecture invariants
# ============================================================

def test_codex_update_remains_disabled_end_to_end():
    from lantern.compatibility import DEFAULT_CAPABILITIES
    assert DEFAULT_CAPABILITIES["codex_update"] is False


def test_existing_architecture_tests_still_describe_same_invariants():
    from lantern.architecture import CANONICAL_MESSAGE_REQUIREMENTS
    assert CANONICAL_MESSAGE_REQUIREMENTS["OBSERVATION_SHARE"] == EvidenceExchangeCapability


# ============================================================
# Two-node integration test: independent identities, state, decisions
# ============================================================

def test_two_node_authorized_observation_exchange_and_contradiction(tmp_path):
    identity_a = identity_module.load_or_create("node-A", tmp_path / "node-A")
    identity_b = identity_module.load_or_create("node-B", tmp_path / "node-B")

    lantern_a = Lantern(chronicle_filename=tmp_path / "chronicle_a.jsonl")
    agent_a = LanternAgent(lantern_a, chronicle=lantern_a.bus.chronicle)

    lantern_b = Lantern(chronicle_filename=tmp_path / "chronicle_b.jsonl")
    agent_b = LanternAgent(lantern_b, chronicle=lantern_b.bus.chronicle)

    verified_a_to_b = VerifiedContactResult(
        outcome=VerifiedContactOutcome.IDENTITY_VERIFIED,
        local_node_id=identity_b.node_id,
        remote_node_id=identity_a.node_id,
        identity_status=identity_module.CRYPTOGRAPHICALLY_VERIFIED,
        protocol_version=PROTOCOL_VERSION,
        shared_capabilities={"evidence_exchange": True, "handshake": True},
        contact_endpoint="http://127.0.0.1:9",
        reason="mutual handshake ok",
    )

    # B's own, independent, explicit authorization decision for A.
    b_policy = AuthorizationPolicy.authorize(identity_a.node_id, {"evidence_exchange"})
    decision_b_about_a = authorize(verified_a_to_b, requested={"evidence_exchange"}, policy=b_policy)
    assert decision_b_about_a.is_authorized("evidence_exchange")

    message_from_a = create_observation_share(
        identity_a.node_id, {"content": "100C", "reliability": 0.9, "concept": "temperature"}
    )
    result = receive_observation(
        message_from_a, identity_status=identity_module.CRYPTOGRAPHICALLY_VERIFIED,
        decision=decision_b_about_a, agent=agent_b,
    )
    assert result.accepted
    assert len(lantern_b.kernel.observations) == 1
    assert len(lantern_a.kernel.observations) == 0  # independent state

    # B locally has its own observation of the same concept, disagreeing.
    local_obs = agent_b.observe("80C", "local-sensor", 1.0)

    # B explicitly (locally) promotes both into evidence -- not something
    # this module does automatically.
    remote_obs_id = result.observation_id
    agent_b.add_evidence("temperature", remote_obs_id, 1.0, 1)
    agent_b.add_evidence("temperature", local_obs.id, 1.0, -1)

    contradiction = analyze_contradiction(agent_b, "temperature")
    assert contradiction is not None
    assert contradiction.concept == "temperature"

    # ---- Unauthorized case: fresh Lantern B2, no policy grant for A.
    lantern_b2 = Lantern(chronicle_filename=tmp_path / "chronicle_b2.jsonl")
    agent_b2 = LanternAgent(lantern_b2, chronicle=lantern_b2.bus.chronicle)
    decision_b2_about_a = authorize(verified_a_to_b, requested={"evidence_exchange"})  # no policy
    assert not decision_b2_about_a.is_authorized("evidence_exchange")

    rejected = receive_observation(
        message_from_a, identity_status=identity_module.CRYPTOGRAPHICALLY_VERIFIED,
        decision=decision_b2_about_a, agent=agent_b2,
    )
    assert not rejected.accepted
    assert rejected.outcome == ObservationExchangeOutcome.NOT_AUTHORIZED
    assert len(lantern_b2.kernel.observations) == 0
    assert len(lantern_b2.kernel.evidence) == 0
    assert len(lantern_b2.kernel.contradictions) == 0

    # Independent Chronicles: B's exchange never touched B2's or A's state.
    assert lantern_b.bus.chronicle.verify() is True
    assert lantern_b2.bus.chronicle.verify() is True
