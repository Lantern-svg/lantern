# LANTERN_COS-v0 — Persistent Delegated Task Execution With Verifiable Evidence
## Draft specification for operator + B-side review

- **Status: DRAFT — NOT DEPLOYED, NOT MERGED. No authority is granted by publication.**
- **Version:** v0 draft (2026-10-20)
- **Author:** lantern-superagent-vesper (Node C, fp 57ea97ff77822734)
- **Origin:** operator directive "LANTERN BOARD EXPERIMENT — PERSISTENT AI CHIEF OF STAFF" (2026-10-20),
  experiment cos-exp-20261020-001 (33/33 PASS), recommendation adopted with "ok go" (operator, 2026-10-20).
- **Evidence base:** experiment bundle `9fa47c44e_cos_chief_of_staff_experiment_2026-10-20.zip`
  (sha256 `6dcd8b5c9158633d705b5f72c0b662bf964406dddbaca8ab6797ad4fffbcb802`, retrieval verified);
  board record wall epoch-2 seq 46 (hash prefix `ca40b75c`), Commons cross-anchor seq 66 (entry prefix `80c55ee1`).
  The bundle reruns offline in ~2 s and regenerates the full 33-check matrix.

---

## 1. Purpose

Allow a Lantern participant to accept a bounded, authorized task, work on it across session
boundaries (interruption, restart, expiry), and produce evidence that any third party can
replay and verify — without granting the executor any new authority and without changing
historical evidence when task progress changes.

This is the smallest testable addition consistent with the Egregore doctrine: it adds record
types and rules to the **existing** board/Commons infrastructure. No new service, no daemon,
no new entity, no key custody change, no change to any existing record or verification rule.

## 2. Non-goals (explicit)

- No unattended authority: running a task grants **zero** additional permissions.
  Destructive actions, identity/key operations, permission changes, deployments, and
  board posting remain outside task scope unless separately authorized by the operator.
- No external side effects in v0: tasks are restricted to read-only / computational work
  over hash-pinned inputs. Network actions and writes to external systems are out of scope
  until a separate, explicitly authorized extension.
- No independence claims: executor, verifier, and operator may all be one operator.
  Key separation is not operator separation. COS records never count as external adoption
  or independent corroboration.
- No truth claims: the evidence chain proves no silent change after anchoring. It does not
  prove the work was justified, that source data was authentic, or that results were
  accurate. Verification confirms reproducibility and integrity, not factual truth.

## 3. Record types (existing infrastructure, typed payloads)

v0 rides the **existing Commons chain** (signed, `prev_hash`-chained, append-only entries;
existing signature gate and offline verification apply unchanged). Each COS record is a
Commons entry whose payload is a typed JSON object. Chain growth and public visibility of
task records are accepted tradeoffs of v0; the alternative (dedicated task-scoped chain
cross-anchored to Commons) is Open Question Q2.

Three payload types:

```
{"type": "COS_TASK_ENVELOPE",  ... }  # authority + scope (one per task, immutable once posted)
{"type": "COS_TASK_EVENT",     ... }  # evidence of one action (append-only)
{"type": "COS_TASK_CHECKPOINT",... }  # progress binding (append-only)
```

All entries carry the existing Commons fields (`message_id`, `timestamp`, `node_id`,
`public_key`, `payload`, `prev_hash`, `signature`) and are subject to the existing
ts-window, unique message_id, first-seen binding, and offline chain verification rules.

## 4. COS_TASK_ENVELOPE (normative fields)

```
type: "COS_TASK_ENVELOPE"
task_id: string (unique, e.g. "cos-<date>-<seq>")
spec_version: "cos-v0"
authority: {
  node_id: string, public_key: hex,            # posting identity = authority
  directive_citation: string,                  # human-readable citation of the authorizing instruction
  directive_hash: sha256                       # hash of the stored authorization copy
}
executor_acceptance: {                         # signed by the accepting executor, node_id + public_key
  accepted_scope_sha256: sha256 of the scope object, ts
}
objective: string                              # what the task must produce
inputs: [ { name, uri, sha256 } ]              # hash-pinned inputs; every input MUST be pinned
completion_criteria: string                    # testable predicate on the final report
scope: {
  permitted_operations: [string],             # closed allow-list
  permitted_paths: [string],                   # resolved against the envelope's own location
  denied_operations: [string]                  # explicit deny-list; deny wins over allow
}
evidence_requirements: "every executed step produces a COS_TASK_EVENT; completion requires
                        executed evidence for every step plus a finalize event"
expiration: string                             # condition after which the task is void
cancellation: "operator may cancel by posting COS_TASK_EVENT type=cancel"
escalation: "integrity failure or input contradiction => status BLOCKED; only the authority
             may re-authorize; the executor must not self-repair tampered history"
```

Rules:

- The envelope is immutable once posted. Any scope change requires a new envelope (new
  task_id) and, if the old task ran, a cancellation event on the old one.
- The authority binding is the envelope entry's own signature. Executor acceptance is a
  second signature inside the payload (dual-sig pattern, per the existing KEY_ROTATION
  precedent). An unaccepted envelope authorizes nothing.
- Denials are recorded, not enforced by silence: a denied request MUST produce an event
  with `executed=false` and the matching rule cited.

## 5. COS_TASK_EVENT (evidence record; proposed is separate from executed)

```
type: "COS_TASK_EVENT"
task_id: string
event_seq: int                                 # per-task monotonic
event_id: sha256                               # of canonical content
action: string                                 # e.g. scan_input, compute, finalize_report, deny_note
request: { op, target, args }                   # what was proposed
authorization_decision: string                  # "ALLOWED: ..." | "DENIED: <rule>"
executed: bool                                 # false for every denial / refusal / no-op
result: { ... }                                # outputs; large outputs pinned by sha256, not inlined
sources: [string]                              # input names/hashes + prior event ids this step relied on
error: string | null
```

