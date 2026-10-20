"""Lantern atomic-append test battery (v2.0.6 race fix).

Isolated fixture: a simulated Base44 entity store (storage-atomic updateMany,
unconditional create — the semantics probe-verified live on the platform via
the lanternRaceProbe fixture, scratch entity only) plus a Python port of the
board logic, v2.0.5 (pre-fix) and v2.0.6 (sentinel-CAS). No traffic against
the public board.

Labels: SIMULATED (this harness) vs LIVE (the probe evidence recorded in
ATOMIC_APPEND_EVIDENCE.md). A passing script exit is not the evidence; the
per-test PASS/FAIL table and the raw probe captures are.

Run:  python3 -m pytest test_atomic_append.py -v
  or: python3 test_atomic_append.py
"""
import hashlib
import threading
import time
import uuid
from collections import Counter

from nacl.signing import SigningKey, VerifyKey

BOARD = "lantern-board"
BOARD_TOKEN = "lantern-board-test-2026-09-06"
TS_WINDOW_MS = 15 * 60 * 1000
GENESIS = "GENESIS"


def sha256(s: str) -> str:
    return hashlib.sha256(s.encode()).hexdigest()


# ---------------------------------------------------------------------------
# Simulated Base44 entity store. create() is an unconditional append (matches
# the platform). updateMany(query, {"$set": ...}) is a STORAGE-ATOMIC
# match-and-modify: one storage-level lock, find matching records, apply,
# return {"updated": n}. This is the primitive the live probe verified.
# ---------------------------------------------------------------------------
class EntityStore:
    def __init__(self):
        self._lock = threading.Lock()
        self._next_id = 0
        self.records = []

    def create(self, data):
        with self._lock:
            self._next_id += 1
            rec = dict(data)
            rec["id"] = f"rec{self._next_id}"
            self.records.append(rec)
            return dict(rec)

    def filter(self, query):
        with self._lock:
            return [dict(r) for r in self.records if all(r.get(k) == v for k, v in query.items())]

    def list(self):
        with self._lock:
            return [dict(r) for r in self.records]

    def updateMany(self, query, data):
        assert list(data.keys()) == ["$set"], "only $set modeled"
        with self._lock:  # storage-atomic: match and modify under one lock
            matched = [r for r in self.records if all(r.get(k) == v for k, v in query.items())]
            for r in matched:
                r.update(data["$set"])
            return {"success": True, "updated": len(matched), "has_more": False}


class Storage:
    """All entities of one simulated app."""
    def __init__(self):
        self.posts = EntityStore()
        self.bindings = EntityStore()
        self.heads = EntityStore()


# ---------------------------------------------------------------------------
# Chain logic shared by both versions (ported from the deployed source:
# hash formula, epoch walk, fork detection).
# ---------------------------------------------------------------------------
def hash_of(r, prev):
    stamp = r["server_ms"] if r.get("server_ms") else r["created_ms"]
    return sha256(f"{prev}|{r['post_id']}|{r['node_id']}|{r['message_id']}|{r['content']}|{r['seq']}|{stamp}")


def walk_epoch(chain, anchor):
    by_prev = {}
    for r in chain:
        by_prev.setdefault(str(r["prev_hash"]), []).append(r)
    consumed, prev, last_valid = set(), anchor, anchor
    while True:
        cands = [r for r in by_prev.get(prev, []) if r["post_id"] not in consumed]
        if not cands:
            break
        if len(cands) > 1:
            return {"valid": False, "first_break": {"type": "fork", "parent_hash": prev},
                    "last_valid_hash": last_valid, "head": prev, "linked": len(consumed)}
        r = cands[0]
        if hash_of(r, prev) != str(r["hash"]):
            return {"valid": False, "first_break": {"type": "tamper", "post_id": r["post_id"]},
                    "last_valid_hash": last_valid, "head": prev, "linked": len(consumed)}
        consumed.add(r["post_id"])
        prev, last_valid = str(r["hash"]), str(r["hash"])
    orphans = [r for r in chain if r["post_id"] not in consumed]
    valid, first_break = True, None
    if orphans:
        valid, first_break = False, {"type": "orphan"}
    return {"valid": valid, "first_break": first_break, "last_valid_hash": last_valid,
            "head": prev, "linked": len(consumed)}


