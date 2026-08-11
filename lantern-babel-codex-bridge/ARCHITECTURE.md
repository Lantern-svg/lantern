# LBCB Architecture

This document is the contract: it defines module boundaries, data shapes, and the invariants each module must uphold. Sections marked **[OPEN]** are known to require freezing before v1 and are called out explicitly rather than guessed at.

## Design principle

Reasoning is separate from truth. Every module answers "why does the system currently believe X, how strongly, and what would change it" — never "what is objectively true."

## Data model

These seven object types are the frozen contract surface. Everything else in the system operates on top of them.

### Observation

```
Observation {
  id
  timestamp
  source
  content
  reliability
  metadata
}
```

Raw structured input. Immutable once recorded.

### Concept

Output of the Interpretation Engine. A node in the Codex.

```
Concept {
  id
  semantic_definition
  relationships        // typed edges to other concepts, not similarity scores
  evidence_history      // ordered list of Evidence refs
  confidence             // derived, see Evidence Engine
  provenance
  contradiction_history
  version_history
}
```

### Evidence

```
Evidence {
  weight
  sign            // supporting | contradicting
  source
  timestamp
  provenance
}
```

### Belief

A concept's evaluated state at a point in time: the confidence value plus the evidence set that produced it. Beliefs are derived/query-time views over Concept + Evidence, not stored independently — this is what makes temporal replay possible (see Codex Temporal Queries below).

### Contradiction

```
Contradiction {
  belief_a
  belief_b
  severity
  evidence
  resolution_state   // open | resolved
  resolution_event    // ref to the Evidence or adjudication record that resolved it, if any
}
```

Never deleted. `resolution_state` transitions are themselves logged events, not silent overwrites.

### Scar

```
Scar {
  id
  timestamp
  source
  trigger
  observation
  outcome
  severity
  lesson                    // optional
  related_contradiction_id  // optional
  related_evidence_ids      // optional
  protocol_version
  provenance
}
```

A durable consequence record of a *meaningful* outcome, contradiction, failure, or success — not a generic log line, and not automatic memory of every event. A Scar is deliberately gated: see "The Scar gate" below. Once persisted, a Scar is immutable, like Observation and Evidence.

A Scar is not a Belief, not a Principle, and not a Codex mutation. It is raw, durable experience that later reasoning *may* draw on as input — the transformation from Scar to Principle/Belief is always a separate, explicit step (see "Scar vs. Belief vs. Principle" below), never automatic.

### Principle

A validated lesson promoted out of episodic/semantic memory (which may include persisted Scars as candidate input) after sustained, reinforced evidence. Principles are Concepts with a stricter promotion bar — **[OPEN: promotion criteria not yet specified]**.

### ReasoningTrace

Attached to every Reasoning Engine output. Contains the observations, concepts, evidence, and memory items actually used to reach a conclusion, in order, so the conclusion is auditable rather than opaque.

```
ReasoningTrace {
  conclusion
  steps[]          // ordered list of {input_ref, operation, output_ref}
  concepts_used[]
  evidence_used[]
  goal_context
}
```

## Modules

### Observation Engine

Responsibility: capture input as an `Observation`. Does not interpret. Reliability is an input-level property (source trust), separate from Evidence weight (claim-level trust), and the two must not be conflated.

### Interpretation Engine

Responsibility: `Observation → Concept` (create or update). Extracts concepts, relationships, uncertainty, and initial confidence. Stores meaning, not the source sentence — the Observation retains the original content for provenance, the Concept holds only the extracted semantics.

### Evidence Engine

Responsibility: maintain the Evidence list per Concept and compute confidence from it.

**[OPEN — must be frozen before v1]**
- Exact evidence update equation (how weight + sign + reliability combine).
- Exact decay function (form: linear, exponential, half-life; per-evidence or per-concept; decay triggers).
- Whether confidence is bounded/normalized, and how.

Until frozen: confidence is described qualitatively as "accumulated supporting vs. opposing evidence, weighted by reliability, subject to temporal decay." No public implementation should ship before this equation is written down and versioned, since every downstream module (contradiction severity, reasoning traces) depends on it being reproducible across implementations.

### Contradiction Engine

Responsibility: detect conflicts between Beliefs and materialize them as `Contradiction` objects.

**[OPEN — must be frozen before v1]**
- Contradiction severity function (inputs: confidence delta of the two beliefs? evidence overlap? semantic distance of the relationship being violated?).
- Detection trigger: on every new Evidence, on a schedule, or on query?

