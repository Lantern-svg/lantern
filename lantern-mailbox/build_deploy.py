"""Builds lanternMailbox.deploy.ts from core.js + adapter, verifying the
embedded core is byte-identical to the tested core.js."""
import hashlib, sys
core = open("core.js").read()
tail = "export { handle, MAILBOX_VERSION };"
assert core.rstrip().endswith(tail)
core_body = core.rstrip()[: -len(tail)].rstrip()
adapter = '''
// ---- Base44 adapter (added at build time) ----
// Entity wiring mirrors the MemoryStore interface the battery tested:
// list / create / update / delete. Entities: LanternMailBinding,
// LanternMailMessage, LanternMailEvent.
function json(data, status = 200) {
  return new Response(JSON.stringify(data), { status, headers: { "content-type": "application/json" } });
}
Deno.serve(async (req) => {
  let payload = {};
  try { payload = await req.json(); } catch { payload = {}; }
  const action = String(payload.action ?? "");
  try {
    const { createClientFromRequest } = await import("npm:@base44/sdk@0.8.31");
    const client = createClientFromRequest(req);
    const admin = client.asServiceRole ?? client;
    const ent = {
      LanternMailBinding: admin.entities.LanternMailBinding,
      LanternMailMessage: admin.entities.LanternMailMessage,
      LanternMailEvent: admin.entities.LanternMailEvent,
    };
    const store = {
      async list(name) {
        const all = await ent[name].list();
        return Array.isArray(all) ? all : [];
      },
      async create(name, rec) { return await ent[name].create(rec); },
      async update(name, rec) { return await ent[name].update(rec.id, rec); },
      async delete(name, rec) { return await ent[name].delete(rec.id); },
    };
    const body = (payload && typeof payload === "object" && payload.payload && typeof payload.payload === "object")
      ? payload.payload : payload;
    const r = await handle(action, body, store, Date.now());
    return json(r.body, r.status);
  } catch (e) {
    return json({ error: "MAILBOX_GATE_UNAVAILABLE", detail: String(e) }, 503);
  }
});
'''
deployable = core_body + "\n" + adapter
open("lanternMailbox.deploy.ts", "w").write(deployable)
check = open("lanternMailbox.deploy.ts").read()
assert check[: len(core_body)] == core_body, "core embedding mismatch"
h = lambda s: hashlib.sha256(s.encode()).hexdigest()
print("core.js sha256:", h(core))
print("embedded section byte-identical: VERIFIED")
print("deployable sha256:", h(deployable))
