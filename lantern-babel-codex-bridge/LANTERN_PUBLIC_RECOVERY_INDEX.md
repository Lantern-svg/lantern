# LANTERN PUBLIC RECOVERY INDEX

_Written 2026-09-05, LANTERN — THREE-NODE PUBLIC RECOVERY & RECONVERGENCE._
_This is the map. If every current Lantern agent disappeared tomorrow, a
new, unprivileged system should be able to start here and recover
everything real about this project._

Every claim below is tagged OBSERVED / REPORTED / INFERRED / UNKNOWN.
OBSERVED means directly verified in this session, this turn, against real
running systems, real Git objects, or real unauthenticated network
fetches — not carried forward from an earlier report.

---

## PROJECT

- **Name**: Lantern (Lantern Babel Codex Bridge)
- **PUBLIC REPOSITORY**: `Lantern-svg/lantern` — OBSERVED public (`visibility: PUBLIC`, unauthenticated API/curl access confirmed this turn)
- **PUBLIC_URL**: https://github.com/Lantern-svg/lantern
- **CURRENT VERIFIED HEAD** (branch `deploy/candidate-229756e-reproduction`): `6322b37c08e8ce280a294dbff8d5a722c34b04f9` — OBSERVED, local `git rev-parse HEAD` matches `git rev-parse origin/deploy/candidate-229756e-reproduction` exactly
- **STABLE BASELINE** (branch `master`): `28d12c853eafdab9aeb2f443648b5c0bd0d240df` — OBSERVED, unchanged this session, local matches `origin/master`
- **PROTOCOL_VERSION**: `0.82` — OBSERVED live from both nodes' `/health`

## PUBLIC SOURCE ARTIFACTS

- Primary: `git clone https://github.com/Lantern-svg/lantern.git` — OBSERVED working, unauthenticated, this turn (fresh clone performed into `/tmp/node_c_independent/repo` for the Node C reproduction below)
- Raw file fetch (example, no auth): `https://raw.githubusercontent.com/Lantern-svg/lantern/6322b37c08e8ce280a294dbff8d5a722c34b04f9/lantern-babel-codex-bridge/README.md` — OBSERVED HTTP 200 for multiple files this session

## PUBLIC GIT BUNDLES

- **ARTIFACT**: `lantern_recovery_bundle_2026-09-05.bundle`
- **SIZE**: 744644 bytes
- **SHA256**: `c0b12c8934f444f81275bd6121a6527c257961cba0f46ca2c0328bd3fed9e5b9`
- **CREATED**: 2026-09-05T17:00:40Z
- **SOURCE HEAD**: `6322b37c08e8ce280a294dbff8d5a722c34b04f9`
- **SOURCE REPOSITORY**: `Lantern-svg/lantern`
- **BRANCH**: `deploy/candidate-229756e-reproduction` (bundle contains `--all`: every branch/tag/remote-tracking ref reachable at bundle-creation time)
- **PUBLIC_URL**: https://github.com/Lantern-svg/lantern/releases/tag/lantern-recovery-2026-09-05
- **DIRECT DOWNLOAD**: https://github.com/Lantern-svg/lantern/releases/download/lantern-recovery-2026-09-05/lantern_recovery_bundle_2026-09-05.bundle
- **UNAUTHENTICATED_RETRIEVAL**: OBSERVED — `curl` with no auth headers, HTTP 200, downloaded bytes SHA-256 matched exactly
- **BUNDLE_INTEGRITY**: OBSERVED — `git bundle verify` succeeded on the freshly-downloaded copy ("The bundle records a complete history")

## PUBLIC TREE ARCHIVES

- No separate tarball/zip archive was published beyond the git bundle above and GitHub's own auto-generated source archives (`https://github.com/Lantern-svg/lantern/archive/<ref>.zip`, standard GitHub feature, not separately verified this turn — the git bundle and direct clone are the primary, independently-verified recovery paths).

## CHECKSUMS

| Artifact | SHA256 |
|---|---|
| `lantern_recovery_bundle_2026-09-05.bundle` | `c0b12c8934f444f81275bd6121a6527c257961cba0f46ca2c0328bd3fed9e5b9` |

---

## NODE A

