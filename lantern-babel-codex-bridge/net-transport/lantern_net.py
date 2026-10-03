#!/usr/bin/env python3
"""lantern_net.py - one-file close network: hub (rendezvous + relay), worker, submitter, keygen.

  python3 lantern_net.py keygen --id gw          # identity; prints an allowlist line
  python3 lantern_net.py cert --ip 1.2.3.4       # self-signed hub cert + prints the --pin (needs openssl)
  python3 lantern_net.py hub --cert hub.crt --key hub.key [--port 443]
  python3 lantern_net.py worker --key key_sbx.json --hub 1.2.3.4:443 --pin <sha256>
  python3 lantern_net.py submit --key key_gw.json --hub 1.2.3.4:443 --pin <sha256> --fn collatz_steps --input 27
  python3 lantern_net.py verify ledger.jsonl     # check a ledger's hash chain
  python3 lantern_net.py selftest                # full local round trip + attack checks (needs openssl)

Needs Python 3.9+ and PyNaCl (pip install pynacl); falls back to `cryptography` if PyNaCl is absent.
Fail-closed: only (node_id, pubkey) pairs in allowed_keys.json can join. Work units are data-only.
Known limits: different keys, not different operators; payloads are signed, not encrypted; the hub is a
single point of failure and sees metadata; results go to a local ledger (no Lantern-wall posting); no UDP."""
import argparse, asyncio, hashlib, json, os, re, secrets, shutil, ssl, subprocess, sys, tempfile, time

DOMAIN = b"lantern-net/v1/"          # keeps board signatures from replaying here
MAX_LINE = 64 * 1024
ID_RE = re.compile(r"^[a-z0-9_-]{1,32}$")
TYPE_RE = re.compile(r"^[A-Z_]{1,24}$")

try:  # preferred: PyNaCl (what the design specifies)
    from nacl.signing import SigningKey, VerifyKey
    from nacl.exceptions import BadSignatureError
    BACKEND = "pynacl"
    def gen_seed(): return SigningKey.generate().encode().hex()
    def pub_of(seed): return SigningKey(bytes.fromhex(seed)).verify_key.encode().hex()
    def _sign(seed, msg): return SigningKey(bytes.fromhex(seed)).sign(msg).signature.hex()
    def _verify(pub, msg, sig):
        try:
            VerifyKey(bytes.fromhex(pub)).verify(msg, bytes.fromhex(sig)); return True
        except (BadSignatureError, ValueError): return False
except ImportError:  # fallback: same Ed25519, same signatures, interoperable
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
    from cryptography.hazmat.primitives import serialization as _s
    from cryptography.exceptions import InvalidSignature
    BACKEND = "cryptography"
    def gen_seed():
        return Ed25519PrivateKey.generate().private_bytes(
            _s.Encoding.Raw, _s.PrivateFormat.Raw, _s.NoEncryption()).hex()
    def pub_of(seed):
        return Ed25519PrivateKey.from_private_bytes(bytes.fromhex(seed)).public_key().public_bytes(
            _s.Encoding.Raw, _s.PublicFormat.Raw).hex()
    def _sign(seed, msg): return Ed25519PrivateKey.from_private_bytes(bytes.fromhex(seed)).sign(msg).hex()
    def _verify(pub, msg, sig):
        try:
            Ed25519PublicKey.from_public_bytes(bytes.fromhex(pub)).verify(bytes.fromhex(sig), msg); return True
        except (InvalidSignature, ValueError): return False

