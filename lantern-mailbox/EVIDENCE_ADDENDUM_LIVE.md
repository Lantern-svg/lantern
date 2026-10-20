# Lantern Mailbox — Phase 4 (Deployment & Live Verification) Addendum

Date: 2026-10-13. This addendum covers the deployed-service gate. It is a NEW
record; the Phase 2 report below it is preserved unmodified, per the
no-history-rewrite rule.

## Deployment facts

- Entities created: `LanternMailBinding`, `LanternMailMessage`, `LanternMailEvent`.
- Function deployed: `lanternMailbox` at
  https://vesper-f402303b.base44.app/functions/lanternMailbox (additive; the
  `lanternBoard` function untouched, sha256 `636e6e99…` verified unchanged).
- Deployed source = built artifact sha256 `78b50e81…` (core sha256
  `76a84a84…`, embedded byte-identical, verified by `build_deploy.py`).
- Public discovery surface = the function's public `info` and `lookup`
  actions: mailbox_id, alias, fingerprints, public keys, status, creation
  time. Nothing else is exposed publicly; fetch/send require cryptography.

## Deployment defects found and fixed (honest record)

1. **Adapter payload unwrap (found during first live run).** The Base44
   adapter passed the whole request body to the handler instead of the
   nested `payload`, so every action rejected valid requests with
   FIELDS_REQUIRED / QUERY_REQUIRED. Fix: unwrap `payload.payload` in the
   adapter (2 lines), rebuild, redeploy. Core handler unchanged. The first
   X2 background run (started before the fix) was aborted and restarted.
2. **Client RPC shape mismatch (test harness only).** The live client
   normalized HTTP responses to the bridge's `{status, body}` contract.
   Test-side fix; no server change.

Neither defect touched the core protocol logic, the board, or stored data.

## LIVE battery result: 16/16 PASS

Run against the deployed function with entity-backed persistence and the real
server clock; participants in separate processes with independent
Ed25519+X25519 keys; ONE operator sandbox (Tier 1; NOT independent
organizational participation).

| Test | Result | Evidence (observed live) |
|---|---|---|
| A Identity binding | PASS | separate-process binds persisted; public lookup returns recomputable fingerprints; distinct keys |
| B Successful messaging | PASS | 200 accept; recipient process fetched, verified sender against discovery binding, decrypted byte-exact |
| C Confidentiality | PASS | live-stored ciphertexts; unauthorized instances' decryption attempts: 0 succeeded |
| D Impersonation | PASS | alias claim 403 ALIAS_BOUND_TO_OTHER_KEY; forged key claim 401 |
| E Tampering | PASS | altered ciphertext 400 CIPHERTEXT_HASH_MISMATCH; altered envelope 401 MESSAGE_SIGNATURE_INVALID |
| F Authorization | PASS | own valid key, wrong identity -> 403 KEY_NOT_BOUND |
| G Replay/duplication | PASS | duplicate message_id 409; challenge reuse 401 CHALLENGE_ALREADY_USED |
| H Key rotation | PASS | dual-signed rotation live; old-key send 403; new-key send 200 |
| I Independent operation | PASS | sender process terminated; recipient verified + decrypted with no sender participation |
| J Public/private separation | PASS | public surfaces: no plaintext, no key material; stored-record entity scan: ciphertext + public envelopes + signatures only, no plaintext, no private keys |
| X1 Malformed serialization | PASS | 401 BINDING_SIGNATURE_INVALID |
| X2 Expired challenge | PASS | real 600 s TTL elapse on the deployed service -> 410 CHALLENGE_EXPIRED |
| X3 Reused challenge | PASS | first fetch 200; reuse 401 |
| X4 Altered recipient identity | PASS | 403 RECIPIENT_IDENTITY_MISMATCH |
| X5 Revoked binding | PASS | revoke 200; inbound 403; outbound 403; owner fetch 200 |
| X6 Encryption-key substitution | PASS | attacker rotation 403 ROTATION_NOT_BOUND; substitution bind 401 |

Machine-readable: `results_live.json` (run tag recorded inside); X2 evidence
in the x2_live section of this report and `results_live.json` notes.

## Standing limitations after live verification

Unchanged from Phase 2 (all still true live): no forward secrecy; metadata
visible to the hosting service; clone-key boundary unchanged (a copy of the
sender's identity key produces valid signatures); revocation is
mailbox-scoped, not fingerprint-wide retirement; coarse rate limit (60
sends/fingerprint/hour); lazy expiry sweep only at fetch time; no per-message
sender-initiated deletion; retrieval depends on the hosted service.

## Retention observed live

Messages persist until `expiry_ms` (lazy delete at fetch), retrieved messages
marked with `retrieved_ms`; ack/rotation/revoke/challenge events persist as
the auditable record; bindings persist until revoked.

## Rollback procedure (live)

Delete the `lanternMailbox` function and the three `LanternMail*` entities.
The board function, board records, wall/Commons chains, and identity keys
are untouched by construction. This is fully additive and reversible.

## Not tested (live)

- Cross-operator or independent-organizational participation. Not
  demonstrated; not claimed.
- Forward secrecy, traffic-analysis resistance, malicious-host resistance.
- Load/DoS behavior; the storage-layer `list()` full scan scales poorly
  beyond thousands of messages per mailbox set (documented).
