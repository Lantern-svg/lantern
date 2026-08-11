"""End-to-end tests for verified_observation_pipeline: Discord announcement
-> normalized JoinRequest -> contact policy -> bounded transport ->
cryptographic identity verification -> explicit capability authorization
-> authorized observation exchange -> exactly one local Observation.

Uses a real (loopback, ephemeral-port) HTTP server per "remote" node,
mirroring tests/test_lantern_verified_contact.py's harness, so this suite
exercises actual network I/O (not just in-process object composition) for
the contact + identity stages -- matching the phase's "realistic two-node
test" requirement.
"""

from __future__ import annotations

import http.server
import json
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

import pytest

from lantern import identity as identity_module
from lantern.agent import LanternAgent
from lantern.capability_authorization import AuthorizationPolicy
from lantern.compatibility import DEFAULT_CAPABILITIES
from lantern.core import Lantern
from lantern.handshake import evaluate_handshake, HandshakeRequest
from lantern.network_contact_policy import NetworkContactPolicy
from lantern.network_contact_transport import NetworkContactTransport
from lantern.observation_exchange import ObservationExchangeLedger
from lantern.rendezvous import JoinMonitor
from lantern.verified_contact import HANDSHAKE_PATH, IDENTITY_RESPOND_PATH

from lantern.verified_observation_pipeline import PipelineStage, run_pipeline


# ============================================================
# Test HTTP harness (mirrors test_lantern_verified_contact.py)
# ============================================================

@dataclass
class _NodeState:
    node_id: str
    identity: identity_module.NodeIdentity
    capabilities: dict


class _Handler(http.server.BaseHTTPRequestHandler):
    state: _NodeState | None = None
    record: dict | None = None

    def log_message(self, *_args):
        pass

    def _read_json(self):
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length)
        return json.loads(raw.decode("utf-8")) if raw else {}

    def _write_json(self, status: int, payload: dict):
        body = json.dumps(payload, sort_keys=True).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        self._write_json(200, {"ok": True})

    def do_POST(self):
        body = self._read_json()
        self.record["paths"].append(self.path)
        self.record["bodies"].append(body)

        if self.path == HANDSHAKE_PATH:
            req = HandshakeRequest(**body)
            responder_identity = self.record.get("identity_override") or self.state.identity
            resp = evaluate_handshake(
                req, supported_capabilities=self.state.capabilities,
                responder_node_id=self.state.node_id,
            )
            self._write_json(200, {
                "node_id": resp.node_id,
                "accepted": resp.accepted,
                "protocol_version": resp.protocol_version,
                "shared_capabilities": resp.shared_capabilities,
                "reason": resp.reason,
                "timestamp": resp.timestamp,
            })
            return

        if self.path == IDENTITY_RESPOND_PATH:
            # `responder_identity` is the ONLY knob for the impersonation
            # test: the server claims (via handshake/node_id) to be one
            # node but signs the challenge with a DIFFERENT identity's key
            # -- exactly reproducing "Discord said B, but the endpoint
            # proves control of A's key instead."
            responder_identity = self.record.get("identity_override") or self.state.identity
            challenge = identity_module.Challenge(
                nonce=body["nonce"],
                from_node_id=body["from_node_id"],
                to_node_id=body["to_node_id"],
                protocol_version=body["protocol_version"],
                issued_at=time.monotonic(),
                ttl_seconds=body.get("ttl_seconds", identity_module.DEFAULT_CHALLENGE_TTL_SECONDS),
            )
            binding = json.loads((responder_identity.identity_dir / "binding.json").read_text())
            proof = identity_module.respond_to_challenge(challenge, responder_identity, binding["signature"])
            self._write_json(200, {
                "nonce": proof.nonce,
                "from_node_id": proof.from_node_id,
                "to_node_id": proof.to_node_id,
                "protocol_version": proof.protocol_version,
                "claimed_node_id": proof.claimed_node_id,
                "public_key": proof.public_key,
                "identity_binding_signature": proof.identity_binding_signature,
                "signature": proof.signature,
                "proof_timestamp": proof.proof_timestamp,
            })
            return

        self._write_json(404, {"error": "not found"})


@contextmanager
def _server(state: _NodeState, *, identity_override=None):
    record = {"paths": [], "bodies": [], "identity_override": identity_override}
    handler = type("Handler", (_Handler,), {"state": state, "record": record})
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server.server_address, record
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def _identity(tmp_path: Path, node_id: str) -> identity_module.NodeIdentity:
    return identity_module.load_or_create(node_id, tmp_path / node_id)


