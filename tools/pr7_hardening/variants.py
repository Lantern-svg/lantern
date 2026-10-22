#!/usr/bin/env python3
"""variants.py — build isolated fix-variant board sources from the PR #7 baseline.
Each variant = baseline + exactly one fix subset (no cosmetic changes), so the
concurrency matrix isolates each fix's contribution. Synthetic test copies get
the documented SDK-import redirection only.
Variants:
  v1  idCAS        : ID-bound CAS filters (post/rotate/resync paths)
  v2  recount     : recount after resync sentinel creation
  v3  noInit      : posts never create head records; SENTINEL_MISSING/MULTI
  v4  idCAS+recount
  v5  idCAS+noInit
  v6  recount+noInit
  v7  idCAS+recount+noInit (all three)
  v8  full patch  : the worktree source (all three + in-flight recheck)
"""
import subprocess, hashlib, sys, re, difflib

BASE = "/app/conversations/6abbddf33ea313eca4529cfe/"
REPO = BASE + "lantern_review_pr7"
HARD = BASE + "pr7_hardening/"
IMP_OLD = 'await import("npm:@base44/sdk@0.8.31")'
IMP_NEW = 'await import("./sdk_mock.ts")'

def git_baseline() -> str:
    return subprocess.run(["git", "-C", REPO, "show",
        "pr7:lantern-babel-codex-bridge/relay-transport/lanternBoard_base44.ts"],
        capture_output=True, text=True, check=True).stdout

def apply_idcas(src: str) -> str:
    old_cas = '''    const casSentinel = async (board: string, match: Record<string, unknown>, transition: Record<string, unknown>): Promise<number> => {
      const res = await heads.updateMany(Object.assign({ board }, match), { $set: transition });
      return Number((res as any)?.updated ?? 0); // 1 = claimed, 0 = lost the race
    };'''
    new_cas = '''    // VARIANT idCAS: CAS filter carries the head record's document id.
    const casSentinel = async (board: string, id: string, match: Record<string, unknown>, transition: Record<string, unknown>): Promise<number> => {
      const res = await heads.updateMany(Object.assign({ board, id }, match), { $set: transition });
      return Number((res as any)?.updated ?? 0); // 1 = claimed, 0 = lost the race
    };'''
    assert old_cas in src, "idCAS helper"
    src = src.replace(old_cas, new_cas)
    for call in [
        ('      const claimed = await casSentinel(board,\n        { epoch: sentinel.epoch, next_seq: sentinel.next_seq, head_hash: sentinel.head_hash },',
         '      const claimed = await casSentinel(board, String(sentinel.id),\n        { epoch: sentinel.epoch, next_seq: sentinel.next_seq, head_hash: sentinel.head_hash },'),
        ('      const rClaimed = await casSentinel(board,\n        { epoch: rSent.epoch, next_seq: rSent.next_seq, head_hash: rSent.head_hash },',
         '      const rClaimed = await casSentinel(board, String(rSent.id),\n        { epoch: rSent.epoch, next_seq: rSent.next_seq, head_hash: rSent.head_hash },'),
        ('      const claimed = await casSentinel(board,\n        { epoch: before.epoch, next_seq: before.next_seq, head_hash: before.head_hash }, target);',
         '      const claimed = await casSentinel(board, String(before.id),\n        { epoch: before.epoch, next_seq: before.next_seq, head_hash: before.head_hash }, target);'),
    ]:
        assert call[0] in src, "idCAS call: " + call[0][:60]
        src = src.replace(call[0], call[1])
    return src

def apply_recount(src: str) -> str:
    old_rs = '''      const sents = await getSentinels(board);
      if (sents.length === 0) {
        await heads.create(Object.assign({ board }, target));
        return json({ ok: true, resynced: true, created: true, sentinel: target, source_tag: SOURCE_TAG });
      }'''
    new_rs = '''      const sents = await getSentinels(board);
      if (sents.length === 0) {
        await heads.create(Object.assign({ board }, target));
        // VARIANT recount: re-read after creating; refuse unless exactly one.
        const recount = await getSentinels(board);
        if (recount.length !== 1) {
          return json({ error: "SENTINEL_MULTI", count: recount.length,
            note: "concurrent sentinel creation detected during resync; reduce to zero and resync once more; nothing else was written" }, 500);
        }
        return json({ ok: true, resynced: true, created: true, sentinel: target, source_tag: SOURCE_TAG });
      }'''
    assert old_rs in src, "recount block"
    return src.replace(old_rs, new_rs)