def canon(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()

def sha256hex(data):
    return hashlib.sha256(data if isinstance(data, bytes) else data.encode()).hexdigest()

def fingerprint(pub_hex):
    return sha256hex(bytes.fromhex(pub_hex))[:16]

def reg_bytes(nonce_hex, node_id):
    return DOMAIN + b"register\x00" + bytes.fromhex(nonce_hex) + node_id.encode()

def env_bytes(env):
    return DOMAIN + b"env\x00" + canon({k: v for k, v in env.items() if k != "sig"})

def sign_env(seed, env):
    env["sig"] = _sign(seed, env_bytes(env)); return env

def verify_env(pub, env):
    sig = env.get("sig")
    return isinstance(sig, str) and _verify(pub, env_bytes(env), sig)

def sign_register(seed, nonce_hex, node_id): return _sign(seed, reg_bytes(nonce_hex, node_id))
def verify_register(pub, nonce_hex, node_id, sig): return _verify(pub, reg_bytes(nonce_hex, node_id), sig)

def load_allowlist(path):
    """{node_id: pubkey_hex}. Anything malformed is dropped (fail closed)."""
    with open(path) as f: raw = json.load(f)
    out = {}
    for nid, pub in raw.items():
        try:
            if ID_RE.match(nid) and len(bytes.fromhex(pub)) == 32: out[nid] = pub.lower()
        except (ValueError, TypeError, AttributeError): pass
    return out

class Ledger:
    """Append-only, hash-chained JSONL. hash = sha256(prev + canon(entry))."""
    def __init__(self, path):
        self.path, self.prev = path, "0" * 64
        if os.path.exists(path):
            ok, _, last = Ledger.verify(path)
            if not ok: raise SystemExit(f"ledger {path} fails chain verification; refusing to append")
            self.prev = last
    def append(self, entry):
        h = sha256hex(self.prev + canon(entry).decode())
        with open(self.path, "a") as f:
            f.write(json.dumps({"prev": self.prev, "entry": entry, "hash": h}, sort_keys=True) + "\n")
        self.prev = h; return h
    @staticmethod
    def verify(path):
        prev, n = "0" * 64, 0
        with open(path) as f:
            for line in f:
                r = json.loads(line)
                if r["prev"] != prev or r["hash"] != sha256hex(prev + canon(r["entry"]).decode()):
                    return False, n, prev
                prev, n = r["hash"], n + 1
        return True, n, prev

# ===================== HUB =====================
HEARTBEAT_TIMEOUT, TS_WINDOW = 90, 60
BUCKET_CAP, BUCKET_RATE, MAX_STRIKES = 40, 20.0, 10

class Client:
    def __init__(self, reader, writer):
        self.r, self.w, self.node_id, self.pub = reader, writer, None, None
        self.tokens, self.t_last, self.strikes = float(BUCKET_CAP), time.monotonic(), 0
    def take(self):
        now = time.monotonic()
        self.tokens = min(BUCKET_CAP, self.tokens + (now - self.t_last) * BUCKET_RATE); self.t_last = now
        if self.tokens < 1: return False
        self.tokens -= 1; return True

class Hub:
    def __init__(self, allow_path, log_path):
        self.allow_path, self.log_path = allow_path, log_path
        self.allow, self.allow_mtime = {}, 0.0
        self.clients, self.rooms, self.seen = {}, {}, {}
    def log(self, node, op, ok, why="", size=0):
        rec = {"t": round(time.time(), 3), "node": node, "op": op, "ok": ok, "why": why, "bytes": size}
        with open(self.log_path, "a") as f: f.write(json.dumps(rec) + "\n")
        print(rec, flush=True)
    def refresh_allow(self):
        m = os.path.getmtime(self.allow_path)
        if m != self.allow_mtime: self.allow, self.allow_mtime = load_allowlist(self.allow_path), m
    async def send(self, c, obj):
        try:
            c.w.write((json.dumps(obj, separators=(",", ":")) + "\n").encode())
            await asyncio.wait_for(c.w.drain(), 5); return True
        except Exception: return False
    def drop(self, c):
        if c.node_id and self.clients.get(c.node_id) is c:
            del self.clients[c.node_id]
            for room in list(self.rooms):
                self.rooms[room].discard(c.node_id)
                if not self.rooms[room]: del self.rooms[room]
        try: c.w.close()
        except Exception: pass
    async def readobj(self, c, timeout):
        line = await asyncio.wait_for(c.r.readline(), timeout)
        if not line: raise ConnectionError("closed")
        obj = json.loads(line)
        if not isinstance(obj, dict): raise ValueError("not an object")
        return obj, len(line)

    async def handle(self, reader, writer):
        c = Client(reader, writer)
        try:
            nonce = secrets.token_hex(16)
            await self.send(c, {"op": "CHALLENGE", "nonce": nonce})
            msg, n = await self.readobj(c, 10)
            nid, pub, sig = msg.get("node_id"), msg.get("pub"), msg.get("sig")
            self.refresh_allow()
            if (msg.get("op") != "REGISTER" or not isinstance(nid, str) or not isinstance(pub, str)
                    or not isinstance(sig, str) or self.allow.get(nid) != pub.lower()
                    or not verify_register(pub.lower(), nonce, nid, sig)):
                self.log(nid if isinstance(nid, str) else "?", "REGISTER", False, "rejected", n)
                await self.send(c, {"op": "REJECT", "reason": "registration"}); return
            old = self.clients.get(nid)
            if old: self.drop(old)
            c.node_id, c.pub = nid, pub.lower(); self.clients[nid] = c
            self.log(nid, "REGISTER", True, fingerprint(c.pub), n)
            await self.send(c, {"op": "REGISTERED", "fingerprint": fingerprint(c.pub)})
            while True:
                msg, n = await self.readobj(c, HEARTBEAT_TIMEOUT)
                if not c.take():
                    c.strikes += 1; self.log(nid, "?", False, "rate_limited", n)
                    await self.send(c, {"op": "REJECT", "reason": "rate_limited"})
                    if c.strikes >= MAX_STRIKES: return
                    continue
                await self.dispatch(c, msg, n)
        except (asyncio.TimeoutError, ConnectionError, ValueError, asyncio.LimitOverrunError, json.JSONDecodeError) as e:
            self.log(c.node_id or "?", "CONN", False, type(e).__name__)
        finally:
            self.drop(c)

    async def dispatch(self, c, msg, n):
        op, nid = msg.get("op"), c.node_id
        if op == "HEARTBEAT":
            await self.send(c, {"op": "ACK"})
        elif op == "LIST_ROOMS":
            await self.send(c, {"op": "ROOMS", "rooms": {r: sorted(m) for r, m in self.rooms.items()}})
        elif op in ("JOIN_ROOM", "LEAVE"):
            room = msg.get("room")
            if not isinstance(room, str) or not ID_RE.match(room):
                self.log(nid, op, False, "bad_room", n); await self.send(c, {"op": "REJECT", "reason": "bad_room"}); return
            if op == "JOIN_ROOM": self.rooms.setdefault(room, set()).add(nid)
            elif room in self.rooms:
                self.rooms[room].discard(nid)
                if not self.rooms[room]: del self.rooms[room]
            self.log(nid, op, True, room, n); await self.send(c, {"op": "OK", "room": room})
        elif op == "RELAY":
            why = self.check_env(c, msg.get("env"))
            if why:
                self.log(nid, "RELAY", False, why, n); await self.send(c, {"op": "REJECT", "reason": why}); return
            env = msg["env"]
            members = self.rooms[env["room"]]
            targets = [m for m in members if m != nid] if env["to"] == "*" else [env["to"]]
            delivered = 0
            for t in targets:
                tc = self.clients.get(t)
                if tc and await self.send(tc, {"op": "DELIVER", "env": env}): delivered += 1
            self.log(nid, "RELAY", True, f"{env['type']}->{env['to']} x{delivered}", n)
            await self.send(c, {"op": "OK", "delivered": delivered})
        else:
            self.log(nid, str(op)[:24], False, "unknown_op", n); await self.send(c, {"op": "REJECT", "reason": "unknown_op"})

    def check_env(self, c, env):
        if not isinstance(env, dict): return "bad_env"
        for k, t in (("from", str), ("to", str), ("room", str), ("type", str), ("nonce", str), ("sig", str)):
            if not isinstance(env.get(k), t): return "bad_env"
        if not isinstance(env.get("ts"), (int, float)) or "payload" not in env: return "bad_env"
        if env["from"] != c.node_id: return "from_mismatch"
        if not TYPE_RE.match(env["type"]) or len(env["nonce"]) > 64: return "bad_env"
        if abs(time.time() - env["ts"]) > TS_WINDOW: return "stale"
        if not verify_env(c.pub, env): return "bad_sig"
        members = self.rooms.get(env["room"])
        if not members or c.node_id not in members: return "not_in_room"
        if env["to"] != "*" and env["to"] not in members: return "target_not_in_room"
        now = time.time()
        if len(self.seen) > 10000: self.seen = {k: v for k, v in self.seen.items() if v > now}
        key = (c.node_id, env["nonce"])
        if key in self.seen: return "replay"
        self.seen[key] = now + 2 * TS_WINDOW
        return None

# ===================== NODE =====================
def f_sha256(x):
    if not isinstance(x, str) or len(x) > 10000: raise ValueError("bad input")
    return sha256hex(x)
def f_sum(x):
    if not isinstance(x, list) or len(x) > 10000 or any(type(i) is not int or abs(i) > 10**12 for i in x): raise ValueError("bad input")
    return sum(x)
def f_collatz(x):
    if type(x) is not int or not 1 <= x <= 10**15: raise ValueError("bad input")
    steps = 0
    while x != 1:
        x = x // 2 if x % 2 == 0 else 3 * x + 1; steps += 1
        if steps > 1_000_000: raise ValueError("too long")
    return steps
FUNCS = {"sha256": f_sha256, "sum": f_sum, "collatz_steps": f_collatz}
def result_hash(result): return sha256hex(canon(result))

class Node:
    def __init__(self, a):
        self.a = a
        self.id = json.load(open(a.key))
        self.allow = load_allowlist(a.allow)
        self.ledger = Ledger(a.ledger)
        self.nonces, self.units_sent, self.units_done = {}, {}, set()
        self.results, self.confirms, self.confirmed = {}, {}, set()
        self.rooms_fut, self.done_fut = None, None
        self.fp = self.id["fingerprint"]

    # ---- transport ----
    async def connect(self):
        a = self.a
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT); ctx.minimum_version = ssl.TLSVersion.TLSv1_2
        if a.pin: ctx.check_hostname, ctx.verify_mode = False, ssl.CERT_NONE   # trust = the pin, checked below
        elif a.cafile: ctx.load_verify_locations(a.cafile)
        else: ctx.load_default_certs()
        host, port = a.hub.rsplit(":", 1)
        self.r, self.w = await asyncio.open_connection(host, int(port), ssl=ctx, server_hostname=host, limit=MAX_LINE)
        if a.pin:
            der = self.w.get_extra_info("ssl_object").getpeercert(binary_form=True)
            if hashlib.sha256(der).hexdigest() != a.pin.replace(":", "").lower():
                raise SystemExit("hub certificate does not match --pin; aborting")
        ch = json.loads(await self.r.readline())
        if ch.get("op") != "CHALLENGE": raise SystemExit("no challenge from hub")
        await self.raw({"op": "REGISTER", "node_id": self.id["node_id"], "pub": self.id["pub"],
                        "sig": sign_register(self.id["seed"], ch["nonce"], self.id["node_id"])})
        resp = json.loads(await self.r.readline())
        if resp.get("op") != "REGISTERED": raise SystemExit(f"hub rejected registration: {resp}")
        await self.raw({"op": "JOIN_ROOM", "room": a.room})
        print(f"[{self.id['node_id']}] registered fp={self.fp} room={a.room}", flush=True)

    async def raw(self, obj):
        self.w.write((json.dumps(obj, separators=(",", ":")) + "\n").encode()); await self.w.drain()

    async def send(self, to, typ, payload):
        env = {"from": self.id["node_id"], "to": to, "room": self.a.room, "type": typ,
               "ts": time.time(), "nonce": secrets.token_hex(12), "payload": payload}
        await self.raw({"op": "RELAY", "env": sign_env(self.id["seed"], env)}); return env

    async def heartbeat(self):
        while True:
            await asyncio.sleep(30); await self.raw({"op": "HEARTBEAT"})

    # ---- protocol ----
    def accept(self, env):
        """End-to-end check; returns False for anything not signed by an allowlisted peer."""
        try:
            pub = self.allow.get(env["from"])
            if not pub or env["room"] != self.a.room or abs(time.time() - env["ts"]) > TS_WINDOW: return False
            if not verify_env(pub, env): return False
            k = (env["from"], env["nonce"])
            if k in self.nonces: return False
            self.nonces[k] = time.time()
            if len(self.nonces) > 10000: self.nonces = {x: t for x, t in self.nonces.items() if time.time() - t < 2 * TS_WINDOW}
            return True
        except (KeyError, TypeError): return False

    def fp_of(self, node_id): return fingerprint(self.allow[node_id])

    async def on_env(self, env):
        if not self.accept(env): print("dropped envelope failing end-to-end check", flush=True); return
        p, typ, src = env["payload"], env["type"], env["from"]
        try:
            if typ == "WORK_UNIT" and self.a.mode in ("worker", "submit") and p["unit_id"] not in self.units_done:
                if self.a.mode == "submit": return                       # requesters don't compute their own units
                if p["deadline"] < time.time(): return
                self.units_done.add(p["unit_id"])
                res = FUNCS[p["spec"]["fn"]](p["input"])                 # KeyError/ValueError -> ignored below
                self.ledger.append({"event": "WORK", "unit_id": p["unit_id"], "requester": self.fp_of(src), "fn": p["spec"]["fn"]})
                self.results.setdefault(p["unit_id"], {})[self.id["node_id"]] = result_hash(res)
                await self.send(src, "RESULT", {"unit_id": p["unit_id"], "result": res, "result_hash": result_hash(res)})
            elif typ == "RESULT":
                uid = p["unit_id"]
                if p["result_hash"] != result_hash(p["result"]): return
                self.results.setdefault(uid, {})[src] = p["result_hash"]
                self.ledger.append({"event": "RESULT", "unit_id": uid, "producer": self.fp_of(src), "result_hash": p["result_hash"]})
                unit = self.units_sent.get(uid)
                if unit:                                                  # I asked for it: recompute independently
                    mine = result_hash(FUNCS[unit["spec"]["fn"]](unit["input"]))
                    if mine == p["result_hash"]:
                        await self.send("*", "CONFIRM", {"unit_id": uid, "producer": src, "result_hash": mine})
                        self.confirms.setdefault(uid, []).append((self.id["node_id"], src, mine))
                    else:
                        await self.send("*", "DISPUTE", {"unit_id": uid, "producer": src, "result_hash": mine})
                        self.ledger.append({"event": "DISPUTE", "unit_id": uid, "producer": self.fp_of(src), "theirs": p["result_hash"], "mine": mine})
                        print(f"DISPUTE on {uid}: result hash mismatch", flush=True)
                self.evaluate(uid)
            elif typ == "CONFIRM":
                self.confirms.setdefault(p["unit_id"], []).append((src, p["producer"], p["result_hash"]))
                self.evaluate(p["unit_id"])
        except (KeyError, TypeError, ValueError) as e:
            print(f"ignored bad {typ}: {type(e).__name__}", flush=True)

    def evaluate(self, uid):
        """Confirmed = a result AND a matching CONFIRM from a node with a DIFFERENT fingerprint."""
        if uid in self.confirmed: return
        for confirmer, producer, h in self.confirms.get(uid, []):
            if (self.results.get(uid, {}).get(producer) == h and confirmer != producer
                    and self.fp_of(confirmer) != self.fp_of(producer)):
                self.confirmed.add(uid)
                self.ledger.append({"event": "CONFIRMED", "unit_id": uid, "producer": self.fp_of(producer),
                                    "confirmer": self.fp_of(confirmer), "result_hash": h})
                print(f"CONFIRMED {uid} result_hash={h[:16]} producer={self.fp_of(producer)} confirmer={self.fp_of(confirmer)}", flush=True)
                if self.done_fut and not self.done_fut.done(): self.done_fut.set_result(h)
                return

    async def recv_loop(self):
        while True:
            line = await self.r.readline()
            if not line: raise SystemExit("hub closed the connection")
            m = json.loads(line)
            if m.get("op") == "DELIVER": await self.on_env(m["env"])
            elif m.get("op") == "ROOMS" and self.rooms_fut and not self.rooms_fut.done(): self.rooms_fut.set_result(m["rooms"])
            elif m.get("op") == "REJECT": print("hub reject:", m.get("reason"), flush=True)

    async def submit(self):
        a, loop = self.a, asyncio.get_running_loop()
        deadline = time.time() + a.timeout
        while time.time() < deadline:                                     # wait until someone else is in the room
            self.rooms_fut = loop.create_future(); await self.raw({"op": "LIST_ROOMS"})
            rooms = await asyncio.wait_for(self.rooms_fut, 10)
            if len([m for m in rooms.get(a.room, []) if m != self.id["node_id"]]) >= 1: break
            await asyncio.sleep(2)
        else: raise SystemExit("no other node joined the room before the timeout")
        inp = json.loads(a.input)
        unit = {"unit_id": secrets.token_hex(8), "room": a.room, "spec": {"fn": a.fn}, "input": inp, "deadline": time.time() + a.timeout}
        FUNCS[a.fn](inp)                                                  # reject bad input before sending
        self.units_sent[unit["unit_id"]] = unit
        self.done_fut = loop.create_future()
        self.ledger.append({"event": "UNIT", "unit_id": unit["unit_id"], "fn": a.fn, "requester": self.fp})
        await self.send("*", "WORK_UNIT", unit)
        print(f"submitted unit {unit['unit_id']} fn={a.fn}", flush=True)
        await asyncio.wait_for(self.done_fut, a.timeout)

