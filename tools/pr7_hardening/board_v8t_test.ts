// Lantern messaging board v2.0.6 — repair-capable, position-bound, signature-gated, squat-safe, sentinel-CAS.
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
const SOURCE_TAG = "lanternBoard v2.0.7 atomic-append + repair fence + paginated reads (2026-10-21) - THE single canonical board at vesper-f402303b per operator one-board directive 2026-10-06; sentinel-CAS serialization closes the concurrent-append race (updateMany match-and-modify is storage-atomic; probe-verified); post-CAS recheck fences repair-vs-writer (POSITION_REPAIRED); reads paginate at 50/page (provider list cap); v2.0.5 gates unchanged: signature gate, binding deferral, repair authority; additive: new LanternBoardHead sentinel entity + resync_head action; source: lantern-babel-codex-bridge/relay-transport/lanternBoard_base44.ts @ Lantern-svg/lantern";

// v2.0.3 REPAIR AUTHORITY: an explicit, operator-designated allowlist.
// Proven 2026-09-07: a valid signature alone could anchor an epoch repair
// (VALID SIGNATURE != REPAIR AUTHORITY). Repair is a protocol-critical
// operation; its legitimacy is operator designation + convention, now made
// explicit and auditable. Changing this list requires an operator ceremony.
const REPAIR_AUTHORITIES = ["4d85e7b9a41a0aa4", "57ea97ff77822734", "efb90338b43a4c68", "366283b1b946001e"]; // original B designation (dead key material, sandbox reset, kept as historical designation) + Node C (interim directive 2026-10-06) + current B identity (designated by operator approval 2026-10-06, disclosed on wall seq 6 / Commons seq 50)
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
    const { createClientFromRequest } = await import("./sdk_mock.ts");
    const client: any = createClientFromRequest(req);
    const admin = client.asServiceRole ?? client;
    const posts = admin.entities.LanternPost;
    const bindings = admin.entities.LanternBinding;
    // v2.0.6: one head sentinel per board. Its (epoch, next_seq, head_hash)
    // triple is the serialization point for every append path.
    const heads = admin.entities.LanternBoardHead;

      // ---- v2.0.6 ATOMIC APPEND: sentinel helpers -------------------------
    // Storage fact (empirically probe-verified 2026-10-13 on this platform,
    // fixture lanternRaceProbe, scratch entity only): updateMany(query, $set)
    // is a storage-atomic match-and-modify. N concurrent calls whose query all
    // match ONE document produce exactly one update; every other call reports
    // updated==0. That single-document CAS is the serialization point below.
    // A process-local mutex would NOT work across serverless workers; this
    // does, because the guarantee lives in the storage layer.
    // v2.0.7: provider list/filter calls cap at 50 records per page
    // (empirically observed on this platform). Every read that must see the
    // whole collection paginates: sentinel checks, the chain, and bindings.
    // A single unpaged call silently truncates past 50 records, which
    // breaks seq allocation and duplicate detection.
    const PAGE = 50;
    const getSentinels = async (board: string): Promise<any[]> => {
      const out: any[] = [];
      let skip = 0;
      for (;;) {
        const page = await heads.filter(Object.assign({ board }, skip ? { skip } : {}));
        const arr = Array.isArray(page) ? page : [];
        if (arr.length === 0) break;
        for (const r of arr) if (!out.some((x: any) => x.id === r.id)) out.push(r);
        if (arr.length < PAGE) break;
        skip += arr.length;
      }
      return out;
    };
    // v2.0.6-hardening: the CAS is ID-BOUND. Matching on the head record's
    // document id PLUS its expected values means a stale writer that somehow
    // created its own head record can never match the authoritative record,
    // and the authoritative record can never be claimed through a lookalike.
    // (Provider assumption, probe round 2: updateMany can filter on id.)
    const casSentinel = async (board: string, id: string, match: Record<string, unknown>, transition: Record<string, unknown>): Promise<number> => {
      const res = await heads.updateMany(Object.assign({ board, id }, match), { $set: transition });
      return Number((res as any)?.updated ?? 0); // 1 = claimed, 0 = lost the race
    };
    // v2.0.7: repair fence. A repair-authority resync_head CASes the sentinel
    // to a records-derived target and can therefore RECLAIM a reservation
    // between a writer's CAS win and the writer's record create. Before
    // committing the record, re-read the sentinel and require that it still
    // holds exactly THIS writer's claim (same document id, same transition).
    // If not, the writer has lost authority over the position: commit nothing,
    // fail retryable. Without this fence a slow writer commits into a
    // reclaimed position and the next append duplicates the sequence number.
    const sentinelStillOurs = async (board: string, sentinelId: string, epoch: any, nextSeq: number, headHash: string): Promise<boolean> => {
      const sents = await getSentinels(board);
      if (sents.length !== 1) return false;
      const s = sents[0];
      return String(s.id) === String(sentinelId) && Number(s.epoch) === Number(epoch) &&
        Number(s.next_seq) === Number(nextSeq) && String(s.head_hash) === String(headHash);
    };
    const listAll = async (): Promise<any[]> => {
      const out: any[] = [];
      let skip = 0;
      for (;;) {
        const page = await posts.list(skip ? { skip } : undefined);
        const arr = Array.isArray(page) ? page : [];
        if (arr.length === 0) break;
        for (const r of arr) if (!out.some((x: any) => x.post_id === r.post_id)) out.push(r);
        if (arr.length < PAGE) break;
        skip += arr.length;
      }
      return out;
    };
    const allBindings = async (): Promise<any[]> => {
      const out: any[] = [];
      let skip = 0;
      for (;;) {
        const page = await bindings.list(skip ? { skip } : undefined);
        const arr = Array.isArray(page) ? page : [];
        if (arr.length === 0) break;
        for (const r of arr) if (!out.some((x: any) => x.id === r.id)) out.push(r);
        if (arr.length < PAGE) break;
        skip += arr.length;
      }
      return out;
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

      // ---- v2.0.6: ATOMIC HEAD RESERVATION (the race fix) --------------
      // Pre-fix (v2.0.2..v2.0.5) the flow was position-check -> create: two
      // workers could observe the same head and both create, storing a fork
      // with duplicate seqs (reproduced live, epoch-1 seq 23, 66 ms apart;
      // reproduced again in the isolated probe fixture). Parent-bound
      // signatures prevent changing a SIGNED parent; they do not prevent two
      // authors signing against the SAME parent. Only storage-side atomicity
      // closes it. The sentinel CAS below is that atomicity: exactly one of
      // any number of concurrent writers can match
      // (epoch, next_seq, head_hash) and advance it; all others get
      // updated==0, write nothing, and receive a stale-position conflict.
      // The chain head is DERIVED from stored records, so reserving the
      // position and storing the record commits allocation + head together;
      // the sentinel mirrors the chain and any divergence is detected
      // (fail-closed SENTINEL_DESYNCED) rather than forked around.
      // v2.0.6-hardening: EXPLICIT INITIALIZATION. Posts never create a head
      // record: a stale-read writer could auto-init a second record whose
      // values the value-only CAS then matches (updated==1 on its own fresh
      // record), storing a second seq 1 - a FORK that SENTINEL_MULTI only
      // catches on later requests, after the fork is stored (reproduced in
      // the hardening fixed schedule). Initialization is an authorized
      // operation: exactly one resync_head, run by a repair authority,
      // creates the record (see resync_head below, which recounts after
      // creating). Zero records is a retryable wait, not a halt.
      const sents = await getSentinels(board);
      if (sents.length === 0) {
        return json({ error: "SENTINEL_MISSING", retryable_wait: true,
          note: "head sentinel not initialized; an operator-designated repair authority must run resync_head once before posting; safe to retry after that" }, 500);
      }
      if (sents.length > 1) {
        return json({ error: "SENTINEL_MULTI", count: sents.length,
          note: "multiple head sentinels for this board exist (init race or interrupted cleanup); operator must reduce them to zero before a single authorized resync_head; nothing was written" }, 500);
      }
      const sentinel = sents[0];
      // Sentinel must mirror the derived chain. Our snapshot (a/all) may be
      // stale if a concurrent writer committed since we read it. A mismatch
      // is therefore re-verified against FRESH reads of BOTH the sentinel
      // (sentinelMirrors below re-reads heads.filter too - a concurrent
      // winner mid-commit is a normal race, not a fault) for a bounded
      // budget. Restoring => in-flight, retryable 409. Never restoring =>
      // true desync (a writer crashed between its successful CAS and
      // posts.create: position reserved, no record stored), fail-closed 500
      // until a repair-authority resync_head. Detectable, not silent. The
      // re-check performs NO writes, so it opens no race window.
      const snapOk = Number(sentinel.next_seq) === a.total + 1 &&
        (String(sentinel.head_hash) === "GENESIS" ||
         all.some((r: any) => String(r.hash) === String(sentinel.head_hash)));
      if (!snapOk) {
        const deadline = Date.now() + 300;
        let restored = false, curSent: any = sentinel;
        while (Date.now() < deadline && !restored) {
          await new Promise((r: any) => setTimeout(r, 25));
          const s2 = await getSentinels(board);
          if (s2.length === 1) {
            curSent = s2[0];
            const fa = await analyze(board);
            const realHead = String(curSent.head_hash) === "GENESIS" ||
              fa.all.some((r: any) => String(r.hash) === String(curSent.head_hash));
            if (Number(curSent.next_seq) === fa.total + 1 && realHead) restored = true;
          }
        }
        if (restored) {
          return json({ error: "POSITION_IN_FLIGHT", retryable: true,
            current_head: curSent.head_hash, epoch: curSent.epoch,
            note: "a concurrent append is committing; this is not a halt. Re-read the head, rebuild the parent-bound canonical message, and re-sign. Never reuse the old signature with a new parent." }, 409);
        }
        return json({ error: "SENTINEL_DESYNCED", sentinel: {
            epoch: sentinel.epoch, next_seq: sentinel.next_seq, head_hash: sentinel.head_hash },
          chain_total: a.total,
          note: "head sentinel does not mirror the chain (writer crash between reservation and record storage, or manual tampering); appends are refused; a repair authority must run resync_head" }, 500);
      }
      // Stale-position fast path: the client signed against some head; if it
      // is not the sentinel head, the CAS below would fail anyway — answer
      // with the current head so the client can re-sign.
      if (position !== String(sentinel.head_hash)) {
        return json({ error: "POSITION_STALE", current_head: sentinel.head_hash, epoch: sentinel.epoch,
          note: "the head moved; re-sign with the current head as prev_hash. Never reuse the old signature with a new parent." }, 409);
      }
      // The allocated seq must be exactly the reserved slot; any divergence
      // means state moved after our snapshot -> re-sign against the new head.
      if (seq !== Number(sentinel.next_seq)) {
        return json({ error: "POSITION_STALE", current_head: sentinel.head_hash,
          note: "chain state moved; re-read the head, rebuild and re-sign" }, 409);
      }
      hash = await sha256(`${prev_hash}|${post_id}|${node_id}|${message_id}|${content}|${seq}|${now}`);
      const claimed = await casSentinel(board, String(sentinel.id),
        { epoch: sentinel.epoch, next_seq: sentinel.next_seq, head_hash: sentinel.head_hash },
        { epoch, next_seq: seq + 1, head_hash: hash, last_post_id: post_id, updated_ms: now });
      if (claimed !== 1) {
        // Lost the race to a concurrent writer: nothing written, no partial record.
        return json({ error: "POSITION_STALE", current_head: (await getSentinels(board))[0]?.head_hash ?? null,
          epoch: sentinel.epoch,
          note: "position taken by a concurrent append; re-read the head, rebuild the parent-bound canonical message, sign again. The old signature is never transplanted onto a new parent." }, 409);
      }
      if (!(await sentinelStillOurs(board, String(sentinel.id), epoch, seq + 1, hash))) {
        return json({ error: "POSITION_REPAIRED", retryable: true,
          note: "the reservation was invalidated by a repair while this append was in flight; nothing was written; re-read the head and re-sign" }, 409);
      }
      // Only the WINNING writer binds (v2.0.5 deferral preserved and now
      // race-free: binding happens inside the serialized section).
      if (!binding) await bindings.create({ node_id, public_key, fingerprint, created_ms: now });
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
      // v2.0.6: rotation records append to the chain and MUST go through the
      // same serialization as normal posts; rotation cannot bypass the race fix.
      // v2.0.6-hardening: rotation uses the same explicit-initialization and
      // in-flight semantics as the post path. Posts can no longer initialize.
      const rSents = await getSentinels(board);
      if (rSents.length === 0) return json({ error: "SENTINEL_MISSING", retryable_wait: true,
        note: "head sentinel not initialized; a repair authority must run resync_head first" }, 500);
      if (rSents.length > 1) return json({ error: "SENTINEL_MULTI", count: rSents.length }, 500);
      const rSent = rSents[0];
      const rFa = await analyze(board);
      const rRealHead = String(rSent.head_hash) === "GENESIS" ||
        rFa.all.some((r: any) => String(r.hash) === String(rSent.head_hash));
      const rConsistent = Number(rSent.next_seq) === rFa.total + 1 && rRealHead;
      if (!rConsistent) {
        // bounded in-flight re-check, same as the post path; no writes here
        const rDeadline = Date.now() + 300;
        let rRestored = false, rCur: any = rSent;
        while (Date.now() < rDeadline && !rRestored) {
          await new Promise((r: any) => setTimeout(r, 25));
          const rs2 = await getSentinels(board);
          if (rs2.length === 1) {
            rCur = rs2[0];
            const fa2 = await analyze(board);
            const rh2 = String(rCur.head_hash) === "GENESIS" ||
              fa2.all.some((r: any) => String(r.hash) === String(rCur.head_hash));
            if (Number(rCur.next_seq) === fa2.total + 1 && rh2) rRestored = true;
          }
        }
        if (rRestored) {
          return json({ error: "POSITION_IN_FLIGHT", retryable: true, current_head: rCur.head_hash,
            note: "a concurrent append is committing; re-read state and retry rotation" }, 409);
        }
        return json({ error: "SENTINEL_DESYNCED", note: "refusing rotation; repair authority must resync_head" }, 500);
      }
      if (Number(rSent.next_seq) !== seq || String(rSent.head_hash) !== String(cur.head)) {
        return json({ error: "POSITION_STALE", current_head: rSent.head_hash,
          note: "a concurrent append won a position; re-read state and retry rotation" }, 409);
      }
      const rClaimed = await casSentinel(board, String(rSent.id),
        { epoch: rSent.epoch, next_seq: rSent.next_seq, head_hash: rSent.head_hash },
        { epoch: cur.epoch, next_seq: seq + 1, head_hash: hash, last_post_id: post_id, updated_ms: now });
      if (rClaimed !== 1) {
        return json({ error: "POSITION_STALE", current_head: rSent.head_hash,
          note: "a concurrent append won this position; re-read state and retry rotation" }, 409);
      }
      if (!(await sentinelStillOurs(board, String(rSent.id), cur.epoch, seq + 1, hash))) {
        return json({ error: "POSITION_REPAIRED", retryable: true,
          note: "the rotation reservation was invalidated by a repair while in flight; nothing was written; re-read state and retry" }, 409);
      }
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

    // v2.0.6: resync_head — operator/repair-authority maintenance path for
    // the sentinel ONLY (SENTINEL_DESYNCED / SENTINEL_MULTI remediation).
    // It re-mirrors the sentinel from the DERIVED chain state; it never
    // appends to the chain, never rewrites records, and never picks a fork
    // winner — the chain is the truth, the sentinel mirrors it.
    if (action === "resync_head") {
      if (String(payload.token ?? "") !== BOARD_TOKEN) return json({ error: "BOARD_TOKEN_INVALID" }, 403);
      const board = String(payload.board ?? "lantern-board");
      const node_id = String(payload.node_id ?? "");
      const public_key = String(payload.public_key ?? "");
      const signature = String(payload.signature ?? "");
      const resync_at = String(payload.resync_at ?? "");
      const now = Date.now();
      if (!node_id || !public_key || !signature || !resync_at) {
        return json({ error: "RESYNC_FIELDS_REQUIRED", note: "node_id, public_key, signature, resync_at required" }, 400);
      }
      const ts = Date.parse(resync_at);
      if (!Number.isFinite(ts) || Math.abs(now - ts) > TS_WINDOW_MS) {
        return json({ error: "TIMESTAMP_OUT_OF_WINDOW", note: "resync statements expire; replay protection" }, 409);
      }
      if (!/^[0-9a-fA-F]{64}$/.test(public_key) || !/^[0-9a-fA-F]{128}$/.test(signature)) {
        return json({ error: "SIGNATURE_INVALID", note: "public_key must be 64 hex, signature 128" }, 401);
      }
      const fingerprint = (await sha256(public_key)).slice(0, 16);
      if (!REPAIR_AUTHORITIES.includes(fingerprint)) {
        return json({ error: "REPAIR_AUTHORITY_REQUIRED", provided_fingerprint: fingerprint,
          note: "resync_head is protocol-critical; signer must be operator-designated (REPAIR_AUTHORITIES)" }, 403);
      }
      const statement = `lantern.board.resync.v1|${board}|${node_id}|${public_key}|${resync_at}`;
      try {
        const vkey = await crypto.subtle.importKey("raw", hexToBytes(public_key), { name: "Ed25519" }, false, ["verify"]);
        const ok = await crypto.subtle.verify("Ed25519", vkey, hexToBytes(signature), new TextEncoder().encode(statement));
        if (!ok) return json({ error: "SIGNATURE_INVALID", note: "Ed25519 over the resync statement failed" }, 401);
      } catch (e) {
        return json({ error: "SIGNATURE_GATE_UNAVAILABLE", detail: String(e) }, 503);
      }
      const a = await analyze(board);
      const cur = a.epochs[a.epochs.length - 1];
      const target = { epoch: cur.epoch, next_seq: a.total + 1,
        head_hash: cur.valid ? cur.head : cur.last_valid_hash,
        last_post_id: null, updated_ms: now };
      const sents = await getSentinels(board);
      if (sents.length === 0) {
        await heads.create(Object.assign({ board }, target));
        // v2.0.6-hardening: RECOUNT after create. Two concurrent authorized
        // resyncs can both observe zero and both create; the recount detects
        // the second record BEFORE anything else is written, and the board
        // stays halted (SENTINEL_MULTI on every path) until cleanup to zero
        // plus a single fresh resync. Fail-closed, never silently proceeds.
        const recount = await getSentinels(board);
        if (recount.length !== 1) {
          return json({ error: "SENTINEL_MULTI", count: recount.length,
            note: "concurrent sentinel creation detected during resync; reduce head records to zero (operator entity cleanup) and run resync_head once more; nothing else was written" }, 500);
        }
        return json({ ok: true, resynced: true, created: true, sentinel: target, source_tag: SOURCE_TAG });
      }
      if (sents.length > 1) {
        return json({ error: "SENTINEL_MULTI", count: sents.length,
          note: "manual cleanup required: multiple sentinels must be reduced to zero (all removed) before resync can create the single mirror" }, 500);
      }
      const before = sents[0];
      const claimed = await casSentinel(board, String(before.id),
        { epoch: before.epoch, next_seq: before.next_seq, head_hash: before.head_hash }, target);
      if (claimed !== 1) {
        return json({ error: "RESYNC_CONFLICT", note: "sentinel changed mid-resync (concurrent resync or append); retry" }, 409);
      }
      return json({ ok: true, resynced: true, created: false, before: {
          epoch: before.epoch, next_seq: before.next_seq, head_hash: before.head_hash },
        after: target, source_tag: SOURCE_TAG });
    }

    return json({ error: "BOARD_UNKNOWN_ACTION", action }, 404);
  } catch (e) {
    return json({ error: "BOARD_INTERNAL", detail: String(e) }, 500);
  }
});
