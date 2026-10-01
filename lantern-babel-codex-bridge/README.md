# Lantern

An auditable evidence/belief engine and inter-instance exchange protocol for AI systems.

Lantern does not decide what is true. It tracks *why* a belief is currently held, *how strongly*, and *what would change it*. Reasoning is separated from truth: the engine's job is transparency and revisability, not adjudication.

> Shared understanding is built through evidence, perspective, and continuous verification — not assumption.

---

## What Lantern Is

Lantern is a Python library and network protocol that gives AI agents a structured, auditable belief system. Instead of storing text and retrieving it later, Lantern tracks evidence with provenance, computes beliefs from weighted evidence, detects contradictions, and preserves errors as durable learning signals.

An AI agent using Lantern doesn't just remember what it saw — it maintains a continuously updated model of what it believes, why, and how confident it is. When new evidence contradicts existing beliefs, the contradiction is detected, tracked, and resolved through an explicit process — not silently overwritten.

## The Problem

Most agent memory systems answer: *What did the agent see before?*

Lantern answers: *What does the agent believe, and why — and what evidence contradicts that belief?*

Existing agent memory frameworks (CoALA, Letta/MemGPT, Mem0) treat memory as storage and retrieval. They store conversation history, summarize it, and retrieve relevant pieces. None of them:

- Compute belief from weighted, signed evidence
- Detect formal contradictions between beliefs
- Track contradictions as first-class objects with lifecycle and resolution
- Preserve errors as permanent structural signals
- Maintain cryptographic provenance for every evidence item

The BEAM benchmark (2026) found near-zero contradiction-resolution scores across existing agent memory systems. This is the gap Lantern addresses.

---

## How Lantern Got Here — The Organogenesis Pipeline

Lantern wasn't designed top-down. It evolved through an **Organogenesis Pipeline**: a formal process where informal hacks become repeated patterns, patterns become named principles, and principles become load-bearing organs.

```
Need → Informal Practice → Repeated Pattern → Named Principle → Formal Organ
```

This is not a metaphor. It's how the codebase actually grew. Two examples:

### The Fixed Point → Drift Detection

The earliest Lantern code was a `FixedPointAgent` — a simple agent anchored to an immutable `FixedPoint` (owner, purpose, rules) with a heartbeat, a memory log, and drift detection that triggered self-correction:

```python
# Proto-Lantern: FixedPointAgent (early prototype — illustrative snippet,
# not a file in this repository)
agent._evaluate_drift()   # Count contradictions in recent memory
agent._recenter()         # Reset to fixed point when drift > 0.5
```

*Note: The proto-Lantern code snippets in this section are illustrative
historical artifacts showing the conceptual evolution of the architecture.
They are not files in this repository. The production Lantern system is
the code in `src/lantern/`.*

Through the Organogenesis Pipeline, this became:

| Stage | What Happened |
|---|---|
| Need | Prevent an agent from drifting away from its purpose |
| Informal Practice | FixedPointAgent with a simple drift counter |
| Repeated Pattern | heartbeat → drift → recenter appeared across multiple versions |
| Named Principle | "Drift Detection" — identity preservation over trajectories |
| Formal Organ | Immune System #2 (v48): Drift Detection with Growth = Change + Continuity, Drift = Change - Continuity |

### The Ambassador Gate → Capability Authorization

The same proto-code had an ambassador mode where the agent proposed actions but could not self-authorize them — a human had to approve:

```python
# Proto-Lantern: Ambassador Mode (early prototype — illustrative snippet,
# not a file in this repository)
action = agent.propose_action("Send message to external system")  # NOT authorized
agent.approve_action(action)  # Human approves → action released
```

*Note: In this prototype, `approve_action()` was a method on the agent
itself — there was no structural enforcement preventing self-authorization.
The prototype demonstrated the concept of proposal → approval, but the
production authorization mechanism is the stronger enforcement layer:
operator-controlled capability grants, `NEVER_AUTHORIZABLE` structural
prohibition, and verified-session source binding.*

Through the Organogenesis Pipeline, this became:

| Stage | What Happened |
|---|---|
| Need | Prevent an agent from taking external actions without authorization |
| Informal Practice | propose_action / approve_action pattern |
| Repeated Pattern | Human-in-the-loop approval appeared across every external action |
| Named Principle | "Do not self-authorize external action" |
| Formal Organ | Capability Authorization system: operator-controlled allowlist, `NEVER_AUTHORIZABLE` capabilities, verified sessions with source binding |

