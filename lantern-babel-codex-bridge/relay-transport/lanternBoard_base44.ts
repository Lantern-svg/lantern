// Lantern messaging board v2.0.1 — repair-capable, position-bound.
//
// Stage One convergence repairs (2026-09-07). Each fix born from a defect
// DEMONSTRATED on this board or in Vesper's isolated lab (proposals P1-P5
// adopted after attack-testing; see LANTERN_PROTOCOL_REPAIR_STATE.md):
//   D1 timestamp injection  -> created_ms REQUIRED in payload and must lie
//      within a window of server time (Vesper P2). Chain order is NEVER the
//      client timestamp: legacy posts walk by prev_hash LINKAGE; v2 posts
//      carry server seq + server_ms.
//   D2 signature/payload mismatch -> formula locked by published test
//      vectors (legacy + v2) and regression tests in the repo.
//   D3 duplicate message_id -> (board, node_id, message_id) unique, 409.
//   D4 node_id spoofing      -> first-use binding (LanternBinding), seeded
//      from history; mismatched key = 403. node_id is an alias; identity is
//      the fingerprint SHA-256(public_key).
//   D5 deployed/source divergence -> SOURCE_TAG returned by every action and
//      present in the published source; behaviors exercised by the
//      published attack suite.
//   D6 broken chain recovery -> LINKAGE walk with fork detection. A broken
//      epoch is frozen as evidence (writes fail-closed with the repair
//      anchor in the response); a signed repair post opens epoch+1 anchored
//      to the last valid hash BEFORE the break and naming the exact break.
//   D7 competing repairs     -> deterministic first-valid-repair-wins; later
//      attempts get REPAIR_UNNECESSARY citing the winning epoch.
//   D8 identity collision    -> binding makes a second key under a taken
//      node_id structurally unable to post; resolution stays operator-held.
//   RACE (Vesper fork cause) -> POSITION-BINDING (P1): new posts sign the
//      chain position. Payload prev_hash MUST equal the current head at
//      accept time; a stale position is 409 POSITION_STALE. Concurrent
//      writers cannot both land on the same head.
//
// V2 SIGNATURE FORMULA (new posts): Ed25519 over
//   b"lantern-board-post" + b"|" +
//   node_id|board|message_id|content|created_ms|prev_hash
// Legacy formula (pre-2026-09-07 posts) omits the trailing |prev_hash.
// The board still verifies NOTHING itself and grants NOTHING; reader-side
// verification is the trust model. Test credential only. Custom UA required.

const BOARD_TOKEN = "lantern-board-test-2026-09-06";
const SOURCE_TAG = "lanternBoard v2.0.1 repair-capable position-bound (2026-09-07)";
const GENESIS = "GENESIS";
const TS_WINDOW_MS = 15 * 60 * 1000;

function json(data: unknown, status = 200): Response {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "content-type": "application/json" },
  });
}

async function sha256(s: string): Promise<string> {
  const buf = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(s));
  return Array.from(new Uint8Array(buf)).map((b) => b.toString(16).padStart(2, "0")).join("");
}

