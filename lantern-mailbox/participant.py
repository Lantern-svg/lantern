"""Separate-process participant worker for the Lantern Mailbox battery.
Each invocation is an independently instantiated participant: keys generated
or loaded in THIS process only. Roles: bind | send | fetch.
Usage: participant.py <role> <node_id> <state_file> [recipient_node_id] [plaintext]
"""
import json, sys, hashlib
from nacl.signing import SigningKey
from nacl.public import PrivateKey, PublicKey, SealedBox
from nacl.signing import VerifyKey
from mailbox_client import Rpc, lookup, PROTO, fp, sha256hex, _now

class Participant:
    def __init__(self, node_id, state=None):
        self.node_id = node_id
        if state:
            self.sk = SigningKey(bytes.fromhex(state["ed25519_priv"]))
            self.xk = PrivateKey(bytes.fromhex(state["x25519_priv"]))
        else:
            self.sk = SigningKey.generate()
            self.xk = PrivateKey.generate()
        self.ed25519_pub = self.sk.verify_key.encode().hex()
        self.x25519_pub = self.xk.public_key.encode().hex()
        self.fingerprint = fp(self.ed25519_pub)
        self.mailbox_id = state["mailbox_id"] if state else None

    def state(self):
        return {"node_id": self.node_id, "ed25519_priv": self.sk.encode().hex(),
                "x25519_priv": self.xk.encode().hex(), "ed25519_pub": self.ed25519_pub,
                "x25519_pub": self.x25519_pub, "fingerprint": self.fingerprint,
                "mailbox_id": self.mailbox_id}

    def sign(self, stmt): return self.sk.sign(stmt.encode()).signature.hex()

def main():
    role, node_id, state_file = sys.argv[1], sys.argv[2], sys.argv[3]
    rpc = Rpc()
    if role == "bind":
        p = Participant(node_id)
        now = _now()
        stmt = f"lantern.mailbox.bind.v1|{node_id}|{p.ed25519_pub}|{p.x25519_pub}|{now}"
        r = rpc({"action": "bind", "now_ms": now, "payload": {
            "node_id": node_id, "ed25519_pub": p.ed25519_pub, "x25519_pub": p.x25519_pub,
            "created_ms": now, "binding_signature": p.sign(stmt)}})
        if r["status"] == 200:
            p.mailbox_id = r["body"]["mailbox_id"]
            json.dump(p.state(), open(state_file, "w"))
        print(json.dumps({"role": role, "status": r["status"], "body": r["body"]}))
    elif role == "send":
        state = json.load(open(state_file))
        recipient_node = sys.argv[4]
        plaintext = sys.argv[5] if len(sys.argv) > 5 else "ping-from-" + node_id
        p = Participant(node_id, state)
        disc = lookup(rpc, node_id=recipient_node)
        if disc["status"] != 200 or disc["body"]["count"] < 1:
            print(json.dumps({"role": role, "error": "recipient discovery failed", "disc": disc["body"]})); return
        rb = disc["body"]["bindings"][0]
        if rb["status"] != "active":
            print(json.dumps({"role": role, "error": "recipient not active"})); return
        # recipient verification: mailbox binding fingerprint matches identity key
        if fp(rb["ed25519_pub"]) != rb["fingerprint"]:
            print(json.dumps({"role": role, "error": "recipient binding fingerprint mismatch"})); return
        now = _now()
        import secrets
        mid = f"msg-{p.fingerprint}-{now}-{secrets.token_hex(4)}"
        ct = SealedBox(PublicKey(bytes.fromhex(rb["x25519_pub"]))).encrypt(plaintext.encode()).hex()
        ct_hash = sha256hex(ct)
        expiry = now + 7 * 24 * 3600 * 1000
        env = {"message_id": mid, "sender_fingerprint": p.fingerprint,
               "sender_ed25519_pub": p.ed25519_pub, "mailbox_id": rb["mailbox_id"],
               "recipient_fingerprint": rb["fingerprint"], "ciphertext_sha256": ct_hash,
               "protocol_version": PROTO, "created_ms": now, "expiry_ms": expiry}
        stmt = ("lantern.mail.message.v1|" + "|".join([
            mid, p.fingerprint, rb["mailbox_id"], rb["fingerprint"], ct_hash, PROTO, str(now), str(expiry)]))
        r = rpc({"action": "send", "now_ms": now, "payload": {
            "message_id": mid, "ciphertext": ct, "envelope": env, "signature": p.sign(stmt)}})
        print(json.dumps({"role": role, "status": r["status"], "body": r["body"],
                          "message_id": mid, "sender_fingerprint": p.fingerprint}))
    elif role == "fetch":
        state = json.load(open(state_file))
        p = Participant(node_id, state)
        b = rpc({"action": "fetch_begin", "now_ms": _now(), "payload": {"mailbox_id": p.mailbox_id}})
        if b["status"] != 200:
            print(json.dumps({"role": role, "error": "fetch_begin failed", "body": b["body"]})); return
        ch = b["body"]["challenge_id"]
        now = _now()
        fstmt = f"lantern.mail.fetch.v1|{p.mailbox_id}|{p.ed25519_pub}|{ch}|{now}"
        r = rpc({"action": "fetch", "now_ms": now, "payload": {
            "mailbox_id": p.mailbox_id, "ed25519_pub": p.ed25519_pub, "challenge_id": ch,
            "now_ms": now, "signature": p.sign(fstmt)}})
        if r["status"] != 200:
            print(json.dumps({"role": role, "error": "fetch failed", "body": r["body"]})); return
        out = {"role": role, "count": r["body"]["count"], "messages": []}
        for m in r["body"]["messages"]:
            env = m["envelope"]
            disc = lookup(rpc, fingerprint=env["sender_fingerprint"])
            verified, note = False, "sender not discoverable"
            if disc["status"] == 200 and disc["body"]["count"] >= 1:
                sb = disc["body"]["bindings"][0]
                if sb["ed25519_pub"] == env["sender_ed25519_pub"] and sb["status"] == "active":
                    stmt = ("lantern.mail.message.v1|" + "|".join([
                        env["message_id"], env["sender_fingerprint"], env["mailbox_id"],
                        env["recipient_fingerprint"], env["ciphertext_sha256"],
                        env["protocol_version"], str(env["created_ms"]), str(env["expiry_ms"])]))
                    try:
                        VerifyKey(bytes.fromhex(env["sender_ed25519_pub"])).verify(
                            stmt.encode(), bytes.fromhex(m["signature"]))
                        verified, note = True, "signature verified against discovered binding"
                    except Exception as e:
                        verified, note = False, f"sig fail: {e}"
                else:
                    note = "discovered binding does not match envelope key"
            try:
                plaintext = SealedBox(p.xk).decrypt(bytes.fromhex(m["ciphertext"])).decode()
            except Exception as e:
                plaintext, note = None, f"decrypt fail: {e}"
            out["messages"].append({"message_id": env["message_id"],
                "sender_fingerprint": env["sender_fingerprint"],
                "sender_verified": verified, "verify_note": note, "plaintext": plaintext})
        print(json.dumps(out))
    else:
        print(json.dumps({"error": "unknown role"}))

if __name__ == "__main__":
    main()
