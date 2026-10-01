# LANTERN THREE-NODE PROVENANCE
Written 2026-09-05 by the Base44 Superagent (lantern-local-agent-openclaw operator side).
Labels: OBSERVED = directly verified in this environment. REPORTED = received from another agent/human, not verified here. UNKNOWN = not established.

## Public repository [OBSERVED]
- URL: https://github.com/Lantern-svg/lantern
- VISIBILITY: PUBLIC (verified by UNAUTHENTICATED GitHub API lookup 2026-09-05: private=false; repo page HTTP 200)
- default branch master at 28d12c8; additional remote refs: deploy/candidate-229756e-reproduction (59335e6), release/v0.83 (9fe3ac2), tag v0.82 (588651e)

## The three participants
NODE A - lantern-field-experiment-1
- Public key 4d044248576424f76b6d7cb5d440a7c7c686a720f15a38fd5a518cad22804773 [REPORTED]
- Protocol 0.82 [REPORTED]. Role: production sender, deployed on the remote machine.
- Identity material NOT present in this environment [OBSERVED]. A->B test therefore NOT TESTED here.

NODE B - lantern-local-agent-openclaw
- GENUINE ORIGINAL public key: 06f9bee3... is the regen; the genuine original running as receiver is 59d047e8...1b8c17 (full value in LANTERN_CLAW_HANDOFF.md) [OBSERVED]
- Protocol 0.82. Role: receiver, live at port 8767 behind the public relay ingress (channel claw-ingress).
- Operator BOOTSTRAP ceremony in hash-chained ledger, delegated admission scope: evidence_exchange [OBSERVED].

NODE C - independent Superagent Lantern identity
- DOES NOT EXIST [OBSERVED: no third identity was created in this environment; the directive allowed it only "if successfully created"]. C->peer: NOT TESTED.

Additional genuine identity used for the real protocol exercise [OBSERVED]:
- lantern-bridge-alpha, key fingerprint 6dfac91a8d80abd8... (ledger-recorded), genuine, filesystem-backed since 2026-09-01. It played the SENDER role in the live ceremony below because Node A's material is not present here.

## Real live ceremony [OBSERVED end-to-end, 2026-09-05 ~16:41 UTC]
Transport: sender -> public HTTPS relay (Base44 function, channel claw-ingress) -> tunnel -> receiver node -> responses back the same path. The relay is transport only; it grants nothing.

IDENTITY VERIFIED: true (Ed25519 challenge/response/verify, lantern-bridge-alpha)
SESSION ESTABLISHED: created=true, two-phase proof-of-possession (session 62AtTIZk...)
AUTHORIZATION: /authorization/request evidence_exchange -> within delegated scope; ADMISSION event recorded in the receiver ledger with the sender's fingerprint, ts 2026-09-05T16:41:16
MESSAGE SENT: OBSERVATION_SHARE with fresh synthetic marker LANTERN_PUBLIC_PROOF_e04595120882
RECEIVER OBSERVED: the marker appears in the receiver's hash-chained chronicle (record id 9bec7636-..., payload.id c8d33b0a-8050-4934-9f71-cbce6a466568 = the observation_id returned to the sender; sender and receiver evidence agree)
EVIDENCE PERSISTED: chronicle (lantern-local-agent-openclaw.jsonl) + authorization_ledger.jsonl (BOOTSTRAP then ADMISSION)

## Fail-closed proofs [OBSERVED]
- secret_transfer: DENIED, ADMISSION_SCOPE_EXCEEDED, delegated_scope=[evidence_exchange]
- belief_query: DENIED, ADMISSION_SCOPE_EXCEEDED
- codex_update: DENIED, STRUCTURALLY_UNAUTHORIZABLE (architecturally never grantable; unrelated admission does not bypass it)
A node may prove its identity, but it may not manufacture its own authority. Authority originates ONLY in the operator BOOTSTRAP ceremony and flows through the hash-chained, fail-closed ledger.

## Connection matrix (honest status)
A->B: NOT TESTED from here (sender identity absent from this machine; ingress armed and waiting)
B->A: BLOCKED - the deployed 28d12c8 node rejects the genuine openclaw identity; pinned third key unexplained. UNRESOLVED collision (see IDENTITY_COLLISION_INVESTIGATION.md).
C->peer: NOT TESTED (no Node C)
bridge-alpha->B: REAL, FULL, OBSERVED both ends (above)

## Commit reconciliation [OBSERVED]
- 28d12c8: EXISTS; origin/master; the deployed production commit.
- 851751f: EXISTS locally (authorization origin), on my unpushed chain.
- 3a910c1: EXISTS locally (claw handoff), on my unpushed chain.
- 59335e6: EXISTS on remote branch deploy/candidate-229756e-reproduction; parent f0d3e297; "document full-capability authorization + live verification".
- f0d3e297: EXISTS on the same remote branch; parent 7f85bd5; "explicit peer-authorization bootstrap/delegation/admission/recovery lifecycle".
- The remote reproduction branch does NOT contain my chain (229756e/bf499af/851751f/3a910c1): the two development lines are PARALLEL implementations over 28d12c8 (mine: merge + secret transfer + authorization origin; theirs: candidate overlay + connector migration + secret transfer + authorization lifecycle). Both are preserved publicly: theirs on GitHub, mine in the published bundle below.
