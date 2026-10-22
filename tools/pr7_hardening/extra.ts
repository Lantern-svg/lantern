// extra.ts — v2.0.7 hardening gates: repair-vs-writer fence (S1), rotation
// revocation boundary (R13), provider pagination (P). Run:
//   deno run -A --quiet extra.ts <module> <out>
// module: board_v8t_test | board_baset_test
import { __store } from "./sdk_mock.ts";
import {
  genKey, makePost, makeRotate, makeResync, call, track, settle, pending, releaseAt,
  driveUntil, verify, dupSeqs, fpOf,
} from "./lib.ts";

const MODULE = Deno.args[0] ?? "board_v8t_test";
const out = Deno.args[1] ?? "extra_default";
const R: any = {};
const phase = (s: string) => console.error(`[phase] ${s}`);
const scripted = (order = "insertion") => { __store.admin.clear(); __store.mode = "scripted"; __store.filterOrder = order; };
const setRandom = () => { __store.mode = "random"; __store.filterOrder = "insertion"; };

await import(`./${MODULE}.ts`);
await new Promise((r) => setTimeout(r, 300));
const t_start = Date.now();
setTimeout(() => {
  console.error(`WATCHDOG 120s: stuck; q=${JSON.stringify(pending())} opLogTail=${__store.opLog.slice(-6).join(",")}`);
  Deno.exit(9);
}, 120000);

// deterministic repair-authority key (PKCS8 seed 0x11*32; fingerprint
// 366283b1b946001e is embedded ONLY in the -t test copies, which otherwise
// differ from the product source solely by the SDK-import redirect)
async function fixedAuthKey() {
  const pkcs8 = new Uint8Array(48);
  const hex = "302e020100300506032b657004220420" + "11".repeat(32);
  for (let i = 0; i < 48; i++) pkcs8[i] = parseInt(hex.slice(i * 2, i * 2 + 2), 16);
  const sk = await crypto.subtle.importKey("pkcs8", pkcs8, { name: "Ed25519" }, false, ["sign"]);
  const pk = "d04ab232742bb4ab3a1368bd4615e4e6d0224ab71a016baf8520a332c9778737";
  return { sk, pk, fp: await fpOf(pk) };
}

// driven one-shot post inside a scripted section (release everything until done)
async function driveDone(p: { done: boolean }, label: string, budget = 8000) {
  await driveUntil(label, () => p.done, budget);
}

// ---- S1: repair-vs-in-flight-writer -----------------------------------------
phase("S1");
{
  scripted("insertion");
  __store.admin.seedHead(1, 1, "GENESIS");
  const keyA = await genKey(), keyB = await genKey();
  const m0 = track(makePost(keyA, "s1", "s1m0", "x", "GENESIS"));
  await driveDone(m0, "S1.m0");
  if (m0.result?.status !== 200) throw new Error(`S1 setup failed: ${JSON.stringify(m0.result)}`);
  const head1 = m0.result.body.hash;

  // writer A wins the CAS reservation, then is held at its post-CAS op
  const aP = track(makePost(keyA, "s1", "s1m1", "x", head1));
  await driveUntil("S1.A-at-CAS", () => pending().includes("LanternBoardHead.updateMany"), 6000);
  const casIdx = __store.gate.queue.findIndex((e) => e.name === "LanternBoardHead.updateMany");
  await releaseAt(casIdx);
  await driveUntil("S1.A-held", () => __store.gate.queue.length > 0, 6000);
  const heldGid = __store.gate.queue[0].gid;
  const heldName = __store.gate.queue[0].name;

  // repair authority reclaims the reservation while A is in flight
  const KA = await fixedAuthKey();
  const rs = track(makeResync(KA));
  await driveUntil("S1.resync", () => rs.done, 8000, async () => {
    const i = __store.gate.queue.findIndex((e) => e.gid !== heldGid);
    if (i === -1) { await settle(); return; }
    await releaseAt(i);
  });

  // release A's held op: fenced sources must refuse; baseline commits
  const hi = __store.gate.queue.findIndex((e) => e.gid === heldGid);
  if (hi !== -1) await releaseAt(hi);
  await driveDone(aP, "S1.A-done");
  R.S1 = { heldOp: heldName, resync: rs.result?.status, resyncErr: rs.result?.body?.error,
    a: aP.result?.status, aErr: aP.result?.body?.error };

  // S1b: stale writer retry with the invalidated position must be refused
  setRandom();
  const retryOld = await makePost(keyA, "s1", "s1m1", "x", head1);
  const bP = await makePost(keyB, "s2", "s2m0", "x", (await verify()).authoritative_head);
  R.S1b = { retryOld: retryOld.status, retryOldErr: retryOld.body?.error,
    freshWriter: bP.status, freshWriterErr: bP.body?.error,
    dup: dupSeqs(), posts: __store.admin.posts().length };
}