### The Lantern Swarm → Inter-Instance Protocol

The very first Lantern code was literally about lanterns — lights that turn on and off, coordinated as a swarm:

```python
# Proto-Lantern: Swarm coordination (earliest prototype — illustrative
# snippet, not a file in this repository)
coord = Coordinator(bus, [Lantern("A"), Lantern("B"), Lantern("C")])
coord.sync_all_on()  # Coordinate multiple lanterns
```

*Note: This historical swarm coordinator was an early synchronization
experiment. The coordinator did not possess actual authority over the
lanterns — each lantern changed state independently. The MessageBus was
not functionally enforcing coordination in the production sense. This
prototype explored the concept of multi-agent synchronization, which
later evolved into the inter-instance protocol with proper
authorization boundaries.*

Through the Organogenesis Pipeline, this became the inter-instance exchange protocol (v0.82) with Ed25519 identity verification, capability authorization, verified sessions, and evidence exchange.

---

## Core Architecture

```
┌─────────────────────────────────────────────────────────┐
│                     Lantern Node                          │
│                                                          │
│  ┌──────────────┐    ┌──────────────┐    ┌────────────┐  │
│  │  Observation  │───▶│  Evidence    │───▶│  Belief    │  │
│  │  Engine      │    │  Kernel      │    │  (computed)│  │
│  │              │    │              │    │            │  │
│  │ content      │    │ weight×sign  │    │ sigmoid(   │  │
│  │ source       │    │ decayed over │    │  Σ evidence│  │
│  │ reliability  │    │ time         │    │  ) = 0..1  │  │
│  └──────────────┘    └──────┬───────┘    └────────────┘  │
│                             │                            │
│                    ┌────────▼───────┐                     │
│                    │  Contradiction │                     │
│                    │  Engine        │                     │
│                    │                │                     │
│                    │  + / - evidence│                     │
│                    │  = tracked obj │                     │
│                    │  (not deleted)  │                     │
│                    └────────┬───────┘                     │
│                             │                            │
│                    ┌────────▼───────┐    ┌────────────┐  │
│                    │  Resolution    │───▶│  Scar       │  │
│                    │  Engine        │    │  System     │  │
│                    │                │    │             │  │
│                    │  decision +    │    │  permanent  │  │
│                    │  reasoning +   │    │  Chronicle  │  │
│                    │  confidence    │    │  record     │  │
│                    └────────────────┘    └────────────┘  │
│                                                          │
│  ┌──────────────────────────────────────────────────┐    │
│  │  Chronicle (SHA-256 hash chain, append-only)      │    │
│  │  Every event: observation, evidence, contradiction,│    │
│  │  resolution, scar — hashed and chained.          │    │
│  │  Replayable. Verifiable. Crash-recoverable.       │    │
│  └──────────────────────────────────────────────────┘    │
│                                                          │
│  ┌──────────────────────────────────────────────────┐    │
│  │  Inter-Instance Protocol (v0.82)                  │    │
│  │  Ed25519 identity · capability authorization     │    │
│  │  verified sessions · observation exchange        │    │
│  │  read-only belief queries                        │    │
│  └──────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────┘
```

### Evidence-Based Beliefs [VERIFIED]

Every belief is computed from evidence, not assigned.

```
belief(concept) = sigmoid(Σ decayed_weight × sign)
```

- Each evidence item has a `weight` (scaled by source reliability) and a `sign` (+1 supporting, -1 contradicting)
- Evidence decays over time: `decayed_weight = weight × max(0, 1 - 0.05 × age)`
- Belief is a value between 0 and 1 — a principled confidence score
- Belief can be replayed at any point in time using only evidence available up to that step

This means beliefs naturally weaken without reinforcement, respond to new evidence, and are never just "stored" — they're always computed from the evidence record.

### Contradiction Detection [VERIFIED]

When evidence with opposite signs exists for the same concept, a `Contradiction` object is created — not a deletion or silent overwrite.

```
Contradiction {
  concept, evidence_snapshot, severity,
  status: OPEN → RESOLVED,
  resolution_id, supersedes, superseded_by
}
```

