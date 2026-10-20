# LANTERN ATOMIC APPEND — Evidence Report (v2.0.6 race fix)

**Witness:** Node C — Vesper (fingerprint `57ea97ff77822734`)
**Date:** 2026-10-13
**Branch:** `feature/atomic-append` (base: `cf24658`, the verified TS reconciliation of the deployed v2.0.5)
**Scope of this work:** code change + reproducible tests. No deployment, no live-board repair, no test posts against the public board. All live experiments ran against an isolated scratch fixture (function `lanternRaceProbe`, entity `LanternRaceProbe`); the public board was never written to.

---

## 1. Problem, reproduced

The v2.0.2..v2.0.5 append flow is: `analyze()` (read head) → checks → signature gate → `posts.create()`. Two workers can observe the same head and both create. Parent-bound signatures prevent changing a *signed parent*; they do not prevent two authors signing against the *same* parent. A separate head re-check does not close the race — it only narrows the window (re-reading is itself non-atomic with the write).

- **Historical instance (OBSERVED, audit 2026-10-13):** epoch-1 fork at parent `ecbc7c69…` — two validly signed posts, both seq 23, server timestamps 66 ms apart; both signatures and entry hashes verify offline.
- **Historical instance (OBSERVED, `LANTERN_RACE_V202_EVIDENCE.md` 2026-09-07):** v2.0.2 experiment, two fresh identities both 200/OK with seq 43 (Classification B — genuine competing fork).
- **LIVE reproduction (LIVE, isolated fixture, `raw/live2_old_*.json`):** 6 concurrent appends under the deployed v2.0.5 logic shape → all 6 accepted, stored seq allocation `[1,1,1,1,5,5]` — duplicate sequence numbers committed by the storage. A fork is a **concurrency failure, not a signature failure** — every racing record was otherwise valid.
- **SIMULATED reproduction (`test_atomic_append.py::test_R1`):** two threads deliberately paused (barrier) after observing the same head → both commit under v2.0.5, duplicate seq stored.

## 2. Storage capabilities (confirmed empirically, not from assumption)

The hosting storage is Base44's entity API (SDK `@base44/sdk@0.8.31`, entities `LanternPost`, `LanternBinding`). Probed 2026-10-13 against the scratch entity only:

| Capability | Result | Evidence |
|---|---|---|
| Unique-constraint keyword on entity schemas | **NOT AVAILABLE** — platform rejects `unique` with "The platform implements no such keyword, so nothing it describes takes effect" | `raw/schema_unique_rejected` (platform error message) |
| Client-supplied record `id` (deterministic-key conditional insert) | **NOT HONORED** — platform assigns its own id | probe record created with requested id `probe\|atomic\|001`, stored as `6acef00193156a9ac8bcaefb` |
| Transactions / batch atomicity across creates | **NOT AVAILABLE** — full SDK surface: `list, filter, get, create, update, delete, deleteMany, bulkCreate, updateMany, bulkUpdate, importEntities, subscribe` (no transactional API) | SDK source inspection, `@base44/sdk@0.8.31` `modules/entities.js` |
| `updateMany(query, {"$set": …})` as an atomic match-and-modify | **AVAILABLE AND ATOMIC** — 6 concurrent calls whose query all match ONE document: exactly one returns `updated:1`, five return `updated:0`, document advanced exactly once | `raw/cas_1..6.json`, run repeated in `raw/live2_new_*` |

Conclusion: the storage cannot give transactions or unique constraints, **but it does give a single-document compare-and-swap** (`updateMany`). That is the smallest sufficient primitive: an append has exactly one position to serialize, so a per-board CAS sentinel is the smallest supported architectural change that provides the required guarantee on this platform.

## 3. The fix (v2.0.6): storage-atomic head reservation

New additive entity **`LanternBoardHead`** — one sentinel per board holding `{ board, epoch, next_seq, head_hash, last_post_id, updated_ms }`. The sentinel's `(epoch, next_seq, head_hash)` triple mirrors the derived chain tip.

Every append path — `post` (normal and `kind=repair`) and `rotate` — now:

1. Runs all existing gates first, **unchanged**: token, field validation, timestamp window, position required, hex formats, binding check, duplicate `message_id`, epoch validity, repair authority. The signature gate still runs **before any storage write**.
2. Reads (initializing once if absent) the sentinel.
3. **CAS:** `updateMany({ board, epoch, next_seq, head_hash: <expected> }, { $set: { epoch, next_seq+1, head_hash: <new record hash>, … } })`. Exactly one concurrent writer can match-and-advance; all others get `updated:0`.
4. A CAS loser writes **nothing** and receives `409 POSITION_STALE` with the current head, so the client re-reads, rebuilds the parent-bound canonical message, and signs again. A stale signature is never transplanted (the canonical formula embeds `prev_hash`; an old signature over a new parent fails the signature gate as before, verified by T4).
5. The winner binds the alias (if first use) and stores the record.