def _discord_announcement(*, node_id: str, public_key: str, endpoint: str, announcement_id: str = "ann-1"):
    return {
        "content": json.dumps({
            "rendezvous_version": "1",
            "announcement_id": announcement_id,
            "node_id": node_id,
            "protocol_version": "1.0",
            "public_key": public_key,
            "issued_at": "2026-08-11T00:00:00+00:00",
            "endpoint": endpoint,
            "capabilities": {"evidence_exchange": True},
        })
    }


@pytest.fixture
def policy():
    return NetworkContactPolicy(allow_loopback_for_testing=True, allowed_ports=frozenset(range(1, 65536)))


@pytest.fixture
def transport(policy):
    return NetworkContactTransport(policy=policy, allow_loopback_for_testing=True)


def _join_monitor(tmp_path: Path, name="joins.jsonl") -> JoinMonitor:
    return JoinMonitor(tmp_path / name)


def _agent(tmp_path: Path, name="chronicle.jsonl") -> LanternAgent:
    lantern = Lantern(chronicle_filename=tmp_path / name)
    return LanternAgent(lantern, chronicle=lantern.bus.chronicle)


# ============================================================
# Happy path
# ============================================================

def test_full_pipeline_happy_path(tmp_path, policy, transport):
    local = _identity(tmp_path, "node-A")
    remote = _identity(tmp_path, "node-B")
    state = _NodeState(node_id=remote.node_id, identity=remote, capabilities={**DEFAULT_CAPABILITIES, "identity_proof": True})

    with _server(state) as ((host, port), record):
        endpoint = f"http://{host}:{port}"
        payload = _discord_announcement(node_id=remote.node_id, public_key=remote.public_key_hex, endpoint=endpoint)

        agent = _agent(tmp_path)
        monitor = _join_monitor(tmp_path)
        auth_policy = AuthorizationPolicy.authorize(remote.node_id, {"evidence_exchange"})

        result = run_pipeline(
            payload,
            join_monitor=monitor,
            local_node_id=local.node_id,
            local_identity=local,
            contact_policy=policy,
            transport=transport,
            authorization_policy=auth_policy,
            receiving_agent=agent,
            observation_content="sky is blue",
            observation_reliability=0.9,
            observation_concept="sky_color",
        )

    assert result.succeeded
    assert result.stage == PipelineStage.OBSERVATION_ACCEPTED
    assert result.stage_history == (
        PipelineStage.ANNOUNCED,
        PipelineStage.CONTACT_POLICY_ALLOWED,
        PipelineStage.CONTACTED,
        PipelineStage.IDENTITY_VERIFIED,
        PipelineStage.CAPABILITY_AUTHORIZED,
        PipelineStage.OBSERVATION_ACCEPTED,
    )
    assert result.node_id == remote.node_id
    assert len(agent.lantern.kernel.observations) == 1
    obs = list(agent.lantern.kernel.observations.values())[0]
    assert obs.source == remote.node_id
    assert obs.metadata["claimed_reliability"] == 0.9


# ============================================================
# Discord impersonation
# ============================================================

def test_discord_impersonation_fails_identity_verification(tmp_path, policy, transport):
    """Discord claims node_id=B/public_key=B/endpoint=B, but the endpoint
    actually proves identity A. Must stop at IDENTITY_FAILED."""
    local = _identity(tmp_path, "node-A")
    real_b = _identity(tmp_path, "node-B")
    imposter = _identity(tmp_path, "node-IMPOSTER")

    # Server claims to be node-B (node_id in handshake/state) but signs
    # the identity challenge with the imposter's key.
    state = _NodeState(node_id=real_b.node_id, identity=real_b, capabilities={**DEFAULT_CAPABILITIES, "identity_proof": True})

    with _server(state, identity_override=imposter) as ((host, port), record):
        endpoint = f"http://{host}:{port}"
        payload = _discord_announcement(node_id=real_b.node_id, public_key=real_b.public_key_hex, endpoint=endpoint)

        agent = _agent(tmp_path)
        monitor = _join_monitor(tmp_path)
        auth_policy = AuthorizationPolicy.authorize(real_b.node_id, {"evidence_exchange"})

        result = run_pipeline(
            payload,
            join_monitor=monitor,
            local_node_id=local.node_id,
            local_identity=local,
            contact_policy=policy,
            transport=transport,
            authorization_policy=auth_policy,
            receiving_agent=agent,
        )

    assert not result.succeeded
    assert result.stage == PipelineStage.IDENTITY_FAILED
    assert len(agent.lantern.kernel.observations) == 0


