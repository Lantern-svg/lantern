import { __store } from "./sdk_mock.ts";
export function releaseOne(): void {
  const r = __store.gate.queue.shift();
  if (r) r();
}
export async function settle(): Promise<void> { await new Promise((r) => setTimeout(r, 5)); }
// advance a specific request by resolving the NEXT gate op while asserting
// which op it was (opLog tail), so schedules are exact and fail loudly.
export async function step(expect?: string): Promise<void> {
  await settle();
  const pending = __store.gate.queue.length;
  if (pending === 0) return;
  releaseOne();
  await settle();
}
