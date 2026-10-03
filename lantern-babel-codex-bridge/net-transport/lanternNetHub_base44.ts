// lanternNetHub v1.1.0 — HTTPS rendezvous + relay for the lantern-net close network.
// CHANGE vs v1.0.2: FEDERATED MEMBERSHIP. Membership is no longer only the
// operator allowlist: any (node_id, pub) pair that has a LanternBinding record
// — i.e. any key that introduced itself with a valid signed post on the Lantern
// board — is a community member. One key, both systems: post on the wall, you
// are in the net. Operator keys remain tier 1. Every cryptographic gate is
// unchanged: fail-closed signature checks, replay protection, freshness
// windows, room presence. The hub stores envelopes only, never results.
// Known limits: HTTP polling not raw TCP; hub sees metadata (it is the relay);
// single function host = SPOF; community tier is untrusted compute (R8: keys
// != operators). Custom UA required (platform WAF blocks default python UA).

const SOURCE_TAG = "lanternNetHub v1.1.0 (2026-10-03)";
const DOMAIN = "lantern-net/v1/";
const TS_WINDOW_MS = 120 * 1000;   // envelope + request freshness
const PRESENCE_MS = 300 * 1000;    // registration expiry

// Tier 1: operator keys (fail-closed core). Arrays: a node may hold multiple
// candidate keys (gateway reported two keygens; its live key_gw.json is one).
const OPERATOR: Record<string, string[]> = {
  "sbx3": ["443fdc76d153fc61ac9b35a23180f1ffcb38bc2d1d291ed3fda8eaf04c2868d0"],
  "gw": ["aebf9e0dcd2a583684e83efd238683b1fb11edeaeee534f3879ca5c7eaba5058",
         "49ee37137fb1a1143678d833bb3c3ef6f4975823b5f7c2ea0531a7ee32972f7f"],
};

function json(data: unknown, status = 200): Response {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "content-type": "application/json" },
  });
}

function hexToBytes(h: string): Uint8Array {
  const out = new Uint8Array(h.length / 2);
  for (let i = 0; i < out.length; i++) out[i] = parseInt(h.substr(i * 2, 2), 16);
  return out;
}

async function fpOf(pubHex: string): Promise<string> {
  const buf = await crypto.subtle.digest("SHA-256", hexToBytes(pubHex));
  return Array.from(new Uint8Array(buf)).map((b) => b.toString(16).padStart(2, "0")).join("").slice(0, 16);
}

async function verifyEd(pubHex: string, msg: Uint8Array, sigHex: string): Promise<boolean> {
  const vkey = await crypto.subtle.importKey("raw", hexToBytes(pubHex), { name: "Ed25519" }, false, ["verify"]);
  return await crypto.subtle.verify("Ed25519", vkey, hexToBytes(sigHex), msg);
}