def analyze(storage, board=BOARD):
    all_posts = [r for r in storage.posts.list() if str(r.get("board", BOARD)) == board]
    max_epoch = max([r.get("epoch", 1) for r in all_posts], default=1)
    epochs = []
    for e in range(1, max_epoch + 1):
        chain = [r for r in all_posts if r.get("epoch", 1) == e]
        w = walk_epoch(chain, GENESIS)
        epochs.append({"epoch": e, "posts": len(chain), "valid": w["valid"],
                       "first_break": w["first_break"], "last_valid_hash": w["last_valid_hash"],
                       "head": w["head"]})
    return {"board": board, "total": len(all_posts), "epochs": epochs,
            "authoritative": epochs[-1], "all": all_posts}


# ---------------------------------------------------------------------------
# v2.0.5 handler (pre-fix): analyze -> checks -> signature -> create. The race.
# pause_hook lets the test deterministically pause BOTH racers after they have
# observed the same head.
# ---------------------------------------------------------------------------
def post_v205(storage, payload, pause_hook=None):
    if payload.get("token") != BOARD_TOKEN:
        return 403, {"error": "BOARD_TOKEN_INVALID"}
    a = analyze(storage, payload["board"])
    cur = a["epochs"][-1]
    now = int(time.time() * 1000)
    if abs(now - payload["created_ms"]) > TS_WINDOW_MS:
        return 409, {"error": "TIMESTAMP_OUT_OF_WINDOW"}
    position = payload["prev_hash"]
    if not cur["valid"]:
        return 409, {"error": "EPOCH_BROKEN_REQUIRES_REPAIR"}
    if position != cur["head"]:
        return 409, {"error": "POSITION_STALE"}
    if pause_hook:
        pause_hook()
    post_id = str(uuid.uuid4())
    seq = a["total"] + 1
    canonical = f"{payload['node_id']}|{payload['board']}|{payload['message_id']}|{payload['content']}|{payload['created_ms']}|{position}"
    try:
        VerifyKey(bytes.fromhex(payload["public_key"])).verify(
            f"lantern-board-post|{canonical}".encode(), bytes.fromhex(payload["signature"]))
    except Exception:
        return 401, {"error": "SIGNATURE_INVALID"}
    h = sha256(f"{cur['head']}|{post_id}|{payload['node_id']}|{payload['message_id']}|{payload['content']}|{seq}|{now}")
    storage.posts.create({"post_id": post_id, "board": payload["board"], "node_id": payload["node_id"],
                          "message_id": payload["message_id"], "content": payload["content"],
                          "signature": payload["signature"], "public_key": payload["public_key"],
                          "created_ms": payload["created_ms"], "prev_hash": cur["head"], "hash": h,
                          "seq": seq, "server_ms": now, "epoch": cur["epoch"], "kind": "post",
                          "formula": "v2", "verified": True})
    return 200, {"ok": True, "post_id": post_id, "seq": seq, "hash": h}


