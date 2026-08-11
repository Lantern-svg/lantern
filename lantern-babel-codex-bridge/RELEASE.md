# Lantern Release Checklist

Status document only. Nothing in this file publishes, tags, or pushes
anything. It exists so the operator can see, in one place, every item that
gates `PUBLIC_RELEASE_READY: YES`, where each item lives in the repo, and
which ones require an explicit operator decision versus which are already
satisfied.

## 1. License

- **Location:** `pyproject.toml:11` (`license = { text = "MIT" }`),
  `README.md` "License" section, `LICENSE` file at repo root.
- **LICENSE file:** present (MIT).
- **Status:** `[x]` Operator authorized MIT for the public release
  (2026-08-09). `pyproject.toml`, `README.md`, and `LICENSE` are
  consistent.

## 2. Version / Release Identifier

- **Location:** `pyproject.toml:3` (`version = "0.82"`),
  `src/lantern/__init__.py:201` (`__version__ = "0.82"`) — internally
  consistent.
- **Immutable identifier:** annotated git tag `v0.82`, pointing at
  commit `ed03734ab1c7602df7815fb0934188df4e726aa2`. Confirmed present
  on the public remote via `git ls-remote --tags`.
- **Status:** `[x]` Public, externally citable release identifier
  exists: `v0.82` at the commit above.

## 3. Public Repository / Distribution Location

- **Location:** `https://github.com/Lantern-svg/lantern` (GitHub
  account `Lantern-svg`, authenticated via `gh` device-flow auth,
  repo created with `gh repo create --public`).
- **Status:** `[x]` Selected and live. Independently verified twice by
  fresh-cloning that exact URL into a clean directory, using a fresh
  virtualenv unrelated to this project's own `.venv`, confirming commit
  `ed03734ab1c7602df7815fb0934188df4e726aa2` and tag `v0.82`, running
  `pip install .`, starting `bootstrap_node`, confirming `/health`, and
  running the full test suite (240 passed each time).

## 4. Reproducibility Instructions

- **Location:** `EXTERNAL_BOOTSTRAP.md` sections 3-6 (install, run a node,
  connect a second node, observation flow).
- **Status:** `[x]` Verified this session by actually running the
  documented steps in a disposable clean venv against an extracted copy of
  the release content (install, full test suite, create/observe/evidence/
  snapshot, kill process, restart in a separate interpreter, confirm
  identical belief value read from disk). Not merely asserted.

## 5. External Bootstrap Instructions

- **Location:** `EXTERNAL_BOOTSTRAP.md` (full file; written for an
  operator who has never seen the code).
- **Status:** `[x]` Present and accurate as of this audit. No overclaims
  found; one minor terminology-overlap note (`EXTERNAL_BOOTSTRAP.md`'s
  plain-English "Codex" vs `ARCHITECTURE.md`'s richer semantic-graph
  description — the real `CodexModule` in `core.py` is a flat dict).

## 6. Security Warning (unauthenticated HTTP transport)

- **Location:** `EXTERNAL_BOOTSTRAP.md` section 12 ("Security Warning").
- **Status:** `[x]` Already present and accurate: states plain HTTP, no
  TLS, no authentication, no replay protection; explicitly says this is
  not safe on the public internet; states a private network/VPN only
  narrows who can reach the port, it does not add authentication or
  encryption.

## 7. Inter-Instance Compatibility Test Results

- **Test files:** `tests/test_two_process_bootstrap.py` (real two-OS-process
  boundary, subprocess + real TCP socket) and
  `tests/test_two_instance_integration.py` (in-process two-instance
  protocol path).
- **Release-gate regression added this session:**
  `tests/test_two_process_bootstrap.py::test_release_gate_full_chain_blocks_protected_state_mutation`
  — walks join → identity → handshake → limited-capability negotiation →
  harmless `OBSERVATION_SHARE` → adversarial `CODEX_UPDATE` attempt, over a
  real subprocess/HTTP boundary, and asserts from an independent re-read of
  the receiving node's on-disk Chronicle that exactly one Observation was
  recorded, zero Evidence was created, and the `CODEX_UPDATE` attempt was
  rejected and left no trace in the Chronicle.
- **Live gate run (this session, disposable, not part of the test suite):**
  a real two-process run (`bootstrap_node` subprocess + a driver script
  acting as the external participant) completed
  `INDEPENDENT_INSTANCE → RENDEZVOUS/JOIN → IDENTITY_OBSERVED →
  PROTOCOL_COMPATIBILITY → HANDSHAKE → LIMITED_PARTICIPANT →
  HARMLESS_TEST_OBSERVATION → LOCAL_EVALUATION → CHRONICLE_RECORD →
  VERIFICATION` and returned `INTER_INSTANCE_TEST_PASSED`. A `CODEX_UPDATE`
  probe sent on the same connection was rejected
  (`Capability unavailable: codex_update`) and left no Evidence/Codex
  trace. Full JSON transcript retained only in the disposable
  `/tmp/lantern-inter-instance-test/` verification directory, not in this
  repo.