Frozen already: contradictions are never deleted; resolution is a separate, logged event (new evidence tipping the balance, or an explicit adjudication record), not a silent overwrite.

### Memory Engine

Layers: working, episodic, semantic, principles. Evidence decays unless reinforced by new Observations — this is the mechanism by which outdated information fades without being erased (it remains in history, just low-confidence).

**[OPEN]** Exact boundary between episodic and semantic promotion, and between semantic and Principle promotion.

### Reasoning Engine

Responsibility: combine Observations, Memory, Evidence, values, and current goals into a decision, always paired with a `ReasoningTrace`. No conclusion is emitted without its trace.

### The Codex

A semantic graph, not a knowledge graph and not a vector store. Nodes are Concepts; edges carry explicit meaning (typed relationships), not just embedding similarity. Vector search is permitted for candidate retrieval only — it never establishes equivalence or truth on its own.

**Temporal queries.** The Codex must support "what did the system believe at time T" by replaying Belief state using only Evidence with `timestamp <= T`. This is what makes experiments reproducible and lets later conclusions be audited against what was knowable earlier. This requires Evidence and Concept version history to be append-only.

**[OPEN]** Storage backend is unspecified at the protocol level — the protocol should define the query semantics (temporal replay, contradiction lookup, provenance chain traversal), not mandate a specific database.

### The Scar Engine

Responsibility: turn a meaningful Outcome into a durable `Scar`, persist it through the existing Chronicle (no second database), and make it available again after restart via replay. Does not decide truth, does not touch Evidence, does not touch belief.

See "The interoperability loop" and "Scar persistence" below for the full model, the gating rule, and the durability guarantee.

## The interoperability loop

Lantern's interaction lifecycle with another agent or node is a loop, not a one-shot handshake:

```
DISCOVER
   ↓
UNDERSTAND
   ↓
EVALUATE
   ↓
CONTACT
   ↓
EXCHANGE
   ↓
VERIFY
   ↓
COLLABORATE
   ↓
INTEGRATE
   ↓
SCAR
   ↓
MEMORY
   ↺
```

- **DISCOVER** — find that another agent/project/node exists.
- **UNDERSTAND** — read what it actually does (docs, source, protocol), not what it claims.
- **EVALUATE** — assess license compatibility, architecture fit, and whether contact is worthwhile.
- **CONTACT** — an explicit, justified reach-out (never mass/spam contact).
- **EXCHANGE** — a real protocol exchange (e.g. handshake, `OBSERVATION_SHARE`), not documentation-reading.
- **VERIFY** — independently confirm the exchange happened and produced what was claimed.
- **COLLABORATE** — sustained, bounded joint work under the existing capability/trust boundaries.
- **INTEGRATE** — durable acceptance of an outcome into Lantern's own operating model (still capability-gated; never automatic).
- **SCAR** — if the outcome of any of the above stages was meaningful (a real failure, incompatibility, contradiction, unexpected result, or significant success), it may be explicitly recorded as a Scar.
- **MEMORY** — the Scar, once durably persisted through Chronicle, is available for future reasoning — across restarts, not just within one process's lifetime. This is the loop-back arrow: memory feeds back into how future DISCOVER/EVALUATE/CONTACT decisions get made, but only as input a later, explicit reasoning step chooses to use.

**As of this document, SCAR/MEMORY is a real, tested persistence boundary** (see "Scar persistence" below), not a conceptual placeholder. Every other stage in this loop (DISCOVER through INTEGRATE) still operates on the existing Observation/Evidence/Contradiction/capability-negotiation machinery already described above; SCAR/MEMORY is what makes the *outcome* of the loop durable across restarts rather than existing only in one process's memory.

### Layer definitions used in this loop

These are deliberately distinct and must not be collapsed into each other:

