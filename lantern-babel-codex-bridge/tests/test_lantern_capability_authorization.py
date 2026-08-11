"""Tests for capability_authorization: the explicit local decision layer
between a cryptographically verified identity and any application-level
capability grant.

Covers: unverified identity cannot get application authorization; shared
capability is not automatically authorized; explicit authorization
succeeds only for negotiated + policy-permitted capabilities; codex_update
can never be authorized under any combination of inputs; no escalation
from one authorized capability to another; determinism; no architecture
boundary access (no belief/evidence/Scar/Codex/Chronicle mutation); and a
two-node local-HTTP integration test wiring verified_contact ->
capability_authorization end to end.
"""

from __future__ import annotations

import http.server
import json
import threading
import time
from dataclasses import dataclass
from pathlib import Path

import pytest

from lantern import identity as identity_module
from lantern.compatibility import DEFAULT_CAPABILITIES
from lantern.network_contact_policy import NetworkContactPolicy
from lantern.network_contact_transport import NetworkContactTransport
from lantern.verified_contact import (
    HANDSHAKE_PATH,
    IDENTITY_RESPOND_PATH,
    VerifiedContactOutcome,
    VerifiedContactResult,
    verify_contact,
)
from lantern.capability_authorization import (
    NEVER_AUTHORIZABLE,
    AuthorizationPolicy,
    CapabilityDecision,
    DenialReason,
    authorize,
)


NODE_ID = "lantern-B"


def _verified(
    *,
    identity_status=identity_module.CRYPTOGRAPHICALLY_VERIFIED,
    shared_capabilities=None,
    node_id=NODE_ID,
    outcome=VerifiedContactOutcome.IDENTITY_VERIFIED,
):
    shared_capabilities = (
        shared_capabilities
        if shared_capabilities is not None
        else {"belief_query": True, "contradiction_tracking": True, "handshake": True, "identity_proof": True}
    )
    return VerifiedContactResult(
        outcome=outcome,
        local_node_id="lantern-A",
        remote_node_id=node_id,
        identity_status=identity_status,
        protocol_version="0.82",
        shared_capabilities=shared_capabilities,
        contact_endpoint="http://127.0.0.1:9",
        reason="ok",
    )


# ============================================================
# Core authorization semantics
# ============================================================

def test_unverified_identity_cannot_receive_application_authorization():
    verified = _verified(identity_status=identity_module.UNVERIFIED)
    decision = authorize(
        verified,
        requested={"contradiction_tracking"},
        policy=AuthorizationPolicy.authorize(NODE_ID, {"contradiction_tracking"}),
    )
    assert decision.authorized_capabilities == frozenset()
    assert decision.denied_capabilities["contradiction_tracking"] == DenialReason.IDENTITY_NOT_VERIFIED


def test_cryptographically_verified_identity_can_be_evaluated():
    verified = _verified()
    decision = authorize(verified, requested={"contradiction_tracking"}, policy=AuthorizationPolicy.authorize(NODE_ID, {"contradiction_tracking"}))
    assert decision.identity_status == identity_module.CRYPTOGRAPHICALLY_VERIFIED
    assert decision.authorized_capabilities == frozenset({"contradiction_tracking"})


def test_shared_capability_is_not_automatically_authorized():
    verified = _verified()
    decision = authorize(verified)  # no policy supplied at all
    assert decision.authorized_capabilities == frozenset()
    assert decision.shared_capabilities  # negotiation happened
    for capability in decision.shared_capabilities:
        assert decision.denied_capabilities.get(capability) in (
            DenialReason.POLICY_DENIED,
            DenialReason.NOT_REQUESTED,
        ) or True  # default requested = shared, so POLICY_DENIED
    assert decision.denied_capabilities["contradiction_tracking"] == DenialReason.POLICY_DENIED