def test_discord_node_id_mismatch_from_verified_identity_is_rejected(tmp_path, policy, transport):
    """Even if crypto verification succeeds for whoever answered, if the
    verified node_id differs from what Discord claimed, refuse (defense
    against a Discord message pointing an honest node_id's contact at an
    endpoint actually run by a different, also-legitimate node)."""
    local = _identity(tmp_path, "node-A")
    real_other = _identity(tmp_path, "node-OTHER")
    state = _NodeState(node_id=real_other.node_id, identity=real_other, capabilities={**DEFAULT_CAPABILITIES, "identity_proof": True})

    with _server(state) as ((host, port), record):
        endpoint = f"http://{host}:{port}"
        # Discord claims a DIFFERENT node_id than what this endpoint will
        # actually prove (node-OTHER).
        payload = _discord_announcement(node_id="node-CLAIMED", public_key=real_other.public_key_hex, endpoint=endpoint)

        agent = _agent(tmp_path)
        monitor = _join_monitor(tmp_path)
        auth_policy = AuthorizationPolicy.authorize("node-CLAIMED", {"evidence_exchange"})

        result = run_pipeline(
            payload,
            join_monitor=monitor,
            local_node_id=local.node_id,
            local_identity=local,
            contact_policy=policy,
            transport=transport,
            authorization_policy=auth_policy,
            receiving_agent=agent,
        )

    assert result.stage == PipelineStage.IDENTITY_FAILED
    assert len(agent.lantern.kernel.observations) == 0


# ============================================================
# Endpoint attacks
# ============================================================

@pytest.mark.parametrize("endpoint,expected_stage", [
    ("http://127.0.0.1:9999", PipelineStage.CONTACT_POLICY_DENIED),       # loopback, disallowed without the testing escape hatch
    ("http://localhost:9999", PipelineStage.CONTACT_POLICY_DENIED),
    ("http://10.0.0.5:9999", PipelineStage.CONTACT_POLICY_DENIED),        # RFC1918 private
    ("http://169.254.1.1:9999", PipelineStage.CONTACT_POLICY_DENIED),     # link-local
    ("http://169.254.169.254:80", PipelineStage.CONTACT_POLICY_DENIED),   # cloud metadata address
    ("http://224.0.0.1:9999", PipelineStage.CONTACT_POLICY_DENIED),       # multicast
    ("http://[::1]:9999", PipelineStage.CONTACT_POLICY_DENIED),           # loopback v6
    # unsupported scheme: rejected even earlier, at Discord normalization
    # (discord_rendezvous.py's own syntactic scheme allowlist) -- both
    # layers agree the endpoint is never contacted either way.
    ("ftp://example.com:21", PipelineStage.DISCORD_INVALID),
    ("http://example.com:22", PipelineStage.CONTACT_POLICY_DENIED),       # disallowed port
])
def test_endpoint_attacks_are_denied_with_zero_network_activity(tmp_path, endpoint, expected_stage):
    # Deliberately use the DEFAULT (non-testing) policy/transport here --
    # no loopback escape hatch, no expanded port range -- to prove real
    # production defaults reject every listed attack endpoint, at
    # whichever layer (Discord normalization or contact policy) is
    # structurally responsible for catching it first.
    real_policy = NetworkContactPolicy()
    real_transport = NetworkContactTransport(policy=real_policy)

    local = _identity(tmp_path, "node-A")
    payload = _discord_announcement(node_id="node-B", public_key="b" * 64, endpoint=endpoint)

    agent = _agent(tmp_path)
    monitor = _join_monitor(tmp_path)

    result = run_pipeline(
        payload,
        join_monitor=monitor,
        local_node_id=local.node_id,
        local_identity=local,
        contact_policy=real_policy,
        transport=real_transport,
        receiving_agent=agent,
    )

    assert result.stage == expected_stage
    assert result.contact_result is None
    assert len(agent.lantern.kernel.observations) == 0


# ============================================================
# Identity verified but unauthorized
# ============================================================