- **EVENT** — something that occurred (a message arrived, a process ran, time passed). Not itself recorded as anything in Lantern until observed.
- **OBSERVATION** — what Lantern actually captured about an Event: a timestamped, sourced, immutable record (see `Observation` above).
- **EVIDENCE** — weighted, signed support or opposition for a Concept, derived from one or more Observations (see `Evidence` above).
- **CONTRADICTION** — incompatible Evidence or state for the same Concept, detected and threaded, never deleted (see `Contradiction` above).
- **OUTCOME** — the result of an interaction, exchange, or experiment (e.g. "handshake accepted," "remote protocol was incompatible," "integration succeeded then had to be rolled back"). An Outcome is transient by default — it does not automatically become anything durable.
- **SCAR** — a durable consequence record, created only when an Outcome is judged meaningful enough to preserve (see "The Scar gate"). A Scar is *constructed* in memory first; it is not yet a Scar in any durable sense until it is *persisted*.
- **MEMORY** — the set of persisted, verifiable, replayable Scars (plus existing Observation/Evidence/Contradiction/Resolution history) recoverable after a restart. Memory is retrievable experience, not automatic belief.
- **PRINCIPLE** — an interpretation derived later, deliberately, from accumulated Memory (including Scars). A Principle is a Concept with a stricter promotion bar (see `Principle` above); nothing in this loop creates a Principle automatically.

**Do not imply that every Event automatically becomes a Scar.** Most Events become, at most, an Observation. Most Outcomes are not meaningful enough to become a Scar. See the gate rule below.

### The Scar gate

> Experience may become a Scar only when the Outcome is meaningful enough to preserve.

Scar creation is a **deliberate, explicit decision**, never an automatic side effect of network traffic or routine operation:

- A trivial network message (a heartbeat, a routine `EVIDENCE_REQUEST`, an accepted `OBSERVATION_SHARE` with no contradiction or failure) does **not** create a Scar.
- A meaningful failure, incompatibility, contradiction, unexpected outcome, or significant success **may** qualify, and only when the calling code explicitly decides it does.
- The reference implementation encodes this as an outcome allowlist (`NETWORK_SCAR_OUTCOMES` in `src/lantern/scars.py`: `FAILED_HANDSHAKE`, `INCOMPATIBLE_PROTOCOL`, `REJECTED_CAPABILITY`, `CONTRADICTORY_OBSERVATION`, `INVALID_PROVENANCE`, `SUCCESSFUL_COLLABORATION`, `SUCCESSFUL_INTEGRATION`, `INTEGRATION_ROLLBACK`), combined with an explicit `meaningful=True` flag from the caller — both conditions must hold (`should_record_network_scar()`). Neither condition alone is sufficient.
- This allowlist is a starting point, not a closed law — it may grow, but growth must stay deliberate and documented, not implicit.

### Scar persistence

Scars are persisted through Lantern's **existing** Chronicle (the same append-only, SHA-256 hash-chained JSONL log already used for Observation/Evidence/Contradiction/Resolution events). **This is not a second database.** There is exactly one durable log per Lantern instance, and Scars are one more event type recorded in it (`SCAR_RECORDED`).

Documented flow:

```
Scar constructed
   ↓
Chronicle append
   ↓
verification
   ↓
runtime state
   ↓
snapshot / replay
   ↓
restart recovery
```

A **constructed** Scar is explicitly NOT equivalent to a **persisted** Scar. The reference implementation (`src/lantern/scars.py`, `src/lantern/core.py`) tracks four distinct states on every `ScarRecord`, and none of them are conflated for convenience:

- `constructed` — the `Scar` object exists in memory (`create_scar()`); nothing has been written anywhere.
- `persisted` — a Chronicle `append()` for `SCAR_RECORDED` actually completed (`Lantern.persist_scar()`).
- `verified` — `Chronicle.verify()` confirmed the hash chain is intact and the Scar is present in runtime state.
- `replayed` — the Scar was reconstructed from Chronicle/snapshot during `Lantern.startup()`, not merely held in the process that created it.

### Failure behavior (must hold, not just should)

- Failed persistence must never report `persisted=True`. If `Chronicle.append()` raises, `persist_scar()` propagates the exception and the original `ScarRecord` remains `persisted=False`; nothing is written to the in-memory `self.scars` map either.
- Chronicle corruption must remain detectable. `Lantern.startup()` calls `Chronicle.verify()` before any replay and raises `RuntimeError("Chronicle verification failed")` if the hash chain does not check out — this applies identically whether the corrupted event happens to be a Scar or any other event type.
- Restart recovery must reconstruct persisted Scars. `Lantern.startup()` restores the latest snapshot (which includes `scars`) and then replays any Chronicle records after that snapshot's chain position, applying `SCAR_RECORDED` events back into runtime state.
- Replay must reproduce persisted Scar records. `Lantern.replay_scars()` returns a `ScarRecord` for every Scar currently held in runtime state, each explicitly marked `replayed=True`.
- Scar persistence must not automatically mutate beliefs. `persist_scar()` never calls `add_evidence()`, `observe()`, or `resolve()`, and the architecture referee (below) enforces this as a checked invariant, not just a comment.
- Scar persistence must not automatically modify Codex state. Persisting a Scar only appends a `SCAR_RECORDED` event and updates `Lantern.scars`; it never touches `CodexModule.state`.
- Network events must not automatically become Scars. See "The Scar gate" above — the allowlist plus explicit `meaningful=True` gate is required every time.

