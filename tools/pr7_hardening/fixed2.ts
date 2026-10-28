// fixed2.ts — multi-scenario runner (F2-F6, CP1-CP7, R1-R12) against one loaded
// source. Emits JSON lines; analysis/comparison happens outside.
// Usage: deno run -A --quiet fixed2.ts <boardModule> <outName>
import { __store } from "./sdk_mock.ts";
import {
  genKey, makePost, makeRotate, makeResync, call, track, settle, pending,
  releaseAt, advanceOldest, driveUntil, verify, dupSeqs,
} from "./lib.ts";

const mod = Deno.args[0];
const out = Deno.args[1] ?? mod;
await import(`./${mod}.ts`);
await new Promise((r) => setTimeout(r, 300));

const R: any = { source: mod };
const PHASES: string[] = [];
function phase(p: string) { PHASES.push(p); console.error("[phase] " + p); }
setTimeout(() => { console.error("WATCHDOG 120s: hung after phases: " + PHASES.join(" -> ")); Deno.exit(9); }, 45000);
function scripted(order: "insertion" | "reverse" = "insertion") {
  __store.admin.clear(); __store.mode = "scripted"; __store.filterOrder = order;
}
function random() { __store.admin.clear(); __store.mode = "random"; __store.nonAtomic = false; __store.failNext = null; }
async function drive(tracked: { done: boolean }, label: string, budget = 6000, hold?: number) {
  await driveUntil(label, () => tracked.done, budget, async () => {
    if (hold === undefined) { if (__store.gate.queue.length === 0) { await new Promise((r) => setTimeout(r, 5)); return; } await releaseAt(0); }
    else {
      const idx = __store.gate.queue.findIndex((e) => e.gid !== hold);
      if (idx === -1) { await new Promise((r) => setTimeout(r, 5)); return; }
      await releaseAt(idx);
    }
  });
}

phase("F2-start");
// ---- F2: simultaneous init (two first posts, both read empty) ----
{
  scripted("reverse");
  const A = await genKey(), B = await genKey();
  const aP = track(makePost(A, "alpha", "m-a", "x", "GENESIS"));
  await settle();
  const bP = track(makePost(B, "beta", "m-b", "x", "GENESIS"));
  await settle();
  await drive(aP, "F2.A"); await drive(bP, "F2.B");
  __store.mode = "random"; // scripted race done
  const probe = await makePost(await genKey(), "probe", "m-p", "x", (await verify()).authoritative_head);
  R.F2 = { a: aP.result?.status, aErr: aP.result?.body?.error, b: bP.result?.status, bErr: bP.result?.body?.error,
    heads: __store.admin.heads().length, headsState: __store.admin.heads().map((h) => ({ next_seq: h.next_seq, head: String(h.head_hash).slice(0, 8) })),
    posts: __store.admin.posts().length, dup: dupSeqs(), probe: probe.status, probeErr: probe.body?.error,
    cas: __store.casLog.map((c) => ({ q_next: c.query.next_seq, updated: c.updated, targets: c.targetIds })) };
}

phase("F3-start");
// ---- F3: CAS-to-create gap contention (winner mid-commit, checker arrives) ----
{
  scripted("reverse"); __store.admin.seedHead(1, 1, "GENESIS");
  const A = await genKey(), X = await genKey();
  const aP = track(makePost(A, "winner", "m-a", "x", "GENESIS"));
  await settle();
  await driveUntil("F3.A-to-create", () => pending().includes("LanternPost.create"), 4000);
  const xP = track(makePost(X, "checker", "m-x", "x", "GENESIS"));
  await settle();
  // drive X's reads while A's create is held (A's create = the OLDEST pending entry)
  const aCreateGid = __store.gate.queue[0]?.gid;
  // drive X's reads to completion (or until X resolves) releasing only the newest
  await driveUntil("F3.X-reads", () => xP.done || !pending().some((n) => n === "LanternPost.list" || n === "LanternBinding.list" || n === "LanternBoardHead.filter"), 3000,
    async () => { await releaseAt(__store.gate.queue.length - 1); }).catch(() => {});
  // release A's create, then drive both to completion
  await driveUntil("F3.finish", () => aP.done && xP.done, 8000, async () => {
    if (pending()[0] === "LanternPost.create") await releaseAt(0);
    else await releaseAt(0);
  });
  __store.mode = "random";
  const probeOk = (await makePost(await genKey(), "probe", "m-p", "x", (await verify()).authoritative_head)).status;
  R.F3 = { winner: aP.result?.status, checker: xP.result?.status, checkerErr: xP.result?.body?.error,
    retryable: xP.result?.body?.retryable, probeAfter: probeOk, dup: dupSeqs(), posts: __store.admin.posts().length };
}

