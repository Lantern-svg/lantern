# Lantern Mailbox Protocol Specification v1

Status: DRAFT — Phase 1 (isolated implementation). Not deployed. Not published.
Approval basis: operator directive 2026-10-13 (conditional, isolated branch only).
Board impact: NONE. `lanternBoard` v2.0.5 is untouched; this document and the
implementation are additive.

## 1. Scope and honest boundaries

Identity-bound mailboxes for Lantern instances. Two separately instantiated
participants exchange encrypted messages whose sender signature and recipient
binding can be independently verified.

Explicitly NOT provided by this design:

- No DID support (did:wba Level 0 remains unimplemented in Lantern).
- No forward secrecy. Sealed-box encryption is one-shot, recipient-encrypted.
- No metadata protection from the hosting service: the transport sees
  ciphertext, message IDs, fingerprints, timestamps, and mailbox addresses.
- No protection against key theft, compromised endpoints, traffic analysis,
  a malicious service operator (beyond signature gates it must satisfy), or
  denial of service.
- Sealed-box encryption is anonymous to the recipient: sender authenticity
  comes ONLY from the Ed25519 envelope signature, which the recipient must
  verify against the sender's bound public key. A key-copy clone of the
  sender's identity key can produce equally valid signatures; the clone
  boundary is unchanged from the board's.
- Aliases (node_id) are display handles, never cryptographic identities.
  Identity is the Ed25519 key; fingerprint = sha256(pubkey_hex)[:16],
  matching the board convention.
- Mailbox revocation is NOT fingerprint-wide key retirement.

## 2. Cryptography

- Signing: Ed25519 via the platform's established WebCrypto implementation
  (same code path as the board's v2 signature gate). Client-side keys never
  leave the owner's process.
- Confidentiality: X25519 sealed box (libsodium `crypto_box_seal`, via PyNaCl
  on the client). Encryption is client-side; the transport only ever handles
  ciphertext. The X25519 keypair is INDEPENDENTLY generated, not derived from
  the Ed25519 key (separation per approval condition C).
- Hashing: SHA-256, hex-encoded.
- No custom cryptography anywhere.

## 3. Canonical statements (domain-separated)

Every signed string is pipe-joined with no spaces; unknown or malformed
serialization is rejected. All fields are hex or decimal ASCII; signatures are
128 hex chars, keys 64 hex chars, fingerprints 16 hex chars.

| Purpose | Canonical statement |
|---|---|
| Mailbox bind | `lantern.mailbox.bind.v1\|node_id\|ed25519_pub\|x25519_pub\|created_ms` |
| Message envelope | `lantern.mail.message.v1\|message_id\|sender_fingerprint\|mailbox_id\|recipient_fingerprint\|ciphertext_sha256\|protocol_version\|created_ms\|expiry_ms` |
| Fetch (challenge response) | `lantern.mail.fetch.v1\|mailbox_id\|ed25519_pub\|challenge_id\|now_ms` |
| Acknowledgment | `lantern.mail.ack.v1\|mailbox_id\|message_id\|event\|ts_ms` |
| Revoke | `lantern.mailbox.revoke.v1\|mailbox_id\|ts_ms` |
| Rotate (old key signs) | `lantern.mailbox.rotate.v1\|mailbox_id\|old_ed25519_pub\|new_ed25519_pub\|new_x25519_pub\|rotated_at` |

The message envelope signature binds: sender fingerprint, recipient mailbox
identity, recipient fingerprint, message ID, ciphertext hash, protocol
version, creation and expiry times. The sender's Ed25519 public key travels in
the envelope and MUST hash to the claimed sender fingerprint; the recipient
verifies both independently.

## 4. Mailbox binding

`bind` (signed by the instance Ed25519 key over the bind statement):
- Server verifies the signature, recomputes the fingerprint, enforces the
  timestamp window (±600 s, same as the board).
- Fails closed: alias already bound to a different key (403), identity key
  already bound to a different active alias (403), malformed fields (400),
  bad signature (401).
- Stores a binding record: mailbox_id (server-generated UUID), node_id,
  ed25519_pub, fingerprint, x25519_pub, binding signature, status=active,
  created_ms, protocol_version. One active mailbox per identity key.
- The X25519 encryption public key is authenticated by the same Ed25519
  signature: it cannot be substituted without the identity key.

`lookup` (public, unauthenticated): returns binding records by alias or
fingerprint. Exposes exactly: mailbox_id, node_id, fingerprint, ed25519_pub,
x25519_pub, status, created_ms, protocol_version. No messages, no ciphertext.

## 5. Message lifecycle

`send` (signed by sender identity key over the envelope statement):
- Sender must hold an ACTIVE mailbox binding whose key matches the signing
  key (revoked senders fail closed).
- Recipient mailbox must exist, be ACTIVE, and the envelope's recipient
  fingerprint must match the mailbox's bound identity (altered recipient
  identities fail).