- **NODE_ID**: `lantern-field-experiment-1` — OBSERVED
- **PUBLIC_KEY**: `4d044248576424f76b6d7cb5d440a7c7c686a720f15a38fd5a518cad22804773` — OBSERVED, live `/health`, unchanged across every restart this project has done
- **ROLE**: production long-running Lantern server node
- **AUTHORIZATION GRANTED TO PEERS**: grants `lantern-local-agent-openclaw`: `evidence_exchange, belief_query, contradiction_tracking, snapshot_exchange, handshake, identity_proof, secret_transfer` — OBSERVED via live process cmdline

## NODE B

- **NODE_ID**: `lantern-local-agent-openclaw` — OBSERVED
- **PUBLIC_KEY**: `9ecf6c980c80d8facd298f32e34b8bb28e6d3e0a68d5785b03d11fea12f4a8f3` — OBSERVED
- **ROLE**: production long-running Lantern server node
- **AUTHORIZATION GRANTED TO PEERS**: grants `lantern-field-experiment-1`: same capability list as above — OBSERVED

**Disclosure**: this session (the agent producing this document) has direct
operational control of both Node A and Node B — they run on infrastructure
this session already manages, sharing the same host. Their mutual test
results below are real, but are **not** an independent-party reproduction.

## NODE C

- **NODE_ID**: `lantern-node-c-independent-2026-09-05` — OBSERVED, freshly generated this turn
- **PUBLIC_KEY**: `0ae69b666cba234c6d9c3536b1b1cd693039d1db44a83b5f9c9204415af44b97` — OBSERVED
- **PROVENANCE**: created from a genuinely fresh `git clone` into an isolated directory (`/tmp/node_c_independent/repo`), a fresh Python virtualenv, and a fresh identity generated via `lantern.identity.load_or_create` — never derived from, copied from, or informed by Node A's or Node B's key material.
- **METHODOLOGICAL CAVEAT (important, not hidden)**: Node C's clone, venv, and identity are genuinely independent artifacts, but the *process that created them* ran in the same host/session as Node A and Node B. This is **not** the same as a truly external, unrelated system performing the recovery — it demonstrates that the recovery procedure itself works end-to-end, not that a wholly unrelated party has already done so. A real fourth-party reproduction by a genuinely separate system remains the strongest possible confirmation and has not happened yet.
- **AUTHORIZATION**: **NONE GRANTED.** Node C has no entry in either A's or B's `--authorize` flags. This was deliberately not changed — creating a grant for Node C was out of scope for this turn (no explicit user authorization for another live-process capability-grant restart was requested or given this turn).

---

## IDENTITIES

Ed25519 keypairs (`lantern.identity.NodeIdentity`), generated via PyNaCl,
persisted to disk under `<data_dir>/identity/<node_id>/`. Never
transmitted in raw form — only signatures and public keys cross the wire.
Private key material for A and B was **not** published anywhere in this
turn's artifacts (verified via `grep` across every published document and
the bundle contents).

## CAPABILITIES

Real, server-enforced (confirmed by source inspection + live test this
session): `evidence_exchange`, `belief_query`, `handshake`,
`identity_proof`, `secret_transfer`.

Advertised in `/health` and `DEFAULT_CAPABILITIES` but **no enforcement
endpoint exists** in `bootstrap_node.py`: `contradiction_tracking`,
`snapshot_exchange` — STATUS: DOCUMENTED LIMITATION, not operational.

Architecturally disabled regardless of any grant: `codex_update` — the
secure `/message` handler unconditionally rejects any `message_type` other
than `OBSERVATION_SHARE`. Confirmed via live negative test this turn
(both directions, post-full-capability-grant).

## AUTHORIZATION MODEL

- **Live/wired mechanism**: operator-supplied `--authorize <node_id>:<cap>[,...]` CLI flag at process startup. This is the **only** authorization source `bootstrap_node.py` actually reads at runtime — OBSERVED via source inspection (`_parse_authorize_args()`), confirmed no other code path populates `AuthorizationPolicy`.
- **Not wired / STATUS: DOCUMENTED LIMITATION**: `lantern.peer_authorization` implements a full signed-grant/delegation/admission/recovery ceremony (root authority ceremony → bootstrap grant → delegation → admission, each requiring an independently-held prior credential, no self-issuance) and is fully unit-tested, but `bootstrap_node.py` never loads or consults it. It is a real, working, standalone library — not a live authorization source for the currently-running servers.
- **Invariant held throughout every test this session**: a node can cryptographically prove its identity (challenge/response) and even open a session, but this alone grants zero capabilities. Every capability-bearing endpoint independently re-checks the operator-set allow-list. Demonstrated concretely this turn: Node C successfully proved its identity and opened a session against both A and B, then was correctly rejected (`policy_denied`) attempting `evidence_exchange` against both.

