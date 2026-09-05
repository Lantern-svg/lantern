# CANDIDATE MANIFEST — 229756e (IMMUTABLE RELEASE CANDIDATE)
Status: CANDIDATE — LOCAL ONLY. NOT PUSHED. NOT DEPLOYED. NO GIT REFS MODIFIED.
Provenance: LOCAL-LANTERN, 2026-09-05.

## Commit
- SHA: 229756e34e9e18159d3d57d731cdfcad5f374a6b
- Parent: def8736b178c58785072305bdc7de6f32d3e4ab8 (parent field of this commit's object)
- Tree: 8bdae7822c5b703cfc5bc572a18e53a7951907cf
  CORRECTION 2026-09-05: an earlier version of this manifest recorded tree hash
  322a27e8... which matches NO commit in this repository — it was a transcription
  error, caught and corrected during the final validation window. The value above
  is freshly reproduced via `git rev-parse 229756e^{tree}` and `git cat-file -p`.
- Subject: "LAR-1 identity witness ledger + deployment readiness: env config,
  authenticated retrieval, version allowlist, self-test, operator docs (1001 tests)"

## Why this candidate is immutable
A Git commit's hash is a SHA-1 over its full content (tree, parent, author, message).
Any byte changed anywhere in the tree, history, or metadata produces a different hash.
Preserving the candidate requires NO action on the commit itself — it requires only
that nobody rewrites local history (no rebase / reset --hard / amend on this chain)
and that all four local commits remain intact:
eb7bb6e -> b1347c0 -> def8736 -> 229756e (all UNPUSHED; origin/master is 28d12c8)

## Verification anyone can run (read-only)
- git cat-file -p 229756e34e9e18159d3d57d731cdfcad5f374a6b
- git rev-parse 229756e^{tree}  -> must equal the tree hash above
- git hash-object <file> for each core module -> must equal the blob IDs below
- sha256sum of the exported archive -> must equal ARCHIVE_SHA256 below

## Core source blobs (git object IDs) and file SHA-256 at this commit
bootstrap_client.py  a41a15f4a4cda4dc3f6887775264765a02e53df7  4730462f7ec1c7ec3ac77635104f972d18a878d08971b64acb42c606509ff5db
bootstrap_node.py    3799b4b6fb0375e378f8f535224239c92cfa19fd  1cea6dd2fa44809b1127bc5fc4c08109c38ae576123dff8bb80f1058c1b985ad
identity.py          9897d5a2a2b8cf10c53a520d60b49c22afad0f08  4fd2e51f60bc5973a334fa3d50ed471432afa17f69bb5c29ba012b80f2fc682f
verified_session.py  db9acbb284817a68c0ef4e8d50f200d1f32cb64f  fce48ce6f59e1198e6bde3a375d0222da89d9184b1ec3f2700a9da59eed7dad1
capability_authorization.py 7140b04effa5ddb6ff4155bd8da23c439808afc5  5daa6e509c77e3b865c8d0a27e16462a3755a3e14250042123fb540ee6c12135

## Independently verified artifact export (2026-09-04)
Archive: https://base44.app/api/apps/6a695ec5983607164457b476/files/mp/public/6a695ec5983607164457b476/2e061f9ab_lantern_artifacts_2026-09-04tar.gz
ARCHIVE_SHA256: 579e244caca6d1548e3cecb0efb189149092622d8112a3340c40220fcdd4ec16
Cross-node verification: MyClaw independently reproduced the archive SHA-256, the blob
IDs, and the source bytes on 2026-09-04.

## Test record
1001 passed, 5 skipped, 0 failed — reproduced read-only on the committed tree
2026-09-04 (68.14s, cache and bytecode writes disabled; tree clean before and after).

## Phase-3 isolated runtime validation (2026-09-04)
28/28 compatibility tests passed on loopback against this exact tree (tree verified
byte-identical to the commit at run time). See Phase-3 report.

## Current state (2026-09-05)
- Local repo working tree: 0 tracked changes; HEAD = 229756e.
- Not pushed; origin untouched; no tags created; no refs modified.
- Cosmetic review items remain PROPOSED only (docstring relocation L365-383;
  expires_at_monotonic disclosure; unsigned proof_timestamp). None applied.
- Release gate: GATE 2 declared; GATE 3 pending (see PROMOTION_CEREMONY.md).

## COMPLETE TREE ARTIFACT (2026-09-05T03:25Z — supersedes the five-file partial)
The previously transferred archive covered 5 source modules only. The COMPLETE tree
of commit 229756e is now available:
- Artifact: lantern_229756e_full_tree.tar.gz (git archive of the commit — every
  tracked file at 229756e, nothing added, nothing removed)
- Files: 218 (51 Python modules incl. witness_ledger.py, deployment_config.py,
  handshake.py, compatibility.py; full test suite; all docs incl. DEPLOYMENT_RUNBOOK,
  ROLLBACK_PROCEDURE is NOT in the archive — it postdates the commit and remains an
  untracked doc)
- Size: 497,975 bytes
- ARCHIVE_SHA256: 7a688447a87ceed3735ea50f5b4cec52717b556427f43ee424dad28c08c66001
- URL: https://base44.app/api/apps/6a695ec5983607164457b476/files/mp/public/6a695ec5983607164457b476/079ea7aa2_lantern_229756e_full_treetar.gz
  (note: paste exactly as delivered in the final report; public storage, no secrets —
  the tree passed a secrets scan at release audit)
- Verification procedure: sha256sum the download (must match above), extract,
  then verify any file against its git blob ID (git hash-object) — five core
  blob IDs listed above. This artifact IS the complete candidate; a five-file
  subset is NOT.