phase("F4-start");
// ---- F4: cleanup gap + interrupted cleanup + recovery sequence ----
{
  // Build a real chain first, then introduce a second (stale) head record.
  __store.mode = "random"; __store.admin.clear(); __store.admin.seedHead(1, 1, "GENESIS");
  const basePost = await makePost(await genKey(), "base", "m0", "x", "GENESIS");
  const realHead = { ...__store.admin.heads()[0] };
  const staleHead = { id: "h-stale", board: "lantern-board", epoch: 1, next_seq: 1, head_hash: "GENESIS", last_post_id: null, updated_ms: 0 };
  __store.admin.heads().push({ ...staleHead });
  // (a) two heads present -> post refused, no head records created
  const f4a = await makePost(await genKey(), "t", "m1", "x", realHead.head_hash);
  // (b) recovery "paused before deletion" (still two heads) -> refused
  const f4b = await makePost(await genKey(), "t2", "m2", "x", realHead.head_hash);
  // (c) paused mid-deletion, stale removed, good remains -> proceeds
  const beforeC = __store.admin.heads().length;
  __store.admin.heads().splice(__store.admin.heads().findIndex((h: any) => h.id === "h-stale"), 1);
  const f4c = await makePost(await genKey(), "t3", "m3", "x", realHead.head_hash);
  // (d) paused mid-deletion the other way: good removed, stale remains -> fail closed
  __store.mode = "random"; __store.admin.clear();
  __store.admin.seedHead(1, 1, "GENESIS");
  const basePost2 = await makePost(await genKey(), "base2", "m0", "x", "GENESIS");
  __store.admin.heads().splice(0, 1); // remove the good head
  __store.admin.heads().push({ ...staleHead }); // only the stale one remains
  const f4d = await makePost(await genKey(), "t4", "m4", "x", basePost2.body?.hash);
  // (e) full cleanup (zero heads): two concurrent posts during the gap
  __store.mode = "scripted"; __store.admin.clear();
  const g1 = track(makePost(await genKey(), "g1", "m1", "x", "GENESIS"));
  await settle();
  const g2 = track(makePost(await genKey(), "g2", "m2", "x", "GENESIS"));
  await settle();
  await drive(g1, "F4.g1"); await drive(g2, "F4.g2");
  __store.mode = "random";
  const headsAfterGap = __store.admin.heads().length;
  // (f) recovery complete: one authoritative head -> posting resumes
  __store.admin.clear(); __store.admin.seedHead(1, 1, "GENESIS");
  const f4f = await makePost(await genKey(), "after-recovery", "m5", "x", "GENESIS");
  R.F4 = {
    setup: { basePost: basePost.status, realChainHead: String(realHead.head_hash).slice(0, 12) },
    a_twoHeads: { status: f4a.status, err: f4a.body?.error, headsAfter: beforeC },
    b_pauseBeforeDeletion: { status: f4b.status, err: f4b.body?.error },
    c_pause_staleRemoved: { status: f4c.status, err: f4c.body?.error },
    d_pause_goodRemoved: { status: f4d.status, err: f4d.body?.error, dup: dupSeqs() },
    e_gap_posts: { g1: g1.result?.status, g1Err: g1.result?.body?.error, g2: g2.result?.status, g2Err: g2.result?.body?.error, headsAfterGap },
    f_afterRecovery: { status: f4f.status, err: f4f.body?.error, dup: dupSeqs() },
  };
}

