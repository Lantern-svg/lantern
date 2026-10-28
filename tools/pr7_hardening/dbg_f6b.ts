import { __store } from "./sdk_mock.ts";
import { genKey, makePost, track, settle, pending, driveUntil, dupSeqs } from "./lib.ts";
await import("./board_pr7_test.ts");
await new Promise((r) => setTimeout(r, 300));
setTimeout(() => { console.log("WATCHDOG20"); Deno.exit(9); }, 20000);
__store.admin.clear(); __store.mode = "scripted"; __store.filterOrder = "reverse";
__store.admin.seedHead(1, 1, "GENESIS");
__store.nonAtomic = true;
const A = await genKey(), B = await genKey();
const aP = track(makePost(A, "na-a", "m-a", "x", "GENESIS"));
const bP = track(makePost(B, "na-b", "m-b", "x", "GENESIS"));
await settle();
await driveUntil("both-at-CAS", () =>
  pending().filter((n) => n === "LanternBoardHead.updateMany").length >= 2 || (aP.done && bP.done), 5000,
  async () => {
    const q = __store.gate.queue;
    const idx = [...q].reverse().findIndex((e) => e.name !== "LanternBoardHead.updateMany");
    await (async (i: number) => { const e2 = q.splice(i, 1)[0]; e2.resolve(); __store.gate.released++; await settle(); })(idx === -1 ? 0 : q.length - 1 - idx);
  });
const casEntries = __store.gate.queue.filter((e) => e.name === "LanternBoardHead.updateMany");
for (const e of casEntries) { __store.gate.queue.splice(__store.gate.queue.indexOf(e), 1); e.resolve(); __store.gate.released++; }
await settle();
console.log("sync release done; q=", JSON.stringify(pending()));
let it = 0;
await driveUntil("F6.done", () => aP.done && bP.done, 8000, async () => {
  it++; console.log("it", it, "q=", JSON.stringify(pending()));
  const q = __store.gate.queue;
  if (q.length === 0) { await new Promise((r) => setTimeout(r, 5)); return; }
  const e2 = q.splice(0, 1)[0]; e2.resolve(); __store.gate.released++; await settle();
});
__store.nonAtomic = false; __store.mode = "random";
console.log("a:", aP.result?.status, aP.result?.body?.error, "| b:", bP.result?.status, bP.result?.body?.error);
console.log("dup:", JSON.stringify(dupSeqs()), "posts:", __store.admin.posts().length);
Deno.exit(0);