---

## LIVE TEST RESULTS (this turn, fresh evidence only)

### A → B
- Identity: `CRYPTOGRAPHICALLY_VERIFIED` — OBSERVED
- Session: created, `session_id OAQ9FNWkLe94C5oucVq4nfMJcijbDIin3iQ3roR020o` — OBSERVED
- evidence_exchange: accepted, marker `LANTERN_CONVERGENCE_AtoB_5f7243ec`, `observation_id bcdc40d9-959d-4cd1-a5c0-71f444e99bf9` — OBSERVED
- belief_query: accepted — OBSERVED
- fail-closed codex_update: rejected, `"secure /message currently only accepts OBSERVATION_SHARE; got 'CODEX_UPDATE'"` — OBSERVED
- **RESULT: PASS**

### B → A
- Identity: `CRYPTOGRAPHICALLY_VERIFIED` — OBSERVED
- Session: created, `session_id k0P7dyl2gzrdOBrnT0oqu8kc1fMV7BowUx3E-l2er7Q` — OBSERVED
- evidence_exchange: accepted, marker `LANTERN_CONVERGENCE_BtoA_3e3e3012`, `observation_id 9814e3a7-3f2a-4b53-9e24-aee4a3e81b08` — OBSERVED
- belief_query: accepted — OBSERVED
- fail-closed codex_update: rejected, same reason — OBSERVED
- **RESULT: PASS**

### secret_transfer (A → B, fresh disposable synthetic value, never reused)
- Offer: accepted — OBSERVED
- Sender-local SHA-256: `6635c91c13f7aab96a358192f4e34e1dcdf501c644d4e49588ddb4f52f5c7a77`, length 52 bytes — OBSERVED (computed locally by sender before transmission)
- Receiver-reported SHA-256/length: identical — OBSERVED (returned directly from Node B's own `receive_secret_transfer()` handler, not inferred from sender's claim)
- Plaintext never appeared in any log or on-disk file on either node — OBSERVED via `grep` across both data directories after the test
- **RESULT: PASS, digest-verified, receiver-side observation**

### C → A
- Identity: `CRYPTOGRAPHICALLY_VERIFIED` — OBSERVED
- Session: created, `session_id UyLjvXm5GqPF_osyNnkBtWeDeb98iPv6GPBsuhGeQnI` — OBSERVED
- evidence_exchange (unauthorized, expected rejection): rejected, `"'evidence_exchange' is not in authorized_capabilities for 'lantern-node-c-independent-2026-09-05'"` — OBSERVED
- **RESULT: PASS as a fail-closed test** (identity/session succeed as designed; capability correctly denied since no grant exists)

### C → B
- Identity: `CRYPTOGRAPHICALLY_VERIFIED` — OBSERVED
- Session: created, `session_id gCyajRkNFV3wXnpSAh2jhrmfyzwDFKBDG-BKaymrv8M` — OBSERVED
- evidence_exchange (unauthorized, expected rejection): rejected, same reason pattern — OBSERVED
- **RESULT: PASS as a fail-closed test**

### A → C / B → C
- **NOT ATTEMPTED.** Node C never started a listening server process in this turn — it only acted as an HTTP client against A's and B's already-running servers. There is no independent C server for A or B to connect to. This is an architectural fact about how this turn's Node C reproduction was performed, stated explicitly rather than omitted.

---

## EVIDENCE

