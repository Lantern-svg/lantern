# Lantern External-Exchange Runbook

From zero to a successful external two-agent exchange. This runbook
keeps three facts strictly separate:

- SOFTWARE READY: the code is committed, self-tested, and the node starts.
- PUBLIC INGRESS READY: an operator-controlled public HTTPS endpoint
  forwards to the node's internal listener.
- EXTERNAL EXCHANGE VERIFIED: a genuinely external peer completed the
  full authenticated exchange through the public endpoint, and both
  sides independently verified digests.

A local loopback test is NEVER an Internet-level test. Do not describe
one as such.

## 1. Install / setup requirements

- Python 3.11+
- `pip install pynacl` (Ed25519 identity crypto)
- The Lantern repository at the validated commit
- No other runtime dependencies

## 2. Environment variables (all optional except node_id)

LANTERN_NODE_ID (required), LANTERN_BIND_HOST (default 127.0.0.1),
LANTERN_BIND_PORT (default 8765), LANTERN_DATA_DIR (default .lantern),
LANTERN_CHRONICLE (default <data-dir>/<node-id>.jsonl),
LANTERN_WITNESS_REGISTRY (default off), LANTERN_PUBLIC_URL (this node's
public base URL; diagnostics only), LANTERN_AUTHORIZE (e.g.
"peer-node:evidence_exchange"), LANTERN_ALLOWED_PROTOCOL_VERSIONS
(e.g. "0.82"), LANTERN_SESSION_TTL_SECONDS (default 300),
LANTERN_ALLOW_LEGACY_MESSAGE_INGESTION (default off; true/1/yes/on).

CLI flags override env vars. Nothing is hard-coded.

## 3. Self-test (pre-flight, binds nothing)

    PYTHONPATH=src python3 -m lantern.bootstrap_node --self-test \
      --node-id <node_id> --data-dir <dir> \
      [--witness-registry <registry.jsonl>]

Prints public-only diagnostics (node_id, public key, SHA-256
fingerprint, protocol version, capabilities, chronicle/witness health,
external_exchange_ready). Exit 0 = ready, 1 = FAIL (fail closed; the
node must not be deployed on FAIL).

## 4. Production startup

    PYTHONPATH=src python3 -m lantern.bootstrap_node \
      --node-id <node_id> \
      --data-dir <dir> \
      --chronicle <dir>/<node_id>.jsonl \
      [--witness-registry <registry.jsonl>] \
      --authorize <sender_node_id>:evidence_exchange \
      --public-url https://<operator-ingress> \
      [--allowed-protocol-versions 0.82]

Startup prints the same diagnostics banner, then serves. Never prints
private keys.

## 5. Expected /health response

    GET /health →
    {"status": "ok", "node_id": <id>, "protocol_version": "0.82",
     "identity_public": {"node_id", "public_key", "binding_signature"},
     "capabilities": {...}, "legacy_message_ingestion": false, ...}

Verify the receiver's identity from this: check
verify_binding(node_id, public_key, binding_signature) with the
lantern.identity primitives, and pin the public key on first use.

## 6. Public endpoint configuration

The node binds a plain-HTTP internal listener (default
127.0.0.1:8765). Point any legitimate operator-controlled HTTPS ingress
(reverse proxy or tunnel) at it:

    https://<public-host> → http://<bind_host>:<bind_port>

Set LANTERN_PUBLIC_URL to the public base URL for honest diagnostics.
Authentication is cryptographic (identity proof + proof-of-possession
sessions), independent of TLS.

## 7. Sender authorization

Capability grants are explicit and never automatic:

    --authorize <sender_node_id>:evidence_exchange

A verified session alone grants nothing. Wildcards are not supported.

## 8. Protocol version configuration

    --allowed-protocol-versions 0.82

With an allowlist configured, handshakes from other versions are
rejected (PROTOCOL_VERSION_NOT_ALLOWED) AND a prior accepted handshake
becomes mandatory for session creation (SESSION_HANDSHAKE_REQUIRED) --
the gate cannot be bypassed by skipping the handshake.

## 9. Verify node identity / fingerprint

From the diagnostics banner or /health, take the public key hex and
compute: SHA-256 of the raw 32 key bytes. Compare against the value the
operator recorded at first deployment (pin it). The witness ledger
(LAR-1) additionally detects key replacement across restarts.

## 10. First external exchange

The sender follows docs/external_connection_contract.md exactly:
handshake → identity challenge/respond/verify → two-phase session
proof → POST /message OBSERVATION_SHARE. Receiver response includes
observation_id.

## 11. Independently verify the digest

    POST /observation/retrieve {session_id, node_id, observation_id}
    → {accepted, content, stored_digest, record_hash, ...}

The retriever computes SHA-256(content) itself and accepts ONLY on
match with stored_digest. Cross-peer retrieval is rejected
(OBSERVATION_NOT_YOURS). Acknowledgment = reverse-direction
OBSERVATION_SHARE (digest-only content referencing the original
observation_id) through the identical authenticated path on the sender.

## 12. Safe shutdown

SIGINT (Ctrl-C) or SIGTERM: the server closes its socket cleanly after
in-flight requests; every Chronicle write is atomic (staged write +
fsync + rename), so there is no dirty-shutdown repair path to trust.
Verify integrity after any restart with --self-test.

## 13. Preserve identity across restarts

The identity directory (binding.json, private_key.bin, public_key.bin)
under <data-dir>/identity/<node_id> IS the node. Back it up with
encrypted export only:

    PYTHONPATH=src python3 -m lantern.witness_ledger export \
      --registry <registry.jsonl> --node-id <node_id> \
      --identity-dir <dir> --out identity.enc

Never copy private_key.bin in the clear. With a witness registry
configured, a lost-and-replaced key is DETECTED (fork) at startup --
load fails closed rather than silently regenerating.
