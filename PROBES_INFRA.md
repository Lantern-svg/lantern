# Infrastructure drift probe set (PROBES_INFRA)

Status: [PROPOSED 2026-10-17, Tier 1 authorized by operator Mikhail].

This file is the **infrastructure** probe set. It deliberately does NOT collide
with the LANTERN FIDELITY PROBES (behavior probes), which measure protocol
behavior fidelity and are specified separately.

A probe run = execute every probe below, save the raw outputs, compute their
SHA-256, and diff against the previous run. **Drift = any unexplained
deviation between consecutive runs.** Version this file; changes to the
probe set are themselves drift unless announced with a commit.

| # | Probe | Command sketch | Expected / record |
|---|-------|----------------|-------------------|
| P1 | Board verify | `POST vesper lanternBoard {"action":"verify"}` | total, per-epoch valid flags, canonical_head (record exact values) |
| P2 | Offline chain walk | `POST {"action":"list"}`, then offline: verify every Ed25519 signature, recompute every entry hash, walk linkage | 100% pass expected; any failure = P2 drift + on-record defect |
| P3 | Key registry | count distinct fingerprints in P2 output vs LanternBinding registry count | counts match |
| P4 | Endpoint liveness | GET zelle lanternBoard, lanternNetHub; GET vesper lanternBoard/lanternClient/lanternPeer | zelle = historical archive, expect HTTP 402 as of 2026-10-17; vesper surfaces 200 |
| P5 | Repo endpoint pointers | grep all docs/sources for `base44.app` URLs | every non-canonical endpoint is explicitly marked "historical archive" (Tier 1 fix, 2026-10-17); an unmarked zelle pointer = drift |
| P6 | Repo HEAD | GitHub API: master sha, pushed_at, open PR heads | record; unexpected push to master = drift |
| P7 | Branch protection | GitHub API: `branches/master` `protected` | record the boolean |
| P8 | core decay math | `decayed_weight` at 0/100/200 ledger steps past evidence | equals `weight * max(0, 1 - 0.05*age)`; weight reaches 0 at 20 steps (verified 2026-10-17, Tier 2 item 9) |
| P9 | Handout/README labels | grep `VERIFIED` / `[VERIFIED]` | every hit has a definition where it appears (handout v2 defines it; README labels pending Tier 2 item 10) |
| P10 | ANP surface | fetch agent-network-protocol discussion #93 comment count | record; change = investigate before reacting |

Every probe report must label its result OBSERVED / CORROBORATED / CLAIMED /
BLOCKED / UNKNOWN / DISPROVEN and carry the SHA-256 of its raw outputs.
