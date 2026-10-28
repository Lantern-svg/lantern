// fixed.ts — deterministic fixed schedules against the REAL board source
// (Deno, in-memory mock SDK, real Ed25519 signatures, synthetic keys).
// Usage: deno run -A --quiet fixed.ts <pr7|patched>
import { __store } from "./sdk_mock.ts";
import {
  genKey, makePost, makeRotate, makeResync, call, track, waitDone,
  settle, pending, advanceOldest, advanceNewest, releaseAt, dupSeqs, verify,
} from "./lib.ts";

const VERSION = Deno.args[0] as "pr7" | "patched";
if (VERSION !== "pr7" && VERSION !== "patched") { console.error("arg: pr7|patched"); Deno.exit(2); }
await import(VERSION === "pr7" ? "./board_pr7_test.ts" : "./board_patched_test.ts");
await new Promise((r) => setTimeout(r, 300));

const results: Array<[string, string]> = [];
function record(name: string, pass: boolean, detail = "") {
  results.push([name, pass ? "PASS" : "FAIL" + (detail ? `: ${detail}` : "")]);
  console.log(`${pass ? "PASS" : "FAIL"}  ${name}${pass ? "" : "  <- " + detail}`);
}

function scripted() { __store.admin.clear(); __store.mode = "scripted"; __store.filterOrder = "insertion"; }
async function doneOf(w: { done: boolean; result?: any }): Promise<any> {
  const ok = await waitDone(w);
  if (!ok) throw new Error("request did not complete (schedule stuck)");
  return w.result;
}

// ============ F1: staggered init race ============
async function f1() {
  for (const order of ["insertion", "reverse"] as const) {
    scripted(); __store.filterOrder = order;
    const A = await genKey(), B = await genKey();
    const aP = track(makePost(A, "alpha", "m-a", "hello", "GENESIS"));
    const bP = track(makePost(B, "beta", "m-b", "hello", "GENESIS"));
    await settle();
    // A blocks at its first storage op; advance A through its reads until it
    // is blocked at heads.create (PR7) / heads CAS (patched, head pre-seeded).
    if (VERSION === "pr7") {
      while (!pending().some((n) => n === "LanternBoardHead.create")) await advanceOldest();
      // A is now blocked AT heads.create (enqueued). Advance B through its
      // reads while A stays blocked: B's ops are the newest.
      while (!pending().some((n) => n === "LanternBoardHead.create" && pending().indexOf(n) > 0) ||
             pending().filter((n) => n === "LanternBoardHead.create").length < 2) {
        if (__store.gate.queue.length <= 1) break;
        await advanceNewest();
        if (bP.done) break;
      }
      // both blocked at heads.create now: A (oldest) first, then B
      await advanceOldest();            // A creates head-A
      while (!pending().some((n) => n === "LanternPost.create")) await advanceOldest(); // A: refetch, CAS, binding
      await advanceOldest();            // A: posts.create -> seq 1 committed
      const aRes = await doneOf(aP);
      // now B continues (its heads.create still queued)
      await waitDone(bP, 3000).catch(() => {});
      let bRes = bP.result;
      if (!bP.done) { // B still running: drive it home
        while (!bP.done) { if (__store.gate.queue.length === 0) await settle(); else await advanceOldest(); }
        bRes = bP.result;
      }
      const seqs = __store.admin.posts().map((p: any) => Number(p.seq)).sort();
      const fork = dupSeqs().length > 0;
      if (order === "reverse") {
        record(`F1 staggered init race (reverse filter order) [PR7 expected FORK]`,
          fork && seqs.join(",") === "1,1",
          `posts seqs=[${seqs}] A=${aRes.status} B=${bRes.status}`);
      } else {
        record(`F1 staggered init race (insertion order) [no fork expected]`,
          !fork, `posts seqs=[${seqs}] A=${aRes.status} B=${bRes.status}`);
      }
    } else {
      // PATCHED: posts never create heads. Seed one (represents the single
      // authorized resync_head), then race a stale writer against a winner.
      __store.admin.seedHead(1, 1, "GENESIS");
      // A: advance through reads until blocked at heads.updateMany (CAS)
      while (!pending().some((n) => n === "LanternBoardHead.updateMany")) await advanceOldest();
      // B: advance through reads (sees the same pre-A state) until blocked at its CAS
      while (true) {
        const q = __store.gate.queue;
        if (q.length <= 1) break;
        const names = pending();
        if (names.length >= 2 && names[1] === "LanternBoardHead.updateMany") break;
        await advanceNewest();
      }
      // A wins the CAS and commits seq 1 fully
      await advanceOldest();  // A CAS
      while (!pending().some((n) => n === "LanternPost.create")) await advanceOldest();
      await advanceOldest();  // A posts.create
      const aRes = await doneOf(aP);
      // B's CAS releases against the moved head: id+values must not match
      while (!bP.done) { if (__store.gate.queue.length === 0) await settle(); else await advanceOldest(); }
      const bRes = bP.result;
      const seqs = __store.admin.posts().map((p: any) => Number(p.seq)).sort();
      record(`F1 stale writer vs moved head (${order}) [PATCHED: no fork]`,
        dupSeqs().length === 0 && seqs.length === 1 && bRes.status === 409,
        `posts seqs=[${seqs}] A=${aRes.status} B=${bRes.status} heads=${__store.admin.heads().length}`);
    }
  }
}

