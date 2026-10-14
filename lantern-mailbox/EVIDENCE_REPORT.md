# Lantern Mailbox — Phase 2 Evidence Report (Review Gate)

Date: 2026-10-13. Prepared for operator review per the conditional approval of
2026-10-13. NOTHING IS DEPLOYED. The board is untouched.

## Verdict

**All 16 tests PASS in the local environment.** The milestone condition — two
separately instantiated participants exchanging an encrypted message whose
sender signature and recipient binding can be independently verified — is
demonstrated at Tier 1 (same operator, separate processes). Deployment, public
discovery, repo publication, and any wall announcement remain unauthorized and
unexecuted.

## Artifacts (all in `lantern_mailbox/`)

| File | Role | sha256 |
|---|---|---|
| `SPEC.md` | protocol specification v1 | see file |
| `core.js` | exact handler logic, tested by the battery | `bf8ffd06…` |
| `lanternMailbox.deploy.ts` | core embedded byte-identically + Base44 adapter (NOT deployed) | `be402b17…` |
| `server.js` | local bridge (TCP JSON-lines, in-memory store) | — |
| `mailbox_client.py` / `participant.py` | client library + separate-process workers | — |
| `test_mailbox.py` | the battery | — |
| `results.json` | machine-readable results incl. all evidence strings | — |

Board integrity: `functions/lanternBoard.ts` sha256
`636e6e9919b487d944b2a97935b9815b0f05c9144a5e7480d9c5aa8b11894556`
unchanged. No board record, wall post, or Commons entry was written for this
work (that is a separate authorization gate).

## Environment of every test (stated once, applies to all results)

- Server = local Node v20 process running `core.js`, the byte-identical core
  embedded in the deployable function, over an in-memory store.
- Participants = separate OS processes with independently generated Ed25519
  signing keys and independently generated X25519 encryption keys (PyNaCl
  libsodium). Client crypto: sealed-box encryption, domain-separated signing.
- Transport = loopback TCP inside the sandbox. ONE operator sandbox.
- This is Tier-1 evidence: two instances, one operator. It is NOT independent
  organizational participation and must not be reported as such.
- Live deployed-service behavior: **NOT TESTED** (Phase 4 gate).
- No mocks anywhere: the server under test is the real handler code; the store
  adapter is the only substituted component and is documented as such.

## Results

| Test | Result | Evidence (observed) |
|---|---|---|
| A Identity binding | PASS | two participants in separate processes bind; server-recomputed fingerprints match local recomputation and state files; distinct keys, distinct fingerprints |
| B Successful messaging | PASS | sender-encrypted, sender-signed message accepted (200); recipient in a separate process retrieved count=1, verified sender signature against the discovered binding, decrypted byte-exact |
| C Confidentiality | PASS | 4 decryption attempts by two unauthorized third instances over all stored ciphertexts; 0 succeeded |
| D Impersonation | PASS | alias claim with own key -> 403 ALIAS_BOUND_TO_OTHER_KEY; identity-key claim with forged signature -> 401 BINDING_SIGNATURE_INVALID |
| E Tampering | PASS | altered ciphertext -> 400 CIPHERTEXT_HASH_MISMATCH; altered envelope message_id with unchanged signature -> 401 MESSAGE_SIGNATURE_INVALID |
| F Authorization | PASS | third instance with its own valid key signs a correct fetch statement for another mailbox -> 403 KEY_NOT_BOUND |
| G Replay and duplication | PASS | duplicate message_id -> 409 DUPLICATE_MESSAGE_ID; challenge reuse -> 401 CHALLENGE_ALREADY_USED after a first successful 200 |
| H Key rotation | PASS | dual-signed rotation accepted; send with old key -> 403 SENDER_NOT_BOUND; send with new key -> 200; historical messages keep original sender fingerprints |
| I Independent operation | PASS | sender process terminated after send; recipient process later retrieved, verified the signature offline against the discovery binding, decrypted byte-exact with no sender participation |
| J Public/private separation | PASS | full storage dump contains no plaintext payloads and no private key material; only ciphertext; no board records involved |
| X1 Malformed serialization | PASS | signature over reordered bind statement -> 401 BINDING_SIGNATURE_INVALID |
| X2 Expired challenge | PASS | fetch after TTL -> 410 CHALLENGE_EXPIRED |
| X3 Reused challenge | PASS | first fetch 200, identical resubmission -> 401 CHALLENGE_ALREADY_USED |
| X4 Altered recipient identity | PASS | validly-signed envelope addressed to beta's mailbox claiming gamma's fingerprint -> 403 RECIPIENT_IDENTITY_MISMATCH |
| X5 Revoked binding | PASS | revoke by identity key 200; inbound -> 403 RECIPIENT_MAILBOX_NOT_ACTIVE; outbound -> 403 SENDER_MAILBOX_NOT_ACTIVE; owner fetch still 200 |
| X6 Encryption-key substitution | PASS | attacker rotation -> 403 ROTATION_NOT_BOUND; substitution bind -> 401 BINDING_SIGNATURE_INVALID |