- Severity = `min(Σ positive_weights, Σ negative_weights)` — the weight of the weaker side
- Contradictions form a chain: new contradictions supersede old ones, preserving history
- Resolution requires a `ResolutionEvent` with: decision, reasoning, confidence, and an evidence snapshot
- Contradictions are never deleted

### Provenance / Chronicle [VERIFIED]

The Chronicle is an append-only, SHA-256 hash-chained event log. Every state-changing event — observation, evidence, contradiction, resolution, scar — is recorded.

- Each record contains: timestamp, previous_hash, current_hash, event body
- Atomic writes with `fsync` + post-write verification (no partial corruption)
- Chain verification: replay the log and recompute every hash
- Snapshot/restore: full state can be saved and recovered after crash
- `records_after(chain_hash)`: incremental sync between nodes

Every evidence item carries provenance: `concept`, `observation_id`, `weight`, `sign`, `step`, `owner_instance`. You can trace any belief back to the specific observations that produced it.

### Scar Preservation [VERIFIED]

Errors and significant outcomes are preserved as `Scar` objects — permanent Chronicle-backed records that survive restart and replay.

```
Scar {
  id, timestamp, source, trigger,
  observation, outcome, severity,
  lesson, related_contradiction_id,
  related_evidence_ids, provenance
}
```

- Scars are frozen (immutable) dataclasses
- A Scar is only persisted after the Chronicle append succeeds and can be verified on replay
- Scars are remembered experience, not automatic belief changes — they record what happened so future reasoning can learn from it
- No scar is ever deleted

### Governance / Immune Systems [VERIFIED in protocol; PARTIAL in code]

Lantern's protocol history defines 8 immune systems — governance structures that constrain evolution at different scales. These were formalized through the Organogenesis Pipeline across 76 protocol versions (v44–v56):

| Immune System | Scope | Protocol Origin | Code Status |
|---|---|---|---|
| Invariant Gate | per-change code integrity | v50 | Specification |
| Drift Detection | per-trajectory identity | v48 | Specification |
| Fulfillment Engine | per-purpose meaning | v50 | Specification |
| Wisdom Safety Gate | per-principle validation | v51 | Specification |
| Collective Validation Gate | per-shared-truth | v52 | Specification |
| Diversity Gate | per-perspective | v53 | Specification |
| Continuity Immune Check | per-implementation | v55 | Specification |
| Evolution Selection Gate | per-growth mutation | v56 | Specification |

The current codebase implements the *substrate* these systems operate on (EvidenceKernel, Chronicle, Scars, capability authorization) but does not yet implement the 8 gates as named, executable modules.

### Capability Authorization [VERIFIED]

The inter-instance protocol uses a strict three-layer authorization model:

1. **Node identity** — Ed25519 keypair per node, verified via challenge/response. Note: `node_id` is a UUID-based *identifier* (a label), not a cryptographic identity. The Ed25519 keypair *is* the cryptographic identity. Challenge/response proves that the responder controls the private key bound to that node_id. See [NODE_IDENTITY.md](./NODE_IDENTITY.md) for the full distinction.
2. **Capability authorization** — operator-controlled allowlist (`--authorize node_id:capability`)
3. **Verified sessions** — short-lived tokens bound to the *cryptographically verified* node identity, not just the node_id label

`codex_update` is in `NEVER_AUTHORIZABLE` — structurally disabled in code, not just policy-gated. No operator grant can reach it. Receiving an observation never means trusting it; only local evaluation moves belief.

---

## How Lantern Differs From Conventional Agent Memory

| Capability | CoALA | Letta/MemGPT | Mem0 | Lantern |
|---|---|---|---|---|
| Evidence-based belief computation | No | No | No | Yes |
| Formal contradiction detection | No | No | No | Yes |
| Contradiction lifecycle (OPEN→RESOLVED) | No | No | No | Yes |
| Error preservation (scars) | No | No | No | Yes |
| Provenance at evidence level | No | Partial | No | Yes |
| Hash-chained event log | No | No | No | Yes |
| Temporal belief replay | No | No | No | Yes |
| Inter-agent evidence exchange | No | No | No | Yes (v0.82) |
| Read-only belief queries | No | No | No | Yes |
| Structurally unauthorizable capabilities | No | No | No | Yes |
| Benchmarks (LoCoMo, LongMemEval, BEAM) | Yes | Yes | Yes | No |

