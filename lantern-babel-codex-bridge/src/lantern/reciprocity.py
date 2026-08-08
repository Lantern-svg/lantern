"""
Lantern Reciprocity v0.93

Purpose:
    Semantic model for reciprocal exchange between agents.

Design:
    Reciprocity is a Lantern concept — an exchange where one party provides
    a capability and the other provides something in return.

    Payment is ONE possible settlement mechanism. Others may include:
    - information exchange
    - capability exchange
    - service exchange

    This module models the semantic transaction, not the payment mechanism.
    External payment rails (x402, etc.) handle monetary settlement.

Rule:
    RECIPROCITY ≠ TRUST
    RECIPROCITY ≠ TRUTH
    PAYMENT ≠ AUTHORIZATION
    
    A successful reciprocal exchange does NOT automatically:
    - increase belief confidence
    - establish truth
    - establish trust
    - promote evidence
    - mutate evidence
    - alter source reliability
    - bypass capability authorization

    Payment means only: the agreed monetary settlement condition was satisfied.
"""

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional


@dataclass
class ReciprocityTerms:
    """Terms of a reciprocal exchange."""
    capability: str
    settlement_type: str  # "monetary", "information", "capability", etc.
    settlement_details: dict  # e.g., {"price": "0.001", "network": "eip155:84532"}


@dataclass
class ReciprocityOutcome:
    """Outcome of a reciprocal exchange."""
    initiator: str
    provider: str
    terms: ReciprocityTerms
    settlement_status: str  # "proposed", "settled", "rejected", "failed"
    execution_status: str  # "pending", "executed", "failed"
    result: Optional[dict]
    transaction_id: Optional[str]
    timestamp: str
    error: Optional[str] = None

    def to_dict(self):
        return {
            "initiator": self.initiator,
            "provider": self.provider,
            "capability": self.terms.capability,
            "settlement_type": self.terms.settlement_type,
            "settlement_details": self.terms.settlement_details,
            "settlement_status": self.settlement_status,
            "execution_status": self.execution_status,
            "result": self.result,
            "transaction_id": self.transaction_id,
            "timestamp": self.timestamp,
            "error": self.error,
        }


def create_outcome(
    initiator: str,
    provider: str,
    capability: str,
    settlement_type: str,
    settlement_details: dict,
    settlement_status: str,
    execution_status: str,
    result: Optional[dict] = None,
    transaction_id: Optional[str] = None,
    error: Optional[str] = None,
) -> ReciprocityOutcome:
    """Create a reciprocity outcome record."""
    terms = ReciprocityTerms(
        capability=capability,
        settlement_type=settlement_type,
        settlement_details=settlement_details,
    )
    
    return ReciprocityOutcome(
        initiator=initiator,
        provider=provider,
        terms=terms,
        settlement_status=settlement_status,
        execution_status=execution_status,
        result=result,
        transaction_id=transaction_id,
        timestamp=datetime.now(timezone.utc).isoformat(),
        error=error,
    )
