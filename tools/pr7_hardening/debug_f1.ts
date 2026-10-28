// debug_f1.ts — FULL-TRACE staggered init-race schedule (§3 evidence).
// Usage: deno run -A --quiet debug_f1.ts <pr7|patched|variant-file> <filterOrder>
import { __store } from "./sdk_mock.ts";
import { genKey, makePost, track, settle, pending, releaseAt, driveUntil, verify, dupSeqs } from "./lib.ts";

const boardFile = Deno.args[0] ?? "pr7";
const order = (Deno.args[1] ?? "reverse") as "insertion" | "reverse";
await import(`./${boardFile}.ts`);
await new Promise((r) => setTimeout(r, 300));
__store.admin.clear(); __store.mode = "scripted"; __store.filterOrder = order;

const A = await genKey(), B = await genKey();
const trace: string[] = [];
const T = (s: string) => { trace.push(s); console.log(s); };

T(`SCHEDULE F1 staggered-init | source=${boardFile} | filterOrder=${order}`);
T(`writer A: node=alpha fp=${A.fp.slice(0, 8)} | writer B: node=beta fp=${B.fp.slice(0, 8)}`);

const aP = track(makePost(A, "alpha", "m-a", "hello", "GENESIS"));
await settle();
// phase 1: A reads empty state; stop when A is blocked at its head-record create
// (baseline) or has simply failed/rejected (patched: no create op exists)
await driveUntil("A-past-reads", () =>
  pending().includes("LanternBoardHead.create") || aP.done || pending().includes("LanternBoardHead.updateMany"), 3000);
T(`phase1: A blocked; pending=[${pending().join(" | ")}] heads=${__store.admin.heads().length} posts=${__store.admin.posts().length}`);

let bDone = false;
const bP = track(makePost(B, "beta", "m-b", "hello", "GENESIS"));
await settle();
if (!aP.done) {
  // phase 2: B reads the SAME empty state while A stays blocked (advance only B)
  await driveUntil("B-past-reads", () =>
    bP.done || (pending().filter((n) => n === "LanternBoardHead.create").length >= 2) ||
    (pending().includes("LanternBoardHead.updateMany") && pending().indexOf("LanternBoardHead.updateMany") > 0), 3000,
    async () => { const q = __store.gate.queue; if (q.length <= 1) { await releaseAt(0); } else { await releaseAt(q.length - 1); } });
  T(`phase2: B read empty too; pending=[${pending().join(" | ")}]`);
  // phase 3: A completes first (release A's ops, FIFO)
  await driveUntil("A-commits", () => aP.done, 3000);
  T(`phase3: A done status=${aP.result?.status} ${aP.result?.body?.error ?? "ok"}; posts=${JSON.stringify(__store.admin.posts().map((p) => ({ seq: p.seq, node: p.node_id, prev: p.prev_hash.slice(0, 12) })))}`);
} else {
  T(`phase1: A finished early: status=${aP.result?.status} ${aP.result?.body?.error ?? "ok"}`);
}
// phase 4: B finishes
await driveUntil("B-commits", () => bP.done, 5000);
T(`phase4: B done status=${bP.result?.status} ${bP.result?.body?.error ?? "ok"}`);

// evidence dump
T("--- sentinels ---");
for (const h of __store.admin.heads()) T(`sentinel id=${h.id} epoch=${h.epoch} next_seq=${h.next_seq} head_hash=${String(h.head_hash).slice(0, 16)} created_initial(${h.next_seq === 1 ? "next_seq=1/GENESIS" : "advanced"})`);
T(`final sentinel count=${__store.admin.heads().length}`);
T("--- posts ---");
for (const p of __store.admin.posts()) T(`post node=${p.node_id} seq=${p.seq} prev=${p.prev_hash} kind=${p.kind}`);
T("--- CAS log ---");
for (const c of __store.casLog) T(`CAS q=${JSON.stringify(c.query)} -> updated=${c.updated} targets=[${(c.targetIds ?? []).join(",")}] set_next_seq=${c.set.next_seq}`);
const v = await verify();
const dup = dupSeqs();
const verdict = dup.length > 0 ? "FORK" : (v.epochs?.some((e: any) => !e.valid) ? "HALT/DIVERGENT" : "CLEAN");
T(`--- verdict ---`);
T(`dup seqs=[${dup.join(",")}] verify_total=${v.total} epoch1_valid=${v.epochs?.[0]?.valid} epoch1_head=${v.epochs?.[0]?.head?.slice(0, 16)}`);
T(`VERDICT: ${verdict}`);
Deno.writeFileSync(`f1_trace_${boardFile}_${order}.txt`, new TextEncoder().encode(trace.join("\n")));
Deno.exit(0);
