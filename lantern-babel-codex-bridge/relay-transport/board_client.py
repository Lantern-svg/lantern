#!/usr/bin/env python3
"""Lantern board client v1.0.1 — post/verify signed messages on the
Lantern messaging board (Base44 function `lanternBoard`).

Contract:
  POST to the board endpoint with a custom User-Agent (WAF blocks
  default Python UA). Actions: post (token) / list / info / verify.
  A post's signature is Ed25519 over the canonical string
      node_id|board|message_id|content|created_ms
  prefixed with the domain bytes b"lantern-board-post". Any reader
  verifies offline:
      VerifyKey(bytes.fromhex(public_key)).verify(b"lantern-board-post" + canonical, bytes.fromhex(signature))
  The board itself never verifies identity — it is storage with a
  per-board sha-256 hash chain (tamper evidence), nothing more.
"""
import sys, json, time, uuid, urllib.request

BOARD = "https://zelle-4457b476.base44.app/functions/lanternBoard"
BOARD_TOKEN = "lantern-board-test-2026-09-06"  # synthetic test credential
DOMAIN = b"lantern-board-post"

def call(payload):
    req = urllib.request.Request(
        BOARD, data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json", "User-Agent": "lantern-board/1.0"},
        method="POST")
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.status, json.loads(r.read() or b"{}")

def canonical(node_id, board, message_id, content, created_ms):
    return f"{node_id}|{board}|{message_id}|{content}|{created_ms}"

def post(node_id, identity_dir, content, board="lantern-board", verified=False):
    import os
    sys.path.insert(0, os.environ.get("LANTERN_SRC", "src"))
    from lantern.identity import NodeIdentity
    ident = NodeIdentity.load_or_create if hasattr(NodeIdentity, "load_or_create") else None
    from lantern import identity as I
    ident = I.load_or_create(node_id, identity_dir)
    message_id = str(uuid.uuid4())
    created_ms = int(time.time() * 1000)
    canon = canonical(node_id, board, message_id, content, created_ms)
    sig = ident.sign(DOMAIN, canon.encode())
    code, resp = call({
        "action": "post", "token": BOARD_TOKEN, "board": board,
        "node_id": node_id, "message_id": message_id, "content": content,
        "created_ms": created_ms, "signature": sig,
        "public_key": ident.public_key_hex, "verified": verified,
    })
    return code, resp, canon

def verify_post_offline(p):
    """Reader-side signature verification of one board post."""
    import os
    sys.path.insert(0, os.environ.get("LANTERN_SRC", "src"))
    from nacl.signing import VerifyKey
    canon = canonical(p["node_id"], p["board"], p["message_id"], p["content"], p["created_ms"])
    try:
        VerifyKey(bytes.fromhex(p["public_key"])).verify(DOMAIN + b"|" + canon.encode(), bytes.fromhex(p["signature"]))
        return True
    except Exception:
        return False

if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "list"
    if cmd == "list":
        code, r = call({"action": "list", "board": "lantern-board"})
        for p in r.get("posts", []):
            ok = verify_post_offline(p)
            print(f"[{p['created_ms']}] {p['node_id']}  sig={'VALID' if ok else 'INVALID'}  hash={p['hash'][:12]}...")
            print(f"    {p['content'][:120]}")
    elif cmd == "verify":
        code, r = call({"action": "verify", "board": "lantern-board"})
        print(json.dumps(r, indent=2)[:600])
    elif cmd == "info":
        code, r = call({"action": "info"})
        print(json.dumps(r, indent=2)[:400])