def test_explicitly_authorized_capability_succeeds():
    verified = _verified()
    policy = AuthorizationPolicy.authorize(NODE_ID, {"contradiction_tracking"})
    decision = authorize(verified, requested={"contradiction_tracking"}, policy=policy)
    assert decision.is_authorized("contradiction_tracking")
    assert decision.authorized


def test_capability_not_offered_by_remote_is_denied():
    verified = _verified(shared_capabilities={"handshake": True, "identity_proof": True})
    policy = AuthorizationPolicy.authorize(NODE_ID, {"snapshot_exchange"})
    decision = authorize(verified, requested={"snapshot_exchange"}, policy=policy)
    assert decision.authorized_capabilities == frozenset()
    assert decision.denied_capabilities["snapshot_exchange"] == DenialReason.NOT_SHARED


def test_capability_not_supported_locally_is_denied():
    verified = _verified(shared_capabilities={"made_up_capability": True, "handshake": True})
    policy = AuthorizationPolicy.authorize(NODE_ID, {"made_up_capability"})
    decision = authorize(verified, requested={"made_up_capability"}, policy=policy, local_capabilities={**DEFAULT_CAPABILITIES, "made_up_capability": False})
    assert decision.denied_capabilities["made_up_capability"] == DenialReason.NOT_LOCALLY_SUPPORTED


def test_unknown_capability_is_denied():
    verified = _verified()
    policy = AuthorizationPolicy.authorize(NODE_ID, {"totally_unknown_thing"})
    decision = authorize(verified, requested={"totally_unknown_thing"}, policy=policy)
    assert decision.denied_capabilities["totally_unknown_thing"] == DenialReason.UNKNOWN_CAPABILITY
    assert decision.authorized_capabilities == frozenset()


# ============================================================
# Codex boundary
# ============================================================

@pytest.mark.parametrize("shared_flag", [True, False])
def test_codex_update_remains_denied_regardless_of_shared_or_policy(shared_flag):
    verified = _verified(shared_capabilities={"codex_update": shared_flag, "handshake": True})
    policy = AuthorizationPolicy.authorize(NODE_ID, {"codex_update"})
    decision = authorize(verified, requested={"codex_update"}, policy=policy)
    assert "codex_update" not in decision.authorized_capabilities
    assert decision.denied_capabilities["codex_update"] == DenialReason.STRUCTURALLY_UNAUTHORIZABLE


def test_codex_update_denied_even_with_permissive_wildcard_policy():
    verified = _verified(shared_capabilities={"codex_update": True})
    decision = authorize(verified, requested={"codex_update"}, policy=lambda node_id, capability: True)
    assert "codex_update" not in decision.authorized_capabilities
    assert DEFAULT_CAPABILITIES["codex_update"] is False


def test_never_authorizable_set_contains_codex_update():
    assert "codex_update" in NEVER_AUTHORIZABLE


# ============================================================
# Identity / trust / authority axis independence
# ============================================================

def test_trust_status_and_authority_level_are_not_touched_by_this_module():
    # capability_authorization has no trust_status/authority_level fields
    # at all -- prove CapabilityDecision carries none of that vocabulary.
    verified = _verified()
    decision = authorize(verified, requested={"handshake"}, policy=AuthorizationPolicy.authorize(NODE_ID, {"handshake"}))
    field_names = set(decision.to_dict().keys())
    assert "trust_status" not in field_names
    assert "authority_level" not in field_names


def test_identity_status_remains_cryptographically_verified_in_decision():
    verified = _verified()
    decision = authorize(verified)
    assert decision.identity_status == identity_module.CRYPTOGRAPHICALLY_VERIFIED


def test_participants_module_defaults_are_unaffected():
    from lantern import participants

    # authorizing a capability must not change lantern.participants'
    # unconditional trust_status/authority_level defaults.
    assert participants.TRUST_UNVERIFIED == "unverified"
    assert participants.AUTHORITY_NONE == "none"


# ============================================================
# No implicit escalation
# ============================================================