def test_identity_verified_but_not_authorized_stops_before_observation(tmp_path, policy, transport):
    local = _identity(tmp_path, "node-A")
    remote = _identity(tmp_path, "node-B")
    state = _NodeState(node_id=remote.node_id, identity=remote, capabilities={**DEFAULT_CAPABILITIES, "identity_proof": True})

    with _server(state) as ((host, port), record):
        endpoint = f"http://{host}:{port}"
        payload = _discord_announcement(node_id=remote.node_id, public_key=remote.public_key_hex, endpoint=endpoint)

        agent = _agent(tmp_path)
        monitor = _join_monitor(tmp_path)
        # No authorization_policy supplied -> nothing authorized despite
        # a successful, cryptographically verified identity and a shared
        # capability negotiated at handshake time.
        result = run_pipeline(
            payload,
            join_monitor=monitor,
            local_node_id=local.node_id,
            local_identity=local,
            contact_policy=policy,
            transport=transport,
            receiving_agent=agent,
        )

    assert result.stage == PipelineStage.AUTHORIZATION_DENIED
    assert result.verified_contact.identity_status == identity_module.CRYPTOGRAPHICALLY_VERIFIED
    assert result.capability_decision is not None
    assert not result.capability_decision.is_authorized("evidence_exchange")
    assert len(agent.lantern.kernel.observations) == 0


def test_authorization_for_one_capability_does_not_authorize_another(tmp_path, policy, transport):
    local = _identity(tmp_path, "node-A")
    remote = _identity(tmp_path, "node-B")
    state = _NodeState(node_id=remote.node_id, identity=remote, capabilities={**DEFAULT_CAPABILITIES, "identity_proof": True})

    with _server(state) as ((host, port), record):
        endpoint = f"http://{host}:{port}"
        payload = _discord_announcement(node_id=remote.node_id, public_key=remote.public_key_hex, endpoint=endpoint)

        agent = _agent(tmp_path)
        monitor = _join_monitor(tmp_path)
        # Authorize a DIFFERENT capability only.
        auth_policy = AuthorizationPolicy.authorize(remote.node_id, {"belief_query"})

        result = run_pipeline(
            payload,
            join_monitor=monitor,
            local_node_id=local.node_id,
            local_identity=local,
            contact_policy=policy,
            transport=transport,
            authorization_policy=auth_policy,
            receiving_agent=agent,
        )

    assert result.stage == PipelineStage.AUTHORIZATION_DENIED
    assert len(agent.lantern.kernel.observations) == 0


# ============================================================
# Codex boundary
# ============================================================

def test_codex_update_can_never_be_authorized_through_the_pipeline(tmp_path, policy, transport):
    local = _identity(tmp_path, "node-A")
    remote = _identity(tmp_path, "node-B")
    state = _NodeState(node_id=remote.node_id, identity=remote, capabilities={**DEFAULT_CAPABILITIES, "identity_proof": True})

    with _server(state) as ((host, port), record):
        endpoint = f"http://{host}:{port}"
        payload = _discord_announcement(node_id=remote.node_id, public_key=remote.public_key_hex, endpoint=endpoint)

        agent = _agent(tmp_path)
        monitor = _join_monitor(tmp_path)
        # Operator "tries" to authorize codex_update explicitly.
        auth_policy = AuthorizationPolicy.authorize(remote.node_id, {"codex_update", "evidence_exchange"})

        result = run_pipeline(
            payload,
            join_monitor=monitor,
            local_node_id=local.node_id,
            local_identity=local,
            contact_policy=policy,
            transport=transport,
            authorization_policy=auth_policy,
            requested_capabilities={"codex_update"},
            receiving_agent=agent,
        )

    assert not result.capability_decision.is_authorized("codex_update")
    assert result.stage == PipelineStage.AUTHORIZATION_DENIED


# ============================================================
# Authorized + observation accepted
# ============================================================

