"""
Lantern Content Provenance v1

Purpose:
- Tag every piece of content entering a personal instance's memory with
  where it actually came from, using exactly the seven classes the
  personal-instance mission requires:
      FIRST_PARTY_OBSERVATION
      VERIFIED_ARTIFACT
      OWNER_ASSERTION
      AUTHORIZED_OVERRIDE
      IMPORTED_EXTERNAL_CONTENT
      PEER_CONTENT
      UNVERIFIED_CONTENT
- Enforce the PROVENANCE_TAG invariant as executable code, not just a
  docstring: external content cannot become first-party belief without
  independent artifact-backed verification, an authorized human
  override, or a valid ownership transfer. Relay never counts as
  independent corroboration.

Relationship to the existing provenance system (per the mission's
explicit instruction: "use the existing provenance system rather than
creating a second competing truth mechanism"):

    lantern.orchestration.ProvenanceTag / PROVENANCE_CLASSES
        answers: "where did this DELEGATION RESULT come from"
        (LOCAL_TOOL, REMOTE_AGENT, MCP_ENDPOINT, HUMAN, ...). It is
        scoped to the orchestration/delegation lifecycle
        (DelegationRecord.result_provenance) and is untouched by this
        module.

    lantern.content_provenance.ContentProvenanceTag (this module)
        answers a related but distinct question: "what evidence class
        does this piece of CONTENT SITTING IN MEMORY belong to, and is
        it eligible to become first-party belief." This is the axis
        the personal-instance mission asks for by name, and it did not
        exist anywhere in the codebase prior to this module (confirmed
        by the 2026-08-26 baseline audit: FIRST_PARTY, VERIFIED_ARTIFACT,
        AUTHORIZED_OVERRIDE, OWNERSHIP_TRANSFER were NOT FOUND under any
        name). Rather than overload orchestration.ProvenanceTag's
        existing ten-class enum (which is specifically about
        LOCAL_*/REMOTE_*/MCP_ENDPOINT/A2A_ENDPOINT source classification
        for delegation results, and is exercised by
        compression.py's _check_provenance_invariant and by
        mcp_integration.py), this module defines its OWN class set for
        this OWN axis. This mirrors the same discipline
        orchestration.py itself already uses (frozen dataclass,
        __post_init__ membership validation, a documented
        never-rewritten invariant) rather than inventing a different
        validation style -- it is the same PATTERN, applied to a new,
        previously-unmodeled axis, not a competing truth mechanism for
        the same axis.

This module attaches its tags to Observation.metadata (an existing,
already-persisted dict field on lantern.core.Observation -- see
core.py's Observation dataclass and EvidenceKernel.observe()). No
change to Observation's schema, EvidenceKernel's snapshot/restore
format, or the Chronicle event shapes was needed or made; this is
additive metadata within an existing extension point, per the
constraint to preserve existing schemas unless there is a demonstrated
reason to change them. There is no such reason here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional


class ContentProvenanceError(Exception):
    """Raised for content-provenance tagging / promotion failures."""


# ============================================================
# The seven classes
# ============================================================

FIRST_PARTY_OBSERVATION = "FIRST_PARTY_OBSERVATION"
VERIFIED_ARTIFACT = "VERIFIED_ARTIFACT"
OWNER_ASSERTION = "OWNER_ASSERTION"
AUTHORIZED_OVERRIDE = "AUTHORIZED_OVERRIDE"
IMPORTED_EXTERNAL_CONTENT = "IMPORTED_EXTERNAL_CONTENT"
PEER_CONTENT = "PEER_CONTENT"
UNVERIFIED_CONTENT = "UNVERIFIED_CONTENT"

CONTENT_PROVENANCE_CLASSES = (
    FIRST_PARTY_OBSERVATION,
    VERIFIED_ARTIFACT,
    OWNER_ASSERTION,
    AUTHORIZED_OVERRIDE,
    IMPORTED_EXTERNAL_CONTENT,
    PEER_CONTENT,
    UNVERIFIED_CONTENT,
)

#: Classes that already ARE first-party (or are the explicit,
#: authorized mechanisms for BECOMING first-party) by construction --
#: content tagged with one of these needs no further promotion step.
#: This mirrors orchestration.REMOTE_PROVENANCE_CLASSES's shape: a
#: frozenset computed once, checked via a property, never mutated.
ALREADY_FIRST_PARTY_CLASSES = frozenset({
    FIRST_PARTY_OBSERVATION,
    VERIFIED_ARTIFACT,
    OWNER_ASSERTION,
    AUTHORIZED_OVERRIDE,
})

#: Classes that are external by construction -- content in one of
#: these classes can NEVER be first-party belief merely by sitting in
#: memory; it requires an explicit promotion event (see
#: promote_to_first_party below) that itself produces a NEW tag in one
#: of the ALREADY_FIRST_PARTY_CLASSES, never a silent rewrite of the
#: original tag.
EXTERNAL_CLASSES = frozenset({
    IMPORTED_EXTERNAL_CONTENT,
    PEER_CONTENT,
    UNVERIFIED_CONTENT,
})


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class ContentProvenanceTag:
    """Where one piece of memory content actually came from.

    origin_id: for PEER_CONTENT/IMPORTED_EXTERNAL_CONTENT, the
    identifier of the actual originating source (a peer node_id, a URL,
    a document hash) -- required and non-empty for every EXTERNAL_CLASS
    tag, specifically so relay chains can be inspected (see
    detect_relay_amplification below): "A -> B -> C -> D" must record
    A's origin_id at every hop, not just "came from a Lantern peer."

    relay_path: the ordered list of intermediate identifiers content
    passed through before reaching this instance, oldest first. Empty
    for content this instance obtained directly from origin_id. This is
    what makes relay-amplification detectable: multiple tags that share
    the same terminal origin_id are the same witness, no matter how
    many relay hops or restatements sit between them.
    """

    source_class: str
    origin_id: str
    recorded_at: str = field(default_factory=_now)
    relay_path: tuple = field(default_factory=tuple)
    note: str = ""

    def __post_init__(self) -> None:
        if self.source_class not in CONTENT_PROVENANCE_CLASSES:
            raise ContentProvenanceError(f"unknown content provenance class: {self.source_class}")
        if self.source_class in EXTERNAL_CLASSES and not (self.origin_id and self.origin_id.strip()):
            raise ContentProvenanceError(
                f"{self.source_class} requires a non-empty origin_id identifying the actual source"
            )

    @property
    def is_first_party(self) -> bool:
        return self.source_class in ALREADY_FIRST_PARTY_CLASSES

    @property
    def is_external(self) -> bool:
        return self.source_class in EXTERNAL_CLASSES

    def to_dict(self) -> dict:
        return {
            "source_class": self.source_class,
            "origin_id": self.origin_id,
            "recorded_at": self.recorded_at,
            "relay_path": list(self.relay_path),
            "note": self.note,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ContentProvenanceTag":
        return cls(
            source_class=data["source_class"],
            origin_id=data.get("origin_id", ""),
            recorded_at=data.get("recorded_at", _now()),
            relay_path=tuple(data.get("relay_path", ())),
            note=data.get("note", ""),
        )


# ============================================================
# Attaching a tag to an Observation (metadata extension point)
# ============================================================

METADATA_KEY = "content_provenance"


def tag_metadata(tag: ContentProvenanceTag, existing_metadata: Optional[dict] = None) -> dict:
    """Return a NEW metadata dict with the provenance tag attached.

    Never mutates existing_metadata in place -- callers pass the result
    to Observation(metadata=...) / EvidenceKernel.observe(metadata=...).
    """
    merged = dict(existing_metadata or {})
    merged[METADATA_KEY] = tag.to_dict()
    return merged


def read_tag(metadata: Optional[dict]) -> Optional[ContentProvenanceTag]:
    """Read a previously attached tag back out of an Observation's
    metadata dict. Returns None if no tag was ever attached -- callers
    that require a tag to be present should treat None as
    UNVERIFIED_CONTENT-or-worse, never as an implicit FIRST_PARTY_OBSERVATION."""
    if not metadata:
        return None
    raw = metadata.get(METADATA_KEY)
    if raw is None:
        return None
    return ContentProvenanceTag.from_dict(raw)


# ============================================================
# The PROVENANCE_TAG invariant, enforced
# ============================================================

@dataclass(frozen=True)
class PromotionEvidence:
    """What was presented to justify promoting external content to
    first-party. Exactly one of the three fields may be set -- this is
    checked in promote_to_first_party(), not left to caller discipline."""

    artifact_verification: Optional[str] = None  # e.g. a Chronicle hash / verified digest reference
    human_override_authority: Optional[str] = None  # explicit authorizer identifier, never "self"
    ownership_transfer_record_signature: Optional[str] = None  # signature from an ownership.OwnershipRecord


def promote_to_first_party(tag: ContentProvenanceTag, evidence: PromotionEvidence) -> ContentProvenanceTag:
    """The ONLY function in this codebase that may turn external content
    into first-party content. It never rewrites the original tag object
    (ContentProvenanceTag is frozen) -- it returns a NEW tag, and the
    caller's storage layer must add a new Observation/Evidence entry
    for it (see core.py's design law: "Evidence is immutable once
    recorded; only new Evidence changes belief"). The original external
    tag remains in the history exactly as it was, so the evidence chain
    showing HOW a claim became verified is preserved, per mission
    section 5's requirement.

    Raises ContentProvenanceError unless:
      - tag is actually external (promoting already-first-party content
        is a no-op error, not silently allowed), AND
      - exactly one of PromotionEvidence's three fields is a real,
        non-empty value (never more than one -- combining two forms of
        evidence into a single call would blur which one actually
        justified the promotion in an audit).

    Note what this function does NOT do: it does not itself VERIFY that
    an artifact_verification reference is real, that a
    human_override_authority string names a real authorized human, or
    that an ownership_transfer_record_signature actually verifies
    against lantern.ownership.verify_ownership_record(). Those checks
    belong to the caller, which has access to the actual Chronicle /
    OwnershipRecord / human-authorization channel this module
    deliberately does not depend on (keeping this module free of a
    circular import on ownership.py/core.py). This function's job is
    narrower and non-negotiable: refuse to promote without SOME
    specific, single, named justification, and never let a caller
    accidentally promote by omission.
    """
    if not tag.is_external:
        raise ContentProvenanceError(
            f"{tag.source_class} is already first-party or an authorized-override class; "
            "there is nothing to promote"
        )

    provided = [
        value for value in (
            evidence.artifact_verification,
            evidence.human_override_authority,
            evidence.ownership_transfer_record_signature,
        )
        if value and value.strip()
    ]
    if len(provided) == 0:
        raise ContentProvenanceError(
            "promotion refused: no artifact verification, human override authority, or "
            "ownership transfer signature was presented"
        )
    if len(provided) > 1:
        raise ContentProvenanceError(
            "promotion refused: exactly one justification must be presented, not multiple -- "
            "an audit must be able to name the single authorizing mechanism"
        )

    if evidence.artifact_verification:
        new_class = VERIFIED_ARTIFACT
        note = f"promoted from {tag.source_class} via artifact verification: {evidence.artifact_verification}"
    elif evidence.human_override_authority:
        new_class = AUTHORIZED_OVERRIDE
        note = f"promoted from {tag.source_class} via human override by: {evidence.human_override_authority}"
    else:
        new_class = FIRST_PARTY_OBSERVATION
        note = f"promoted from {tag.source_class} via ownership transfer record"

    return ContentProvenanceTag(
        source_class=new_class,
        origin_id=tag.origin_id,
        relay_path=tag.relay_path,
        note=note,
    )


# ============================================================
# Relay-amplification detection
# ============================================================

def terminal_origin(tag: ContentProvenanceTag) -> str:
    """The actual original source, ignoring every relay hop. Two tags
    with the same terminal_origin are the SAME witness, no matter how
    many peers restated it in between."""
    return tag.relay_path[0] if tag.relay_path else tag.origin_id


def count_independent_witnesses(tags: list) -> int:
    """Count DISTINCT terminal origins among a list of ContentProvenanceTag.

    This is the direct enforcement of the mission's example:
        A -> B -> C -> D
    does not become four witnesses merely because four instances
    repeated the same claim. If tags = [D's copy of A's claim via B,
    D's copy of A's claim via C], both trace back to terminal_origin
    A -- this returns 1, not 2. A caller (e.g. an evaluation/evidence
    module) that was about to treat "N peers told me this" as N
    independent pieces of corroboration must call this first and use
    its result, not len(tags).
    """
    origins = {terminal_origin(tag) for tag in tags}
    return len(origins)


def is_independent_corroboration(existing_tags: list, new_tag: ContentProvenanceTag) -> bool:
    """Would new_tag add a genuinely NEW witness, or is it the same
    terminal origin as something already present? Relay never counts:
    a self-restatement of the same origin_id (with or without a longer
    relay_path) is not independent corroboration."""
    existing_origins = {terminal_origin(tag) for tag in existing_tags}
    return terminal_origin(new_tag) not in existing_origins
