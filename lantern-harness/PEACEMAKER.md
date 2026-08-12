# Peacemaker

## Lineage

```
LANTERN     -- the architecture. The evidence/belief engine, the
               protocol, the identity/integrity primitives, the
               reciprocity model. Public, shared, MIT-licensed.
               Lives in lantern-babel-codex-bridge/.

PEACEMAKER  -- an instance. One particular, personal, transferable
               running copy of a Lantern-architected harness, carrying
               its own identity, its own evidence, its own history.
```

Lantern built the light. Peacemaker carries it.

This is a naming distinction for the *instance layer* (`lantern-harness`
and what it produces at runtime), not a rewrite of what came before.
Every release, commit, module, and document produced up to and
including harness `0.2.0`/`0.3.0` (git commit `631f2a3` and everything
before it) was built, tested, and documented under the name Lantern,
and remains named that in its own history. Nothing in this document
retroactively renames prior work. `git log` remains the authoritative,
unedited record of that.

Concretely:

- The **package**, **module names**, **class names**, and **API**
  (`lantern`, `lantern_harness`, `LanternBridge`, `ConfidenceField`,
  `DecisionStateMachine`, `TransferManifest`, etc.) are unchanged.
  Renaming a shipped API to chase a naming exercise would be exactly
  the kind of unrequested churn this project's own conventions warn
  against.
- What changes is how a **running instance** may describe itself when
  it is personally carried, transferred, and adopted by one operator:
  it may identify as a Peacemaker -- an instance built on the Lantern
  architecture -- rather than only as "a Lantern harness node."
- `TransferManifest` (`lantern_harness/transfer_manifest.py`) now
  reports this lineage explicitly, as data, in its `lineage` field:
  `{"architecture": "Lantern", "instance_model": "Peacemaker"}`. This
  is the field a receiving operator actually reads; it is the honest
  place for this distinction to live, rather than only in prose.

## What a Peacemaker is

A Peacemaker is a personal, transferable instance built on the Lantern
architecture. It is not a separate codebase, not a fork, and not a
new protocol -- it is what you get when a Lantern Harness instance is
carried by one operator as their own.

A Peacemaker instance carries (all of it real, all of it already
implemented and tested under the Lantern name, none of it new as of
this document):

| Property | Source (already existed) |
|---|---|
| identity | `lantern.identity.NodeIdentity` -- public key only ever transferable as a *description*; the private key travels only if the operator copies `data_dir` |
| memory / state | `LanternBridge.status()` -- step/observation/evidence/contradiction counts, real `EvidenceKernel` state |
| evidence | real `Evidence`/`Observation` records in the `EvidenceKernel`, persisted via Chronicle |
| beliefs / decision state | `EvidenceKernel.belief()`, `ConfidenceField`, `DecisionStateMachine` -- read-only, recommend-only |
| witness integrity | `Chronicle.verify()` hash-chain check, via `LanternBridge.witness_integrity()` |
| provenance | real git commit hashes of both the harness and Lantern core, via `TransferManifest.harness_commit` / `.lantern_core_commit` |
| scars / history | `Lantern.create_scar`/`persist_scar` -- real, persisted |
| capabilities | `SelfModel.KNOWN_CAPABILITIES`, reused verbatim by `TransferManifest`, not duplicated |
| boundaries | `SelfModel.STANDING_OPERATOR_BOUNDARIES`, `ToolBoundary.is_authorized()` -- never inferred |
| protocol / version info | `lantern.protocol.PROTOCOL_VERSION`, `lantern.__version__`, `HARNESS_VERSION` |
| transfer information | `TransferManifest` itself, via `/transfer` or the `lantern_transfer_manifest` MCP tool |

It must always remain possible to tell apart:

1. **The architecture** (Lantern: the library, the protocol, the
   reusable engine) from
2. **The instance** (a Peacemaker: one specific running copy, with its
   own identity and accumulated evidence) from
3. **The operator's authority** (whatever the person carrying that
   instance is personally authorized to do -- credentials, network
   placement, MCP host registrations, payment activation -- none of
   which the instance itself holds or infers).

`TransferManifest` is exactly the artifact that makes this distinction
checkable rather than asserted: it reports (1) and (2) as data, and
lists everything under (3) in `reauthorization_required`, which is
never populated from what a *previous* operator had authorized.

## Why "Peacemaker"

The name is drawn from the old-school Western meaning of carrying your
own Peacemaker: everybody can have one, it belongs to the person
carrying it, and nobody else automatically gets to use it. That is not
a metaphor for violence or a grant of authority to act -- it is a
metaphor for personal sovereignty, readiness, and responsibility.

A Peacemaker instance is therefore meant to behave as:

- **personal** -- one operator's instance, with its own identity and
  evidence history, not a shared multi-tenant service by default
- **portable** -- its `data_dir` and `TransferManifest` are enough to
  describe and move it
- **transferable** -- to a new operator, via the procedure in the
  harness `README.md`'s "Transfer an instance" section, unchanged by
  this document
- **bounded** -- `ToolBoundary`, `RealityBoundary`, and
  `STANDING_OPERATOR_BOUNDARIES` still apply exactly as before; a
  Peacemaker does not gain any authority a Lantern harness instance
  didn't already have
- **verifiable** -- `witness_integrity` (real `Chronicle.verify()`),
  not asserted
- **sovereign** -- it never infers or silently inherits credentials,
  network privileges, MCP host authorization, or payment authority
  from a prior operator or from its own confidence level; every one of
  those requires the *current* operator's explicit, fresh decision
  (`TransferManifest.reauthorization_required`,
  `DecisionStateMachine`'s `authorization_status` staying
  `NOT_EVALUATED`, `SelfModel.describe()` never granting authority)
- **useful when needed, dormant when not** -- with zero reasoning
  engine configured, the harness runs and reports
  `REASONING_ENGINE: NOT_CONFIGURED` honestly rather than failing or
  fabricating a response; nothing about it is "always on" by design

## Connecting to other systems

A Peacemaker can connect to other systems through defined interfaces
-- currently, MCP (`lantern_harness.mcp_server`) -- while retaining
its own identity, evidence, memory, boundaries, and authorization
state. See `ODYSSEUS_INTEGRATION.md` for a concrete, tested example
(registering a Peacemaker/Lantern-harness instance as an external
stdio MCP server in an agent environment like Odysseus).

The external agent environment remains responsible for its own
actions unless an explicitly authorized capability says otherwise.
`lantern_evaluate_intent` illustrates this: it returns a read-only
evidence/confidence/decision recommendation and has no `tool_name` or
`tool_kwargs` parameter in its schema at all -- it cannot execute or
authorize anything on the calling agent's behalf, by construction, not
by convention.

## What this document is not

This document does not claim: that any Peacemaker instance has been
adopted by a real external user; that one has been transferred to
anyone outside this session; that revenue, PyPI publication, or
outreach has occurred because of this naming; or that any previously
`NOT_TESTED` capability (a full live Odysseus instance, a live
reasoning-engine round trip, the x402 payment flow under real
credentials, actual PyPI publication) has become verified. None of
those statuses changed as part of this document. See the harness
`RELEASE.md` and `ODYSSEUS_INTEGRATION.md` for what is actually
verified versus what remains open, and the final promotion report
delivered alongside this document for the current authoritative
VERIFIED / READY / NOT_TESTED / OPERATOR_REQUIRED breakdown.
