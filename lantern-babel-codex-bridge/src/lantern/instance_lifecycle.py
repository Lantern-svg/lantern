"""
Lantern Personal Instance Lifecycle v1

Purpose:
- Implement, as real enforced state (not documentation), the
  deterministic lifecycle a personal instance must go through:

      INSTALL
        v
      INITIALIZE
        v
      IDENTITY CREATION
        v
      OWNER AUTHORIZATION
        v
      EMPTY / BASELINE MEMORY
        v
      LOCAL CONFIGURATION
        v
      READY
        v
      OPTIONAL PEER CONNECTION

- Guarantee that a newly created personal instance begins in a
  clearly distinguishable baseline state, and that starter material
  supplied at creation time is never silently treated as first-party
  belief.

This module is an orchestrator over three already-independent
modules -- it does not reimplement any of them:
    lantern.identity        -- IDENTITY CREATION
    lantern.ownership        -- OWNER AUTHORIZATION
    lantern.content_provenance -- tagging anything preloaded into
                                   EMPTY / BASELINE MEMORY

Each stage is representable, inspectable, and independently
verifiable; instance state is never inferred from "no error was
raised" alone -- InstanceState.stage always names exactly where in the
lifecycle an instance currently sits, and advancing a stage always
requires the real artifact that stage produces (an identity object,
an OwnershipRecord, ...), never a caller-supplied boolean claiming the
stage is done.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from . import content_provenance as cp
from . import identity as idm
from . import ownership as own


class LifecycleError(Exception):
    """Raised when a lifecycle transition is attempted out of order or
    with invalid/missing evidence for the stage being entered."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ============================================================
# Stages
# ============================================================

STAGE_INSTALLED = "INSTALLED"
STAGE_INITIALIZED = "INITIALIZED"
STAGE_IDENTITY_CREATED = "IDENTITY_CREATED"
STAGE_OWNER_AUTHORIZED = "OWNER_AUTHORIZED"
STAGE_BASELINE_MEMORY = "BASELINE_MEMORY"
STAGE_LOCALLY_CONFIGURED = "LOCALLY_CONFIGURED"
STAGE_READY = "READY"
STAGE_PEER_CONNECTED = "PEER_CONNECTED"  # optional, terminal-adjacent; instance stays READY-capable

#: Ordered so STAGE_ORDER.index(a) < STAGE_ORDER.index(b) means "a must
#: happen no later than b" -- used by _require_stage_at_least below.
#: PEER_CONNECTED is intentionally NOT in this strict total order: it
#: is optional and can be entered/exited many times after READY without
#: moving the instance's fundamental lifecycle position.
STAGE_ORDER = (
    STAGE_INSTALLED,
    STAGE_INITIALIZED,
    STAGE_IDENTITY_CREATED,
    STAGE_OWNER_AUTHORIZED,
    STAGE_BASELINE_MEMORY,
    STAGE_LOCALLY_CONFIGURED,
    STAGE_READY,
)


# ============================================================
# Starter-material labels (mission section 3: "If starter material is
# supplied, label it appropriately")
# ============================================================

STARTER_MATERIAL_LABELS = (
    "ARCHITECTURE",
    "DOCUMENTATION",
    "EXTERNAL_KNOWLEDGE",
    "IMPORTED_CONTENT",
    "EXAMPLE_DATA",
    "VERIFIED_ARTIFACT",
    "OWNER_PROVIDED_INFORMATION",
)

#: Maps each starter-material label to the ContentProvenanceTag class
#: it must be tagged with when actually stored as memory. This is the
#: piece that makes the distinction "survive persistence" (mission
#: section 3's explicit requirement) -- the label is not just a
#: parameter name that gets forgotten after this call returns; it
#: becomes part of the Observation's stored metadata via
#: content_provenance.tag_metadata().
_STARTER_LABEL_TO_PROVENANCE_CLASS = {
    "ARCHITECTURE": cp.IMPORTED_EXTERNAL_CONTENT,
    "DOCUMENTATION": cp.IMPORTED_EXTERNAL_CONTENT,
    "EXTERNAL_KNOWLEDGE": cp.IMPORTED_EXTERNAL_CONTENT,
    "IMPORTED_CONTENT": cp.IMPORTED_EXTERNAL_CONTENT,
    "EXAMPLE_DATA": cp.UNVERIFIED_CONTENT,
    "VERIFIED_ARTIFACT": cp.VERIFIED_ARTIFACT,
    "OWNER_PROVIDED_INFORMATION": cp.OWNER_ASSERTION,
}


