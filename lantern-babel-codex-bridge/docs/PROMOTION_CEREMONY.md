# PROMOTION CEREMONY — 229756e to production
Status: PREPARED, NOT EXECUTED. No step below has been performed.
Requires: explicit owner authorization for the push, and remote-operator authorization
for every action on the deployed node. Two human authorizations, recorded.

## Preconditions (all must be true before Phase 1)
P1. GATE 3 declared: candidate manifest, rollback procedure, compatibility matrix, and
    collision resolution plan all present (docs: CANDIDATE_229756e_MANIFEST.md,
    ROLLBACK_PROCEDURE.md, IDENTITY_COLLISION_INVESTIGATION.md).
P2. MyClaw re-verifies the candidate artifact at execution time (archive SHA-256, blob
    IDs, source bytes) and answers the Phase-7 question: "Does the candidate source
    contain what LOCAL-LANTERN claims it contains?" -> must be VERIFIED.
P3. The identity collision questions (Q1-Q4) are answered and Path A/B/C chosen.
P4. Production snapshot completed per ROLLBACK_PROCEDURE.md (S1-S5), hashes recorded.

## Phase 1 — Push (owner-authorized; performed by owner or delegated)
1.1. Push the four local commits: eb7bb6e, b1347c0, def8736, 229756e to origin/master.
1.2. Verify origin/master == 229756e34e9e18159d3d57d731cdfcad5f374a6b.
1.3. MyClaw pulls and independently re-verifies blobs + archive hash.

## Phase 2 — Pre-deploy (remote operator)
2.1. Snapshot per ROLLBACK_PROCEDURE.md S1-S5 (chronicle, identity dirs, config,
     /health, running commit).
2.2. Answer Q1-Q4; export the remote's openclaw PUBLIC material (fingerprint, created_at).
2.3. Choose the collision resolution path (A recommended) and record it.

## Phase 3 — Deploy (remote operator, per DEPLOYMENT_RUNBOOK.md)
3.1. git checkout 229756e34e9e18159d3d57d731cdfcad5f374a6b on the deployed repo.
3.2. Configure env: bind host/port, protocol-version allowlist (0.82),
     --authorize for the ambassador node_id(s) and capabilities
     (e.g., evidence_exchange, OBSERVATION_RETRIEVE) as operationally required.
3.3. Initialize the LAR-1 witness registry (public material only).
3.4. Run --self-test; exit 0 required BEFORE binding the socket.
3.5. Start the node.

## Phase 4 — Identity reconciliation (the collision ceremony)
4.1. Retire the remote's stale openclaw key: witness_ledger retirement ceremony
     (append-only record; never deletion).
4.2. Register the GENUINE keys (openclaw 59d047e8..., bridge-alpha) in the witness
     registry via the LAR-1 encrypted export ceremony. NEVER raw-copy private keys.
4.3. Re-verify identity for every participating node_id; all must be
     CRYPTOGRAPHICALLY_VERIFIED.

## Phase 5 — Post-deployment verification (blocks real traffic; rollback trigger on failure)
5.1. Full Phase-3 matrix against the deployed node, BOTH directions (LOCAL -> REMOTE
     and REMOTE -> LOCAL): two-phase session, all negative PoP tests, replay, expiry,
     cross-peer rejection, legacy refusal, malformed-version structured rejection.
5.2. Chronicle compatibility check: retrieve a PRE-deploy observation through the new
     build's authenticated retrieval endpoint; record the result (old-record format
     compatibility was never tested — treat unknown outcome as a checkpoint, not a
     guess).
5.3. Confirm no downgrade: nonce present on every session; --legacy refused unless
     the operator explicitly enabled it.

## Phase 6 — First real cross-node session (disposable value only)
6.1. Full exchange with recorded provenance: sender/receiver node_ids, source commit,
     destination commit, protocol version, challenge nonce id, proof result, session
     result, received value, timestamps.
6.2. Reverse-direction digest-only ACK per the existing mechanism.
6.3. Receiving side reports the received value exactly and its computed SHA-256.

## Phase 7 — Deployment provenance record (fill on execution)
SOURCE COMMIT: 229756e34e9e18159d3d57d731cdfcad5f374a6b
TARGET NODE:
DEPLOYMENT EVENT:
DEPLOYMENT TIME:
RUNTIME PATH:
RUNTIME COMMIT:
RUNTIME HASH:
POST-DEPLOYMENT TEST:
RESULT:

## Rollback triggers (any one -> execute ROLLBACK_PROCEDURE.md and stop)
- Self-test failure, or any Phase-5 check fails.
- Any session created without proof-of-possession.
- Chronicle integrity failure after the swap.
- Operator decision.

## Explicitly NOT authorized by this document
Pushing, deploying, restarting production, rotating keys, altering registries, or
executing any step above. This is the plan, not permission.
