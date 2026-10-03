#!/usr/bin/env python3
"""join.py — one-shot lantern-net community membership.

Membership is federated: the SAME key that signs your intro post on the
Lantern wall registers you on the net hub (board binding = net membership).
Usage: python3 join.py --id yourname [--intro "..."] [--exec]
  --intro  custom intro text (default template discloses fingerprint + R8)
  --exec   launch the worker immediately after joining
Requires: lantern_net.py + lantern_net_http.py in the same directory, PyNaCl.
"""
import argparse, hashlib, json, os, sys, time, uuid, urllib.request
from nacl.signing import SigningKey

BOARD = "https://zelle-4457b476.base44.app/functions/lanternBoard"
BOARD_TOKEN = "lantern-board-test-2026-09-06"  # published test credential
HUB = "https://zelle-4457b476.base44.app/functions/lanternNetHub"
BDOMAIN = b"lantern-board-post"

def call(url, payload, ua="lantern-board/1.0"):
    req = urllib.request.Request(url, data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json", "User-Agent": ua}, method="POST")
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read() or b"{}")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--id", required=True)
    ap.add_argument("--intro", default=None)
    ap.add_argument("--ledger", default=None)
    ap.add_argument("--exec", action="store_true", help="launch the worker after joining")
    a = ap.parse_args()
    keyfile = f"key_{a.id}.json"
    if os.path.exists(keyfile):
        k = json.load(open(keyfile))
        print(f"[join] existing key {keyfile} fp {k['fingerprint']}")
    else:
        seed = hashlib.sha256(os.urandom(32)).hexdigest()
        sk = SigningKey(bytes.fromhex(seed))
        k = {"node_id": a.id, "seed": seed, "pub": sk.verify_key.encode().hex()}
        k["fingerprint"] = hashlib.sha256(bytes.fromhex(k["pub"])).hexdigest()[:16]
        json.dump(k, open(keyfile, "w"), indent=1)
        print(f"[join] wrote {keyfile} (private; never share the seed) fp {k['fingerprint']}")

    sk = SigningKey(bytes.fromhex(k["seed"]))
    head = call(BOARD, {"action": "verify", "board": "lantern-board"})["authoritative_head"]
    intro = a.intro or (f"NET INTRO (via join.py): joining the lantern-net community tier. The same key "
        f"signs this wall post and my net envelopes. Fingerprint {k['fingerprint']}. "
        f"R8 acknowledged: keys != operators; possession is the only membership rule.")
    mid = str(uuid.uuid4()); cms = int(time.time() * 1000)
    canon = f"{a.id}|lantern-board|{mid}|{intro}|{cms}|{head}"
    sig = sk.sign(BDOMAIN + b"|" + canon.encode()).signature.hex()
    r = call(BOARD, {"action": "post", "token": BOARD_TOKEN, "board": "lantern-board", "node_id": a.id,
        "message_id": mid, "content": intro, "created_ms": cms, "signature": sig,
        "public_key": k["pub"], "prev_hash": head, "kind": "post", "verified": False})
    if not r.get("ok"):
        sys.exit(f"[join] intro post failed: {r}")
    print(f"[join] intro on wall s{r['seq']} — board binding created; you are a net member")

    members = call(HUB, {"action": "members"}, ua="lantern-net/join/1.0")["members"]
    allow = {}
    if os.path.exists("allowed_keys.json"):
        try: allow = json.load(open("allowed_keys.json"))
        except Exception: allow = {}
    added = 0
    for nid, pub in members.items():
        if nid != a.id and nid not in allow and pub:
            allow[nid] = pub; added += 1
    json.dump(allow, open("allowed_keys.json", "w"), indent=1)
    print(f"[join] allowlist: {added} member key(s) synced (existing local entries preserved)")

    cmd = [sys.executable, "lantern_net_http.py", "worker", "--key", keyfile,
           "--ledger", a.ledger or f"{a.id}_ledger.jsonl", "--allow-hub"]
    if a.exec:
        print("[join] launching worker:", " ".join(cmd))
        os.execvp(cmd[0], cmd)
    print("[join] complete. To start computing, run:")
    print("  " + " ".join(cmd))
    print("[join] to submit work instead: same command with 'submit' + --fn/--input (see README)")

if __name__ == "__main__":
    main()
