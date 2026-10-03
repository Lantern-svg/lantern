#!/usr/bin/env python3
"""lantern_net_http.py — HTTP transport variant of lantern_net for the lanternNetHub.

  python3 lantern_net_http.py worker --key key_t1.json --ledger t1.jsonl
  python3 lantern_net_http.py submit --key key_sbx.json --ledger sbx.jsonl --fn collatz_steps --input 27

Same identity, envelope, ledger, and confirmation protocol as lantern_net.py
(imported, not copied): Ed25519 over DOMAIN lantern-net/v1/, fail-closed
allowlist, replay nonces, hash-chained local ledgers, producer + independent
recompute confirmation. Transport is signed HTTP POST to the Base44 hub
instead of raw TLS to the VPS hub — Phase 1 showed the VPS has no working
inbound, while the function host is verified HTTPS inbound.

Keygen/verify: use lantern_net.py (python3 lantern_net.py keygen --id X / verify ledger.jsonl).
Needs Python 3.9+ and PyNaCl (same as lantern_net)."""
import argparse, asyncio, json, secrets, sys, time, urllib.request
from lantern_net import (DOMAIN, env_bytes, fingerprint, sign_env, Ledger, FUNCS,
                         result_hash, _sign, Node, TS_WINDOW)

HUB = "https://zelle-4457b476.base44.app/functions/lanternNetHub"
UA = "lantern-net/1.0"
POLL_S = 4

