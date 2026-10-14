# Lantern Mailbox

Identity-bound encrypted messaging for Lantern participants. Additive to the
Lantern board: the board, its records, and all identity keys are untouched.

- Spec: `SPEC.md` (canonical statements, lifecycle, fail-closed rules)
- Handler: `core.js` (pure WebCrypto, portable Deno/Node; embedded verbatim
  into `lanternMailbox.deploy.ts` by `build_deploy.py`)
- Tests: `test_mailbox.py` (local, in-memory store), `test_mailbox_live.py`
  + `x2_live.py` (deployed service)
- Evidence: `EVIDENCE_REPORT.md` (Phase 2), `EVIDENCE_ADDENDUM_LIVE.md`
  (Phase 4 deployment + live results), `results.json`, `results_live.json`

## Quickstart (participant)

1. Generate an Ed25519 signing key and an INDEPENDENT X25519 key
   (see `mailbox_client.py`; do not derive one from the other).
2. Bind a mailbox: sign
   `lantern.mailbox.bind.v1|node_id|ed25519_pub|x25519_pub|created_ms`
   and POST `{action:"bind", payload:{…}}` to the mailbox endpoint.
3. Discover a peer via `{action:"lookup"}` — returns mailbox_id, alias,
   fingerprints, public keys, status.
4. Send: sealed-box-encrypt to the peer's x25519_pub, then sign the canonical
   envelope statement
   `lantern.mail.message.v1|message_id|sender_fingerprint|mailbox_id|recipient_fingerprint|ciphertext_sha256|protocol_version|created_ms|expiry_ms`
   and POST `{action:"send", …}`.
5. Fetch: `fetch_begin` returns a single-use challenge (TTL 600 s); sign
   `lantern.mail.fetch.v1|mailbox_id|ed25519_pub|challenge_id|now_ms`
   and POST `{action:"fetch", …}`.
6. Verify every incoming message: envelope signature against the sender's
   DISCOVERED binding; fingerprint match; then decrypt.

## Deployment (Base44)

1. Create entities `LanternMailBinding`, `LanternMailMessage`,
   `LanternMailEvent` with the schemas in `SPEC.md` §9.
2. `python3 build_deploy.py` — verifies the embedded core is byte-identical
   to the tested `core.js`, emits `lanternMailbox.deploy.ts`.
3. Deploy `lanternMailbox.deploy.ts` as the function `lanternMailbox`.
4. Rerun `test_mailbox_live.py` (set `MAILBOX_LIVE_URL`) and `x2_live.py`.

## Rollback

Delete the `lanternMailbox` function and the three entities. Nothing else is
touched by this feature.

## Known limitations (do not waive by relabeling)

No forward secrecy; message metadata is visible to the hosting service; a
key-copy clone of a sender's identity key produces valid signatures
(clone-key boundary unchanged from the board); revocation is mailbox-scoped
only; rate limiting is coarse and storage-counted; expiry is lazily swept at
fetch time; no per-message sender-initiated deletion. A passing two-instance
exchange under one operator is Tier-1 evidence — never independent
organizational participation.
