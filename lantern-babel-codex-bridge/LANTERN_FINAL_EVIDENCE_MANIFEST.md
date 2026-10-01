# LANTERN FINAL EVIDENCE MANIFEST
All entries executed 2026-09-05 on this machine unless labeled REPORTED. Source commit for the live ceremony: the working tree at this commit's parent chain (851751f lineage, protocol 0.82).

TEST_ID: E1-full-suite
PURPOSE: complete protocol regression suite
SOURCE_COMMIT: 851751f
ENVIRONMENT: Python 3.11 sandbox
COMMAND: python3 -m pytest tests/ -q
EXPECTED: all pass except 5 known environmental skips
OBSERVED: 1038 passed, 5 skipped, 0 failed
RESULT: PASS
RECEIVER_EVIDENCE: n/a (offline suite)

TEST_ID: E2-relay-cycle
PURPOSE: public transport path call->next->respond->poll with exactly-once claiming
SOURCE_COMMIT: relay v3.2 (relay-transport/lanternRelay_base44.ts)
COMMAND: curl POST to relay /functions/lanternRelay (actions call/next/respond/poll)
OBSERVED: full cycle through public HTTPS boundary, metadata passthrough, second next empty (exactly-once)
RESULT: PASS

TEST_ID: E3-live-ceremony
PURPOSE: identity -> session -> authorization -> message over the real public relay
SOURCE_COMMIT: this tree
COMMAND: see LANTERN_THREE_NODE_PROVENANCE.md "Real live ceremony"; bootstrap_client reference consumer routed through the relay
EXPECTED: handshake accepted; identity verified; session created; admission within scope; message accepted; receiver chronicle contains the marker
OBSERVED: all six held; observation_id c8d33b0a-8050-4934-9f71-cbce6a466568; marker LANTERN_PUBLIC_PROOF_e04595120882 present in receiver chronicle record 9bec7636 (hash-chained)
RESULT: PASS
RECEIVER_EVIDENCE: lantern-local-agent-openclaw.jsonl chronicle + authorization_ledger.jsonl ADMISSION (fingerprint 6dfac91a8d80abd8...)

TEST_ID: E4-fail-closed-scope
PURPOSE: unauthorized capabilities rejected after legitimate admission
OBSERVED: secret_transfer DENIED ADMISSION_SCOPE_EXCEEDED; belief_query DENIED ADMISSION_SCOPE_EXCEEDED
RESULT: PASS (system correctly refuses)

TEST_ID: E5-fail-closed-architectural
PURPOSE: never-grantable capability
OBSERVED: codex_update DENIED STRUCTURALLY_UNAUTHORIZABLE
RESULT: PASS

TEST_ID: E6-secret-transfer
PURPOSE: synthetic secret transfer
RESULT: NOT ATTEMPTED BEYOND AUTHORIZATION STAGE - secret_transfer is outside the receiver's operator-delegated scope; the authorization request was correctly DENIED. Completing this test requires an explicit human-authorized operator ceremony extending the delegated scope. No secret value was generated or transmitted.

TEST_ID: E7-public-lookup
PURPOSE: unauthenticated visibility of the public repository
COMMAND: curl https://api.github.com/repos/Lantern-svg/lantern (no credentials)
OBSERVED: HTTP 200, private=false
RESULT: PASS

TEST_ID: E8-gate-rejection-through-relay
PURPOSE: security gates hold through the transport
OBSERVED: /session/open without identity proof -> identity_not_verified; /message without valid session -> rejected at validation
RESULT: PASS

REPORTED (not verified here): two-node gate LANTERN_REAL_PEER_TEST_001 in the other environment (sender 4d044248..., receiver 9ecf6c98...); that receiver key is not any identity present here.
