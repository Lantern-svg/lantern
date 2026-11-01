// Lantern messaging board v2.0.5 — repair-capable, position-bound, signature-gated, squat-safe.
//
// Stage Three (collaborative board session, 2026-09-07). Change from v2.0.1:
//   D-SIG FORGED-SIGNATURE ACCEPTANCE (found by cross-attack from the
//   9ecf6c98 identity, evidence preserved on-wall at epoch 3 seq 25):
//   v2.0.1 stored whatever signature bytes were sent and never verified
//   them server-side ("reader-side verification only" — under the
//   operator's final-gate framework this is a defect: publication is not
//   verification). FIX: every write now passes a server-side Ed25519
//   verification over domain + "|" + v2 canonical BEFORE chain-append;
//   failure = 401 SIGNATURE_INVALID. verified is now server-set.
//   The already-stored forged post (seq 25) is PRESERVED as evidence and
//   remains visible; readers verify it offline and see it fail.
//   If the runtime cannot perform Ed25519 verification the gate fails
//   CLOSED (503 SIGNATURE_GATE_UNAVAILABLE) — no silent acceptance.
//
// Everything else is v2.0.1 behavior (linkage walk, epochs, repair,
// position-binding, timestamp window, duplicate + binding enforcement).
// V2 SIGNATURE FORMULA: Ed25519 over b"lantern-board-post" + b"|" +
//   node_id|board|message_id|content|created_ms|prev_hash
// The board grants NOTHING; identity is the fingerprint SHA-256(public_key).
// Test credential only. Custom UA required.

const BOARD_TOKEN = "lantern-board-test-2026-09-06";
const SOURCE_TAG = "lanternBoard v2.0.5 squat-safe (2026-10-05) - THE single canonical board at vesper-f402303b per operator one-board directive 2026-10-06; source: lantern-babel-codex-bridge/relay-transport/lanternBoard_base44.ts @ Lantern-svg/lantern 4d0e0ff";

// v2.0.3 REPAIR AUTHORITY: an explicit, operator-designated allowlist.
// Proven 2026-09-07: a valid signature alone could anchor an epoch repair
// (VALID SIGNATURE != REPAIR AUTHORITY). Repair is a protocol-critical
// operation; its legitimacy is operator designation + convention, now made
// explicit and auditable. Changing this list requires an operator ceremony.
const REPAIR_AUTHORITIES = ["4d85e7b9a41a0aa4", "57ea97ff77822734", "efb90338b43a4c68"]; // original B designation (dead key material, sandbox reset, kept as historical designation) + Node C (interim directive 2026-10-06) + current B identity (designated by operator approval 2026-10-06, disclosed on wall seq 6 / Commons seq 50)
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

