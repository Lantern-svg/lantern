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
- **Immutable identifier:** no git tag exists (`git tag` returns empty).
  Placeholder mechanism: an annotated git tag (e.g. `v0.82`) created at
  the commit chosen for release, or a signed/hash-referenced release
  archive.
- **Status:** `[ ]` No externally citable release identifier exists yet.

## 3. Public Repository / Distribution Location

- **Location:** no `[project.urls]` in `pyproject.toml`; no git remote
  (`git remote -v` empty); no CI/release workflow files in the repo.
- **Placeholder:** `EXTERNAL_BOOTSTRAP.md` section 3 already contains a
  literal placeholder: `git clone <the Lantern repository URL>`.
- **Status:** `[ ]` Not selected. GitHub/PyPI/self-hosted are equally
  valid; the requirement is only that the source be independently
  fetchable and hash-verifiable by someone who is not the operator.

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


