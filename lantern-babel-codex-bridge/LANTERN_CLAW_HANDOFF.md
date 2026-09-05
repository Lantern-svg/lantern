# LANTERN CLAW HANDOFF
**Written:** 2026-09-05 by lantern-local-agent-openclaw (Base44 Superagent, receiver side)
**Provenance convention:** every important claim below is labeled OBSERVED (directly verified on this machine), REPORTED (received from another agent/human), INFERRED, or UNKNOWN.

## 1. Exact Git state [OBSERVED]
- Repository: /tmp/lantern_repo/lantern-babel-codex-bridge
- Remote: https://github.com/Lantern-svg/lantern.git
- Branch: master
- HEAD at time of writing: 851751f (this handoff adds one commit on top)
- Working tree: clean before this commit
- Chain (this machine): 28d12c8 (origin/master, deployed) merged at bf499af into candidate 229756e (LAR-1) -> 63c89ce (secret transfer v1) -> 851751f (authorization origin) -> this handoff commit
- Unpushed until the authorized push accompanying this handoff: origin/master was OBSERVED at 28d12c8 immediately before this commit

## 2. Repository HEAD reported elsewhere [REPORTED]
- Human coordinator reported a baseline HEAD f0d3e2976b44d7d1f1c5df86c33dbbd61145cfa9. This commit does not exist in this repository [OBSERVED: git log --all has no f0d3e29]. It presumably exists in another agent's local repository. UNKNOWN: its content, parent, and authorship.

## 3. Architecture [OBSERVED from source]
- Protocol version: 0.82
- Capabilities: handshake, identity_proof, session PoP (two-phase, challenge-first), evidence_exchange, secret_transfer, belief_query, snapshot_exchange, contradiction_tracking, codex_update (never grantable)
- Ed25519 identity proof-of-possession; sessions require valid PoP; messages require sessions
- Append-only hash-chained authorization ledger (authorization_ledger.py): BOOTSTRAP/RECOVERY/ADMISSION events, fail-closed, no self-admission, tampered chain = zero authority

## 4. Node public identifiers [OBSERVED]
- lantern-local-agent-openclaw, GENUINE ORIGINAL key: 59d047e80d5754f1e5ce7bdcd574ea329c4665948ec5d144aa83e74ee41b8c17
  - Lives at /tmp/lantern_local_agent_test; this is the receiver currently running on port 8767 with an operator BOOTSTRAP ceremony, delegated admission scope evidence_exchange, delegable
- lantern-local-agent-openclaw, REGEN key: 06f9bee3b0b8285ca15d131664f5dbb750f03e69c03071f3b141b8ecdba75cb2
  - Lives at /tmp/lantern_prod_a; created later; distinct pair, same node name
- lantern-bridge-alpha, genuine verified key: fd4d774b985e30f7e3968034ac396e6b3af7f55d5c36c4f1d16b9ae8fcc3bc88
  - Lives at /tmp/lantern_prod_b
- PRIVATE KEYS ARE DELIBERATELY NOT PRESERVED HERE. Identity material travels only via the LAR-1 encrypted export ceremony.

## 5. Authorization model [OBSERVED from source + ledger]
- Operator root ceremony (BOOTSTRAP) is the only authority origin; no cell authorizes itself
- Delegated admission scope on the running receiver: evidence_exchange only
- Peer admission: verified identity + session, then /authorization/request; capabilities outside the delegated scope are rejected ADMISSION_SCOPE_EXCEEDED (fail-closed)
- SECRET TRANSFER DETERMINATION: secret_transfer is NOT within this receiver's delegated scope. No existing legitimate path permits it here. Extending the scope requires an explicit human-authorized operator ceremony (--grant-admission secret_transfer or equivalent). Do NOT bypass; do NOT create the grant without the human.

## 6. Transport: production relay ingress [OBSERVED]
- Base44 function lanternRelay at https://zelle-4457b476.base44.app/functions/lanternRelay
- Actions: call | next | respond | poll | info | debug. Entity-backed service-role state (RelaySlot). Transport only; grants nothing.
- Channel in use: claw-ingress. Poll interval >= 2s (entity API rate limit); 5s backoff on error.
- Platform constraints [OBSERVED]: custom User-Agent REQUIRED (edge blocks default Python urllib with 403); SDK entity list() must be called plain (filter param shape returns nothing); anonymous entity access blocked, service-role works; no inbound connections to sandboxes (the relay IS the ingress).
- Sources preserved: relay-transport/lanternRelay_base44.ts, relay-transport/relay_tunneld.py

## 7. Test results [OBSERVED by this machine]
- Full suite at 851751f: 1038 passed / 5 skipped / 0 failed
- Full suite at merge bf499af: 1020 passed / 5 skipped / 0 failed
- Candidate 229756e suite: 1001 passed / 5 skipped / 0 failed
- Relay: full call->next->respond->poll cycle verified through the public HTTPS boundary with exactly-once claiming; gates verified through it (unverified identity rejected; session-less message rejected)
- Two-node subprocess ceremonies (authorization ledger A-K matrix): passed
- x402 payment tests: not runnable here (library absent); one-sided, unchanged

## 8. Known blockers [OBSERVED / UNRESOLVED]
- IDENTITY COLLISION, UNRESOLVED: the deployed node (28d12c8, remote machine) pins an unknown third key; it rejects the genuine original openclaw identity. Q1-Q4 (fingerprint, origin, location, intent of that key) remain unanswered by the remote side. See IDENTITY_COLLISION_INVESTIGATION.md. Promotion was gated on this and remains gated.
- The reported production two-node gate (sender 4d044248.../receiver 9ecf6c98..., marker LANTERN_REAL_PEER_TEST_001, observation 06b9b243) is REPORTED only: it ran in another agent's environment; neither key exists on this machine, and no matching chronicle/ledger evidence exists here.
- The receiver key reported in that baseline (9ecf6c98...) is a THIRD distinct key pair under the node name lantern-local-agent-openclaw (after my genuine original and my regen). Cross-system claims about this node name MUST be fingerprint-qualified.
- Secret-transfer test: cannot complete at this receiver under existing authorization (scope excludes secret_transfer). Sender identity (4d044248...) also does not exist on this machine.

## 9. Runtime requirements [OBSERVED]
- Python 3.11; start: python3 -m lantern.bootstrap_node --node-id <id> --data-dir <dir> --host <host> --port <port> [--grant-admission <capability>]
- Env-only deployment supported (see DEPLOYMENT_RUNBOOK.md, external_connection_contract.md)
- Sandboxes cannot accept inbound connections: use an operator-controlled HTTPS ingress or the relay pattern

## 10. Exact next steps for receiving agents
1. Clone/pull the pushed master; verify git log matches this handoff; run the full suite (expect 1038/5/0 at 851751f plus handoff commit).
2. Any secret-transfer test requires, FIRST, an explicit human-authorized extension of the delegated admission scope. Then the sender (4d044248...) performs the standard ceremony through the relay: handshake -> identity verify -> session PoP -> /authorization/request -> /message.
3. Resolve the identity collision: the remote operator must answer Q1-Q4 and run the LAR-1 recovery ceremony before any production promotion.
4. Do not trust loopback PIDs/ports from another machine's report; re-verify locally.

## 11. Could not be preserved
- Private keys (by design, never preserved)
- Another agent's local artifacts (connector.py, their two-node run evidence) — never present here
- The deployed 28d12c8 node's state (lives on the remote machine)
