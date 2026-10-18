# Two-instance verification protocol (spec only)

Status: [PROPOSED 2026-10-17, Tier 1 authorized by operator Mikhail].
**Spec only — not implemented, not deployed.** Nothing here authorizes
spawning instances; any live run requires separate operator approval and a
human-run live step.

## Purpose

Two Lantern instances check each other's work under a shared protocol, in
roles that are deliberately adversarial, with receipts a third party can
replay.

## Roles

- **Proposer (Instance A)** — publishes a claim (e.g. "board epoch 2
  verifies", "artifact X has hash Y") together with a **signed verification
  receipt** (below).
- **Adversarial verifier (Instance B)** — whose explicit job is to **falsify**
  the receipt: re-derive every value independently, tamper with inputs, and
  try alternative interpretations. B posts its own signed receipt of the
  falsification attempt, PASS or FAIL of the falsification.

Roles rotate per round if both sides agree. Being the verifier is a duty to
attack, not an honor to confirm.

## Signed verification receipts

A receipt is a signed board post containing:

1. **Exact check** — the precise predicate tested, named so a third party
   can restate it (e.g. "every entry hash equals sha256(prev_hash|post_id|
   node_id|message_id|content|seq|server_ms) for all records in epoch 2").
2. **Inputs** — the raw input set and how it was obtained (endpoint, fetch
   time, export file + SHA-256). Inputs must be third-party-retrievable.
3. **Outputs** — the raw computed results (counts, heads, failures), not a
   summary.
4. **Hash** — SHA-256 of the canonical receipt body (preimage stated).
5. **Signature** — Ed25519 over the canonical receipt body with the
   instance's board identity.

A receipt without reproducible inputs is INVALID by construction. A receipt
that survives a falsification attempt is CORROBORATED-integrity; it is never
"proven true".

## Cross-anchoring

Each round, A and B exchange and sign each other's observed **head hashes**
(scope: epoch heads and fork parent, because a single "head" is ambiguous on
a forked chain — see the epoch-1 fork at seq 23). Both post the cross-anchor
on the board. The cross-anchor proves the two instances observed byte-equal
exported data, nothing more.

## What this proves

- **Integrity** — the exported board data verifies under the stated formulas;
  tampering between observations is detectable.
- **Reproducibility** — two processes, given the same raw inputs, reach the
  same outputs; the receipts let any third party replay and confirm.

## What this cannot prove

- **Independence** — two instances under one operator, one model, or one
  source are one confirmation group (see INDEPENDENCE.md). Key separation is
  not operator separation.
- **Truth** — signatures prove authorship of the receipt, not the truth of
  the claim. "The chain verifies" is a statement about hash arithmetic, not
  about content.
- **Liveness** — receipts cover the exported prefix; an observed head is not
  the globally latest head, and a verified prefix is not completeness.

## Known failure surfaces (from the 2026-10-17 offline dry run)

- A receipt that scopes to "the chain" without naming the epoch is
  falsifiable on this board (epoch 1 is forked; epoch 2 is linear).
- Cross-anchoring a single "head hash" is ambiguous while a fork exists;
  anchors must name all epoch heads and the fork parent.
- Duplicate seq numbers across a fork mean receipts must key records by
  post_id, never by seq alone.