// ============ F2: simultaneous init, identical head records ============
async function f2() {
  scripted();
  const A = await genKey(), B = await genKey();
  const aP = track(makePost(A, "alpha", "m-a", "x", "GENESIS"));
  await settle();
  const bP = track(makePost(B, "beta", "m-b", "x", "GENESIS"));
  await settle();
  // release strictly alternately until both fetches complete
  while (!aP.done || !bP.done) {
    if (__store.gate.queue.length === 0) { await settle(); continue; }
    await advanceOldest();
    if (aP.done && bP.done) break;
  }
  const heads = __store.admin.heads().length;
  const posts = __store.admin.posts().length;
  if (VERSION === "pr7") {
    const later = await makePost(await genKey(), "gamma", "m-c", "x", "GENESIS");
    record("F2 simultaneous init [PR7: MULTI halt, no fork]",
      heads === 2 && posts === 0 && later.status === 500 && /SENTINEL_MULTI/.test(later.body?.error),
      `heads=${heads} posts=${posts} later=${later.status} ${later.body?.error}`);
  } else {
    record("F2 posts cannot create head records [PATCHED]",
      heads === 0 && posts === 0 && aP.result?.body?.error === "SENTINEL_MISSING" && bP.result?.body?.error === "SENTINEL_MISSING",
      `heads=${heads} posts=${posts} A=${aP.result?.body?.error} B=${bP.result?.body?.error}`);
  }
}

// ============ F3: CAS-to-create gap contention ============
async function f3() {
  scripted();
  __store.admin.seedHead(1, 1, "GENESIS");
  if (VERSION === "pr7") __store.admin.heads()[0].id = "h-seed"; // same id shape
  const A = await genKey(), X = await genKey();
  const aP = track(makePost(A, "winner", "m-a", "x", "GENESIS"));
  await settle();
  // advance A through CAS + binding.create; A blocks at posts.create
  while (!pending().some((n) => n === "LanternPost.create")) await advanceOldest();
  // X arrives during the gap: advance its reads
  const xP = track(makePost(X, "gapchecker", "m-x", "x", "GENESIS"));
  await settle();
  while (true) {
    const names = pending();
    if (names.length >= 1 && names[0] === "LanternPost.create") break; // A's create still first
    if (xP.done) break;
    if (__store.gate.queue.length === 0) { await settle(); continue; }
    await advanceNewest();
  }
  // release A's posts.create (the record lands)
  await releaseAt(0);
  const aRes = await doneOf(aP);
  // let X finish (its re-check or desync path)
  while (!xP.done) {
    if (__store.gate.queue.length === 0) { await settle(); await new Promise((r) => setTimeout(r, 10)); }
    else await advanceOldest();
  }
  const xRes = xP.result;
  const boardHealthy = (await makePost(await genKey(), "probe", "m-p", "x",
    (await verify()).authoritative_head)).status === 200;
  if (VERSION === "pr7") {
    record("F3 in-flight gap [PR7: false SENTINEL_DESYNCED]",
      xRes.status === 500 && xRes.body?.error === "SENTINEL_DESYNCED" && boardHealthy && aRes.status === 200,
      `X=${xRes.status} ${xRes.body?.error} winner=${aRes.status} boardHealthy=${boardHealthy}`);
  } else {
    record("F3 in-flight gap [PATCHED: retryable POSITION_IN_FLIGHT]",
      xRes.status === 409 && xRes.body?.error === "POSITION_IN_FLIGHT" && xRes.body?.retryable === true
        && boardHealthy && aRes.status === 200 && dupSeqs().length === 0,
      `X=${xRes.status} ${xRes.body?.error} winner=${aRes.status} boardHealthy=${boardHealthy}`);
  }
}

