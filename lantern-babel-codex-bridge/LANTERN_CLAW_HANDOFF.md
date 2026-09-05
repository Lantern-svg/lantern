# Lantern Full-Capability Authorization & Verification — 2026-09-05

## Provenance

- Git HEAD (unchanged before/after this event): `f0d3e2976b44d7d1f1c5df86c33dbbd61145cfa9`
- Branch: `deploy/candidate-229756e-reproduction` (not merged/pushed to `master`)
- `master`/`origin/master`: `28d12c853eafdab9aeb2f443648b5c0bd0d240df` (untouched)
- Working tree: clean before and after this event (no source changes were required — this was an authorization/operational action, not a code change)

## 1. Capabilities enumerated (OBSERVED from source + live `/health`)

| Capability | Advertised | Enforcement point in current source |
|---|---|---|
| `evidence_exchange` | yes | `/message` (OBSERVATION_SHARE path) — real gate |
| `belief_query` | yes | `/belief/query` (`query_beliefs()`) — real gate |
| `handshake` | yes | `/handshake` — real gate |
| `identity_proof` | yes (once identity loaded) | `/identity/*` (`verify_identity_proof()`) — real gate |
| `secret_transfer` | yes | `/secret/offer`, `/secret/send` — real gate |
| `contradiction_tracking` | yes | **advertised only — no endpoint/enforcement exists in current source** |
| `snapshot_exchange` | yes | **advertised only — no endpoint/enforcement exists in current source** |
| `codex_update` | `false` | **architecturally disabled** — `/message` rejects any `message_type` other than `OBSERVATION_SHARE`, regardless of any capability grant |

## 2. Authorization grants before/after (OBSERVED)

**Only real authorization mechanism in current source**: the operator-supplied `--authorize node_id:cap[,cap...]` CLI flag at process launch, parsed by `_parse_authorize_args()` in `bootstrap_node.py`. There is no dynamic/self-issued grant API. `peer_authorization.py`'s signed-grant model exists as a standalone library but is **not wired into `bootstrap_node.py`'s runtime** — confirmed via source inspection (no loading code, no grant files on disk for either node prior to this event).

| Direction | Before | After |
|---|---|---|
| `lantern-field-experiment-1` → `lantern-local-agent-openclaw` | `evidence_exchange, belief_query, contradiction_tracking, snapshot_exchange, handshake, identity_proof` | + `secret_transfer` |
| `lantern-local-agent-openclaw` → `lantern-field-experiment-1` | `evidence_exchange` | `evidence_exchange, belief_query, contradiction_tracking, snapshot_exchange, handshake, identity_proof, secret_transfer` |

`codex_update` was deliberately **not** granted to either side — granting it would have no effect given the architectural rejection above, and it is excluded from `DEFAULT_CAPABILITIES` (`False`) by design pending an explicit trust/evaluation protocol for remote-authority claims.

Mechanism used: graceful `SIGTERM` of each existing process, relaunch with an updated `--authorize` argument, identical launch command otherwise (same host/port/node-id/data-dir/session-ttl). Identity preserved exactly — `public_key` and `binding_signature` byte-identical pre/post restart for both nodes (confirmed via `/health`). New PIDs: `lantern-field-experiment-1` 94141→94327; `lantern-local-agent-openclaw` 94143→94329.

Full structured event record: `/tmp/lantern_public_experiment/authorization_grant_record_2026-09-05.json` (not committed to git — operational/runtime record, analogous to a log, not source).

## 3. End-to-end capability verification (OBSERVED, harmless synthetic data only)

All requests below were made from `lantern-field-experiment-1`'s real on-disk identity against the real running `lantern-local-agent-openclaw` production process (`http://127.0.0.1:8767`), over a freshly-established, real challenge/proof-verified session.

| Capability | Result |
|---|---|
| `evidence_exchange` | **PASS** — synthetic marker `SYNTHETIC_CAPABILITY_VERIFY_EVIDENCE_001` accepted, `observation_id d816d834-1fe8-4e99-a1cc-205426108460` |
| `belief_query` | **PASS** — query accepted, `200`, well-formed response |
| `codex_update` | **correctly still rejected** — `"secure /message currently only accepts OBSERVATION_SHARE; got 'CODEX_UPDATE'"` (proves the architectural gate holds independent of any capability grant) |
| `secret_transfer` | **PASS** — disposable synthetic value `SYNTHETIC-TEST-VALUE-2026-09-05-not-a-real-secret` (49 bytes, **not a real credential**) sealed with fresh ephemeral X25519 keys bound to both nodes' real long-term Ed25519 identities, transmitted, and authenticated-decrypted by the receiver. Receiver-reported `secret_sha256 e1c131edda0457ae0534dd0206fb81f94fde5ae6c97bc064073425cfdb9bbe1d` / `secret_length 49` independently matches `sha256()` of the known synthetic plaintext, computed locally — proof the receiver actually decrypted the correct value, without requiring the receiver to ever echo plaintext back over the wire or into any log. |

`contradiction_tracking` and `snapshot_exchange`: **not exercised** — no real endpoint exists to exercise them against in current source (see table above). Granting the capability string was harmless (it is now `authorized` in policy terms) but there is nothing in `bootstrap_node.py` that consults it yet.

Verified no plaintext leakage: grepped both nodes' logs and both data directories for the synthetic secret string — not present anywhere on disk or in logs.

## Summary (OBSERVED unless noted)

- **Capabilities successfully authorized**: `belief_query`, `contradiction_tracking`, `snapshot_exchange`, `handshake`, `identity_proof`, `secret_transfer` (added to whichever side didn't already have them; `evidence_exchange` was already present both directions).
- **Capabilities already authorized**: `evidence_exchange` (both directions, pre-existing).
- **Capabilities unavailable in this build**: none unavailable per se, but `contradiction_tracking` and `snapshot_exchange` have no server-side enforcement to exercise (advertised-only), and `codex_update` is architecturally disabled regardless of grant.
- **Capabilities that failed authorization**: none — all requested grants succeeded via the existing operator-level `--authorize` mechanism; no bypass was needed or used.
- **Actual end-to-end capabilities successfully exercised**: `evidence_exchange`, `belief_query`, `secret_transfer` (all three PASS, live, real sockets, real crypto, synthetic payloads only). `codex_update` exercised as a **negative** test and correctly rejected.

## Invariant preserved

No node manufactured its own authority. Every grant flowed through the same pre-existing, operator-controlled `--authorize` mechanism used to establish the original grants — restarting with an expanded flag, not a new bypass, not self-issuance, not a dynamically-invented grant API. Identity verification and cryptographic proof-of-possession were not weakened at any point (session establishment still required the full real challenge/response flow; `secret_transfer` still required a valid, non-expired, peer-bound session plus the explicit capability grant, exactly as designed in `secret_transfer.py`/`bootstrap_node.py`).