- **Status:** `[x]` PASSED — see
  `LANTERN — INTER-INSTANCE VALIDATION` report delivered alongside this
  file for full field-by-field detail.

## 8. Cross-Machine Validation

- **Requested:** a genuine second physical/virtual machine ("Machine B")
  reaching a first machine ("Machine A") over a real network boundary,
  not merely two subprocesses on the same host via loopback.
- **Environment check performed this session:** this sandbox is a single
  Docker container (`cat /proc/1/cgroup` confirms a container cgroup;
  `nodes(action=status)` returned zero paired nodes; no `docker`/`podman`/
  `lxc` binaries are present to launch a second container from inside
  this one). There is no second machine, VM, or paired node reachable
  from this environment.
- **CROSS_MACHINE_TEST: BLOCKED** — no second machine is available in
  this sandbox. Not faked, not weakened, not renamed as a substitute
  pass.
- **Improvement actually performed in place of the blocked test:** a
  same-host, real-network-interface test. Machine A was bound to the
  container's real `eth0` IP address (`172.17.0.120`) using the
  existing, unmodified `--host` CLI flag on `bootstrap_node.py` (no
  code change; this flag already existed for exactly this purpose).
  Machine B ran as a fully separate OS subprocess
  (`python -m lantern.bootstrap_client`) with its own node id, its own
  data directory, and its own Chronicle, connecting to Machine A over
  that real IP address and the actual kernel network stack — not
  `127.0.0.1`/loopback. This is explicitly weaker evidence than a true
  cross-machine test (both processes still share one kernel network
  namespace) and is reported as such, not conflated with it.
- **Real-IP same-host result:** handshake accepted, `OBSERVATION_SHARE`
  (`content="INTER_MACHINE_TEST"`) accepted and created exactly one
  Observation; a follow-up adversarial `CODEX_UPDATE` over the same real
  IP was rejected (`Capability unavailable: codex_update`); independent
  re-read of Machine A's on-disk Chronicle confirmed 1 `OBSERVATION_CREATED`,
  0 `EVIDENCE_CREATED`, watermark step advanced by exactly 1. Disposable
  transcript retained only under `/tmp/lantern-cross-machine-test/`, not
  in this repo.
- **Status:** `[ ]` Genuine cross-machine validation NOT performed —
  environmentally blocked. `[x]` Same-host real-IP validation performed
  as the closest safe substitute and clearly labeled as distinct from
  both the loopback test and a true cross-machine test.

## 9. Public Release Attempt (2026-08-09)

- **Operator authorization:** LICENSE=MIT, DISTRIBUTION=GitHub,
  REPOSITORY NAME=lantern, VERSION=0.82, RELEASE AUTHORIZATION=YES.
- **Work completed:**
  - `LICENSE` file created (MIT), `pyproject.toml` and `README.md`
    updated from `UNLICENSED`/"License: TBD" to MIT, consistently.
  - A clean, standalone git repository was constructed at
    `/tmp/lantern-release-repo` by copying only
    `lantern-babel-codex-bridge/` content (not the parent workspace,
    which has no relation to Lantern and was never part of this repo's
    history) and running `git init` + a single commit
    (`ed03734`, "Lantern v0.82: initial public release"). No parent
    workspace files, history, personal files (`AGENTS.md`, `SOUL.md`,
    `USER.md`, `IDENTITY.md`, `memory/`), credentials, virtual
    environments, caches, or Chronicle/state files are present in that
    tree — verified by full file listing and a secret/credential grep
    before committing (one false positive: `DEMO_WALLET_PRIVATE_KEY`,
    an environment-variable *name* referenced in `demo_e2e.py`, not a
    secret value).
  - Clean-install verification performed from that release tree, in a
    fresh venv unrelated to this project's own `.venv`: `pip install .`
    succeeded, `python -m lantern.bootstrap_node` started, `/health`
    returned `node_id: release-test-node`, `protocol_version: 0.82`,
    `status: ok`, `codex_update: false` — matching the expected result
    exactly.
  - Full test suite run from inside the clean release tree (not the
    original project): **240 passed** (`test_service_integration.py`
    excluded; needs the separate `fastapi`/`x402` service extras, not
    required by `bootstrap_node`).
- **Publication step — DONE:** pushed to `https://github.com/Lantern-svg/lantern`
  (GitHub account `Lantern-svg`, authenticated via `gh` device-flow
  auth) as commit `ed03734ab1c7602df7815fb0934188df4e726aa2`, tagged
  `v0.82`.