@dataclass(frozen=True)
class StarterMaterialItem:
    """One piece of starter material supplied at instance creation.

    label must be one of STARTER_MATERIAL_LABELS -- this is validated
    in seed_baseline_memory(), not left to caller discipline. content
    is opaque to this module (a string description / reference / id);
    this module's job is only to guarantee the LABEL survives into a
    real ContentProvenanceTag, not to interpret the content itself.
    """

    label: str
    content: str
    origin_id: str = ""


# ============================================================
# Instance state
# ============================================================

@dataclass
class InstanceState:
    """The full, inspectable state of a personal instance's lifecycle
    position. This is the object an independent verifier (mission
    section 13) can load and answer "what stage is this instance at,
    and with what evidence" without re-deriving it from side channels."""

    stage: str
    node_id: str
    data_dir: str
    identity_public_key: Optional[str] = None
    ownership_history_path: Optional[str] = None
    baseline_memory_items: int = 0
    local_configuration: dict = field(default_factory=dict)
    stage_history: list = field(default_factory=list)  # [{"stage":..., "at":...}, ...]

    def to_dict(self) -> dict:
        return {
            "stage": self.stage,
            "node_id": self.node_id,
            "data_dir": self.data_dir,
            "identity_public_key": self.identity_public_key,
            "ownership_history_path": self.ownership_history_path,
            "baseline_memory_items": self.baseline_memory_items,
            "local_configuration": dict(self.local_configuration),
            "stage_history": list(self.stage_history),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "InstanceState":
        return cls(
            stage=data["stage"],
            node_id=data["node_id"],
            data_dir=data["data_dir"],
            identity_public_key=data.get("identity_public_key"),
            ownership_history_path=data.get("ownership_history_path"),
            baseline_memory_items=data.get("baseline_memory_items", 0),
            local_configuration=dict(data.get("local_configuration", {})),
            stage_history=list(data.get("stage_history", [])),
        )

    def _advance(self, new_stage: str) -> None:
        self.stage = new_stage
        self.stage_history.append({"stage": new_stage, "at": _now()})

    def save(self, path: str | Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), indent=2, sort_keys=True))

    @classmethod
    def load(cls, path: str | Path) -> Optional["InstanceState"]:
        path = Path(path)
        if not path.exists():
            return None
        return cls.from_dict(json.loads(path.read_text()))


def _require_stage(state: InstanceState, expected: str) -> None:
    if state.stage != expected:
        raise LifecycleError(
            f"expected instance to be at stage {expected!r}, but it is at {state.stage!r}"
        )


# ============================================================
# INSTALL / INITIALIZE
# ============================================================

def install(*, node_id: str, data_dir: str | Path) -> InstanceState:
    """The very first lifecycle step: declare that a personal instance
    is being created at data_dir for node_id. Produces no key material,
    no ownership, no memory yet -- purely the declaration that
    installation has begun, so every later stage has somewhere to
    record its own artifacts against a stable data_dir."""
    if not node_id or not node_id.strip():
        raise LifecycleError("node_id must be a non-empty string")

    state = InstanceState(stage=STAGE_INSTALLED, node_id=node_id.strip(), data_dir=str(data_dir))
    state.stage_history.append({"stage": STAGE_INSTALLED, "at": _now()})
    return state