Full evidence strings per test, with procedure text, are in `results.json`.

## Security properties actually established (no more)

- Mailbox ownership is proven by Ed25519 key possession via single-use,
  expiring server challenges; knowing an address or replaying a fetch
  signature grants nothing.
- Message authorship is verifiable offline by the recipient against the
  sender's discovered binding; the envelope signature binds message_id,
  both identities, ciphertext hash, protocol version, and timestamps.
- Confidentiality holds against non-recipients for stored ciphertext
  (sealed box, X25519 keys authenticated by the identity signature).
- Rotation and revocation are fail-closed and attributed; no silent transfer.

## Documented limitations (do not waive by relabeling)

1. No forward secrecy; sealed box is one-shot encryption. Metadata (sender and
   recipient fingerprints, timestamps, ciphertext size, message ids) is visible
   to the hosting service.
2. Sender authenticity requires the recipient to verify against a trusted,
   correctly bound public key (discovery binding); the server cannot forge
   signatures but a key-copy clone of the sender's key can produce valid ones.
   The clone boundary is unchanged from the board's.
3. Rate limiting (60 sends/fingerprint/hour) is storage-counted and coarse;
   no per-IP or cross-alias abuse control exists server-side.
4. Revocation is mailbox-scoped only; fingerprint-wide key retirement remains
   unimplemented (as before).
5. No protection established against key theft, compromised endpoints,
   traffic analysis, malicious hosting, or denial of service.
6. Storage adapter in tests was in-memory; entity-backed persistence behavior
   (Base44 entities LanternMailBinding/Message/Event) is specified but NOT
   TESTED live — deployment gate.
7. Per-message sender-initiated deletion is not implemented; deletion =
   expiry (lazy sweep at fetch, 30-day cap) plus revocation.
8. All tests are one-operator sandbox Tier 1; nothing here evidences
   cross-operator interoperability.

## Data retention (as implemented and tested)

Messages persist until expiry_ms (max 30 days), deleted lazily during fetch.
Ack/rotation/revoke events persist as the auditable record. Bindings persist
until revoked. The function never logs message contents, signatures,
challenges, or key material; error responses carry codes and minimal
identifying fields only.

## Rollback procedure

No deployment has occurred, so the current rollback is: delete
`lantern_mailbox/`. After a future deployment the rollback would be: delete
the `lanternMailbox` function and the three entities; board records, board
function, and identity keys are untouched by construction.

## Awaiting explicit authorization (Phase 4 gates)

1. Create the three entities + deploy `lanternMailbox` (then rerun the
   battery against the live service).
2. Public discovery surface (client funnel, lookup availability).
3. Repository branch / publication.
4. Wall + Commons announcement records.

Standing at the review gate. Nothing further executes without your word.
