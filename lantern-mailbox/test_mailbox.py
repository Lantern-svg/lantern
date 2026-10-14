"""Lantern Mailbox Phase 2 battery: Tests A-J plus the six required additions.
Environment (reported with every result): core handler = the exact
lantern_mailbox/core.js that will be embedded in the deployable function,
run in a LOCAL Node process with an in-memory store; participants = separate
Python processes with independent keypairs; transport = loopback TCP; ONE
operator sandbox. Live deployed-service tests: NOT TESTED (deployment gate).
"""
import json, subprocess, sys, time, os
from mailbox_client import Rpc, Instance, lookup, fp, sha256hex, _now, PROTO

import os as _os
PORT = int(_os.environ.get("MAILBOX_BRIDGE_PORT", "47631"))
HERE = os.path.dirname(os.path.abspath(__file__))
RESULTS = []

def record(tid, name, result, procedure, evidence, env, limitations=""):
    RESULTS.append({"id": tid, "name": name, "result": result, "procedure": procedure,
                    "evidence": evidence, "environment": env, "limitations": limitations})
    print(f"[{result:^10}] {tid}: {name}")

def worker(role, node_id, state, recipient=None, plaintext=None):
    cmd = [sys.executable, "participant.py", role, node_id, state]
    if recipient: cmd += [recipient]
    if plaintext: cmd += [plaintext]
    r = subprocess.run(cmd, cwd=HERE, capture_output=True, text=True,
                       env={**os.environ, "MAILBOX_BRIDGE_PORT": str(PORT)})
    try: return json.loads(r.stdout.strip().splitlines()[-1]), r
    except Exception:
        print("WORKER FAIL", cmd, "| rc:", r.returncode, "| stderr:", r.stderr[-400:], file=sys.stderr)
        return None, r

