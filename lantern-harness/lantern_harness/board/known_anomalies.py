"""Known-anomalies allowlist for chain-level board verification.

The verifier cannot (and must not) decide from prose whether a fork was
legitimately repaired. This table is the explicit, reviewable record of
which chain anomalies the operator and participants have acknowledged.
Each row names the anomalous entry hashes AND the entry hashes of the
on-chain repair records that acknowledge them. The verifier confirms the
acknowledging records actually exist on the retrieved chain; a row whose
acknowledgements are missing does NOT excuse the anomaly.

The table's own hash (sha256 of its canonical JSON) is reported in every
verify result so reviewers can see exactly what was allowlisted.

Rows are append-only in spirit: editing history here is as visible as a
board entry, because the table hash changes.

Row kinds:
  fork      - a parent with more than one child, plus the seqs the race
              consumed, acknowledged by on-chain repair records.
  reanchor  - a legitimate epoch re-anchor: one child continuing from an
              earlier parent entry while starting a HIGHER epoch.
"""

from __future__ import annotations

import hashlib
import json

# Full 64-hex hashes only. Confirmed against the live board 2026-11-03
# (70 records, head seq 70 epoch 2) before being recorded here.
KNOWN_ANOMALIES: list[dict] = [
    {
        "kind": "fork",
        "parent": "ecbc7c69429a4ee9f9c118d0c4c99a2949e7541f9255c587f933011e53db9eed",
        "children": [
            "930cbf229f38c4fb5c229e0894645f4a05f1869d81c1cd6c8d67447741d2f58d",
            "4ea92cff85938e4faf92d491ad235e1fb9cebe28dc50fcc306a14f5da75402df",
        ],
        "duplicate_seqs": [23],
        "skipped_seqs": [24],
        "acknowledged_by": [
            # epoch-2 repair attempt (seq 25)
            "e766d54efa102c668c5af9226096655311767eef022185608efea553d21965bd",
            # fork + repair record (seq 26)
            "4e4d85abe66d280d635b9051799378843646c19a5a4946f51758cf34cc2d1330",
            # closeout directive executed (seq 29)
            "6b23e3e2a227144e3cb1205d680d2d211652e679c93312f22e700a8ec8e86b97",
            # Node C epoch-1 fork acknowledgment (seq 44)
            "90d018ff9f41b7df64c66fe48e37992778fe4858cc095c3988ccc0fd868d56f8",
        ],
        "note": "epoch-1 witness race 2026-10-09: two independent writers 154 ms apart, both position-bound to seq-22 head",
    },
    {
        "kind": "reanchor",
        "parent": "ecbc7c69429a4ee9f9c118d0c4c99a2949e7541f9255c587f933011e53db9eed",
        "child": "e766d54efa102c668c5af9226096655311767eef022185608efea553d21965bd",
        "epoch": 2,
        "note": "epoch 2 re-anchored at the last pre-fork entry (seq 22) per repair protocol",
    },
]


def table_hash(table: list[dict] | None = None) -> str:
    """sha256 over the canonical JSON of the table, so reviewers can pin
    exactly which allowlist produced a verify result."""
    canonical = json.dumps(
        KNOWN_ANOMALIES if table is None else table,
        sort_keys=True, separators=(",", ":"), ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()
