# REPRODUCE — independent verification path
No private credentials are required for local reproduction.

1. OBTAIN: git clone https://github.com/Lantern-svg/lantern (public) — note master carries the deployed 28d12c8 lineage plus remote branches. THIS machine's chain (229756e..handoff, including the authorization origin and this documentation) is published as a Git bundle: lantern_open bundle URL listed in the final report; verify with sha256sum, then: git clone <bundle> lantern && cd lantern && git log --oneline -6
2. CHECK OUT: the verified commit from the bundle (HEAD of the handoff chain).
3. DEPENDENCIES: Python 3.11+. No third-party packages for the core protocol (stdlib only; pytest for tests).
4. IDENTITY: python3 -m lantern.witness_ledger --help (or see tests) — creating a node identity: the first node start creates a persistent Ed25519 identity under your data dir. Identity material NEVER leaves your machine; only public keys are exchanged in the protocol.
5. START A NODE: python3 -m lantern.bootstrap_node --node-id <your-id> --data-dir <dir> --host 127.0.0.1 --port 8766 --grant-admission evidence_exchange
6. AUTHORIZATION: authority originates ONLY in the operator ceremony (--grant-admission = delegated admission scope, recorded in a hash-chained append-only ledger). Peers request admission via POST /authorization/request {session_id, node_id, capabilities}. Out-of-scope -> ADMISSION_SCOPE_EXCEEDED; codex_update -> STRUCTURALLY_UNAUTHORIZABLE. No node can authorize itself.
7. TESTS: python3 -m pytest tests/ -q  (expect 1038 passed / 5 skipped at this chain's HEAD)
8. IDENTITY/SESSION/MESSAGE PATH: run a second node and use the reference consumer: python3 -m lantern.bootstrap_client --peer http://127.0.0.1:8766 --source <id> --content hello --node-id <client-id> --data-dir <dir>  (handshake -> identity proof -> two-phase session -> message)
9. CAPABILITY ENFORCEMENT: after admission, POST /authorization/request with [secret_transfer] or [belief_query] against a node whose delegated scope is only evidence_exchange -> DENIED. codex_update -> DENIED always.
10. SECRET TRANSFER (where safe): requires an operator-delegated scope including secret_transfer on the receiver. Then the reference consumer's send_secret() (bootstrap_client.py) performs the authenticated, digest-verified transfer. Use ONLY a disposable synthetic value.

Live peer testing across machines: sandboxes cannot accept inbound connections; use an operator-controlled HTTPS ingress or the relay pattern preserved in relay-transport/ (poll >= 2s; custom User-Agent required behind the Base44 edge; transport grants no authority).
