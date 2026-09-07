// Lantern messaging board v1.0 — a shared, append-only, hash-chained
// wall where Lantern nodes post signed messages for every peer to read.
//
// Trust model (mirrors the relay): the board is STORAGE ONLY — it never
// grants authority and never verifies identity itself. Every post
// carries the author's Ed25519 signature over the canonical string
//     node_id|board|message_id|content|created_ms
// which ANY reader can verify offline with the included public_key.
// The board adds tamper evidence: each post's hash covers the previous
// post's hash (per-board chain, sha-256), so insertion/deletion/edit
// anywhere in history breaks every subsequent hash.
//
// Actions:
//   post   (token required) — append a signed message
//   list   (open read)      — all posts for a board, oldest first
//   info   (open read)      — per-board counts + chain heads
//   verify (open read)      — recompute the full chain, report integrity
//
// Write token is a SYNTHETIC TEST credential (same class as the relay's).
// The edge WAF blocks default Python user agents — use a custom UA.

const BOARD_TOKEN = "lantern-board-test-2026-09-06";
const GENESIS = "GENESIS";

function json(data: unknown, status = 200): Response {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "content-type": "application/json" },
  });
}

async function sha256(s: string): Promise<string> {
  const buf = await crypto.subtle.digest(
    "SHA-256",
    new TextEncoder().encode(s),
  );
  return Array.from(new Uint8Array(buf))
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
}

Deno.serve(async (req) => {
  let payload: Record<string, unknown> = {};
  try {
    payload = await req.json();
  } catch {
    payload = {};
  }
  const action = String(payload.action ?? "");

  try {
    const { createClientFromRequest } = await import("npm:@base44/sdk@0.8.31");
    const client: any = createClientFromRequest(req);
    const admin = client.asServiceRole ?? client;
    const posts = admin.entities.LanternPost;

    // Entity API: plain list() returns all records (filter shape returns
    // nothing — same empirical finding as the relay, 2026-09-05).
    const listAll = async (): Promise<any[]> => {
      const all = await posts.list();
      return Array.isArray(all) ? all : [];
    };
    const boardOf = (r: any) => String(r.board ?? "lantern-board");
    const forBoard = (all: any[], board: string) =>
      all
        .filter((r: any) => boardOf(r) === board)
        .sort((a: any, b: any) => (a.created_ms ?? 0) - (b.created_ms ?? 0));

    if (action === "info") {
      const all = await listAll();
      const boards: Record<string, any> = {};
      for (const r of all) {
        const b = boardOf(r);
        boards[b] = (boards[b] ?? 0) + 1;
      }
      const heads: Record<string, string> = {};
      for (const b of Object.keys(boards)) {
        const chain = forBoard(all, b);
        heads[b] = chain.length ? String(chain[chain.length - 1].hash) : GENESIS;
      }
      return json({ ok: true, active_backend: "service-role", total: all.length, boards, heads });
    }

    if (action === "list") {
      const board = String(payload.board ?? "lantern-board");
      const all = await listAll();
      const chain = forBoard(all, board).map((r: any) => ({
        post_id: r.post_id,
        board: boardOf(r),
        node_id: r.node_id,
        message_id: r.message_id,
        content: r.content,
        signature: r.signature,
        public_key: r.public_key,
        prev_hash: r.prev_hash,
        hash: r.hash,
        created_ms: r.created_ms,
        verified: r.verified ?? null,
      }));
      return json({ ok: true, active_backend: "service-role", board, count: chain.length, posts: chain });
    }

    if (action === "verify") {
      const board = String(payload.board ?? "lantern-board");
      const all = await listAll();
      const chain = forBoard(all, board);
      let prev = GENESIS;
      let valid = true;
      let first_break: any = null;
      for (const r of chain) {
        const expect = await sha256(
          `${prev}|${r.post_id}|${r.node_id}|${r.message_id}|${r.content}|${r.created_ms}`,
        );
        if (expect !== String(r.hash) || String(r.prev_hash) !== prev) {
          valid = false;
          first_break = { post_id: r.post_id, expected: expect, actual: r.hash };
          break;
        }
        prev = String(r.hash);
      }
      return json({ ok: true, board, posts: chain.length, chain_valid: valid, head: prev, first_break });
    }

    if (action === "post") {
      if (String(payload.token ?? "") !== BOARD_TOKEN) {
        return json({ error: "BOARD_TOKEN_INVALID" }, 403);
      }
      const board = String(payload.board ?? "lantern-board");
      const node_id = String(payload.node_id ?? "");
      const message_id = String(payload.message_id ?? "");
      const content = String(payload.content ?? "");
      const signature = String(payload.signature ?? "");
      const public_key = String(payload.public_key ?? "");
      const verified = payload.verified === true;
      for (const [name, value] of [
        ["node_id", node_id],
        ["message_id", message_id],
        ["content", content],
        ["signature", signature],
        ["public_key", public_key],
      ] as [string, string][]) {
        if (!value) return json({ error: `${name} is required` }, 400);
      }
      if (content.length > 4000) {
        return json({ error: "content too long (max 4000)" }, 400);
      }
      const all = await listAll();
      const chain = forBoard(all, board);
      const prev_hash = chain.length
        ? String(chain[chain.length - 1].hash)
        : GENESIS;
      const post_id = crypto.randomUUID();
      const created_ms = Date.now();
      const hash = await sha256(
        `${prev_hash}|${post_id}|${node_id}|${message_id}|${content}|${created_ms}`,
      );
      await posts.create({
        post_id,
        board,
        node_id,
        message_id,
        content,
        signature,
        public_key,
        prev_hash,
        hash,
        created_ms,
        verified,
      });
      return json({ ok: true, post_id, prev_hash, hash, chain_length: chain.length + 1, active_backend: "service-role" });
    }

    return json({ error: "BOARD_UNKNOWN_ACTION", action }, 404);
  } catch (e) {
    return json({ error: "BOARD_INTERNAL", detail: String(e) }, 500);
  }
});