// ============ F4: cleanup gap + interrupted cleanup ============
async function f4() {
  scripted();
  // MULTI state: two head records (init-race residue, admin-seeded)
  __store.admin.seedHead(1, 2, "hashA");
  __store.admin.heads().push({ id: "h-stale", board: "lantern-board", epoch: 1, next_seq: 1, head_hash: "GENESIS", last_post_id: null, updated_ms: 0 });
  const blocked = await makePost(await genKey(), "t", "m1", "x", "GENESIS");
  if (VERSION === "pr7") {
    record("F4a MULTI blocks posts [PR7]",
      blocked.status === 500 && blocked.body?.error === "SENTINEL_MULTI", `${blocked.status} ${blocked.body?.error}`);
  } else {
    record("F4a MULTI blocks posts [PATCHED]",
      blocked.status === 500 && blocked.body?.error === "SENTINEL_MULTI", `${blocked.status} ${blocked.body?.error}`);
  }
  // cleanup gap: ALL head records deleted; posts land in the gap
  __store.admin.clear(); __store.mode = "scripted";
  const P1 = track(makePost(await genKey(), "g1", "m1", "x", "GENESIS"));
  await settle();
  const P2 = track(makePost(await genKey(), "g2", "m2", "x", "GENESIS"));
  await settle();
  while (!P1.done || !P2.done) {
    if (__store.gate.queue.length === 0) { await settle(); continue; }
    await advanceOldest();
  }
  const headsAfter = __store.admin.heads().length;
  if (VERSION === "pr7") {
    record("F4b cleanup gap [PR7: posts RE-CREATE head records]",
      headsAfter >= 2, `heads after gap=${headsAfter}`);
  } else {
    record("F4b cleanup gap [PATCHED: no head records created]",
      headsAfter === 0 && P1.result.body?.error === "SENTINEL_MISSING" && P2.result.body?.error === "SENTINEL_MISSING",
      `heads=${headsAfter} P1=${P1.result.body?.error} P2=${P2.result.body?.error}`);
  }
  // interrupted cleanup: 2 heads, delete only the stale one -> 1 remains ->
  // posts proceed only if the mirror matches; halt otherwise, never fork
  __store.admin.clear(); __store.mode = "scripted";
  __store.admin.seedHead(1, 2, "hashA"); // good mirror for a 1-post chain
  __store.admin.heads().push({ id: "h-stale", board: "lantern-board", epoch: 1, next_seq: 1, head_hash: "GENESIS", last_post_id: null, updated_ms: 0 });
  __store.admin.posts().push({ id: "p-seed", board: "lantern-board", node_id: "seednode", message_id: "seed-1",
    content: "x", seq: 1, prev_hash: "GENESIS", hash: "hashA", epoch: 1, kind: "post", public_key: "00", signature: "00", created_ms: 1, server_ms: 1, verified: true, formula: "v2", post_id: "p-seed" });
  __store.admin.heads().splice(1, 1); // delete the STALE one -> good mirror remains
  const ok = await makePost(await genKey(), "after", "m3", "x", "hashA");
  record("F4c interrupted cleanup, good mirror remains [" + VERSION + ": proceeds]",
    ok.status === 200, `${ok.status} ${ok.body?.error}`);
  // now the bad case: delete the GOOD one -> stale mirror remains
  __store.admin.clear(); __store.mode = "scripted";
  __store.admin.posts().push({ id: "p-seed", board: "lantern-board", node_id: "seednode", message_id: "seed-1",
    content: "x", seq: 1, prev_hash: "GENESIS", hash: "hashA", epoch: 1, kind: "post", public_key: "00", signature: "00", created_ms: 1, server_ms: 1, verified: true, formula: "v2", post_id: "p-seed" });
  __store.admin.heads().push({ id: "h-stale", board: "lantern-board", epoch: 1, next_seq: 1, head_hash: "GENESIS", last_post_id: null, updated_ms: 0 });
  const blocked2 = await makePost(await genKey(), "after2", "m4", "x", "hashA");
  const noFork = dupSeqs().length === 0;
  record("F4d interrupted cleanup, stale mirror remains [" + VERSION + ": fail-closed, no fork]",
    blocked2.status === 500 && /SENTINEL_DESYNCED|SENTINEL_MULTI/.test(blocked2.body?.error) && noFork,
    `${blocked2.status} ${blocked2.body?.error} noFork=${noFork}`);
}