- **Status:** `[x]` License, version consistency, clean isolated repo
  construction, clean-install verification, test suite, and public
  push all done and independently verified (twice, via fresh clone of
  the real public URL into a clean environment). `PUBLIC_RELEASE_READY`
  is `YES` for `v0.82`, already released — see the repository above.

---

## 10. v0.83 Release Notes (Scar / Memory persistence) — PREPARED, NOT PUBLISHED

Status document only for this section too — no tag has been created and
nothing has been pushed for v0.83. This repo has no dedicated
`CHANGELOG.md`; the existing convention is release notes recorded here in
`RELEASE.md`, so this entry follows that convention rather than
introducing a new file.

### What changed since v0.82

- **Durable Scar persistence.** Scars (`src/lantern/scars.py`) are no
  longer construct-only. `Lantern.create_scar()` constructs a Scar in
  memory; `Lantern.persist_scar()` writes it through the existing
  `EventBus`/`Chronicle` as a `SCAR_RECORDED` event, then verifies the
  chain before reporting success.
- **Chronicle-backed, not a second database.** Scar durability reuses
  Lantern's existing SHA-256 hash-chained append-only Chronicle — the same
  primitive that already backs Observation/Evidence/Contradiction
  recovery. No new storage engine was introduced.
- **Scar replay and restart recovery.** `Lantern.replay_scars()` and
  `Lantern.load_scar()` recover persisted Scars from the Chronicle after
  a process restart. `Lantern.startup()` replays `SCAR_RECORDED` events
  into runtime state automatically on boot.
- **Snapshot preservation.** `EvidenceKernel.snapshot()`/`restore()` and
  `Lantern.save_snapshot()`/`load_snapshot()` now include Scars, so a
  snapshot-based restore preserves recorded Scars, not just belief state.
- **Explicit Scar gating.** `should_record_network_scar()` requires both
  an outcome on the `NETWORK_SCAR_OUTCOMES` allowlist and an explicit
  `meaningful=True` — not every Event or Outcome becomes a Scar.
- **Architecture-referee enforcement.** `src/lantern/architecture.py` now
  inspects live source to enforce, as hard ERROR-level invariants:
  `scar_persistence_implemented=True` and `scar_auto_mutates_belief=False`.
  These are drift checks against actual code, not documentation claims.
- **SCAR ≠ BELIEF, SCAR ≠ PRINCIPLE, SCAR ≠ CODEX_UPDATE.** No code path
  connects Scar creation/persistence to belief mutation, Codex updates, or
  Principle creation. `codex_update` remains hard-disabled
  (`capabilities.codex_update = False`) independent of Scar work.
  Scar-to-Principle promotion remains an explicit, unresolved
  `OPEN_DECISIONS` item — never automatic.
- **Documentation of the interoperability loop.** `ARCHITECTURE.md` now
  documents the full
  `DISCOVER → UNDERSTAND → EVALUATE → CONTACT → EXCHANGE → VERIFY →
  COLLABORATE → INTEGRATE → SCAR → MEMORY ↺` loop, the
  EVENT/OBSERVATION/EVIDENCE/CONTRADICTION/OUTCOME/SCAR/MEMORY/PRINCIPLE
  layer distinctions, the Scar gate, the
  constructed→persisted→verified→replayed state model, failure-behavior
  guarantees, and one worked end-to-end example
  (incompatible-protocol → Scar → Chronicle → restart → replay).

### Files changed for this pass

`src/lantern/scars.py`, `src/lantern/core.py`, `src/lantern/architecture.py`,
`src/lantern/__init__.py`, `tests/test_lantern_scars.py`, `ARCHITECTURE.md`,
`README.md`, `MODULE_INVENTORY.md`, `RELEASE.md`, `pyproject.toml`.

### Version

- **Version strings bumped:** `pyproject.toml` (`version = "0.83"`) and
  `src/lantern/__init__.py` (`__version__ = "0.83"`) now read `0.83`.
- **Protocol version unchanged:** `PROTOCOL_VERSION` in
  `src/lantern/protocol.py` remains `"0.82"` — no wire-protocol message
  format changed in this pass, so the protocol version was left alone per
  the existing protocol-versioning rule (only bump on real protocol
  changes).

### Not done in this pass (release boundary, awaiting operator authorization)

- `[ ]` Create annotated tag `v0.83` — explicitly withheld this pass.
- `[ ]` Push `v0.83` to the public repository — explicitly withheld this
  pass.
- `[ ]` Any claim that `v0.83` is public — none made; `v0.82` remains the
  only public release.
- **Status:** `[x]` Code, tests, documentation, referee enforcement,
  version bump, and release notes are complete and verified for this
  pass. `[ ]` Tag and publish remain intentionally undone, pending
  explicit operator authorization in a future turn.


