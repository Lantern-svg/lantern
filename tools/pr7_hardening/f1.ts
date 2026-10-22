// f1.ts — the two F1 schedules, shared by the trace runner and the matrix runner.
//  (a) staggered auto-init race (sources that auto-create a head record on post)
//  (b) stale writer vs moved head (board pre-initialized; no-auto-init sources)
import { __store } from "./sdk_mock.ts";
import { genKey, makePost, track, settle, pending, releaseAt, advanceOldest, advanceNewest, driveUntil, verify, dupSeqs } from "./lib.ts";

export interface F1Result {
  trace: string[]; verdict: "FORK" | "HALT" | "CLEAN" | "OTHER";
  aStatus: number; bStatus: number; dup: number[]; heads: number; posts: any[];
  casLog: any[]; bError?: string; aError?: string; verify: any;
}

/** (a) staggered auto-init race, exact interleaving:
 *  A reads empty -> B reads empty (both stale) -> A creates+commits seq 1 fully
 *  -> B creates its stale head -> B refetch -> B CASes its own record. */
export async function runStaggeredAutoInit(order: "insertion" | "reverse"): Promise<F1Result> {
  __store.admin.clear(); __store.mode = "scripted"; __store.filterOrder = order;
  const trace: string[] = [];
  const T = (s: string) => { trace.push(s); if (Deno.env.get("F1_DEBUG")) console.error("[F1] " + s); };
  const A = await genKey(), B = await genKey();
  T(`writer A: node=alpha fp=${A.fp} | writer B: node=beta fp=${B.fp} | filterOrder=${order}`);
  const aP = track(makePost(A, "alpha", "m-a", "hello", "GENESIS"));
  await settle();
  // phase 1: A reads the empty state and blocks at its head-record create
  await driveUntil("A-past-reads", () =>
    aP.done || pending().includes("LanternBoardHead.create"), 3000);
  T(`P1 A blocked: pending=[${pending().join(" | ")}] heads=${__store.admin.heads().length} posts=${__store.admin.posts().length}`);
  const bP = track(makePost(B, "beta", "m-b", "hello", "GENESIS"));
  await settle();
  // phase 2: B reads the SAME empty state while A stays blocked
  await driveUntil("B-past-reads", () =>
    bP.done || pending().filter((n) => n === "LanternBoardHead.create").length >= 2, 3000,
    async () => { await releaseAt(__store.gate.queue.length - 1); });
  T(`P2 B read empty too: pending=[${pending().join(" | ")}]`);
  // phase 3: drive A home ONLY. B's create is identified by its gate id
  // (the LAST-queued create); every OTHER queued op belongs to A.
  const bCreateGid = (() => {
    const creates = __store.gate.queue.filter((e) => e.name === "LanternBoardHead.create");
    return creates.length ? creates[creates.length - 1].gid : -1;
  })();
  if (!aP.done) {
    await driveUntil("A-commits", () => aP.done, 4000, async () => {
      const idx = __store.gate.queue.findIndex((e) => e.gid !== bCreateGid);
      await releaseAt(idx === -1 ? __store.gate.queue.length - 1 : idx);
    });
  }
  T(`P3 A done: status=${aP.result?.status} ${aP.result?.body?.error ?? "ok"} | posts=${JSON.stringify(__store.admin.posts().map((p) => ({ seq: p.seq, node: p.node_id, prev: String(p.prev_hash).slice(0, 12) })))} | heads=${JSON.stringify(__store.admin.heads().map((h) => ({ id: h.id, next_seq: h.next_seq, head: String(h.head_hash).slice(0, 12) })))}`);
  // phase 4: release B's held create and drive B home
  await driveUntil("B-commits", () => bP.done, 6000);
  T(`P4 B done: status=${bP.result?.status} ${bP.result?.body?.error ?? "ok"}`);
  for (const h of __store.admin.heads()) T(`sentinel id=${h.id} next_seq=${h.next_seq} head_hash=${String(h.head_hash).slice(0, 16)}`);
  T(`final sentinel count=${__store.admin.heads().length}`);
  for (const p of __store.admin.posts()) T(`post node=${p.node_id} seq=${p.seq} prev=${p.prev_hash} hash=${String(p.hash).slice(0, 16)}`);
  for (const c of __store.casLog) T(`CAS q=${JSON.stringify(c.query)} -> updated=${c.updated} targets=[${(c.targetIds ?? []).join(",")}]`);
  __store.mode = "random"; // scenario done; reads no longer gated
  const v = await verify();
  const dup = dupSeqs();
  const verdict = dup.length > 0 ? "FORK"
    : (__store.admin.heads().length > 1 || v.epochs?.some((e: any) => !e.valid)) ? "HALT" : "CLEAN";
  T(`dup seqs=[${dup.join(",")}] verify_total=${v.total} epochs=${JSON.stringify(v.epochs?.map((e: any) => ({ e: e.epoch, valid: e.valid })))}`);
  T(`VERDICT: ${verdict}`);
  return { trace, verdict, aStatus: aP.result?.status, aError: aP.result?.body?.error,
    bStatus: bP.result?.status, bError: bP.result?.body?.error, dup,
    heads: __store.admin.heads().length, posts: __store.admin.posts(), casLog: [...__store.casLog], verify: v };
}

