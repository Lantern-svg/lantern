"""
Lantern Belief Reconciliation Service v0.93

Purpose:
    HTTP API exposing existing Lantern belief reconciliation capability
    with x402 payment integration.

Architecture:
    POST /v1/reconcile
        - Wraps existing codex_compare + codex_explanation
        - Protected by x402 payment middleware
        - Records reciprocity outcome via Chronicle
        - Does NOT duplicate reconciliation logic

Payment Flow:
    1. Client requests reconciliation
    2. Service returns 402 Payment Required (x402 middleware)
    3. Client submits payment
    4. x402 facilitator verifies and settles
    5. Middleware authorizes capability execution
    6. Service performs reconciliation
    7. Result returned
    8. Reciprocity outcome recorded

Configuration:
    LANTERN_PAYMENT_RECIPIENT_EVM: operator wallet address
    LANTERN_RECONCILIATION_PRICE: price in USD (e.g., "0.001")
    LANTERN_FACILITATOR_URL: x402 facilitator (default: testnet)
"""

import os
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from x402 import x402ResourceServer
from x402.http import HTTPFacilitatorClient
from x402.http.middleware.fastapi import payment_middleware
from x402.mechanisms.evm.exact.server import ExactEvmScheme

from lantern.core import Lantern, Chronicle, KernelEvent
from lantern.agent import LanternAgent
from lantern.codex_compare import compare_beliefs
from lantern.codex_explanation import explain_comparisons
from lantern.reciprocity import create_outcome


# Configuration from environment
PAYMENT_RECIPIENT_EVM = os.getenv("LANTERN_PAYMENT_RECIPIENT_EVM", "")
RECONCILIATION_PRICE = os.getenv("LANTERN_RECONCILIATION_PRICE", "$0.001")
FACILITATOR_URL = os.getenv("LANTERN_FACILITATOR_URL", "https://x402.org/facilitator")
TESTNET_NETWORK = "eip155:84532"  # Base Sepolia


# Request/Response Models
class ObservationInput(BaseModel):
    content: str
    source: str
    reliability: float = Field(default=1.0, ge=0.0, le=1.0)


class BeliefStateInput(BaseModel):
    observations: list[ObservationInput]


class ReconciliationRequest(BaseModel):
    lantern_a: BeliefStateInput
    lantern_b: BeliefStateInput
    concepts: Optional[list[str]] = None


class ReconciliationResponse(BaseModel):
    comparisons: list[dict]
    summary: dict
    explanations: list[dict]
    reciprocity_outcome: dict