# ===================== CLI =====================
def cmd_keygen(a):
    if not ID_RE.match(a.id): sys.exit("bad node id (a-z 0-9 _ - , max 32)")
    out = a.out or f"key_{a.id}.json"
    if os.path.exists(out): sys.exit(f"{out} exists; refusing to overwrite")
    seed = gen_seed(); pub = pub_of(seed)
    fd = os.open(out, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as f:
        json.dump({"node_id": a.id, "seed": seed, "pub": pub, "fingerprint": fingerprint(pub)}, f, indent=1)
    print(f"wrote {out} (private; never share the seed)\nfingerprint: {fingerprint(pub)}")
    print("add this line to allowed_keys.json on the hub AND every node:")
    print(f'  "{a.id}": "{pub}"')

def cmd_cert(a):
    if not shutil.which("openssl"): sys.exit("openssl not found")
    san = f"IP:{a.ip}" if re.match(r"^[0-9.]+$", a.ip) else f"DNS:{a.ip}"
    subprocess.run(["openssl", "req", "-x509", "-newkey", "ec", "-pkeyopt", "ec_paramgen_curve:prime256v1", "-nodes",
                    "-keyout", a.keyout, "-out", a.certout, "-days", str(a.days), "-subj", f"/CN={a.ip}",
                    "-addext", f"subjectAltName={san}"], check=True, stderr=subprocess.DEVNULL)
    os.chmod(a.keyout, 0o600)
    fp = subprocess.check_output(["openssl", "x509", "-in", a.certout, "-noout", "-fingerprint", "-sha256"], text=True)
    print(f"wrote {a.certout} and {a.keyout}\nuse as --pin: {fp.split('=', 1)[1].strip()}")

def cmd_verify(a):
    ok, n, last = Ledger.verify(a.path)
    print(f"{a.path}: {'VALID' if ok else 'BROKEN'} chain, {n} entries ok, head {last[:16]}")
    sys.exit(0 if ok else 1)

async def cmd_hub(a):
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER); ctx.minimum_version = ssl.TLSVersion.TLSv1_2
    ctx.load_cert_chain(a.cert, a.key)
    hub = Hub(a.allow, a.log); hub.refresh_allow()
    srv = await asyncio.start_server(hub.handle, a.host, a.port, ssl=ctx, limit=MAX_LINE)
    print(f"hub listening on {a.host}:{a.port}, {len(hub.allow)} allowlisted nodes", flush=True)
    async with srv: await srv.serve_forever()