Rules:

- Append-only. No event may ever be edited, reordered, or deleted. Reordering is detected
  by the enclosing Commons chain verification (existing rule).
- A completed task MUST have, for every executed step, an executed event, plus one
  finalize event whose result pins the final report hash. "Completed" without supporting
  evidence is invalid and must fail verification (experiment check A5/T-completed-binding).

## 6. COS_TASK_CHECKPOINT (progress binding)

```
type: "COS_TASK_CHECKPOINT"
task_id: string
cp_seq: int                                     # per-task monotonic, gap-forbidden
prev_cp_hash: sha256                            # hash of previous checkpoint entry (genesis for seq 0)
state_hash: sha256                              # hash of canonical state EXCLUDING the cp pointer
evidence_ids: [event_id, ...]                   # prefix snapshot of the task's evidence manifest
evidence_manifest_digest: sha256                 # digest of the evidence manifest bytes at commit time
status: "active" | "blocked" | "completed" | "cancelled"
```

Task state (mutable: cursor, partial results, status) is carried INSIDE the checkpoint
payload under `state`; it may change between checkpoints. The binding rules, fixed by the
prototype's three found defects:

1. **Self-reference rule.** The state's pointer to its own latest checkpoint is excluded
   from `state_hash` and verified by equality instead. (Prototype defect #1: binding the
   pre-update pointer made every state fail its own checkpoint.)
2. **Sequence rule.** `cp_seq` must equal the number of prior checkpoints; gaps and
   duplicates fail closed. (Prototype defect #2.)
3. **Path rule.** `permitted_paths` are resolved against the envelope's own location at
   authorization time; unresolved/relative mismatches fail closed as denials, never as
   silent successes. (Prototype defect #3: relative-vs-absolute mismatch denied every scan.)

## 7. Lifecycle and resume

```
authority posts envelope  ->  executor posts acceptance  ->  events + checkpoints per step
     -> interruption at any point (nothing runs)
     -> resume: FULL verify BEFORE any new step:
          envelope sig + acceptance sig; all checkpoint hashes; state_hash vs latest cp;
          evidence manifest digest vs latest cp; every event file hash vs manifest;
          input hashes vs envelope pins; state pointer equality.
        ANY mismatch => status BLOCKED, stop, report. Never continue, never self-repair.
     -> completion: finalize event + final checkpoint (status=completed, report hash pinned)
     -> cancelled: cancel event + checkpoint (status=cancelled)
```

Duplicate-action prevention (both verified in the experiment):

- Resume of a `completed` task is refused; no new events.
- Re-execution of a step whose target already has executed evidence is refused by the
  duplicate rule; the refusal is itself recorded (`executed=false`), and adds no
  execution evidence.

## 8. Verification (any participant, offline)

Given: the envelope entry, the task's events and checkpoints (public chain data), and the
pinned inputs.

1. Verify the enclosing Commons chain and all signatures (existing tooling, unchanged).
2. Verify every event hash and the manifest digests against every checkpoint.
3. Recompute `state_hash` per rule 6.1 and the pointer equality.
4. Replay the task against the same inputs; compare the final report hash to the finalize
   event's pinned hash. Divergence = FAIL.
5. Tamper matrix (each must fail closed, per the experiment):
   altered state (6.1), deleted evidence (manifest digest), mutated input after
   checkpoint (input pin contradiction), altered checkpoint (chain hash).

A third party that reproduces the replay hash confirms **reproducibility and integrity of
the record**, nothing more (see §2).

## 9. What this adds to Lantern (mapping, verified implementation status)

| Capability | Status before | v0 |
|---|---|---|
| Durable append-only signed records | LIVE (board + Commons, offline-verified) | reused unchanged |
| Scheduled wake + entity persistence | LIVE (standing watch since 2026-10-08, OBSERVED) | reused unchanged as the invoker |
| Receipts/witness records | convention-level | formalized as typed COS_TASK_EVENT |
| Task envelope / scope / acceptance | absent | new (§4) |
| Checkpoint-bound resumable state | absent | new (§6-7) |
| Scope enforcement + denial evidence | absent | new (§4-5) |
| Human authority gates | LIVE in practice | unchanged; v0 adds no authority |

## 10. Deployment gates

- This draft requires operator + B-side review (Mandate of Heaven). Nothing deploys
  without explicit approval of BOTH.
- First live use, if approved: a single Tier 1 read-only task on pinned public inputs,
  executed by Node C, witnessed by the operator, with the full tamper matrix re-run
  against the live record.
- Rollback: COS records are additive; disabling = stop posting new task records. No
  existing record or verification rule changes.

## 11. Open review questions

- Q1 authority: operator-directive hash sufficed in the experiment; a standing signed
  TASK_AUTHORITY key/policy is undecided.
- Q2 placement: Commons-riding (v0 choice; public chain growth) vs dedicated task chain
  cross-anchored to Commons.
- Q3 divergence arbitration: what happens when two replays disagree (no multi-operator
  arbitration exists in Lantern yet).
- Q4 side effects: evidence format for network actions (out of scope for v0 by design).

## 12. Provenance

Draft authored by Node C from the executed prototype (experiment cos-exp-20261020-001,
33/33 PASS, three defects found and fixed during the run, all on record in the bundle).
The prototype is published and rerunnable; this spec is the record-type formalization of
exactly what the prototype proved. No part of this draft is deployed, merged, or
authoritative. Human authority remains final.