// ---- R13a: writer whose CAS loses to a completed rotation -------------------
phase("R13a");
{
  scripted("insertion");
  __store.admin.seedHead(1, 1, "GENESIS");
  const kOld = await genKey(), kNew = await genKey();
  const m0 = track(makePost(kOld, "r13", "m0", "x", "GENESIS"));
  await driveDone(m0, "R13a.m0");
  if (m0.result?.status !== 200) throw new Error(`R13a setup failed: ${JSON.stringify(m0.result)}`);
  const head1 = m0.result.body.hash;

  // A admitted (binding checked pre-rotation), parked AT its CAS entry
  const aP = track(makePost(kOld, "r13", "m1", "x", head1));
  await driveUntil("R13a.A-at-CAS", () => pending().includes("LanternBoardHead.updateMany"), 6000);
  const heldGid = __store.gate.queue[0].gid;

  // the rotation completes fully while A is parked
  const rot = track(makeRotate("r13", kOld, kNew));
  await driveUntil("R13a.rot", () => rot.done, 10000, async () => {
    const i = __store.gate.queue.findIndex((e) => e.gid !== heldGid);
    if (i === -1) { await settle(); return; }
    await releaseAt(i);
  });
  // release A's CAS: stale reservation must be refused
  const hi = __store.gate.queue.findIndex((e) => e.gid === heldGid);
  if (hi !== -1) await releaseAt(hi);
  await driveDone(aP, "R13a.A-done");

  setRandom();
  const oldRetry = await makePost(kOld, "r13", "m1b", "x", (await verify()).authoritative_head);
  const newPost = await makePost(kNew, "r13", "m2", "x", (await verify()).authoritative_head);
  R.R13a = { rot: rot.result?.status, a: aP.result?.status, aErr: aP.result?.body?.error,
    oldRetry: oldRetry.status, oldRetryErr: oldRetry.body?.error,
    newPost: newPost.status, dup: dupSeqs() };
}