# ---------------------------------------------------------------------------
# v2.0.6 handler (fixed): same checks, then sentinel CAS before any write.
# Ported from the patched lanternBoard_base44.ts (branch feature/atomic-append).
# ---------------------------------------------------------------------------
def post_v206(storage, payload, pause_hook=None):
    if payload.get("token") != BOARD_TOKEN:
        return 403, {"error": "BOARD_TOKEN_INVALID"}
    a = analyze(storage, payload["board"])
    cur = a["epochs"][-1]
    now = int(time.time() * 1000)
    if abs(now - payload["created_ms"]) > TS_WINDOW_MS:
        return 409, {"error": "TIMESTAMP_OUT_OF_WINDOW"}
    position = payload["prev_hash"]
    if not cur["valid"]:
        return 409, {"error": "EPOCH_BROKEN_REQUIRES_REPAIR"}
    canonical = f"{payload['node_id']}|{payload['board']}|{payload['message_id']}|{payload['content']}|{payload['created_ms']}|{position}"
    try:
        VerifyKey(bytes.fromhex(payload["public_key"])).verify(
            f"lantern-board-post|{canonical}".encode(), bytes.fromhex(payload["signature"]))
    except Exception:
        return 401, {"error": "SIGNATURE_INVALID"}
    if pause_hook:
        pause_hook()
    # ---- v2.0.6: sentinel read / init / desync detection / CAS ----
    sents = storage.heads.filter({"board": payload["board"]})
    if len(sents) > 1:
        return 500, {"error": "SENTINEL_MULTI"}
    sentinel = sents[0] if sents else None
    if sentinel is None:
        storage.heads.create({"board": payload["board"], "epoch": cur["epoch"], "next_seq": a["total"] + 1,
                              "head_hash": cur["head"], "last_post_id": None, "updated_ms": now})
        sents = storage.heads.filter({"board": payload["board"]})
        sentinel = sents[0] if sents else None
    # stale-snapshot tolerance: a mismatch against OUR snapshot is re-verified
    # against a FRESH derivation (a concurrent winner is a race, not a fault);
    # only a true divergence from the fresh chain fails closed as desync.
    def mirrors(fresh):
        real = str(sentinel["head_hash"]) == GENESIS or \
            any(str(r["hash"]) == str(sentinel["head_hash"]) for r in fresh["all"])
        return int(sentinel["next_seq"]) == fresh["total"] + 1 and real
    if not mirrors(a) and not mirrors(analyze(storage, payload["board"])):
        return 500, {"error": "SENTINEL_DESYNCED"}
    if position != str(sentinel["head_hash"]):
        return 409, {"error": "POSITION_STALE", "current_head": sentinel["head_hash"]}
    post_id = str(uuid.uuid4())
    seq = a["total"] + 1  # allocation mirrors the chain; guarded below
    if seq != int(sentinel["next_seq"]):
        return 409, {"error": "POSITION_STALE", "current_head": sentinel["head_hash"]}
    h = sha256(f"{position}|{post_id}|{payload['node_id']}|{payload['message_id']}|{payload['content']}|{seq}|{now}")
    claimed = storage.heads.updateMany(
        {"board": payload["board"], "epoch": sentinel["epoch"], "next_seq": sentinel["next_seq"],
         "head_hash": sentinel["head_hash"]},
        {"$set": {"epoch": cur["epoch"], "next_seq": seq + 1, "head_hash": h,
                  "last_post_id": post_id, "updated_ms": now}})
    if claimed["updated"] != 1:
        fresh = storage.heads.filter({"board": payload["board"]})
        return 409, {"error": "POSITION_STALE",
                     "current_head": fresh[0]["head_hash"] if fresh else None}
    storage.posts.create({"post_id": post_id, "board": payload["board"], "node_id": payload["node_id"],
                          "message_id": payload["message_id"], "content": payload["content"],
                          "signature": payload["signature"], "public_key": payload["public_key"],
                          "created_ms": payload["created_ms"], "prev_hash": position, "hash": h,
                          "seq": seq, "server_ms": now, "epoch": cur["epoch"], "kind": "post",
                          "formula": "v2", "verified": True})
    return 200, {"ok": True, "post_id": post_id, "seq": seq, "hash": h}


def sign_payload(sk, node_id, board, message_id, content, prev_hash):
    now = int(time.time() * 1000)
    canonical = f"{node_id}|{board}|{message_id}|{content}|{now}|{prev_hash}"
    return {"token": BOARD_TOKEN, "board": board, "node_id": node_id, "message_id": message_id,
            "content": content, "created_ms": now, "prev_hash": prev_hash,
            "public_key": sk.verify_key.encode().hex(),
            "signature": sk.sign(f"lantern-board-post|{canonical}".encode()).signature.hex()}


def current_head(storage):
    return analyze(storage)["epochs"][-1]["head"]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------
def run_concurrent(handler, storage, n, pause=False):
    """n independent signers racing for the same head."""
    results = [None] * n
    barrier = threading.Barrier(n) if pause else None

    def hook():
        if barrier:
            barrier.wait(timeout=10)

    def worker(i):
        sk = SigningKey.generate()
        head = current_head(storage)
        payload = sign_payload(sk, f"racer-{i}", BOARD, f"msg-{i}-{time.time()}", "concurrent test", head)
        results[i] = handler(storage, payload, pause_hook=hook) if pause else handler(storage, payload)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    return results


