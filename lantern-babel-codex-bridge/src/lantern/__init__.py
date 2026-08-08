"""
lantern

Public package surface for the Lantern Babel Codex Bridge.

Re-exports the stable, frozen classes/functions from the core,
agent, and protocol modules so callers can do:

    from lantern import Lantern, LanternAgent, create_observation_share

instead of reaching into submodules directly. Submodules remain
importable individually (lantern.core, lantern.agent, lantern.protocol)
for callers who want to be explicit about which layer they depend on.
"""

from .core import (
    Chronicle,
    Contradiction,
    Evidence,
    EvidenceKernel,
    EventBus,
    KernelEvent,
    Lantern,
    Observation,
    ResolutionEvent,
)
from .agent import LanternAgent
from .compatibility import (
    CompatibilityResult,
    can_exchange,
    negotiate,
)
from .continuity import (
    AHEAD,
    BEHIND,
    COMPATIBLE,
    CONTINUITY_STATES,
    ContinuityResult,
    DIVERGED,
    INCOMPATIBLE,
    Watermark,
    compare_watermarks,
    local_watermark,
    parse_remote_watermark,
)
from .handshake import (
    HandshakeRequest,
    HandshakeResponse,
    create_handshake,
    evaluate_handshake,
    handshake_summary,
)
from .heartbeat import (
    ConnectionState,
    Heartbeat,
    UNREACHABLE,
    create_heartbeat,
    evaluate_connection,
)
from .participants import (
    COMPATIBILITY_STATES,
    COMPATIBLE as PARTICIPANT_COMPATIBLE,
    INCOMPATIBLE as PARTICIPANT_INCOMPATIBLE,
    REQUIRES_NEGOTIATION,
    UNKNOWN as PARTICIPANT_UNKNOWN,
    ParticipantView,
    find as find_participant,
    inspect as inspect_participant,
    inspect_all as inspect_all_participants,
    next_verification_step,
)
from .protocol import (
    PROTOCOL_VERSION,
    ProtocolMessage,
    create_codex_update,
    create_evidence_request,
    create_message,
    create_observation_share,
    validate_message,
)
from .rendezvous import (
    AWAITING_HANDSHAKE,
    EXPIRED,
    JoinMonitor,
    JoinRequest,
)
from .router import LanternRouter, RouteResult
from .boundary import LanternBoundary
from .architecture import (
    ArchitectureRegistry,
    REGISTRY,
    architecture_status,
)
from .bridge import LanternAgentBridge, BridgeResult
from .codex_compare import ConceptComparison, ComparisonResult, compare_beliefs, comparison_summary
from .codex_explanation import Explanation, explain_comparison, explain_comparisons
from .evaluation import EvaluationResult, EvidenceCandidate, EvidenceEvaluationGate
from .federation import (
    FederationAdapter,
    FederationMetadata,
    FederationResult,
    RemoteObservation,
)

__all__ = [
    "AHEAD",
    "ArchitectureRegistry",
    "REGISTRY",
    "architecture_status",
    "AWAITING_HANDSHAKE",
    "BEHIND",
    "BridgeResult",
    "COMPATIBILITY_STATES",
    "COMPATIBLE",
    "CONTINUITY_STATES",
    "Chronicle",
    "CompatibilityResult",
    "ComparisonResult",
    "ConceptComparison",
    "ConnectionState",
    "Contradiction",
    "ContinuityResult",
    "DIVERGED",
    "EXPIRED",
    "EvaluationResult",
    "Evidence",
    "EvidenceCandidate",
    "EvidenceEvaluationGate",
    "EvidenceKernel",
    "EventBus",
    "Explanation",
    "FederationAdapter",
    "FederationMetadata",
    "FederationResult",
    "HandshakeRequest",
    "HandshakeResponse",
    "Heartbeat",
    "INCOMPATIBLE",
    "JoinMonitor",
    "JoinRequest",
    "KernelEvent",
    "Lantern",
    "LanternAgent",
    "LanternAgentBridge",
    "LanternBoundary",
    "LanternRouter",
    "Observation",
    "PARTICIPANT_COMPATIBLE",
    "PARTICIPANT_INCOMPATIBLE",
    "PARTICIPANT_UNKNOWN",
    "ParticipantView",
    "PROTOCOL_VERSION",
    "ProtocolMessage",
    "REQUIRES_NEGOTIATION",
    "RemoteObservation",
    "ResolutionEvent",
    "RouteResult",
    "UNREACHABLE",
    "Watermark",
    "can_exchange",
    "compare_beliefs",
    "compare_watermarks",
    "comparison_summary",
    "create_codex_update",
    "create_evidence_request",
    "create_handshake",
    "create_heartbeat",
    "create_message",
    "create_observation_share",
    "create_outcome",
    "evaluate_connection",
    "evaluate_handshake",
    "explain_comparison",
    "explain_comparisons",
    "find_participant",
    "handshake_summary",
    "inspect_all_participants",
    "inspect_participant",
    "local_watermark",
    "negotiate",
    "next_verification_step",
    "parse_remote_watermark",
    "validate_message",
]

__version__ = "0.82"
