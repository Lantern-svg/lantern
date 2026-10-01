// Lantern relay/rendezvous v3.2 — scoped credentials + slot ownership.
//
// v3.2 (2026-09-08, B relay-boundary repair):
//   1. The shared hardcoded RELAY_TOKEN is REMOVED. Every action now
//      requires a per-node scoped relay credential: sha256(credential)
//      must match an ACTIVE RelayCredential record bound to exactly
//      one (node_id, channel). Credentials are revocable (status=revoked).
//   2. Slot ownership: creator_credential_hash is stored at call time;
//      only that credential may poll the response. respond is restricted
//      to the credential bound to the slot's channel. sender/recipient
//      metadata on respond comes from the STORED slot, never from the
//      responder's payload (anti-metadata-injection).
//   3. sender_node_id must match the credential's scope — but the
//      credential is the ONLY transport authentication. Metadata alone
//      grants nothing.
//
// TRANSPORT ONLY — the relay never grants authority. A credential is
// NOT Lantern cryptographic identity and NOT node authorization: the
// local Lantern node authenticates peers through its own mechanisms
// (Ed25519 identity PoP, sessions, authorization ledger) regardless of
// how a request arrived. Compromise of this relay must never equal
// Lantern authorization.
//
// Actions: call | next | respond | poll | info
// Legacy: the v3.1 shared token and debug action are retired. Slots
// created before v3.2 have no creator_credential_hash and are no
// longer pollable — they remain as historical records only.

const RELAY_TIMEOUT_MS = 180000;

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

let kv: any = null;

interface SlotMeta {
  sender_node_id?: string;
  recipient_node_id?: string;
  authorization_status?: string;
  message_status?: string;
}

interface Slot extends SlotMeta {
  call_id: string;
  channel: string;
  method: string;
  path: string;
  body: unknown;
  state: "pending" | "claimed" | "done" | "expired";
  created_ms: number;
  code: number;
  response: unknown;
  creator_credential_hash?: string;
  responder_credential_hash?: string;
}

async function relayBackend(req: Request): Promise<{
  backend: string;
  create: (rec: Slot) => Promise<void>;
  listPending: (channel: string) => Promise<Slot[]>;
  claim: (callId: string) => Promise<boolean>;
  saveResponse: (
    callId: string,
    code: number,
    body: unknown,
    meta: SlotMeta & { responder_credential_hash?: string },
  ) => Promise<boolean>;
  lookup: (callId: string) => Promise<Slot | null>;
  countAll: () => Promise<{ total: number; by_state: Record<string, number> }>;
}> {
  // ---- backend 1: Deno KV (shared across instances) ----
  if (kv === null) {
    try {
      kv = await (Deno as any).openKv();
    } catch {
      kv = false;
    }
  }
  if (kv) {
    const keyOf = (id: string) => ["relay", id];
    return {
      backend: "deno-kv",
      slots: null,
      async create(rec: Slot) {
        await kv.set(keyOf(rec.call_id), rec);
      },
      async listPending(channel: string) {
        const out: Slot[] = [];
        const iter = kv.list({ prefix: ["relay"] });
        for await (const entry of iter) {
          const rec: Slot = entry.value;
          if (rec.channel === channel && rec.state === "pending") out.push(rec);
        }
        out.sort((a, b) => (a.created_ms ?? 0) - (b.created_ms ?? 0));
        return out;
      },
      async claim(callId: string) {
        const entry = await kv.get(keyOf(callId));
        const rec: Slot | null = entry.value;
        if (!rec || rec.state !== "pending") return false;
        const res = await kv.atomic()
          .check(entry)
          .set(keyOf(callId), { ...rec, state: "claimed" })
          .commit();
        return res.ok === true;
      },
      async saveResponse(callId, code, body, meta) {
        const entry = await kv.get(keyOf(callId));
        const rec: Slot | null = entry.value;
        if (!rec) return false;
        const res = await kv.atomic()
          .check(entry)
          .set(keyOf(callId), {
            ...rec,
            state: "done",
            code,
            response: body,
            ...meta,
          })
          .commit();
        return res.ok === true;
      },
      async lookup(callId) {
        const entry = await kv.get(keyOf(callId));
        return entry.value ?? null;
      },
      async countAll() {
        const byState: Record<string, number> = {};
        let total = 0;
        const iter = kv.list({ prefix: ["relay"] });
        for await (const entry of iter) {
          const rec: Slot = entry.value;
          byState[rec.state] = (byState[rec.state] ?? 0) + 1;
          total += 1;
        }
        return { total: total, by_state: byState };
      },
    };
  }

  // ---- backend 2: service-role entity access ----
  const { createClientFromRequest } = await import("npm:@base44/sdk@0.8.31");
  const client: any = createClientFromRequest(req);
  const admin = client.asServiceRole ?? client;
  const slots = admin.entities.RelaySlot;
  // Empirically (debug action, 2026-09-05): slots.list() plain returns
  // ALL records; the {filter: ...} param shape returns nothing. Filter
  // in TypeScript over the plain list. Record counts in a test window
  // are small; a production relay would paginate via the entity API.
  const listAll = async (): Promise<any[]> => {
    const all = await slots.list();
    return Array.isArray(all) ? all : [];
  };
  const findByCallId = async (callId: string): Promise<any | null> => {
    const all = await listAll();
    return all.find((r: any) => r.call_id === callId) ?? null;
  };
  return {
    backend: "service-role",
    slots,
    async create(rec: Slot) {
      await slots.create(rec);
    },
    async listPending(channel: string) {
      const all = await listAll();
      return all
        .filter((r: any) => r.channel === channel && r.state === "pending")
        .sort((a: any, b: any) => (a.created_ms ?? 0) - (b.created_ms ?? 0));
    },
    async claim(callId: string) {
      const rec = await findByCallId(callId);
      if (!rec || rec.state !== "pending") return false;
      await slots.update(rec.id, { state: "claimed" });
      return true;
    },
    async saveResponse(callId, code, body, meta) {
      const rec = await findByCallId(callId);
      if (!rec) return false;
      await slots.update(rec.id, {
        state: "done",
        code,
        response: body,
        ...meta,
      });
      return true;
    },
    async lookup(callId) {
      return await findByCallId(callId);
    },
    async countAll() {
      const all = await listAll();
      const byState: Record<string, number> = {};
      for (const rec of all) {
        byState[rec.state] = (byState[rec.state] ?? 0) + 1;
      }
      return { total: all.length, by_state: byState };
    },
  };
}

