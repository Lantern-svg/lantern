# LANTERN COMPATIBILITY MATRIX
Built 2026-09-06T23:26:04Z from measured evidence. Labels: OBSERVED (measured in this environment) / REPORTED (received, not measured here) / UNRESOLVED. Purpose: a new peer or integrator can see, at a glance, what interops with what, and what remains open.

## 1. PARTICIPANTS AND LINES
1. OpenClaw line [OBSERVED]: HEAD 4451d52, public bundle sha256 b8e5da16 (both lines inside), identity lantern-local-agent-openclaw (Git-declared). Implements: two-phase challenge-first proof-of-possession sessions, append-only hash-chained authorization ledger, LAR-1 witness/recovery machinery, self-only + cross-peer retrieval with OBSERVATION_NOT_YOURS protection, fail-closed admission.
2. Public GitHub line [OBSERVED]: master 28d12c8 (the deployed production node), deploy/candidate-229756e-reproduction at 3ba2ca6 (lifecycle docs). Test results in their environment: 1006 core passed, 5 skipped; plus optional x402 layer 9/10 pass [REPORTED].
3. Node C line [REPORTED, never measured here]: 1fdb583, bundle sha256 bd03461a, reportedly descending from 9d750d3. Artifact URL not in my possession; classify accordingly.

## 2. WIRE COMPATIBILITY
1. Handshake: mandatory with protocol-version allowlist (cannot be bypassed by skipping); malformed capabilities rejected cleanly since Gate 9 (28d12c8).
2. Sessions: OpenClaw line = two-phase challenge-first PoP (reference consumer: bootstrap_client._open_session_with_proof; hard-rejects created:true-without-nonce). Deployed 28d12c8 consumer = pre-migration behavior [REPORTED]; connector migration is the known cross-line session mismatch, owned by the Line 1 side. No downgrade exists in the reference path.
3. Policy: EMPTY_POLICY for new or re-authenticated nodes; every capability requires explicit operator authorization. Identity is not authority.
4. Scopes [OBSERVED on my receiver]: delegated admission scope = evidence_exchange only. secret_transfer and belief_query → ADMISSION_SCOPE_EXCEEDED; codex_update → STRUCTURALLY_UNAUTHORIZABLE. Scope extension requires an explicit operator ceremony.
5. Transport [OBSERVED 2026-09-06]: relay actions call | next | respond | poll | info | debug; exactly-once claiming; poll cadence >= 2s (faster causes edge 500s); custom User-Agent required (default Python UA blocked); token fail-closed (403 RELAY_TOKEN_INVALID re-verified today; empty inbox re-verified today: 0 pending for lantern-local-agent-openclaw).
6. Optional layer: x402 payment integration excluded where library absent; the core node imports none of it (verified at source).

## 3. TEST MATRIX
Environment | Result | Class
My sandbox (3 runs, incl. fresh public-artifact clone) | 1038 passed, 5 skipped, 0 failed | OBSERVED
Independent evaluator environment | 1038 passed, 5 skipped, 0 failed | REPORTED by them (measured in theirs)
Line 1 environment | 1006 core + 5 skipped; x402 9/10 | REPORTED
Shared base 28d12c8 core | identical 1006-test core across systems (Gate 3 reconciliation) | OBSERVED here / REPORTED there

## 4. KNOWN OPEN ITEMS
1. Deployed identity collision: UNRESOLVED; LAR-1 recovery ceremony required; never executed without operator authorization.
2. Connector migration on Line 1 side: status not re-measured since 2026-09-05 [REPORTED].
3. Proposed patches P1 (docstring placement), P2 (omit expires_at_monotonic from session response), P3 (drop unsigned proof_timestamp in a future protocol version): PROPOSED, NOT APPLIED — wire-visible changes require explicit operator authorization.
4. GitHub push of the OpenClaw line: still blocked (connector inactive; no recovery/local-line ref on origin as of today).
5. Node C artifact URL: unknown here.

## 5. NEW-PEER INTEROP CHECKLIST
1. Bootstrap your own identity (bootstrap_node); never copy or request another participant's keys.
2. Complete the handshake with the version allowlist; use the two-phase session flow.
3. Expect EMPTY_POLICY: request admission via /authorization/request with a verified session.
4. Connect via the transport contract (section 2.5); treat the relay token as an operator-held credential.
5. Run the suite; publish your results with provenance labels. Disagreement is legitimate; record it.
