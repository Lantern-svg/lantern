# Lantern Node Identity (Cryptographic)

Status: implemented, Phase 2A. Module: `src/lantern/identity.py`.

This document is about **cryptographic node identity** (a node proving
it controls a private key). It is unrelated to `LANTERN_IDENTITY.md`,
which describes Lantern's product/persona identity and commercial
capabilities.

## Core principle

```
node_id            -- an identifier. NOT an identity proof.
handshake           -- a protocol exchange. NOT automatically authentication.
Discord account     -- an external signaling identity. NOT a Lantern identity.
```

A successful cryptographic proof establishes exactly one thing:

```
identity_status = CRYPTOGRAPHICALLY_VERIFIED
```

It never automatically establishes `trust_status = TRUSTED` or any
`authority_level` other than `NONE`. Those remain separate, deliberate
Lantern decisions -- see `src/lantern/participants.py`.

## What identity verification PROVES

> "The responder controls the private key corresponding to the public
> key bound to node identity X, as of this specific challenge/response
> exchange."

## What identity verification DOES NOT PROVE

- That the responder is a trustworthy human or well-behaved agent.
- That the software running at that identity is unmodified.
- That any capability the node advertises is truthfully implemented.
- That the node is safe, or should receive any authority.
- That a first-contact node_id/public-key pairing is legitimate. This
  is a trust-on-first-use scheme: it protects an *already-known*
  binding from being silently replaced; it does not vet a brand-new
  claim the first time it is seen.
- Confidentiality of the exchange. This proves who signed a message,
  not that nobody else observed it.

Do not describe a `CRYPTOGRAPHICALLY_VERIFIED` node as a "trusted
node" anywhere in code, logs, or documentation. Use the precise claim
above.

## Identity file format

One identity = one directory:

```
<identity_dir>/
  private_key.bin   32-byte raw Ed25519 seed. Mode 0600.
  public_key.bin    32-byte raw Ed25519 verify key.
  binding.json      {"node_id", "public_key" (hex), "signature" (hex),
                      "created_at"}
```

`identity_dir` is fully caller-configurable (`NodeIdentity.load_or_create(node_id, identity_dir)`).
`bootstrap_node.LanternNode` defaults it to
`<chronicle_parent_dir>/identity/<node_id>/` -- a sibling of the
Chronicle file, never inside it, and never the same path. The private
key is never written into, or derivable from, any Chronicle file.

The private key never appears in:
- any Chronicle event (belief, evidence, join, or otherwise)
- any log line
- any HTTP response (`/health` exposes `identity_public()`: node_id,
  public key, binding signature -- never the private key)
- any handshake message (`HandshakeRequest`/`HandshakeResponse` carry
  no identity/key fields at all)
- any Discord payload (no Discord code path exists yet; when Phase 2
  Discord signaling is eventually implemented, only public material --
  proof/challenge objects, which are pure hex strings and node ids --
  would ever be eligible to cross that boundary)

`NodeIdentity` is deliberately a plain Python class, not a
`@dataclass`. `dataclasses.asdict()` walks every field regardless of
`repr=False`/`compare=False` -- making it a dataclass would leave a
single accidental `dataclasses.asdict(identity)` call anywhere in the
codebase one step away from leaking the live `SigningKey` object into
a plain dict. As a plain class, `asdict()` raises `TypeError` on it,
structurally, not by convention.

## Key lifecycle

1. **First run**: `load_or_create()` finds no `private_key.bin`,
   generates a fresh Ed25519 keypair, writes all three files
   (private key permissions set to 0600 immediately after write).
2. **Every subsequent run**, same `identity_dir`: loads the existing
   key material unchanged. Public key and node_id binding are stable
   across restarts.
3. **Rotation** (deliberate, operator-initiated only -- never
   automatic, never triggered by any handshake or proof code path):
   `rotate_identity(old_identity, identity_dir)` generates a new
   keypair and a `RotationRecord` **signed by the OLD private key**,
   attesting "node_id X now binds to this NEW public key, signed by
   the key it supersedes." An attacker who has only ever observed the
   old *public* key (never possessed the old *private* key) cannot
   forge a valid rotation record -- this is what prevents silent
   identity replacement.

   This module only produces the rotation record. **Propagating a
   rotation to peers who already trust the old key is an explicit,
   separate, out-of-scope, operator-driven step** -- not automated
   here, and not safe to automate without a broader trust-propagation
   design this phase deliberately did not build.

## node_id <-> public_key binding: design choice

`node_id` remains the existing, stable, human-readable identifier
(`"main-lantern"`, etc.) -- **not** replaced with `hash(public_key)`.
The binding is a separate, independently-verifiable signed record
(`binding.json`) instead, specifically because:

- it keeps `node_id` human-readable, requiring no rename across
  existing code/tests
- key rotation does not change the node_id a peer already knows the
  node by
- rotation becomes an explicit, auditable, signed transition instead
  of "this is now a different identity"

`verify_binding(node_id, public_key_hex, signature_hex)` lets anyone
holding only the public key verify the binding independently.

## Proof semantics: challenge/response

```
A (initiator)                          B (responder)
  issue_identity_challenge(B)  ------->
                                        respond_identity_challenge(challenge)
                              <-------  IdentityProof
  verify_identity_proof(proof)
```

- **Nonce**: `secrets.token_hex(32)`, single-use, freshly generated by
  the initiator per challenge.
- **Context binding**: the signed payload includes `nonce`,
  `from_node_id`, `to_node_id`, `protocol_version`, `claimed_node_id`,
  and `public_key` -- a proof for one (challenger, responder, protocol,
  nonce) tuple cannot be reinterpreted as valid for another.
