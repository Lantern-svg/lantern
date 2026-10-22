// random.ts — randomized concurrency acceptance runner.
// One JSON line per trial with full raw evidence. Fresh gate state per trial.
// Usage: deno run -A --quiet random.ts <sourceModule> <writers> <trials> <seed> <family:steady|fresh> [label]
import { __store } from "./sdk_mock.ts";
import { genKey, makePost, call, verify, dupSeqs, mulberry32 } from "./lib.ts";

const [mod, writersArg, trialsArg, seedArg, family, orderArg, label] = Deno.args;
const WRITERS = Number(writersArg), TRIALS = Number(trialsArg), SEED = Number(seedArg);
const OUT = `trials_${label ?? `${mod}_${family}_w${WRITERS}_s${SEED}`}.jsonl`;
const TRIAL_TIMEOUT_MS = 10000;

await import(`./${mod}.ts`);
await new Promise((r) => setTimeout(r, 300));

// source hash of the loaded board module (test copy)
const modBytes = Deno.readFileSync(`${mod}.ts`);
const sourceSha = Array.from(new Uint8Array(await crypto.subtle.digest("SHA-256", modBytes)))
  .map((b) => b.toString(16).padStart(2, "0")).join("");

async function attemptOnce(k: any, node: string, mid: string): Promise<any> {
  const v = await verify();
  const head = v.authoritative_head;
  return await makePost(k, node, mid, `payload-${mid}`, head);
}

const summary = { fork: 0, halt: 0, clean: 0, other: 0, timeouts: 0, attempted: 0, completed: 0,
  dupSeqPositions: 0, falseDesyncs: 0, inFlight: 0, missing: 0 };
const runtimes: number[] = [];
const file = await Deno.open(OUT, { write: true, create: true, truncate: true });