// ---- F5: crash points CP1-CP7 (fault injection at storage ops) ----
{
  // CP1 fault at first read
  random(); __store.admin.seedHead(1, 1, "GENESIS");
  __store.failNext = { entity: "LanternPost", op: "list" };
  const cp1 = await makePost(await genKey(), "cp1", "m", "x", "GENESIS");
  const cp1later = await makePost(await genKey(), "cp1b", "m", "x", (await verify()).authoritative_head);
  R.CP1 = { fault: cp1.status, faultErr: cp1.body?.error, later: cp1later.status, posts: __store.admin.posts().length };
  // CP2 fault at CAS
  random(); __store.admin.clear(); __store.admin.seedHead(1, 1, "GENESIS");
  __store.failNext = { entity: "LanternBoardHead", op: "updateMany" };
  const cp2 = await makePost(await genKey(), "cp2", "m", "x", "GENESIS");
  const cp2later = await makePost(await genKey(), "cp2b", "m", "x", (await verify()).authoritative_head);
  R.CP2 = { fault: cp2.status, later: cp2later.status, posts: __store.admin.posts().length, headUnchanged: __store.admin.heads()[0].next_seq === 1 };
  // CP3 fault after CAS win (reserved, never stored)
  random(); __store.admin.clear(); __store.admin.seedHead(1, 1, "GENESIS");
  __store.failNext = { entity: "LanternPost", op: "create" };
  const cp3 = await makePost(await genKey(), "cp3", "m", "x", "GENESIS");
  const cp3head = { ...__store.admin.heads()[0] };
  const cp3later = await makePost(await genKey(), "cp3b", "m", "x", (await verify()).authoritative_head);
  R.CP3 = { fault: cp3.status, headAdvanced: cp3head.next_seq === 2, posts: __store.admin.posts().length,
    later: cp3later.status, laterErr: cp3later.body?.error, dup: dupSeqs() };
  // CP4 record stored, response discarded; blind retry same message_id
  random(); __store.admin.clear(); __store.admin.seedHead(1, 1, "GENESIS");
  const k = await genKey();
  const cp4 = await makePost(k, "cp4", "m", "x", "GENESIS");
  const listed = (await call({ action: "list", board: "lantern-board" })).body.posts.filter((p: any) => p.message_id === "m");
  const blind = await makePost(k, "cp4", "m", "x", (await verify()).authoritative_head);
  R.CP4 = { first: cp4.status, listedFound: listed.length, blindRetry: blind.status, blindErr: blind.body?.error, posts: __store.admin.posts().length };
  // CP5 serverless restart: later requests re-derive consistently
  const v = await verify();
  R.CP5 = { headMatches: v.authoritative_head === cp4.body?.hash, total: v.total };
  // CP7 contradictory state injected (head advanced beyond the chain = the
  // post-CAS-crash signature), then a fresh request ("restart") must fail closed
  __store.admin.clear(); __store.admin.seedHead(1, 1, "GENESIS");
  await makePost(await genKey(), "cp7pre", "m0", "x", "GENESIS");
  const h7 = __store.admin.heads()[0];
  h7.next_seq = Number(h7.next_seq) + 1; // reserved position with no stored record
  const cp7 = await makePost(await genKey(), "cp7", "m", "x", (await verify()).authoritative_head);
  R.CP7 = { status: cp7.status, err: cp7.body?.error, dup: dupSeqs(), heads: __store.admin.heads().length };
  // CP6 unauthorized resync (synthetic keys are never authorities)
  const unauth = await makeResync(await genKey());
  R.CP6_unauthorized = { status: unauth.status, err: unauth.body?.error };
}

