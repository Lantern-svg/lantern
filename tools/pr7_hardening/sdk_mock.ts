// In-memory mock of the Base44 SDK surface used by lanternBoard_base44.ts.
// - ATOMIC (default) updateMany: all matching docs updated in one synchronous
//   step, exact updated counts (probe-corroborated provider model).
// - nonAtomic switch: check-then-act per doc with a yield between match and
//   write, to show what breaks if the provider assumption fails.
// - Scripted mode: EVERY storage op awaits a driver-controlled gate
//   (deterministic fixed schedules). Random mode: seeded event-loop yields.
// - failNext: inject a one-shot fault at a specific entity op (crash points).
// Fully local; no network, no provider, no persistent state.

export function createClientFromRequest(_req: unknown): any {
  return { asServiceRole: { entities: {
    LanternPost: entity("LanternPost"),
    LanternBinding: entity("LanternBinding"),
    LanternBoardHead: entity("LanternBoardHead"),
  } } };
}

export const __store = {
  collections: { LanternPost: [], LanternBinding: [], LanternBoardHead: [] } as Record<string, any[]>,
  mode: "random" as "random" | "scripted",
  rng: Math.random,
  nonAtomic: false, paginated: false,
  filterOrder: "insertion" as "insertion" | "reverse", // real Base44 order UNKNOWN
  gate: { queue: [] as Array<{ name: string; resolve: (v?: any) => void; gid: number }>, released: 0,
    seq: 0 },
  failNext: null as null | { entity: string; op: string },
  opLog: [] as string[],
  casLog: [] as any[],   // every updateMany: query, $set, matched, updated, nonAtomic
  admin: {
    heads(): any[] { return __store.collections.LanternBoardHead; },
    posts(): any[] { return __store.collections.LanternPost; },
    bindings(): any[] { return __store.collections.LanternBinding; },
    clear() {
      __store.collections = { LanternPost: [], LanternBinding: [], LanternBoardHead: [] };
      __store.gate.queue = []; __store.gate.released = 0;
      __store.failNext = null; __store.opLog = []; __store.nonAtomic = false; __store.casLog = [];
      __store.paginated = false;
    },
    seedHead(epoch = 1, next_seq = 1, head_hash = "GENESIS") {
      __store.collections.LanternBoardHead.push({ id: "h-seed", board: "lantern-board",
        epoch, next_seq, head_hash, last_post_id: null, updated_ms: 0 });
    },
  },
};

let idCounter = 0;
function newId(): string { return `id-${(++idCounter).toString().padStart(6, "0")}`; }

async function gate(name: string): Promise<void> {
  __store.opLog.push(name);
  if (__store.mode === "scripted") {
    await new Promise<void>((resolve) => { __store.gate.queue.push({ name, resolve, gid: ++__store.gate.seq }); });
    // NOTE: release accounting lives ONLY in the driver (lib.ts releaseAt),
    // single increment per release.
  } else {
    const n = Math.floor(__store.rng() * 3); // 0..2 macrotask yields
    for (let i = 0; i < n; i++) await new Promise((r) => setTimeout(r, 0));
  }
}

function maybeFail(entity: string, op: string) {
  const f = __store.failNext;
  if (f && f.entity === entity && f.op === op) { __store.failNext = null; throw new Error("INJECTED_FAULT"); }
}

function matches(doc: any, q: any): boolean {
  for (const k of Object.keys(q)) if (String(doc[k]) !== String(q[k])) return false;
  return true;
}

function entity(name: string): any {
  const col = () => __store.collections[name];
  return {
    async list(params?: any) {
      maybeFail(name, "list"); await gate(`${name}.list`);
      let out = JSON.parse(JSON.stringify(col()));
      // broken/real provider model: list caps at 50 records per call; the
      // client must paginate with skip. Non-paginated mode returns everything
      // (documented; existing scenario semantics preserved).
      if (__store.paginated) { const s = Number((params as any)?.skip ?? 0); out = out.slice(s, s + 50); }
      return out;
    },
    async filter(q: any) {
      maybeFail(name, "filter"); await gate(`${name}.filter`);
      const { skip, ...qq } = q ?? {};
      let out = col().filter((d: any) => matches(d, qq));
      if (name === "LanternBoardHead" && __store.filterOrder === "reverse") out = [...out].reverse();
      if (__store.paginated) { const s = Number(skip ?? 0); out = out.slice(s, s + 50); }
      return JSON.parse(JSON.stringify(out));
    },
    async create(d: any) {
      maybeFail(name, "create"); await gate(`${name}.create`);
      const rec: any = { id: newId(), created_date: new Date().toISOString(), ...JSON.parse(JSON.stringify(d)) };
      col().push(rec); return rec;
    },
    async update(id: string, d: any) {
      maybeFail(name, "update"); await gate(`${name}.update`);
      const rec = col().find((r: any) => r.id === id);
      if (rec) Object.assign(rec, JSON.parse(JSON.stringify(d)));
      return { success: !!rec };
    },
    async updateMany(q: any, mod: any) {
      maybeFail(name, "updateMany"); await gate(`${name}.updateMany`);
      if (__store.nonAtomic) {
        let updated = 0;
        for (const doc of [...col()]) {
          if (matches(doc, q)) {
            await new Promise((r) => setTimeout(r, 0)); // broken-provider race window
            // NO recheck: classic lost-update model (non-atomic provider)
            Object.assign(doc, mod.$set); updated++;
          }
        }
        __store.casLog.push({ entity: name, query: q, set: mod.$set, matched: -1, updated, nonAtomic: true });
        return { success: true, updated };
      }
      const matched = col().filter((d: any) => matches(d, q));
      for (const doc of matched) Object.assign(doc, mod.$set);
      __store.casLog.push({ entity: name, query: q, set: mod.$set, matched: matched.length,
        updated: matched.length, targetIds: matched.map((d: any) => d.id), nonAtomic: false });
      return { success: true, updated: matched.length };
    },
  };
}
