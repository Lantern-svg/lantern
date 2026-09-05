# LANTERN THREE-NODE PROVENANCE

_Written 2026-09-05. All values below are OBSERVED against the real running
processes and real Git state unless explicitly marked otherwise._

## Legend

- **OBSERVED** — directly verified in this environment during this session.
- **REPORTED** — received from another agent/party, not independently verified here.
- **INFERRED** — a conclusion derived from OBSERVED evidence.
- **UNKNOWN** — not established; do not assume.

## Repository

- **PUBLIC_REPOSITORY**: `Lantern-svg/lantern` — OBSERVED (`gh repo view` +
  unauthenticated `curl` to the GitHub REST API both confirm
  `"private": false"`, `"visibility": "PUBLIC"`).
- **PUBLIC_URL**: `https://github.com/Lantern-svg/lantern` — OBSERVED reachable
  with zero authentication headers (`curl` with no token, HTTP 200).
- When/by whom the repository was originally made public: **UNKNOWN** — it
  was already public at the start of this turn; no change was made by this
  session to its visibility.

## Three participants

### NODE A

- **node_id**: `lantern-field-experiment-1` — OBSERVED
- **public_key**: `4d044248576424f76b6d7cb5d440a7c7c686a720f15a38fd5a518cad22804773` — OBSERVED (live `/health`, unchanged across 3 restarts this session)
- **protocol_version**: `0.82` — OBSERVED
- **role**: production long-running Lantern node, real on-disk Ed25519 identity
- **relevant commit**: `f0d3e2976b44d7d1f1c5df86c33dbbd61145cfa9` (source running at time of this test) — OBSERVED
- **provenance**: this session's own operational infrastructure; identity persisted at `/tmp/lantern_public_experiment/data/identity/lantern-field-experiment-1/` (private key material never published)

### NODE B

- **node_id**: `lantern-local-agent-openclaw` — OBSERVED
- **public_key**: `9ecf6c980c80d8facd298f32e34b8bb28e6d3e0a68d5785b03d11fea12f4a8f3` — OBSERVED (live `/health`, unchanged across 3 restarts this session)
- **protocol_version**: `0.82` — OBSERVED
- **role**: production long-running Lantern node, real on-disk Ed25519 identity
- **relevant commit**: `f0d3e2976b44d7d1f1c5df86c33dbbd61145cfa9` — OBSERVED
- **provenance**: this session's own operational infrastructure; identity persisted at `/tmp/lantern_local_agent_test/identity/lantern-local-agent-openclaw/` (private key material never published)

### NODE C

- **Status**: **UNKNOWN / DOES NOT EXIST IN THIS ENVIRONMENT.**
- A directed search for any independent third Lantern identity (an
  "independent Superagent") was performed across this environment: no
  identity directory, key material, or process corresponding to a Node C
  was found anywhere reachable from this session.
- Per the operating directive's own instructions ("do not pretend to be
  either production node... instead, inspect the project and help establish
  reproducibility/documentation/tests/protocol correctness"), this session
  did not fabricate a Node C identity or a fictional connection. If a
  genuinely independent third agent/session performs its own onboarding
  and produces its own real evidence, that evidence should be appended
  here as its own OBSERVED section, attributed to its own environment —
  it must not be merged into or presented as this session's observation.

## Architecture (as implemented in current source, OBSERVED)