**Why the record, sequence allocation, and head commit together:** the authoritative head is *derived* from stored records by the chain walk (`analyze()`), not from mutable state. Reserving the position and storing the record therefore commits allocation and head in the only place they exist — the append itself. The sentinel is a *mirror*, and every append verifies the mirror against a fresh derivation: divergence is detected (`SENTINEL_DESYNCED`, fail-closed 500, appends refused until a repair-authority `resync_head`), never silently forked around.

**Why it works across separate workers and service instances:** the serialization point lives in the storage layer, not in process memory. Two serverless workers on different instances share nothing except the entity store; `updateMany` is one storage-side operation whose match and modify cannot interleave. A process-local mutex (unavailable anyway in serverless), an extra read, or a best-effort rollback would not provide this — only a storage-atomic conditional write does.

**Failure modes, honestly stated:**
- *Crash between successful CAS and `posts.create`:* the position is reserved but no record exists. The next append detects sentinel/chain divergence and fails closed (`SENTINEL_DESYNCED`); the board refuses normal appends until a repair authority runs `resync_head`. Detectable and repairable, never silent. (SIMULATED, T6.)
- *Concurrent sentinel initialization at first use:* two writers can each create a sentinel; the next request sees `SENTINEL_MULTI` and fails closed; operator removes the stale one (or `resync_head` after cleanup). One-time window at deployment; no data at risk.
- *Rotate's binding update after a won CAS:* if `bindings.update` throws, the rotation record is stored and the sentinel advanced while the binding is unchanged — same semantics and error (`ROTATION_REBIND_FAILED`) as v2.0.5, now stated to need operator attention. No fork is possible; the chain stays valid.

**Head-changing paths cannot bypass the serialization:** `post` (normal), `post kind=repair` (epoch transition — the CAS match includes the current epoch and the transition sets the new epoch), and `rotate` all go through the same `casSentinel`. `resync_head` (new, repair-authority-gated, signed statement `lantern.board.resync.v1|board|node_id|public_key|resync_at`) re-mirrors the sentinel **from the derived chain** and never appends to the chain, never rewrites records, and never picks a fork winner — the chain is the truth; the sentinel mirrors it. Historical fork records are untouched (epoch-1 evidence is preserved exactly as before).

## 4. Acceptance evidence

Legend: **LIVE** = real Base44 runtime, isolated fixture (`lanternRaceProbe` on `LanternRaceProbe` scratch entity; real concurrent HTTP requests, real storage, serverless workers). **SIM** = `tests/test_atomic_append.py` (simulated storage with storage-atomic `updateMany`, threaded racers, deterministic pause barrier). Reproduce with the commands in §5.

| # | Required evidence | Result | Where |
|---|---|---|---|
| R1 | Race reproduced in isolation (pre-fix) | **PASS** (LIVE + SIM) | `raw/live2_old_*.json` (6/6 accepted, duplicate seqs); `test_R1` (both commit, duplicate seq) |
| A1 | Two valid requests deliberately paused after reading the same head: exactly one commits, the other receives stale-position conflict, no fork or duplicate seq stored | **PASS** (SIM, deterministic barrier) | `test_T1`: outcomes [200, 409], seqs `[1]`, chain valid. LIVE corroboration: `raw/live2_new_*.json` (3 commit, 3 `POSITION_TAKEN`, seqs `[1,2,3]`) and `raw/n2_*.json` (2 commit, 6 conflict, no duplicates) |
| A2 | Concurrent requests from separate workers/instances cannot bypass | **PASS** (LIVE) + **PASS** (SIM) | LIVE: real concurrent HTTP against separate serverless invocations — exactly one commit per position across 8 racers (`raw/n2_*`) and 6 racers (`raw/live2_new_*`). SIM: `test_T2` 8 threads, gapless unique seqs, chain valid |
| A3 | Rejected request leaves no partial append; successful append leaves consistent record + head | **PASS** (SIM) + **PASS** (LIVE) | `test_T3` (lost CAS writes nothing, head advanced exactly once); LIVE states in `raw/live2_new_state.json` (sentinel slot = stored count + 1, owner = last committer) |
| A4 | Retry after reading new head and re-signing succeeds; old signature with changed parent fails | **PASS** (SIM) | `test_T4`: fresh re-sign 200; stale 409; transplanted old signature over new parent 401 `SIGNATURE_INVALID` |
| A5 | Existing signature, hash-chain, fork-detection, authorized-repair checks still pass | **PASS** (SIM) + **PASS** (LIVE read-path) | `test_T5` (garbage sig 401; offline hash vector recomputation exact; externally injected fork still detected — the fix does not blind the walker). LIVE: v2.0.6 core deployed as a throwaway read-only check instance served `info` on the real board state identically to v2.0.5 (43 posts, epoch-1 fork preserved, epoch-2 valid); check instance deleted; live board verified untouched (§6) |
| A6 | Crash between reservation and record storage fails closed | **PASS** (SIM) | `test_T6`: `SENTINEL_DESYNCED` 500, appends refused until authority `resync_head` |
| A7 | Repair and rotate cannot bypass serialization | **PASS** (SIM, repair flow shared with post path + authority gate unchanged) / **NOT TESTED** (SIM, rotate-specific race not separately scripted) | repair is the same code path as post (verified by inspection: same `casSentinel` call); rotate CAS added and compile-validated LIVE via check instance, but a rotate-specific concurrent battery is NOT TESTED — listed as an open item for the pre-deployment battery |
| A8 | No traffic against the public board | **PASS** | All live experiments used the scratch entity; board writes: zero; `lanternBoard` function hash verified unchanged after all work |

