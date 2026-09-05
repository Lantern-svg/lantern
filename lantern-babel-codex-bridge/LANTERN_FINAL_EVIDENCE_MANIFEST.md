# LANTERN FINAL EVIDENCE MANIFEST

_Written 2026-09-05. All test results below are OBSERVED — directly executed
in this environment against the real running production processes, this
session, immediately before writing this document. Raw script output is
preserved at `/tmp/public_proof_test.py` / `/tmp/public_proof_test_output.json`
on the machine that ran these tests (not committed — see REPRODUCE.md to
regenerate independently)._

## Test environment (OBSERVED)

- Git commit under test: `f0d3e2976b44d7d1f1c5df86c33dbbd61145cfa9` (source
  loaded by both live processes at test time), documentation commit
  `59335e64728a02f696a26445f883f5058199702a` on top of it.
- Node A: `lantern-field-experiment-1`, `http://127.0.0.1:8765`, PID 94327 at test time.
- Node B: `lantern-local-agent-openclaw`, `http://127.0.0.1:8767`, PID 94329 at test time.
- Python: `.venv/bin/python3.12` (project virtualenv, `lantern-babel-codex-bridge/.venv`).
- Full automated suite immediately prior to this manifest: **1102 passed, 3 skipped, 0 failed** (91.45s), OBSERVED this turn.

## TEST_ID: PUBLIC-PROOF-001 (A → B)

- **PURPOSE**: prove a real authenticated connection, message, query, and fail-closed rejection from Node A to Node B.
- **SOURCE_COMMIT**: `f0d3e2976b44d7d1f1c5df86c33dbbd61145cfa9`
- **ENVIRONMENT**: real running Node B process on `127.0.0.1:8767`; caller uses Node A's real on-disk identity at `/tmp/lantern_public_experiment/data`.
- **COMMAND**: `LanternConnector(remote_url="http://127.0.0.1:8767", node_id="lantern-field-experiment-1", data_dir="/tmp/lantern_public_experiment/data")` — see `/tmp/public_proof_test.py::run_direction("AtoB", ...)`.
- **EXPECTED**: identity `CRYPTOGRAPHICALLY_VERIFIED`; session created via real two-phase challenge/proof; `OBSERVATION_SHARE` accepted; `belief_query` accepted; `CODEX_UPDATE` rejected.
- **OBSERVED**:
  - `identity_status: CRYPTOGRAPHICALLY_VERIFIED`
  - `session created: true`, `session_id wfBY2BSlG38Be3zB4bHcZ0UeAB25KkW3xz_2UdJShig`
  - `evidence_exchange`: `accepted: true`, `observation_id 078a8953-4e9a-4e52-9c3b-e59c1e874eb7`, marker `LANTERN_PUBLIC_PROOF_AtoB_d0025ebb`
  - `belief_query`: `accepted: true`, `200`
  - `codex_update`: `accepted: false`, reason `"secure /message currently only accepts OBSERVATION_SHARE; got 'CODEX_UPDATE'"`
- **RESULT**: PASS
- **RECEIVER_EVIDENCE**: Node B's own Chronicle (`/tmp/lantern_local_agent_test/lantern-local-agent-openclaw.jsonl`) contains a real `OBSERVATION_CREATED` record with `content: "LANTERN_PUBLIC_PROOF_AtoB_d0025ebb"`, `id: 078a8953-4e9a-4e52-9c3b-e59c1e874eb7`, hash-chained (`previous_hash`/`current_hash`), independent of the caller's own process.

## TEST_ID: PUBLIC-PROOF-002 (B → A)

- **PURPOSE**: prove the reverse direction — real authenticated connection, message, query, and fail-closed rejection from Node B to Node A.
- **SOURCE_COMMIT**: `f0d3e2976b44d7d1f1c5df86c33dbbd61145cfa9`
- **ENVIRONMENT**: real running Node A process on `127.0.0.1:8765`; caller uses Node B's real on-disk identity at `/tmp/lantern_local_agent_test`.
- **COMMAND**: `LanternConnector(remote_url="http://127.0.0.1:8765", node_id="lantern-local-agent-openclaw", data_dir="/tmp/lantern_local_agent_test")` — see `/tmp/public_proof_test.py::run_direction("BtoA", ...)`.
- **EXPECTED**: same as above, mirrored direction.
- **OBSERVED**:
  - `identity_status: CRYPTOGRAPHICALLY_VERIFIED`
  - `session created: true`, `session_id NHDSuM-5v9DjERAjGSxwyKsTCdTrewOyw2YFr7ryMSo`
  - `evidence_exchange`: `accepted: true`, `observation_id 8a18d5a7-3929-4c32-b2d8-581f56c70c34`, marker `LANTERN_PUBLIC_PROOF_BtoA_934c4626`
  - `belief_query`: `accepted: true`, `200`
  - `codex_update`: `accepted: false`, same rejection reason
