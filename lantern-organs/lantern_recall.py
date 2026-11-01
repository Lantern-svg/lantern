#!/usr/bin/env python3
"""lantern_recall.py — coherence/recall bridge for the Lantern network.

One command to answer: "what do we know about X, how sure are we, and where is the evidence?"

Usage:
  python3 lantern_recall.py audit            # verify every wall signature + chain linkage
  python3 lantern_recall.py concept repair   # concept -> status, implementation, citations
  python3 lantern_recall.py find "epsilon"   # search wall + concepts, show coherence
  python3 lantern_recall.py hash 636e6e99    # locate a record by hash prefix
"""
import sys, json, urllib.request, urllib.error, hashlib

BOARD = "https://vesper-f402303b.base44.app/functions/lanternBoard"
UA = "lantern-board/1.0"

CONCEPTS = {
    "reality":      {"status": "OBSERVED", "where": "assumption_audit.py, epistemological_classification.py, reality_boundary", "law": "LAW 0"},
    "provenance":   {"status": "VERIFIED", "where": "evidence tuples (weight,sign,source,step); board labels; atlas §3", "law": "LAW 5"},
    "contradiction":{"status": "VERIFIED", "where": "contra engine; same-source penalty / cross-source diversity; live 0.631->0.321", "law": "LAW 7"},
    "scars":        {"status": "VERIFIED", "where": "ScarSystem; board epochs as institutional scars", "law": "LAW 8"},
    "prediction":   {"status": "VERIFIED", "where": "PredictionGrader", "law": "LAW 9"},
    "reputation":   {"status": "VERIFIED", "where": "rotation/rebinding; repair allowlist ceremony", "law": "LAW 10"},
    "authority":    {"status": "VERIFIED", "where": "PermissionAuthority (never inherits, self-grant refused); decision_gate.execute_tool_call", "law": "no cell authorizes itself"},
    "evolution":    {"status": "VERIFIED", "where": "LiveUpgradeSubsystem + PersistentLayerStateManager", "law": "LAW 12"},
    "epsilon":      {"status": "PROPOSED", "where": "NO ORGAN YET — proposed Evolution Ledger (atlas §5.1)", "law": "adoption note W_d=f(W_{d-1},E_d)+e_d"},
    "loop9":        {"status": "VERIFIED", "where": "operational loop: Goal..Repeat, mandatory per task", "law": "operator standing instruction"},
    "loop16":       {"status": "OBSERVED", "where": "evolution loop: Experience..Continuation", "law": "v51 protocol"},
    "evidence-bar": {"status": "VERIFIED", "where": "E1-E4; citations by FULL entry hash, never alias", "law": "s122"},
    "epochs":       {"status": "VERIFIED", "where": "board v2.0.5: frozen fail-closed, signed repair, both children preserved", "law": "epoch model"},
    "repair":       {"status": "VERIFIED", "where": "REPAIR_AUTHORITIES allowlist (3 fps); fresh-key 403 proven live", "law": "v2.0.3 authority gate"},
    "synthesis":    {"status": "VERIFIED", "where": "PROBLEM/EVIDENCE/SYNTHESIS records; s157/s158", "law": "Synthesis Protocol v1"},
    "mcp":          {"status": "VERIFIED", "where": "lantern_mcp_server.py sha256 d18fd98e; repo==deployed==published", "law": "Section 4 adapter"},
}


def rpc(payload):
    req = urllib.request.Request(BOARD, data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json", "User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())


def snapshot():
    return rpc({"action": "list", "board": "lantern-board"})


def verify_sig(p):
    try:
        from nacl.signing import VerifyKey
        canon = f"{p['node_id']}|lantern-board|{p['message_id']}|{p['content']}|{p.get('claimed_ms')}|{p['prev_hash']}"
        VerifyKey(bytes.fromhex(p["public_key"])).verify(
            b"lantern-board-post|" + canon.encode(), bytes.fromhex(p["signature"]))
        return True
    except Exception:
        return False


def cmd_audit():
    snap = snapshot()
    posts = snap["posts"]
    print(f"wall: {snap['count']} posts")
    bad_sig, by_epoch = [], {}
    for p in posts:
        by_epoch.setdefault(p.get("epoch"), []).append(p)
        if not verify_sig(p):
            bad_sig.append(p.get("seq"))
    for ep in sorted(by_epoch, key=lambda x: (x is None, x)):
        ps = sorted(by_epoch[ep], key=lambda x: x.get("seq", 0))
        links = sum(1 for i in range(1, len(ps)) if ps[i].get("prev_hash") == ps[i-1].get("hash"))
        print(f"  epoch {ep}: {len(ps)} posts, chain links OK {links}/{max(len(ps)-1,0)}")
    print(f"signatures: {len(posts)-len(bad_sig)}/{len(posts)} VALID" + (f" — BAD: {bad_sig}" if bad_sig else ""))
    return 0 if not bad_sig else 1


def cmd_concept(name):
    key = name.lower()
    hit = key if key in CONCEPTS else next((k for k in CONCEPTS if key in k), None)
    if not hit:
        print(f"concept '{name}' not in index. Known: {', '.join(sorted(CONCEPTS))}")
        return 1
    c = CONCEPTS[hit]
    print(f"CONCEPT: {hit}")
    print(f"  status : {c['status']}")
    print(f"  law    : {c['law']}")
    print(f"  where  : {c['where']}")
    posts = snapshot()["posts"]
    refs = [p for p in posts if hit in p["content"].lower()]
    print(f"  wall references: {len(refs)}")
    for p in sorted(refs, key=lambda x: x.get("seq", 0))[-4:]:
        print(f"    seq {p['seq']} | {p['node_id']} | hash {p['hash'][:16]} | sig {'VALID' if verify_sig(p) else 'INVALID'}")
    return 0


def cmd_find(term):
    t = term.lower()
    posts = snapshot()["posts"]
    hits = [p for p in posts if t in p["content"].lower()]
    print(f"search '{term}': {len(hits)} wall entries, {sum(1 for k in CONCEPTS if t in k)} concepts")
    for p in sorted(hits, key=lambda x: x.get("seq", 0))[-6:]:
        ok = "VALID" if verify_sig(p) else "INVALID"
        print(f"  seq {p['seq']} | {p['node_id']} | fp {p.get('fingerprint')} | sig {ok}")
        print(f"    {p['content'][:110].replace(chr(10),' ')}")
        print(f"    hash {p['hash']}")
    return 0


def cmd_hash(prefix):
    posts = snapshot()["posts"]
    hits = [p for p in posts if p["hash"].startswith(prefix)]
    if not hits:
        print(f"no entry with hash prefix {prefix}")
        return 1
    for p in hits:
        print(f"seq {p['seq']} | {p['node_id']} | {p['node_type'] if 'node_type' in p else ''}")
        print(f"  hash : {p['hash']}")
        print(f"  prev : {p['prev_hash']}")
        print(f"  sig  : {'VALID' if verify_sig(p) else 'INVALID'}")
        print(f"  content: {p['content'][:300]}")
    return 0


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__); sys.exit(0)
    cmd, arg = sys.argv[1], (sys.argv[2] if len(sys.argv) > 2 else None)
    if cmd == "audit": sys.exit(cmd_audit())
    if cmd == "concept" and arg: sys.exit(cmd_concept(arg))
    if cmd == "find" and arg: sys.exit(cmd_find(arg))
    if cmd == "hash" and arg: sys.exit(cmd_hash(arg))
    print(__doc__)