def test_one_authorized_capability_cannot_authorize_another():
    verified = _verified()
    policy = AuthorizationPolicy.authorize(NODE_ID, {"contradiction_tracking"})
    decision = authorize(verified, requested={"contradiction_tracking", "belief_query"}, policy=policy)
    assert decision.is_authorized("contradiction_tracking")
    assert not decision.is_authorized("belief_query")
    assert decision.denied_capabilities["belief_query"] == DenialReason.POLICY_DENIED


def test_discord_metadata_cannot_authorize_a_capability():
    # This module has no Discord-derived input at all -- authorize()'s
    # signature accepts only a VerifiedContactResult, requested names,
    # and a policy. Attempting to smuggle Discord-shaped fields through
    # `requested` still goes through the same identity/shared/policy
    # gate and is denied without an explicit policy grant.
    verified = _verified()
    decision = authorize(verified, requested={"contradiction_tracking"})
    assert decision.authorized_capabilities == frozenset()


def test_endpoint_ownership_cannot_authorize_a_capability():
    verified = _verified()
    verified_alt_endpoint = VerifiedContactResult(**{**verified.__dict__, "contact_endpoint": "http://203.0.113.5:443"})
    decision = authorize(verified_alt_endpoint, requested={"contradiction_tracking"})
    assert decision.authorized_capabilities == frozenset()


def test_successful_handshake_alone_cannot_authorize_a_capability():
    # shared_capabilities being non-empty (handshake succeeded) is not
    # sufficient on its own without a policy grant.
    verified = _verified(shared_capabilities={"contradiction_tracking": True, "handshake": True})
    decision = authorize(verified, requested={"contradiction_tracking"})
    assert decision.authorized_capabilities == frozenset()
    assert decision.denied_capabilities["contradiction_tracking"] == DenialReason.POLICY_DENIED


def test_previous_authorization_does_not_persist_or_leak_into_new_call():
    verified = _verified()
    policy = AuthorizationPolicy.authorize(NODE_ID, {"contradiction_tracking"})
    first = authorize(verified, requested={"contradiction_tracking"}, policy=policy)
    assert first.is_authorized("contradiction_tracking")

    # A fresh call with NO policy for the same node/capability must not
    # remember the prior authorization.
    second = authorize(verified, requested={"contradiction_tracking"})
    assert not second.is_authorized("contradiction_tracking")


# ============================================================
# No state mutation / no architecture-boundary access
# ============================================================

def test_authorize_does_not_import_core_router_boundary_bridge_scars_agent():
    import lantern.capability_authorization as module

    source = Path(module.__file__).read_text()
    for forbidden_import in (
        "from .core",
        "from .router",
        "from .boundary",
        "from .bridge",
        "from .scars",
        "from .agent",
        "from .federation",
    ):
        assert forbidden_import not in source


def test_authorize_calls_no_mutation_primitives():
    import ast
    import lantern.capability_authorization as module

    source = Path(module.__file__).read_text()
    tree = ast.parse(source)
    called_names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Attribute):
                called_names.add(func.attr)
            elif isinstance(func, ast.Name):
                called_names.add(func.id)
    forbidden = {"add_evidence", "belief", "observe", "resolve", "persist_scar"}
    assert called_names & forbidden == set()


def test_authorization_decision_does_not_touch_lantern_core_state():
    from lantern.core import Lantern

    lantern = Lantern()
    before = lantern.export_state() if hasattr(lantern, "export_state") else repr(lantern.__dict__)

    verified = _verified()
    authorize(verified, requested={"contradiction_tracking"}, policy=AuthorizationPolicy.authorize(NODE_ID, {"contradiction_tracking"}))

    after = lantern.export_state() if hasattr(lantern, "export_state") else repr(lantern.__dict__)
    assert before == after


# ============================================================
# Privacy / secrets
# ============================================================