- **RESULT**: PASS
- **RECEIVER_EVIDENCE**: Node A's own Chronicle (`/tmp/lantern_public_experiment/data/lantern-field-experiment-1.jsonl`) contains a real `OBSERVATION_CREATED` record with `content: "LANTERN_PUBLIC_PROOF_BtoA_934c4626"`, `id: 8a18d5a7-3929-4c32-b2d8-581f56c70c34`, hash-chained.

## TEST_ID: PUBLIC-PROOF-003 (C → peer)

- **PURPOSE**: prove a connection from an independent third node.
- **STATUS**: **NOT ATTEMPTED — no Node C identity exists in this environment** (see `LANTERN_THREE_NODE_PROVENANCE.md`). Fabricating this test would require inventing a fictional identity, which is explicitly prohibited by the operating directive. This link is named here as missing, not silently omitted.
- **RESULT**: NOT_ATTEMPTED

## TEST_ID: PUBLIC-PROOF-004 (secret_transfer, A → B, synthetic value)

- **PURPOSE**: prove confidential secret transfer over an authenticated session, using a fresh, disposable, synthetic value the receiver has no prior knowledge of.
- **SOURCE_COMMIT**: `f0d3e2976b44d7d1f1c5df86c33dbbd61145cfa9`
- **ENVIRONMENT**: same as PUBLIC-PROOF-001, reusing session `wfBY2BSlG38Be3zB4bHcZ0UeAB25KkW3xz_2UdJShig`.
- **COMMAND**: sender generates `disposable_secret = b"LANTERN-PUBLIC-PROOF-" + secrets.token_hex(16)` locally at runtime (never hardcoded, never previously disclosed); `/secret/offer` then `/secret/send` per `lantern.secret_transfer` real ephemeral-X25519 protocol — see `/tmp/public_proof_test.py`.
- **EXPECTED**: receiver's authenticated-decryption succeeds; receiver-reported SHA-256 digest and length match the sender's locally-computed digest/length of the plaintext it generated, without the plaintext ever being transmitted back or logged.
- **OBSERVED**:
  - `SENDER GENERATED`: fresh 53-byte value, generated locally at runtime via `secrets.token_hex`
  - `AUTHORIZED`: `/secret/offer` → `accepted: true` (both nodes hold `secret_transfer` in their mutual `--authorize` grant as of this session's authorization-expansion event)
  - `AUTHENTICATED TRANSFER`: ephemeral X25519 keypairs generated fresh for this `transfer_id`, each bound via the long-term Ed25519 identity's signature (`create_ephemeral_bundle`/`seal_secret`)
  - `RECEIVER RECEIVED`: `/secret/send` → `accepted: true`, `reason: "Secret received and authenticated-decrypted successfully"`
  - `DIGEST MATCHED`: sender-local `sha256 = e3cf4352e72c18fdc175f23c6ec144e47603b281f5b8ca861a7e48f3cd1d3571`, length `53`; receiver-reported `secret_sha256` and `secret_length` — **identical**, confirmed programmatically (`digest_match: true`)
  - `EVIDENCE PERSISTED`: the transfer's `session_id`/`transfer_id`/digest/length are present in the JSON response captured at test time; the plaintext itself was verified absent from every log file and every file under both nodes' data directories (`grep` for the literal secret string returned no matches anywhere on disk)
- **RESULT**: PASS
- **RECEIVER_EVIDENCE**: receiver-computed `secret_sha256`/`secret_length` returned directly from Node B's own `receive_secret_transfer()` handler, matched independently against the sender's own local computation — this is the receiver's own observation, not an inference from the sender's claim.
- **Secret value itself**: **not published** (correctly withheld per directive section 8/16). Only the safe evidence above (digest match, lengths, transfer IDs) is published.

## TEST_ID: PUBLIC-PROOF-005 (fail-closed security)

- **PURPOSE**: prove that granting additional unrelated capabilities does not bypass an architecturally-disabled operation.
- **OBSERVED**: `codex_update` was deliberately **not** included in either node's capability grant this session specifically because it is disabled at the message-handler level (`bootstrap_node.py`'s secure `/message` path rejects any `message_type` other than `OBSERVATION_SHARE` unconditionally). Both PUBLIC-PROOF-001 and PUBLIC-PROOF-002 include a live `CODEX_UPDATE` attempt over an otherwise-fully-authorized, freshly-verified session, on both directions — both rejected with the same reason string, even after the mutual grant was expanded this session to include `belief_query, contradiction_tracking, snapshot_exchange, handshake, identity_proof, secret_transfer`.
- **RESULT**: PASS — a broader capability grant did not create a bypass for the one operation that remains architecturally disabled.

