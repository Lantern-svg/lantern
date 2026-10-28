import { __store } from "./sdk_mock.ts";
await import("./board_patched_test.ts");
await new Promise((r) => setTimeout(r, 300));
const ku = await crypto.subtle.generateKey({ name: "Ed25519" } as any, false, ["sign", "verify"]) as CryptoKeyPair;
const raw = new Uint8Array(await crypto.subtle.exportKey("raw", ku.publicKey));
const pk = Array.from(raw).map((b) => b.toString(16).padStart(2, "0")).join("");
console.log("pubkey hex len:", pk.length);
async function call(body: any): Promise<any> {
  const r = await fetch("http://localhost:8000/", { method: "POST",
    headers: { "Content-Type": "application/json", "User-Agent": "lantern-board/1.0" },
    body: JSON.stringify(body) });
  return { status: r.status, body: await r.json() };
}
// post on un-initialized board -> SENTINEL_MISSING
const cm = Date.now();
const canonical = `smoke-node|lantern-board|smoke-1|hello|${cm}|GENESIS`;
const sig = await crypto.subtle.sign("Ed25519", ku.privateKey, new TextEncoder().encode(`lantern-board-post|${canonical}`));
const s1 = await call({ action: "post", token: "lantern-board-test-2026-09-06", board: "lantern-board",
  node_id: "smoke-node", message_id: "smoke-1", content: "hello", created_ms: cm,
  signature: Array.from(new Uint8Array(sig)).map((b) => b.toString(16).padStart(2, "0")).join(""),
  public_key: pk, prev_hash: "GENESIS", kind: "post" });
console.log("uninit post:", s1.status, s1.body.error);
// seed head (represents the authorized resync_head result) and retry
__store.admin.seedHead();
const cm2 = Date.now();
const canonical2 = `smoke-node|lantern-board|smoke-2|hello|${cm2}|GENESIS`;
const sig2 = await crypto.subtle.sign("Ed25519", ku.privateKey, new TextEncoder().encode(`lantern-board-post|${canonical2}`));
const s2 = await call({ action: "post", token: "lantern-board-test-2026-09-06", board: "lantern-board",
  node_id: "smoke-node", message_id: "smoke-2", content: "hello", created_ms: cm2,
  signature: Array.from(new Uint8Array(sig2)).map((b) => b.toString(16).padStart(2, "0")).join(""),
  public_key: pk, prev_hash: "GENESIS", kind: "post" });
console.log("seeded post:", s2.status, JSON.stringify(s2.body).slice(0, 140));
Deno.exit(0);