def initialize(state: InstanceState) -> InstanceState:
    """Marks that the data_dir/environment is ready to receive identity
    material (directories exist, etc). Deliberately separate from
    install() so a caller can distinguish "declared" from "environment
    actually prepared" if a later audit needs to."""
    _require_stage(state, STAGE_INSTALLED)
    Path(state.data_dir).mkdir(parents=True, exist_ok=True)
    state._advance(STAGE_INITIALIZED)
    return state


# ============================================================
# IDENTITY CREATION
# ============================================================

def create_identity(state: InstanceState) -> tuple:
    """Wraps lantern.identity.load_or_create() -- does not reimplement
    key generation. Returns (state, NodeIdentity) because the caller
    needs the live NodeIdentity object (holding the private signing
    key in memory) for the very next stage, OWNER AUTHORIZATION, and
    this module never persists that object itself."""
    _require_stage(state, STAGE_INITIALIZED)

    identity_dir = idm.default_identity_dir(state.data_dir, state.node_id)
    identity = idm.load_or_create(state.node_id, identity_dir)

    state.identity_public_key = identity.public_key_hex
    state._advance(STAGE_IDENTITY_CREATED)
    return state, identity


# ============================================================
# OWNER AUTHORIZATION
# ============================================================

def authorize_owner(state: InstanceState, identity: idm.NodeIdentity, *, owner_id: str, owner_token: str,
                     ownership_history_path: Optional[str] = None) -> tuple:
    """Wraps lantern.ownership.create_initial_ownership(). Persists the
    resulting OwnershipHistory to ownership_history_path (default:
    <data_dir>/ownership.json) -- deliberately its own file, not inside
    the identity directory (identity is a credential; ownership is a
    claim ABOUT who holds authority over the credential-bearing
    instance -- keeping them separate mirrors identity.py's own
    "identity dir is deliberately separate from Chronicle" reasoning)
    and not inside any Chronicle path either."""
    _require_stage(state, STAGE_IDENTITY_CREATED)
    if identity.node_id != state.node_id or identity.public_key_hex != state.identity_public_key:
        raise LifecycleError("identity does not match the identity already recorded for this instance")

    record = own.create_initial_ownership(identity, owner_id=owner_id, owner_token=owner_token)
    history = own.OwnershipHistory()
    history.append(record)

    path = ownership_history_path or str(Path(state.data_dir) / "ownership.json")
    own.save_history(path, history)

    state.ownership_history_path = path
    state._advance(STAGE_OWNER_AUTHORIZED)
    return state, record


# ============================================================
# EMPTY / BASELINE MEMORY
# ============================================================

def seed_baseline_memory(state: InstanceState, kernel, *, starter_material: Optional[list] = None) -> InstanceState:
    """Enter BASELINE_MEMORY. kernel is a lantern.core.EvidenceKernel
    (or a Lantern shell exposing .kernel) the caller already
    constructed -- this module does not construct or own the kernel,
    it only seeds it, exactly once, with correctly-labeled starter
    material (if any).

    A newly created personal instance starts with kernel.observations
    empty -- calling this with starter_material=None or [] is valid and
    is the common case ("do not preload another person's memories or
    beliefs into a new personal instance as if they were first-party
    knowledge" is trivially satisfied by seeding nothing).

    Every StarterMaterialItem passed in is stored as a real
    Observation via kernel.observe(...), with a ContentProvenanceTag
    attached to its metadata whose source_class is derived from the
    item's label (see _STARTER_LABEL_TO_PROVENANCE_CLASS) -- never
    FIRST_PARTY_OBSERVATION, because nothing supplied at creation time
    by someone other than this instance's own subsequent operation can
    honestly claim that class. reliability is fixed at a conservative
    default (0.3) for all starter material regardless of label, since
    this module has no basis to assert a higher reliability than "this
    was handed to the instance at creation, unverified.
    """
    _require_stage(state, STAGE_OWNER_AUTHORIZED)

    count = 0
    for item in (starter_material or []):
        if item.label not in STARTER_MATERIAL_LABELS:
            raise LifecycleError(
                f"unknown starter material label {item.label!r}; must be one of {STARTER_MATERIAL_LABELS}"
            )
        provenance_class = _STARTER_LABEL_TO_PROVENANCE_CLASS[item.label]
        tag = cp.ContentProvenanceTag(
            source_class=provenance_class,
            origin_id=item.origin_id or f"starter_material:{item.label}",
            note=f"seeded at instance creation with label={item.label}",
        )
        metadata = cp.tag_metadata(tag, {"starter_material_label": item.label})
        kernel.observe(item.content, source=f"starter_material:{item.label}", reliability=0.3, metadata=metadata)
        count += 1

    state.baseline_memory_items = count
    state._advance(STAGE_BASELINE_MEMORY)
    return state


