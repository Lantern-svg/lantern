# Lantern Babel Codex Bridge (LBCB)

An interoperability layer for shared understanding between humans and AI systems.

LBCB does not decide what is true. It exposes **why** a belief is currently held, **how strongly**, and **what would change it**. Reasoning is separated from truth: the engine's job is transparency and revisability, not adjudication.

> Shared understanding is built through evidence, perspective, and continuous verification — not assumption.

## Status

Research prototype ("the Lantern organism") with working evidence accumulation, confidence scoring, contradiction handling, temporal decay, priority management, and reflective narration. Currently being extracted into a minimal, documented, public core, separate from the full prototype.

This repository will ship the **protocol first, implementation second**: a specification precise enough that an independent implementation (Rust, Python, Go, JS) should arrive at the same reasoning behavior given the same inputs.

## Why

Most multi-model / human-AI systems exchange either raw text (lossy, ambiguous) or embeddings (similarity, not meaning). LBCB proposes a middle layer: a semantic graph of concepts backed by an auditable evidence trail, so agents and humans can compare *why* they believe something, not just *what* they output.

Core positions:

- Semantic similarity is never sufficient to establish equivalence.
- Contradictions are not deleted; they become first-class, tracked objects.
- Cross-model agreement is correlation, not independent verification — it can nudge confidence but is never authoritative.
- Belief state must be replayable at any point in time, using only evidence available up to that point.

## Architecture

See [ARCHITECTURE.md](./ARCHITECTURE.md) for the full module breakdown, data model, and open (not-yet-frozen) specification items.

## Modules

- **Observation Engine** — captures incoming information as structured, sourced observations.
- **Interpretation Engine** — turns observations into concepts, relationships, and confidence/uncertainty estimates. Stores meaning, not sentences.
- **Evidence Engine** — maintains weighted, signed, sourced evidence for and against every concept. Confidence is computed, not assigned.
- **Contradiction Engine** — detects logical conflicts between beliefs and tracks them as objects with a lifecycle, not deletions.
- **Memory Engine** — working / episodic / semantic memory plus validated principles. Evidence decays unless reinforced.
- **Reasoning Engine** — combines observation, memory, evidence, values, and goals into decisions with an explicit reasoning trace.
- **The Codex** — a semantic graph of concepts (not documents), with explicit-meaning edges. Vector search is used for retrieval only; vectors are navigation, never truth.

## Target users

Developers building AI systems that need an interoperability layer above one or more models, rather than a replacement for any of them. Candidate applications: human↔AI collaboration, AI↔AI communication, multi-agent reasoning, long-term memory systems, research assistants, autonomous software agents.

## Roadmap

1. Freeze the mathematical core (evidence update equation, decay, contradiction severity, confidence-over-time).
2. Freeze the data model (Observation, Concept, Evidence, Belief, Contradiction, Principle, ReasoningTrace).
3. Publish the protocol specification, independent of any single implementation.
4. Extract and release the minimal reference implementation.
5. Code review of the isolated public core.

## Non-goals

- LBCB does not replace any language model.
- LBCB does not assert ground truth; it reports belief state and its provenance.
- Cross-model agreement is not treated as proof of correctness.

## License

TBD.