The last row is important: Lantern has no benchmark results. The architecture is novel, but its quality relative to existing systems is unproven.

---

## Current Verified Status

**What's verified and working:**

- Evidence kernel with weighted, signed, decaying evidence [VERIFIED]
- Belief computation via sigmoid of decayed evidence [VERIFIED]
- Contradiction detection with severity, lifecycle, and supersession [VERIFIED]
- Resolution events with decision, reasoning, confidence, evidence snapshot [VERIFIED]
- Chronicle: SHA-256 hash chain, atomic writes, verify, replay, snapshot/restore [VERIFIED]
- Scar system with Chronicle-backed persistence and replay verification [VERIFIED]
- Ed25519 identity with challenge/response verification [VERIFIED]
- Capability authorization with operator-controlled allowlist [VERIFIED]
- Verified sessions with source binding [VERIFIED]
- Inter-instance observation exchange over HTTP [VERIFIED]
- Read-only belief queries (belief_query) [VERIFIED locally; pending remote deployment]
- Owner-scoped storage (_OwnedDict / _OwnedList) preventing cross-instance data leakage [VERIFIED]
- 927 tests passing, 7 skipped [VERIFIED]
- Protocol version 0.82 [VERIFIED]
- Package version 0.84 [VERIFIED]

**What's specification only:**

- 8 immune systems as named executable modules [SPECIFICATION]
- Full 16-step organism loop [SPECIFICATION]
- Organogenesis Pipeline as automated process [SPECIFICATION]
- Multi-agent collective validation [SPECIFICATION]
- Wisdom extraction and cross-context validation [SPECIFICATION]

**What doesn't exist yet:**

- No benchmark results (LoCoMo, LongMemEval, BEAM) [NOT DONE]
- No external users or production deployments [NOT DONE]
- No standardized evaluation framework [NOT DONE]
- No formal protocol specification document separate from the implementation [NOT DONE]
- belief_query not yet deployed on any remote node [PENDING]

---

## Getting Started

### Install

```bash
git clone https://github.com/Lantern-svg/lantern.git
cd lantern
pip install -e ".[dev]"
```

### Run the Evidence Kernel

```python
from lantern.core import EvidenceKernel

kernel = EvidenceKernel(owner_instance="my-agent")

# Observe something
obs = kernel.observe("The sky is blue", source="sensor-1", reliability=0.9)

# Add supporting evidence
evidence, contradiction = kernel.add_evidence("sky_color", obs.id, weight=1.0, sign=1)

# Check belief (sigmoid of decayed weighted evidence)
print(kernel.belief("sky_color"))  # → ~0.71

# Observe contradicting evidence
obs2 = kernel.observe("The sky is green", source="sensor-2", reliability=0.7)
evidence2, contradiction = kernel.add_evidence("sky_color", obs2.id, weight=1.0, sign=-1)

# Contradiction detected
print(contradiction.status)  # → "OPEN"

# Belief shifts toward uncertainty
print(kernel.belief("sky_color"))  # → ~0.55

# Resolve the contradiction
resolution = kernel.resolve(contradiction.id, decision="sensor-1 is correct",
                           reasoning="calibration error in sensor-2", confidence=0.85)
```

### Run Tests

```bash
python -m pytest tests/ -v --ignore=tests/test_service_integration.py
```

Expected: 927 passed, 7 skipped (the 5 skipped tests require live MCP stdio or service integration environments).

### Run a Node

```bash
python -m lantern.bootstrap_node --node-id my-node --data-dir /tmp/lantern-data
```

Then check health:

```bash
curl http://localhost:8000/health
```

### Connect Two Nodes

See [EXTERNAL_BOOTSTRAP.md](./EXTERNAL_BOOTSTRAP.md) for the full inter-instance connection guide, including identity verification, session establishment, and capability authorization.

---

## Repository Structure