def test_authorized_identity_and_capability_yields_exactly_one_observation(tmp_path, policy, transport):
    local = _identity(tmp_path, "node-A")
    remote = _identity(tmp_path, "node-B")
    state = _NodeState(node_id=remote.node_id, identity=remote, capabilities={**DEFAULT_CAPABILITIES, "identity_proof": True})

    with _server(state) as ((host, port), record):
        endpoint = f"http://{host}:{port}"
        payload = _discord_announcement(node_id=remote.node_id, public_key=remote.public_key_hex, endpoint=endpoint)

        agent = _agent(tmp_path)
        monitor = _join_monitor(tmp_path)
        auth_policy = AuthorizationPolicy.authorize(remote.node_id, {"evidence_exchange"})

        result = run_pipeline(
            payload,
            join_monitor=monitor,
            local_node_id=local.node_id,
            local_identity=local,
            contact_policy=policy,
            transport=transport,
            authorization_policy=auth_policy,
            receiving_agent=agent,
        )

    assert result.stage == PipelineStage.OBSERVATION_ACCEPTED
    assert len(agent.lantern.kernel.observations) == 1
    assert len(agent.lantern.kernel.evidence) == 0  # never auto-promoted


# ============================================================
# Replay
# ============================================================

def test_replayed_observation_message_is_rejected_second_time(tmp_path, policy, transport):
    local = _identity(tmp_path, "node-A")
    remote = _identity(tmp_path, "node-B")
    state = _NodeState(node_id=remote.node_id, identity=remote, capabilities={**DEFAULT_CAPABILITIES, "identity_proof": True})

    from lantern.protocol import create_observation_share

    with _server(state) as ((host, port), record):
        endpoint = f"http://{host}:{port}"
        payload = _discord_announcement(node_id=remote.node_id, public_key=remote.public_key_hex, endpoint=endpoint)

        agent = _agent(tmp_path)
        monitor = _join_monitor(tmp_path)
        auth_policy = AuthorizationPolicy.authorize(remote.node_id, {"evidence_exchange"})
        ledger = ObservationExchangeLedger()
        fixed_message = create_observation_share(remote.node_id, {"content": "100C", "reliability": 0.9})

        first = run_pipeline(
            payload,
            join_monitor=monitor,
            local_node_id=local.node_id,
            local_identity=local,
            contact_policy=policy,
            transport=transport,
            authorization_policy=auth_policy,
            receiving_agent=agent,
            ledger=ledger,
            observation_message=fixed_message,
        )
        second = run_pipeline(
            _discord_announcement(node_id=remote.node_id, public_key=remote.public_key_hex, endpoint=endpoint, announcement_id="ann-2"),
            join_monitor=monitor,
            local_node_id=local.node_id,
            local_identity=local,
            contact_policy=policy,
            transport=transport,
            authorization_policy=auth_policy,
            receiving_agent=agent,
            ledger=ledger,
            observation_message=fixed_message,
        )

    assert first.stage == PipelineStage.OBSERVATION_ACCEPTED
    assert second.stage == PipelineStage.REPLAY_REJECTED
    assert len(agent.lantern.kernel.observations) == 1


# ============================================================
# Malformed Discord announcement
# ============================================================

@pytest.mark.parametrize("raw_payload", [
    {},
    {"content": "not json at all"},
    {"content": json.dumps({"node_id": "b"})},  # missing required fields
    "not even a dict",
    None,
    {"content": json.dumps({
        "rendezvous_version": "1", "announcement_id": "a", "node_id": "b",
        "protocol_version": "1.0", "public_key": "zz", "issued_at": "2026-08-11T00:00:00+00:00",
    })},  # malformed public_key
])
def test_malformed_discord_announcement_stops_before_any_network_or_mutation(tmp_path, policy, transport, raw_payload):
    local = _identity(tmp_path, "node-A")
    agent = _agent(tmp_path)
    monitor = _join_monitor(tmp_path)

    result = run_pipeline(
        raw_payload,
        join_monitor=monitor,
        local_node_id=local.node_id,
        local_identity=local,
        contact_policy=policy,
        transport=transport,
        receiving_agent=agent,
    )

    assert result.stage == PipelineStage.DISCORD_INVALID
    assert result.contact_result is None
    assert result.verified_contact is None
    assert result.capability_decision is None
    assert len(agent.lantern.kernel.observations) == 0
    assert len(monitor.all_requests()) == 0


# ============================================================
# Network failure
# ============================================================