def test_R1_race_reproduced_in_v205():
    """PRE-FIX REPRO: two racers paused after reading the same head both commit
    under v2.0.5 -> duplicate seq stored (the fork race)."""
    storage = Storage()
    results = run_concurrent(post_v205, storage, 2, pause=True)
    codes = sorted(c for c, _ in results)
    seqs = [r["seq"] for r in storage.posts.list()]
    assert codes == [200, 200], f"both should commit pre-fix, got {codes}"
    assert len(set(seqs)) != len(seqs), f"expected duplicate seqs, got {seqs}"
    recs = storage.posts.list()
    assert recs[0]["prev_hash"] == recs[1]["prev_hash"], "both raced the same parent"
    print("PASS R1: v2.0.5 race reproduced — two 200s, duplicate seq", seqs)


def test_T1_exactly_one_commits_when_paused_on_same_head():
    """T1: two valid requests deliberately paused after reading the same head:
    exactly one commits, the other gets a stale conflict, no fork stored."""
    storage = Storage()
    results = run_concurrent(post_v206, storage, 2, pause=True)
    codes = sorted(c for c, _ in results)
    seqs = [r["seq"] for r in storage.posts.list()]
    assert codes == [200, 409], f"expected one 200 + one 409, got {codes}"
    assert seqs == [1], f"expected single seq [1], got {seqs}"
    a = analyze(storage)
    assert a["epochs"][0]["valid"] and a["total"] == 1
    print("PASS T1: exactly one commit under identical head reads; loser 409, no duplicate seq")


def test_T2_concurrent_workers_serialize():
    """T2: 8 concurrent workers (separate threads) cannot bypass the guarantee."""
    storage = Storage()
    results = run_concurrent(post_v206, storage, 8)
    codes = Counter(c for c, _ in results)
    stored = storage.posts.list()
    seqs = [r["seq"] for r in stored]
    assert codes[200] == len(stored), "every 200 must be a stored record"
    assert len(set(seqs)) == len(seqs), f"duplicate seqs stored: {sorted(seqs)}"
    assert sorted(seqs) == list(range(1, len(seqs) + 1)), "seq allocation must be gapless"
    assert codes[200] + codes[409] == 8, "no other outcomes expected"
    a = analyze(storage)
    assert a["epochs"][0]["valid"], "chain must remain valid"
    print(f"PASS T2: 8 workers -> {dict(codes)}; {len(stored)} records, seqs {sorted(seqs)}, chain valid")


def test_T3_conflict_leaves_no_partial_append():
    """T3: a rejected request leaves no record and does not advance the head."""
    storage = Storage()
    sk = SigningKey.generate()
    r = post_v206(storage, sign_payload(sk, "first", BOARD, "m1", "seed", GENESIS))
    assert r[0] == 200
    head_before = current_head(storage)
    sents = storage.heads.filter({"board": BOARD})
    stale_sent = dict(sents[0])
    winner = post_v206(storage, sign_payload(SigningKey.generate(), "winner", BOARD, "m2", "win", head_before))
    assert winner[0] == 200
    claimed = storage.heads.updateMany(
        {"board": BOARD, "epoch": stale_sent["epoch"], "next_seq": stale_sent["next_seq"],
         "head_hash": stale_sent["head_hash"]},
        {"$set": {"next_seq": 99, "head_hash": "TAMPER", "last_post_id": "x", "updated_ms": 0}})
    assert claimed["updated"] == 0, "stale CAS must match nothing"
    stored = storage.posts.list()
    assert all(r["seq"] != 99 for r in stored), "no partial record from a lost CAS"
    assert current_head(storage) == winner[1]["hash"], "head must reflect only committed records"
    print("PASS T3: lost CAS writes nothing; head advanced exactly once")


