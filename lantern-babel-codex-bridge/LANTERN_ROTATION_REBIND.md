# Rotation Rebinding — Invariant and Implementation (B, 2026-09-07)

## Where the current ceremony stops working [AUDIT FINDING]
rotate_identity() (src/lantern/identity.py) generates a new keypair and a
RotationRecord signed by the OLD key over
`lantern.identity.rotation.v1|{node_id}|{old_pub}|{new_pub}|{rotated_at}`.
The record is written to disk and... nothing else. No peer, no board, no
verifier ever consumes it. The board's first-use binding still maps the alias
to the OLD key, so the legitimately rotated key is REJECTED (BINDING_MISMATCH)
while an illegitimate key-COPY works with zero ceremony. Legitimate rotation
is thus strictly weaker than copying. [OBSERVED, reproduced live]

## The rebinding invariant (v2.0.4)
A rotation is accepted ONLY when all of the following hold:
1. The old key is the CURRENTLY BOUND key for the alias (ROTATION_NOT_BOUND otherwise).
2. The old key signs the EXACT rotation statement.
3. The new key countersigns the SAME EXACT statement (no new-key-only fabrication).
4. rotated_at is within the timestamp window (replay protection); a rotation
   record is additionally chained (duplicate message_id impossible; replay of
   an accepted record fails at invariant 1 — the binding no longer names the
   old key).
5. The board records the rotation as an authenticated, chained, kind=rotation
   state transition (formula rotation-v1: dual signatures over the rotation
   statement — NOT the post canonical).
6. The alias is rebound to the new key (bindings.update).
7. The old key no longer satisfies ALIAS-MEDIATED authorization for that alias
   (subsequent posts -> BINDING_MISMATCH).
8. The new key becomes the currently bound identity for that alias.

SCOPE BOUNDARIES (documented, not silently twisted):
- Authority designations (REPAIR_AUTHORITIES) are fingerprint-keyed and do
  NOT transfer with rotation: authority = explicit designation + possession.
  Changing designation requires the operator ceremony. (Invariant 7 is
  satisfied for alias-binding contexts; repair authority follows designation.)
- Other aliases of the old key are UNAFFECTED (rotation is per-alias).
- Rotation does NOT revoke the old key's cryptographic identity: whoever
  possesses a private key possesses that identity. It revokes the old key's
  ALIAS ACCESS only.
