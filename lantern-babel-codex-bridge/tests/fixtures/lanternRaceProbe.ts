// lanternRaceProbe — ISOLATED test fixture for the Lantern atomic-append
// investigation. Operates ONLY on the scratch entity LanternRaceProbe.
// Never touches LanternPost / LanternBinding / the public board.
// Actions:
//   setup     — reset scratch records, create sentinel {slot:1, head:GENESIS}
//   cas       — atomicity probe: updateMany({kind:sentinel, slot:expected}, {$set:{slot+1,...}})
//   appendOld — deployed v2.0.5 logic shape (read -> compute seq -> create), the race
//   appendNew — sentinel-CAS logic (CAS the slot first; create only on success)
//   read      — list scratch records

const json = (o: any, s = 200) => new Response(JSON.stringify(o), { status: s, headers: { "Content-Type": "application/json" } });

Deno.serve(async (req) => {
  let payload: any = {};
  try { payload = await req.json(); } catch { payload = {}; }
  const action = String(payload.action ?? "");
  try {
    const { createClientFromRequest } = await import("npm:@base44/sdk@0.8.31");
    const client: any = createClientFromRequest(req);
    const admin = client.asServiceRole ?? client;
    const recs = admin.entities.LanternRaceProbe;

    if (action === "setup") {
      await recs.deleteMany({ kind: "sentinel" });
      await recs.deleteMany({ kind: "post" });
      const r = await recs.create({ kind: "sentinel", board: "probe", slot: 1, head: "GENESIS", owner: null });
      return json({ ok: true, sentinel: r });
    }

    if (action === "cas") {
      const expected = Number(payload.expected_slot ?? 0);
      const racer = String(payload.racer ?? "?");
      const newHead = String(payload.new_head ?? "H");
      const res = await recs.updateMany({ kind: "sentinel", slot: expected },
        { $set: { slot: expected + 1, head: newHead, owner: racer } });
      return json({ ok: true, racer, expected, response: res });
    }

    if (action === "appendOld") {
      const racer = String(payload.racer ?? "?");
      const all = await recs.filter({ kind: "post" });
      const posts = Array.isArray(all) ? all : [];
      const seq = posts.length + 1;
      const r = await recs.create({ kind: "post", board: "probe", seq, racer });
      return json({ ok: true, racer, seq, id: r.id });
    }

    if (action === "appendNew") {
      const racer = String(payload.racer ?? "?");
      const sent = await recs.filter({ kind: "sentinel" });
      const s = (Array.isArray(sent) ? sent : [])[0];
      if (!s) return json({ error: "NO_SENTINEL" }, 409);
      const res = await recs.updateMany({ kind: "sentinel", slot: s.slot },
        { $set: { slot: (s.slot ?? 0) + 1, head: racer + ":" + s.slot, owner: racer } });
      const modified = (res as any)?.updated ?? (res as any)?.modified ?? (res as any)?.modifiedCount ?? (res as any)?.n ?? 0;
      if (Number(modified) === 0) return json({ ok: false, error: "POSITION_TAKEN", racer, slot: s.slot }, 409);
      const r = await recs.create({ kind: "post", board: "probe", seq: s.slot, racer, owner: racer });
      return json({ ok: true, racer, seq: s.slot, id: r.id });
    }

    if (action === "read") {
      const all = await recs.list();
      return json({ ok: true, records: all });
    }

    return json({ error: "UNKNOWN_ACTION" }, 400);
  } catch (e) {
    return json({ error: "PROBE_ERROR", detail: String(e) }, 500);
  }
});