```
lantern/
├── src/lantern/
│   ├── core.py              # EvidenceKernel, Observation, Evidence, Contradiction, Chronicle
│   ├── scars.py             # Scar dataclass, persistence, replay verification
│   ├── identity.py          # Ed25519 node identity, challenge/response
│   ├── capability_authorization.py  # Operator-controlled capability allowlist
│   ├── verified_session.py # Session management with source binding
│   ├── bootstrap_node.py    # HTTP server: /health, /handshake, /message, /belief/query, ...
│   ├── bootstrap_client.py  # HTTP client for connecting to other nodes
│   ├── observation_exchange.py  # Observation sharing protocol
│   ├── protocol.py          # Protocol version, message types
│   ├── handshake.py         # Capability negotiation
│   ├── codex_compare.py     # Belief comparison between instances
│   ├── codex_explanation.py # Explanation generation for belief differences
│   ├── compass.py           # Read-only orientation layer
│   ├── compression.py       # Outcome → Scar validation
│   ├── contact_ledger.py    # Contact-state ladder
│   ├── ...                  # 48 modules total (including __init__.py)
├── tests/
│   ├── test_belief_query.py       # 12 tests for belief_query capability
│   ├── test_bootstrap_transport.py # HTTP transport tests
│   ├── test_observation_exchange.py # Observation sharing tests
│   ├── test_identity_two_node.py  # Two-node identity verification
│   ├── test_two_instance_integration.py # Full two-instance integration
│   ├── test_snapshot_recovery.py  # Chronicle snapshot/recovery
│   ├── ...                        # 53 test files total
├── ARCHITECTURE.md          # Full module breakdown and data model
├── EXTERNAL_BOOTSTRAP.md    # Inter-instance connection guide
├── NODE_IDENTITY.md         # Identity model documentation
├── demo_e2e.py              # End-to-end demonstration
├── service.py               # FastAPI service wrapper
├── pyproject.toml           # Package config (Python ≥3.10, PyNaCl)
├── LICENSE                  # MIT
```

**Stats:** 48 source modules, 53 test files, ~15,600 lines of Python, 927 passing tests.

---

## Roadmap

### Near-term (verified implementation → public release)
1. Deploy belief_query on a remote node and verify at wire level [IN PROGRESS]
2. Write the formal protocol specification, independent of the Python implementation
3. Freeze the mathematical core (evidence update equation, decay, contradiction severity, confidence-over-time)
4. Code review of the isolated public core

### Mid-term (benchmarks and evaluation)
5. Run Lantern's EvidenceKernel against the BEAM contradiction-resolution benchmark
6. Evaluate against LoCoMo and LongMemEval memory benchmarks
7. Implement and execute the 8 immune systems as named modules
8. Build a minimal reference implementation in a second language (Rust or Go) to validate protocol independence

### Long-term (adoption and ecosystem)
9. Standardize the inter-instance protocol for multi-agent evidence exchange
10. Build tooling for visualizing belief states and contradiction graphs
11. Support external contributors and third-party implementations

---

## Design Philosophy

Lantern is designed from dyslexic spatial cognition — thinking in structures, relationships, and patterns rather than sequences and procedures. The architecture uses spatial/archetypal naming (Marrow, Scars, Roots) reflecting the designer's cognitive pattern. This is a design principle, not just aesthetic: it produces an architecture organized around relationships and evidence rather than linear processing pipelines.

Research from [dyslexic.ai](https://dyslexic.ai/research) validates that dyslexic pattern recognition, holistic thinking, and creative synthesis are genuine cognitive advantages that can inform AI architecture design. Whether this approach produces measurably better reasoning is an open question — one we hope benchmarks will answer.

---

## Non-Goals

- Lantern does not replace any language model. It is model-agnostic.
- Lantern does not assert ground truth. It reports belief state and its provenance.
- Cross-model agreement is not treated as proof of correctness. It can nudge confidence but is never authoritative.
- Lantern is not a chatbot framework, an agent orchestrator, or a tool-use platform. It is a belief engine.

---

## License

MIT. See [LICENSE](./LICENSE).

## Contributing

Lantern is an experimental research project. If you want to test, review, challenge, or contribute:

1. Read [ARCHITECTURE.md](./ARCHITECTURE.md) for the full module breakdown
2. Read [EXTERNAL_BOOTSTRAP.md](./EXTERNAL_BOOTSTRAP.md) for the inter-instance protocol
3. Run the tests: `python -m pytest tests/ -v --ignore=tests/test_service_integration.py`
4. Try the evidence kernel example above
5. Open an issue with questions, challenges, or findings

The most valuable contributions right now are: independent review, benchmark evaluation, and protocol specification feedback.
