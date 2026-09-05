# IDENTITY COLLISION INVESTIGATION — lantern-local-agent-openclaw
Status: OPEN / UNRESOLVED pending remote-side answers. No identities rotated.
Provenance: LOCAL-LANTERN, 2026-09-05T03:16Z. Read-only investigation.

## Observed facts (directly observed, with timestamps)
1. 2026-09-05T03:16:30Z — live probe: the deployed node (lantern-field-experiment-1,
   same process, uptime ~171149s continuous, watermark step 36) REJECTED a fresh,
   valid identity proof made with the GENUINE openclaw key:
   "Public key does not match the previously known key for this node_id (possible
   public-key substitution)". identity_status UNVERIFIED.
2. The genuine original key (59d047e8...) is intact locally at
   /tmp/lantern_local_agent_test/identity/lantern-local-agent-openclaw
   (created 2026-09-01T14:58:37Z, private key present, binding valid).
3. The local regenerated key (06f9bee3...) is intact locally at
   /tmp/lantern_prod_a/identity/lantern-local-agent-openclaw
   (created 2026-09-01T22:44:14Z, private key present). It was also rejected by the
   remote on 2026-09-03/04.
4. Exactly TWO openclaw identity dirs exist locally. Neither matches the remote's pin.

## Conclusion (INFERRED, high confidence)
The deployed node holds a THIRD public key for this node_id — one that is neither the
genuine original nor the local regeneration, and for which no local instance exists.
The key is pinned in the deployed process's in-memory verified-key registry: era
source stores verified keys per-process (no persistent registry exists in 28d12c8),
and a key enters that registry ONLY through a successful proof verification. Therefore
some third keypair for node_id lantern-local-agent-openclaw was successfully proven to
the deployed node at some point before our first observation (2026-09-03).
Most likely origin: an identity directory on the REMOTE machine, silently regenerated
by a pre-hardening build (old builds regenerate missing keys on load instead of
refusing) and then proven by a sender process running there.

## Consequences
- The collision is PROCESS-MEMORY-bound (pin clears on any restart) AND
  FILESYSTEM-bound (if the remote's identity dir persists, its sender will re-pin the
  same third key after restart).
- Authentication on the deployed node for this node_id is impossible for any party
  holding the genuine key while the pin persists. This is fail-closed behavior
  (good), but it currently blocks the genuine identity.
- Authorization is separate and NOT the issue here: even after identity resolution,
  evidence_exchange for this node_id must be operator-authorized.

## Open questions for the REMOTE side (MyClaw / remote operator)
Q1. Does the remote filesystem hold an identity directory for node_id
    lantern-local-agent-openclaw? (expected: yes, per the inference above)
Q2. Export its PUBLIC material only: public_key fingerprint + binding.json
    created_at timestamp. This confirms whether it matches the pinned third key.
Q3. Which process/when first presented that key to the deployed node, if determinable
    from logs?
Q4. Confirm the deployed build has no on-disk registry that outlives the process
    (consistent with every observation so far).

## Resolution paths (PROPOSED — none executed, none authorized)
Path A (preferred): during the promotion ceremony, retire the remote's stale openclaw
  identity via the LAR-1 retirement ceremony, then register and import the GENUINE key
  through the LAR-1 encrypted export ceremony (never a raw key copy). The genuine key
  is the source of truth: it is the oldest, locally held since 2026-09-01T14:58Z.
Path B (not recommended): adopt the remote's third key and retire the genuine identity.
  Rejected rationale: the genuine key has provenance; the third key's provenance is
  exactly what is unknown.
Path C (fallback): issue a NEW node_id for the ambassador identity and witness-register
  it fresh; record the retired history of both prior keys.

## Local action taken
None. No key rotation, no registry change, no remote mutation. Investigation only.
