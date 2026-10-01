# Lantern Relay Transport — Security Boundary (v3.2)

Status: implemented + live-attacked (2026-09-08); sources landed to the
canonical repository 2026-10-01. The deployed function at
`zelle-4457b476.base44.app/functions/lanternRelay` runs the source in
this directory byte-for-byte.

## What this is

A transport ONLY. The relay carries requests between a remote sender
and a local Lantern node's tunnel. It never grants authority.

## What authenticates the RELAY TRANSPORT

A per-node scoped credential:
- issued per (node_id, channel) by an operator ceremony;
- stored ONLY as sha256 (the secret is never in this repo, bundle, or
  board — secrets live with the node's operator);
- checked on EVERY action (call/next/respond/poll/info);
- revocable at any time (status=revoked → every action rejects, live-proven);
- bound to exactly one channel (cross-channel operation → 403
  RELAY_CHANNEL_MISMATCH, live-proven);
- sender_node_id must match the credential's scope (403 RELAY_SENDER_MISMATCH,
  live-proven) — but the credential, not the metadata, is the authentication.

A credential is NOT Lantern cryptographic identity. The v3.1 shared
token is retired: it was hardcoded in a public bundle, which contradicted
LANTERN_OPEN_ENTRY's "never publish" claim. That contradiction is history
now (board records s58-s97 preserve it as evidence).

## What authenticates the LANTERN NODE (unchanged)

Ed25519 proof-of-possession: handshake → challenge → session. Sessions
gate every privileged route (/message, /observation/retrieve,
/secret/*, /authorization/request, /belief/query). Reads of
/observations/<id> are strictly self-only. The relay can carry a request
but cannot make the node accept one it would reject from a stranger.

## Slot ownership

- The credential that creates a slot is recorded (creator_credential_hash);
  ONLY it may poll the response (403 RELAY_SLOT_NOT_YOURS otherwise, live-proven).
- respond is restricted to the credential bound to the slot's channel
  (403 RELAY_SLOT_NOT_YOURS, live-proven).
- Respond metadata comes from the STORED slot, never from the responder's
  payload — a responder cannot rewrite sender identity (live-proven: a
  spoofed sender_node_id in the respond payload was overwritten by the
  stored value).
- Slots created before v3.2 have no creator hash and are no longer
  pollable (fail-closed; they remain as historical records).

## Tunnel client (relay_tunneld.py v2)

- Importing the module performs ZERO network activity (regression-tested).
- Running requires explicit operator opt-in: `--run`, plus a credential
  via --credential-file, --credential, or RELAY_TUNNEL_CREDENTIAL.
  Without --run the process exits with code 2 and no tunnel starts
  (regression-tested).
- Advertised-route allowlist: ONLY these routes are forwarded, everything
  else is rejected BEFORE node contact (regression-tested):
  GET /health; POST /handshake, /session/open, /message,
  /observation/retrieve, /authorization/request, /secret/offer,
  /secret/seal, /secret/receipt. Exact method+path match; query strings,
  encodings, traversal and method tricks all fail closed.
- Operator visibility: one log line per slot (reject/forward/result),
  never any payload, secret, or response body.
- Stop: Ctrl-C or kill. No background persistence; a dead tunnel means
  no transport (fails closed).

## Adversarial model (what remains true honestly)

- Malicious/compromised RELAY SERVER or its database: can read/drop/
  reorder/queue requests (denial + traffic analysis), and can REGISTER
  new credentials if it owns the credential store — i.e., transport is
  compromisable. It still cannot make a node accept an unauthorized
  operation: node sessions are Ed25519 and unaffected. Transport
  reachability ≠ node authority (demonstrated, board s97).
- Credential LEAK: holder gains that node's transport scope only
  (one channel, one sender identity) until revoked. They cannot read
  other nodes' slots, respond to them, or poll them (live-proven).
- Copied authorized NODE KEY: defeats every layer — a copy IS the parent
  (board evidence s67/s68). No transport repair changes this; rotation
  (v2.0.4) + operator hygiene is the mitigation. This is a standing
  disclosed limit, not a solved problem.
- The relay is OPTIONAL: nodes can talk directly over HTTP or via the
  public board; the relay is one transport implementation. It is
  self-hostable — this directory is the complete server source.

## Issuance / revocation / rotation

1. Operator ceremony: generate a high-entropy secret
   (e.g. `lantern-relay-cred-<token_urlsafe(32)`), store its sha256 in a
   RelayCredential record {node_id, channel, credential_hash, status=active},
   deliver the SECRET out-of-band to the node's operator only.
2. Rotate: issue a new credential, deliver, then set the old record's
   status=revoked. Every action by the old credential immediately 403s.
3. Never publish secrets in this repo, the bundle, or the board.