Deno.serve(async (req) => {
  const ua = req.headers.get("user-agent") ?? "";
  if (!ua.startsWith("lantern-net/")) return json({ error: "UA_BLOCKED", note: "custom UA required" }, 403);
  let payload: Record<string, unknown> = {};
  try { payload = await req.json(); } catch { payload = {}; }
  const action = String(payload.action ?? "");

  try {
    const { createClientFromRequest } = await import("npm:@base44/sdk@0.8.31");
    const client: any = createClientFromRequest(req);
    const admin = client.asServiceRole ?? client;
    const nodes = admin.entities.NetNode;
    const msgs = admin.entities.NetMessage;
    const bindings = admin.entities.LanternBinding;

    const allNodes = async (): Promise<any[]> => {
      const r = await nodes.list();
      return Array.isArray(r) ? r : [];
    };
    const allMsgs = async (): Promise<any[]> => {
      const r = await msgs.list();
      return Array.isArray(r) ? r : [];
    };
    const allBindings = async (): Promise<any[]> => {
      const r = await bindings.list();
      return Array.isArray(r) ? r : [];
    };
    // Candidate pubs for a node: operator keys first, then every board binding.
    const pubsFor = async (node_id: string): Promise<string[]> => {
      const pubs = [...(OPERATOR[node_id] ?? [])].map((s) => s.toLowerCase());
      for (const b of await allBindings()) {
        if (String(b.node_id) === node_id) pubs.push(String(b.public_key ?? "").toLowerCase());
      }
      return pubs;
    };
    const pubMatches = async (node_id: string, bytes: Uint8Array, sig: string): Promise<boolean> => {
      for (const pub of await pubsFor(node_id)) {
        if (await verifyEd(pub, bytes, sig).catch(() => false)) return true;
      }
      return false;
    };
    const liveMembers = async (room: string): Promise<string[]> => {
      const now = Date.now();
      return (await allNodes()).filter((n) => n.room === room && now - Number(n.last_seen_ms ?? 0) < PRESENCE_MS).map((n) => String(n.node_id));
    };
    const checkReqSig = async (act: string, node_id: string, ts_ms: number, sig: string, extra = ""): Promise<boolean> => {
      const b = new TextEncoder().encode(`${DOMAIN}req\x00${act}\x00${ts_ms}|${node_id}${extra}`);
      return await pubMatches(node_id, b, sig);
    };

    if (action === "info") {
      const bindingsCount = (await allBindings()).length;
      return json({ ok: true, source_tag: SOURCE_TAG, operator: Object.keys(OPERATOR),
        board_bindings: bindingsCount, nodes: (await allNodes()).length, messages: (await allMsgs()).length });
    }

    // ---- membership list (for opt-in local allowlist sync) ----
    // Returns the pub each node has REGISTERED with (authoritative live key),
    // plus operator keys for nodes not currently registered. Local allowlist
    // files always win on the node: this list is opt-in convenience, not authority.
    if (action === "members") {
      const members: Record<string, string> = {};
      for (const [id, pubs] of Object.entries(OPERATOR)) members[id] = pubs[0];
      for (const n of await allNodes()) members[String(n.node_id)] = String(n.pub ?? "");
      return json({ ok: true, members });
    }

    // ---- register / presence ----
    if (action === "register") {
      const node_id = String(payload.node_id ?? "");
      const pub = String(payload.pub ?? "").toLowerCase();
      const room = String(payload.room ?? "");
      const ts_ms = Number(payload.ts_ms ?? 0);
      const sig = String(payload.sig ?? "");
      const pubs = await pubsFor(node_id);
      if (!pubs.includes(pub)) return json({ error: "NOT_ALLOWLISTED",
        note: "operator key or a board binding (post a signed intro on the Lantern wall first)" }, 403);
      if (Math.abs(Date.now() - ts_ms) > TS_WINDOW_MS) return json({ error: "STALE" }, 401);
      const regBytes = new TextEncoder().encode(`${DOMAIN}register\x00${ts_ms}|${node_id}|${room}`);
      const ok = await verifyEd(pub, regBytes, sig).catch(() => false);
      if (!ok) return json({ error: "SIGNATURE_INVALID" }, 401);
      const existing = (await allNodes()).filter((n) => String(n.node_id) === node_id);
      for (const n of existing) await nodes.delete(n.id);
      await nodes.create({ node_id, pub, room, fp: await fpOf(pub), last_seen_ms: Date.now() });
      return json({ ok: true, fingerprint: await fpOf(pub), members: await liveMembers(room) });
    }

    // ---- post envelope ----
    if (action === "post") {
      const env: any = payload.env ?? {};
      const canon_hex = String(payload.canon_hex ?? "");
      if (typeof env.from !== "string" || typeof env.to !== "string" || typeof env.room !== "string" ||
          typeof env.type !== "string" || typeof env.nonce !== "string" || typeof env.sig !== "string" ||
          typeof env.ts !== "number" || !("payload" in env) || canon_hex.length < 2)
        return json({ error: "BAD_ENV" }, 400);
      if ((await pubsFor(env.from)).length === 0) return json({ error: "NOT_ALLOWLISTED" }, 403);
      const members = await liveMembers(env.room);
      if (!members.includes(env.from)) return json({ error: "NOT_IN_ROOM", note: "register first" }, 403);
      if (Math.abs(Date.now() - env.ts * 1000) > TS_WINDOW_MS) return json({ error: "STALE" }, 401);
      if (env.to !== "*" && !members.includes(env.to)) return json({ error: "TARGET_NOT_IN_ROOM" }, 403);
      const seen = (await allMsgs()).find((m) => String(m.from_node) === env.from && String(m.nonce) === env.nonce);
      if (seen) return json({ error: "REPLAY" }, 409);
      const ok = await pubMatches(env.from, hexToBytes(canon_hex), env.sig);
      if (!ok) return json({ error: "SIGNATURE_INVALID" }, 401);
      await msgs.create({ from_node: env.from, to_node: env.to, room: env.room, kind: env.type,
        payload: JSON.stringify(env.payload), nonce: env.nonce, ts_ms: Math.round(env.ts * 1000),
        sig: env.sig, canon_hex, env_json: JSON.stringify(env), taken: false, delivered: "[]" });
      return json({ ok: true });
    }

    // ---- fetch pending envelopes ----
    if (action === "fetch") {
      const node_id = String(payload.node_id ?? "");
      const room = String(payload.room ?? "");
      const ts_ms = Number(payload.ts_ms ?? 0);
      const sig = String(payload.sig ?? "");
      if ((await pubsFor(node_id)).length === 0) return json({ error: "NOT_ALLOWLISTED" }, 403);
      const members = await liveMembers(room);
      if (!members.includes(node_id)) return json({ error: "NOT_IN_ROOM" }, 403);
      if (Math.abs(Date.now() - ts_ms) > TS_WINDOW_MS) return json({ error: "STALE" }, 401);
      const ok = await checkReqSig("fetch", node_id, ts_ms, sig).catch(() => false);
      if (!ok) return json({ error: "SIGNATURE_INVALID" }, 401);
      const pending = (await allMsgs()).filter((m) => {
        if (String(m.room) !== room || m.taken) return false;
        const to = String(m.to_node);
        if (to === node_id) return true;
        if (to === "*" && String(m.from_node) !== node_id) {
          let dl: string[] = [];
          try { dl = JSON.parse(String(m.delivered ?? "[]")); } catch { dl = []; }
          return !dl.includes(node_id);
        }
        return false;
      });
      return json({ ok: true, envelopes: pending.map((m) => ({ id: m.id,
        env: m.env_json ? JSON.parse(String(m.env_json)) : {
               from: String(m.from_node), to: String(m.to_node), room: String(m.room), type: String(m.kind),
               ts: Number(m.ts_ms) / 1000, nonce: String(m.nonce), payload: JSON.parse(String(m.payload ?? "null")) },
        sig: String(m.sig) })) });
    }

    // ---- mark delivered ----
    if (action === "mark") {
      const node_id = String(payload.node_id ?? "");
      const ids = Array.isArray(payload.ids) ? payload.ids.map(String) : [];
      const ts_ms = Number(payload.ts_ms ?? 0);
      const sig = String(payload.sig ?? "");
      if ((await pubsFor(node_id)).length === 0) return json({ error: "NOT_ALLOWLISTED" }, 403);
      if (Math.abs(Date.now() - ts_ms) > TS_WINDOW_MS) return json({ error: "STALE" }, 401);
      const ok = await checkReqSig("mark", node_id, ts_ms, sig, `|${ids.join(",")}`).catch(() => false);
      if (!ok) return json({ error: "SIGNATURE_INVALID" }, 401);
      let marked = 0;
      const all = await allMsgs();
      for (const id of ids) {
        const m = all.find((x) => String(x.id) === id);
        if (!m) continue;
        if (String(m.to_node) === node_id) {
          await msgs.update(m.id, { taken: true }); marked++;
        } else if (String(m.to_node) === "*") {
          let dl: string[] = [];
          try { dl = JSON.parse(String(m.delivered ?? "[]")); } catch { dl = []; }
          if (!dl.includes(node_id)) dl.push(node_id);
          await msgs.update(m.id, { delivered: JSON.stringify(dl) }); marked++;
        }
      }
      return json({ ok: true, marked });
    }

    return json({ error: "UNKNOWN_ACTION", note: "register|post|fetch|mark|info|members" }, 400);
  } catch (e) {
    return json({ error: "HUB_ERROR", detail: String(e) }, 500);
  }
});