phase("R-start");
// ---- R1-R12 rotation battery ----
{
  phase("R1");
  // R1 stable key post
  random(); __store.admin.seedHead(1, 1, "GENESIS");
  const k1 = await genKey();
  const r1 = await makePost(k1, "rot", "m1", "x", "GENESIS");
  R.R1 = { status: r1.status };
  phase("R2");
  // R2 rotate then old-key post
  const k2 = await genKey();
  const rot2 = await makeRotate("rot", k1, k2);
  const r2 = await makePost(k1, "rot", "m2", "x", (await verify()).authoritative_head);
  R.R2 = { rotate: rot2.status, oldKeyPost: r2.status, oldKeyErr: r2.body?.error, dup: dupSeqs() };
  phase("R3");
  // R3 in-flight post vs rotation (scripted): poster bound, blocked at CAS, rotation completes, CAS loses, retry 403
  scripted("reverse"); __store.admin.clear(); __store.admin.seedHead(1, 1, "GENESIS");
  const ka = await genKey();
  __store.mode = "random";
  await makePost(ka, "r3", "m0", "x", "GENESIS"); // bind alias
  const r3head = (await verify()).authoritative_head;
  __store.mode = "scripted";
  const kb = await genKey();
  const xP = track(makePost(ka, "r3", "m1", "x", r3head));
  await settle();
  await driveUntil("R3.X-at-CAS", () => pending().includes("LanternBoardHead.updateMany"), 4000);
  const rotP = track(makeRotate("r3", ka, kb));
  await settle();
  await driveUntil("R3.rot-done", () => rotP.done, 5000, async () => { await releaseAt(__store.gate.queue.length - 1); });
  await drive(xP, "R3.X");
  __store.mode = "random";
  const r3retry = await makePost(ka, "r3", "m1", "x", (await verify()).authoritative_head);
  R.R3 = { casLoser: xP.result?.status, casErr: xP.result?.body?.error, retryOldKey: r3retry.status, retryErr: r3retry.body?.error, dup: dupSeqs() };
  phase("R4");
  // R4 rotation CAS won, create fault -> fail closed, unforked
  random(); __store.admin.clear(); __store.admin.seedHead(1, 1, "GENESIS");
  const kc = await genKey();
  await makePost(kc, "r4", "m0", "x", "GENESIS");
  __store.failNext = { entity: "LanternPost", op: "create" };
  const kd = await genKey();
  const r4 = await makeRotate("r4", kc, kd);
  const r4later = await makePost(await genKey(), "r4b", "m", "x", (await verify()).authoritative_head);
  R.R4 = { rot: r4.status, rotErr: r4.body?.error, later: r4later.status, laterErr: r4later.body?.error, dup: dupSeqs(), posts: __store.admin.posts().length };
  phase("R5");
  // R5 old-key post direct
  random();
  const r5 = await makePost(kc, "r4", "m5", "x", (await verify()).authoritative_head);
  R.R5 = { status: r5.status, err: r5.body?.error };
  phase("R6");
  // R6 concurrent rotate + post
  random(); __store.admin.clear(); __store.admin.seedHead(1, 1, "GENESIS");
  const ke = await genKey();
  await makePost(ke, "r6", "m0", "x", "GENESIS");
  const kf = await genKey();
  const [rot6, post6] = await Promise.all([
    makeRotate("r6", ke, kf),
    makePost(await genKey(), "poster6", "m1", "x", (await verify()).authoritative_head),
  ]);
  R.R6 = { rot: rot6.status, post: post6.status, dup: dupSeqs(), posts: __store.admin.posts().length };
  phase("R7");
  // R7 rotation racing rotation (same alias)
  random(); __store.admin.clear(); __store.admin.seedHead(1, 1, "GENESIS");
  const kg = await genKey();
  await makePost(kg, "r7", "m0", "x", "GENESIS");
  const [r7a, r7b] = await Promise.all([makeRotate("r7", kg, await genKey()), makeRotate("r7", kg, await genKey())]);
  const bound = __store.admin.bindings().find((b: any) => b.node_id === "r7");
  R.R7 = { a: r7a.status, b: r7b.status, dup: dupSeqs(), oneRebind: !!bound };
  phase("R8");
  // R8 rotation during in-flight gap
  scripted("reverse"); __store.admin.clear(); __store.admin.seedHead(1, 1, "GENESIS");
  const kh = await genKey();
  __store.mode = "random";
  await makePost(kh, "r8", "m0", "x", "GENESIS");
  const r8head = (await verify()).authoritative_head;
  __store.mode = "scripted";
  const wP = track(makePost(await genKey(), "w8", "m1", "x", r8head));
  await settle();
  await driveUntil("R8.w-at-create", () => pending().includes("LanternPost.create"), 4000);
  const rotP8 = track(makeRotate("r8", kh, await genKey()));
  await settle();
  await driveUntil("R8.both", () => wP.done && rotP8.done, 8000);
  __store.mode = "random";
  R.R8 = { winner: wP.result?.status, rot: rotP8.result?.status, dup: dupSeqs() };
  // R9a rotation crash after CAS
  random(); __store.admin.clear(); __store.admin.seedHead(1, 1, "GENESIS");
  const ki = await genKey();
  await makePost(ki, "r9", "m0", "x", "GENESIS");
  __store.failNext = { entity: "LanternPost", op: "create" };
  const r9a = await makeRotate("r9", ki, await genKey());
  const r9aLater = await makePost(await genKey(), "r9b", "m", "x", (await verify()).authoritative_head);
  R.R9a = { rot: r9a.status, later: r9aLater.status, laterErr: r9aLater.body?.error, dup: dupSeqs() };
  // R9b rebind fault -> record kept, retry heals
  random(); __store.admin.clear(); __store.admin.seedHead(1, 1, "GENESIS");
  const kj = await genKey();
  await makePost(kj, "r9c", "m0", "x", "GENESIS");
  __store.failNext = { entity: "LanternBinding", op: "update" };
  const r9b = await makeRotate("r9c", kj, await genKey());
  const r9bRetry = await makeRotate("r9c", kj, await genKey());
  R.R9b = { first: r9b.status, firstErr: r9b.body?.error, retry: r9bRetry.status, dup: dupSeqs(),
    rotRecords: __store.admin.posts().filter((p: any) => p.kind === "rotation").length };
  phase("R10");
  // R10 rotation blocked at its CAS while a post commits -> 409, then retry clean
  scripted("reverse"); __store.admin.clear(); __store.admin.seedHead(1, 1, "GENESIS");
  const kk = await genKey();
  __store.mode = "random";
  await makePost(kk, "r10", "m0", "x", "GENESIS");
  const kl = await genKey();
  const r10head = (await verify()).authoritative_head;
  __store.mode = "scripted";
  const rot10 = track(makeRotate("r10", kk, kl));
  await settle();
  await driveUntil("R10.rot-at-CAS", () => rot10.done || pending().includes("LanternBoardHead.updateMany"), 4000);
  const rotCasGid = (() => {
    const cass = __store.gate.queue.filter((e) => e.name === "LanternBoardHead.updateMany");
    return cass.length ? cass[0].gid : -1;
  })();
  const movP = track(makePost(await genKey(), "mover10", "m1", "x", r10head));
  await settle();
  await driveUntil("R10.mover-done", () => movP.done, 4000, async () => {
    const idx = __store.gate.queue.findIndex((e) => e.gid !== rotCasGid);
    if (idx === -1) { await new Promise((r) => setTimeout(r, 5)); return; }
    await releaseAt(idx);
  });
  await drive(rot10, "R10.rot", 6000);
  __store.mode = "random";
  const r10retry = await makeRotate("r10", kk, kl);
  const r10binding = __store.admin.bindings().filter((b: any) => b.node_id === "r10").map((b: any) => b.public_key.slice(0, 8));
  R.R10 = { bindingAfter: r10binding, conflictFirst: rot10.result?.status, conflictErr: rot10.result?.body?.error,
    mover: movP.result?.status, moverErr: movP.result?.body?.error, retry: r10retry.status, retryErr: r10retry.body?.error, dup: dupSeqs() };
  phase("R11");
  // R11 malformed rotations (own alias, no state clear)
  const k11 = await genKey();
  await makePost(k11, "r11a", "m0", "x", (await verify()).authoritative_head);
  const kSame = await call({ action: "rotate", token: "lantern-board-test-2026-09-06", node_id: "r11a",
    old_public_key: k11.pk, new_public_key: k11.pk, rotated_at: new Date().toISOString(),
    old_signature: "ab".repeat(64), new_signature: "cd".repeat(64) });
  const kBadSig = await call({ action: "rotate", token: "lantern-board-test-2026-09-06", node_id: "r11a",
    old_public_key: k11.pk, new_public_key: (await genKey()).pk, rotated_at: new Date().toISOString(),
    old_signature: "ab".repeat(64), new_signature: "cd".repeat(64) });
  const kUnbound = await call({ action: "rotate", token: "lantern-board-test-2026-09-06", node_id: "ghost",
    old_public_key: k11.pk, new_public_key: (await genKey()).pk, rotated_at: new Date().toISOString(),
    old_signature: "ab".repeat(64), new_signature: "cd".repeat(64) });
  R.R11 = { sameKey: kSame.status, sameKeyErr: kSame.body?.error, badSig: kBadSig.status, badSigErr: kBadSig.body?.error, unbound: kUnbound.status, unboundErr: kUnbound.body?.error };
  phase("R12");
  // R12 old key cannot post or rotate again; new key works (own alias, own rotation, no clears)
  const k12 = await genKey(), k12new = await genKey();
  await makePost(k12, "r12a", "m0", "x", (await verify()).authoritative_head);
  const r12rot = await makeRotate("r12a", k12, k12new);
  const r12post = await makePost(k12, "r12a", "m1", "x", (await verify()).authoritative_head);
  const r12oldRot = await call({ action: "rotate", token: "lantern-board-test-2026-09-06", node_id: "r12a",
    old_public_key: k12.pk, new_public_key: (await genKey()).pk, rotated_at: new Date().toISOString(),
    old_signature: "ab".repeat(64), new_signature: "cd".repeat(64) });
  const r12new = await makePost(k12new, "r12a", "m2", "x", (await verify()).authoritative_head);
  R.R12 = { rotation: r12rot.status, oldPost: r12post.status, oldPostErr: r12post.body?.error,
    oldRot: r12oldRot.status, oldRotErr: r12oldRot.body?.error,
    newKeyPost: r12new.status, newKeyErr: r12new.body?.error };
}

phase("F6-start");
// ---- F6: broken-provider (non-atomic updateMany) refutation, deterministic ----
{
  scripted("reverse"); __store.admin.clear(); __store.admin.seedHead(1, 1, "GENESIS");
  __store.nonAtomic = true;
  const A = await genKey(), B = await genKey();
  const aP = track(makePost(A, "na-a", "m-a", "x", "GENESIS"));
  const bP = track(makePost(B, "na-b", "m-b", "x", "GENESIS"));
  await settle();
  // hold both CAS ops until BOTH are queued, then release both into the
  // non-atomic window (each writer's updateMany overlaps the other's yield)
  await driveUntil("F6.both-at-CAS", () =>
    pending().filter((n) => n === "LanternBoardHead.updateMany").length >= 2 || (aP.done && bP.done), 6000,
    async () => {
      const q = __store.gate.queue;
      const idx = [...q].reverse().findIndex((e) => e.name !== "LanternBoardHead.updateMany");
      await releaseAt(idx === -1 ? 0 : q.length - 1 - idx);
    });
  // resolve BOTH CAS entries before any settle, so both updateMany calls are
  // inside their non-atomic yield windows simultaneously
  console.error("[F6dbg] both-at-CAS reached; q=" + JSON.stringify(pending()));
  const casEntries = __store.gate.queue.filter((e) => e.name === "LanternBoardHead.updateMany");
  for (const e of casEntries) { __store.gate.queue.splice(__store.gate.queue.indexOf(e), 1); e.resolve(); __store.gate.released++; }
  await settle();
  console.error("[F6dbg] after sync release; q=" + JSON.stringify(pending()));
  let f6it = 0; const f6t0 = Date.now();
  try {
    await driveUntil("F6.done", () => aP.done && bP.done, 8000, async () => {
      f6it++; console.error("[F6dbg] it" + f6it + " q=" + JSON.stringify(pending()));
      const q = __store.gate.queue;
      if (q.length === 0) { await new Promise((r) => setTimeout(r, 5)); return; }
      const e2 = q.splice(0, 1)[0]; e2.resolve(); __store.gate.released++; await settle();
    });
  } catch (e) {
    console.error("[F6dbg] driveUntil threw: " + String(e));
    R.F6_driverError = String(e);
  }
  console.error("[F6dbg] driveUntil returned");
  R.F6_iters = f6it; R.F6_ms = Date.now() - f6t0;
  __store.nonAtomic = false;
  __store.mode = "random";
  R.F6 = { a: aP.result?.status, aErr: aP.result?.body?.error, b: bP.result?.status, bErr: bP.result?.body?.error,
    dup: dupSeqs(), posts: __store.admin.posts().length, heads: __store.admin.heads().length,
    cas: __store.casLog.map((c) => ({ updated: c.updated, nonAtomic: c.nonAtomic })) };
}

Deno.writeFileSync(`${out}.json`, new TextEncoder().encode(JSON.stringify(R, null, 1)));
console.log(JSON.stringify(R));
Deno.exit(0);