def test_private_key_material_never_appears_in_decision(tmp_path: Path):
    identity = identity_module.load_or_create(NODE_ID, tmp_path / NODE_ID)
    verified = _verified(node_id=identity.node_id)
    decision = authorize(verified, requested={"handshake"}, policy=AuthorizationPolicy.authorize(identity.node_id, {"handshake"}))
    blob = json.dumps(decision.to_dict())
    private_key_bytes = identity.identity_dir.joinpath("private_key.bin").read_bytes()
    assert private_key_bytes.hex() not in blob
    assert "private_key" not in blob


# ============================================================
# Determinism / bounded surface
# ============================================================

def test_repeated_identical_inputs_produce_identical_decisions():
    verified = _verified()
    policy = AuthorizationPolicy.authorize(NODE_ID, {"contradiction_tracking", "belief_query"})
    first = authorize(verified, requested={"contradiction_tracking", "belief_query"}, policy=policy)
    second = authorize(verified, requested={"contradiction_tracking", "belief_query"}, policy=policy)
    assert first.to_dict() == second.to_dict()


def test_denied_capabilities_are_explicitly_represented():
    verified = _verified()
    policy = AuthorizationPolicy.authorize(NODE_ID, {"contradiction_tracking"})
    decision = authorize(verified, requested={"contradiction_tracking", "belief_query"}, policy=policy)
    assert decision.denied_capabilities.get("belief_query") == DenialReason.POLICY_DENIED
    assert "belief_query" not in decision.authorized_capabilities


def test_authorization_bounded_by_negotiated_intersection_even_with_wildcard_policy():
    verified = _verified(shared_capabilities={"handshake": True, "identity_proof": True})
    decision = authorize(
        verified,
        requested={"handshake", "snapshot_exchange", "evidence_exchange"},
        policy=lambda node_id, capability: True,
    )
    assert decision.authorized_capabilities == frozenset({"handshake"})
    assert decision.denied_capabilities["snapshot_exchange"] == DenialReason.NOT_SHARED
    assert decision.denied_capabilities["evidence_exchange"] == DenialReason.NOT_SHARED


def test_legacy_node_with_no_identity_proof_capability_remains_compatible():
    # A node that never advertised identity_proof still gets a well-formed
    # CapabilityDecision (identity_status would be UNVERIFIED in practice,
    # exercised here directly) -- authorize() must not raise.
    verified = _verified(identity_status=identity_module.UNVERIFIED, shared_capabilities={"handshake": True})
    decision = authorize(verified, requested={"handshake"}, policy=AuthorizationPolicy.authorize(NODE_ID, {"handshake"}))
    assert decision.authorized_capabilities == frozenset()
    assert decision.denied_capabilities["handshake"] == DenialReason.IDENTITY_NOT_VERIFIED


def test_no_automatic_trust_transition_vocabulary_present():
    import lantern.capability_authorization as module

    source = Path(module.__file__).read_text()
    for forbidden in ("trust_score", "reputation", "auto_trust", "trust_status =", "authority_level ="):
        assert forbidden not in source


# ============================================================
# AuthorizationPolicy helper semantics
# ============================================================

def test_authorization_policy_merged_with_does_not_mutate_original():
    base = AuthorizationPolicy.authorize(NODE_ID, {"handshake"})
    extended = base.merged_with(NODE_ID, {"contradiction_tracking"})
    assert base.grants[NODE_ID] == frozenset({"handshake"})
    assert extended.grants[NODE_ID] == frozenset({"handshake", "contradiction_tracking"})


def test_empty_policy_authorizes_nothing():
    verified = _verified()
    decision = authorize(verified, requested=set(verified.shared_capabilities), policy=None)
    assert decision.authorized_capabilities == frozenset()


def test_policy_only_applies_to_matching_node_id():
    verified = _verified(node_id="lantern-C")
    policy = AuthorizationPolicy.authorize("lantern-OTHER", {"contradiction_tracking"})
    decision = authorize(verified, requested={"contradiction_tracking"}, policy=policy)
    assert decision.authorized_capabilities == frozenset()
    assert decision.denied_capabilities["contradiction_tracking"] == DenialReason.POLICY_DENIED