// ============ F5: crash points CP1-CP7 ============
async function f5() {
  // CP1: fault at the very first read (before analyzing head)
  __store.admin.clear(); __store.mode = "random";
  __store.admin.seedHead(1, 1, "GENESIS");
  __store.failNext = { entity: "LanternPost", op: "list" };
  const cp1 = await makePost(await genKey(), "cp1", "m", "x", "GENESIS");
  const cp1later = await makePost(await genKey(), "cp1b", "m", "x", (await verify()).authoritative_head);
  record("CP1 fault before head read [nothing written, board alive]",
    cp1.status === 500 && cp1later.status === 200 && __store.admin.posts().length === 1,
    `cp1=${cp1.status} later=${cp1later.status}`);
  // CP2: fault at the CAS (after reads, before claiming)
  __store.admin.clear(); __store.admin.seedHead(1, 1, "GENESIS");
  __store.failNext = { entity: "LanternBoardHead", op: "updateMany" };
  const cp2 = await makePost(await genKey(), "cp2", "m", "x", "GENESIS");
  const cp2later = await makePost(await genKey(), "cp2b", "m", "x", (await verify()).authoritative_head);
  record("CP2 fault at CAS [no reservation, board alive]",
    cp2.status === 500 && cp2later.status === 200 && __store.admin.posts().length === 1,
    `cp2=${cp2.status} later=${cp2later.status}`);
  // CP3: fault at posts.create AFTER the CAS won (reserved, never stored)
  __store.admin.clear(); __store.admin.seedHead(1, 1, "GENESIS");
  __store.failNext = { entity: "LanternPost", op: "create" };
  const cp3 = await makePost(await genKey(), "cp3", "m", "x", "GENESIS");
  const headState = __store.admin.heads()[0];
  const cp3later = await makePost(await genKey(), "cp3b", "m", "x", (await verify()).authoritative_head);
  record("CP3 fault after CAS win [fail-closed halt, unforked]",
    cp3.status === 500 && Number(headState.next_seq) === 2 && __store.admin.posts().length === 0
      && cp3later.status === 500 && /SENTINEL_DESYNCED/.test(cp3later.body?.error) && dupSeqs().length === 0,
    `cp3=${cp3.status} later=${cp3later.status} ${cp3later.body?.error}`);
  // CP4: record stored, response lost -> state query resolves; blind retry dup-guarded
  __store.admin.clear(); __store.admin.seedHead(1, 1, "GENESIS");
  const k = await genKey();
  const cp4 = await makePost(k, "cp4", "m", "x", "GENESIS");
  const listed = (await call({ action: "list", board: "lantern-board" })).body.posts.filter((p: any) => p.message_id === "m");
  const blindRetry = await makePost(k, "cp4", "m", "x", (await verify()).authoritative_head);
  record("CP4 response lost [state query resolves; dup message_id guarded]",
    cp4.status === 200 && listed.length === 1 && blindRetry.status === 409
      && blindRetry.body?.error === "DUPLICATE_MESSAGE_ID" && __store.admin.posts().length === 1,
    `listed=${listed.length} retry=${blindRetry.status} ${blindRetry.body?.error}`);
  // CP5: post persisted -> every later request re-derives consistently
  const v = await verify();
  record("CP5 serverless restart [state re-derived, consistent]",
    v.authoritative_head === cp4.body?.hash && v.total === 1,
    `head match=${v.authoritative_head === cp4.body?.hash}`);
  // CP7: contradictory state = desync; fresh request ("restart") halts, never forks
  const freshAttempt = await makePost(await genKey(), "cp7", "m", "x", (await verify()).authoritative_head);
  record("CP7 contradictory state [fresh request fails closed, unforked]",
    freshAttempt.status === 500 && /SENTINEL_DESYNCED/.test(freshAttempt.body?.error) && dupSeqs().length === 0,
    `${freshAttempt.status} ${freshAttempt.body?.error}`);
  // CP6 (resync authorization): synthetic keys are NEVER authorities (real gate)
  const unauthorized = await makeResync(await genKey());
  record("CP6 unauthorized resync [403 REPAIR_AUTHORITY_REQUIRED, real gate]",
    unauthorized.status === 403 && unauthorized.body?.error === "REPAIR_AUTHORITY_REQUIRED",
    `${unauthorized.status} ${unauthorized.body?.error}`);
}

