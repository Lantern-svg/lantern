# ROLLBACK PROCEDURE — Lantern Node Deployment
Status: DRAFT (untracked, awaiting authorized release commit)
Scope: applies to the deployed production node (currently 28d12c8) and any future deployment of candidate 229756e.
Provenance: LOCAL-LANTERN, 2026-09-05. Closes the GATE 3 blocker "rollback procedure known."

## Principles
1. A deployment is reversible only if the pre-deployment state is captured BEFORE the swap.
2. The Chronicle is append-only evidence. Rollback never deletes observations.
3. Identity keys live on disk and are NEVER rotated, regenerated, or copied raw during rollback.
4. Rollback restores the previous BUILD; it does not erase the record that the newer build ran.

## Pre-deployment snapshot (mandatory, before any swap)
On the target node's operator infrastructure, capture and store:
- S1. Full copy of the Chronicle file(s) (and note byte size + SHA-256 of each).
- S2. Full copy of every identity directory (private + public + binding.json).
- S3. Runtime configuration (env vars / flags: bind, port, allowlist, authorizations, witness registry path).
- S4. Current running commit hash and /health JSON output.
- S5. Timestamp and operator identity performing the snapshot.
Store snapshots under a dedicated backup directory outside the runtime data dir.

## Rollback steps (trigger: any post-deployment verification failure or operator decision)
- R1. Stop the node process cleanly (SIGTERM; allow graceful shutdown).
- R2. Copy the post-deployment Chronicle aside (append-only history of the newer build is preserved, never deleted).
- R3. Restore the PREVIOUS build: in the target repo, git checkout <previous-commit>
  (e.g., 28d12c853eafdab9aeb2f443648b5c0bd0d240df), or restore the previous build artifact
  exactly as it was captured in S4.
- R4. Restore runtime configuration from S3 (the previous build's env/flags).
- R5. Restore identity directories from S2 ONLY if the newer deployment altered them
  (normal deployments do not; verify byte-identical before deciding).
- R6. Restart the node with the previous configuration.
- R7. Verification checklist (all must pass to declare rollback complete):
  - /health responds; node_id unchanged; process is the previous build (behavioral
    fingerprint: for 28d12c8, /session/open returns a nonce-less session on membership;
    /observation/retrieve returns 404).
  - Chronicle loads: last pre-deploy observation is present (integrity check).
  - No witness registry file is consumed by the old build (28d12c8 predates LAR-1;
    any registry file created by the newer build stays on disk, unused and untouched).
- R8. Record rollback provenance (template below). Rollback is an explicit, recorded event.

## Memory-state notes
- Verified-key pins, sessions, challenge nonces, and handshake records are IN-PROCESS
  memory only. Any restart (deploy OR rollback) clears them; peers must re-authenticate.
  This is expected behavior, not data loss.
- If a LAR-1 witness registry was initialized by the newer build: keep the file. The
  ledger is append-only public material. Never delete records; retire or annotate
  node_ids through the witness_ledger CLI instead.

## Chronicle compatibility decision point
The newer build introduces record types the old build has never parsed. If the old build
fails to load a Chronicle containing newer records, the operator chooses:
- Option A (preferred if the old build tolerates unknown records): append-only retention.
- Option B (if the old build cannot parse): restore the pre-deploy Chronicle snapshot (S1)
  and archive the post-deploy copy separately. Observations recorded by the newer build
  remain in the archived copy but are not served by the rolled-back node.
This choice MUST be made by the operator and recorded in the rollback provenance.

## Rollback provenance record (fill on execution)
ROLLBACK TRIGGER:
PREVIOUS COMMIT RESTORED:
ROLLBACK TIME:
SNAPSHOT USED (S1-S5 ids/hashes):
CHRONICLE DECISION (A/B):
POST-ROLLBACK TEST:
RESULT:
OPERATOR:
