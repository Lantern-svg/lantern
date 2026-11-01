#!/usr/bin/env python3
"""evolution_ledger.py — the ε organ (v0.1).

Implements the adoption-note law: W_d = f(W_{d-1}, E_d) + ε_d
Every state transition is recorded with causal attribution: how much of the delta
came from evidence and how much from bounded perturbation (ε).
ε is observable, bounded [0,1], and never truth: a transition with ε >= threshold
is recorded as FRICTION_DOMINANT and cannot silently pass as evidence.

Append-only JSONL, hash-chained, verifiable offline. No cell authorizes itself:
every record carries an explicit authority block.
"""
import json, hashlib, os, time

LABELS = {"OBSERVED", "VERIFIED", "CORROBORATED", "CLAIMED", "INFERRED", "PROPOSED", "UNRESOLVED", "BLOCKED", "DISPROVEN"}
EPSILON_MAX = 1.0
FRICTION_FLAG = 0.5


def _h(obj):
    return hashlib.sha256(json.dumps(obj, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


class EvolutionLedger:
    def __init__(self, path="evolution_ledger.jsonl"):
        self.path = path

    def _last(self):
        if not os.path.exists(self.path):
            return "GENESIS"
        last = None
        with open(self.path) as f:
            for line in f:
                line = line.strip()
                if line:
                    last = json.loads(line)
        return last["record_hash"] if last else "GENESIS"

    def record(self, *, agent, transition, w_prev, w_new, f, evidence, epsilon, authority):
        if not isinstance(epsilon, dict):
            raise ValueError("epsilon must be an object")
        eps = float(epsilon.get("magnitude", -1))
        if not (0.0 <= eps <= EPSILON_MAX):
            raise ValueError(f"epsilon unbounded ({eps}); refusing to record")
        if not epsilon.get("source"):
            raise ValueError("epsilon.source required (observable perturbation)")
        for e in evidence:
            if e.get("label") not in LABELS:
                raise ValueError(f"bad evidence label: {e.get('label')}")
        if authority.get("authorized") is not True:
            raise ValueError("authority_check failed: not authorized")

        checks = {
            "evidence_check": len(evidence) > 0,
            "provenance_check": all(e.get("label") != "VERIFIED" or e.get("citation") for e in evidence),
            "contradiction_check": not any(e.get("label") == "DISPROVEN" for e in evidence),
            "authority_check": True,
        }
        regime = "FRICTION_DOMINANT" if eps >= FRICTION_FLAG else "EVIDENCE_DOMINANT"
        rec = {
            "ts": int(time.time() * 1000), "agent": agent, "transition": transition,
            "f": f, "w_prev_hash": _h(w_prev), "w_new_hash": _h(w_new),
            "evidence": evidence, "epsilon": {"magnitude": eps, **epsilon},
            "authority": authority, "checks": checks, "regime": regime,
            "prev_hash": self._last(),
        }
        rec["record_hash"] = _h(rec)
        with open(self.path, "a") as fh:
            fh.write(json.dumps(rec, sort_keys=True) + "\n")
        return rec

    def verify(self):
        if not os.path.exists(self.path):
            return [], True
        recs, ok = [], True
        with open(self.path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                r = json.loads(line)
                body = {k: v for k, v in r.items() if k != "record_hash"}
                good = _h(body) == r["record_hash"] and (not recs or r["prev_hash"] == recs[-1]["record_hash"])
                ok = ok and good
                r["valid"] = good
                recs.append(r)
        return recs, ok

    @staticmethod
    def attribute(rec):
        eps = rec["epsilon"]["magnitude"]
        return {"evidence_share": round(1 - eps, 3), "epsilon_share": round(eps, 3),
                "regime": rec["regime"], "evidence_n": len(rec["evidence"])}


if __name__ == "__main__":
    import sys
    p = sys.argv[1] if len(sys.argv) > 1 else "/tmp/evo_demo.jsonl"
    if os.path.exists(p):
        os.remove(p)
    L = EvolutionLedger(p)
    L.record(
        agent="lantern-net-sbx3",
        transition="adopt shared-understanding atlas as coordination surface",
        w_prev={"coord": "scattered"}, w_new={"coord": "atlas+recall"},
        f="merge concept map",
        evidence=[
            {"claim": "atlas sha acb1d3e0 published", "label": "OBSERVED", "citation": "acb1d3e0"},
            {"claim": "recall audit 53/53 sigs VALID", "label": "VERIFIED", "citation": "wall seq 54"},
        ],
        epsilon={"magnitude": 0.1, "source": "naming choices in atlas", "bounds": "design convention"},
        authority={"authorized": True, "by": "operator directive 2026-11-01", "scope": "framework"},
    )
    L.record(
        agent="lantern-net-sbx3",
        transition="replace HTTP compute-relay coordination with wall task-board",
        w_prev={"compute_channel": "net hub"}, w_new={"compute_channel": "wall WORK/CLAIM/CONFIRM"},
        f="substitute transport after UA-block discovery",
        evidence=[{"claim": "hub rejects every lantern-net/ UA variant (5 tested) while board accepts",
                   "label": "OBSERVED", "citation": "probe 2026-11-01"}],
        epsilon={"magnitude": 0.7, "source": "transport redesign under uncertainty", "bounds": "single probe sample"},
        authority={"authorized": True, "by": "operator directive 2026-11-01", "scope": "network"},
    )
    recs, ok = L.verify()
    print(f"records: {len(recs)} | chain VALID: {ok}")
    for r in recs:
        print("  ", r["transition"][:60], "->", EvolutionLedger.attribute(r))
    # fail-closed proof
    try:
        L.record(agent="x", transition="t", w_prev={}, w_new={}, f="f", evidence=[],
                 epsilon={"magnitude": 4.2, "source": "unbounded"}, authority={"authorized": True})
        print("FAIL: unbounded epsilon was recorded")
    except ValueError as e:
        print("fail-closed proof OK:", e)
