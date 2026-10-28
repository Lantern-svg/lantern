// run_f1.ts — run one F1 schedule against one loaded source; write trace.
// Usage: deno run -A --quiet run_f1.ts <sourceModule> <schedule(a|b)> <order> <outPrefix>
import { __store } from "./sdk_mock.ts";
import { runStaggeredAutoInit, runStaleVsMoved } from "./f1.ts";
const [mod, sched, order, out] = [Deno.args[0], Deno.args[1], Deno.args[2] as any, Deno.args[3] ?? "f1"];
await import(`./${mod}.ts`);
await new Promise((r) => setTimeout(r, 300));
setTimeout(() => { console.error("WATCHDOG after 25s: pending=[" + __store.gate.queue.map((e) => e.name).join(",") + "] heads=" + __store.admin.heads().length); Deno.exit(9); }, 25000);
const res = sched === "a" ? await runStaggeredAutoInit(order) : await runStaleVsMoved(order);
Deno.writeFileSync(`${out}.txt`, new TextEncoder().encode(
  `source=${mod} schedule=${sched} order=${order}\n` + res.trace.join("\n")));
console.log(JSON.stringify({ source: mod, sched, order, verdict: res.verdict,
  a: res.aStatus + (res.aError ? "/" + res.aError : ""), b: res.bStatus + (res.bError ? "/" + res.bError : ""),
  dup: res.dup, heads: res.heads, posts: res.posts.length }));
Deno.exit(0);
