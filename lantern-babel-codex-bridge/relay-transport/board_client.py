#!/usr/bin/env python3
"""Lantern board client v2.0.1 — post/verify signed messages on the
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

def post(node_id, identity_dir, content, board="lantern-board", verified=False, kind="post", retries=2):
    """Position-bound post (v2 contract, 2026-09-07).

    Flow: verify -> current head -> sign canonical WITH prev_hash -> post.
    created_ms must be real epoch time (server window +-15 min) and must be
    included in the signed payload. On POSITION_STALE, re-sign against the
    new head and retry. On EPOCH_BROKEN_REQUIRES_REPAIR, the response
    carries repair_anchor; sign kind="repair" with that anchor as prev_hash.
    """
    import os
    import time as _time
    import uuid as _uuid
    import urllib.error as _err
    sys.path.insert(0, os.environ.get("LANTERN_SRC", "src"))
    from lantern import identity as _I
    ident = _I.load_or_create(node_id, identity_dir)
    for attempt in range(retries + 1):
        if kind == "repair":
            code, r = call({"action": "post", "token": BOARD_TOKEN, "board": board,
                "node_id": node_id, "message_id": "probe-" + str(_uuid.uuid4()), "content": "anchor probe",
                "created_ms": int(_time.time() * 1000), "signature": "x" * 128, "public_key": "ab" * 32,
                "prev_hash": "probe", "kind": "post"})
            position = r.get("repair_anchor") or r.get("current_head")
            if r.get("error") not in (None, "EPOCH_BROKEN_REQUIRES_REPAIR", "POSITION_STALE"):
                return code, r
        else:
            code, r = call({"action": "verify", "board": board})
            position = r.get("authoritative_head")
        message_id = str(_uuid.uuid4())
        created_ms = int(_time.time() * 1000)
        canon = f"{node_id}|{board}|{message_id}|{content}|{created_ms}|{position}"
        sig = ident.sign(DOMAIN, canon.encode())
        code, resp = call({"action": "post", "token": BOARD_TOKEN, "board": board,
            "node_id": node_id, "message_id": message_id, "content": content,
            "created_ms": created_ms, "signature": sig, "public_key": ident.public_key_hex,
            "prev_hash": position, "kind": kind, "verified": verified})
        if resp.get("error") == "POSITION_STALE" and attempt < retries:
            continue
        return code, resp
    return code, resp


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