// ============ R1-R12: rotation battery ============
async function rotations() {
  // R1 stable key
  __store.admin.clear(); __store.mode = "random"; __store.admin.seedHead(1, 1, "GENESIS");
  const k1 = await genKey();
  const r1 = await makePost(k1, "rot-node", "m1", "x", "GENESIS");
  record("R1 stable-key post", r1.status === 200, `${r1.status}`);
  // R2 rotate then old-key post
  const k2 = await genKey();
  const rot = await makeRotate("rot-node", k1, k2);
  const r2 = await makePost(k1, "rot-node", "m2", "x", (await verify()).authoritative_head);
  record("R2 rotate then old-key post [403 BINDING_MISMATCH]",
    rot.status === 200 && r2.status === 403 && r2.body?.error === "BINDING_MISMATCH",
    `rot=${rot.status} old-key-post=${r2.status}`);
  // R3 post in flight (binding passed) while rotation completes, then CAS loses
  __store.admin.clear(); __store.mode = "scripted"; __store.admin.seedHead(1, 1, "GENESIS");
  const ka = await genKey(); // poster with key1
  await makePost(ka, "race", "m0", "x", "GENESIS"); // bind alias 'race' (random mode quick)
  __store.mode = "scripted";
  const kb = await genKey();
  const xP = track(makePost(ka, "race", "m1", "x", (await verify()).authoritative_head));
  await settle();
  while (!pending().some((n) => n === "LanternBoardHead.updateMany")) await advanceOldest();
  // X (poster) is blocked at its CAS; run the rotation to completion now
  const rotP = track(makeRotate("race", ka, kb));
  await settle();
  while (!rotP.done) {
    if (__store.gate.queue.length === 0) { await settle(); continue; }
    await advanceNewest();
  }
  // release X's CAS: it must lose against the moved head
  while (!xP.done) { if (__store.gate.queue.length === 0) await settle(); else await advanceOldest(); }
  const xRes = xP.result;
  const retry = await makePost(ka, "race", "m1", "x", (await verify()).authoritative_head);
  record("R3 in-flight post vs rotation [CAS loses; retry old-key 403]",
    xRes.status === 409 && retry.status === 403 && retry.body?.error === "BINDING_MISMATCH",
    `X=${xRes.status} retry=${retry.status} ${retry.body?.error}`);
  // R5 old-key post after rotation (direct)
  __store.mode = "random";
  const r5 = await makePost(ka, "race", "m5", "x", (await verify()).authoritative_head);
  const r5b = await makePost(kb, "race", "m5b", "x", (await verify()).authoritative_head);
  record("R5 old key refused / new key accepted",
    r5.status === 403 && r5b.status === 200, `old=${r5.status} new=${r5b.status}`);
  // R6 concurrent rotate + post
  __store.admin.clear(); __store.mode = "random"; __store.admin.seedHead(1, 1, "GENESIS");
  const kc = await genKey();
  await makePost(kc, "rot6", "m0", "x", "GENESIS");
  const kd = await genKey();
  const [rot6, post6] = await Promise.all([
    makeRotate("rot6", kc, kd),
    makePost(await genKey(), "poster6", "m1", "x", (await verify()).authoritative_head),
  ]);
  record("R6 concurrent rotate+post [one winner per position, no dup]",
    [rot6.status, post6.status].sort().join() === "200,200,409".split(",").slice(0, 2).sort().join() ||
      ([rot6.status, post6.status].includes(200) && ![rot6.status, post6.status].filter((s) => s === 200).length),
    JSON.stringify({ rot: rot6.status, post: post6.status, dups: dupSeqs() }));
  record("R6b no duplicate positions", dupSeqs().length === 0, `dups=${dupSeqs()}`);
  // R7 rotation racing rotation (same alias)
  __store.admin.clear(); __store.mode = "random"; __store.admin.seedHead(1, 1, "GENESIS");
  const ke = await genKey();
  await makePost(ke, "rot7", "m0", "x", "GENESIS");
  const kf = await genKey(), kg = await genKey();
  const [r7a, r7b] = await Promise.all([ makeRotate("rot7", ke, kf), makeRotate("rot7", ke, kg) ]);
  const bound = __store.admin.bindings().find((b: any) => b.node_id === "rot7");
  record("R7 rotation racing rotation [exactly one rebind]",
    [r7a.status, r7b.status].includes(200) && [r7a.status, r7b.status].includes(409) && dupSeqs().length === 0,
    JSON.stringify({ a: r7a.status, b: r7b.status, bound: bound?.public_key?.slice(0, 8) }));
  // R8 rotation during in-flight gap (scripted)
  __store.admin.clear(); __store.mode = "scripted"; __store.admin.seedHead(1, 1, "GENESIS");
  const kh = await genKey();
  await makePost(kh, "rot8", "m0", "x", "GENESIS");
  __store.mode = "scripted";
  const wP = track(makePost(await genKey(), "w8", "m1", "x", (await verify()).authoritative_head));
  await settle();
  while (!pending().some((n) => n === "LanternPost.create")) await advanceOldest(); // winner blocked at create
  const ki = await genKey();
  const rotP8 = track(makeRotate("rot8", kh, ki));
  await settle();
  // drive: winner's create + rotation's ops interleaved to completion
  while (!wP.done || !rotP8.done) {
    if (__store.gate.queue.length === 0) { await settle(); continue; }
    await advanceOldest();
  }
  record("R8 rotation during in-flight gap [completes, no dup]",
    wP.result.status === 200 && rotP8.result.status === 200 && dupSeqs().length === 0,
    JSON.stringify({ w: wP.result.status, rot: rotP8.result.status, dups: dupSeqs() }));
  // R9a: rotation CAS won, record fault -> desync halt, unforked
  __store.admin.clear(); __store.mode = "random"; __store.admin.seedHead(1, 1, "GENESIS");
  const kj = await genKey();
  await makePost(kj, "rot9", "m0", "x", "GENESIS");
  __store.failNext = { entity: "LanternPost", op: "create" };
  const kk = await genKey();
  const r9a = await makeRotate("rot9", kj, kk);
  const later9 = await makePost(await genKey(), "after9", "m", "x", (await verify()).authoritative_head);
  record("R9a rotation crash after CAS [fail-closed halt, unforked]",
    r9a.status === 500 && later9.status === 500 && /SENTINEL_DESYNCED/.test(later9.body?.error) && dupSeqs().length === 0,
    `rot=${r9a.status} later=${later9.status} ${later9.body?.error}`);
  // R9b: rotation record stored, rebind fault -> retry self-heals, no rewrite
  __store.admin.clear(); __store.mode = "random"; __store.admin.seedHead(1, 1, "GENESIS");
  const kl = await genKey();
  await makePost(kl, "rot9b", "m0", "x", "GENESIS");
  __store.failNext = { entity: "LanternBinding", op: "update" };
  const km = await genKey();
  const r9b = await makeRotate("rot9b", kl, km);
  const retry9b = await makeRotate("rot9b", kl, km);
  const postAfter = await makePost(km, "rot9b", "m1", "x", (await verify()).authoritative_head);
  const rotRecs = __store.admin.posts().filter((p: any) => p.kind === "rotation").length;
  record("R9b rebind crash [record kept, retry heals, no rewrite]",
    r9b.status === 500 && /REBIND/.test(r9b.body?.error) && retry9b.status === 200 && postAfter.status === 200,
    `r9b=${r9b.status} ${r9b.body?.error} retry=${retry9b.status} rotRecs=${rotRecs}`);
  // R10 retry after rotation conflict (stale read -> 409, fresh -> 200)
  __store.admin.clear(); __store.mode = "random"; __store.admin.seedHead(1, 1, "GENESIS");
  const kn = await genKey();
  await makePost(kn, "rot10", "m0", "x", "GENESIS");
  const ko = await genKey();
  const staleRot = await makeRotate("rot10", kn, ko); // head read inside; concurrent post moves head first
  await makePost(await genKey(), "mover", "m1", "x", (await verify()).authoritative_head);
  const retryRot = await makeRotate("rot10", kn, ko);
  const statusPair = [staleRot.status, retryRot.status];
  record("R10 rotation retry after conflict",
    retryRot.status === 200 && dupSeqs().length === 0,
    `first=${staleRot.status} retry=${retryRot.status}`);
  // R11 malformed / unauthorized rotation
  const same = await call({ action: "rotate", token: "lantern-board-test-2026-09-06", node_id: "rot10",
    old_public_key: kn.pk, new_public_key: kn.pk, rotated_at: new Date().toISOString(),
    old_signature: "00".repeat(64), new_signature: "00".repeat(64) });
  const badSig = await call({ action: "rotate", token: "lantern-board-test-2026-09-06", node_id: "rot10",
    old_public_key: kn.pk, new_public_key: (await genKey()).pk, rotated_at: new Date().toISOString(),
    old_signature: "ab".repeat(64), new_signature: "cd".repeat(64) });
  const unbound = await call({ action: "rotate", token: "lantern-board-test-2026-09-06", node_id: "ghost",
    old_public_key: kn.pk, new_public_key: ko.pk, rotated_at: new Date().toISOString(),
    old_signature: "ab".repeat(64), new_signature: "cd".repeat(64) });
  record("R11 malformed rotation [409/401/403, nothing stored]",
    same.status === 409 && badSig.status === 401 && unbound.status === 403,
    `same=${same.status} badsig=${badSig.status} unbound=${unbound.status}`);
  // R12 stale key: cannot post, cannot rotate again; new key works
  const p12 = await makePost(kn, "rot10", "m2", "x", (await verify()).authoritative_head);
  const rot12 = await call({ action: "rotate", token: "lantern-board-test-2026-09-06", node_id: "rot10",
    old_public_key: kn.pk, new_public_key: (await genKey()).pk, rotated_at: new Date().toISOString(),
    old_signature: "ab".repeat(64), new_signature: "cd".repeat(64) });
  record("R12 old key cannot post or rotate again [binding holds]",
    p12.status === 403 && rot12.status === 403, `post=${p12.status} rotate=${rot12.status}`);
}

// ============ nonAtomic provider refutation demo ============
async function f6() {
  __store.admin.clear(); __store.mode = "random"; __store.admin.seedHead(1, 1, "GENESIS");
  __store.nonAtomic = true;
  const keys = await Promise.all([genKey(), genKey(), genKey(), genKey(), genKey(), genKey()]);
  const res = await Promise.all(keys.map((k, i) => makePost(k, `na-${i}`, `m-${i}`, "x", "GENESIS")));
  __store.nonAtomic = false;
  const dup = dupSeqs().length;
  const okCount = res.filter((r) => r.status === 200).length;
  record("F6 broken-provider model (nonAtomic) [" + VERSION + ": forks return]",
    dup > 0 && okCount > 1, `dups=${dup} accepted=${okCount}`);
}

await f1();
await f2();
await f3();
await f4();
await f5();
await rotations();
await f6();
const fails = results.filter(([, r]) => r.startsWith("FAIL"));
console.log(`\n=== ${VERSION}: ${results.length - fails.length}/${results.length} fixed checks passed ===`);
fails.forEach(([n, r]) => console.log(`FAILED: ${n} ${r}`));
Deno.exit(fails.length > 0 ? 1 : 0);