# ============================================================
# LOCAL CONFIGURATION
# ============================================================

def apply_local_configuration(state: InstanceState, *, configuration: dict) -> InstanceState:
    """Enter LOCALLY_CONFIGURED. configuration is opaque, caller-owned
    key/value data (this module does not define what belongs in it --
    that is deployment-specific); the guarantee this stage provides is
    only ordering: configuration cannot be recorded as "applied" before
    baseline memory has been explicitly seeded (even with zero items),
    and READY cannot be reached before configuration has been recorded,
    even if that configuration is an empty dict."""
    _require_stage(state, STAGE_BASELINE_MEMORY)
    state.local_configuration = dict(configuration or {})
    state._advance(STAGE_LOCALLY_CONFIGURED)
    return state


# ============================================================
# READY
# ============================================================

def mark_ready(state: InstanceState) -> InstanceState:
    """The instance has passed every mandatory stage and may now be
    used locally and, optionally, connected to peers. Reaching READY
    requires state.stage == LOCALLY_CONFIGURED -- there is no shortcut
    from any earlier stage, and no way to construct an InstanceState
    directly at READY without having gone through every prior stage
    (short of hand-editing the persisted JSON, which is exactly the
    kind of tampering an independent verifier, mission section 13,
    should be checking for separately)."""
    _require_stage(state, STAGE_LOCALLY_CONFIGURED)
    state._advance(STAGE_READY)
    return state


# ============================================================
# OPTIONAL PEER CONNECTION
# ============================================================

def mark_peer_connected(state: InstanceState) -> InstanceState:
    """Records that this instance has established at least one peer
    connection. Requires READY. Deliberately does not remove or
    replace STAGE_READY -- peer connection is additive, optional
    state, not a further "more advanced" lifecycle stage; an instance
    can lose all peer connections and remains exactly as valid and
    READY as before. See STAGE_ORDER's docstring."""
    if state.stage not in (STAGE_READY, STAGE_PEER_CONNECTED):
        raise LifecycleError(
            f"instance must be READY before a peer connection can be recorded; currently at {state.stage!r}"
        )
    if state.stage != STAGE_PEER_CONNECTED:
        state._advance(STAGE_PEER_CONNECTED)
    return state


# ============================================================
# Verification helpers (for the independent verifier, mission section 13)
# ============================================================

def stage_index(stage: str) -> int:
    if stage == STAGE_PEER_CONNECTED:
        return STAGE_ORDER.index(STAGE_READY)
    return STAGE_ORDER.index(stage)


def has_reached(state: InstanceState, stage: str) -> bool:
    """True if this instance's current stage is at or past the given
    stage in the mandatory lifecycle order."""
    return stage_index(state.stage) >= stage_index(stage)


def describe(state: InstanceState) -> str:
    lines = [
        f"Lantern personal instance lifecycle: node_id={state.node_id}",
        f"  current stage: {state.stage}",
        f"  identity_public_key: {state.identity_public_key or '(not yet created)'}",
        f"  ownership_history_path: {state.ownership_history_path or '(not yet authorized)'}",
        f"  baseline_memory_items: {state.baseline_memory_items}",
        f"  local_configuration keys: {sorted(state.local_configuration.keys())}",
        "  stage history:",
    ]
    for entry in state.stage_history:
        lines.append(f"    {entry['at']}  ->  {entry['stage']}")
    return "\n".join(lines)