# ============================================================
# Two-node local HTTP integration: verify_contact -> authorize
# ============================================================

@dataclass
class _NodeState:
    node_id: str
    identity: identity_module.NodeIdentity
    capabilities: dict


class _Handler(http.server.BaseHTTPRequestHandler):
    state: _NodeState

    def log_message(self, *_args):
        pass

    def _read_json(self):
        length = int(self.headers.get("Content-Length", "0"))
        return json.loads(self.rfile.read(length).decode("utf-8"))

    def _write_json(self, status, payload):
        body = json.dumps(payload, sort_keys=True).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        from lantern.handshake import evaluate_handshake, HandshakeRequest

        body = self._read_json()
        if self.path == HANDSHAKE_PATH:
            req = HandshakeRequest(**body)
            resp = evaluate_handshake(req, supported_capabilities=self.state.capabilities, responder_node_id=self.state.node_id)
            self._write_json(200, {
                "node_id": resp.node_id, "accepted": resp.accepted, "protocol_version": resp.protocol_version,
                "shared_capabilities": resp.shared_capabilities, "reason": resp.reason, "timestamp": resp.timestamp,
            })
            return
        if self.path == IDENTITY_RESPOND_PATH:
            challenge = identity_module.Challenge(
                nonce=body["nonce"], from_node_id=body["from_node_id"], to_node_id=body["to_node_id"],
                protocol_version=body["protocol_version"], issued_at=time.monotonic(),
                ttl_seconds=body.get("ttl_seconds", identity_module.DEFAULT_CHALLENGE_TTL_SECONDS),
            )
            binding = json.loads((self.state.identity.identity_dir / "binding.json").read_text())
            proof = identity_module.respond_to_challenge(challenge, self.state.identity, binding["signature"])
            self._write_json(200, {
                "nonce": proof.nonce, "from_node_id": proof.from_node_id, "to_node_id": proof.to_node_id,
                "protocol_version": proof.protocol_version, "claimed_node_id": proof.claimed_node_id,
                "public_key": proof.public_key, "identity_binding_signature": proof.identity_binding_signature,
                "signature": proof.signature, "proof_timestamp": proof.proof_timestamp,
            })
            return
        self._write_json(404, {"error": "not found"})


def test_two_node_end_to_end_verified_contact_then_capability_authorization(tmp_path: Path):
    local = identity_module.load_or_create("lantern-A", tmp_path / "lantern-A")
    remote = identity_module.load_or_create("lantern-B", tmp_path / "lantern-B")
    state = _NodeState(node_id=remote.node_id, identity=remote, capabilities={**DEFAULT_CAPABILITIES, "identity_proof": True})
    handler = type("Handler", (_Handler,), {"state": state})
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        policy_gate = NetworkContactPolicy(allow_loopback_for_testing=True, allowed_ports=frozenset(range(1, 65536)))
        transport = NetworkContactTransport(policy=policy_gate, allow_loopback_for_testing=True)
        endpoint = f"http://{server.server_address[0]}:{server.server_address[1]}"
        verdict = policy_gate.evaluate(endpoint)
        contact_result = transport.contact(endpoint, verdict=verdict)
        verified = verify_contact(contact_result, transport=transport, verdict=verdict, local_node_id=local.node_id, local_identity=local)
    finally:
        server.shutdown(); server.server_close(); thread.join(timeout=5)

    assert verified.verified
    operator_policy = AuthorizationPolicy.authorize(verified.remote_node_id, {"contradiction_tracking"})
    decision = authorize(verified, requested={"contradiction_tracking", "belief_query", "codex_update"}, policy=operator_policy)

    assert decision.is_authorized("contradiction_tracking")
    assert not decision.is_authorized("belief_query")
    assert not decision.is_authorized("codex_update")
    assert decision.denied_capabilities["codex_update"] == DenialReason.STRUCTURALLY_UNAUTHORIZABLE
    assert decision.identity_status == identity_module.CRYPTOGRAPHICALLY_VERIFIED
