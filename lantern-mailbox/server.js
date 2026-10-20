// Local test bridge: runs the EXACT core handler (the same file embedded in
// the deployable function) against an in-memory store, over a local TCP
// JSON-lines protocol so each participant is a genuinely separate process.
// Honest label: local process, in-memory storage adapter, loopback TCP,
// NOT the deployed Base44 service, single operator sandbox.
import net from "node:net";
import { handle } from "./core.js";

const entities = new Map();
class MemoryStore {
  list(name) { return Promise.resolve([...(entities.get(name) ?? [])]); }
  create(name, rec) {
    const arr = entities.get(name) ?? [];
    const with_id = { id: `rec-${arr.length + 1}-${Math.random().toString(16).slice(2, 8)}`, ...rec };
    arr.push(with_id); entities.set(name, arr); return Promise.resolve(with_id);
  }
  update(name, rec) {
    const arr = entities.get(name) ?? [];
    const i = arr.findIndex((r) => r.id === rec.id);
    if (i === -1) throw new Error("record not found");
    arr[i] = { ...rec }; entities.set(name, arr); return Promise.resolve(arr[i]);
  }
  delete(name, rec) {
    const arr = entities.get(name) ?? [];
    const i = arr.findIndex((r) => r.id === rec.id);
    if (i !== -1) arr.splice(i, 1);
    entities.set(name, arr); return Promise.resolve(true);
  }
}
const store = new MemoryStore();
let buf = "";

const server = net.createServer((sock) => {
  sock.on("data", async (data) => {
    buf += data.toString();
    let idx;
    while ((idx = buf.indexOf("\n")) !== -1) {
      const line = buf.slice(0, idx).trim(); buf = buf.slice(idx + 1);
      if (!line) continue;
      let req; try { req = JSON.parse(line); } catch { continue; }
      const { id, action, payload = {}, now_ms } = req;
      try {
        if (action === "__dump__") {
          const dump = {};
          for (const [k, v] of entities) dump[k] = v.map((r) => ({ ...r }));
          sock.write(JSON.stringify({ id, status: 200, body: { ok: true, entities: dump } }) + "\n");
          continue;
        }
        const r = await handle(action, payload, store, now_ms);
        sock.write(JSON.stringify({ id, status: r.status, body: r.body }) + "\n");
      } catch (e) {
        sock.write(JSON.stringify({ id, status: 500, body: { error: "BRIDGE_CRASH", detail: String(e) } }) + "\n");
      }
    }
  });
});
const PORT = Number(process.env.MAILBOX_BRIDGE_PORT ?? 47631);
server.listen(PORT, "127.0.0.1", () => {
  process.stderr.write(`mailbox bridge listening on 127.0.0.1:${PORT}\n`);
});