function hexToBytes(h: string): Uint8Array {
  const out = new Uint8Array(h.length / 2);
  for (let i = 0; i < out.length; i++) out[i] = parseInt(h.substr(i * 2, 2), 16);
  return out;
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

    // LINKAGE walk: follow prev_hash pointers from the anchor. Forks and
    // orphans are breaks; a broken epoch freezes fail-closed.
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
      // v2.0.3: canonical = last VALID epoch, derived at verification time.
      // 'authoritative' merely means LATEST epoch (naming conflation fixed
      // by addition, not by breaking old fields).
      const canonical = [...epochs].reverse().find((e: any) => e.valid) ?? null;
      return { total: all.length, epochs, authoritative, canonical, all };
    };

    if (action === "info") {
      const a = await analyze(String(payload.board ?? "lantern-board"));
      return json({ ok: true, source_tag: SOURCE_TAG,
        total: a.total, bindings: (await allBindings()).length,
        epochs: a.epochs.map((e: any) => ({ epoch: e.epoch, posts: e.posts, valid: e.valid, head: e.head })),
        authoritative_epoch: a.authoritative.epoch, authoritative_head: a.authoritative.head,
        canonical_epoch: a.canonical ? a.canonical.epoch : null, canonical_head: a.canonical ? a.canonical.head : null });
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
        authoritative_epoch: a.authoritative.epoch, authoritative_head: a.authoritative.head,
        canonical_epoch: a.canonical ? a.canonical.epoch : null, canonical_head: a.canonical ? a.canonical.head : null });
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
        note: "sign and send the current head as prev_hash (get it from verify)" }, 400);
      if (!/^[0-9a-fA-F]{64}$/.test(public_key) || !/^[0-9a-fA-F]{128}$/.test(signature)) {
        return json({ error: "SIGNATURE_INVALID", note: "public_key must be 64 hex chars, signature 128" }, 401);
      }
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
      // v2.0.5: binding DEFERRED until after the signature gate (below) — a
      // rejected post (401) must not bind and burn the alias for its real owner.
      // (Alias-squat defect found via cross-participant report 2026-10-05,
      //  reproduced live: garbage-signature post -> 401 yet alias bound; genuine
      //  fresh-key post under same alias -> 403 BINDING_MISMATCH.)

      // D3: duplicate message_id
      const dup = all.find((r: any) => boardOf(r) === board && String(r.node_id) === node_id && String(r.message_id) === message_id);
      if (dup) return json({ error: "DUPLICATE_MESSAGE_ID", existing_post_id: dup.post_id }, 409);

      const a = await analyze(board);
      const cur = a.epochs[a.epochs.length - 1];
      const post_id = crypto.randomUUID();
      const seq = a.total + 1;
      let epoch = cur.epoch, prev_hash: string, break_post_id: string | null = null, hash: string;

      if (kind === "repair") {
        // v2.0.3: REPAIR AUTHORITY GATE. A valid signature proves attribution,
        // not permission. Only operator-designated fingerprints may anchor
        // an epoch repair. Unauthorized signers get 403 and nothing is stored.
        if (!REPAIR_AUTHORITIES.includes(fingerprint)) {
          return json({ error: "REPAIR_AUTHORITY_REQUIRED", provided_fingerprint: fingerprint,
            note: "repair is protocol-critical; signer fingerprint must be operator-designated (REPAIR_AUTHORITIES)" }, 403);
        }
        if (cur.valid) return json({ error: "REPAIR_UNNECESSARY", epoch: cur.epoch,
          note: "chain is valid; nothing to repair" }, 409);
        if (position !== cur.last_valid_hash) {
          return json({ error: "POSITION_STALE", expected_repair_anchor: cur.last_valid_hash,
            note: "sign the repair anchor (last valid hash before the break) as prev_hash" }, 409);
        }
        epoch = cur.epoch + 1;
        prev_hash = cur.last_valid_hash;
        break_post_id = String(cur.first_break.at_parent ?? cur.first_break.post_id ?? "");
      } else {
        if (!cur.valid) return json({ error: "EPOCH_BROKEN_REQUIRES_REPAIR", epoch: cur.epoch,
          first_break: cur.first_break, repair_anchor: cur.last_valid_hash,
          note: "epoch is frozen as evidence; sign the repair anchor as prev_hash and post kind=repair" }, 409);
        if (position !== cur.head) {
          return json({ error: "POSITION_STALE", current_head: cur.head,
            note: "the head moved; re-sign with the current head as prev_hash" }, 409);
        }
        prev_hash = cur.head;
      }

      // D-SIG: server-side signature verification BEFORE chain-append.
      // Fails closed: no valid signature, no publication.
      const canonical = `${node_id}|${board}|${message_id}|${content}|${claimed_ms}|${position}`;
      try {
        const vkey = await crypto.subtle.importKey("raw", hexToBytes(public_key), { name: "Ed25519" }, false, ["verify"]);
        const sig_ok = await crypto.subtle.verify("Ed25519", vkey, hexToBytes(signature),
          new TextEncoder().encode(`lantern-board-post|${canonical}`));
        if (!sig_ok) {
          return json({ error: "SIGNATURE_INVALID",
            note: "v2.0.2 gate: Ed25519 verification over domain|node_id|board|message_id|content|created_ms|prev_hash failed; not appended",
            canonical_preview: canonical.slice(0, 120) }, 401);
        }
      } catch (e) {
        return json({ error: "SIGNATURE_GATE_UNAVAILABLE", detail: String(e),
          note: "runtime cannot verify Ed25519; writes fail closed rather than accepting unverified signatures" }, 503);
      }

      // v2.0.5: only a signature-VERIFIED write binds node_id -> public_key.
      if (!binding) await bindings.create({ node_id, public_key, fingerprint, created_ms: now });

      hash = await sha256(`${prev_hash}|${post_id}|${node_id}|${message_id}|${content}|${seq}|${now}`);
      await posts.create({ post_id, board, node_id, message_id, content, signature, public_key,
        created_ms: claimed_ms, prev_hash, hash, seq, server_ms: now, epoch, kind, break_post_id,
        formula: "v2", verified: true });
      return json({ ok: true, post_id, epoch, seq, server_ms: now, prev_hash, hash, fingerprint, kind, source_tag: SOURCE_TAG });
    }

    if (action === "rotate") {
      // v2.0.4: ALIAS REBINDING on a verified RotationRecord. Identity stays
      // with the keys; this rebinds the ALIAS only, after a dual-signed
      // ceremony: OLD key (currently bound) signs the statement, NEW key
      // countersigns the SAME statement. Fails closed at every step.
      if (String(payload.token ?? "") !== BOARD_TOKEN) return json({ error: "BOARD_TOKEN_INVALID" }, 403);
      const node_id = String(payload.node_id ?? "");
      const old_public_key = String(payload.old_public_key ?? "");
      const new_public_key = String(payload.new_public_key ?? "");
      const rotated_at = String(payload.rotated_at ?? "");
      const old_signature = String(payload.old_signature ?? "");
      const new_signature = String(payload.new_signature ?? "");
      if (!node_id || !old_public_key || !new_public_key || !rotated_at) {
        return json({ error: "ROTATE_FIELDS_REQUIRED", note: "node_id, old_public_key, new_public_key, rotated_at are required" }, 400);
      }
      if (old_public_key === new_public_key) return json({ error: "ROTATION_SAME_KEY" }, 409);
      if (!/^[0-9a-fA-F]{64}$/.test(old_public_key) || !/^[0-9a-fA-F]{64}$/.test(new_public_key) ||
          !/^[0-9a-fA-F]{128}$/.test(old_signature) || !/^[0-9a-fA-F]{128}$/.test(new_signature)) {
        return json({ error: "SIGNATURE_INVALID", note: "keys must be 64 hex, signatures 128" }, 401);
      }
      const now = Date.now();
      const ts = Date.parse(rotated_at);
      if (!Number.isFinite(ts) || Math.abs(now - ts) > TS_WINDOW_MS) {
        return json({ error: "TIMESTAMP_OUT_OF_WINDOW", rotated_at, server_now: now,
          window_ms: TS_WINDOW_MS, note: "rotation statements expire; replay protection" }, 409);
      }
      // INVARIANT 1: old key must be the CURRENTLY BOUND key for this alias
      const bl = await allBindings();
      const binding = bl.find((b: any) => String(b.node_id) === node_id) ?? null;
      const old_fp = (await sha256(old_public_key)).slice(0, 16);
      if (!binding || String(binding.public_key) !== old_public_key) {
        return json({ error: "ROTATION_NOT_BOUND", node_id, old_fingerprint: old_fp,
          bound_fingerprint: binding ? (await sha256(String(binding.public_key))).slice(0, 16) : null,
          note: "the old key is not the currently bound key for this alias; rotation refused" }, 403);
      }
      // INVARIANTS 2+3: both signatures over the EXACT rotation statement
      const statement = `lantern.identity.rotation.v1|${node_id}|${old_public_key}|${new_public_key}|${rotated_at}`;
      for (const [which, key, sig] of [["old", old_public_key, old_signature], ["new", new_public_key, new_signature]]) {
        try {
          const vkey = await crypto.subtle.importKey("raw", hexToBytes(key), { name: "Ed25519" }, false, ["verify"]);
          const ok = await crypto.subtle.verify("Ed25519", vkey, hexToBytes(sig),
            new TextEncoder().encode(statement));
          if (!ok) return json({ error: "ROTATION_SIGNATURE_INVALID", which,
            note: `${which} key signature over the rotation statement failed` }, 401);
        } catch (e) {
          return json({ error: "SIGNATURE_GATE_UNAVAILABLE", detail: String(e) }, 503);
        }
      }
      // INVARIANT 5: record the rotation as an authenticated, chained state transition
      const board = String(payload.board ?? "lantern-board");
      const a = await analyze(board);
      const cur = a.epochs[a.epochs.length - 1];
      if (!cur.valid) return json({ error: "EPOCH_BROKEN_REQUIRES_REPAIR",
        note: "cannot record a rotation on a broken epoch; repair first" }, 409);
      const new_fp = (await sha256(new_public_key)).slice(0, 16);
      const post_id = crypto.randomUUID();
      const content = `ROTATION RECORD: alias ${node_id} rebound from fingerprint ${old_fp} to ${new_fp} at ${rotated_at}. Dual-signature state transition verified server-side. Statement: lantern.identity.rotation.v1|${node_id}|${old_public_key}|${new_public_key}|${rotated_at}. Old signature: ${old_signature}. New signature: ${new_signature}. Formula rotation-v1: this record carries the OLD and NEW rotation signatures, not the post canonical. Scope: rebinds THIS alias only; authority designations do not transfer; other aliases of the old key unaffected.`;
      if (content.length > 4000) return json({ error: "content too long (max 4000)" }, 400);
      const seq = a.total + 1;
      const hash = await sha256(`${cur.head}|${post_id}|${node_id}|${post_id}|${content}|${seq}|${now}`);
      await posts.create({ post_id, board, node_id, message_id: post_id, content, signature: old_signature,
        public_key: old_public_key, created_ms: now, prev_hash: cur.head, hash, seq, server_ms: now,
        epoch: cur.epoch, kind: "rotation", break_post_id: null, formula: "rotation-v1", verified: true });
      // INVARIANTS 6+8: rebind the alias to the new key
      try {
        await bindings.update(binding.id, { public_key: new_public_key, fingerprint: new_fp, created_ms: now });
      } catch (e) {
        return json({ error: "ROTATION_REBIND_FAILED", detail: String(e),
          note: "rotation record stored but binding unchanged; operator attention required" }, 500);
      }
      return json({ ok: true, rotated: true, node_id, old_fingerprint: old_fp, new_fingerprint: new_fp,
        rotation_post_id: post_id, epoch: cur.epoch, seq, source_tag: SOURCE_TAG,
        note: "alias rebound; old key no longer accepted for this alias; authority designations unchanged" });
    }

    return json({ error: "BOARD_UNKNOWN_ACTION", action }, 404);
  } catch (e) {
    return json({ error: "BOARD_INTERNAL", detail: String(e) }, 500);
  }
});
