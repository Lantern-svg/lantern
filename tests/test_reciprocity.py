"""
Tests for lantern.reciprocity v0.93

Verifies:
- Reciprocity semantic model
- Payment/trust separation
- Outcome recording
"""

from lantern.reciprocity import create_outcome, ReciprocityTerms


def test_create_outcome():
    """Test reciprocity outcome creation."""
    outcome = create_outcome(
        initiator="agent-a",
        provider="lantern-service",
        capability="belief_reconciliation",
        settlement_type="monetary",
        settlement_details={"price": "0.001", "network": "eip155:84532"},
        settlement_status="settled",
        execution_status="executed",
        transaction_id="tx-123",
    )
    
    assert outcome.initiator == "agent-a"
    assert outcome.provider == "lantern-service"
    assert outcome.terms.capability == "belief_reconciliation"
    assert outcome.terms.settlement_type == "monetary"
    assert outcome.settlement_status == "settled"
    assert outcome.execution_status == "executed"
    assert outcome.transaction_id == "tx-123"
    assert outcome.timestamp is not None


def test_outcome_to_dict():
    """Test outcome serialization."""
    outcome = create_outcome(
        initiator="agent-a",
        provider="lantern-service",
        capability="test",
        settlement_type="monetary",
        settlement_details={"price": "1.00"},
        settlement_status="settled",
        execution_status="executed",
    )
    
    data = outcome.to_dict()
    
    assert data["initiator"] == "agent-a"
    assert data["capability"] == "test"
    assert data["settlement_type"] == "monetary"
    assert data["settlement_details"]["price"] == "1.00"


def test_payment_does_not_imply_trust():
    """
    Verify payment settlement does NOT automatically establish trust.
    
    A completed payment means the settlement condition was satisfied.
    It does NOT mean:
    - the provider is trustworthy
    - the result is true
    - the evidence is reliable
    """
    outcome = create_outcome(
        initiator="agent-a",
        provider="untrusted-service",
        capability="belief_reconciliation",
        settlement_type="monetary",
        settlement_details={"price": "0.001"},
        settlement_status="settled",
        execution_status="executed",
        result={"claim": "deliberately_false"},
    )
    
    # Payment settled
    assert outcome.settlement_status == "settled"
    
    # Execution completed
    assert outcome.execution_status == "executed"
    
    # Result can be false even when payment succeeded
    assert outcome.result["claim"] == "deliberately_false"
    
    # Payment ≠ truth
    # Payment ≠ trust
    # These are SEPARATE concerns


def test_failed_execution_after_payment():
    """
    Verify execution can fail even after payment succeeds.
    
    Settlement status: "settled"
    Execution status: "failed"
    
    These are independent.
    """
    outcome = create_outcome(
        initiator="agent-a",
        provider="lantern-service",
        capability="belief_reconciliation",
        settlement_type="monetary",
        settlement_details={"price": "0.001"},
        settlement_status="settled",
        execution_status="failed",
        error="Internal reconciliation error",
    )
    
    # Payment succeeded
    assert outcome.settlement_status == "settled"
    
    # But execution failed
    assert outcome.execution_status == "failed"
    assert outcome.error == "Internal reconciliation error"
    
    # Payment does not guarantee successful execution


def test_reciprocity_outcome_immutability():
    """Verify reciprocity outcomes do not mutate Lantern state."""
    outcome = create_outcome(
        initiator="agent-a",
        provider="lantern-service",
        capability="belief_reconciliation",
        settlement_type="monetary",
        settlement_details={"price": "0.001"},
        settlement_status="settled",
        execution_status="executed",
    )
    
    # Outcome is a record
    # It does NOT contain:
    assert "belief_mutation" not in outcome.to_dict()
    assert "evidence_mutation" not in outcome.to_dict()
    assert "trust_established" not in outcome.to_dict()
    assert "confidence_increase" not in outcome.to_dict()
    
    # Payment outcomes are provenance, not epistemic updates