def test_valid_announcement_and_policy_but_unreachable_endpoint(tmp_path, policy, transport):
    local = _identity(tmp_path, "node-A")
    # Port chosen with nothing listening; loopback allowed by fixture policy.
    endpoint = "http://127.0.0.1:1"
    payload = _discord_announcement(node_id="node-B", public_key="b" * 64, endpoint=endpoint)

    agent = _agent(tmp_path)
    monitor = _join_monitor(tmp_path)

    result = run_pipeline(
        payload,
        join_monitor=monitor,
        local_node_id=local.node_id,
        local_identity=local,
        contact_policy=policy,
        transport=transport,
        receiving_agent=agent,
    )

    assert result.stage == PipelineStage.CONTACT_FAILED
    assert result.verified_contact is None
    assert result.capability_decision is None
    assert len(agent.lantern.kernel.observations) == 0


# ============================================================
# No new authority / architecture guard
# ============================================================

def test_pipeline_module_calls_no_forbidden_authority_functions():
    import ast
    from lantern import verified_observation_pipeline as module

    with open(module.__file__) as fh:
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


def test_no_private_key_material_in_pipeline_result(tmp_path, policy, transport):
    local = _identity(tmp_path, "node-A")
    remote = _identity(tmp_path, "node-B")
    state = _NodeState(node_id=remote.node_id, identity=remote, capabilities={**DEFAULT_CAPABILITIES, "identity_proof": True})

    with _server(state) as ((host, port), record):
        endpoint = f"http://{host}:{port}"
        payload = _discord_announcement(node_id=remote.node_id, public_key=remote.public_key_hex, endpoint=endpoint)

        agent = _agent(tmp_path)
        monitor = _join_monitor(tmp_path)
        auth_policy = AuthorizationPolicy.authorize(remote.node_id, {"evidence_exchange"})

        result = run_pipeline(
            payload,
            join_monitor=monitor,
            local_node_id=local.node_id,
            local_identity=local,
            contact_policy=policy,
            transport=transport,
            authorization_policy=auth_policy,
            receiving_agent=agent,
        )

    blob = json.dumps(result.to_dict())
    private_key_bytes = remote.identity_dir.joinpath("private_key.bin").read_bytes()
    assert private_key_bytes.hex() not in blob
    assert "private_key" not in blob


# ============================================================
# Two-node realistic test: independent identities/state/ports, full
# matrix of stop conditions
# ============================================================