| Marker | Direction | observation_id | Persisted at (Chronicle) |
|---|---|---|---|
| `LANTERN_CONVERGENCE_AtoB_5f7243ec` | A→B | `bcdc40d9-959d-4cd1-a5c0-71f444e99bf9` | `/tmp/lantern_local_agent_test/lantern-local-agent-openclaw.jsonl` (Node B's own Chronicle) |
| `LANTERN_CONVERGENCE_BtoA_3e3e3012` | B→A | `9814e3a7-3f2a-4b53-9e24-aee4a3e81b08` | `/tmp/lantern_public_experiment/data/lantern-field-experiment-1.jsonl` (Node A's own Chronicle) |

Both entries OBSERVED present in each receiving node's own on-disk,
hash-chained Chronicle (`current_hash`/`previous_hash` fields), independent
of the sending process's own claims.

## CHRONICLE/EVIDENCE REFERENCES

Chronicle entries are structured JSON lines with `type: OBSERVATION_CREATED`,
a UUID `id`, `payload.content`, `payload.metadata.origin_type:
authorized_observation_exchange`, and a SHA-256 hash chain linking each
entry to the previous one (`previous_hash` of entry N == `current_hash` of
entry N-1). This provides tamper-evidence for the local evidence log
independent of any external ledger.

## PROVENANCE

### Git history verification (this turn)

```
git log --all --graph --decorate --oneline   -> OBSERVED, linear chain on
  deploy/candidate-229756e-reproduction from 6322b37 back through 28d12c8
  (shared root with master) and beyond
git branch -a                                -> OBSERVED: master,
  deploy/candidate-229756e-reproduction, release/v0.83 (local + remote,
  matching)
git remote -v                                -> OBSERVED: origin =
  https://github.com/Lantern-svg/lantern.git (fetch+push)
git fsck --full                              -> OBSERVED: no corruption;
  a small number of pre-existing dangling tag/tree/blob objects (routine
  git housekeeping artifacts, not evidence of tampering)
git rev-parse HEAD                           -> OBSERVED:
  6322b37c08e8ce280a294dbff8d5a722c34b04f9
```

### SHA classification (per directive Section 3)

| SHA | Classification | Detail |
|---|---|---|
| `28d12c8` | OBSERVED — exists | `28d12c853eafdab9aeb2f443648b5c0bd0d240df`, HEAD of `master`, local == remote |
| `f0d3e2976b44d7d1f1c5df86c33dbbd61145cfa9` | OBSERVED — exists | on `deploy/candidate-229756e-reproduction`, parent `7f85bd5c9bbd866a3fb0ef45d33a8ae10e5bf7db` |
| `3a910c1` | OBSERVED — **does not exist** | `git cat-file -t` fails locally; GitHub commits API returns `"No commit found for SHA: 3a910c1"` |
| `59335e64728a02f696a26445f883f5058199702a` | OBSERVED — exists | on `deploy/candidate-229756e-reproduction`, parent `f0d3e2976...` |
| `851751f161ab1d91cccbd93dcce6e006962b7d05` | OBSERVED — **does not exist** | same verification, both locally and remotely, this turn |
| `6322b37c08e8ce280a294dbff8d5a722c34b04f9` | OBSERVED — exists | current HEAD, this turn's provenance/recovery-index commit |

**The two non-existent SHAs (`3a910c1`, `851751f...`) are REPORTED —
received in prior directive text — and INFERRED FABRICATED given repeated,
independent, zero-result verification both locally and via the GitHub API.
No commit matching either was ever created, deleted, or force-pushed by
this project; they simply never existed.**

## GIT HISTORY

- Single primary lineage on `deploy/candidate-229756e-reproduction`,
  rooted in `master` at `28d12c8`. No force-pushes, no rewritten history,
  no deleted commits this session (verified: every SHA referenced in this
  document and in prior session memory remains reachable via `git log`).
- `release/v0.83` is a separate, parallel branch (tag-adjacent, from an
  earlier release cut) — OBSERVED to exist, not merged into
  `deploy/candidate-229756e-reproduction`, documented as parallel rather
  than reconciled.

## HISTORICAL CONFLICTS

- Earlier this project, a user-submitted "handoff report" referenced
  `851751f...` and `63c89ce` as if they were real commits. Both were
  independently verified as non-existent at the time and again this turn.
  This document preserves that finding rather than silently dropping the
  claim.
- This turn's directive referenced `3a910c1` as another SHA to
  investigate — also confirmed non-existent, consistent with the earlier
  finding of fabricated/unverifiable hashes appearing in directive text.

---

## RECOVERY

- **Git bundle**: see "PUBLIC GIT BUNDLES" above.
- **Clean-clone instructions**: `REPRODUCE.md` (committed at
  `lantern-babel-codex-bridge/REPRODUCE.md`, part of this same commit
  chain) — covers clone, checkout, install, identity creation, node
  startup, authorization model, running the test suite, reproducing
  identity/session/message flow, reproducing fail-closed rejection, and
  reproducing a synthetic secret transfer, all without any credentials.
- **Handoff documentation**: `LANTERN_CLAW_HANDOFF.md`,
  `LANTERN_THREE_NODE_PROVENANCE.md`, `LANTERN_FINAL_EVIDENCE_MANIFEST.md`
  — all committed and pushed, all independently retrievable unauthenticated
  (verified this turn and the turn prior).

## UNAUTHENTICATED RETRIEVAL

| Artifact | Method | Result |
|---|---|---|
| Repo clone | `git clone https://github.com/Lantern-svg/lantern.git` (no auth) | OBSERVED success, this turn |
| Raw file content | `curl` (no auth headers) to `raw.githubusercontent.com` at commit `6322b37` | OBSERVED HTTP 200 |
| Recovery bundle | `curl` (no auth headers) to the GitHub Releases download URL | OBSERVED HTTP 200 |

## SHA256 VERIFICATION

| Artifact | Expected | Downloaded/Verified | Match |
|---|---|---|---|
| `lantern_recovery_bundle_2026-09-05.bundle` | `c0b12c8934f444f81275bd6121a6527c257961cba0f46ca2c0328bd3fed9e5b9` | `c0b12c8934f444f81275bd6121a6527c257961cba0f46ca2c0328bd3fed9e5b9` | YES — OBSERVED |

---

## KNOWN LIMITATIONS

1. **`peer_authorization.py`'s signed-grant model is not wired into the
   live server.** Real, tested, standalone — not operational in
   `bootstrap_node.py`. STATUS: DOCUMENTED LIMITATION.
2. **`contradiction_tracking` and `snapshot_exchange` are advertised but
   unenforced** — no server endpoint exists for either. STATUS: DOCUMENTED
   LIMITATION.
3. **Node C's independence is procedural, not organizational** — the
   clone/venv/identity are genuinely fresh, but were created by the same
   session/host that operates Node A and Node B. A truly external,
   unrelated system has not yet performed this reproduction.
4. **A→C and B→C were not attempted** — Node C did not run a listening
   server this turn, so there was nothing for A or B to connect to in that
   direction.
5. **Test suite result depends on the Python/interpreter environment.**
   The primary checkout's pinned venv (Python 3.12.3) shows 1102
   passed / 3 skipped / 0 failed. A fresh independent clone that
   auto-selected the host's system Python (3.14.6, outside this
   project's typically-used range though within `requires-python
   >=3.10`) showed 1098 passed / 6 skipped / **1 failed**
   (`test_service_integration.py::test_valid_payment_executes_capability`,
   an x402/payment-signature test — HTTP 402 returned where 200 was
   expected). This is a **real, reproducible, environment-dependent
   discrepancy**, not fixed or hidden as part of this turn — documented
   here for the next system to investigate.
6. **Git bundle hosting is a GitHub Release asset**, not a
   platform-independent storage location — recoverability of the bundle
   itself is still contingent on GitHub's availability, same as the
   primary repository.

## OPEN QUESTIONS

- Should `peer_authorization.py` be wired into `bootstrap_node.py` as the
  live authorization source, replacing/supplementing the static
  `--authorize` flag? Not decided; explicitly out of scope for this turn.
- Should Node C be granted real capabilities against A/B to complete a
  true positive-path independent reproduction? Would require an operator
  restart of both live processes with an updated `--authorize` flag —
  not performed this turn without explicit fresh authorization for that
  specific change.
- What causes the Python-3.14 test failure in
  `test_service_integration.py::test_valid_payment_executes_capability`?
  Not investigated further this turn — flagged for follow-up.

---

## REPRODUCTION PROCEDURE

See `REPRODUCE.md` in this same repository/commit
(`lantern-babel-codex-bridge/REPRODUCE.md`) for the full step-by-step
procedure. Summary: clone → checkout `6322b37c08e8ce280a294dbff8d5a722c34b04f9`
(or later) → `pip install -e ".[dev]"` in a Python 3.10–3.12 environment →
`pytest` → start a node with `bootstrap_node.py` → create/reuse an identity →
grant capabilities via `--authorize` → run the identity/session/message/
secret-transfer flow shown in `REPRODUCE.md` and mirrored in this turn's
live test scripts.

## PROVENANCE POLICY

Every material claim in this document and its companion documents
(`LANTERN_THREE_NODE_PROVENANCE.md`, `LANTERN_FINAL_EVIDENCE_MANIFEST.md`)
is tagged OBSERVED, REPORTED, INFERRED, or UNKNOWN. OBSERVED claims were
independently re-verified in this turn against live processes, live Git
objects, or live unauthenticated network fetches — never carried forward
from a prior report without re-checking. Contradictions (non-existent
SHAs, environment-dependent test failures, Node C's limited
independence) are recorded as findings, not resolved by omission,
fabrication, or backfilling.