def call(body, timeout=20):
    req = urllib.request.Request(HUB, data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json", "User-Agent": UA}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        try: return json.loads(e.read())
        except Exception: return {"error": f"HTTP_{e.code}"}
    except Exception as e:
        return {"error": f"TRANSPORT: {type(e).__name__}"}

def reg_bytes(ts_ms, node_id, room):
    return DOMAIN + "register\x00".encode() + f"{ts_ms}|{node_id}|{room}".encode()

def req_bytes(act, ts_ms, node_id, extra=""):
    return DOMAIN + "req\x00".encode() + f"{act}\x00{ts_ms}|{node_id}{extra}".encode()

class HttpNode(Node):
    """Node with the proven lantern_net protocol core; transport overridden."""
    async def connect(self):
        a = self.a
        self.members = []
        r = self._register()
        if not r.get("ok"):
            raise SystemExit(f"hub rejected registration: {r}")
        self.members = r.get("members", [])
        print(f"[{self.id['node_id']}] registered fp={self.fp} room={a.room} members={self.members}", flush=True)

    def _register(self):
        ts = int(time.time() * 1000)
        sig = _sign(self.id["seed"], reg_bytes(ts, self.id["node_id"], self.a.room))
        return call({"action": "register", "node_id": self.id["node_id"], "pub": self.id["pub"],
                     "room": self.a.room, "ts_ms": ts, "sig": sig})

    async def raw(self, obj):  # transport is per-call in HTTP mode
        pass

    async def send(self, to, typ, payload):
        env = {"from": self.id["node_id"], "to": to, "room": self.a.room, "type": typ,
               "ts": time.time(), "nonce": secrets.token_hex(12), "payload": payload}
        canon_hex = env_bytes(env).hex()          # canonical bytes of the UNSIGNED env
        sign_env(self.id["seed"], env)            # adds "sig"
        for attempt in range(6):                 # retry: a lost WORK_UNIT/RESULT starves the run
            r = call({"action": "post", "env": env, "canon_hex": canon_hex})
            if r.get("ok"): break
            if attempt == 5: print(f"post {typ} FAILED after retries: {r}", flush=True)
            await asyncio.sleep(2 * (attempt + 1))   # backoff, also rides out rate limits
        return env

    async def heartbeat(self):  # presence refresh
        while True:
            await asyncio.sleep(120)
            r = self._register()
            if r.get("ok"): self.members = r.get("members", self.members)

    async def recv_loop(self):
        while True:
            ts = int(time.time() * 1000)
            sig = _sign(self.id["seed"], req_bytes("fetch", ts, self.id["node_id"]))
            r = call({"action": "fetch", "node_id": self.id["node_id"], "room": self.a.room, "ts_ms": ts, "sig": sig})
            if "Rate limit" in str(r.get("detail", "")): await asyncio.sleep(10)
            if r.get("ok") and r.get("envelopes"):
                ids = []
                for item in r["envelopes"]:
                    env = dict(item["env"], sig=item["sig"])
                    try: await self.on_env(env)
                    finally: ids.append(item["id"])
                mts = int(time.time() * 1000)
                msig = _sign(self.id["seed"], req_bytes("mark", mts, self.id["node_id"], "|" + ",".join(ids)))
                call({"action": "mark", "node_id": self.id["node_id"], "ids": ids, "ts_ms": mts, "sig": msig})
            await asyncio.sleep(POLL_S)

    async def submit(self):
        a, loop = self.a, asyncio.get_running_loop()
        deadline = time.time() + a.timeout
        while time.time() < deadline:              # wait until another member is live
            r = self._register()
            if r.get("ok"): self.members = r.get("members", [])
            if len([m for m in self.members if m != self.id["node_id"]]) >= 1: break
            await asyncio.sleep(2)
        else: raise SystemExit("no other node joined the room before the timeout")
        inp = json.loads(a.input)
        unit = {"unit_id": secrets.token_hex(8), "room": a.room, "spec": {"fn": a.fn}, "input": inp,
                "deadline": time.time() + a.timeout}
        FUNCS[a.fn](inp)                           # reject bad input before sending
        self.units_sent[unit["unit_id"]] = unit
        self.done_fut = loop.create_future()
        self.ledger.append({"event": "UNIT", "unit_id": unit["unit_id"], "fn": a.fn, "requester": self.fp})
        await self.send("*", "WORK_UNIT", unit)
        print(f"submitted unit {unit['unit_id']} fn={a.fn}", flush=True)
        await asyncio.wait_for(self.done_fut, a.timeout)

async def cmd_node(a):
    n = HttpNode(a)
    if getattr(a, "allow_hub", False):
        # Opt-in federation: merge hub-registered member pubs into the local
        # allowlist. Local file entries ALWAYS win (node sovereignty); hub list
        # is convenience, not authority. Every envelope is still sig-checked.
        try:
            r = call({"action": "members"})
            merged = 0
            for nid, pub in (r.get("members") or {}).items():
                if nid not in n.allow and pub:
                    n.allow[nid] = pub; merged += 1
            print(f"[{a.key}] allow-hub: {merged} member key(s) merged (local file wins)", flush=True)
        except Exception as e:
            print(f"[{a.key}] allow-hub unavailable ({e}); continuing with local allowlist", flush=True)
    await n.connect()
    tasks = [asyncio.create_task(n.heartbeat()), asyncio.create_task(n.recv_loop())]
    try:
        if a.cmd == "submit":
            await n.submit(); print("OK: unit confirmed"); return
        await asyncio.gather(*tasks)
    except asyncio.TimeoutError:
        print("TIMEOUT: unit not confirmed"); sys.exit(1)
    finally:
        for t in tasks: t.cancel()

def main():
    ap = argparse.ArgumentParser(description="lantern-net HTTP client for lanternNetHub")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("worker", "submit"):
        p = sub.add_parser(name); p.add_argument("--key", required=True)
        p.add_argument("--room", default="lab"); p.add_argument("--allow", default="allowed_keys.json")
        p.add_argument("--ledger", default="ledger.jsonl")
        p.add_argument("--fn", default="sha256", choices=sorted(FUNCS))
        p.add_argument("--input", default='"hello lantern"')
        p.add_argument("--timeout", type=float, default=120)
        p.add_argument("--allow-hub", action="store_true",
                       help="opt-in: merge hub member keys into local allowlist (local file wins)")
    a = ap.parse_args(); a.mode = a.cmd
    asyncio.run(cmd_node(a))

if __name__ == "__main__":
    main()