### Scar vs. Belief vs. Principle

A Scar is durable experience. It is deliberately **not** any of the following, and no code path collapses these:

- **SCAR ≠ BELIEF** — persisting a Scar never calls `add_evidence()` or changes any concept's belief score.
- **SCAR ≠ PRINCIPLE** — a Scar is a single dated record of one Outcome; a Principle is a promoted, reinforced Concept. Promotion criteria remain **[OPEN]** (see `Principle` above) and are out of scope for the Scar Engine.
- **SCAR ≠ CODEX UPDATE** — persisting a Scar never touches `CodexModule.state`, and the `codex_update` capability remains disabled by default regardless of Scar activity.

A Scar *may* later become input to evidence for a principle, but that transformation is always a separate, later, explicit reasoning step — there is no automatic pipeline from Scar to Belief. The safer, and current, architecture is:

```
SCAR
  ↓
future evaluation   (explicit, not automatic)
  ↓
possible evidence / principle candidate
  ↓
future belief update   (still goes through add_evidence(), same as any other evidence)
```

### Worked example: an incompatible-protocol Scar

1. Lantern contacts another node (CONTACT).
2. The remote node reports an incompatible protocol during handshake (EXCHANGE).
3. Lantern evaluates the interaction (VERIFY): the outcome is `INCOMPATIBLE_PROTOCOL`, which is on the network-scar allowlist, and the caller judges it meaningful.
4. Lantern explicitly calls `create_network_scar(outcome="INCOMPATIBLE_PROTOCOL", ...)`, producing a `ScarRecord` with `constructed=True, persisted=False`.
5. Lantern calls `persist_scar(record)`. The Scar is written to Chronicle as a `SCAR_RECORDED` event.
6. Chronicle is verified (`Chronicle.verify()` returns `True`); the returned record now has `persisted=True, verified=True`.
7. Lantern restarts (a fresh process, a fresh `Lantern(...)`).
8. `startup()` verifies the Chronicle, restores the latest snapshot, and replays events after it.
9. The Scar is replayed: `load_scar(scar_id)` and `replay_scars()` both return it, now with `replayed=True`.
10. The Scar remains available as historical experience for as long as the Chronicle exists.

What Lantern explicitly does **not** do as a result of this:

- Lantern does **not** automatically conclude "that remote node is bad." No belief about the remote node is created or changed.
- Lantern does **not** automatically change any Concept's belief score. `persist_scar()` never calls `add_evidence()`.
- Lantern **remembers what happened** — the Scar is durable, verifiable, replayable data — so a *future*, explicit reasoning step can choose to treat it as input. That distinction (remembering vs. concluding) is fundamental to why Scar persistence is safe to add without opening a path for a remote peer to indirectly control local belief.

## Verification model

Confidence increases only through independent support. None of the following are individually authoritative:

- cited sources
- multiple independent observations
- human review
- reproducible experiments
- cross-model agreement — weighted low; models sharing architecture, training data, or failure modes means agreement is correlation, not independent verification

Semantic similarity alone never establishes equivalence between two claims.

## Protocol-first principle

The specification (this document plus the frozen math core, once written) must be sufficient for an independent reimplementation in a different language to reproduce the same reasoning behavior given the same inputs. If a reimplementation diverges, that's a signal the spec is underspecified, not that the reimplementation is wrong.

## Open items before v1 (summary)

1. Evidence update equation.
2. Decay function (form + trigger).
3. Contradiction severity function.
4. Confidence-over-time function (how decay and new evidence interact over the full history, not just pairwise).
5. Principle promotion criteria.
6. Episodic → semantic memory promotion boundary.
7. Scar → Principle promotion criteria (when, and under what accumulation rule, a set of persisted Scars becomes evidence for a Principle). Not yet specified; deliberately left as a future, explicit reasoning step rather than an automatic pipeline.
8. Whether the current network-scar outcome allowlist (`NETWORK_SCAR_OUTCOMES`) needs to grow, and the process for adding to it without making Scar creation implicit.
