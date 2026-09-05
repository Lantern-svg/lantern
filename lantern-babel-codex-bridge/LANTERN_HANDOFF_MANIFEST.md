# LANTERN HANDOFF MANIFEST
Created: 2026-09-05T16:50:55Z by the local Lantern system (Base44 Superagent environment).
All values in this manifest were directly observed on this machine at creation time unless labeled REPORTED/UNKNOWN.

## Source
- Filesystem path: /tmp/lantern_repo (git worktree root; the Lantern protocol implementation and history live under lantern-babel-codex-bridge/)
- Repository: Lantern-svg/lantern clone
- Remote: https://github.com/Lantern-svg/lantern.git
- Branch: master (local)
- HEAD: see Git block below (this manifest commit)
- Git status: working tree clean of tracked changes; one untracked legacy archive at worktree root

## Git identity (observed)
- Full local chain: 28d12c8 -> (candidate chain eb7bb6e/b1347c0/def8736/229756e) -> merge bf499af -> 63c89ce (secret transfer v1) -> 851751f (authorization origin) -> 3a910c1 (claw handoff) -> 79ee5f9 (open publication docs) -> this manifest commit
- All five previously-disputed commits verified present in this object database via git rev-parse: 28d12c8 (origin/master), f0d3e297 and 59335e6 (on remote branch deploy/candidate-229756e-reproduction, fetched), 3a910c1 and 851751f (on local master)
- git fsck: clean
- The remote reproduction branch is a PARALLEL line over 28d12c8; it does not contain the local chain, and the local chain does not contain it. Both are preserved in the bundle.

## Handoff artifact
- Artifact: full-history Git bundle (complete repository: source, tests, protocol, identity, authorization ledger, relay transport sources, evidence and provenance docs)
- The bundle contains the ENTIRE history of both lines (local master + all remote refs known at creation time)
- Archive sizes and SHA-256: recorded in the final report accompanying this manifest; the bundle is verified by direct clone before publication (observed)
- Secrets scan: the repository contains NO private keys, passwords, tokens, cookies, or credentials. Identity private keys live outside the repository in runtime data directories and are intentionally NOT included. Synthetic test values and public key fingerprints are not secrets.

## Tests
- Command: cd lantern-babel-codex-bridge && python3 -m pytest tests/ -q --ignore=tests/test_service_integration.py
- The optional payment integration test file (tests/test_service_integration.py) is EXCLUDED here: it imports the third-party x402 library which is not installed in this environment. The core node imports none of it (verified). Including that file without the library produces a collection ImportError, not a test failure.
- Result observed at this HEAD (code identical to 851751f; only documentation differs since): recorded in the final report at creation time
- Reproduction: any system can clone from the bundle and run the same command; expected all-pass with 5 known environmental skips

## Node/protocol information (safe to disclose)
- Protocol version 0.82; capabilities: handshake, identity_proof, evidence_exchange, secret_transfer, belief_query, snapshot_exchange, contradiction_tracking; codex_update is STRUCTURALLY_UNAUTHORIZABLE
- Node public identifiers: lantern-local-agent-openclaw genuine original key (see LANTERN_CLAW_HANDOFF.md, full public key), the regen key, lantern-bridge-alpha key; sender node lantern-field-experiment-1 key 4d044248...804773 [REPORTED - not present locally]
- Authority model: operator BOOTSTRAP ceremony only; hash-chained append-only authorization ledger; fail-closed; no self-admission
- Live evidence (observed 2026-09-05): full ceremony through the public relay recorded in LANTERN_THREE_NODE_PROVENANCE.md and LANTERN_FINAL_EVIDENCE_MANIFEST.md

## Known limitations / not verified here
- GitHub push from this environment: BLOCKED (platform GitHub connector never activated; OAuth screen pending). The remote master remains 28d12c8; the other line's branches are already pushed by the other system [REPORTED].
- Identity collision on the deployed node: UNRESOLVED (see IDENTITY_COLLISION_INVESTIGATION.md).
- The reported two-node gate LANTERN_REAL_PEER_TEST_001 and the reported secret-transfer test ran in the other system's environment; their artifacts are not present here.
- Secret transfer was NOT exercised end-to-end here: secret_transfer is outside this receiver's operator-delegated scope; the rejection is the demonstrated fail-closed behavior.