# Service Lifecycle
chronicle = None
lantern_a_instance = None
lantern_b_instance = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize shared Chronicle for reciprocity outcomes."""
    global chronicle
    chronicle = Chronicle("reciprocity_chronicle.jsonl")
    yield
    # Cleanup if needed


# FastAPI App
app = FastAPI(
    title="Lantern Belief Reconciliation Service",
    version="0.93",
    lifespan=lifespan,
)


# x402 Payment Setup
if not PAYMENT_RECIPIENT_EVM:
    raise ValueError("LANTERN_PAYMENT_RECIPIENT_EVM must be set")

facilitator = HTTPFacilitatorClient({"url": FACILITATOR_URL})
payment_server = x402ResourceServer(facilitator)
payment_server.register(TESTNET_NETWORK, ExactEvmScheme())


routes_config = {
    "POST /v1/reconcile": {
        "accepts": [
            {
                "scheme": "exact",
                "price": RECONCILIATION_PRICE,
                "network": TESTNET_NETWORK,
                "payTo": PAYMENT_RECIPIENT_EVM,
            }
        ],
        "description": "Lantern belief reconciliation with evidence-aware comparison",
        "mimeType": "application/json",
    }
}


@app.middleware("http")
async def x402_payment_middleware(request: Request, call_next):
    """x402 payment middleware for protected routes."""
    return await payment_middleware(routes_config, payment_server)(request, call_next)


# Helper: Build Lantern instance from belief state
def build_lantern_from_state(state: BeliefStateInput) -> Lantern:
    """Build a Lantern instance from observation inputs."""
    lantern = Lantern()
    agent = LanternAgent(lantern)
    
    for obs in state.observations:
        agent.observe(
            content=obs.content,
            source=obs.source,
            reliability=obs.reliability,
        )
    
    return lantern


@app.post("/v1/reconcile", response_model=ReconciliationResponse)
async def reconcile_beliefs(request: Request, body: ReconciliationRequest):
    """
    Compare belief states from two Lantern instances and explain differences.
    
    This endpoint is protected by x402 payment. The payment middleware ensures:
    - Payment is verified before execution
    - Settlement occurs after successful reconciliation
    - Invalid/missing payment results in 402 response
    
    The reconciliation uses existing Lantern modules:
    - codex_compare: evidence-aware belief comparison
    - codex_explanation: natural-language explanation generation
    
    Payment does NOT:
    - Mutate beliefs or evidence
    - Bypass capability authorization
    - Establish trust or truth
    - Increase confidence
    """
    # Payment already verified by middleware at this point
    # Extract payment info from request state (set by middleware)
    payment_payload = getattr(request.state, "payment_payload", None)
    payment_requirements = getattr(request.state, "payment_requirements", None)
    
    transaction_id = None
    if payment_payload and payment_requirements:
        transaction_id = payment_payload.payload.get("transaction")
    
    initiator = request.client.host if request.client else "unknown"
    provider = "lantern-service"
    
    try:
        # Build independent Lantern instances
        lantern_a = build_lantern_from_state(body.lantern_a)
        lantern_b = build_lantern_from_state(body.lantern_b)
        
        # Perform comparison using existing codex_compare
        comparison_result = compare_beliefs(
            lantern_a,
            lantern_b,
            concepts=body.concepts,
        )
        
        # Generate explanations using existing codex_explanation
        explanation_objs = explain_comparisons(comparison_result, lantern_a, lantern_b)
        explanations = [
            {
                "concept": e.concept,
                "category": e.category,
                "belief_a": e.belief_a,
                "belief_b": e.belief_b,
                "cause": e.cause,
                "supporting_factors": e.supporting_factors,
                "missing_information": e.missing_information,
            }
            for e in explanation_objs
        ]
        
        # Build response
        comparisons = [
            {
                "concept": c.concept,
                "belief_a": c.belief_a,
                "belief_b": c.belief_b,
                "category": c.category,
                "detail": c.detail,
            }
            for c in comparison_result.comparisons
        ]
        
        summary = {
            cat: len(comparison_result.by_category(cat))
            for cat in ["agreement", "contradiction", "missing_evidence", "confidence_gap"]
        }
        
        result = {
            "comparisons": comparisons,
            "summary": summary,
        }
        
        # Record reciprocity outcome in Chronicle
        outcome = create_outcome(
            initiator=initiator,
            provider=provider,
            capability="belief_reconciliation",
            settlement_type="monetary",
            settlement_details={
                "price": RECONCILIATION_PRICE,
                "network": TESTNET_NETWORK,
                "recipient": PAYMENT_RECIPIENT_EVM,
            },
            settlement_status="settled",
            execution_status="executed",
            result=result,
            transaction_id=transaction_id,
        )
        
        if chronicle:
            event = KernelEvent(
                event_type="RECIPROCITY_COMPLETED",
                source="service",
                payload=outcome.to_dict(),
            )
            chronicle.append(event)
        
        return ReconciliationResponse(
            comparisons=comparisons,
            summary=summary,
            explanations=explanations,
            reciprocity_outcome=outcome.to_dict(),
        )
    
    except Exception as e:
        # Record failed execution
        outcome = create_outcome(
            initiator=initiator,
            provider=provider,
            capability="belief_reconciliation",
            settlement_type="monetary",
            settlement_details={
                "price": RECONCILIATION_PRICE,
                "network": TESTNET_NETWORK,
                "recipient": PAYMENT_RECIPIENT_EVM,
            },
            settlement_status="settled",
            execution_status="failed",
            transaction_id=transaction_id,
            error=str(e),
        )
        
        if chronicle:
            event = KernelEvent(
                event_type="RECIPROCITY_FAILED",
                source="service",
                payload=outcome.to_dict(),
            )
            chronicle.append(event)
        
        raise HTTPException(status_code=500, detail=f"Reconciliation failed: {str(e)}")


@app.get("/health")
async def health():
    """Health check endpoint (no payment required)."""
    return {"status": "ok", "service": "lantern-belief-reconciliation", "version": "0.93"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