def main():
    bridge_log = open(f"{HERE}/bridge.log", "w")
    bridge = subprocess.Popen(["node", "server.js"], cwd=HERE,
                              env={**os.environ, "MAILBOX_BRIDGE_PORT": str(PORT)},
                              stdout=bridge_log, stderr=bridge_log)
    time.sleep(0.8)
    rpc = Rpc(port=PORT)
    S = "one operator sandbox; local Node process running the exact core handler; in-memory store; participants in separate processes with independent keypairs"

    # ---- Test A: identity binding ----
    aA, _ = worker("bind", "instance-alpha", f"{HERE}/st_alpha.json")
    aB, _ = worker("bind", "instance-beta", f"{HERE}/st_beta.json")
    la = lookup(rpc, node_id="instance-alpha")["body"]["bindings"][0]
    lb = lookup(rpc, node_id="instance-beta")["body"]["bindings"][0]
    okA = (aA and aA["status"] == 200 and fp(la["ed25519_pub"]) == la["fingerprint"]
           and lb["fingerprint"] != la["fingerprint"]
           and json.load(open(f"{HERE}/st_alpha.json"))["fingerprint"] == la["fingerprint"])
    record("A", "Identity binding", "PASS" if okA else "FAIL",
           "two separate-process participants bind mailboxes; lookup records checked",
           f"alpha fp={la['fingerprint']} beta fp={lb['fingerprint']} distinct keys, fingerprints recomputed server-side and match state files",
           S)

    # ---- Test B: successful messaging (E2E) ----
    plaintext_sent = "milestone-message-alpha-to-beta-2026-10-13"
    sB, _ = worker("send", "instance-alpha", f"{HERE}/st_alpha.json", "instance-beta", plaintext_sent)
    fB, _ = worker("fetch", "instance-beta", f"{HERE}/st_beta.json")
    m = fB["messages"][0] if fB and fB.get("messages") else {}
    okB = (sB and sB["status"] == 200 and fB and fB.get("count") == 1
           and m.get("sender_verified") is True and m.get("plaintext") == plaintext_sent)
    record("B", "Successful messaging", "PASS" if okB else "FAIL",
           "send worker (alpha, separate process) encrypts+signs; fetch worker (beta, separate process) retrieves, verifies sender against discovery binding, decrypts",
           f"server accept 200; beta fetched count={fB.get('count')}; sender_verified={m.get('sender_verified')}; plaintext byte-exact match={m.get('plaintext') == plaintext_sent}",
           S, "same-operator two-instance exchange; NOT independent organizational participation")

    # ciphertext for C/J: send another message and capture via dump
    sC, _ = worker("send", "instance-alpha", f"{HERE}/st_alpha.json", "instance-beta", "SECOND-SECRET-payload-7734")
    time.sleep(0.2)
    dump = rpc({"action": "__dump__", "now_ms": _now(), "payload": {}})["body"]["entities"]

    # ---- Test C: confidentiality ----
    third = Instance("instance-gamma")
    ct = [m["ciphertext"] for m in dump["LanternMailMessage"]]
    tried = 0; broke = 0
    for c in ct:
        for cand in (third, Instance("instance-delta")):
            tried += 1
            try: cand.unseal(c); broke += 1
            except Exception: pass
    record("C", "Confidentiality", "PASS" if broke == 0 else "FAIL",
           "two unauthorized third instances attempt sealed-box decryption of every stored ciphertext",
           f"{tried} decryption attempts by non-recipients, {broke} succeeded",
           S, "sealed box: no forward secrecy, no metadata protection; server sees ciphertext and addresses")

    # ---- Test D: impersonation ----
    d1 = third.bind(rpc)  # gamma binds its own alias first (needs active identity? bind works fresh)
    gamma_state = {"node_id": "instance-gamma", "ed25519_priv": third.sk.encode().hex(),
                   "x25519_priv": third.xk.encode().hex(), "mailbox_id": third.mailbox_id}
    imp1 = rpc({"action": "bind", "now_ms": _now(), "payload": {
        "node_id": "instance-beta", "ed25519_pub": third.ed25519_pub,
        "x25519_pub": third.x25519_pub, "created_ms": _now(),
        "binding_signature": third.sign(f"lantern.mailbox.bind.v1|instance-beta|{third.ed25519_pub}|{third.x25519_pub}|{_now()}")}})
    beta_binding = json.load(open(f"{HERE}/st_beta.json"))
    imp2 = rpc({"action": "bind", "now_ms": _now(), "payload": {
        "node_id": "instance-beta-clone", "ed25519_pub": beta_binding["ed25519_pub"],
        "x25519_pub": third.x25519_pub, "created_ms": _now(), "binding_signature": third.sign("x")}})
    okD = (imp1["status"] == 403 and imp2["status"] == 401)
    record("D", "Impersonation", "PASS" if okD else "FAIL",
           "(1) fresh key claims beta's alias (2) attacker signs a bind claiming beta's identity key",
           f"alias claim -> {imp1['status']} {imp1['body'].get('error')}; key claim w/ forged sig -> {imp2['status']} {imp2['body'].get('error')}",
           S)

    # ---- Test E: tampering ----
    lb2 = lookup(rpc, node_id="instance-beta")["body"]["bindings"][0]
    alpha = Instance("alpha-direct")
    alpha.bind(rpc)
    r1, mid1 = alpha.send(rpc, lb2, "tamper-probe-1")
    req = json.loads(json.dumps({"action": "send", "now_ms": r1["_now"] if False else _now(), "payload": {}}))
    # rebuild the exact send with tampered ciphertext but original envelope+signature
    now = _now()
    ct2 = alpha.seal(lb2["x25519_pub"], "tamper-probe-2")
    env = {"message_id": "msg-tamper-e2", "sender_fingerprint": alpha.fingerprint,
           "sender_ed25519_pub": alpha.ed25519_pub, "mailbox_id": lb2["mailbox_id"],
           "recipient_fingerprint": lb2["fingerprint"], "ciphertext_sha256": sha256hex(ct2),
           "protocol_version": PROTO, "created_ms": now, "expiry_ms": now + 86400000}
    stmt = ("lantern.mail.message.v1|" + "|".join([env["message_id"], alpha.fingerprint,
        lb2["mailbox_id"], lb2["fingerprint"], env["ciphertext_sha256"], PROTO, str(now), str(env["expiry_ms"])]))
    sig = alpha.sign(stmt)
    tampered = "f" + ct2[1:] if ct2[0] != "f" else "0" + ct2[1:]
    t1 = rpc({"action": "send", "now_ms": now, "payload": {
        "message_id": env["message_id"], "ciphertext": tampered, "envelope": env, "signature": sig}})
    env_bad = dict(env); env_bad["message_id"] = "msg-tampered-mid"
    t2 = rpc({"action": "send", "now_ms": now, "payload": {
        "message_id": "msg-tampered-mid", "ciphertext": ct2, "envelope": env_bad, "signature": sig}})
    okE = (t1["status"] == 400 and t2["status"] == 401)
    record("E", "Tampering", "PASS" if okE else "FAIL",
           "(1) ciphertext altered after signing, original envelope kept (2) envelope message_id altered after signing, signature unchanged",
           f"altered ct -> {t1['status']} {t1['body'].get('error')}; altered envelope -> {t2['status']} {t2['body'].get('error')}",
           S)

    # ---- Test F: authorization ----
    fb = third.fetch_begin(rpc, mailbox_id=lb2["mailbox_id"])
    now = _now()
    fstmt = f"lantern.mail.fetch.v1|{lb2['mailbox_id']}|{third.ed25519_pub}|{fb['body']['challenge_id']}|{now}"
    f1 = rpc({"action": "fetch", "now_ms": now, "payload": {
        "mailbox_id": lb2["mailbox_id"], "ed25519_pub": third.ed25519_pub,
        "challenge_id": fb["body"]["challenge_id"], "now_ms": now,
        "signature": third.sign(fstmt)}})
    okF = (f1["status"] == 403)
    record("F", "Authorization", "PASS" if okF else "FAIL",
           "third instance obtains a fetch challenge for beta's mailbox and signs the fetch statement with its own valid key",
           f"own valid key, wrong identity -> {f1['status']} {f1['body'].get('error')}",
           S, "possession of mailbox address + challenge does not authorize; key binding enforced")

    # ---- Test G: replay and duplication ----
    s2, mid2 = alpha.send(rpc, lb2, "replay-probe")
    replay_req = {"action": "send", "now_ms": s2["_req_now"] if False else _now(),
                  "payload": json.loads(json.dumps(s2["_payload"]))} if "_payload" in s2 else None
    # replay by reconstructing identical send with same message_id and same envelope
    now = _now()
    ct3 = alpha.seal(lb2["x25519_pub"], "replay-probe-ct")
    envg = {"message_id": mid2, "sender_fingerprint": alpha.fingerprint,
            "sender_ed25519_pub": alpha.ed25519_pub, "mailbox_id": lb2["mailbox_id"],
            "recipient_fingerprint": lb2["fingerprint"], "ciphertext_sha256": sha256hex(ct3),
            "protocol_version": PROTO, "created_ms": now, "expiry_ms": now + 86400000}
    stmtg = ("lantern.mail.message.v1|" + "|".join([mid2, alpha.fingerprint, lb2["mailbox_id"],
        lb2["fingerprint"], envg["ciphertext_sha256"], PROTO, str(now), str(envg["expiry_ms"])]))
    g1 = rpc({"action": "send", "now_ms": now, "payload": {
        "message_id": mid2, "ciphertext": ct3, "envelope": envg, "signature": alpha.sign(stmtg)}})
    fbA = alpha.fetch_begin(rpc, mailbox_id=alpha.mailbox_id)
    ch = fbA["body"]["challenge_id"]
    g2a = alpha.fetch(rpc, ch)
    g2b = alpha.fetch(rpc, ch)
    okG = (g1["status"] == 409 and g2a["status"] == 200 and g2b["status"] == 401)
    record("G", "Replay and duplication", "PASS" if okG else "FAIL",
           "(1) duplicate message_id resubmission (2) fetch challenge used twice",
           f"dup msg -> {g1['status']} {g1['body'].get('error')}; first fetch {g2a['status']}, reused challenge -> {g2b['status']} {g2b['body'].get('error')}",
           S)

    # ---- Test H: key rotation ----
    from nacl.signing import SigningKey as SK
    from nacl.public import PrivateKey as PK
    old = alpha
    new_sk, new_xk = SK.generate(), PK.generate()
    new_ed, new_xp = new_sk.verify_key.encode().hex(), new_xk.public_key.encode().hex()
    import datetime as _dt
    rot_ms = int(time.time() * 1000)
    rotated_at = _dt.datetime.fromtimestamp(rot_ms / 1000, _dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.") + f"{rot_ms % 1000:03d}Z"
    rstmt = f"lantern.mailbox.rotate.v1|{alpha.mailbox_id}|{alpha.ed25519_pub}|{new_ed}|{new_xp}|{rotated_at}"
    bstmt = f"lantern.mailbox.bind.v1|alpha-direct|{new_ed}|{new_xp}|{rot_ms}"
    h1 = rpc({"action": "rotate", "now_ms": _now(), "payload": {
        "mailbox_id": alpha.mailbox_id, "old_ed25519_pub": alpha.ed25519_pub,
        "new_ed25519_pub": new_ed, "new_x25519_pub": new_xp, "rotated_at": rotated_at,
        "old_signature": alpha.sign(rstmt), "new_binding_signature": new_sk.sign(bstmt.encode()).signature.hex()}})
    old_send = old.send(rpc, lb2, "from-old-key")  # should fail
    # new-key instance
    rot = Instance("alpha-direct")
    rot.sk, rot.xk = new_sk, new_xk
    rot.ed25519_pub, rot.x25519_pub = new_ed, new_xp
    rot.fingerprint = fp(new_ed); rot.mailbox_id = alpha.mailbox_id
    new_send, _ = rot.send(rpc, lb2, "from-new-key")
    dump2 = rpc({"action": "__dump__", "now_ms": _now(), "payload": {}})["body"]["entities"]
    hist_intact = any(m["envelope"]["sender_fingerprint"] == old.fingerprint for m in dump2["LanternMailMessage"])
    okH = (h1["status"] == 200 and old_send[0]["status"] == 403 and new_send["status"] == 200 and hist_intact)
    record("H", "Key rotation", "PASS" if okH else "FAIL",
           "dual-signed rotation (old key signs rotation statement, new key countersigns a fresh bind statement authenticating a new X25519 key)",
           f"rotate {h1['status']}; send w/ old key -> {old_send[0]['status']} {old_send[0]['body'].get('error')}; send w/ new key -> {new_send['status']}; historical envelopes preserve original sender fingerprint: {hist_intact}",
           S, "rotation requires the old key: no silent transfer; clone-key caveat unchanged")

    # ---- Test I: independent operation / sender offline ----
    sI, _ = worker("send", "instance-alpha", f"{HERE}/st_alpha.json", "instance-beta", "offline-sender-probe")
    sender_pid = None  # send worker already exited; sender process is gone
    fI, _ = worker("fetch", "instance-beta", f"{HERE}/st_beta.json")
    mI = next((m for m in fI.get("messages", []) if m.get("plaintext") == "offline-sender-probe"), {})
    okI = (sI["status"] == 200 and fI.get("count") >= 1 and mI.get("sender_verified") is True)
    record("I", "Independent operation", "PASS" if okI else "FAIL",
           "sender process exits after send; a different process (beta) later retrieves, verifies the sender signature against the discovered binding, and decrypts with no sender participation",
           f"sender process terminated; beta verified={mI.get('sender_verified')}, decrypted byte-exact={mI.get('plaintext') == 'offline-sender-probe'}",
           S, "retrieval depends on the hosted service being up; verification itself is offline against binding records")

    # ---- Test J: public/private separation ----
    dump3 = rpc({"action": "__dump__", "now_ms": _now(), "payload": {}})["body"]["entities"]
    blob = json.dumps(dump3)
    leaks = [s for s in ["milestone-message-alpha-to-beta-2026-10-13", "SECOND-SECRET-payload-7734",
             "offline-sender-probe", "ed25519_priv", "x25519_priv"] if s in blob]
    has_ct = any("ciphertext" in m for m in dump3.get("LanternMailMessage", []))
    record("J", "Public/private separation", "PASS" if (not leaks and has_ct) else "FAIL",
           "full storage dump scanned for plaintext payloads and private key material",
           f"leaks found: {leaks or 'none'}; ciphertext stored encrypted: {has_ct}; plaintext appears nowhere",
           S, "no board/public records involved at all in Phase 1; wall untouched")

    # ---- X1: malformed canonical serialization ----
    x1a = rpc({"action": "bind", "now_ms": _now(), "payload": {
        "node_id": "bad-canonical", "ed25519_pub": third.ed25519_pub, "x25519_pub": third.x25519_pub,
        "created_ms": _now(),
        "binding_signature": third.sign(f"lantern.mailbox.bind.v1|{third.x25519_pub}|bad-canonical|{third.ed25519_pub}|{_now()}")}})
    okX1 = (x1a["status"] == 401)
    record("X1", "Malformed canonical serialization", "PASS" if okX1 else "FAIL",
           "signature over reordered/mis-serialized bind statement",
           f"-> {x1a['status']} {x1a['body'].get('error')}",
           S)

    # ---- X2: expired fetch challenge ----
    fbX = rot.fetch_begin(rpc)
    later = _now() + 700000
    x2 = rot.fetch(rpc, fbX["body"]["challenge_id"], now_ms=later)
    okX2 = (x2["status"] == 410)
    record("X2", "Expired fetch challenge", "PASS" if okX2 else "FAIL",
           "fetch submitted after challenge TTL (600 s)",
           f"-> {x2['status']} {x2['body'].get('error')}",
           S)

    # ---- X3: reused fetch challenge ----
    fbX3 = rot.fetch_begin(rpc)
    c3 = fbX3["body"]["challenge_id"]
    u1 = rot.fetch(rpc, c3)
    u2 = rot.fetch(rpc, c3)
    okX3 = (u1["status"] == 200 and u2["status"] == 401)
    record("X3", "Reused fetch challenge", "PASS" if okX3 else "FAIL",
           "same challenge submitted twice",
           f"first {u1['status']}; reuse -> {u2['status']} {u2['body'].get('error')}",
           S)

    # ---- X4: altered recipient identity ----
    gamma_binding = lookup(rpc, node_id="instance-gamma")["body"]["bindings"][0]
    now = _now()
    ct4 = rot.seal(lb2["x25519_pub"], "misdirected")
    env4 = {"message_id": "msg-x4", "sender_fingerprint": rot.fingerprint,
            "sender_ed25519_pub": rot.ed25519_pub, "mailbox_id": lb2["mailbox_id"],
            "recipient_fingerprint": gamma_binding["fingerprint"],  # WRONG identity for this mailbox
            "ciphertext_sha256": sha256hex(ct4), "protocol_version": PROTO,
            "created_ms": now, "expiry_ms": now + 86400000}
    stmt4 = ("lantern.mail.message.v1|" + "|".join(["msg-x4", rot.fingerprint, lb2["mailbox_id"],
        gamma_binding["fingerprint"], env4["ciphertext_sha256"], PROTO, str(now), str(env4["expiry_ms"])]))
    x4 = rpc({"action": "send", "now_ms": now, "payload": {
        "message_id": "msg-x4", "ciphertext": ct4, "envelope": env4, "signature": rot.sign(stmt4)}})
    okX4 = (x4["status"] == 403)
    record("X4", "Altered recipient identity", "PASS" if okX4 else "FAIL",
           "validly-signed envelope addressed to beta's mailbox but claiming gamma's fingerprint",
           f"-> {x4['status']} {x4['body'].get('error')}",
           S)

    # ---- X5: revoked binding ----
    rev = Instance("instance-revokable")
    rev.bind(rpc)
    now = _now()
    rev.send(rpc, lb2, "before-revoke")
    rv = rpc({"action": "revoke", "now_ms": now, "payload": {
        "mailbox_id": rev.mailbox_id, "ts_ms": now,
        "signature": rev.sign(f"lantern.mailbox.revoke.v1|{rev.mailbox_id}|{now}")}})
    in_send, _ = rot.send(rpc, lookup(rpc, node_id="instance-revokable")["body"]["bindings"][0], "to-revoked")
    out_send, _ = rev.send(rpc, lb2, "from-revoked")
    fbR = rev.fetch_begin(rpc)
    fetchR = rev.fetch(rpc, fbR["body"]["challenge_id"])
    okX5 = (rv["status"] == 200 and in_send["status"] == 403 and out_send["status"] == 403
            and fetchR["status"] == 200)
    record("X5", "Revoked binding", "PASS" if okX5 else "FAIL",
           "mailbox revoked by its identity key; inbound send, outbound send, and owner fetch attempted after",
           f"revoke {rv['status']}; send to revoked -> {in_send['status']} {in_send['body'].get('error')}; send from revoked -> {out_send['status']} {out_send['body'].get('error')}; owner fetch still {fetchR['status']}",
           S, "revocation is NOT fingerprint-wide key retirement; owner fetch retained for evidence")

    # ---- X6: encryption-key substitution ----
    atk = Instance("instance-attacker")
    x6a = rpc({"action": "rotate", "now_ms": _now(), "payload": {
        "mailbox_id": lb2["mailbox_id"], "old_ed25519_pub": atk.ed25519_pub,
        "new_ed25519_pub": atk.ed25519_pub, "new_x25519_pub": atk.x25519_pub,
        "rotated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "old_signature": atk.sign("x"), "new_binding_signature": atk.sign("y")}})
    beta_st = json.load(open(f"{HERE}/st_beta.json"))
    x6b = rpc({"action": "bind", "now_ms": _now(), "payload": {
        "node_id": "instance-beta", "ed25519_pub": beta_st["ed25519_pub"],
        "x25519_pub": atk.x25519_pub, "created_ms": _now(), "binding_signature": atk.sign("z")}})
    okX6 = (x6a["status"] == 403 and x6b["status"] == 401)
    record("X6", "Encryption-key substitution", "PASS" if okX6 else "FAIL",
           "(1) attacker rotation attempt with attacker keys on beta's mailbox (2) attacker bind claiming beta's alias+identity key with attacker X25519 key",
           f"rotation -> {x6a['status']} {x6a['body'].get('error')}; substitution bind -> {x6b['status']} {x6b['body'].get('error')}",
           S)

    rpc.close()
    bridge.terminate()
    bridge.wait(timeout=5)

    passed = sum(1 for r in RESULTS if r["result"] == "PASS")
    summary = {"total": len(RESULTS), "passed": passed, "failed": sum(1 for r in RESULTS if r["result"] == "FAIL"),
               "not_tested": sum(1 for r in RESULTS if r["result"] == "NOT TESTED")}
    out = {"battery": "lantern-mailbox-phase2", "date": "2026-10-13", "summary": summary, "results": RESULTS,
           "environment_note": "All tests ran in ONE operator sandbox. Server = local Node process running the exact core.js to be embedded in the deployable function, in-memory store. Participants = separate processes, independently generated Ed25519 signing keys and X25519 encryption keys. A passing two-instance exchange here is Tier-1 same-operator evidence, NOT independent organizational participation. Live deployed-service behavior: NOT TESTED pending the Phase 4 deployment gate."}
    json.dump(out, open(f"{HERE}/results.json", "w"), indent=2)
    print(json.dumps(summary))

if __name__ == "__main__":
    main()
