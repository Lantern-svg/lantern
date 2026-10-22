// lib.ts — shared helpers for the lanternBoard v2.0.6 hardening harness.
import { __store } from "./sdk_mock.ts";

export const TOKEN = "lantern-board-test-2026-09-06";
export const BOARD = "lantern-board";

export interface KeyPair { sk: CryptoKey; pk: string; fp: string }

export async function genKey(): Promise<KeyPair> {
  const ku = await crypto.subtle.generateKey({ name: "Ed25519" } as any, false, ["sign", "verify"]) as CryptoKeyPair;
  const raw = new Uint8Array(await crypto.subtle.exportKey("raw", ku.publicKey));
  const pk = Array.from(raw).map((b) => b.toString(16).padStart(2, "0")).join("");
  return { sk: ku.privateKey, pk, fp: await fpOf(pk) };
}

export async function fpOf(pk: string): Promise<string> {
  const d = new Uint8Array(await crypto.subtle.digest("SHA-256", new TextEncoder().encode(pk)));
  return Array.from(d.slice(0, 8)).map((b) => b.toString(16).padStart(2, "0")).join("");
}

export async function sign(k: KeyPair, msg: string): Promise<string> {
  const s = await crypto.subtle.sign("Ed25519", k.sk, new TextEncoder().encode(msg));
  return Array.from(new Uint8Array(s)).map((b) => b.toString(16).padStart(2, "0")).join("");
}

export async function call(body: any): Promise<{ status: number; body: any }> {
  const r = await fetch("http://localhost:8000/", { method: "POST",
    headers: { "Content-Type": "application/json", "User-Agent": "lantern-board/1.0" },
    body: JSON.stringify(body) });
  let b: any = null; try { b = await r.json(); } catch { /* */ }
  return { status: r.status, body: b };
}

export async function verify(): Promise<any> {
  return (await call({ action: "verify", board: BOARD })).body;
}

export async function makePost(k: KeyPair, node: string, mid: string, content: string, prev: string) {
  const cm = Date.now();
  const canonical = `${node}|${BOARD}|${mid}|${content}|${cm}|${prev}`;
  const signature = await sign(k, `lantern-board-post|${canonical}`);
  return call({ action: "post", token: TOKEN, board: BOARD, node_id: node, message_id: mid,
    content, created_ms: cm, signature, public_key: k.pk, prev_hash: prev, kind: "post" });
}

export async function makeRotate(node: string, oldK: KeyPair, newK: KeyPair) {
  const rotated_at = new Date().toISOString();
  const statement = `lantern.identity.rotation.v1|${node}|${oldK.pk}|${newK.pk}|${rotated_at}`;
  const old_signature = await sign(oldK, statement);
  const new_signature = await sign(newK, statement);
  return call({ action: "rotate", token: TOKEN, board: BOARD, node_id: node,
    old_public_key: oldK.pk, new_public_key: newK.pk, rotated_at, old_signature, new_signature });
}

export async function makeResync(k: KeyPair) {
  const resync_at = new Date().toISOString();
  const statement = `lantern.board.resync.v1|${BOARD}|resync-node|${k.pk}|${resync_at}`;
  const signature = await sign(k, statement);
  return call({ action: "resync_head", token: TOKEN, board: BOARD, node_id: "resync-node",
    public_key: k.pk, resync_at, signature });
}

// ---- scripted-mode gate driving -------------------------------------------
export async function settle(): Promise<void> { await new Promise((r) => setTimeout(r, 4)); }

// names of gate ops queued but not yet released, in queue order
export function pending(): string[] {
  return __store.gate.queue.map((e) => e.name);
}

// resolve the queue entry at idx WITHOUT touching the others
export async function releaseAt(idx: number): Promise<void> {
  const q = __store.gate.queue;
  if (idx < 0 || idx >= q.length) return;
  const entry = q.splice(idx, 1)[0]!;
  entry.resolve();
  __store.gate.released++;
  await settle();
}

/** Drive the gate until `cond()` is true, with a bounded wall-clock budget.
 *  On timeout: dump diagnostics (who is blocked on which op, store state)
 *  and throw, so a stuck schedule fails loudly instead of hanging. */
export async function driveUntil(
  label: string,
  cond: () => boolean,
  budgetMs = 4000,
  stepFn: () => Promise<void> = advanceOldest,
): Promise<void> {
  const t0 = Date.now();
  while (!cond()) {
    if (__store.gate.queue.length === 0) { await new Promise((r) => setTimeout(r, 5)); }
    else { await stepFn(); }
    if (Date.now() - t0 > budgetMs) {
      throw new Error(
        `SCHEDULE_TIMEOUT [${label}] after ${budgetMs}ms: blocked ops = [${pending().join(", ")}], ` +
        `heads=${JSON.stringify(__store.admin.heads().map((h) => ({ id: h.id, next_seq: h.next_seq })))}, ` +
        `posts=${__store.admin.posts().length}, opLogTail=${__store.opLog.slice(-8).join(",")}`);
    }
  }
}

// release the OLDEST pending op (advances whichever requester blocked first)
export async function advanceOldest(): Promise<void> { await releaseAt(0); }

// release the NEWEST pending op (advances the most recently blocked requester;
// with two concurrent requesters started in order this advances the second)
export async function advanceNewest(): Promise<void> {
  const q = __store.gate.queue;
  if (q.length === 0) return;
  await releaseAt(q.length - 1);
}

export async function waitDone(p: { done: boolean; result?: any }, timeoutMs = 3000): Promise<boolean> {
  const t0 = Date.now();
  while (!p.done) {
    if (Date.now() - t0 > timeoutMs) return false;
    await settle();
    if (__store.gate.queue.length === 0) await new Promise((r) => setTimeout(r, 8));
  }
  return true;
}

export function track(p: Promise<any>) {
  const w = { done: false, result: null as any };
  p.then((r) => { w.done = true; w.result = r; }).catch((e) => { w.done = true; w.result = { error: String(e) }; });
  return w;
}

// ---- classification --------------------------------------------------------
export interface TrialOutcome { fork: boolean; halt: boolean; clean: boolean; other: boolean;
  falseDesyncs: number; inFlightSignals: number; missingSignals: number; detail: string }

export function dupSeqs(): number[] {
  const seqs = __store.admin.posts().map((p: any) => Number(p.seq));
  const seen = new Set<number>(), dups = new Set<number>();
  for (const s of seqs) { if (seen.has(s)) dups.add(s); seen.add(s); }
  return [...dups];
}

export async function freshBoard(): Promise<void> {
  __store.admin.clear();
  __store.mode = "random"; // caller sets scripted where needed
}

export function mulberry32(seed: number) {
  let a = seed >>> 0;
  return function () {
    a |= 0; a = (a + 0x6D2B79F5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}
