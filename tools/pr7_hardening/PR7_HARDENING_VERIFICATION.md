# PR #7 Follow-up Hardening — Independent Verification Record
**Date:** 2026-10-21 (Node C / Vesper, local sandbox only — no live Base44 probe, no push, no merge, no deployment)
**Scope:** Independent re-verification of the uncommitted worktree hardening on top of PR #7 (Lantern v2.0.6 sentinel-CAS), covering the staggered initialization race, randomized concurrency at scale, crash points, rotation battery, fix isolation, and the provider-atomicity assumption. All testing used the local gate-controlled storage mock (scripted + seeded-random modes) against byte-identical test copies of the two sources.

## Sources under test
| Label | Origin | sha256 |
|---|---|---|
| baseline (PR #7 as pushed) | `git show pr7:.../lanternBoard_base44.ts` | 5b27039505f7a75cb5412cc8da1d6117be8a9d2eee59f1838ddac6d6e6f5c30e |
| v8 (worktree hardening, uncommitted) | worktree `lanternBoard_base44.ts` | f48e32f63079afb8c582b51fa3fddcd48b71c37951acb9ce842ecfe8d66da34f |
| v1 idCAS-only / v2 recount-only / v3 noInit-only / v4 idCAS+recount / v5 idCAS+noInit / v6 recount+noInit / v7 all-three | variants.py built from baseline, SDK-import redirect only | see manifest |

Test copies differ from the source **only** by the documented SDK-import redirection (verified by diff: exactly 2 lines).

## Gate-integrity requirements (all met)
- F1 hang root-caused: the original driver double-counted released gate entries (release accounting bug in the harness, not the product); gate entries now carry IDs and release accounting is single-increment.
- Every drive loop has a wall-clock budget and throws a diagnostic on timeout (caught three harness bugs mid-run rather than hanging: two gated calls left in scripted mode, one truncated tail).
- Fresh gate state per trial (`admin.clear()` resets collections, queue, opLog, faults); per-trial 10s watchdog; timed-out trials recorded as failures, never skipped.
- Per-trial JSONL with source sha256, seed, op trace, sentinel IDs, CAS queries/targets/results, committed seqs, writer outcomes, final verification, classification.
- Accounting sums verified: `fork+halt+clean+other == trials_attempted` in every config (sum_check recorded per summary).
- Reproduction: scripted schedules are deterministic (rerun of the staggered race reproduces the FORK byte-for-byte in structure); randomized trials record their seed and full delay policy; command line stored in each summary.

## Critical result (the question this run answers)
**Does the exact staggered schedule produce two committed sequence-1 posts on baseline PR #7, and does the patch prevent that outcome? YES → YES.**
- Baseline, schedule (a) staggered auto-init, reverse filter order: **FORK** — both writers 200, duplicate seq [1], 2 head sentinels, 2 posts at seq 1. Deterministic; full trace in `f1_a_pr7_reverse.txt`.
- Baseline, same schedule, insertion order: no fork but a fail-closed MULTI halt (2 heads created; next append halts).
- Patched (v8): both writers 500 SENTINEL_MISSING, **zero head records created, zero commits** — the un-initialized window is closed; a stale writer against a moved head gets 409 POSITION_STALE (schedule (b)).

## Fix isolation (7 variants, F1 matrix + 300-trial randomized, fresh family, 6 writers)
| Variant | F1 (a) staggered | Randomized fresh, insertion | reverse | Verdict |
|---|---|---|---|---|
| baseline | FORK | 10 forks/300 | 25/300 | init race present under realistic concurrency in BOTH orders |
| v1 idCAS only | FORK | 0 | **80/300** | idCAS alone makes the reverse-order fork WORSE (the stale writer claims its own lookalike record) |
| v2 recount only | FORK | 8/300 | 32/300 | recount is inert for the init race (by design: it guards resync) |
| v3 noInit only | CLEAN (MISSING) | 0 | 0 | necessary and sufficient: posts never create head records |
| v4 idCAS+recount | FORK | 0 | **105/300** | worst combo without noInit |
| v5 idCAS+noInit | CLEAN | 0 | 0 | clean |
| v6 recount+noInit | CLEAN | 0 | 0 | clean |
| v7 all three | CLEAN | 0 | 0 | clean |
| v8 full worktree | CLEAN | 0 (300 clean, 1,800 MISSING refusals) | 0 (300 clean) | clean; false DESYNC eliminated |

## Randomized matrix (300 trials each; steady family = pre-initialized head)
- Baseline steady 6w/24w: 0 forks, **551 / 2,233 false SENTINEL_DESYNCED responses** (the false-halt defect under pure contention; board itself remains consistent).
- v8 steady 6w/24w: 0 forks, **0 false desyncs**; contention surfaced as retryable POSITION_IN_FLIGHT (1,567 / 8,118 responses).
- Baseline fresh 6w/24w insertion: 10/27 forks, 116/135 halts. Reverse: 25/40 forks, ~111/132 halts.
- v8 fresh all: 300/300 clean, zero forks, zero halts, zero timeouts, zero other-failures.

## Scenario suite (F2-F6, CP1-CP7, R1-R12) — baseline vs v8
- **F2 simultaneous init:** baseline — value-only CAS multi-matches BOTH identical head docs (updated=2, both mutated), both writers 409, board left in MULTI halt; v8 — both SENTINEL_MISSING, zero writes. The multi-match mutation class is why idCAS exists; v8 also removes the scenario at the source.
- **F3 CAS-to-create gap (checker arrives mid-commit):** baseline — checker gets false 500 SENTINEL_DESYNCED while the winner's commit is actually intact (probe 200 after); v8 — checker gets 409 POSITION_IN_FLIGHT retryable. Exactly the designed fix behavior.
- **CP1/CP2 (fault at read/CAS):** transient 500, board consistent, later posts fine (both).
- **CP3 (crash after CAS win):** head advanced, record lost → board halts fail-closed SENTINEL_DESYNCED on BOTH sources (the recheck intentionally does not heal a lost create; repair-authority resync is the recovery). No duplicate seqs. Consistent with the crash matrix.
- **CP4 (response discarded, blind retry same message_id):** first post stored, blind retry 409 DUPLICATE_MESSAGE_ID citing existing post_id. Correct idempotency behavior.
- **CP7 (contradictory injected state, "restart"):** 500 SENTINEL_DESYNCED fail-closed (both).
- **CP6:** unauthorized resync → 403 REPAIR_AUTHORITY_REQUIRED (both).
- **R1-R12 rotation battery:** R2/R3 (post vs rotation, in-flight CAS loser) — stale writer 409 POSITION_STALE, retry with rotated-away key 403 BINDING_MISMATCH, no history rewrite. R4/R9a (rotation CAS won, create fault) — fail-closed DESYNC, no dup. R6/R7/R8 concurrent rotate+post / rotate+rotate — no dups, exactly one rebind. R9b (rebind fault, retry heals): rotation record is stored even when the rebind faults, then the retry adds a second authenticated rotation record and rebinds — noted as an observation: between fault and retry the rotation record and the binding transiently disagree; the binding remains admission-authoritative, retry heals, no fork. R10 (rotate blocked at CAS, post commits, retry) — 409 then clean 200. R11 malformed (same-key 409, bad-signature 403 NOT_BOUND / 401 SIG_INVALID, unbound alias 403). R12 (own rotation): old key 403 BINDING_MISMATCH on post, 403 ROTATION_NOT_BOUND on rotate, new key 200. Identical on baseline and v8 — the rotation path is unchanged and sound.
- **R12 "binding anomaly" RESOLVED as harness artifact:** an intermediate harness setup called a state-clearing helper between R10 and R12, wiping the binding; the old-key post then exercised the designed TOFU path (no binding for a genuine signature → create). Isolated repro (dbg_r12b) shows correct behavior; scenarios re-isolated; identical PASS on both sources.
- **F6 provider-atomicity refutation (deterministic):** with updateMany modeled as a true lost-update (no atomicity, no recheck), BOTH baseline and v8 fork (both CASes report updated=1, both commit seq 1, dup [1], 2 posts). **The hardening rests on the provider's updateMany atomicity; if that assumption is false, neither version is safe.**

## Documentation / label findings
- **SOURCE_TAG (v8):** retains the full "THE single canonical board at vesper-f402303b per operator one-board directive 2026-10-06" phrase. PASS.
- **SOURCE_TAG atomicity claim:** "updateMany match-and-modify is storage-atomic; probe-verified" — should be read as CORROBORATED (2026-10-13 probe fixtures), NOT platform-documented; the F6 refutation shows this is a load-bearing assumption, not a hard fact. Recommend keeping the caveat explicit in deployment docs.
- **DUPLICATE_MESSAGE_ID:** 409 body cites existing_post_id — sufficient to locate the conflicting record. PASS.
- **Provenance:** PR branch head 2ee6a30 ("atomic head reservation closes the concurrent-append race") = the baseline source (5b270395). The worktree file (f48e32f6) is the UNCOMMITTED hardening — committing/pushing it is what would update PR #7. Merge authority remains B-side.

## Production-readiness (item: deterministic suite, no hangs)
The full scripted suite (F1 both schedules + F2-F6 + CP1-CP7 + R1-R12) now completes on baseline AND all 8 variants with zero hangs, zero unclassified trials, all raw JSON preserved (fixed_*.json, trials_*.jsonl + .summary.json, f1_*.txt). The known hang classes are root-caused and gated. Declared with the standing limits: storage atomicity is a provider assumption (F6); rotation battery ran on synthetic Ed25519 keys against the gate mock, not live entities; all evidence is Tier 1 single-operator.

## Recommendation
1. The worktree hardening is verified effective and is REQUIRED before PR #7 merges: the PR branch as pushed still forks deterministically under the staggered init race and emits false-halt DESYNC errors under contention. Commit the worktree delta (noInit + idCAS + recount + bounded recheck) to the PR branch.
2. Deployment prerequisites (unchanged): pre-initialize the sentinel (one authorized resync_head or warm-up post) before traffic; verify sentinel count == 1 before opening writes.
3. Carry the provider-atomicity caveat forward explicitly (CORROBORATED, not documented).

## Reproduction
- F1: `deno run -A --quiet run_f1.ts <module> a|b reverse|insertion <out>` (deterministic).
- Randomized: `deno run -A --quiet random.ts <module> <writers> <trials> <seed> <steady|fresh> <insertion|reverse> [label]` (seed recorded per trial).
- Scenarios: `deno run -A --quiet fixed2.ts <module> <out>`.
- Variants: `python3 variants.py` (builds v1-v8 test copies from the baseline source).


---

# ADDENDUM — v2.0.7 hardening (2026-10-21, same local-only scope)

Product source extended from f48e32f6 to **a52c5fce** (worktree, branch feature/atomic-append-hardening on 2ee6a30):
1. **Post-CAS repair fence** (`sentinelStillOurs` + `POSITION_REPAIRED` 409): after a post/rotate CAS win, the sentinel is re-read before the record is created; a repair-authority `resync_head` that reclaimed the reservation mid-flight causes the writer to refuse — nothing committed, retryable.
2. **Paginated reads** (PAGE=50): `listAll`, `allBindings`, `getSentinels` paginate with skip, closing the provider 50-record list cap.

## New gates (extra.ts; module board_v8t_test = a52c5fce + import redirect + test repair fingerprint 366283b1b946001e; board_baset_test = baseline 5b270395 + same two deltas)

- **S1 repair-vs-in-flight-writer (staggered, deterministic):** writer A wins the CAS reservation, is held at its post-CAS op, an authorized resync_head reclaims it.
  - v2.0.7 (fenced): A → **409 POSITION_REPAIRED, zero commits**; A's retry on the reclaimed (now-current) position succeeds; a fresh writer commits; no dup seqs; 3 posts, board consistent.
  - baseline: A → **200, committed into the reclaimed position** (the defect, reproduced); next append → 500 SENTINEL_DESYNCED halt (fail-closed consequence, no silent fork).
- **S1b stale-writer retry:** old signature/position after repair → rejected (409/idempotent 409), no transplant.
- **R13a rotation boundary (writer CAS loses to completed rotation):** parked writer → 409 POSITION_STALE (no commit); old-key retry → 403 BINDING_MISMATCH; new key → 200; no dups. Identical on both sources — rotation path unchanged by v2.0.7.
- **R13b rotation attempted mid-flight append:** rotation → 500 SENTINEL_DESYNCED fail-closed (no rotation record, binding unchanged, verified directly in storage); the admitted writer commits; rotation retry → 200; rebind happens only after chain commit; old key then 403. Identical on both sources.
- **Revocation boundary (documented, now tested):** admission is evaluated at binding lookup; the sentinel CAS then serializes commits — a request cannot commit under a key whose rotation record preceded its CAS (stale CAS → 409). Verified-before-committed-after does not occur because rebind follows the rotation's own chain commit and any post CAS racing a rotation loses. The R12 "old key 200 after rotation" from the earlier run was a harness artifact (state-clearing helper between sections, TOFU path exercised); isolated repro clean (dbg_r12b.ts); R11/R12 re-isolated and passing.
- **P provider pagination (list/filter capped at 50, real-provider model):** 120-post build from 60 aliases + a deep-page identity lookup.
  - v2.0.7 (paginated): **120/120 committed, 0 dups, verify count 121, head matches, late-alias (binding record #60, page 2) posts 200, 60 binding records, 0 duplicate bindings.**
  - baseline (unpaged reads): **board bricks at 51 posts** (post 52 onward → 409 POSITION_STALE forever; sentinel true-count vs truncated analyze mismatch); the sentinel serialization prevents the truncation fork but halts the board; repair would resync into a duplicate-seq fork. Real-provider confirmation of the 50-cap itself: previously corroborated by live probe fixtures (2026-10-13); under this instruction no production probe was run — the paginated mock model matches the observed provider behavior, and the fix is safe against both models (loop terminates if a provider ignores skip or returns fewer records).
- **F6 non-atomic provider (deterministic double-CAS):** v2.0.6-hardened (f48e32f6) forked under this schedule (both commit, dup seq 1). **v2.0.7 no longer forks**: the fence re-read catches the non-atomic lost-update (loser gets 409 POSITION_REPAIRED, only the winner commits). Residual window (fence-read to create) remains non-atomic-class exposure; the atomicity assumption is still load-bearing and still CORROBORATED-not-documented.
- **F1 deterministic (a,b schedules, both orders):** VERDICT: CLEAN on v2.0.7.
- **Randomized (seed 1234, 300 trials each):** fresh insertion 300 clean / fresh reverse 300 clean / steady insertion 300 clean — 0 forks, 0 halts, 0 timeouts, 0 other, sums check (missing 1800/1800 fresh refusals; steady 1725 retryable POSITION_IN_FLIGHT, 0 false desyncs).
- **Full scenario suite (fixed2.ts) on v2.0.7:** F2 SENTINEL_MISSING fail-closed; F3 retryable IN_FLIGHT; CP1-CP7 unchanged incl. CP3/CP7 fail-closed DESYNC; R1-R12 all PASS incl. R10 conflict+retry and R12 rotation revocation; CP4 idempotent DUPLICATE_MESSAGE_ID.

Test-copy sha256 for the randomized runner: 103e8fd2c8d05c6d04328c534a75ff5d2c9460803daf2a806bd469f7e46fa81f (board_v8_test.ts = a52c5fce + import redirect only).

## Isolation honesty
- noInit remains necessary for the tested init-race schedules and sufficient for THEM; it is not claimed to be the only possible solution nor to close races outside the tested schedules.
- idCAS is retained for its separate invariant (lookalike-record claims), and its reverse-order worsening without noInit (80/300 vs 25) is retained as documented evidence, not as a claim it is harmful in combination.
- The recount/recheck family covers resync and in-flight windows (CP3 remains a permanent halt requiring authority repair — by design; the fence does not heal it).
- The raw per-trial JSONL evidence (trials_*.jsonl, ~20MB) is retained locally and hash-pinned in MANIFEST_SHA256.txt; it is excluded from the repo commit for size, with the summaries and the manifest committed.