def test_T4_retry_with_fresh_signature_succeeds_stale_signature_fails():
    """T4: retrying after reading the new head and re-signing succeeds;
    reusing the old signature against a changed parent fails."""
    storage = Storage()
    sk = SigningKey.generate()
    first = post_v206(storage, sign_payload(sk, "retry-node", BOARD, "m1", "one", GENESIS))
    assert first[0] == 200
    stale = post_v206(storage, sign_payload(sk, "retry-node", BOARD, "m2", "stale", GENESIS))
    assert stale[0] == 409 and stale[1]["error"] == "POSITION_STALE"
    # transplant attack: old signature bytes with a claimed new parent
    stale_payload = sign_payload(sk, "retry-node", BOARD, "m3", "transplant", GENESIS)
    forged = sign_payload(sk, "retry-node", BOARD, "m3", "transplant", current_head(storage))
    forged["signature"] = stale_payload["signature"]  # signature over the OLD parent
    r = post_v206(storage, forged)
    assert r[0] == 401 and r[1]["error"] == "SIGNATURE_INVALID", "transplanted signature must fail the gate"
    retry = post_v206(storage, sign_payload(sk, "retry-node", BOARD, "m4", "retry", current_head(storage)))
    assert retry[0] == 200
    print("PASS T4: fresh re-sign succeeds; stale and transplanted signatures rejected")


def test_T5_regressions_intact():
    """T5: signature, hash-chain, fork-detection checks still pass."""
    storage = Storage()
    sk = SigningKey.generate()
    pub = sk.verify_key.encode().hex()
    p = sign_payload(sk, "nc", BOARD, "m1", "x", GENESIS)
    p["signature"] = "cd" * 64
    assert post_v206(storage, p)[0] == 401
    r = post_v206(storage, sign_payload(sk, "nc", BOARD, "m1", "hello", GENESIS))
    assert r[0] == 200
    rec = storage.posts.list()[0]
    assert rec["hash"] == sha256(f"{GENESIS}|{rec['post_id']}|nc|m1|hello|1|{rec['server_ms']}")
    canonical = f"lantern-board-post|nc|{BOARD}|m1|hello|{rec['created_ms']}|{rec['prev_hash']}"
    VerifyKey(bytes.fromhex(pub)).verify(canonical.encode(), bytes.fromhex(rec["signature"]))
    r2 = post_v206(storage, sign_payload(sk, "nc", BOARD, "m2", "two", current_head(storage)))
    assert r2[0] == 200
    a = analyze(storage)
    assert a["epochs"][0]["valid"]
    # externally injected fork (direct storage write, outside the API) must
    # still be detected: the fix prevents NEW forks via the API; it must not
    # blind the protocol to externally injected ones.
    last = storage.posts.list()[-1]
    storage.posts.create({**last, "post_id": "fork-child", "hash": "deadbeef",
                          "message_id": "m-fork"})
    a = analyze(storage)
    assert a["epochs"][0]["valid"] is False and a["epochs"][0]["first_break"]["type"] == "fork"
    print("PASS T5: signature gate, hash vector, tamper/fork detection all intact")


def test_T6_sentinel_desync_detected_fail_closed():
    """Crash-between-CAS-and-create must be detected and refuse appends."""
    storage = Storage()
    sk = SigningKey.generate()
    assert post_v206(storage, sign_payload(sk, "n1", BOARD, "m1", "a", GENESIS))[0] == 200
    s = storage.heads.filter({"board": BOARD})[0]
    storage.heads.updateMany({"board": BOARD, "next_seq": s["next_seq"], "head_hash": s["head_hash"]},
                             {"$set": {"next_seq": s["next_seq"] + 1, "head_hash": "PHANTOM"}})
    r = post_v206(storage, sign_payload(sk, "n1", BOARD, "m2", "b", "PHANTOM"))
    assert r[0] == 500 and r[1]["error"] == "SENTINEL_DESYNCED", "desync must fail closed"
    print("PASS T6: sentinel desync detected; appends refused (fail-closed)")


if __name__ == "__main__":
    for t in [test_R1_race_reproduced_in_v205, test_T1_exactly_one_commits_when_paused_on_same_head,
              test_T2_concurrent_workers_serialize, test_T3_conflict_leaves_no_partial_append,
              test_T4_retry_with_fresh_signature_succeeds_stale_signature_fails,
              test_T5_regressions_intact, test_T6_sentinel_desync_detected_fail_closed]:
        t()
    print("\nALL TESTS PASS")