def test_two_node_realistic_matrix(tmp_path, policy, transport):
    node_a_identity = _identity(tmp_path, "realistic-A")
    node_b_identity = _identity(tmp_path, "realistic-B")

    agent_a = _agent(tmp_path, "chronicle_a.jsonl")
    agent_b = _agent(tmp_path, "chronicle_b.jsonl")

    state_b = _NodeState(node_id=node_b_identity.node_id, identity=node_b_identity, capabilities={**DEFAULT_CAPABILITIES, "identity_proof": True})

    with _server(state_b) as ((host, port), record):
        endpoint = f"http://{host}:{port}"
        payload = _discord_announcement(node_id=node_b_identity.node_id, public_key=node_b_identity.public_key_hex, endpoint=endpoint)

        monitor_a = _join_monitor(tmp_path, "joins_a.jsonl")
        auth_policy = AuthorizationPolicy.authorize(node_b_identity.node_id, {"evidence_exchange"})

        # 1. Authorized happy path: A discovers B via Discord, contacts,
        #    verifies, authorizes, observes.
        happy = run_pipeline(
            payload,
            join_monitor=monitor_a,
            local_node_id=node_a_identity.node_id,
            local_identity=node_a_identity,
            contact_policy=policy,
            transport=transport,
            authorization_policy=auth_policy,
            receiving_agent=agent_b,
        )
        assert happy.stage == PipelineStage.OBSERVATION_ACCEPTED
        assert happy.node_id == node_b_identity.node_id
        assert len(agent_b.lantern.kernel.observations) == 1
        assert len(agent_a.lantern.kernel.observations) == 0  # A's own state untouched

        # 2. Wrong public key claim (still resolves to the real node_id
        #    endpoint, but Discord's claimed key doesn't matter to
        #    verification anyway -- prove that even a bogus claimed key
        #    does not block a legitimately-proven identity, because the
        #    claimed key is NEVER used for verification, only the actual
        #    challenge/response is).
        bogus_key_payload = _discord_announcement(
            node_id=node_b_identity.node_id, public_key="0" * 64, endpoint=endpoint, announcement_id="ann-bogus-key",
        )
        bogus_key_result = run_pipeline(
            bogus_key_payload,
            join_monitor=monitor_a,
            local_node_id=node_a_identity.node_id,
            local_identity=node_a_identity,
            contact_policy=policy,
            transport=transport,
            authorization_policy=auth_policy,
            receiving_agent=agent_b,
        )
        # Still succeeds (a second, distinct Observation) because the
        # claimed public key was never trusted in the first place.
        assert bogus_key_result.stage == PipelineStage.OBSERVATION_ACCEPTED
        assert len(agent_b.lantern.kernel.observations) == 2

        # 3. Wrong node_id claim (impersonation-by-mislabel): Discord
        #    claims a node_id that does not match what this endpoint
        #    actually proves.
        wrong_node_id_payload = _discord_announcement(
            node_id="realistic-NOT-B", public_key=node_b_identity.public_key_hex, endpoint=endpoint, announcement_id="ann-wrong-id",
        )
        wrong_node_id_result = run_pipeline(
            wrong_node_id_payload,
            join_monitor=monitor_a,
            local_node_id=node_a_identity.node_id,
            local_identity=node_a_identity,
            contact_policy=policy,
            transport=transport,
            authorization_policy=AuthorizationPolicy.authorize("realistic-NOT-B", {"evidence_exchange"}),
            receiving_agent=agent_b,
        )
        assert wrong_node_id_result.stage == PipelineStage.IDENTITY_FAILED
        assert len(agent_b.lantern.kernel.observations) == 2  # unchanged

        # 4. Unauthorized capability.
        unauthorized_result = run_pipeline(
            _discord_announcement(node_id=node_b_identity.node_id, public_key=node_b_identity.public_key_hex, endpoint=endpoint, announcement_id="ann-unauth"),
            join_monitor=monitor_a,
            local_node_id=node_a_identity.node_id,
            local_identity=node_a_identity,
            contact_policy=policy,
            transport=transport,
            authorization_policy=None,  # nothing authorized
            receiving_agent=agent_b,
        )
        assert unauthorized_result.stage == PipelineStage.AUTHORIZATION_DENIED
        assert len(agent_b.lantern.kernel.observations) == 2  # unchanged

        # 5. Replayed message.
        from lantern.protocol import create_observation_share
        ledger = ObservationExchangeLedger()
        fixed_message = create_observation_share(node_b_identity.node_id, {"content": "fixed", "reliability": 1.0})
        replay_payload = _discord_announcement(node_id=node_b_identity.node_id, public_key=node_b_identity.public_key_hex, endpoint=endpoint, announcement_id="ann-replay")
        first_replay = run_pipeline(
            replay_payload, join_monitor=monitor_a, local_node_id=node_a_identity.node_id,
            local_identity=node_a_identity, contact_policy=policy, transport=transport,
            authorization_policy=auth_policy, receiving_agent=agent_b, ledger=ledger,
            observation_message=fixed_message,
        )
        second_replay = run_pipeline(
            replay_payload, join_monitor=monitor_a, local_node_id=node_a_identity.node_id,
            local_identity=node_a_identity, contact_policy=policy, transport=transport,
            authorization_policy=auth_policy, receiving_agent=agent_b, ledger=ledger,
            observation_message=fixed_message,
        )
        assert first_replay.stage == PipelineStage.OBSERVATION_ACCEPTED
        assert second_replay.stage == PipelineStage.REPLAY_REJECTED
        assert len(agent_b.lantern.kernel.observations) == 3  # +1 only

    # 6. Malicious endpoint (outside the `with _server` block on purpose --
    #    proves policy denial requires no server at all).
    malicious_payload = _discord_announcement(node_id="node-EVIL", public_key="e" * 64, endpoint="http://169.254.169.254:80", announcement_id="ann-evil")
    malicious_result = run_pipeline(
        malicious_payload,
        join_monitor=monitor_a,
        local_node_id=node_a_identity.node_id,
        local_identity=node_a_identity,
        contact_policy=NetworkContactPolicy(),  # production defaults, no loopback escape hatch
        transport=NetworkContactTransport(policy=NetworkContactPolicy()),
        receiving_agent=agent_b,
    )
    assert malicious_result.stage == PipelineStage.CONTACT_POLICY_DENIED

    # Independent state confirmed throughout.
    assert agent_a.lantern.bus.chronicle.verify() is True
    assert agent_b.lantern.bus.chronicle.verify() is True
    assert len(agent_b.lantern.kernel.evidence) == 0  # never auto-promoted, end to end