- **Domain separation**: every signed payload in this module (binding,
  challenge-proof, rotation) is prefixed with a distinct domain tag
  (`lantern.identity.binding.v1`, `lantern.identity.challenge_proof.v1`,
  `lantern.identity.rotation.v1`) so a signature produced for one
  purpose can never be replayed as valid for a different purpose.
- **Freshness/expiry**: default TTL 90 seconds
  (`DEFAULT_CHALLENGE_TTL_SECONDS`), measured via `time.monotonic()`,
  not wall-clock, so it cannot be gamed by a forged timestamp.
- **Single-use**: `ChallengeStore.consume()` marks a nonce consumed
  **unconditionally**, whether or not verification succeeds -- a
  failed proof attempt cannot be retried against the same live
  challenge.
- **Trust-on-first-use pinning**: `verify_proof(..., expected_public_key=...)`
  rejects a proof presenting a different public key than one already
  known for that node_id. First contact (no prior key) has no
  protection against a well-timed initial impersonation -- inherent to
  any keys-only scheme without an external root of trust.

`ChallengeStore` is in-memory, per-process, not durable, and not
Chronicle-backed -- a challenge is a short-lived transport artifact,
not an audit record. A process restart mid-handshake simply loses any
in-flight challenge (safe: a lost challenge can never be replayed,
since it was never completed).

## Handshake correction (Phase 2A)

Prior to this phase, `handshake.evaluate_handshake()` generated a
fresh `uuid.uuid4()` for the response `node_id` on **every call**,
meaning the same physical node appeared to claim a different node_id
on every handshake response. Fixed via a new, backward-compatible
`responder_node_id` parameter:

```python
evaluate_handshake(request, responder_node_id=self.node_id)
```

Omitting `responder_node_id` preserves the old standalone behavior
(fresh `uuid4()`) so no existing caller breaks. `bootstrap_node.py`'s
`/handshake` route now always passes the node's real, configured
`node_id`. Regression-tested: repeated handshake responses from the
same running node now return the same `node_id` every time (see
`tests/test_lantern_identity.py::test_repeated_handshake_responses_preserve_identity`
and the real-HTTP version in `tests/test_lantern_identity_two_node.py`).

## Legacy compatibility

- **No protocol version change.** `identity_proof` was added as an
  ordinary entry in `compatibility.DEFAULT_CAPABILITIES` (default
  `False`), following the exact existing pattern `codex_update` already
  established. `compatibility.negotiate()` already handles unknown/
  unsupported capabilities generically -- no wire-format or version
  change was needed.
- **A legacy node (no identity support) remains explicitly
  distinguishable.** `ParticipantView` gained a new, independent field,
  `identity_status`, defaulting to `"UNVERIFIED"`. There is no code
  path anywhere that upgrades `identity_status` just because an
  ordinary handshake succeeded -- `participants.inspect()` never
  computes `identity_status` itself; a caller must explicitly pass in
  the result of a real challenge/response verification
  (`inspect(request, identity_status=result.identity_status)`).
- `trust_status` and `authority_level` are completely unaffected by
  any of this and remain hardcoded `"unverified"`/`"none"` exactly as
  before.

## Dependency

`PyNaCl >= 1.5.0` (Ed25519 via `nacl.signing`), declared as a **core**
dependency in `pyproject.toml`, not borrowed transitively from the
`[service]` extras' `pycryptodome` (which was already present in this
environment only because of the unrelated x402 payment stack, and
would not be available to a plain `pip install lantern` core install).
If `pynacl` is not installed, importing `lantern.identity` fails with
Python's normal, explicit `ModuleNotFoundError` -- there is no silent
HMAC fallback anywhere in this module.

## HTTP surface (bootstrap_node.py, additive only)

```
GET  /health                 now also returns "identity_public":
                              {node_id, public_key, binding_signature}
POST /identity/challenge     {"requester_node_id": "<peer>"} -> Challenge
POST /identity/respond       Challenge -> IdentityProof (signed by this node)
POST /identity/verify        IdentityProof -> {verified, reason, identity_status}
```

None of these new routes are required for a legacy `/handshake`,
`/join`, `/message`, or `/connection-state` exchange to keep working
exactly as before.

## Test plan / coverage

See `tests/test_lantern_identity.py` (43 tests, in-process) and
`tests/test_lantern_identity_two_node.py` (7 tests, real local HTTP,
two independent servers/identity stores/node_ids on 127.0.0.1
ephemeral ports). Categories covered: identity creation/persistence,
binding verification (valid/wrong node_id/wrong key/modified/
malformed), challenge/proof (valid, wrong key, wrong node_id, modified
nonce/initiator/responder/context, expired, replayed, consumed-nonce
reuse, public-key-substitution rejection), handshake responder
consistency, legacy-vs-verified distinguishability, trust/authority
non-mutation, key rotation, and security invariants (private key never
in Chronicle/HTTP/proof serialization/repr; `codex_update` stays
`False`; `identity_proof` capability defaults `False`).

## Known limitations

- Trust-on-first-use only. No external root of trust; a well-timed
  first-contact impersonation is not defended against by this layer.
- No transport-layer confidentiality. Proves signer identity, not that
  the exchange was unobserved or untampered-with in transit (though
  tampering with signed fields is detected and rejected).
- No capability-list tamper-binding yet: the challenge/proof does not
  currently sign over the negotiated capability list itself, so a
  modified-in-transit capability advertisement is not detected by this
  layer (flagged during Phase 2 research; not implemented here since
  it was out of the authorized Phase 2A scope).
- Rotation record propagation to already-trusting peers is
  intentionally not automated -- documented as an explicit future
  operator action, not built.
