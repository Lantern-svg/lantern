# Lantern Babel Codex Bridge — Module Inventory

Repo root: `lantern-babel-codex-bridge/` (this file's directory)
Package: `src/lantern/`
Full test run: `.venv/bin/python -m pytest tests/ -q` → **698 passed, 0 failed** (confirmed by running it during the v0.84 release gate). This file still is not a complete per-module re-audit of every newer module, but its header now reflects the current tested baseline rather than the long-stale 142-test snapshot.

Package surface note (`__init__.py`, not in the original covered set): it does no independent logic. It re-exports selected classes/functions from the package into a flat `lantern.__all__` namespace, now including the v0.84 additions (`orchestration`, `contact_ledger`, `compass`, `compression`, `mcp_client`, `mcp_integration`, `receiver_readiness`), and sets `__version__ = "0.84"`. It has no dedicated test file and contains no behavior of its own to test.

v0.84 release-scope additions now present in the public package surface:
- `orchestration.py` — capability registry, verification policy, scoped delegation records, planner, provenance tags, self-change proposals.
- `contact_ledger.py` — evidence-backed contact-state ladder with no inferred upgrades.
- `compass.py` — read-only orientation layer answering WHAT matters / WHY / WHAT is allowed / WHAT is next.
- `compression.py` — read-only validator/scar-builder that refuses semantic state-collapse.
- `mcp_client.py` — bounded MCP stdio client with all third-party `mcp` imports isolated here.
- `mcp_integration.py` — discovery/binding/delegation/execution/provenance/verification boundary for MCP-exposed capabilities.
- `receiver_readiness.py` — read-only operator/evaluator path from `JOIN_REQUESTED` through compatibility, identity verification, authorization, contact-ledger translation, and Compass orientation.

---

## core

**Description:** Implements an in-memory "evidence kernel" that turns timestamped text observations into weighted, signed evidence for named concepts, computes a sigmoid-based belief score per concept from that evidence with linear time-decay, detects when a concept has both supporting and opposing evidence (a contradiction) and threads new contradiction states onto prior ones rather than overwriting them, and records non-destructive resolution judgments against contradictions. It also implements an append-only, SHA-256 hash-chained event log (`Chronicle`) written to a JSONL file, a snapshot/restore mechanism for kernel state, and a `Lantern` shell class that wires an `EventBus` (which publishes events to a fixed list of pluggable "modules": memory, codex, reasoning) together with the kernel and chronicle, and provides deterministic startup/recovery (snapshot + replay-after-snapshot, falling back to full replay).

**Public functions/classes:**
- `Observation`, `Evidence` (with `decayed_weight`), `Contradiction`, `ResolutionEvent` — dataclasses representing kernel records.
- `EvidenceKernel` — core state machine: `observe()`, `add_evidence()`, `belief()`, `sigmoid()`, `latest_contradiction()`, `contradiction_severity()`, `detect_contradiction()`, `resolve()`, `snapshot()`, `restore()` (classmethod).
- `KernelEvent` — dataclass for events published on the bus.
- `Chronicle` — hash-chained append-only log: `append()`, `replay()`, `verify()`, `records_after()`.
- `LanternModule`, `MemoryModule`, `CodexModule`, `ReasoningModule` — pluggable event observers with differing state (history list, keyed state dict, none).
- `EventBus` — `register()`, `publish()`, `replay_publish()`, `audit()` (own separate hash chain from Chronicle's).
- `Lantern` — top-level shell: `observe()`, `add_evidence()`, `resolve()`, `save_snapshot()`, `load_snapshot()`, `startup()`.
- Utility functions `uid()`, `now()`, `chronicle_body()`.

**Inputs:** Plain Python values — strings (`content`, `source`, `concept`), floats (`reliability` 0-1, `weight`), ints (`sign` = 1 or -1, `step`), optional dict `metadata`. Chronicle takes a filesystem path (str/Path) for its JSONL file.

**Outputs:** Dataclass instances (`Observation`, `Evidence`, `Contradiction`, `ResolutionEvent`) held in kernel lists/dicts; `belief()` returns a float in (0,1); `snapshot()`/JSONL records are plain dicts/JSON; `Chronicle.verify()` returns bool.

**Functional and tested:** Yes. `tests/test_lantern_core.py` (12 tests: belief derivation, temporal replay, decay, contradiction detection/threading, non-destructive resolution, event propagation, audit chain, Chronicle persistence/replay, tamper detection) and `tests/test_snapshot_recovery.py` (5 tests: snapshot/restore roundtrip, `records_after`, fast recovery, fallback, partial replay) all pass.

**Depends on other lantern modules:** None. This is the base module; nothing else in `core.py` imports from the package.

**Standalone:** Yes, fully. It has no imports from any other `lantern` submodule and can be used with just the stdlib (`hashlib`, `json`, `math`, `uuid`, `pathlib`, `datetime`, `dataclasses`).

**Standalone API candidate:** Yes — it's a complete, self-contained evidence/belief/contradiction engine with persistence. It's the one module whose functionality (submit observations, get a belief score, see contradictions, resolve them) maps directly onto a set of discrete request/response operations.

---

## protocol

**Description:** Defines a plain wire-message envelope (`ProtocolMessage`) with an id, protocol version string, message type, source, timestamp, and JSON-serializable payload dict, plus JSON encode/decode and three factory functions that build specific message shapes (observation share, evidence request, codex update) and a validator that checks required fields are present and the protocol string matches the current version. It performs no reasoning and touches no kernel state — it is purely a message-shape definition module.

**Public functions/classes:**
- `PROTOCOL_VERSION` — module constant, currently `"0.82"`.
- `ProtocolMessage` — dataclass with `encode()` (to JSON string) and static `decode()` (from JSON string).
- `create_message(message_type, source, payload)` — generic message factory.
- `create_observation_share(source, observation)`, `create_evidence_request(source, concept)`, `create_codex_update(source, concept, confidence, evidence_ids)` — typed factories.
- `validate_message(message)` — bool; checks all required fields exist and protocol version matches, without raising on malformed/non-dataclass input.

**Inputs:** Strings and dicts (message_type, source, payload/observation dict, concept string, confidence float, list of evidence id strings). `decode()` takes a JSON string.

**Outputs:** `ProtocolMessage` dataclass instances; `encode()` returns a JSON string; `validate_message()` returns bool.

**Functional and tested:** Yes. `tests/test_lantern_protocol.py` (9 tests: round-trip encode/decode, all three factories, valid/invalid version, missing-field and non-dataclass validation edge cases, version constant sanity) all pass.

**Depends on other lantern modules:** None.

**Standalone:** Yes, fully independent — only stdlib (`dataclasses`, `json`, `datetime`, `uuid`).

**Standalone API candidate:** No as a capability on its own — it's pure message plumbing/serialization, not a discrete capability. It would only make sense exposed indirectly, as the request/response shape of other API endpoints.

---

## compatibility

**Description:** Implements protocol version compatibility checking (major-version-only match, minor versions considered compatible) and capability negotiation between a local and remote capability dict. It holds the single canonical `DEFAULT_CAPABILITIES` dict (evidence_exchange, codex_update [disabled], belief_query, contradiction_tracking, snapshot_exchange, handshake) that other modules (`handshake.py`, `architecture.py`) import rather than redeclare. Given a remote version/capabilities, it returns whether the two sides are compatible and which capabilities are actually shared vs. missing.

**Public functions/classes:**
- `parse_version(version)` — parses a version string (raises `ValueError` on non-numeric parts) into a tuple.
- `major_version(version)` — first element of parsed version.
- `compatible_versions(local, remote)` — bool, true iff major versions match.
- `DEFAULT_CAPABILITIES` — module-level dict, canonical capability defaults.
- `CompatibilityResult` — dataclass: `compatible`, `reason`, `shared_capabilities`, `missing_capabilities`.
- `negotiate(remote_version, remote_capabilities, local_version=None, local_capabilities=None)` — builds a `CompatibilityResult`.
- `can_exchange(result, capability)` — bool convenience check against a `CompatibilityResult`.

**Inputs:** Version strings (e.g. `"0.82"`), dicts mapping capability name (str) to bool.

**Outputs:** `CompatibilityResult` dataclass; `can_exchange` returns bool.

**Functional and tested:** Yes. `tests/test_lantern_compatibility.py` (13 tests: version parsing, major/minor compatibility rules including malformed-version error propagation, negotiation shared/missing sets, local override behavior, `can_exchange` variants) all pass.

**Depends on other lantern modules:** `protocol` (imports `PROTOCOL_VERSION` as the negotiation default).

**Standalone:** Nearly — it needs only `protocol.py`'s version constant, which itself has no dependencies. Can run with just those two files.

**Standalone API candidate:** No as a discrete capability by itself — it's negotiation/plumbing logic consumed internally by handshake/router/boundary, not something an external caller would invoke directly as "a capability."

---

## handshake

**Description:** Builds and evaluates a peer-to-peer capability handshake. `create_handshake()` produces a `HandshakeRequest` carrying a random node id, the local protocol version, and a capabilities dict (defaulting to the canonical `DEFAULT_CAPABILITIES` imported from `compatibility.py`). `evaluate_handshake()` checks major-version compatibility via `compatibility.compatible_versions()`, then intersects the requester's claimed capabilities with the responder's supported ones (both must have the capability enabled) and returns a `HandshakeResponse`. It does not touch kernel state.

**Public functions/classes:**
- `HandshakeRequest` — dataclass: node_id, protocol_version, capabilities, timestamp.
- `HandshakeResponse` — dataclass: node_id, accepted, protocol_version, shared_capabilities, reason, timestamp.
- `create_handshake(capabilities=None)` — builds a request.
- `evaluate_handshake(request, supported_capabilities=None)` — builds a response.
- `handshake_summary(response)` — flattens a response into a small summary dict (accepted, protocol, capability names, reason).

**Inputs:** Optional capabilities dict for `create_handshake`; a `HandshakeRequest` and optional supported-capabilities dict for `evaluate_handshake`.

**Outputs:** `HandshakeRequest`/`HandshakeResponse` dataclasses; `handshake_summary` returns a plain dict.

**Functional and tested:** Yes. `tests/test_lantern_handshake.py` (12 tests: capability dict identity with `compatibility.DEFAULT_CAPABILITIES` — not a copy, default request creation, accept/reject on version compatibility including same-major-different-minor, capability filtering both ways, summary shape) all pass.

**Depends on other lantern modules:** `protocol` (`PROTOCOL_VERSION`), `compatibility` (`compatible_versions`, `DEFAULT_CAPABILITIES`).

**Standalone:** Needs `protocol.py` and `compatibility.py` alongside it; no dependency on `core`, `agent`, or anything belief-related.

**Standalone API candidate:** Marginally — "can two instances talk" is a discrete yes/no check, but it only has meaning paired with an actual message-exchange capability (router/boundary), so on its own it's thin plumbing rather than a standalone product feature.

---

## router

**Description:** A message dispatcher that, given a `ProtocolMessage` and a previously-negotiated `CompatibilityResult`, checks whether the message type's required capability (from a fixed `MESSAGE_REQUIREMENTS` map: `OBSERVATION_SHARE`→`evidence_exchange`, `CODEX_UPDATE`→`codex_update`, `EVIDENCE_REQUEST`→`belief_query`) was actually negotiated, and if so looks up and calls a registered handler function for that message type. Message types with no entry in `MESSAGE_REQUIREMENTS` skip the capability check but still require a registered handler. It never touches evidence, belief, or Codex state directly — it only decides whether a message may be delivered and to whom.

**Public functions/classes:**
- `MESSAGE_REQUIREMENTS` — module-level dict mapping message type string to required capability name.
- `RouteResult` — dataclass: accepted (bool), message_type, reason.
- `LanternRouter` — `register(message_type, handler)`, `route(message, compatibility)`.

**Inputs:** `ProtocolMessage` instance, `CompatibilityResult` instance (from `compatibility.negotiate`); handler registration takes a message-type string and a callable.

**Outputs:** `RouteResult` dataclass; side effect of calling the registered handler with the message if accepted.

**Functional and tested:** Yes. `tests/test_lantern_router.py` (7 tests: capability-gated delivery granted/missing, no-handler rejection, unmapped message types requiring a handler, version-incompatibility blocking, handler overwrite on re-register) all pass.

**Depends on other lantern modules:** `compatibility` (`CompatibilityResult`, `can_exchange`), `protocol` (`ProtocolMessage`, used only as a type reference in the signature).

**Standalone:** Needs `compatibility.py` and (loosely) `protocol.py`; no dependency on `core`/`agent`.

**Standalone API candidate:** No — this is explicitly internal message routing/plumbing (the module's own docstring frames it as exactly that: "does this message type have a home, is it capability-permitted"). Not a discrete external capability.

---

## boundary

**Description:** A thin composition wrapper ("migration bridge," per its docstring) that gives external callers one object (`LanternBoundary`) instead of reaching into `router`, `compatibility`, and `handshake` separately. It owns one `LanternRouter` instance and delegates `connect()` to `compatibility.negotiate`, `receive()` to `self.router.route`, `handshake()` to `handshake.create_handshake`, and `register()` to `self.router.register`. It adds no new logic beyond delegation.

**Public functions/classes:**
- `LanternBoundary` — `__init__()` (creates its own `LanternRouter`), `connect(remote_version, remote_capabilities)`, `receive(message, compatibility)`, `handshake()`, `register(message_type, handler)`.

**Inputs:** Same as the underlying calls: version strings/capability dicts for `connect`, `ProtocolMessage`+`CompatibilityResult` for `receive`, message-type+handler for `register`.

**Outputs:** `CompatibilityResult` (from `connect`), `RouteResult` (from `receive`), `HandshakeRequest` (from `handshake`).

**Functional and tested:** Yes. `tests/test_lantern_boundary.py` (6 tests: connect returns real `CompatibilityResult`, version-mismatch rejection, delivery to a registered handler, capability-missing block, handshake returns a real `HandshakeRequest`, and confirming each `LanternBoundary` instance gets its own fresh router rather than sharing state) all pass.

**Depends on other lantern modules:** `router` (`LanternRouter`, `RouteResult`), `compatibility` (`CompatibilityResult`, `negotiate`), `handshake` (`create_handshake`).

**Standalone:** No independent logic of its own; it's a facade requiring `router.py`, `compatibility.py`, and `handshake.py` (which in turn need `protocol.py`).

**Standalone API candidate:** No — explicitly plumbing/composition, not a capability. Its own docstring states it "does not replace existing modules... it composes them."

---

## bridge

**Description:** Connects the transport/routing layer to the actual `LanternAgent`/kernel. `LanternAgentBridge` owns its own `LanternBoundary` and registers two handlers on it at construction time: `OBSERVATION_SHARE` messages get turned into a real `agent.observe()` call (creating a kernel `Observation`), and `EVIDENCE_REQUEST` messages get turned into an `agent.ask_belief()` call. `CODEX_UPDATE` messages are deliberately left unregistered/unhandled — they are rejected by the boundary's capability gate (since `codex_update` is disabled by default) before ever reaching agent logic, so no code path exists here that lets a remote peer directly move local belief.

**Public functions/classes:**
- `BridgeResult` — dataclass: accepted (bool), action (str), reason (str), data (dict).
- `LanternAgentBridge(agent)` — `connect(remote_version, capabilities)`, `receive(message, compatibility)`. Private handlers `_on_observation_share`, `_on_evidence_request` are wired internally, not meant to be called directly.

**Inputs:** A `LanternAgent` instance at construction; `ProtocolMessage` + `CompatibilityResult` for `receive`; version string + capabilities dict for `connect`.

**Outputs:** `BridgeResult` dataclass carrying either the created observation or the queried belief value, or a rejection reason.

**Functional and tested:** Yes. `tests/test_lantern_bridge.py` (6 tests: real observation creation end-to-end through boundary→router→agent→kernel, default reliability handling, belief-query round trip, missing-capability rejection before reaching the agent, confirming `CODEX_UPDATE` never reaches evidence mutation, and confirming two separate bridge instances don't share handler/kernel state) all pass, using real (not mocked) `Lantern`/`LanternAgent` instances.

**Depends on other lantern modules:** `boundary` (`LanternBoundary`), `agent` (`LanternAgent`) — and transitively `router`, `compatibility`, `handshake`, `protocol`, `core`.

**Standalone:** No — it requires the full chain down to `core.py` (via `agent.py`) plus the full boundary/router/compatibility/handshake/protocol stack to function meaningfully.

**Standalone API candidate:** Yes, in the sense that this is the concrete integration point that would back an actual "submit an observation" / "query a belief" HTTP endpoint — it is the piece that turns a wire message into a real kernel action and back. It is not itself a new capability beyond what `agent.py` exposes, but it is the natural place an API layer would plug into.

---

## federation

**Description:** Receives an `OBSERVATION_SHARE`-shaped protocol message from a remote peer and converts it into a local kernel `Observation`, tagging it with structured provenance metadata (origin type, remote instance id, the concept and confidence the remote peer *claimed*) — but the remote-claimed confidence is stored only as metadata and is hardcoded to never be used as the observation's `reliability` (which is fixed at `0.5` for all remote observations) and is never passed into `add_evidence()` or belief calculations. It does not accept a `ProtocolMessage`'s full validation — it directly reads `message.payload["observation"]` — and does not itself do capability checking (that happens upstream, e.g. in `router`/`boundary`).

**Public functions/classes:**
- `FederationMetadata` — dataclass: origin_type, remote_instance, claimed_concept, claimed_confidence, received_at.
- `RemoteObservation` — dataclass: id, source, concept, content, metadata.
- `FederationResult` — dataclass: accepted (bool), observation_id, reason.
- `FederationAdapter(agent)` — `receive_observation(message)`.

**Inputs:** A `LanternAgent` at construction; a message-like object with `.source` and `.payload["observation"]` (a dict with optional `concept`, `content`, `confidence` keys).

**Outputs:** `FederationResult` dataclass; side effect of creating one new `Observation` in the wrapped agent's kernel with `reliability=0.5` and structured metadata.

**Functional and tested:** Yes. `tests/test_lantern_federation.py` (7 tests: observation stored correctly, remote confidence never creates evidence, fixed 0.5 reliability, remote confidence never moves belief, missing-confidence default, metadata structure preserved, multiple remote sources produce separate observations) all pass.

**Depends on other lantern modules:** None directly imported in the file (it only type-uses a `LanternAgent`-shaped object passed in, and a message-shaped object) — no `import` statements from other `lantern` submodules at all. It is used with a real `LanternAgent`/`protocol.create_observation_share` in tests but has no hard import coupling.

**Standalone:** Yes at the import level (zero `lantern` imports), though functionally it requires an object with an `.observe(content, source, reliability, metadata)` method (i.e., something shaped like `LanternAgent`) to do anything useful.

**Standalone API candidate:** Yes — "accept an observation from a remote/external source without letting it influence local belief directly" is a coherent, self-contained capability (an ingestion endpoint with an explicit trust boundary), matching the module's own stated rule ("a Lantern may share meaning; a Lantern may not donate certainty").

---

## evaluation

**Description:** Implements a two-step gate between a raw observation and its promotion into kernel evidence. `evaluate()` takes an existing observation id plus a concept/sign/optional weight and creates an in-memory `EvidenceCandidate` (default weight 1.0 if not given) — it does not touch kernel evidence at all. A separate explicit `promote(candidate_id)` call is required to actually invoke `agent.add_evidence()` and turn the candidate into real kernel `Evidence`; promotion consumes (deletes) the candidate so it cannot be double-promoted. `reject(candidate_id, reason)` discards a candidate without ever creating evidence. Candidates are stored only in the gate instance's own `self.candidates` dict, not persisted anywhere.

**Public functions/classes:**
- `EvaluationResult` — dataclass: accepted (bool), action (str), reason (str), observation_id, evidence_id (optional).
- `EvidenceCandidate` — dataclass: id, observation_id, concept, weight, sign, evaluator, created_at.
- `EvidenceEvaluationGate(agent)` — `evaluate(observation_id, concept, sign, weight=None, evaluator="local")`, `promote(candidate_id)`, `reject(candidate_id, reason)`.

**Inputs:** A `LanternAgent` at construction; observation id (str, must already exist in the agent's kernel), concept (str), sign (int, 1/-1), optional weight (float), optional evaluator label (str).

**Outputs:** `EvaluationResult` dataclass; side effect on `promote()` of appending one `Evidence` record to the wrapped agent's kernel.

**Functional and tested:** Yes. `tests/test_lantern_evaluation.py` (7 tests: candidate creation without evidence side effects, rejection of unknown observation id, default weight resolving to exactly the observation's reliability (not double-applied), explicit weight applied once, promotion consuming/blocking double-promotion, rejection of unknown candidate id, explicit reject flow) all pass.

**Depends on other lantern modules:** None imported directly in the file — it takes a `LanternAgent`-shaped object as a constructor argument and calls `.lantern.kernel.observations` and `.add_evidence()` on it, but has no `import` statements referencing other `lantern` submodules.

**Standalone:** Yes at the import level; functionally requires an agent-shaped object exposing `.lantern.kernel.observations` and `.add_evidence()`.

**Standalone API candidate:** Yes — "review a candidate piece of evidence, then explicitly approve or reject it" is a coherent, discrete, human-in-the-loop workflow capability distinct from raw observation ingestion.

---

## codex_compare

**Description:** Compares the belief state of two separate `Lantern` instances concept-by-concept and classifies each concept into one of four categories: `missing_evidence` (only one side has any evidence for the concept at all — checked explicitly via evidence presence, not just via the belief value, since a concept with zero evidence would otherwise misleadingly read as belief 0.5), `contradiction` (beliefs are on opposite sides of the 0.5 midpoint and diverge by at least a threshold), `confidence_gap` (same lean, but gap above threshold), or `agreement` (gap below threshold). It reads two kernels' evidence/observations but writes nothing to either.

**Public functions/classes:**
- `ConceptComparison` — dataclass: concept, belief_a, belief_b (either may be None), category, detail.
- `ComparisonResult` — dataclass wrapping a list of comparisons; `by_category(category)` filter method.
- `compare_beliefs(lantern_a, lantern_b, concepts=None, agreement_threshold=0.1, contradiction_threshold=0.3)` — builds the full comparison.
- `comparison_summary(result)` — dict of category → count.

**Inputs:** Two `Lantern` instances; optional explicit list of concept strings to restrict comparison scope; optional float thresholds.

**Outputs:** `ComparisonResult` containing a list of `ConceptComparison` dataclasses; `comparison_summary` returns a plain dict.

**Functional and tested:** Yes. `tests/test_codex_compare.py` (8 tests: agreement, contradiction, confidence gap, missing-evidence (both directions of "which side is missing"), the explicit missing-evidence-vs-neutral-belief regression case, summary counts, category filtering, explicit concept-list scoping) all pass.

**Depends on other lantern modules:** None imported directly — it operates on `.kernel` attributes of whatever `Lantern`-shaped objects are passed in, with no `import` of other lantern submodules.

**Standalone:** Yes at the import level; functionally needs two objects exposing `.kernel.evidence` and `.kernel.belief(concept)` (i.e., `core.Lantern`-shaped).

**Standalone API candidate:** Yes — "diff two belief states" is a self-contained, well-defined comparison capability.

---

## codex_explanation

**Description:** Takes a single `ConceptComparison` (produced by `codex_compare.compare_beliefs`) plus the two `Lantern` instances it was derived from, and builds a human-readable `Explanation` describing why that comparison category was reached — e.g., for a contradiction it reports both sides' evidence counts/signs/average source reliability and flags if either side's evidence relies on low-reliability sources; for missing_evidence it identifies which side is missing and describes the other side's evidence; for confidence_gap it flags differing evidence counts as a possible cause; for agreement it just describes both sides. It reads `kernel.evidence`/`kernel.observations` on both Lanterns but writes nothing to either kernel.

**Public functions/classes:**
- `Explanation` — dataclass: concept, category, belief_a, belief_b, cause (str), supporting_factors (list of str), missing_information (list of str).
- `explain_comparison(comparison, lantern_a, lantern_b)` — builds one `Explanation`.
- `explain_comparisons(result, lantern_a, lantern_b)` — maps `explain_comparison` over every comparison in a `ComparisonResult`.

**Inputs:** A `ConceptComparison` (or `ComparisonResult`) plus two `Lantern`-shaped instances.

**Outputs:** `Explanation` dataclass (or a list thereof).

**Functional and tested:** Yes. `tests/test_codex_explanation.py` (7 tests: confirms zero kernel mutation as a side effect, missing-evidence side naming, contradiction reporting both sides, confidence-gap evidence-count note, agreement having no missing-information entries, belief-value/concept preservation from the source comparison, one explanation produced per input comparison) all pass.

**Depends on other lantern modules:** None imported directly in the file — takes `comparison`/`lantern_a`/`lantern_b` as plain arguments with no `lantern` submodule imports; in practice it's used together with `codex_compare.compare_beliefs`'s output shape.

**Standalone:** Yes at the import level; functionally it's meant to run on the output of `codex_compare` plus the same two `Lantern` instances.

**Standalone API candidate:** Yes — "explain a specific belief divergence in plain language" is a discrete, coherent capability, though it is naturally a companion to `codex_compare` rather than fully independent of it in practice.

---

## scars

**Description:** Implements durable Scar persistence, reusing `core.Chronicle` (the existing append-only, SHA-256 hash-chained log) instead of a second store. A `Scar` is a durable consequence record of a meaningful outcome, contradiction, failure, or success — constructed in memory first (`create_scar()`), then explicitly persisted through `Lantern.persist_scar()` (append to Chronicle, verify, update runtime state). A `ScarRecord` tracks four independent boolean states — `constructed`, `persisted`, `verified`, `replayed` — that are never collapsed into each other: a constructed Scar is not a persisted one, and a persisted Scar is not necessarily replayed until it actually comes back through `Lantern.startup()`. Network-originated scars are additionally gated by `should_record_network_scar()`, which requires both an allowlisted outcome (`NETWORK_SCAR_OUTCOMES`) and an explicit `meaningful=True` from the caller — trivial network traffic never becomes a Scar. `describe_scar_claim()` is preserved from the pre-persistence version of this module: it builds a Scar-shaped dict for conversational/reporting use only and always reports `persisted: False`, since it deliberately never touches Chronicle.

**Public functions/classes:**
- `Scar` — frozen dataclass: id, timestamp, source, trigger, observation, outcome, severity, lesson (optional), related_contradiction_id (optional), related_evidence_ids (optional), protocol_version, provenance; `to_dict()`/`from_dict()`.
- `ScarRecord` — frozen dataclass: scar, constructed, persisted, verified, replayed; `to_dict()`.
- `ScarPersistenceStatus` — frozen dataclass: status, reason; `to_dict()`.
- `scar_persistence_status()` — returns `ACTIVE` with a reason describing Chronicle-backed persistence (this module no longer reports `NOT_IMPLEMENTED` for the persistence mechanism itself; `NOT_IMPLEMENTED` remains defined as a constant for compatibility/documentation of the prior state).
- `create_scar(...)` — builds a `ScarRecord` with `constructed=True, persisted=False`.
- `create_network_scar(...)` — like `create_scar`, but raises `ValueError` unless `should_record_network_scar()` returns True for the given outcome.
- `should_record_network_scar(outcome, meaningful)` — bool gate combining the outcome allowlist and an explicit meaningful flag.
- `persisted_record(scar, verified=...)`, `record_from_replay(scar)`, `verify_scar_record(record, scars_by_id)`, `replay_scars(scars_by_id)`, `load_scar(scars_by_id, scar_id)` — state-transition helpers consumed by `core.Lantern`; not intended to be called directly against a live Chronicle without going through `Lantern`.
- `describe_scar_claim(scar_id, summary)` — non-persisting, conversational-use-only helper; always `persisted: False`.
- `SCAR_EVENT_TYPE` (`"SCAR_RECORDED"`) — the Chronicle event type used for durable Scar writes.
- `NETWORK_SCAR_OUTCOMES` — frozenset of outcome strings eligible for network-triggered Scars.

**Inputs:** Plain strings/dicts describing an outcome (source, trigger, observation, outcome, severity, optional lesson/provenance/related ids). Persistence-facing functions additionally take a `scars_by_id` dict or a live `Lantern` instance (see `core`).

**Outputs:** `ScarRecord`/`Scar`/`ScarPersistenceStatus` dataclasses; `describe_scar_claim()` returns a plain dict.

**Functional and tested:** Yes. `tests/test_lantern_scars.py` (12 tests: persistence-status reporting, non-persisting claim helper, construction without persistence, Chronicle-backed persistence and verification, restart survival and replay, snapshot-preserved scars, corrupted-Chronicle detection before replay, failed-append not reporting `persisted=True`, network-outcome gating, network-integration persistence) all pass. Durable persistence, restart, replay, corruption-detection, and failure-semantics behavior is additionally exercised end-to-end through `core.Lantern.persist_scar/load_scar/verify_scar/replay_scars/startup`.

**Depends on other lantern modules:** `protocol` (`PROTOCOL_VERSION` default). Durable persistence itself is implemented on `core.Lantern`, which imports this module for the `Scar`/`ScarRecord` shapes and the Chronicle event type constant — `scars.py` itself has no import-time dependency on `core`.

**Standalone:** Nearly — `Scar`/`ScarRecord` construction and the network-outcome gate need only `protocol.py`; actual durable persist/verify/replay requires a `core.Lantern` instance (and therefore a Chronicle).

**Standalone API candidate:** Yes, paired with `core.Lantern` — "record and later recall a meaningful experience, verifiably" is a coherent, discrete capability, and it is the durable half of the DISCOVER…INTEGRATE→SCAR→MEMORY loop described in `ARCHITECTURE.md`.

---

## architecture

**Description:** An independent, read-only "architecture referee." It hardcodes a second, separate copy of the capability defaults, message-requirement map, protocol message types, a handful of "frozen constants" (e.g. `decay_rate=0.05`, `belief_neutral_value=0.5`, several boolean trust invariants like `codex_update` must be `False`), the module list, and open design decisions — as an independent reference state that must never alias the live modules' own dicts. `inspect_live_system()` then introspects the actual running package (via `inspect.getsource`, globbing `.py` files, calling real factory functions, reading real default parameter values) to build a live-state snapshot, and compares the reference state against that live state field-by-field, producing `Finding` objects (ERROR/WARNING/INFO) for any drift, plus explicit checks of four hardcoded trust invariants (codex_update disabled, remote confidence must not mutate belief, watermark must not mutate belief, watermark must not bypass capability gating). It does not alter any live module's behavior — it only observes, compares, and reports.

**Public functions/classes:**
- Module constants: `ARCHITECTURE_VERSION`, `CANONICAL_CAPABILITIES`, `CANONICAL_MESSAGE_REQUIREMENTS`, `CANONICAL_PROTOCOL_MESSAGE_TYPES`, `FROZEN_CONSTANTS`, `MODULES`, `OPEN_DECISIONS`.
- `Finding` — frozen dataclass: severity, category, name, expected, actual, plus a `.message` property.
- `ArchitectureReport` — dataclass: findings list, reference/live fingerprints; `.healthy`, `.errors()`, `.warnings()`, `.infos()`, `.by_category()`, `.to_dict()`.
- `ArchitectureRegistry` — the referee: `capability_exists`, `capability_enabled`, `required_capability`, `message_allowed`, `fingerprint()`, `inspect_live_system()`, `compare_capabilities`, `compare_message_requirements`, `compare_protocol_message_types`, `compare_modules`, `compare_constants`, `validate_reference()`, `validate_open_decisions()`, `validate()` (full pass), `snapshot()`.
- `REGISTRY` — single module-level `ArchitectureRegistry()` instance.
- `architecture_status()` — convenience function returning a small health-summary dict.

**Inputs:** No external inputs for the default path — `validate()`/`snapshot()`/`architecture_status()` take no arguments and introspect the live package itself. Individual `compare_*` methods take a live dict/set to diff against the reference.

**Outputs:** `ArchitectureReport` (list of `Finding`s + two SHA-256 fingerprints), or a plain summary dict from `architecture_status()`, or a full state dict from `snapshot()`.

**Functional and tested:** Yes. `tests/test_lantern_architecture.py` (23 tests — the largest test file — covering clean-state health, open-decision preservation as INFO, reference-dict independence from live dicts, drift detection for capabilities/message-requirements/modules/constants added/changed/removed, all four trust-invariant violations, fingerprint presence, snapshot shape, `message_allowed` reference-state checks, and confirming the referee's own `validate()` call does not mutate any live module state) all pass.

**Depends on other lantern modules:** Imports (inside `inspect_live_system`, i.e. deferred/lazy imports) `compatibility`, `continuity`, `federation`, `protocol`, `router`, `codex_compare.compare_beliefs`, `core.Evidence`/`core.EvidenceKernel` — purely for read-only introspection (`inspect.getsource`, calling factory functions, reading default parameter values). It does not call mutating methods on any of them.

**Standalone:** No — its entire purpose requires the rest of the package to exist on disk to introspect; it is meaningless without the other modules present.

**Standalone API candidate:** Yes, but as an internal/ops capability rather than an end-user one — "get a health/drift report of this system's architecture against its own frozen invariants" is a coherent, well-defined, discrete output (e.g. a `/health` or `/architecture-status` endpoint), just not a user-facing "product" feature.

---

## continuity

**Description:** A read-only "watermark" view over state that already exists elsewhere: a `Watermark` is just `(step, chain)`, where `step` is read straight from `EvidenceKernel.step` and `chain` is read straight from `Chronicle.chain` (or `"GENESIS"` if no chronicle is attached) — the module explicitly does not introduce any new counter or persistence mechanism. `local_watermark(lantern)` reads the local pair. `parse_remote_watermark(data)` parses an untrusted peer-supplied dict into a `Watermark` with no verification. `compare_watermarks(local_version, remote_version, local, remote)` first checks major-version compatibility (authoritative, checked before anything else) and then classifies the relationship into one of `COMPATIBLE` (same step, same chain), `DIVERGED` (same step, different chain — meaningful even without a shared ledger, since equal-length-but-different-hash histories are provably different), `BEHIND`/`AHEAD` (remote step lower/higher than local), or `INCOMPATIBLE` (version mismatch). It never mutates belief/evidence and never performs or bypasses capability gating.

**Public functions/classes:**
- State constants: `COMPATIBLE`, `BEHIND`, `AHEAD`, `DIVERGED`, `INCOMPATIBLE`, and `CONTINUITY_STATES` (a frozenset of all five).
- `Watermark` — frozen dataclass: step (int), chain (str); `.to_dict()`.
- `ContinuityResult` — frozen dataclass: status, reason.
- `local_watermark(lantern)` — reads local watermark from a `Lantern` instance.
- `parse_remote_watermark(data)` — parses a dict (e.g. from a handshake payload) into a `Watermark`, defaulting missing fields (`step=0`, `chain="GENESIS"`).
- `compare_watermarks(local_version, remote_version, local, remote)` — classification function.

**Inputs:** A `Lantern` instance (for `local_watermark`); a plain dict with optional `step`/`chain` keys (for `parse_remote_watermark`); two version strings and two `Watermark` instances (for `compare_watermarks`).

**Outputs:** `Watermark` dataclass; `ContinuityResult` dataclass (status string + reason string).

**Functional and tested:** Yes. `tests/test_lantern_continuity.py` (16 tests: reading step+chain correctly, defaulting to GENESIS with no chronicle, confirming zero side effect on kernel step from repeated reads, watermark equality preserved across snapshot/restore and across full Chronicle replay, remote-watermark parsing being a plain untrusted parse with field defaults, all five classification outcomes including malformed-step-defaults-to-0 behavior and version-mismatch overriding an apparently-ahead remote step, confirming comparison cannot mutate belief/evidence, and a source-inspection test confirming the module never references `can_exchange`/`MESSAGE_REQUIREMENTS`/mutation APIs) all pass.

**Depends on other lantern modules:** `compatibility` (`compatible_versions`) only.

**Standalone:** Nearly — needs `compatibility.py` (and transitively `protocol.py` for the version constant) plus a `Lantern`-shaped object with `.kernel.step` and `.bus.chronicle.chain` for the local-reading half.

**Standalone API candidate:** No as a user-facing capability — it's a diagnostic/sync-position primitive ("are these two peers at the same verified point"), explicitly framed by its own docstring as a comparison, not a proof or an action. Useful as an internal building block for a sync-status check, not a standalone feature.

---

## agent

**Description:** A thin, deliberately minimal adapter around `core.Lantern`. It forwards `observe()`, `add_evidence()`, and `resolve()` calls straight through to the wrapped `Lantern` instance with no added logic, exposes a `status()` summary dict (started timestamp, step, observation/evidence/contradiction counts, module names, whether a chronicle is attached), delegates `startup()` entirely to `Lantern.startup()` (measuring how many events got replayed by comparing bus history length before/after) rather than re-implementing recovery, and provides one convenience read method `ask_belief()`. Per its own docstring: "The agent is not the intelligence. The kernel remains the intelligence."

**Public functions/classes:**
- `LanternAgent(lantern, chronicle=None)` — `observe(content, source, reliability=1.0, metadata=None)`, `add_evidence(concept, observation_id, weight, sign)`, `resolve(contradiction_id, decision, reasoning, confidence)`, `status()`, `startup()`, `ask_belief(concept, at_step=None)`.

**Inputs:** A `core.Lantern` instance and optional `core.Chronicle` instance at construction; thereafter the same argument shapes as the underlying `Lantern`/`EvidenceKernel` methods it forwards to.

**Outputs:** Whatever the wrapped `Lantern`/`EvidenceKernel` method returns (an `Observation`, `Evidence`, `ResolutionEvent`, or float belief), plus its own plain dicts from `status()` and `startup()`.

**Functional and tested:** Yes. `tests/test_lantern_agent.py` (4 tests: wrapping/forwarding correctness via `status()`, startup reconstructing bus/module history exactly, startup reconstructing full kernel state via delegated `Lantern.startup()`, and correct `NO_CHRONICLE` behavior with no chronicle attached) all pass.

**Depends on other lantern modules:** `core` only (imports nothing else; it is constructed with a `core.Lantern` instance but the file itself has no other `lantern` imports).

**Standalone:** Nearly fully — it only needs `core.py`.

**Standalone API candidate:** Yes — this is effectively the "public SDK surface" the rest of the system (bridge, evaluation, federation) is built on top of; exposing `observe`/`add_evidence`/`resolve`/`ask_belief`/`status` as API operations is a direct, natural mapping, though its capabilities are the same ones already offered by `core.py` itself (it adds no new capability, just a stable-shaped adapter and status/startup convenience).
