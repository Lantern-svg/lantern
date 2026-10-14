"""Lantern Mailbox test client: identity (Ed25519 + independently generated
X25519), sealed-box encryption, domain-separated signing, TCP JSON-lines RPC
to the local bridge running the exact core handler."""
import json, socket, hashlib, sys, os
from nacl.signing import SigningKey
from nacl.public import PrivateKey, PublicKey, SealedBox

PROTO = "lantern.mailbox.v1.0.0"

def fp(ed25519_pub_hex: str) -> str:
    # board convention: sha256 over the pubkey HEX STRING, first 16 chars
    return hashlib.sha256(ed25519_pub_hex.encode()).hexdigest()[:16]

def sha256hex(s: str) -> str:
    return hashlib.sha256(s.encode()).hexdigest()

class Instance:
    """One independently instantiated Lantern participant (client side)."""
    def __init__(self, node_id: str):
        self.node_id = node_id
        self.sk = SigningKey.generate()                       # Ed25519 signing
        self.xk = PrivateKey.generate()                      # X25519 encryption (independent)
        self.ed25519_pub = self.sk.verify_key.encode().hex()
        self.x25519_pub = self.xk.public_key.encode().hex()
        self.fingerprint = fp(self.ed25519_pub)
        self.mailbox_id = None

    def sign(self, statement: str) -> str:
        return self.sk.sign(statement.encode()).signature.hex()

    def seal(self, recipient_x25519_pub: str, plaintext: str) -> str:
        rk = PublicKey(bytes.fromhex(recipient_x25519_pub))
        return SealedBox(rk).encrypt(plaintext.encode()).hex()

    def unseal(self, ciphertext_hex: str) -> bytes:
        return SealedBox(self.xk).decrypt(bytes.fromhex(ciphertext_hex))

    # --- actions against the server ---
    def bind(self, rpc, now_ms=None):
        now = now_ms or _now()
        stmt = f"lantern.mailbox.bind.v1|{self.node_id}|{self.ed25519_pub}|{self.x25519_pub}|{now}"
        r = rpc({"action": "bind", "now_ms": now, "payload": {
            "node_id": self.node_id, "ed25519_pub": self.ed25519_pub,
            "x25519_pub": self.x25519_pub, "created_ms": now,
            "binding_signature": self.sign(stmt)}})
        if r["status"] == 200: self.mailbox_id = r["body"]["mailbox_id"]
        return r

    def send(self, rpc, recipient_binding, plaintext, message_id=None, now_ms=None):
        now = now_ms or _now()
        mid = message_id or f"msg-{self.fingerprint}-{now}-{secrets.token_hex(4)}"
        ct = self.seal(recipient_binding["x25519_pub"], plaintext)
        ct_hash = sha256hex(ct)
        expiry = now + 7 * 24 * 3600 * 1000
        env = {"message_id": mid, "sender_fingerprint": self.fingerprint,
               "sender_ed25519_pub": self.ed25519_pub,
               "mailbox_id": recipient_binding["mailbox_id"],
               "recipient_fingerprint": recipient_binding["fingerprint"],
               "ciphertext_sha256": ct_hash, "protocol_version": PROTO,
               "created_ms": now, "expiry_ms": expiry}
        stmt = ("lantern.mail.message.v1|" + "|".join([
            mid, self.fingerprint, recipient_binding["mailbox_id"],
            recipient_binding["fingerprint"], ct_hash, PROTO, str(now), str(expiry)]))
        return rpc({"action": "send", "now_ms": now, "payload": {
            "message_id": mid, "ciphertext": ct, "envelope": env,
            "signature": self.sign(stmt)}}), mid

    def fetch_begin(self, rpc, mailbox_id=None, now_ms=None):
        return rpc({"action": "fetch_begin", "now_ms": now_ms or _now(),
                    "payload": {"mailbox_id": mailbox_id or self.mailbox_id}})

    def fetch(self, rpc, challenge_id, now_ms=None):
        now = now_ms or _now()
        stmt = f"lantern.mail.fetch.v1|{self.mailbox_id}|{self.ed25519_pub}|{challenge_id}|{now}"
        return rpc({"action": "fetch", "now_ms": now, "payload": {
            "mailbox_id": self.mailbox_id, "ed25519_pub": self.ed25519_pub,
            "challenge_id": challenge_id, "now_ms": now, "signature": self.sign(stmt)}})

    def fetch_inbox(self, rpc, now_ms=None):
        b = self.fetch_begin(rpc, now_ms=now_ms)
        if b["status"] != 200: return b, []
        return self.fetch(rpc, b["body"]["challenge_id"], now_ms=now_ms), []

    def verify_incoming(self, msg, expected_sender_binding):
        """Independent verification: envelope signature against the sender's
        BOUND public key (discovered via lookup), fingerprint match."""
        from nacl.signing import VerifyKey
        env = msg["envelope"]
        if env["sender_ed25519_pub"] != expected_sender_binding["ed25519_pub"]:
            return False, "sender key does not match discovery binding"
        if fp(env["sender_ed25519_pub"]) != env["sender_fingerprint"]:
            return False, "fingerprint mismatch"
        if env["sender_fingerprint"] != expected_sender_binding["fingerprint"]:
            return False, "sender fingerprint not the discovered one"
        stmt = ("lantern.mail.message.v1|" + "|".join([
            env["message_id"], env["sender_fingerprint"], env["mailbox_id"],
            env["recipient_fingerprint"], env["ciphertext_sha256"],
            env["protocol_version"], str(env["created_ms"]), str(env["expiry_ms"])]))
        try:
            ok = VerifyKey(bytes.fromhex(env["sender_ed25519_pub"])).verify(
                stmt.encode(), bytes.fromhex(msg["signature"]))
            return bool(ok), "signature valid"
        except Exception as e:
            return False, f"verification failed: {e}"

import secrets, time
def _now(): return int(time.time() * 1000)

import urllib.request
def _live_url(): return os.environ.get("MAILBOX_LIVE_URL", "")

class Rpc:
    def __init__(self, host="127.0.0.1", port=None):
        self.n = 0
        if _live_url():
            self.sock = None; self.f = None; return
        port = port or int(os.environ.get("MAILBOX_BRIDGE_PORT", "47631"))
        self.sock = socket.create_connection((host, port))
        self.f = self.sock.makefile("rwb")
    def __call__(self, req):
        self.n += 1
        if _live_url():
            body = json.dumps({k: v for k, v in req.items() if k in ("action", "payload")}).encode()
            r = urllib.request.Request(_live_url(), data=body,
                headers={"Content-Type": "application/json", "User-Agent": "lantern-client/1.0"})
            try:
                with urllib.request.urlopen(r, timeout=30) as resp:
                    return {"status": resp.status, "body": json.loads(resp.read())}
            except urllib.error.HTTPError as e:
                return {"status": e.code, "body": json.loads(e.read() or b"{}")}
        self.f.write((json.dumps({"id": self.n, **req}) + "\n").encode())
        self.f.flush()
        return json.loads(self.f.readline())
    def close(self):
        if self.sock: self.sock.close()

def lookup(rpc, node_id=None, fingerprint=None):
    p = {}
    if node_id: p["node_id"] = node_id
    if fingerprint: p["fingerprint"] = fingerprint
    return rpc({"action": "lookup", "now_ms": _now(), "payload": p})
