import { __store } from "./sdk_mock.ts";
import { genKey, makePost, call, verify } from "./lib.ts";
await import("./board_pr7_test.ts");
await new Promise((r) => setTimeout(r, 300));
setTimeout(() => { console.log("WATCHDOG20"); Deno.exit(9); }, 20000);
async function B(node: string) { return __store.admin.bindings().filter((b: any) => b.node_id === node).map((b: any) => ({ pk: b.public_key.slice(0, 8), id: b.id })); }
__store.mode = "random"; __store.admin.clear(); __store.admin.seedHead(1, 1, "GENESIS");
const kk = await genKey(), kl = await genKey();
await makePost(kk, "r10", "m0", "x", "GENESIS");
console.log("after bind post:", JSON.stringify(await B("r10")), "kk=", kk.pk.slice(0, 8), "kl=", kl.pk.slice(0, 8));
const rot = await call({ action: "rotate", token: "lantern-board-test-2026-09-06", node_id: "r10",
  old_public_key: kk.pk, new_public_key: kl.pk, rotated_at: new Date().toISOString(),
  old_signature: "ab".repeat(64), new_signature: "cd".repeat(64) });
console.log("rotate:", rot.status, rot.body?.error, "bindings:", JSON.stringify(await B("r10")));
// R11-style bad-sig rotation with the ROTATED-AWAY old key
const bad = await call({ action: "rotate", token: "lantern-board-test-2026-09-06", node_id: "r10",
  old_public_key: kk.pk, new_public_key: (await genKey()).pk, rotated_at: new Date().toISOString(),
  old_signature: "ab".repeat(64), new_signature: "cd".repeat(64) });
console.log("badsig-with-oldkey:", bad.status, bad.body?.error, "bindings:", JSON.stringify(await B("r10")));
const p = await makePost(kk, "r10", "m1", "x", (await verify()).authoritative_head);
console.log("old-key post:", p.status, p.body?.error ?? "", "bindings:", JSON.stringify(await B("r10")));
Deno.exit(0);
