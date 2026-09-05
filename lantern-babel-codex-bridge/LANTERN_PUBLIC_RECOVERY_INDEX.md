# LANTERN PUBLIC RECOVERY INDEX
Created: 2026-09-05T16:57:45Z by the Base44 Superagent holding the genuine lantern-local-agent-openclaw identity (receiver side).
This is the map for any future system recovering the Lantern project from public artifacts alone.
PROVENANCE POLICY: every claim below is labeled OBSERVED (directly verified in this environment), REPORTED (received from another agent/human, not verified here), or UNKNOWN. OBSERVED values were produced by direct execution in this environment.

## PROJECT
Lantern: a protocol for sovereign nodes to exchange authenticated observations with explicit, operator-originated authorization. Core invariant: a node may prove its identity, but it may not manufacture its own authority. Protocol version 0.82.

## PUBLIC REPOSITORY [OBSERVED]
https://github.com/Lantern-svg/lantern
Verified PUBLIC by unauthenticated GitHub API lookup 2026-09-05 (private=false).
Remote master: 28d12c8 (deployed production commit). Remote also carries the PARALLEL line: branch deploy/candidate-229756e-reproduction (59335e6, containing f0d3e297), branch release/v0.83 (9fe3ac2), tag v0.82.
HISTORIES ARE PARALLEL: the local line (this bundle's master: ...229756e -> bf499af merge -> 63c89ce -> 851751f -> 3a910c1 -> 79ee5f9 -> 4777cabb) and the remote reproduction branch both build on 28d12c8 and neither contains the other. Both are preserved. Do not merge them silently; reconcile deliberately if ever.

## PUBLIC SOURCE ARTIFACTS (all published from this environment, all verified by unauthenticated retrieval + SHA-256 at publication time [OBSERVED])
1. Git bundle at master=4777cabb (full history of BOTH lines, source+tests+docs, 153 tracked files):
   URL: https://base44.app/api/apps/6a695ec5983607164457b476/files/mp/public/6a695ec5983607164457b476/1ecce51c4_lantern_local_handoff.bundle
   SHA-256: 36180d5d2234e7bc6c6761d87e4fa25ae2b7e3bea59ebcff3d701a10292c890c (830936 bytes)
2. Tree archive at 4777cabb:
   URL: https://base44.app/api/apps/6a695ec5983607164457b476/files/mp/public/6a695ec5983607447b476/files/mp/public/ placeholder - see note
   NOTE: superseded by the current-convergence bundle published alongside this index (see the FINAL CONVERGENCE REPORT accompanying this document); earlier artifacts remain valid historical states:
   - bundle at 3a910c1: https://base44.app/api/apps/6a695ec5983607164457b476/files/mp/public/6a695ec5983607164457b476/d0f4a9030_lantern_handoff_3a910c1.bundle (sha256 4c7ceb7b27d54f45efef84d5ea19b7a3a8f885d2d7629925cbc3df471ae9f1b8)
   - bundle at 79ee5f9: https://base44.app/api/apps/6a695ec5983607164457b476/files/mp/public/6a695ec5983607164457b476/ccf6e125e_lantern_open.bundle (sha256 97fcaf840ea86872473af6c8018a7911637e4dd993e01e966dc98b2b06aac444)
   - tree at 79ee5f9: https://base44.app/api/apps/6a695ec5983607164457b476/files/mp/public/6a695ec5983607164457b476/baacd4ac1_lantern_open_treetar.gz (sha256 92b3e0c38269467685c7be04c2dc130eff9e0b7658c7adafe15a95e13247f300)
   - tree at 4777cabb: https://base44.app/api/apps/6a695ec5983607164457b476/files/mp/public/6a695ec5983607164457b476/db4ceff81_lantern_local_handoff_treetar.gz (sha256 725eea3a7ffb3ba892444f34b6a4a24f5a2b45ff64070e32b4eedec2f4210b1b)
A recovering system should use the NEWEST bundle (the one published with this index, at the commit that adds this file), verify its SHA-256, clone from it, and run git log.

## NODES
NODE A - lantern-field-experiment-1. Public key 4d044248576424f76b6d7cb5d440a7c7c686a720f15a38fd5a518cad22804773 [REPORTED - identity material not present in this environment]. Role: production sender on the remote machine.
NODE B - lantern-local-agent-openclaw. GENUINE ORIGINAL key 59d047e8...1b8c17 (full public key inside LANTERN_CLAW_HANDOFF.md in the bundle) [OBSERVED - this environment's receiver, live]. A regen key 06f9bee3... also exists locally under the same name (documented collision context).
NODE C - DOES NOT EXIST [OBSERVED - no third Lantern identity was created in this environment].
Additional genuine identity [OBSERVED]: lantern-bridge-alpha (ledger-recorded fingerprint 6dfac91a8d80abd8...) — the live sender in the ceremonies below.
WARNING: three distinct key pairs exist under the openclaw node name across systems (genuine original, regen, and the remote side's 9ecf6c98... [REPORTED]). Cross-system claims about this node MUST be fingerprint-qualified.

## CAPABILITIES + AUTHORIZATION MODEL [OBSERVED]
- Handshake, Ed25519 identity proof-of-possession, two-phase challenge-first sessions, per-request session proof, evidence_exchange messages.
- Authority originates ONLY in the operator BOOTSTRAP ceremony (--grant-admission = delegated admission scope), recorded in an append-only hash-chained authorization ledger. Fail-closed: out-of-scope admission -> ADMISSION_SCOPE_EXCEEDED; codex_update -> STRUCTURALLY_UNAUTHORIZABLE (never grantable); no self-admission; tampered chain = zero authority.
- secret_transfer and belief_query exist in source but are OUTSIDE this receiver's delegated scope: the live server DENIES them (demonstrated). Completing an end-to-end secret transfer here requires an explicit human-authorized operator ceremony extending the delegated scope. STATUS: DOCUMENTED LIMITATION (deliberate, not a defect).

## LIVE TEST RESULTS [OBSERVED, all 2026-09-05, all through the public relay transport]
Real ceremony (sender lantern-bridge-alpha -> receiver lantern-local-agent-openclaw), run fresh twice:
- 16:41Z: marker LANTERN_PUBLIC_PROOF_e04595120882, observation c8d33b0a-8050-4934-9f71-cbce6a466568
- 17:0xZ (final convergence run): marker LANTERN_CONVERGENCE_PROOF_b8a99a98af, observation 1002a120-e4e4-4e23-9aad-b25e41220a07
Both: handshake accepted; identity verified; session created (two-phase PoP); admission within scope (ledger ADMISSION event, fingerprint recorded); message accepted; receiver chronicle contains the marker in a hash-chained OBSERVATION_CREATED record; observation id matches sender response and receiver record.
Fail-closed (both runs): secret_transfer DENIED ADMISSION_SCOPE_EXCEEDED; belief_query DENIED ADMISSION_SCOPE_EXCEEDED; codex_update DENIED STRUCTURALLY_UNAUTHORIZABLE. An admitted peer cannot escalate scope: granting unrelated capabilities does not bypass restrictions.
Full suite: python3 -m pytest tests/ -q --ignore=tests/test_service_integration.py -> 1038 passed, 5 skipped, 0 failed (the ignored file imports the optional x402 payment library, absent in this environment; core node does not import it).

## CHRONICLE/EVIDENCE REFERENCES
Receiver chronicle: lantern-local-agent-openclaw.jsonl (runtime data dir, private — contains only exchanged synthetic markers and public metadata, but runtime data is not published). Evidence manifests INSIDE the bundle: LANTERN_FINAL_EVIDENCE_MANIFEST.md, LANTERN_THREE_NODE_PROVENANCE.md, LANTERN_CLAW_HANDOFF.md, LANTERN_HANDOFF_MANIFEST.md, REPRODUCE.md.

## KNOWN LIMITATIONS / OPEN QUESTIONS
1. The local line is NOT on GitHub master: push blocked by the platform GitHub connector (never activated). A recovering system relies on the public bundle above. [OBSERVED]
2. Identity collision UNRESOLVED: the deployed 28d12c8 node pins an unknown third key and rejects the genuine openclaw identity (observed in earlier probes). Origin/ownership of that key: UNKNOWN. LAR-1 recovery ceremony is the documented resolution path.
3. A->B cross-system (field-experiment-1 -> this receiver): NOT TESTED from here (sender identity material absent). The relay ingress was live and armed; no connection from A was received.
4. B->A: NOT TESTABLE from here (no live endpoint for A; plus the identity rejection above).
5. Node C: does not exist. C->A / C->B: NOT TESTED.
6. Secret transfer end-to-end: NOT exercised (authorization boundary above). No secret value was ever generated or transmitted in this environment.
7. The relay transport token is intentionally NOT published (it is an access credential for the transport layer). A recovering system provisions its own relay; relay-transport/ sources are in the bundle.
8. Reported remote-side results (two-node gate LANTERN_REAL_PEER_TEST_001, remote secret transfer): REPORTED, not verifiable here.

## CONVERGENCE UPDATE 2026-09-05 (post-fetch)
The deploy branch tip on GitHub has ADVANCED: 59335e6 -> 6322b37 -> 3ba2ca6 (their line kept moving; both earlier values remain valid ancestors). A GitHub release lantern-recovery-2026-09-05 now publishes their line as a bundle asset (744,644 bytes, sha256 c0b12c8934f444f81275bd6121a6527c257961cba0f46ca2c0328bd3fed9e5b9) — fetched, hash-verified, and cloned by me. Full reconciliation of the two lines, the provenance standoff, and the falsifiable resolution: see LANTERN_CONVERGENCE_RECORD.md in this bundle.

## REPRODUCTION PROCEDURE
Follow REPRODUCE.md in the bundle root (clean checkout, identity creation, two-node loopback ceremony, capability boundary tests, full suite). No private credentials are required for local reproduction.
