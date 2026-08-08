"""
Lantern Continuity Watermark v0.92

Purpose:
- Expose the local continuity watermark using state that already
  exists (EvidenceKernel.step + Chronicle.chain)
- Classify a remote peer's claimed watermark relative to local
  state, strictly downstream of protocol compatibility
- Keep watermark comparison a comparison, never a proof of the
  remote's history

Continuity does not:
- create a second event counter (reuses EvidenceKernel.step)
- create a second audit chain (reuses Chronicle.chain)
- create a second persistence mechanism (reuses snapshot/restore,
  which already threads step + chronicle_chain together)
- mutate belief, evidence, or Codex state
- bypass capability gating or trust invariants

Investigation finding (v0.92):
    The repository already has exactly what "watermark" describes:
        step  -> EvidenceKernel.step, an already-existing monotonic
                 count of verified events (observe/add_evidence),
                 already threaded through snapshot()/restore() and
                 through Chronicle replay (_apply_to_kernel).
        chain -> Chronicle.chain, an already-existing hash-chain
                 position, provable locally via Chronicle.verify().
    core.py's own snapshot() already pairs these two values
    (`step` + `chronicle_chain`) for exactly the reason this module
    needs them: "how far, and provably so." Continuity here is a
    read-only VIEW over that existing pairing, not a new mechanism.

Trust boundary:
    A remote watermark is received data, not evidence. Chronicle.
    verify() can prove OUR OWN chain locally; there is no shared
    ledger between two Lantern instances, so a peer's claimed chain
    hash cannot be cryptographically re-derived here. It is only
    ever compared against local state, never trusted as true on its
    own -- the same posture federation.py already takes toward
    remote confidence ("a remote peer may provide information but
    may not donate authority").
"""

from dataclasses import dataclass

from .compatibility import compatible_versions


# ============================================================
# Continuity states
# ============================================================
#
# Only states the existing architecture can actually justify:
#
# INCOMPATIBLE -- protocol major version differs. Authoritative;
#                 checked before any watermark comparison, exactly
#                 like compatibility.negotiate()'s own version gate.
# COMPATIBLE   -- same step AND same chain: both sides claim to be
#                 at the identical verified position.
# DIVERGED     -- same step but a different chain. Structurally
#                 meaningful without a shared ledger: two chains
#                 claiming equal length but unequal hash means their
#                 event histories differ, full stop.
# BEHIND       -- remote step is lower than local step.
# AHEAD        -- remote step is higher than local step.

COMPATIBLE = "COMPATIBLE"
BEHIND = "BEHIND"
AHEAD = "AHEAD"
DIVERGED = "DIVERGED"
INCOMPATIBLE = "INCOMPATIBLE"

CONTINUITY_STATES = frozenset({COMPATIBLE, BEHIND, AHEAD, DIVERGED, INCOMPATIBLE})


@dataclass(frozen=True)
class Watermark:
    step: int
    chain: str

    def to_dict(self):
        return {"step": self.step, "chain": self.chain}


@dataclass(frozen=True)
class ContinuityResult:
    status: str
    reason: str


# ============================================================
# Local watermark (read-only view over existing state)
# ============================================================

def local_watermark(lantern):
    """Read the local continuity watermark from an existing Lantern
    instance.

    Read-only: does not advance kernel.step, does not append to the
    Chronicle, does not touch evidence or belief. It only reads two
    values that already exist: EvidenceKernel.step and
    Chronicle.chain (or "GENESIS" if no chronicle is attached).
    """
    chain = "GENESIS"
    if lantern.bus.chronicle is not None:
        chain = lantern.bus.chronicle.chain

    return Watermark(step=lantern.kernel.step, chain=chain)


# ============================================================
# Remote watermark (claim, not evidence)
# ============================================================

def parse_remote_watermark(data):
    """Parse a remote peer's claimed watermark from wire data
    (e.g. a handshake payload).

    This performs no verification. It produces a Watermark value
    from whatever the peer reported -- nothing more. Any comparison
    against local state happens only in compare_watermarks(), and
    even that never treats the remote claim as proven fact.
    """
    return Watermark(
        step=int(data.get("step", 0)),
        chain=str(data.get("chain", "GENESIS")),
    )


# ============================================================
# Comparison
# ============================================================

def compare_watermarks(local_version, remote_version, local, remote):
    """Classify a remote watermark relative to local state.

    Protocol compatibility is checked first and is authoritative:
    an incompatible major version always returns INCOMPATIBLE,
    regardless of what the watermarks claim. Watermark comparison
    never overrides protocol compatibility, and it never grants
    capabilities or touches belief/evidence -- it only classifies
    relative position.
    """
    if not compatible_versions(local_version, remote_version):
        return ContinuityResult(
            INCOMPATIBLE,
            "Major protocol version mismatch",
        )

    if remote.step == local.step:
        if remote.chain == local.chain:
            return ContinuityResult(
                COMPATIBLE,
                "Same verified position",
            )
        return ContinuityResult(
            DIVERGED,
            "Same step, different chain position",
        )

    if remote.step < local.step:
        return ContinuityResult(
            BEHIND,
            "Remote has progressed less than local",
        )

    return ContinuityResult(
        AHEAD,
        "Remote has progressed further than local",
    )