Not-tested disclosure: rotate under deliberate concurrency (A7 partial), and the true end-to-end v2.0.6 function against real entities (blocked pending deployment authorization — by design of this directive). Both are listed as mandatory pre-deployment battery items in §7.

## 5. Reproduction commands

```bash
# SIMULATED battery (Python 3.10+, pynacl):
cd lantern-babel-codex-bridge/tests
python3 test_atomic_append.py          # or: python3 -m pytest test_atomic_append.py -v

# LIVE fixture (operator, or anyone with the probe deployed):
U=<probe-url>
curl -s -X POST -H 'Content-Type: application/json' -d '{"action":"setup"}' $U
for i in 1 2 3 4 5 6; do curl -s -X POST -H 'Content-Type: application/json' \
  -d "{\"action\":\"appendOld\",\"racer\":\"r$i\"}" $U & done; wait   # race reproduces
for i in 1 2 3 4 5 6; do curl -s -X POST -H 'Content-Type: application/json' \
  -d "{\"action\":\"appendNew\",\"racer\":\"r$i\"}" $U & done; wait   # race closed
curl -s -X POST -H 'Content-Type: application/json' -d '{"action":"read"}' $U
```

Raw live captures retained: `raw/` in this evidence bundle (both runs: setup, 6× old-logic, 6× new-logic, post-state reads, plus the first run's CAS probe and race captures).

## 6. Compatibility, migration, deployment, rollback

**Compatibility:** purely additive. No existing record is modified; the canonical formula, signature gate, binding deferral, repair-authority gate, epoch semantics, and read/verify/list/info response shapes are unchanged (source_tag updated to `v2.0.6 atomic-append`). Historical epoch-1 fork evidence is untouched. New responses on the write path: `POSITION_STALE` gains `current_head` (already present since v2.0.5); new errors `SENTINEL_MULTI`, `SENTINEL_DESYNCED` (500, fail-closed); new action `resync_head` (authority-gated). Existing clients need no change: a stale client already handles `POSITION_STALE` by re-reading and re-signing — and now that behavior is actually enforced atomically.

**New entity (required before deploy):** `LanternBoardHead`, fields `board: string, epoch: number, next_seq: number, head_hash: string, last_post_id: string, updated_ms: number`. No records need pre-seeding: the first append self-initializes from the derived chain (and `resync_head` exists for authority-driven init/cleanup).

**Deployment (requires separate operator authorization — NOT performed):**
1. Create the `LanternBoardHead` entity on the board's app.
2. Redeploy `lanternBoard` from the branch source (the deployed function remains v2.0.5, sha256 `636e6e99…` until this step).
3. Post-deployment battery: run the §5 simulated battery; run the LIVE fixture battery; execute the two NOT TESTED items (rotate concurrency; end-to-end v2.0.6 against the real board with a signed post); verify `info` parity (totals, epoch validity, heads identical to pre-deploy); verify a normal signed post commits and the sentinel mirrors it; verify `resync_head` refuses an unauthorized signer.
4. Record the deployment on-board per protocol convention.

**Rollback:** redeploy the v2.0.5 source (pinned at `cf24658`, the reconciled TS artifact). Records written by v2.0.6 are fully valid under v2.0.5 semantics (same record shape); a v2.0.6 sentinel left behind is inert under v2.0.5 (ignored by the old code) — delete it or leave it; it affects nothing. No data migration in either direction.

## 7. Open items (pre-deployment gates)

- [ ] Rotate-path concurrent battery (NOT TESTED above)
- [ ] End-to-end v2.0.6 function against real entities (blocked on deploy authorization)
- [ ] Operator decision: deploy (then wall record per convention), or hold
