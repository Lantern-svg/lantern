# Lantern External Connection Contract

What another Lantern instance needs to connect to this node over a public
HTTPS endpoint and perform the authenticated evidence-exchange protocol.

Protocol version: 0.82. All request/response bodies are JSON
(Content-Type: application/json).

## 1. Endpoint format

- Public: `https://<operator-ingress-host>[:port]` — an operator-controlled
  HTTPS ingress (reverse proxy or tunnel) terminating TLS and forwarding to
  this node's internal listener.
- Internal listener: `http://<bind_host>:<bind_port>` (default
  127.0.0.1:8765). The node itself speaks plain HTTP; authentication is
  cryptographic (Ed25519 identity + proof-of-possession sessions), never
  TLS alone.

## 2. Health (unauthenticated, public-safe)

`GET /health` → `{"status": "ok", "node_id", "protocol_version",
"identity_public": {"node_id", "public_key", "binding_signature"},
"capabilities", ...}`

A connecting client should verify the receiver's identity from this:
`verify_binding(node_id, public_key, binding_signature)` using the
lantern.identity primitives, and pin the public key (TOFU first use).

## 3. Handshake

`POST /handshake` with the HandshakeRequest fields (node_id,
protocol_version, timestamp, capabilities). The response is a
HandshakeResponse with `accepted`, `shared_capabilities`.

If the operator configured an allowlist
(LANTERN_ALLOWED_PROTOCOL_VERSIONS), disallowed peer versions are
rejected with reason `PROTOCOL_VERSION_NOT_ALLOWED`. With an allowlist
configured, the handshake is also MANDATORY: a peer with no accepted
handshake on record cannot open a session (SESSION_HANDSHAKE_REQUIRED),
so the version gate cannot be bypassed by skipping /handshake. With no
allowlist configured (default), behavior is unchanged.

## 4. Identity proof (sender proves itself)

1. `POST /identity/challenge` `{"node_id": "<sender>"}`
   → `{nonce, from_node_id, to_node_id, protocol_version, ttl_seconds}`
2. Sign the challenge with the sender's private key (Ed25519) → proof.
3. `POST /identity/respond` / `POST /identity/verify` with the proof.
Result: `verified: true/false`. No session and no authorization is implied.

## 5. Authenticated session (two-phase proof-of-possession)

1. `POST /session/open` `{"node_id": "<sender>"}`
   → challenge `{nonce, ...}` (NOT a session).
2. Sign that challenge → `POST /session/open`
   `{"node_id": "<sender>", "proof": {...}}`
   → `{"created": true, "session_id"}`.

Sessions expire after the receiver's TTL (default 300s).

## 6. Authorization (required, explicit)

The receiver's operator must have pre-authorized the sender's node_id for
`evidence_exchange` (CLI `--authorize <sender_node_id>:evidence_exchange`
or env `LANTERN_AUTHORIZE`). A verified session alone grants NOTHING.
Untrusted senders are rejected with
`'evidence_exchange' is not in authorized_capabilities for '<node_id>'`.

## 7. Observation submission

`POST /message`
`{"message": <ProtocolMessage OBSERVATION_SHARE>, "session_id": "..."}`

The message payload carries `{content, source, reliability}`. The
receiver caps remote reliability at 0.5, deduplicates, and persists the
observation into its hash-chained Chronicle with full provenance.

Response: `{accepted: true, observation_id, watermark, ...}`.

Unauthenticated POSTs without a session are rejected
(`LEGACY_MODE_DISABLED` unless the operator explicitly opted in).

## 8. Authenticated retrieval + SHA-256 verification

`POST /observation/retrieve`
`{"session_id": "...", "node_id": "<sender>", "observation_id": "..."}`

Requires the same valid session and evidence_exchange authorization,
and returns only observations the requesting node ITSELF sent
(payload.source == session node_id). Retrieving another peer's
observation -- even with valid session and authorization -- is rejected
with `OBSERVATION_NOT_YOURS`; guessing IDs yields no data.
Response on success:
`{accepted, content, stored_digest, record_hash, record_timestamp,
chronicle: {chain, step}, retrieved_by, responded_by}`.

The client MUST independently compute
`SHA256(content)` and compare it to `stored_digest`; it only trusts the
observation if they match. The Chronicle hash chain anchors the record.

## 9. Acknowledgment

There is no dedicated ACK message type. The established pattern is a
reverse-direction OBSERVATION_SHARE: the receiver sends its own
observation (e.g. digest-only content referencing the original
`observation_id`/`remote_message_id`) back to the sender's node through
the identical session path on the sender. The sender verifies it the
same way.

## 10. Expected error responses

Additional protocol-level rejections: `SESSION_HANDSHAKE_REQUIRED`
(session attempted without a prior accepted handshake while a version
allowlist is configured), `OBSERVATION_NOT_YOURS` (cross-peer
retrieval).

- 400 `{error}` — malformed input (missing/typed-wrong fields).
- 200 `{accepted: false, reason}` — protocol-level rejections:
  session invalid/expired, capability not authorized,
  `OBSERVATION_NOT_FOUND`, duplicate observation,
  `PROTOCOL_VERSION_NOT_ALLOWED`, `LEGACY_MODE_DISABLED`.
- 500 `{error: "Durable write failed"}` — Chronicle persistence failure
  (never reported as success).
- 404 `{error: "Not found"}` — unknown endpoint.

## 11. Deployment configuration (no hard-coded URLs)

Env (CLI overrides): LANTERN_NODE_ID (required), LANTERN_BIND_HOST,
LANTERN_BIND_PORT, LANTERN_DATA_DIR, LANTERN_CHRONICLE,
LANTERN_WITNESS_REGISTRY, LANTERN_PUBLIC_URL (this node's public base
URL — diagnostics only), LANTERN_AUTHORIZE, LANTERN_ALLOWED_PROTOCOL_
VERSIONS, LANTERN_SESSION_TTL_SECONDS, LANTERN_ALLOW_LEGACY_MESSAGE_
INGESTION (default off).

## 12. Startup & self-test

`python -m lantern.bootstrap_node --self-test` verifies identity load,
witness reconciliation, and Chronicle integrity, prints public-only
diagnostics (node_id, fingerprint, protocol version, capabilities,
listeners, readiness), exits 0/1 — without binding a socket. Normal
startup prints the same banner, then serves.

Never printed anywhere: private keys, credentials.