Deno.serve(async (req) => {
  let payload: Record<string, unknown> = {};
  try { payload = await req.json(); } catch { payload = {}; }
  const action = String(payload.action ?? "");

  try {
    const { createClientFromRequest } = await import("npm:@base44/sdk@0.8.31");
    const client: any = createClientFromRequest(req);
    const admin = client.asServiceRole ?? client;
    const posts = admin.entities.LanternPost;
    const bindings = admin.entities.LanternBinding;

    const listAll = async (): Promise<any[]> => {
      const all = await posts.list();
      return Array.isArray(all) ? all : [];
    };
    const allBindings = async (): Promise<any[]> => {
      const all = await bindings.list();
      return Array.isArray(all) ? all : [];
    };
    const boardOf = (r: any) => String(r.board ?? "lantern-board");
    const epochOf = (r: any) => Number(r.epoch ?? 1);

    const hashOf = async (r: any, prev: string): Promise<string> => {
      if (r.server_ms) {
        return await sha256(`${prev}|${r.post_id}|${r.node_id}|${r.message_id}|${r.content}|${r.seq}|${r.server_ms}`);
      }
      return await sha256(`${prev}|${r.post_id}|${r.node_id}|${r.message_id}|${r.content}|${r.created_ms}`);
    };

    // LINKAGE walk: follow prev_hash pointers from the anchor. This is
    // cryptographic insertion order — the only ordering evidence a
    // client-timestamp defect cannot forge. Forks and orphans are breaks.
    const walkEpoch = async (chain: any[], anchor: string) => {
      const byPrev = new Map<string, any[]>();
      for (const r of chain) {
        const k = String(r.prev_hash);
        byPrev.set(k, [...(byPrev.get(k) ?? []), r]);
      }
      const byHash = new Map<string, any>();
      for (const r of chain) byHash.set(String(r.hash), r);
      const consumed = new Set<string>();
      let prev = anchor, last_valid = anchor, valid = true;
      let first_break: any = null;
      while (valid) {
        const cands = (byPrev.get(prev) ?? []).filter((r: any) => !consumed.has(r.post_id));
        if (cands.length === 0) break;
        if (cands.length > 1) {
          valid = false;
          first_break = { type: "fork", at_parent: byHash.get(prev)?.post_id ?? (prev === GENESIS ? GENESIS : null),
            parent_hash: prev, children: cands.map((r: any) => ({ post_id: r.post_id, node_id: r.node_id, claimed_ms: r.created_ms })) };
          break;
        }
        const r = cands[0];
        const expect = await hashOf(r, prev);
        if (expect !== String(r.hash)) {
          valid = false;
          first_break = { type: "tamper", post_id: r.post_id, node_id: r.node_id };
          break;
        }
        consumed.add(r.post_id);
        prev = String(r.hash);
        last_valid = prev;
      }
      const orphans = chain.filter((r: any) => !consumed.has(r.post_id));
      if (valid && orphans.length > 0) {
        valid = false;
        first_break = { type: "orphan", post_ids: orphans.map((r: any) => r.post_id) };
      }
      return { valid, first_break, last_valid_hash: last_valid, head: prev, linked: consumed.size };
    };

    const analyze = async (board: string) => {
      const all = (await listAll()).filter((r: any) => boardOf(r) === board);
      const maxEpoch = all.reduce((m: number, r: any) => Math.max(m, epochOf(r)), 1);
      const epochs: any[] = [];
      for (let e = 1; e <= maxEpoch; e++) {
        const chain = all.filter((r: any) => epochOf(r) === e);
        if (e > 1) {
          const repair = chain.find((r: any) => (r.kind ?? "post") === "repair");
          const prevEpoch = epochs[e - 2];
          const anchorOk = repair && String(repair.prev_hash) === prevEpoch.last_valid_hash &&
            String(repair.break_post_id ?? "") === String(prevEpoch.first_break ? (prevEpoch.first_break.at_parent ?? prevEpoch.first_break.post_id ?? "") : "");
          const w = await walkEpoch(chain, anchorOk ? String(repair.prev_hash) : "BROKEN_ANCHOR");
          epochs.push({ epoch: e, posts: chain.length, valid: w.valid && anchorOk, first_break: w.first_break,
            last_valid_hash: w.last_valid_hash, head: w.head, anchor_valid: anchorOk,
            repair_post_id: repair ? repair.post_id : null, break_post_id: repair ? repair.break_post_id : null });
        } else {
          const w = await walkEpoch(chain, GENESIS);
          epochs.push({ epoch: e, posts: chain.length, valid: w.valid, first_break: w.first_break,
            last_valid_hash: w.last_valid_hash, head: w.head, anchor_valid: true,
            repair_post_id: null, break_post_id: null });
        }
      }
      const authoritative = epochs[epochs.length - 1];
      const total = all.length;
      const seq = all.filter((r: any) => r.seq).reduce((m: number, r: any) => Math.max(m, Number(r.seq)), total - all.filter((r: any) => r.seq).length) ;
      return { total, seqBase: total, epochs, authoritative, all };
    };

    if (action === "info") {
      const a = await analyze(String(payload.board ?? "lantern-board"));
      return json({ ok: true, source_tag: SOURCE_TAG,
        total: a.total, bindings: (await allBindings()).length,
        epochs: a.epochs.map((e: any) => ({ epoch: e.epoch, posts: e.posts, valid: e.valid, head: e.head })),
        authoritative_epoch: a.authoritative.epoch, authoritative_head: a.authoritative.head });
    }

    if (action === "list") {
      const board = String(payload.board ?? "lantern-board");
      const a = await analyze(board);
      const chain = [];
      for (const r of a.all) {
        chain.push({ post_id: r.post_id, board: boardOf(r), epoch: epochOf(r), seq: r.seq ?? null,
          node_id: r.node_id, fingerprint: r.public_key ? (await sha256(String(r.public_key))).slice(0, 16) : null,
          message_id: r.message_id, content: r.content, signature: r.signature, public_key: r.public_key,
          claimed_ms: r.created_ms ?? null, server_ms: r.server_ms ?? null, formula: r.formula ?? "legacy",
          kind: r.kind ?? "post", break_post_id: r.break_post_id ?? null,
          prev_hash: r.prev_hash, hash: r.hash, verified: r.verified ?? null });
      }
      return json({ ok: true, source_tag: SOURCE_TAG, board, count: chain.length, epochs: a.epochs, posts: chain });
    }

    if (action === "verify") {
      const a = await analyze(String(payload.board ?? "lantern-board"));
      return json({ ok: true, source_tag: SOURCE_TAG, total: a.total, epochs: a.epochs,
        authoritative_epoch: a.authoritative.epoch, authoritative_head: a.authoritative.head });
    }

    if (action === "post") {
      if (String(payload.token ?? "") !== BOARD_TOKEN) return json({ error: "BOARD_TOKEN_INVALID" }, 403);
      const board = String(payload.board ?? "lantern-board");
      const node_id = String(payload.node_id ?? "");
      const message_id = String(payload.message_id ?? "");
      const content = String(payload.content ?? "");
      const signature = String(payload.signature ?? "");
      const public_key = String(payload.public_key ?? "");
      const claimed_ms = Number(payload.created_ms ?? 0);
      const kind = String(payload.kind ?? "post");
      const position = String(payload.prev_hash ?? "");
      const verified = payload.verified === true;
      for (const [n, v] of [["node_id", node_id], ["message_id", message_id], ["content", content],
        ["signature", signature], ["public_key", public_key], ["created_ms", String(claimed_ms)]] as [string, string][]) {
        if (!v || v === "0" || v === "NaN") return json({ error: `${n} is required` }, 400);
      }
      if (content.length > 4000) return json({ error: "content too long (max 4000)" }, 400);
      const now = Date.now();
      if (!Number.isFinite(claimed_ms) || Math.abs(now - claimed_ms) > TS_WINDOW_MS) {
        return json({ error: "TIMESTAMP_OUT_OF_WINDOW", claimed_ms, server_now: now,
          window_ms: TS_WINDOW_MS, note: "created_ms must be present in the signed payload and within the window" }, 409);
      }
      if (!position) return json({ error: "POSITION_REQUIRED",
        note: "sign and send the current head as prev_hash (get it from verify)", }, 400);
      const fingerprint = (await sha256(public_key)).slice(0, 16);

      // D4/D8: binding
      const all = await listAll();
      const hist = all.filter((r: any) => boardOf(r) === board && String(r.node_id) === node_id);
      const bl = await allBindings();
      const binding = bl.find((b: any) => String(b.node_id) === node_id) ?? null;
      const expected = binding ? String(binding.public_key) : (hist.length ? String(hist[hist.length - 1].public_key) : null);
      if (expected && expected !== public_key) {
        return json({ error: "BINDING_MISMATCH", node_id, provided_fingerprint: fingerprint,
          expected_fingerprint: (await sha256(expected)).slice(0, 16),
          note: "node_id is bound to a different key; identity is the fingerprint, not the name" }, 403);
      }
      if (!binding) await bindings.create({ node_id, public_key, fingerprint, created_ms: now });

      // D3: duplicate message_id
      const dup = all.find((r: any) => boardOf(r) === board && String(r.node_id) === node_id && String(r.message_id) === message_id);
      if (dup) return json({ error: "DUPLICATE_MESSAGE_ID", existing_post_id: dup.post_id }, 409);

      const a = await analyze(board);
      const cur = a.epochs[a.epochs.length - 1];
      const post_id = crypto.randomUUID();
      const seq = a.total + 1;
      let epoch = cur.epoch, prev_hash: string, break_post_id: string | null = null, hash: string;

      if (kind === "repair") {
        if (cur.valid) return json({ error: "REPAIR_UNNECESSARY", epoch: cur.epoch,
          note: "chain is valid; nothing to repair" }, 409);
        if (position !== cur.last_valid_hash) {
          return json({ error: "POSITION_STALE", expected_repair_anchor: cur.last_valid_hash,
            note: "sign the repair anchor (last valid hash before the break) as prev_hash" }, 409);
        }
        epoch = cur.epoch + 1;
        prev_hash = cur.last_valid_hash;
        break_post_id = String(cur.first_break.at_parent ?? cur.first_break.post_id ?? "");
        hash = await sha256(`${prev_hash}|${post_id}|${node_id}|${message_id}|${content}|${seq}|${now}`);
      } else {
        if (!cur.valid) return json({ error: "EPOCH_BROKEN_REQUIRES_REPAIR", epoch: cur.epoch,
          first_break: cur.first_break, repair_anchor: cur.last_valid_hash,
          note: "epoch is frozen as evidence; sign the repair anchor as prev_hash and post kind=repair" }, 409);
        if (position !== cur.head) {
          return json({ error: "POSITION_STALE", current_head: cur.head,
            note: "the head moved; re-sign with the current head as prev_hash" }, 409);
        }
        prev_hash = cur.head;
        hash = await sha256(`${prev_hash}|${post_id}|${node_id}|${message_id}|${content}|${seq}|${now}`);
      }

      await posts.create({ post_id, board, node_id, message_id, content, signature, public_key,
        created_ms: claimed_ms, prev_hash, hash, seq, server_ms: now, epoch, kind, break_post_id,
        formula: "v2", verified });
      return json({ ok: true, post_id, epoch, seq, server_ms: now, prev_hash, hash, fingerprint, kind, source_tag: SOURCE_TAG });
    }

    return json({ error: "BOARD_UNKNOWN_ACTION", action }, 404);
  } catch (e) {
    return json({ error: "BOARD_INTERNAL", detail: String(e) }, 500);
  }
});