// ---- R13b: rotation that loses to a writer; rebind only after commit ---------
phase("R13b");
{
  scripted("insertion");
  __store.admin.seedHead(1, 1, "GENESIS");
  const kOld = await genKey(), kNew = await genKey();
  const m0 = track(makePost(kOld, "r13b", "m0", "x", "GENESIS"));
  await driveDone(m0, "R13b.m0");
  if (m0.result?.status !== 200) throw new Error(`R13b setup failed: ${JSON.stringify(m0.result)}`);
  const head1 = m0.result.body.hash;

  // A wins the CAS, held at its post-CAS op
  const aP = track(makePost(kOld, "r13b", "m1", "x", head1));
  await driveUntil("R13b.A-at-CAS", () => pending().includes("LanternBoardHead.updateMany"), 6000);
  const casIdx = __store.gate.queue.findIndex((e) => e.name === "LanternBoardHead.updateMany");
  await releaseAt(casIdx);
  await driveUntil("R13b.A-held", () => __store.gate.queue.length > 0, 6000);
  const heldGid = __store.gate.queue[0].gid;

  // rotation attempted while A's reservation is in flight: must lose cleanly
  const rot = track(makeRotate("r13b", kOld, kNew));
  await driveUntil("R13b.rot1", () => rot.done, 10000, async () => {
    const i = __store.gate.queue.findIndex((e) => e.gid !== heldGid);
    if (i === -1) { await settle(); return; }
    await releaseAt(i);
  });
  const bindingAfterFailedRot = __store.admin.bindings().filter((b: any) => b.node_id === "r13b").map((b: any) => b.public_key.slice(0, 8));

  // release A: the admitted writer commits
  const hi = __store.gate.queue.findIndex((e) => e.gid === heldGid);
  if (hi !== -1) await releaseAt(hi);
  await driveDone(aP, "R13b.A-done");

  setRandom();
  // retry the rotation now that the append landed
  const rot2 = track(makeRotate("r13b", kOld, kNew));
  await driveDone(rot2, "R13b.rot2");
  const newPost = await makePost(kNew, "r13b", "m2", "x", (await verify()).authoritative_head);
  R.R13b = { rotFirst: rot.result?.status, rotFirstErr: rot.result?.body?.error,
    bindingStillOldAfterFailedRot: JSON.stringify(bindingAfterFailedRot) === JSON.stringify([kOld.pk.slice(0, 8)]),
    aCommit: aP.result?.status, rotRetry: rot2.result?.status,
    newPost: newPost.status, dup: dupSeqs() };
}

// ---- P: provider pagination (>50 and >100 records) ---------------------------
phase("P");
{
  __store.admin.clear();
  __store.admin.seedHead(1, 1, "GENESIS");
  __store.mode = "random";
  __store.paginated = true; // list/filter cap at 50 per call, like the real provider
  const keys: any[] = [];
  let ok = 0; const errs: any = {};
  let prev = "GENESIS", lastHash = "GENESIS", firstErr: any = null;
  for (let i = 0; i < 60; i++) {
    const k = await genKey();
    keys.push(k);
    for (let j = 0; j < 2; j++) {
      try {
        const r = await makePost(k, `pa${i}`, `pm${i}-${j}`, "x", prev);
        if (r.status === 200) { ok++; lastHash = r.body.hash; prev = r.body.hash; }
        else { errs[r.body?.error ?? r.status] = (errs[r.body?.error ?? r.status] ?? 0) + 1;
          if (!firstErr) firstErr = { at: ok + 1, status: r.status, err: r.body?.error }; }
      } catch (e) { errs.EXCEPTION = (errs.EXCEPTION ?? 0) + 1; if (!firstErr) firstErr = { at: ok + 1, ex: String(e) }; }
    }
  }
  // identity lookup deep past the first page: alias pa59's binding is record #60
  const lateOk = await makePost(keys[59], "pa59", "pm-late", "x", prev);
  const lastHash2 = lateOk.status === 200 ? lateOk.body.hash : lastHash;
  const bRecs = __store.admin.bindings();
  const dupBindings = bRecs.length - new Set(bRecs.map((b: any) => b.node_id)).size;
  const v = await verify();
  R.P = { paginated: true, attempted: 120, ok, errs, firstErr,
    posts: __store.admin.posts().length, dup: dupSeqs(),
    verifyCount: v?.count, headIsLast: v?.authoritative_head === lastHash2,
    lateAliasPost: lateOk.status, bindingRecords: bRecs.length, dupBindings };
  __store.paginated = false;
}

R._meta = { module: MODULE, elapsed_ms: Date.now() - t_start };
Deno.writeFileSync(`${out}.json`, new TextEncoder().encode(JSON.stringify(R, null, 1)));
console.log(JSON.stringify(R));
Deno.exit(0);