/** (b) board pre-initialized with ONE head record (represents the single
 *  authorized resync_head). A stale writer reads the pre-CAS state, the winner
 *  commits seq 1, then the stale writer's CAS is released against the moved
 *  head. Requires a source with no auto-init (a post that auto-created a head
 *  would also be exercised by (a)). */
export async function runStaleVsMoved(order: "insertion" | "reverse"): Promise<F1Result> {
  __store.admin.clear(); __store.mode = "scripted"; __store.filterOrder = order;
  __store.admin.seedHead(1, 1, "GENESIS");
  const trace: string[] = [];
  const T = (s: string) => { trace.push(s); if (Deno.env.get("F1_DEBUG")) console.error("[F1] " + s); };
  const A = await genKey(), B = await genKey();
  T(`writer A: node=alpha fp=${A.fp} | writer B: node=beta fp=${B.fp} | filterOrder=${order}`);
  T(`pre-state: heads=${JSON.stringify(__store.admin.heads().map((h) => ({ id: h.id, next_seq: h.next_seq, head: h.head_hash })))}`);
  const aP = track(makePost(A, "alpha", "m-a", "hello", "GENESIS"));
  await settle();
  await driveUntil("A-past-reads", () => aP.done || pending().includes("LanternBoardHead.updateMany"), 3000);
  T(`P1 A at CAS: pending=[${pending().join(" | ")}]`);
  const bP = track(makePost(B, "beta", "m-b", "hello", "GENESIS"));
  await settle();
  await driveUntil("B-past-reads", () =>
    bP.done || pending().filter((n) => n === "LanternBoardHead.updateMany").length >= 2, 3000,
    async () => { await releaseAt(__store.gate.queue.length - 1); });
  T(`P2 B at CAS with same pre-state: pending=[${pending().join(" | ")}]`);
  // drive A home only (hold B's CAS)
  const bCasGid = (() => {
    const cass = __store.gate.queue.filter((e) => e.name === "LanternBoardHead.updateMany");
    return cass.length ? cass[cass.length - 1].gid : -1;
  })();
  await driveUntil("A-commits", () => aP.done, 4000, async () => {
    const idx = __store.gate.queue.findIndex((e) => e.gid !== bCasGid);
    await releaseAt(idx === -1 ? __store.gate.queue.length - 1 : idx);
  });
  T(`P3 A done: status=${aP.result?.status} ${aP.result?.body?.error ?? "ok"} | heads=${JSON.stringify(__store.admin.heads().map((h) => ({ id: h.id, next_seq: h.next_seq, head: String(h.head_hash).slice(0, 12) })))}`);
  await driveUntil("B-resolves", () => bP.done, 6000);
  T(`P4 B done: status=${bP.result?.status} ${bP.result?.body?.error ?? "ok"}`);
  T(`final heads=${JSON.stringify(__store.admin.heads().map((h) => ({ id: h.id, next_seq: h.next_seq })))} created_by_post_path=${__store.admin.heads().length - 1}`);
  for (const p of __store.admin.posts()) T(`post node=${p.node_id} seq=${p.seq} prev=${String(p.prev_hash).slice(0, 12)}`);
  for (const c of __store.casLog) T(`CAS q=${JSON.stringify(c.query)} -> updated=${c.updated} targets=[${(c.targetIds ?? []).join(",")}]`);
  __store.mode = "random"; // scenario done; reads no longer gated
  const v = await verify();
  const dup = dupSeqs();
  const verdict = dup.length > 0 ? "FORK"
    : (__store.admin.heads().length > 1 || v.epochs?.some((e: any) => !e.valid)) ? "HALT" : "CLEAN";
  T(`dup seqs=[${dup.join(",")}] verify_total=${v.total} epochs=${JSON.stringify(v.epochs?.map((e: any) => ({ e: e.epoch, valid: e.valid })))}`);
  T(`VERDICT: ${verdict}`);
  return { trace, verdict, aStatus: aP.result?.status, aError: aP.result?.body?.error,
    bStatus: bP.result?.status, bError: bP.result?.body?.error, dup,
    heads: __store.admin.heads().length, posts: __store.admin.posts(), casLog: [...__store.casLog], verify: v };
}