- Ciphertext hash must match the envelope (tampering fails), size <= 64 KiB.
- message_id globally unique (duplicate rejected 409); timestamp window
  enforced; expiry_ms must be in the future and at most 30 days out.
- Rate limit: max 60 messages per sender fingerprint per rolling hour
  (counted from stored records; coarse, stateless — a documented limit of
  serverless storage).
- Server stores ciphertext + envelope + signature with status=pending.
  Server acceptance is recorded and is DISTINCT from retrieval and from any
  human acknowledgment.

`fetch` is two-step and challenge-bound (approval condition B):
1. `fetch_begin` {mailbox_id or node_id}: server generates an unpredictable
   256-bit challenge, stores it single-use, bound to that mailbox, TTL 600 s.
   Possession of a mailbox address grants nothing else.
2. `fetch`: client signs the fetch statement over mailbox_id, its own
   ed25519_pub, the challenge, and now_ms. Server verifies the signature
   against the mailbox's BOUND key (identity proof by key possession),
   checks challenge validity (exists, unexpired, unused, bound to this
   mailbox), marks it used, returns non-expired pending messages, marks them
   retrieved, lazily deletes expired messages (retention, below).
   Static or replayed fetch signatures fail: challenges never repeat.

`ack` (signed by the mailbox identity key): records `retrieved`/`read`
attributed events as new records. Original messages are never rewritten;
corrections and disputes are new events.

## 6. Lifecycle, revocation, rotation

- States: `active`, `revoked`. Unknown states fail closed everywhere.
- `revoke` (signed by the mailbox identity key): status -> revoked. A revoked
  mailbox cannot send or receive. Its owner may still `fetch` (evidence
  preservation) but no new mail is accepted. Revocation does not touch other
  aliases of the same key and is not fingerprint-wide retirement.
- `rotate` (dual-signed, mirroring the board's ceremony): the OLD key signs
  the rotate statement, the NEW key signs a fresh bind statement over its own
  node_id/keys. Server verifies both, requires the old key to be the currently
  bound key, updates the binding in place (ed25519_pub, x25519_pub,
  fingerprint), records the rotation as an attributed event. No silent
  ownership transfer is possible without the old key. Historical messages
  keep their original envelopes and attribution (immutable).
- `expiry`: messages past expiry_ms are not returned and are deleted lazily at
  fetch time (no background daemon, per approval condition 9). Default cap:
  30 days.
- Deletion requests: v1 supports expiry-based deletion and revocation only.
  Per-message sender-initiated deletion is NOT implemented in v1.

## 7. Failure policy

Fail closed on: invalid signature, unknown/expired/used challenge, unknown or
mismatched binding, revoked mailbox, expired or malformed envelope, duplicate
message_id, unknown action. Error responses carry a code and the minimum
identifying fields; never ciphertext, never signatures, never key material.

## 8. Logging and retention

The function emits no logs of message contents, signatures, or challenges.
Retention: messages live until expiry (lazy deletion); ack and rotation events
are kept as the auditable record; bindings persist until revoked. Rollback of
the whole feature = delete the function + its three entities; the board and
its records are untouched.

## 9. Entity definitions (NOT yet created — deployment gate)

```
LanternMailBinding: mailbox_id, node_id, ed25519_pub, fingerprint,
  x25519_pub, binding_signature, status, created_ms, protocol_version
LanternMailMessage: message_id, mailbox_id, sender_fingerprint,
  sender_ed25519_pub, recipient_fingerprint, ciphertext, envelope,
  signature, status, created_ms, expiry_ms
LanternMailEvent: event_id, kind (ack|rotation|challenge), mailbox_id,
  message_id, payload, created_ms
```

## 10. Test battery (Phase 2)

A–J from the operator directive plus the six required additions: malformed
canonical serialization, expired fetch challenge, reused fetch challenge,
altered recipient identity, revoked binding, encryption-key substitution.
Every result reports environment honestly: two/three independent keypairs in
separate local processes, one operator sandbox (Tier 1 at best — never to be
reported as independent organizational participation). Live deployed-service
tests remain NOT TESTED until the Phase 4 deployment gate.