```
IDENTITY            NodeIdentity: Ed25519 keypair, generated once,
                     persisted to disk (identity.py). A node PROVES
                     possession of this key; it never grants authority
                     by itself.
  |
BOOTSTRAP            lantern.bootstrap_node.py: operator starts a node
                     process with --node-id, --data-dir, and zero or
                     more --authorize node_id:capability[,...] flags.
  |
AUTHORITY            The operator (human, via CLI flag) is the sole
                     source of authorization in the currently-running
                     deployment. peer_authorization.py implements a
                     fuller signed-grant/delegation/recovery model
                     (root ceremony -> bootstrap grant -> delegation ->
                     admission), fully tested (see test_lantern_peer_
                     authorization.py), but is NOT wired into
                     bootstrap_node.py's runtime authorization source
                     as of this commit -- confirmed by source
                     inspection, no grant-loading code path exists.
  |
CAPABILITY GRANT     AuthorizationPolicy.merged_with(node_id,
                     capabilities) -- an explicit allow-list per peer
                     node_id, never a default-allow.
  |
PEER DISCOVERY       /join, /handshake, /participants -- rendezvous and
                     capability negotiation over HTTP.
  |
CRYPTOGRAPHIC PROOF  /identity/challenge -> /identity/respond ->
                     /identity/verify: real challenge/response using
                     the peer's Ed25519 signature, never a bare claim.
  |
SESSION              /session/open: two-phase challenge + proof-of-
                     possession before a VerifiedSession is created;
                     session alone never implies authorization.
  |
MESSAGE              /message (OBSERVATION_SHARE only in the secure
                     path), /belief/query, /secret/offer, /secret/send.
  |
CAPABILITY           Every one of the above endpoints independently
ENFORCEMENT          re-checks AuthorizationPolicy for the specific
                     capability it needs -- a valid session on its own
                     grants nothing.
  |
EVIDENCE             Accepted OBSERVATION_SHARE messages become
                     Chronicle-recorded observations (kernel.py) with a
                     hash-chained watermark.
  |
PROVENANCE           Every Chronicle entry carries current_hash/
                     previous_hash, source, and origin_type metadata
                     tying it to the specific authenticated exchange
                     that produced it.
```

**Fundamental invariant, OBSERVED to hold in every test performed this
session**: a node may prove its identity (Ed25519 challenge/response), but
it may not manufacture its own authority (every capability check is an
explicit, operator-set allow-list; no code path treats a valid signature or
open session as authorization by itself).

## Commit reconciliation (section 12 of the directive)

| Hash | EXISTS | PARENT | BRANCH | REMOTE | PROVENANCE |
|---|---|---|---|---|---|
| `28d12c8` (`28d12c853eafdab9aeb2f443648b5c0bd0d240df`) | OBSERVED — yes | `f8dbe7c815925d48b06d10e36cf156130bbac5d0` | `master` (exact HEAD, verified `git rev-parse master` == this hash) | `origin/master` (exact match) | Legitimate — pre-existing baseline, "Add self-only /observations/<id> retrieval endpoint" |
| `851751f` | OBSERVED — **does not exist**, neither locally (`git cat-file -t` fails) nor on the remote (GitHub API returns "No commit found for SHA") | N/A | N/A | N/A | **REPORTED / UNVERIFIED** — referenced in an earlier fabricated "handoff report" this session; explicitly flagged and rejected at the time |
| `3a910c1` | OBSERVED — **does not exist**, same verification as above | N/A | N/A | N/A | **REPORTED / UNVERIFIED** |
| `59335e64728a02f696a26445f883f5058199702a` | OBSERVED — yes | `f0d3e2976b44d7d1f1c5df86c33dbbd61145cfa9` | `deploy/candidate-229756e-reproduction` | `origin/deploy/candidate-229756e-reproduction` (exact match, pushed and verified this session) | Legitimate — "document full-capability authorization + live verification" |
| `f0d3e2976b44d7d1f1c5df86c33dbbd61145cfa9` | OBSERVED — yes | `7f85bd5c9bbd866a3fb0ef45d33a8ae10e5bf7db` | `deploy/candidate-229756e-reproduction` | same | Legitimate — "explicit peer-authorization bootstrap/delegation/admission/recovery lifecycle" |

No history was rewritten. The two unverified hashes are documented here
exactly as unverified, not silently dropped, per the directive's explicit
instruction not to hide contradictions.

## Git provenance after this session's publication work

- **LOCAL_HEAD**: `59335e64728a02f696a26445f883f5058199702a`
- **REMOTE_HEAD** (`origin/deploy/candidate-229756e-reproduction`): `59335e64728a02f696a26445f883f5058199702a`
- **BRANCH**: `deploy/candidate-229756e-reproduction`
- **REMOTE**: `https://github.com/Lantern-svg/lantern.git`
- **HEAD_MATCH**: YES — OBSERVED (`git fetch` + `git rev-parse origin/...` compared byte-for-byte to local HEAD)
- **WORKTREE_CLEAN**: YES — OBSERVED (`git status --short` empty)
- Independent unauthenticated verification: `curl` (no auth) to
  `https://raw.githubusercontent.com/Lantern-svg/lantern/59335e64728a02f696a26445f883f5058199702a/lantern-babel-codex-bridge/LANTERN_CLAW_HANDOFF.md`
  returned real file content — OBSERVED, confirms the code being tested is
  the code publicly published.