Deno.serve(async (req) => {
  let payload: Record<string, unknown> = {};
  try {
    payload = await req.json();
  } catch {
    payload = {};
  }
  const action = String(payload.action ?? "");

  // ---- v3.2 gate: scoped per-node credential (replaces shared token) ----
  const credential = String(payload.credential ?? "");
  if (!credential) {
    return json({
      error: "RELAY_CREDENTIAL_REQUIRED",
      note: "transport authentication only; Lantern identity is proven at the node, never here",
    }, 403);
  }
  const credential_hash = await sha256(credential);
  let cred: { id: string; node_id: string; channel: string } | null = null;
  try {
    const { createClientFromRequest } = await import("npm:@base44/sdk@0.8.31");
    const cclient: any = createClientFromRequest(req);
    const cadmin = cclient.asServiceRole ?? cclient;
    const all = await cadmin.entities.RelayCredential.list();
    const arr = Array.isArray(all) ? all : [];
    const hit = arr.find((c: any) =>
      String(c.credential_hash ?? "") === credential_hash &&
      String(c.status ?? "active") === "active") ?? null;
    if (hit) {
      cred = {
        id: String(hit.id),
        node_id: String(hit.node_id ?? ""),
        channel: String(hit.channel ?? ""),
      };
    }
  } catch (e) {
    return json({ error: "RELAY_CREDENTIAL_BACKEND_UNAVAILABLE", detail: String(e) }, 503);
  }
  if (!cred) {
    return json({
      error: "RELAY_CREDENTIAL_INVALID",
      note: "credential unknown, revoked, or inactive — transport scope only; this is not Lantern identity and grants no node authority",
    }, 403);
  }

  let backend: Awaited<ReturnType<typeof relayBackend>>;
  try {
    backend = await relayBackend(req);
  } catch (err) {
    return json({ error: "RELAY_NO_BACKEND", detail: String(err) }, 500);
  }
  const active_backend = backend.backend;

  try {
    if (action === "info") {
      const counts = await backend.countAll();
      return json({
        ok: true,
        active_backend,
        authenticated_node: cred.node_id,
        authenticated_channel: cred.channel,
        ...counts,
      });
    }

    if (action === "call") {
      const channel = String(payload.channel ?? cred.channel);
      if (channel !== cred.channel) {
        return json({ error: "RELAY_CHANNEL_MISMATCH",
          note: "a credential may only operate on the channel it is scoped to",
          credential_channel: cred.channel }, 403);
      }
      const sender = String(payload.sender_node_id ?? cred.node_id);
      if (sender !== cred.node_id) {
        return json({ error: "RELAY_SENDER_MISMATCH",
          note: "sender_node_id is metadata; it must match the credential's scope and grants nothing on its own" }, 403);
      }
      const id = crypto.randomUUID();
      await backend.create({
        call_id: id,
        channel,
        method: String(payload.method ?? "GET"),
        path: String(payload.path ?? "/"),
        body: payload.body ?? {},
        state: "pending",
        created_ms: Date.now(),
        code: 0,
        response: {},
        sender_node_id: sender,
        recipient_node_id: String(payload.recipient_node_id ?? ""),
        creator_credential_hash: credential_hash,
      });
      return json({ ok: true, id, active_backend, authenticated_node: cred.node_id });
    }

    if (action === "next") {
      const channel = String(payload.channel ?? cred.channel);
      if (channel !== cred.channel) {
        return json({ error: "RELAY_CHANNEL_MISMATCH", credential_channel: cred.channel }, 403);
      }
      const cutoff = Date.now() - RELAY_TIMEOUT_MS;
      const stale = await backend.listPending(channel);
      for (const rec of stale) {
        if ((rec.created_ms ?? 0) < cutoff) {
          await backend.saveResponse(rec.call_id, 504, { error: "RELAY_TIMEOUT" }, {
            responder_credential_hash: credential_hash,
          });
        }
      }
      const fresh = await backend.listPending(channel);
      if (fresh.length === 0) {
        return json({ ok: true, request: null, active_backend });
      }
      const claimed = await backend.claim(fresh[0].call_id);
      if (!claimed) {
        return json({ ok: true, request: null, active_backend });
      }
      const rec = fresh[0];
      return json({
        ok: true,
        active_backend,
        request: {
          id: rec.call_id,
          method: rec.method,
          path: rec.path,
          body: rec.body,
          sender_node_id: rec.sender_node_id ?? "",
          recipient_node_id: rec.recipient_node_id ?? "",
        },
      });
    }

    if (action === "respond") {
      const id = String(payload.id ?? "");
      const rec = await backend.lookup(id);
      if (!rec) return json({ error: "RELAY_UNKNOWN_ID" }, 404);
      if (String(rec.channel ?? "") !== cred.channel) {
        return json({ error: "RELAY_SLOT_NOT_YOURS",
          note: "respond is restricted to the credential bound to the slot's channel" }, 403);
      }
      const state = String(rec.state ?? "");
      if (state !== "pending" && state !== "claimed") {
        return json({ error: "RELAY_SLOT_NOT_OPEN", state }, 409);
      }
      // Metadata comes from the STORED slot, never from the responder's
      // payload — the responder may not rewrite sender identity.
      const meta = {
        sender_node_id: String(rec.sender_node_id ?? ""),
        recipient_node_id: String(rec.recipient_node_id ?? ""),
        authorization_status: String(payload.authorization_status ?? ""),
        message_status: String(payload.message_status ?? ""),
        responder_credential_hash: credential_hash,
      };
      const ok = await backend.saveResponse(
        id,
        Number(payload.code ?? 200),
        payload.body ?? {},
        meta,
      );
      if (!ok) return json({ error: "RELAY_UNKNOWN_ID" }, 404);
      return json({ ok: true, active_backend, ...meta });
    }

    if (action === "poll") {
      const id = String(payload.id ?? "");
      const rec = await backend.lookup(id);
      if (!rec) return json({ error: "RELAY_UNKNOWN_ID" }, 404);
      if (String(rec.creator_credential_hash ?? "") !== credential_hash) {
        return json({ error: "RELAY_SLOT_NOT_YOURS",
          note: "only the credential that created this slot may read its response" }, 403);
      }
      if (rec.state === "done") {
        return json({
          ok: true,
          active_backend,
          done: true,
          request_id: rec.call_id,
          sender_node_id: rec.sender_node_id ?? "",
          recipient_node_id: rec.recipient_node_id ?? "",
          authorization_status: rec.authorization_status ?? "",
          message_status: rec.message_status ?? "",
          code: rec.code ?? 200,
          body: rec.response ?? {},
        });
      }
      return json({ ok: true, active_backend, done: false, request_id: id });
    }

    return json({ error: "RELAY_UNKNOWN_ACTION", action }, 404);
  } catch (e) {
    return json({ error: "RELAY_INTERNAL", detail: String(e) }, 500);
  }
});