NOINIT_OLD = '''      const sents = await getSentinels(board);
      if (sents.length > 1) {
        return json({ error: "SENTINEL_MULTI", count: sents.length,
          note: "multiple head sentinels for this board exist (init race); operator must remove the stale one before appends can proceed; nothing was written" }, 500);
      }
      let sentinel = sents[0] ?? null;
      if (!sentinel) {
        // One-time initialization: mirror the derived chain state exactly.
        // If two workers initialize concurrently, both sentinels are visible
        // to the next request and SENTINEL_MULTI fails closed above.
        await heads.create({ board, epoch: cur.epoch, next_seq: a.total + 1,
          head_hash: cur.valid ? cur.head : cur.last_valid_hash,
          last_post_id: null, updated_ms: now });
        sentinel = (await getSentinels(board))[0] ?? null;
        if (!sentinel) return json({ error: "SENTINEL_INIT_FAILED" }, 500);
      }'''

NOINIT_NEW = '''      // VARIANT noInit: posts NEVER create head records. Explicit init only.
      const sents = await getSentinels(board);
      if (sents.length === 0) {
        return json({ error: "SENTINEL_MISSING", retryable_wait: true,
          note: "head sentinel not initialized; an operator-designated repair authority must run resync_head once before posting; safe to retry after that" }, 500);
      }
      if (sents.length > 1) {
        return json({ error: "SENTINEL_MULTI", count: sents.length,
          note: "multiple head sentinels exist; operator must reduce to zero then a single authorized resync_head; nothing was written" }, 500);
      }
      const sentinel = sents[0];'''

def apply_noinit(src: str) -> str:
    assert NOINIT_OLD in src, "noinit block"
    return src.replace(NOINIT_OLD, NOINIT_NEW)

def write_test_copy(name: str, src: str) -> str:
    assert IMP_OLD in src
    redirected = src.replace(IMP_OLD, IMP_NEW)
    path = HARD + f"board_{name}_test.ts"
    open(path, "w").write(redirected)
    # verify the redirection is the ONLY delta
    delta = [l for l in difflib.unified_diff(src.splitlines(), redirected.splitlines(), lineterm="")
             if l[:1] in "+-" and l[:3] not in ("+++", "---")]
    assert len(delta) == 2, delta
    return hashlib.sha256(open(path, "rb").read()).hexdigest()

baseline = git_baseline()
base_sha = hashlib.sha256(baseline.encode()).hexdigest()
print(f"baseline source sha256 = {base_sha}")

v1 = write_test_copy("v1", apply_idcas(baseline))
v2 = write_test_copy("v2", apply_recount(baseline))
v3 = write_test_copy("v3", apply_noinit(baseline))
v4 = write_test_copy("v4", apply_recount(apply_idcas(baseline)))
v5 = write_test_copy("v5", apply_noinit(apply_idcas(baseline)))
v6 = write_test_copy("v6", apply_noinit(apply_recount(baseline)))
v7 = write_test_copy("v7", apply_noinit(apply_recount(apply_idcas(baseline))))
# v8 = the real worktree patched source (all three + in-flight recheck)
patched_src = open(REPO + "/lantern-babel-codex-bridge/relay-transport/lanternBoard_base44.ts").read()
v8 = write_test_copy("v8", patched_src)
patched_true_sha = hashlib.sha256(patched_src.encode()).hexdigest()
for n, h in [("v1", v1), ("v2", v2), ("v3", v3), ("v4", v4), ("v5", v5), ("v6", v6), ("v7", v7), ("v8", v8)]:
    print(f"board_{n}_test.ts sha256 = {h}")
print(f"worktree patched source sha256 = {patched_true_sha}")
# also pin the baseline test copy
import os
bc = open(HARD + "board_pr7_test.ts").read()
print("board_pr7_test.ts (baseline copy) sha256 =", hashlib.sha256(bc.encode()).hexdigest())
