import { __store } from "./sdk_mock.ts";
import { genKey, makePost, track, settle, pending, releaseAt, driveUntil, verify, dupSeqs } from "./lib.ts";
await import("./board_pr7_test.ts");
await new Promise((r) => setTimeout(r, 300));
setTimeout(() => { console.log("WATCHDOG 15s pending=", JSON.stringify(__store.gate.queue.map(e=>e.name)), "cas=", JSON.stringify(__store.casLog)); Deno.exit(9); }, 15000);
__store.admin.clear(); __store.mode = "scripted"; __store.filterOrder = "reverse";
__store.admin.seedHead(1, 1, "GENESIS");
__store.nonAtomic = true;
const A = await genKey(), B = await genKey();
const aP = track(makePost(A, "na-a", "m-a", "x", "GENESIS"));
const bP = track(makePost(B, "na-b", "m-b", "x", "GENESIS"));
await settle();
console.log("q0:", JSON.stringify(pending()));
await driveUntil("both-at-CAS", () =>
  pending().filter((n) => n === "LanternBoardHead.updateMany").length >= 2 || aP.done || bP.done, 5000,
  async () => { console.log("step q:", JSON.stringify(pending())); await releaseAt(__store.gate.queue.length - 1); });
console.log("past both-at-CAS; aP.done=", aP.done, "bP.done=", bP.done);
await driveUntil("done", () => aP.done && bP.done, 8000);
__store.nonAtomic = false; __store.mode = "random";
console.log("a:", aP.result?.status, aP.result?.body?.error, "b:", bP.result?.status, bP.result?.body?.error);
console.log("dup:", JSON.stringify(dupSeqs()), "posts:", __store.admin.posts().length, "casLog:", JSON.stringify(__store.casLog.map(c=>({u:c.updated,na:c.nonAtomic}))));
Deno.exit(0);
