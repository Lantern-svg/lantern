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

For the first controlled external Lantern connection, see
[EXTERNAL_BOOTSTRAP.md](./EXTERNAL_BOOTSTRAP.md). It documents the minimal
HTTP transport adapter, exact install/start/connect commands, and the
secure-by-default identity/authorization model below, without changing the
core protocol or trust model.

## Networking and Security Model

A Lantern node can talk to other Lantern nodes over a minimal HTTP
transport. Three separate things gate whether that talking actually leads
to anything, and none of them imply the others:

- **Node identity** is a real Ed25519 keypair per node, verified via a
  challenge/response round trip. It proves *who* is on the other end of
  the connection. It is not trust, and it grants nothing by itself. See
  [NODE_IDENTITY.md](./NODE_IDENTITY.md).
- **Capability authorization** is an explicit, operator-set allowlist
  (`--authorize node_id:capability`) mapping a verified node id to specific
  capabilities. A peer proving its identity, or negotiating a shared
  capability during handshake, never grants authorization on its own —
  the operator has to say so.
- **Verified sessions** bind a short-lived token to an already-verified
  node id so the secure `/message` path doesn't have to redo the identity
  proof on every call. A session carries no capabilities of its own.

By default (`legacy_message_ingestion: false`), a peer must pass identity
verification, hold a live session, and have an explicit operator
authorization grant before `/message` accepts anything from it. An
operator can opt back into the old unauthenticated workflow with
`--allow-legacy-message-ingestion` (server) / `--legacy` (client) — off by
default, never inferred, and clearly weaker.

None of the above changes what a verified, authorized peer can actually do:
it can add an observation to your Chronicle. It cannot make your Lantern
believe anything, cannot mutate your Codex, and cannot trigger
`CODEX_UPDATE` — that capability is structurally disabled in code, not
just policy-gated, so no authorization grant can reach it. Receiving an
observation is never the same as trusting it; only your own local
evaluation moves belief.

Lantern also supports being discovered and joined over Discord as an
untrusted signaling/rendezvous channel only (never a trust anchor, never a
direct path to belief or evidence) — see the module docstrings in
`src/lantern/discord_bridge.py` and `src/lantern/discord_rendezvous.py`.

## Modules

- **Observation Engine** — captures incoming information as structured, sourced observations.
- **Interpretation Engine** — turns observations into concepts, relationships, and confidence/uncertainty estimates. Stores meaning, not sentences.
- **Evidence Engine** — maintains weighted, signed, sourced evidence for and against every concept. Confidence is computed, not assigned.
- **Contradiction Engine** — detects logical conflicts between beliefs and tracks them as objects with a lifecycle, not deletions.
- **Memory Engine** — working / episodic / semantic memory plus validated principles. Evidence decays unless reinforced.
- **Reasoning Engine** — combines observation, memory, evidence, values, and goals into decisions with an explicit reasoning trace.
- **The Codex** — a semantic graph of concepts (not documents), with explicit-meaning edges. Vector search is used for retrieval only; vectors are navigation, never truth.
- **The Scar Engine** — turns a *meaningful* outcome (a real failure, contradiction, incompatibility, or significant success — never routine traffic) into a durable, Chronicle-backed record that survives restart and replay. A Scar is remembered experience, not an automatic belief change; see [ARCHITECTURE.md](./ARCHITECTURE.md) for the full gating rule and the interoperability loop it closes (DISCOVER → … → INTEGRATE → SCAR → MEMORY).

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

MIT. See [LICENSE](./LICENSE).
