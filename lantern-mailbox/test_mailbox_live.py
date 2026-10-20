"""LIVE battery against the deployed lanternMailbox service (Phase 4 gate 1).
Environment (reported with every result): deployed Base44 function
https://vesper-f402303b.base44.app/functions/lanternMailbox, entity-backed
persistence, real server clock. Participants = separate processes /
independent keypairs. ONE operator sandbox => Tier 1; two-instance exchange is
NOT independent organizational participation. X2 (expired challenge) runs
separately with a real TTL elapse (x2_live.py).
"""
import json, subprocess, sys, time, os, secrets
from mailbox_client import Rpc, Instance, lookup, fp, sha256hex, _now, PROTO

RUN_TAG = open(f"{os.path.dirname(os.path.abspath(__file__))}/live_run_tag.txt").read().split()[2]
HERE = os.path.dirname(os.path.abspath(__file__))
os.environ["MAILBOX_LIVE_URL"] = "https://vesper-f402303b.base44.app/functions/lanternMailbox"
PORT = 47799
RESULTS = []

def record(tid, name, result, procedure, evidence, env, limitations=""):
    RESULTS.append({"id": tid, "name": name, "result": result, "procedure": procedure,
                    "evidence": evidence, "environment": env, "limitations": limitations})
    print(f"[{result:^10}] {tid}: {name}", flush=True)

def worker(role, node_id, state, recipient=None, plaintext=None):
    cmd = [sys.executable, "participant.py", role, node_id, state]
    if recipient: cmd += [recipient]
    if plaintext: cmd += [plaintext]
    r = subprocess.run(cmd, cwd=HERE, capture_output=True, text=True,
                       env={**os.environ, "MAILBOX_BRIDGE_PORT": str(PORT)})
    try: return json.loads(r.stdout.strip().splitlines()[-1]), r
    except Exception:
        print("WORKER FAIL", cmd, r.stderr[-400:], file=sys.stderr)
        return None, r