for (let t = 0; t < TRIALS; t++) {
  const trialSeed = SEED * 1000003 + t;
  const t0 = Date.now();
  summary.attempted++;
  // fresh gate state per trial (clear() resets collections, queue, opLog, faults)
  __store.admin.clear();
  __store.mode = "random";
  __store.rng = mulberry32(trialSeed);
  __store.filterOrder = (orderArg ?? "insertion") as "insertion" | "reverse";
  if (family === "steady") __store.admin.seedHead(1, 1, "GENESIS");

  const keys = await Promise.all(Array.from({ length: WRITERS }, () => genKey()));
  const responses: any[] = [];
  let timedOut = false;
  const trialPromise = (async () => {
    const out: any[] = [];
    await Promise.all(keys.map(async (k, i) => {
      for (let attempt = 0; attempt < 3; attempt++) {
        const r = await attemptOnce(k, `w${i}`, `t${t}-w${i}-a${attempt}`);
        out.push({ writer: i, attempt, status: r.status, error: r.body?.error ?? null });
        if (r.status === 200) break;
        if (r.status === 409 && ["POSITION_STALE", "POSITION_IN_FLIGHT"].includes(r.body?.error)) continue;
        break; // 500/403/409-other: terminal for this writer
      }
    }));
    return out;
  })();

  const watchdog = new Promise<boolean>((res) => setTimeout(() => res(true), TRIAL_TIMEOUT_MS));
  const result = await Promise.race([trialPromise.then((r) => ({ done: true, r })), watchdog.then((to) => ({ done: false, r: null, to }))]);
  if (!result.done) timedOut = true;
  const writerOutcomes = result.done ? result.r : [];
  responses.push(...writerOutcomes);

  // probe: one fresh post attempt to classify board end-state
  let probe: any = null;
  if (!timedOut) {
    const k = await genKey();
    try { probe = await attemptOnce(k, "probe", `t${t}-probe`); } catch (e) { probe = { status: -1, body: { error: String(e) } }; }
  }
  const runtime = Date.now() - t0;
  runtimes.push(runtime);

  const dup = dupSeqs();
  const seqs = __store.admin.posts().map((p: any) => Number(p.seq)).sort((a: number, b: number) => a - b);
  const v = timedOut ? null : await verify();
  const falseDesync = writerOutcomes.filter((w) => w.error === "SENTINEL_DESYNCED").length;
  const unexpected = writerOutcomes.filter((w) =>
    w.status !== 200 && w.status !== 409 && ![403].includes(w.status) && w.status !== -1 &&
    !["SENTINEL_MISSING", "SENTINEL_MULTI", "SENTINEL_DESYNCED"].includes(w.error ?? "")).length;

  let classification: string;
  if (timedOut) { classification = "other"; summary.timeouts++; }
  else if (dup.length > 0) classification = "fork";
  else if (v && (v.epochs?.some((e: any) => e.valid === false) ||
      (probe && probe.status === 500 && ["SENTINEL_MULTI", "SENTINEL_DESYNCED"].includes(probe.body?.error)))) classification = "halt";
  else if (unexpected === 0) classification = "clean";
  else classification = "other";
  summary[classification as "fork" | "halt" | "clean" | "other"]++;
  if (classification !== "other") summary.completed++;
  if (dup.length) summary.dupSeqPositions += dup.length;
  summary.falseDesyncs += falseDesync;
  summary.inFlight += writerOutcomes.filter((w) => w.error === "POSITION_IN_FLIGHT").length;
  summary.missing += writerOutcomes.filter((w) => w.error === "SENTINEL_MISSING").length;

  const record = {
    trial: t, source: mod, source_sha256: sourceSha, scenario: `random-${family}`,
    writers: WRITERS, seed: trialSeed, delayPolicy: "mock-yield-0-2-per-op (seeded)",
    classification, timeout: timedOut, runtime_ms: runtime,
    committed_seqs: seqs, dup_seqs: dup, posts: __store.admin.posts().length,
    sentinel_ids: __store.admin.heads().map((h: any) => h.id),
    sentinel_state: __store.admin.heads().map((h: any) => ({ next_seq: h.next_seq, head_hash: String(h.head_hash).slice(0, 16) })),
    cas_log: __store.casLog.map((c: any) => ({ query: c.query, updated: c.updated, targets: c.targetIds })),
    writer_outcomes: writerOutcomes,
    probe: probe ? { status: probe.status, error: probe.body?.error ?? null } : null,
    final_verify: v ? { total: v.total, epochs_valid: v.epochs?.map((e: any) => !!e.valid), head: v.authoritative_head?.slice(0, 16) } : null,
    op_trace: __store.opLog,
  };
  await file.write(new TextEncoder().encode(JSON.stringify(record) + "\n"));
}
file.close();

const sortedR = [...runtimes].sort((a, b) => a - b);
const median = sortedR[Math.floor(sortedR.length / 2)];
const rep = {
  source: mod, source_sha256: sourceSha, scenario: `random-${family}`, writers: WRITERS,
  trials_attempted: summary.attempted, trials_completed: summary.attempted - summary.timeouts,
  classification_counts: { fork: summary.fork, halt: summary.halt, clean: summary.clean, other: summary.other },
  sum_check: summary.fork + summary.halt + summary.clean + summary.other,
  timeouts: summary.timeouts, dup_seq_positions: summary.dupSeqPositions,
  false_desync_responses: summary.falseDesyncs, in_flight_responses: summary.inFlight,
  missing_responses: summary.missing,
  runtime_ms: { median, max: sortedR[sortedR.length - 1] },
  seed: SEED, trial_timeout_ms: TRIAL_TIMEOUT_MS, delay_policy: "mock-yield-0-2-per-op (seeded mulberry32)",
  reproduction: `deno run -A --quiet random.ts ${mod} ${WRITERS} ${TRIALS} ${SEED} ${family}`,
};
console.log(JSON.stringify(rep));
Deno.writeFileSync(`${OUT}.summary.json`, new TextEncoder().encode(JSON.stringify(rep, null, 1)));
Deno.exit(0);
