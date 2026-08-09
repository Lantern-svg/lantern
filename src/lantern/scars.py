"""
Lantern Scar Status v0.94

Purpose:
    Answer, honestly and without fabrication, whether "recording a
    Scar" is a real, durable, independently-retrievable operation in
    this codebase today.

Background:
    A prior conversational exchange described a finding ("SCAR-001",
    the observation that a remote peer's self-declared reliability
    could reach Evidence.weight unmediated -- see bridge.py's fix in
    this same revision) as if it had been "recorded". Grepping the
    entire source tree and memory files at the time found no matching
    write. That was a Principle 1 violation: a conversational claim
    was not, and must never be treated as, proof of a state
    transition.

This module does not invent a Scar persistence mechanism. It exists
only to make the current (lack of) capability explicit and
machine-checkable, so future code/conversation cannot silently repeat
that mistake by calling something "recorded" when nothing was
written.

If a real Scar persistence mechanism (e.g. a dedicated Chronicle,
following the exact append/replay/verify shape core.Chronicle already
provides) is built in a future revision, this module's status must be
updated to reflect it -- not before.
"""

from dataclasses import dataclass


NOT_IMPLEMENTED = "NOT_IMPLEMENTED"


@dataclass(frozen=True)
class ScarPersistenceStatus:
    status: str
    reason: str

    def to_dict(self):
        return {"status": self.status, "reason": self.reason}


def scar_persistence_status() -> ScarPersistenceStatus:
    """Report the true current state of Scar persistence.

    There is no Scar-specific Chronicle, table, file, or any other
    durable store anywhere in this package (verified by grep across
    src/lantern/*.py for "Scar"/"SCAR" prior to writing this module --
    the only other hits are this module and its test/doc references).
    Describing a Scar in a chat response, or constructing a
    Scar-shaped Python object in memory, is category (A) or (C) in the
    Principle 1 vocabulary (conversational claim / generated structured
    data) -- neither is (D) persisted state.
    """
    return ScarPersistenceStatus(
        status=NOT_IMPLEMENTED,
        reason=(
            "No Scar-specific durable store exists in this codebase. "
            "A Scar description is, at most, generated structured data "
            "in memory or in a response; it is not persisted state "
            "until a real write operation (e.g. a dedicated Chronicle) "
            "exists and is actually invoked."
        ),
    )


def describe_scar_claim(scar_id: str, summary: str) -> dict:
    """Build a Scar-shaped record WITHOUT claiming it was persisted.

    This is deliberately the only Scar-related helper that returns
    structured data, and it is explicitly labeled as unpersisted
    (category C, not D) every time it is used -- callers must not
    strip or override "persisted": False.
    """
    return {
        "scar_id": scar_id,
        "summary": summary,
        "persisted": False,
        "persistence_status": scar_persistence_status().to_dict(),
    }