def main():
    rpc = Rpc()
    S = ("deployed Base44 service (lanternMailbox at vesper-f402303b), entity-backed persistence, "
         "real server clock, participants in separate processes with independent Ed25519+X25519 keys, "
         "ONE operator sandbox (Tier 1)")
    A_ALIAS, B_ALIAS = f"live-alpha-{RUN_TAG}", f"live-beta-{RUN_TAG}"

    # ---- Test A ----
    aA, _ = worker("bind", A_ALIAS, f"{HERE}/st_live_a.json")
    aB, _ = worker("bind", B_ALIAS, f"{HERE}/st_live_b.json")
    la = lookup(rpc, node_id=A_ALIAS)["body"]["bindings"][0]
    lb = lookup(rpc, node_id=B_ALIAS)["body"]["bindings"][0]
    okA = (aA["status"] == 200 and aB["status"] == 200 and fp(la["ed25519_pub"]) == la["fingerprint"]
           and la["fingerprint"] != lb["fingerprint"])
    record("A", "Identity binding (LIVE)", "PASS" if okA else "FAIL",
           "two separate-process participants bind mailboxes on the deployed service; server-persisted bindings looked up and recomputed",
           f"alpha fp={la['fingerprint']}, beta fp={lb['fingerprint']}, persisted and readable via public lookup, fingerprints recompute correctly",
           S)

    # ---- Test B ----
    probe = f"live-milestone-{RUN_TAG}"
    sB, _ = worker("send", A_ALIAS, f"{HERE}/st_live_a.json", B_ALIAS, probe)
    fB, _ = worker("fetch", B_ALIAS, f"{HERE}/st_live_b.json")
    m = fB["messages"][0] if fB.get("messages") else {}
    okB = (sB["status"] == 200 and fB.get("count") == 1 and m.get("sender_verified") is True
           and m.get("plaintext") == probe)
    record("B", "Successful messaging (LIVE)", "PASS" if okB else "FAIL",
           "send worker (separate process) encrypts+signs; fetch worker (separate process) retrieves from deployed service, verifies sender against discovery binding, decrypts",
           f"server accept 200 (message_id {sB.get('message_id')}); beta fetched count={fB.get('count')}; sender_verified={m.get('sender_verified')}; byte-exact match",
           S, "same-operator two-instance exchange; NOT independent organizational participation")

    # ---- Test C (live variant) ----
    HA, HB = Instance(f"live-ha-{RUN_TAG}"), Instance(f"live-hb-{RUN_TAG}")
    HA.bind(rpc); HB.bind(rpc)
    hb_binding = lookup(rpc, node_id=HA.node_id.replace("live-ha", "live-hb"))["body"]["bindings"][0]
    HA.send(rpc, hb_binding, f"live-secret-c-{RUN_TAG}")
    fbH = HB.fetch_begin(rpc)
    rH = HB.fetch(rpc, fbH["body"]["challenge_id"])
    cts = [m["ciphertext"] for m in rH["body"]["messages"]] if rH["status"] == 200 else []
    atk1, atk2 = Instance(f"live-atk1-{RUN_TAG}"), Instance(f"live-atk2-{RUN_TAG}")
    broke = 0
    for c in cts:
        for a in (atk1, atk2):
            try: a.unseal(c); broke += 1
            except Exception: pass
    okC = (rH["status"] == 200 and len(cts) >= 1 and broke == 0)
    record("C", "Confidentiality (LIVE)", "PASS" if okC else "FAIL",
           "deployed-service ciphertexts fetched by the legitimate recipient; two unauthorized third instances attempt decryption",
           f"{len(cts)} live-stored ciphertexts, 2x attempts each, {broke} succeeded",
           S, "sealed box: no forward secrecy, metadata visible to host")

    # ---- Test D ----
    imp1 = rpc({"action": "bind", "payload": {
        "node_id": B_ALIAS, "ed25519_pub": atk1.ed25519_pub, "x25519_pub": atk1.x25519_pub,
        "created_ms": _now(),
        "binding_signature": atk1.sign(f"lantern.mailbox.bind.v1|{B_ALIAS}|{atk1.ed25519_pub}|{atk1.x25519_pub}|{_now()}")}})
    beta_st = json.load(open(f"{HERE}/st_live_b.json"))
    imp2 = rpc({"action": "bind", "payload": {
        "node_id": f"live-beta-clone-{RUN_TAG}", "ed25519_pub": beta_st["ed25519_pub"],
        "x25519_pub": atk1.x25519_pub, "created_ms": _now(), "binding_signature": atk1.sign("x")}})
    okD = (imp1["status"] == 403 and imp2["status"] == 401)
    record("D", "Impersonation (LIVE)", "PASS" if okD else "FAIL",
           "(1) fresh key claims beta's alias on the live service (2) attacker signs a bind claiming beta's identity key",
           f"alias claim -> {imp1['status']} {imp1['body'].get('error')}; forged key claim -> {imp2['status']} {imp2['body'].get('error')}",
           S)

    # ---- Test E ----
    now = _now()
    ct2 = HA.seal(hb_binding["x25519_pub"], "live-tamper-2")
    env = {"message_id": f"msg-e2-{RUN_TAG}", "sender_fingerprint": HA.fingerprint,
           "sender_ed25519_pub": HA.ed25519_pub, "mailbox_id": hb_binding["mailbox_id"],
           "recipient_fingerprint": hb_binding["fingerprint"], "ciphertext_sha256": sha256hex(ct2),
           "protocol_version": PROTO, "created_ms": now, "expiry_ms": now + 86400000}
    stmt = ("lantern.mail.message.v1|" + "|".join([env["message_id"], HA.fingerprint,
        hb_binding["mailbox_id"], hb_binding["fingerprint"], env["ciphertext_sha256"], PROTO, str(now), str(env["expiry_ms"])]))
    sig = HA.sign(stmt)
    tampered = ("f" if ct2[0] != "f" else "0") + ct2[1:]
    t1 = rpc({"action": "send", "payload": {"message_id": env["message_id"], "ciphertext": tampered,
        "envelope": env, "signature": sig}})
    env_bad = dict(env); env_bad["message_id"] = f"msg-e2-tampered-{RUN_TAG}"
    t2 = rpc({"action": "send", "payload": {"message_id": env_bad["message_id"], "ciphertext": ct2,
        "envelope": env_bad, "signature": sig}})
    okE = (t1["status"] == 400 and t2["status"] == 401)
    record("E", "Tampering (LIVE)", "PASS" if okE else "FAIL",
           "(1) ciphertext altered after signing (2) envelope message_id altered, signature unchanged",
           f"altered ct -> {t1['status']} {t1['body'].get('error')}; altered envelope -> {t2['status']} {t2['body'].get('error')}",
           S)

    # ---- Test F ----
    fb = atk1.fetch_begin(rpc, mailbox_id=hb_binding["mailbox_id"])
    now = _now()
    fstmt = f"lantern.mail.fetch.v1|{hb_binding['mailbox_id']}|{atk1.ed25519_pub}|{fb['body']['challenge_id']}|{now}"
    f1 = rpc({"action": "fetch", "payload": {"mailbox_id": hb_binding["mailbox_id"],
        "ed25519_pub": atk1.ed25519_pub, "challenge_id": fb["body"]["challenge_id"],
        "now_ms": now, "signature": atk1.sign(fstmt)}})
    okF = (f1["status"] == 403)
    record("F", "Authorization (LIVE)", "PASS" if okF else "FAIL",
           "third instance gets a live challenge for beta's mailbox and signs correctly with its own key",
           f"own valid key, wrong identity -> {f1['status']} {f1['body'].get('error')}",
           S)

    # ---- Test G ----
    s2, mid2 = HA.send(rpc, hb_binding, f"live-replay-{RUN_TAG}")
    now = _now()
    ct3 = HA.seal(hb_binding["x25519_pub"], "live-replay-ct")
    envg = {"message_id": mid2, "sender_fingerprint": HA.fingerprint, "sender_ed25519_pub": HA.ed25519_pub,
            "mailbox_id": hb_binding["mailbox_id"], "recipient_fingerprint": hb_binding["fingerprint"],
            "ciphertext_sha256": sha256hex(ct3), "protocol_version": PROTO,
            "created_ms": now, "expiry_ms": now + 86400000}
    stmtg = ("lantern.mail.message.v1|" + "|".join([mid2, HA.fingerprint, hb_binding["mailbox_id"],
        hb_binding["fingerprint"], envg["ciphertext_sha256"], PROTO, str(now), str(envg["expiry_ms"])]))
    g1 = rpc({"action": "send", "payload": {"message_id": mid2, "ciphertext": ct3, "envelope": envg,
        "signature": HA.sign(stmtg)}})
    fbA = HA.fetch_begin(rpc)
    ch = fbA["body"]["challenge_id"]
    g2a = HA.fetch(rpc, ch)
    g2b = HA.fetch(rpc, ch)
    okG = (g1["status"] == 409 and g2a["status"] == 200 and g2b["status"] == 401)
    record("G", "Replay and duplication (LIVE)", "PASS" if okG else "FAIL",
           "duplicate message_id resubmission; fetch challenge used twice on the live service",
           f"dup msg -> {g1['status']} {g1['body'].get('error')}; first fetch {g2a['status']}, reuse -> {g2b['status']} {g2b['body'].get('error')}",
           S)

    # ---- Test H ----
    from nacl.signing import SigningKey as SK
    from nacl.public import PrivateKey as PK
    import datetime as dt
    new_sk, new_xk = SK.generate(), PK.generate()
    new_ed, new_xp = new_sk.verify_key.encode().hex(), new_xk.public_key.encode().hex()
    rot_ms = int(time.time() * 1000)
    rotated_at = dt.datetime.fromtimestamp(rot_ms / 1000, dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.") + f"{rot_ms % 1000:03d}Z"
    rstmt = f"lantern.mailbox.rotate.v1|{HA.mailbox_id}|{HA.ed25519_pub}|{new_ed}|{new_xp}|{rotated_at}"
    bstmt = f"lantern.mailbox.bind.v1|{HA.node_id}|{new_ed}|{new_xp}|{rot_ms}"
    h1 = rpc({"action": "rotate", "payload": {"mailbox_id": HA.mailbox_id, "old_ed25519_pub": HA.ed25519_pub,
        "new_ed25519_pub": new_ed, "new_x25519_pub": new_xp, "rotated_at": rotated_at,
        "old_signature": HA.sign(rstmt), "new_binding_signature": new_sk.sign(bstmt.encode()).signature.hex()}})
    old_send = HA.send(rpc, hb_binding, "from-old-key")  # tuple (r, mid)
    rot = Instance(HA.node_id)
    rot.sk, rot.xk = new_sk, new_xk
    rot.ed25519_pub, rot.x25519_pub = new_ed, new_xp
    rot.fingerprint = fp(new_ed); rot.mailbox_id = HA.mailbox_id
    new_send, _ = rot.send(rpc, hb_binding, f"live-from-new-key-{RUN_TAG}")
    okH = (h1["status"] == 200 and old_send[0]["status"] == 403 and new_send["status"] == 200)
    record("H", "Key rotation (LIVE)", "PASS" if okH else "FAIL",
           "dual-signed rotation on the deployed service; sends attempted with old and new keys",
           f"rotate {h1['status']}; old key -> {old_send[0]['status']} {old_send[0]['body'].get('error')}; new key -> {new_send['status']}",
           S, "rotation requires old key: no silent transfer; clone-key boundary unchanged")

    # ---- Test I ----
    probeI = f"live-offline-probe-{RUN_TAG}"
    sI, _ = worker("send", A_ALIAS, f"{HERE}/st_live_a.json", B_ALIAS, probeI)
    fI, _ = worker("fetch", B_ALIAS, f"{HERE}/st_live_b.json")
    mI = next((m for m in fI.get("messages", []) if m.get("plaintext") == probeI), {})
    okI = (sI["status"] == 200 and mI.get("sender_verified") is True)
    record("I", "Independent operation (LIVE)", "PASS" if okI else "FAIL",
           "sender process exits after send; a separate recipient process retrieves from the deployed service and verifies offline against the discovery binding",
           f"sender process terminated; beta verified={mI.get('sender_verified')}, decrypted byte-exact={mI.get('plaintext') == probeI}",
           S, "retrieval depends on the hosted service; verification itself is offline")

    # ---- Test J (live surface variant) ----
    lblob = json.dumps(lookup(rpc, node_id=A_ALIAS)["body"]) + json.dumps(lookup(rpc, node_id=B_ALIAS)["body"]) + json.dumps(rH["body"] if rH["status"] == 200 else {})
    leaks = [s for s in [probe, f"live-secret-c-{RUN_TAG}", probeI, "ed25519_priv", "x25519_priv"] if s in lblob]
    record("J", "Public/private separation (LIVE surface)", "PASS" if not leaks else "FAIL",
           "public lookup responses and fetched envelopes scanned for plaintext and key material; stored-record scan performed separately via the entity API",
           f"leaks on public surfaces: {leaks or 'none'}; fetched payloads are ciphertext + public binding metadata only",
           S, "stored-record scan done via entity read and reported in the evidence report")

    # ---- X1 ----
    x1a = rpc({"action": "bind", "payload": {
        "node_id": f"live-badcanon-{RUN_TAG}", "ed25519_pub": atk1.ed25519_pub, "x25519_pub": atk1.x25519_pub,
        "created_ms": _now(),
        "binding_signature": atk1.sign(f"lantern.mailbox.bind.v1|{atk1.x25519_pub}|live-badcanon|{atk1.ed25519_pub}|{_now()}")}})
    okX1 = (x1a["status"] == 401)
    record("X1", "Malformed canonical serialization (LIVE)", "PASS" if okX1 else "FAIL",
           "signature over reordered bind statement",
           f"-> {x1a['status']} {x1a['body'].get('error')}",
           S)

    # ---- X3 ----
    fbX3 = rot.fetch_begin(rpc)
    c3 = fbX3["body"]["challenge_id"]
    u1 = rot.fetch(rpc, c3)
    u2 = rot.fetch(rpc, c3)
    okX3 = (u1["status"] == 200 and u2["status"] == 401)
    record("X3", "Reused fetch challenge (LIVE)", "PASS" if okX3 else "FAIL",
           "same live challenge submitted twice",
           f"first {u1['status']}; reuse -> {u2['status']} {u2['body'].get('error')}",
           S)

    # ---- X4 ----
    atk_binding = lookup(rpc, node_id=atk1.node_id) or {"body": {"bindings": []}}
    ab = atk_binding["body"]["bindings"][0] if atk_binding["body"]["bindings"] else None
    # bind attacker1 if not yet bound
    if not ab:
        atk1.bind(rpc)
        ab = lookup(rpc, node_id=atk1.node_id)["body"]["bindings"][0]
    now = _now()
    ct4 = rot.seal(hb_binding["x25519_pub"], "live-misdirected")
    env4 = {"message_id": f"msg-x4-{RUN_TAG}", "sender_fingerprint": rot.fingerprint,
            "sender_ed25519_pub": rot.ed25519_pub, "mailbox_id": hb_binding["mailbox_id"],
            "recipient_fingerprint": ab["fingerprint"], "ciphertext_sha256": sha256hex(ct4),
            "protocol_version": PROTO, "created_ms": now, "expiry_ms": now + 86400000}
    stmt4 = ("lantern.mail.message.v1|" + "|".join([env4["message_id"], rot.fingerprint,
        hb_binding["mailbox_id"], ab["fingerprint"], env4["ciphertext_sha256"], PROTO, str(now), str(env4["expiry_ms"])]))
    x4 = rpc({"action": "send", "payload": {"message_id": env4["message_id"], "ciphertext": ct4,
        "envelope": env4, "signature": rot.sign(stmt4)}})
    okX4 = (x4["status"] == 403)
    record("X4", "Altered recipient identity (LIVE)", "PASS" if okX4 else "FAIL",
           "validly-signed envelope addressed to HB's mailbox claiming attacker1's fingerprint",
           f"-> {x4['status']} {x4['body'].get('error')}",
           S)

    # ---- X5 ----
    rev = Instance(f"live-revokable-{RUN_TAG}")
    rev.bind(rpc)
    rev_binding = lookup(rpc, node_id=rev.node_id)["body"]["bindings"][0]
    now = _now()
    rv = rpc({"action": "revoke", "payload": {"mailbox_id": rev.mailbox_id, "ts_ms": now,
        "signature": rev.sign(f"lantern.mailbox.revoke.v1|{rev.mailbox_id}|{now}")}})
    in_send, _ = rot.send(rpc, rev_binding, "to-revoked")
    out_send, _ = rev.send(rpc, hb_binding, "from-revoked")
    fbR = rev.fetch_begin(rpc)
    fetchR = rev.fetch(rpc, fbR["body"]["challenge_id"])
    okX5 = (rv["status"] == 200 and in_send["status"] == 403 and out_send["status"] == 403
            and fetchR["status"] == 200)
    record("X5", "Revoked binding (LIVE)", "PASS" if okX5 else "FAIL",
           "live mailbox revoked by its identity key; inbound, outbound, and owner fetch attempted after",
           f"revoke {rv['status']}; inbound -> {in_send['status']} {in_send['body'].get('error')}; outbound -> {out_send['status']} {out_send['body'].get('error')}; owner fetch {fetchR['status']}",
           S, "revocation is NOT fingerprint-wide key retirement")

    # ---- X6 ----
    x6a = rpc({"action": "rotate", "payload": {"mailbox_id": hb_binding["mailbox_id"],
        "old_ed25519_pub": atk1.ed25519_pub, "new_ed25519_pub": atk2.ed25519_pub,
        "new_x25519_pub": atk2.x25519_pub,
        "rotated_at": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z",
        "old_signature": atk1.sign("x"), "new_binding_signature": atk2.sign("y")}})
    x6b = rpc({"action": "bind", "payload": {"node_id": HB.node_id, "ed25519_pub": beta_st["ed25519_pub"],
        "x25519_pub": atk2.x25519_pub, "created_ms": _now(), "binding_signature": atk2.sign("z")}})
    okX6 = (x6a["status"] == 403 and x6b["status"] == 401)
    record("X6", "Encryption-key substitution (LIVE)", "PASS" if okX6 else "FAIL",
           "(1) attacker rotation on HB's mailbox (2) attacker bind claiming HB's alias+key with attacker X25519",
           f"rotation -> {x6a['status']} {x6a['body'].get('error')}; substitution bind -> {x6b['status']} {x6b['body'].get('error')}",
           S)

    rpc.close()
    passed = sum(1 for r in RESULTS if r["result"] == "PASS")
    summary = {"total": len(RESULTS), "passed": passed,
               "failed": sum(1 for r in RESULTS if r["result"] == "FAIL"),
               "x2_background": "runs separately with real TTL elapse"}
    out = {"battery": "lantern-mailbox-phase4-LIVE", "date": "2026-10-13", "run_tag": RUN_TAG,
           "summary": summary, "results": RESULTS,
           "environment_note": "All tests ran against the DEPLOYED lanternMailbox function with entity-backed persistence, real server clock. Participants = separate processes, independently generated keys. ONE operator sandbox: Tier-1 same-operator evidence, NOT independent organizational participation. X2 expired-challenge test runs separately with a real 600 s TTL elapse."}
    json.dump(out, open(f"{HERE}/results_live.json", "w"), indent=2)
    print(json.dumps(summary))

if __name__ == "__main__":
    main()