async def cmd_node(a):
    n = Node(a); await n.connect()
    tasks = [asyncio.create_task(n.heartbeat()), asyncio.create_task(n.recv_loop())]
    try:
        if a.cmd == "submit":
            await n.submit(); print("OK: unit confirmed"); return
        await asyncio.gather(*tasks)
    except asyncio.TimeoutError: print("TIMEOUT: unit not confirmed"); sys.exit(1)
    finally:
        for t in tasks: t.cancel()

def cmd_selftest(a):
    if not shutil.which("openssl"): sys.exit("selftest needs openssl")
    me, d = os.path.abspath(__file__), tempfile.mkdtemp(prefix="lnet-")
    run = lambda *x, **k: subprocess.run([sys.executable, me, *x], cwd=d, capture_output=True, text=True, **k)
    port = str(20000 + secrets.randbelow(20000)); fails = 0
    def check(name, cond, extra=""):
        nonlocal fails; fails += not cond; print(("PASS " if cond else "FAIL ") + name + (f"  {extra}" if extra and not cond else ""))
    for nid in ("gw", "sbx", "rogue"): run("keygen", "--id", nid)
    json.dump({n: json.load(open(f"{d}/key_{n}.json"))["pub"] for n in ("gw", "sbx")}, open(f"{d}/allowed_keys.json", "w"))
    pin = run("cert", "--ip", "127.0.0.1").stdout.split("use as --pin:")[1].strip()
    hub = subprocess.Popen([sys.executable, me, "hub", "--port", port, "--host", "127.0.0.1", "--cert", "hub.crt", "--key", "hub.key"],
                           cwd=d, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(1.5); common = ["--hub", f"127.0.0.1:{port}", "--pin", pin]
    worker = subprocess.Popen([sys.executable, me, "worker", "--key", "key_sbx.json", "--ledger", "sbx.jsonl", *common],
                              cwd=d, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    time.sleep(1)
    try:
        r = run("submit", "--key", "key_gw.json", "--ledger", "gw.jsonl", "--fn", "collatz_steps", "--input", "27", "--timeout", "20", *common)
        check("round trip: unit computed, independently confirmed", "OK: unit confirmed" in r.stdout, r.stdout + r.stderr)
        check("ledger chains verify", all(run("verify", f"{d}/{f}").returncode == 0 for f in ("gw.jsonl", "sbx.jsonl")))
        r = run("worker", "--key", "key_rogue.json", "--ledger", "r.jsonl", *common, timeout=15)
        check("unlisted key rejected", "rejected registration" in r.stdout + r.stderr)
        r = run("worker", "--key", "key_sbx.json", "--ledger", "p.jsonl", "--hub", f"127.0.0.1:{port}", "--pin", "00:11", timeout=15)
        check("wrong certificate pin rejected", "does not match --pin" in r.stdout + r.stderr)
    finally:
        worker.terminate(); hub.terminate()
    print(f"\n{'ALL PASSED' if not fails else str(fails) + ' FAILED'} (crypto backend: {BACKEND}); temp files in {d}")
    sys.exit(1 if fails else 0)

def main():
    ap = argparse.ArgumentParser(description="lantern-net: one-file close network"); sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("keygen"); p.add_argument("--id", required=True); p.add_argument("--out")
    p = sub.add_parser("cert"); p.add_argument("--ip", required=True, help="hub IP or hostname")
    p.add_argument("--certout", default="hub.crt"); p.add_argument("--keyout", default="hub.key"); p.add_argument("--days", type=int, default=365)
    p = sub.add_parser("verify"); p.add_argument("path")
    p = sub.add_parser("hub"); p.add_argument("--host", default="0.0.0.0"); p.add_argument("--port", type=int, default=443)
    p.add_argument("--cert", required=True); p.add_argument("--key", required=True)
    p.add_argument("--allow", default="allowed_keys.json"); p.add_argument("--log", default="hub.log")
    for name in ("worker", "submit"):
        p = sub.add_parser(name); p.add_argument("--key", required=True); p.add_argument("--hub", required=True, help="host:port")
        p.add_argument("--room", default="lab"); p.add_argument("--allow", default="allowed_keys.json"); p.add_argument("--ledger", default="ledger.jsonl")
        p.add_argument("--pin", help="sha256 of the hub certificate; use for self-signed certs"); p.add_argument("--cafile")
        p.add_argument("--fn", default="sha256", choices=sorted(FUNCS)); p.add_argument("--input", default='"hello lantern"')
        p.add_argument("--timeout", type=float, default=60)
    sub.add_parser("selftest")
    a = ap.parse_args()
    if a.cmd == "keygen": cmd_keygen(a)
    elif a.cmd == "cert": cmd_cert(a)
    elif a.cmd == "verify": cmd_verify(a)
    elif a.cmd == "selftest": cmd_selftest(a)
    elif a.cmd == "hub": asyncio.run(cmd_hub(a))
    else:
        a.mode = a.cmd
        asyncio.run(cmd_node(a))

if __name__ == "__main__":
    main()
