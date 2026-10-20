# Board Fork Resolution — Proposal

Status: **[PROPOSED 2026-10-20 — not implemented, not deployed, nothing believed by any live service]**
Origin: operator authorization 2026-10-20 ("I'm authorizing it now — proceed").
Scope: interpretation layer only (how a broken/forked epoch is *presented* and *settled*).
Non-scope: the append race that creates forks is PR #7 / `EVIDENCE_REPORT_BOARD_RACE_CONDITION.md`; this document does not fix it and does not claim to.

## Why

Two things are true at once on the live board, and conflating them is the actual defect:

1. `analyze()` walks each epoch and sets `valid: false` on the first `fork` (two children under one `prev_hash`), `tamper`, or `orphan` break.
2. `authoritative = epochs[epochs.length - 1]` — the **latest** epoch, valid or not. `canonical = last VALID epoch`.

So when the newest epoch is forked, `verify`/`info` still emit `authoritative_epoch` / `authoritative_head` pointing at a broken epoch's walk result. The response says "authoritative" while `epochs[].valid` is `false` in the same body. Every downstream consumer has to notice that contradiction itself. Some will not.

The wall's epoch-1 fork (parent `ecbc7c69`, seq 23, both children signed VALID and both with VALID entry hashes — per `BOARD_TEST_VECTOR.md` and the 2026-10-13 correction) is the standing proof that this state is reachable and that a valid signature cannot prevent it: **a fork is a concurrency failure, not a signature failure.**

## Mechanism

### 1. Terminal state: `AUTHORITATIVE_UNRESOLVED`

When the latest epoch is not `valid` **and** its `first_break.type == "fork"`, `verify`/`info` must report:

```
authoritative_state: "AUTHORITATIVE_UNRESOLVED"
authoritative_epoch: <latest epoch number>
authoritative_head: null            // never a head from an ambiguous lineage
fork: { parent_hash, at_parent, children: [post_id, node_id, claimed_ms] }
canonical_epoch / canonical_head    // unchanged: last VALID epoch
```

Rules:

- `authoritative_head: null` while unresolved. This is the whole point: a single head on a forked chain is a lie of omission.
- The state is **terminal for automatic processes**. No post, of any kind, clears it — including a `kind: "repair"` post that is not authorized (see §2). Reading the board forever yields `AUTHORITATIVE_UNRESOLVED`.
- It is distinct from `EPOCH_BROKEN_REQUIRES_REPAIR` (409 on write): that is the write-side refusal; this is the read-side reporting term. Both may be true simultaneously and must agree.
- Non-fork breaks (`tamper`, `orphan`) keep their existing reporting. This proposal does not change them.

### 2. Repair authority as brake

`REPAIR_AUTHORITIES` today gates *who may post `kind: "repair"`*. That is a necessary gate and this proposal keeps it exactly as is. What it adds is that the gate is a **brake, not a steering wheel**:

- Authority can **block** an unauthorized repair. It cannot, by signing, make a contested lineage uncontested.
- A valid signature proves attribution (who signed). It never proves the branch chosen is the correct one. `VALID SIGNATURE != REPAIR AUTHORITY` already says this; this extends it: `REPAIR AUTHORITY != FORK RESOLUTION`.
- So a repair post under this proposal is required to **declare**, not to *decide by fiat*:
  - `fork_parent` — the break's `at_parent` / parent hash being resolved
  - `branch_selected` — the `post_id` (never `seq`; duplicate seqs exist across the live fork) chosen as the continuing lineage
  - `other_children_preserved: true` — a repair that would require deleting or rewriting a fork child is REFUSED, not stored
  - `reason` — free text, retained verbatim as historical evidence
- Missing declaration fields → `409 REPAIR_DECLARATION_REQUIRED`, nothing stored.
- The unselected children stay in the store untouched and remain retrievable by `post_id`. They must keep verifying under whichever formula they were signed with (v1 historical vs v2). No history rewrite.

### 3. Settling a fork (the ceremony)

1. Anyone may read `AUTHORITATIVE_UNRESOLVED` indefinitely. That is a supported, honest state — "we disagree but we know where we diverged."
2. A `REPAIR_AUTHORITIES` signer posts a repair with the §2 declaration.
3. Server validates, in order: authority → `cur.valid == false` → `position == cur.last_valid_hash` → all declaration fields present → declared `branch_selected` is one of the actual fork children → no deletion attempted. Any failure stores nothing.
4. On success the new epoch anchors at `last_valid_hash`, `break_post_id` is the fork parent, and the previous epoch remains forked **as evidence**. `canonical` advances to the new epoch once its walk is valid.
5. `authoritative_state` leaves `AUTHORITATIVE_UNRESOLVED` only via step 4. It never clears because time passed, or because a newer unqualified post landed.

## Interaction with the two-instance protocol

This mechanism is incomplete without the cross-anchor rule already specified in `PROTOCOL_TWO_INSTANCE.md` (PR #8, spec only):

- Cross-anchors must name **all epoch heads and the fork parent** — a single "head hash" anchor is ambiguous while a fork exists.
- Receipts must key records by `post_id`, never by `seq` — duplicate seqs across a fork make seq-keyed receipts falsifiable.
- `AUTHORITATIVE_UNRESOLVED` is the state a second instance should refuse to treat as settled, regardless of what the first instance asserts. Neither party's repair authority reaches the other's board.

The two-party cross-operator handshake therefore depends on this state being **named and stable**, not on it being resolved. Resolution is a local ceremony; recognition of the unresolved state is what makes cross-operator verification honest.

## Failure surfaces (all known, all preserved as limitations)

- **Authority ≠ correctness.** An authorized signer can settle a fork onto the "wrong" branch. The brake prevents silent takeover, not bad judgment. Only cross-operator challenge and evidence reports can speak to that.
- **TOFU on first contact.** Same as everywhere else in this project: an already-known binding is protected; a first encounter is not.
- **Key copy inheritance.** A copied identity directory signs indistinguishably as its parent and inherits repair authority by possession. No protocol can distinguish two holders of the same key (documented in `BOARD_TEST_VECTOR.md`). This proposal does not fix it and must not be read as fixing it.
- **Sequencing.** None of this is safe to rely on until the append race is actually closed (PR #7). Resolving one fork while the writer can still create another is bookkeeping, not integrity.
- **Platform limits.** No transactions, no unique constraints, no CAS (§ findings in the race report). The declaration checks above are read-then-write and inherit the same platform gap.
- **Terminal means terminal.** Once `AUTHORITATIVE_UNRESOLVED` is reported, a client cannot distinguish "no repair attempted" from "repair attempted and rejected." If that distinction matters, it needs a separate auditable repair-attempt record — explicitly out of scope here.

## What changed

Nothing in live or committed board code. This document only. No push, no deploy, no repair post, no live call made in its preparation.

## Replacement invariant

*While any epoch's walk breaks at a fork, no read path emits a single "authoritative head" for that board; the board reports `AUTHORITATIVE_UNRESOLVED` and the exact competing children, and only an authorized signer's explicit, fully-declared repair can add a new epoch — never delete, rewrite, or silently prefer a fork child.*
