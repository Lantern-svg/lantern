"""Command-line client for the minimal external Lantern bootstrap.

Default (secure) workflow, mirroring the server's secure /message gate
in bootstrap_node.py:

    /health
        -> /handshake                          (capability negotiation only)
        -> /identity/challenge + /identity/verify   (cryptographic proof)
        -> /session/open                       (short-lived verified session)
        -> /message {message, session_id}      (session-bound, authorized)

This is the normal path an operator gets by default. The old
unauthenticated workflow (/message with only self-declared
peer_capabilities, no identity proof, no session) is preserved ONLY as
an explicit, clearly-labeled opt-in via --legacy, for talking to a peer
that was itself started with --allow-legacy-message-ingestion. Passing
--legacy against a secure-default peer will be rejected with
LEGACY_MODE_DISABLED, exactly as intended -- this client never silently
falls back from secure to legacy.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path
from urllib.request import Request, urlopen

from . import identity as identity_module
from .compatibility import DEFAULT_CAPABILITIES
from .continuity import local_watermark
from .core import Chronicle, Lantern
from .handshake import create_handshake
from .heartbeat import evaluate_connection
from .protocol import create_observation_share, PROTOCOL_VERSION


def _request(url: str, method: str = "GET", payload: dict | None = None) -> dict:
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    request = Request(url, data=data, method=method, headers={"Content-Type": "application/json"})
    with urlopen(request, timeout=10) as response:
        return json.loads(response.read())


def _verify_identity_with_peer(peer: str, local_node_id: str, local_identity) -> dict:
    """Prove local_node_id's identity to peer using the existing
    challenge/response/verify primitives from lantern.identity, over
    the peer's /identity/* HTTP routes.

    This node acts as RESPONDER here: the peer issues a challenge
    addressed to local_node_id (via /identity/challenge), this client
    signs it with its own persisted NodeIdentity (never sending or
    exposing the private key itself), and the peer verifies the
    resulting proof (via /identity/verify) and records the public key
    against local_node_id for the rest of that peer process's lifetime.
    Only after that verification succeeds can /session/open succeed.
    """
    challenge_data = _request(
        peer + "/identity/challenge", "POST", {"requester_node_id": local_node_id}
    )
    challenge = identity_module.Challenge(
        nonce=challenge_data["nonce"],
        from_node_id=challenge_data["from_node_id"],
        to_node_id=challenge_data["to_node_id"],
        protocol_version=challenge_data["protocol_version"],
        issued_at=0.0,
        ttl_seconds=challenge_data.get("ttl_seconds", identity_module.DEFAULT_CHALLENGE_TTL_SECONDS),
    )
    binding = json.loads((local_identity.identity_dir / "binding.json").read_text())
    proof = identity_module.respond_to_challenge(challenge, local_identity, binding["signature"])
    proof_data = {
        "nonce": proof.nonce,
        "from_node_id": proof.from_node_id,
        "to_node_id": proof.to_node_id,
        "protocol_version": proof.protocol_version,
        "claimed_node_id": proof.claimed_node_id,
        "public_key": proof.public_key,
        "identity_binding_signature": proof.identity_binding_signature,
        "signature": proof.signature,
        "proof_timestamp": proof.proof_timestamp,
    }
    return _request(peer + "/identity/verify", "POST", proof_data)


def _open_session_with_proof(peer: str, node_id: str, local_identity) -> dict:
    """Two-phase session open: request challenge, sign it, prove possession.

    (Gate 2 Finding 9: per-request proof of private-key possession.)

    No downgrade path: a server that returns created:true without a
    nonce is either unpatched or malicious.  The client rejects it
    rather than silently accepting a session with zero proof.
    """
    challenge_data = _request(peer + "/session/open", "POST", {"node_id": node_id})

    # A patched server issues a challenge (nonce present).  A server
    # that returns created:true with no nonce is rejected -- no
    # silent downgrade, no backward-compat fallback.
    if "nonce" not in challenge_data:
        raise SystemExit(json.dumps({"status": "session_rejected", "session": challenge_data}))

    # Phase 1 done: server issued a challenge.  Sign and submit.
    session_challenge = identity_module.Challenge(
        nonce=challenge_data["nonce"],
        from_node_id=challenge_data["from_node_id"],
        to_node_id=challenge_data["to_node_id"],
        protocol_version=challenge_data["protocol_version"],
        issued_at=0.0,
        ttl_seconds=challenge_data.get("ttl_seconds", identity_module.DEFAULT_CHALLENGE_TTL_SECONDS),
    )
    binding = json.loads((local_identity.identity_dir / "binding.json").read_text())
    session_proof = identity_module.respond_to_challenge(
        session_challenge, local_identity, binding["signature"]
    )
    session = _request(peer + "/session/open", "POST", {
        "node_id": node_id,
        "proof": {
            "nonce": session_proof.nonce,
            "from_node_id": session_proof.from_node_id,
            "to_node_id": session_proof.to_node_id,
            "protocol_version": session_proof.protocol_version,
            "claimed_node_id": session_proof.claimed_node_id,
            "public_key": session_proof.public_key,
            "identity_binding_signature": session_proof.identity_binding_signature,
            "signature": session_proof.signature,
            "proof_timestamp": session_proof.proof_timestamp,
        },
    })

    if not session.get("created"):
        raise SystemExit(json.dumps({"status": "session_rejected", "session": session}))

    return session


def _run_secure(args, local_lantern, local_handshake, remote) -> dict:
    peer = args.peer.rstrip("/")

    handshake_response = _request(peer + "/handshake", "POST", asdict(local_handshake))
    if not handshake_response["accepted"]:
        raise SystemExit(json.dumps({"status": "rejected", "handshake": handshake_response}))

    identity_dir = identity_module.default_identity_dir(Path(args.data_dir), args.node_id)
    local_identity = identity_module.load_or_create(args.node_id, identity_dir)

    verify_result = _verify_identity_with_peer(peer, args.node_id, local_identity)
    if not verify_result.get("verified"):
        raise SystemExit(json.dumps({"status": "identity_rejected", "identity": verify_result}))

    session = _open_session_with_proof(peer, args.node_id, local_identity)

    message = create_observation_share(
        args.node_id,
        {"content": args.content, "source": args.source, "reliability": args.reliability},
    )
    result = _request(
        peer + "/message",
        "POST",
        {"message": asdict(message), "session_id": session["session_id"]},
    )

    return {
        "mode": "secure",
        "handshake": handshake_response,
        "identity": verify_result,
        "session": session,
        "exchange": result,
    }


def _run_legacy(args, local_lantern, local_handshake, remote) -> dict:
    """Explicit legacy workflow: unauthenticated /message using only
    self-declared peer_capabilities, exactly as the pre-migration
    client behaved. Only reachable via --legacy. Will be rejected with
    LEGACY_MODE_DISABLED by any peer that has not itself opted into
    --allow-legacy-message-ingestion -- this client never retries or
    silently upgrades/downgrades between modes."""
    peer = args.peer.rstrip("/")

    handshake_response = _request(peer + "/handshake", "POST", asdict(local_handshake))
    if not handshake_response["accepted"]:
        raise SystemExit(json.dumps({"status": "rejected", "handshake": handshake_response}))

    message = create_observation_share(
        args.node_id,
        {"content": args.content, "source": args.source, "reliability": args.reliability},
    )
    result = _request(
        peer + "/message",
        "POST",
        {
            "message": asdict(message),
            "peer_capabilities": local_handshake.capabilities,
        },
    )

    return {
        "mode": "legacy",
        "handshake": handshake_response,
        "exchange": result,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description="Send one observation to a Lantern node")
    parser.add_argument("--peer", required=True, help="Peer base URL, e.g. http://127.0.0.1:8766")
    parser.add_argument("--source", required=True)
    parser.add_argument("--content", required=True)
    parser.add_argument("--reliability", type=float, default=1.0)
    parser.add_argument("--node-id", default="lantern-a")
    parser.add_argument("--data-dir", default=".lantern")
    parser.add_argument(
        "--legacy",
        action="store_true",
        default=False,
        help=(
            "Explicit opt-in ONLY: use the old unauthenticated /message "
            "workflow (self-declared peer_capabilities, no identity proof, "
            "no session). Default is the secure identity-verified, "
            "session-bound workflow. A peer running with secure defaults "
            "will reject a --legacy request with LEGACY_MODE_DISABLED."
        ),
    )
    args = parser.parse_args(argv)

    data_dir = Path(args.data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)
    local_chronicle = data_dir / f"{args.node_id}.jsonl"
    local_lantern = Lantern(chronicle_filename=local_chronicle)
    local_lantern.startup()

    peer = args.peer.rstrip("/")
    remote = _request(peer + "/health")
    local_handshake = create_handshake(dict(DEFAULT_CAPABILITIES))
    local_handshake.node_id = args.node_id

    if args.legacy:
        workflow_result = _run_legacy(args, local_lantern, local_handshake, remote)
    else:
        workflow_result = _run_secure(args, local_lantern, local_handshake, remote)

    # Heartbeat/connection-state check: liveness + identity + Chronicle
    # position reporting only. This never grants trust or capabilities
    # and never changes local belief -- it is purely operator-facing
    # information, produced by the existing continuity/compatibility
    # comparison logic (lantern.heartbeat.evaluate_connection()).
    peer_heartbeat = _request(peer + "/heartbeat")
    connection_state = evaluate_connection(
        PROTOCOL_VERSION,
        local_watermark(local_lantern),
        peer_heartbeat,
    ).to_dict()

    print(json.dumps({
        "local_node_id": args.node_id,
        "peer": remote,
        **workflow_result,
        "connection_state": connection_state,
        "local_watermark": {
            "step": local_lantern.kernel.step,
            "chain": local_lantern.bus.chronicle.chain,
        },
    }, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
