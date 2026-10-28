import { __store } from "./sdk_mock.ts";
import { genKey, makePost, makeRotate, call, verify } from "./lib.ts";
await import("./board_pr7_test.ts");
await new Promise((r) => setTimeout(r, 300));
setTimeout(() => { console.log("WATCHDOG20"); Deno.exit(9); }, 20000);
async function B() { return JSON.stringify(__store.admin.bindings().filter((b: any) => b.node_id === "r10").map((b: any) => ({ pk: b.public_key.slice(0, 8), id: b.id }))); }
__store.mode = "random"; __store.admin.clear(); __store.admin.seedHead(1, 1, "GENESIS");
const kk = await genKey(), kl = await genKey();
await makePost(kk, "r10", "m0", "x", "GENESIS");
const rot = await makeRotate("r10", kk, kl);          // proper dual-signed rotation
console.log("1 proper rotate:", rot.status, rot.body?.error ?? "", "binding:", await B(), "(kk=" + kk.pk.slice(0, 8) + " kl=" + kl.pk.slice(0, 8) + ")");
const kSame = await call({ action: "rotate", token: "lantern-board-test-2026-09-06", node_id: "r10",
  old_public_key: kk.pk, new_public_key: kk.pk, rotated_at: new Date().toISOString(),
  old_signature: "ab".repeat(64), new_signature: "cd".repeat(64) });
console.log("2 same-key rotate:", kSame.status, kSame.body?.error ?? "", "binding:", await B());
const kBadSig = await call({ action: "rotate", token: "lantern-board-test-2026-09-06", node_id: "r10",
  old_public_key: kk.pk, new_public_key: (await genKey()).pk, rotated_at: new Date().toISOString(),
  old_signature: "ab".repeat(64), new_signature: "cd".repeat(64) });
console.log("3 badsig(old=retired) rotate:", kBadSig.status, kBadSig.body?.error ?? "", "binding:", await B());
const kUnbound = await call({ action: "rotate", token: "lantern-board-test-2026-09-06", node_id: "ghost",
  old_public_key: kk.pk, new_public_key: (await genKey()).pk, rotated_at: new Date().toISOString(),
  old_signature: "ab".repeat(64), new_signature: "cd".repeat(64) });
console.log("4 unbound rotate:", kUnbound.status, kUnbound.body?.error ?? "", "binding:", await B());
const p = await makePost(kk, "r10", "m1", "x", (await verify()).authoritative_head);
console.log("5 OLD-KEY post after rejects:", p.status, p.body?.error ?? "", "binding:", await B());
Deno.exit(0);