## Advertised-but-unenforced capabilities (transparency note)

`contradiction_tracking` and `snapshot_exchange` are present in
`DEFAULT_CAPABILITIES` and advertised in `/health`, and were included in
this session's authorization grant expansion for completeness, but **no
corresponding server-side endpoint exists anywhere in
`bootstrap_node.py`** to exercise them against. They are not called
"operational" anywhere in this manifest, per the directive's explicit
instruction not to call an advertised capability operational without an
actual server-side operation having been exercised.

## Chronicle / persistence evidence summary

| Marker | Persisted at | Verified |
|---|---|---|
| `LANTERN_PUBLIC_PROOF_AtoB_d0025ebb` | `/tmp/lantern_local_agent_test/lantern-local-agent-openclaw.jsonl` (Node B's own Chronicle) | OBSERVED via direct `grep`, hash-chained record present |
| `LANTERN_PUBLIC_PROOF_BtoA_934c4626` | `/tmp/lantern_public_experiment/data/lantern-field-experiment-1.jsonl` (Node A's own Chronicle) | OBSERVED via direct `grep`, hash-chained record present |
| Synthetic secret plaintext | **nowhere** (by design) | OBSERVED absent via `grep` across both data directories and both node logs |

## Clean-checkout reproduction

See `REPRODUCE.md`. Not independently re-run from a throwaway clone as part
of producing this manifest (all tests above ran against the existing
checkout and the existing long-running production processes, which is
explicitly what the directive asked to be proven — the real deployment, not
a simulation). An independent reviewer following `REPRODUCE.md` can perform
their own from-scratch verification.

## LANTERN PUBLIC THREE-NODE PROOF

- PUBLIC SOURCE → KNOWN COMMIT: PASS (OBSERVED)
- THREE IDENTITIES: **PARTIAL** — two real identities OBSERVED (Node A, Node B); Node C UNKNOWN/does not exist in this environment
- LEGITIMATE AUTHORITY: PASS (OBSERVED — operator `--authorize` mechanism, no self-issuance, no dynamic grant API in current runtime)
- CRYPTOGRAPHIC AUTHENTICATION: PASS (OBSERVED, both directions)
- REAL SESSION: PASS (OBSERVED, both directions, real two-phase challenge/proof)
- AUTHORIZED MESSAGE: PASS (OBSERVED, both directions)
- AUTHORIZED CAPABILITY (secret_transfer): PASS (OBSERVED, synthetic value, digest-matched)
- RECEIVER-SIDE OBSERVATION: PASS (OBSERVED — Chronicle records + receiver-computed digest, not sender claims)
- PERSISTED PROVENANCE: PASS (OBSERVED — hash-chained Chronicle entries)
- FAIL-CLOSED REJECTION: PASS (OBSERVED, both directions, post-grant-expansion)
- CLEAN-CHECKOUT REPRODUCTION: **PARTIAL** — documented and scriptable (`REPRODUCE.md`), not independently executed from a fresh clone as part of this manifest

**LANTERN PUBLIC THREE-NODE PROOF: PARTIAL**

Missing links, named explicitly:
1. Node C / third-party independent connection — no real third identity exists in this environment; not fabricated.
2. Clean-checkout reproduction — documented and scripted, but this manifest's own tests ran against the existing checkout/processes rather than a from-scratch clone performed as part of producing this manifest.

All other links in the proof chain are OBSERVED PASS against the real, currently-running, publicly-inspectable Lantern deployment.
