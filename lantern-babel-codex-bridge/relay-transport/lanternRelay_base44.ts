// Lantern relay/rendezvous v3.1 — layered durable backends + metadata.
//
// v1 (in-memory): failed — load-balanced instances don't share memory.
// v2 (entity store, user-scoped): blocked — anonymous traffic cannot
//   access a private app's entities.
// v3: Deno KV (shared across instances) -> service-role entities.
// v3.1: every response exposes the relay evidence fields:
//   active_backend, request_id, sender_node_id, recipient_node_id,
//   authorization_status, message_status.
//
// Transport ONLY — the relay never grants authority. The
// authorization_status / message_status fields are PASSTHROUGH
// metadata written by the Local tunnel FROM the Lantern node's own
// responses. All authentication/authorization is the Lantern
// protocol's, end-to-end (Ed25519 identity PoP, sessions,
// authorization ledger). SYNTHETIC TEST credential only.
//
// Actions: call | next | respond | poll | info

const RELAY_TOKEN = "lantern-relay-test-2026-09-05";
const RELAY_TIMEOUT_MS = 180000;

function json(data: unknown, status = 200): Response {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "content-type": "application/json" },
  });
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
    meta: SlotMeta,
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
        return { total, by_state: byState };
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
  if (payload.token !== RELAY_TOKEN) {
    return json({ error: "RELAY_TOKEN_INVALID" }, 403);
  }

  let backend: Awaited<ReturnType<typeof relayBackend>>;
  try {
    backend = await relayBackend(req);
  } catch (err) {
    return json({ error: "RELAY_NO_BACKEND", detail: String(err) }, 500);
  }
  const active_backend = backend.backend;
  const rawSlots: any = (backend as any).slots ?? null;

  try {
    if (action === "debug") {
      const stamp = Date.now();
      let createdReturn: any = null;
      try {
        createdReturn = await rawSlots.create({
          call_id: "debug-" + stamp,
          channel: "debug",
          method: "GET",
          path: "/debug",
          body: { stamp },
          state: "pending",
          created_ms: stamp,
          code: 0,
          response: {},
          sender_node_id: "",
          recipient_node_id: "",
        });
      } catch (e) {
        createdReturn = "ERR:" + String(e);
      }
      const out: Record<string, unknown> = {
        active_backend,
        created_returns: createdReturn,
      };
      try {
        const r = await rawSlots.list();
        out.list_plain = Array.isArray(r) ? r.length : String(r);
      } catch (e) {
        out.list_plain = "ERR:" + String(e);
      }
      try {
        const r = await rawSlots.list({ filter: { channel: "debug" } });
        out.list_filter_channel = Array.isArray(r) ? r.length : String(r);
      } catch (e) {
        out.list_filter_channel = "ERR:" + String(e);
      }
      try {
        const r = await rawSlots.list({ channel: "debug" });
        out.list_direct_channel = Array.isArray(r) ? r.length : String(r);
      } catch (e) {
        out.list_direct_channel = "ERR:" + String(e);
      }
      if (createdReturn && createdReturn.id) {
        try {
          out.get_by_id = await rawSlots.get(createdReturn.id);
        } catch (e) {
          out.get_by_id = "ERR:" + String(e);
        }
      }
      return json(out);
    }

    if (action === "info") {
      const counts = await backend.countAll();
      return json({ ok: true, active_backend, ...counts });
    }

    if (action === "call") {
      const id = crypto.randomUUID();
      await backend.create({
        call_id: id,
        channel: String(payload.channel ?? "main"),
        method: String(payload.method ?? "GET"),
        path: String(payload.path ?? "/"),
        body: payload.body ?? {},
        state: "pending",
        created_ms: Date.now(),
        code: 0,
        response: {},
        sender_node_id: String(payload.sender_node_id ?? ""),
        recipient_node_id: String(payload.recipient_node_id ?? ""),
      });
      return json({ ok: true, id, active_backend });
    }

    if (action === "next") {
      const channel = String(payload.channel ?? "main");
      const cutoff = Date.now() - RELAY_TIMEOUT_MS;
      const stale = await backend.listPending(channel);
      for (const rec of stale) {
        if ((rec.created_ms ?? 0) < cutoff) {
          await backend.saveResponse(rec.call_id, 504, { error: "RELAY_TIMEOUT" }, {});
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
      const meta: SlotMeta = {
        sender_node_id: String(payload.sender_node_id ?? ""),
        recipient_node_id: String(payload.recipient_node_id ?? ""),
        authorization_status: String(payload.authorization_status ?? ""),
        message_status: String(payload.message_status ?? ""),
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

    return json({ error: "RELAY_UNKNOWN_ACTION" }, 400);
  } catch (err) {
    return json(
      { error: "RELAY_BACKEND_ERROR", active_backend, detail: String(err) },
      500,
    );
  }
});
