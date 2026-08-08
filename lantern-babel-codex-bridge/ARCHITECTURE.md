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

### Principle

A validated lesson promoted out of episodic/semantic memory after sustained, reinforced evidence. Principles are Concepts with a stricter promotion bar — **[OPEN: promotion criteria not yet specified]**.

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
