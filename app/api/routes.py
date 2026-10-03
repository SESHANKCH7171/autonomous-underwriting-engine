"""FastAPI Routes for Financial Risk & Underwriting Gateway.

Exposes:
- GET  /health: System health and component status.
- POST /v1/underwrite/transaction: Real-time synchronous card/invoice underwriting (<180ms SLA).
- POST /v1/underwrite/batch: Asynchronous batch underwriting.
"""

import asyncio
from typing import Any, Dict, List
from fastapi import APIRouter, HTTPException, status
from app.schemas.input_payload import CorporateTransactionPayload
from app.schemas.decision_output import UnderwritingDecision
from app.graph.workflow import evaluate_transaction

router = APIRouter()


@router.get("/health", tags=["System"])
async def health_check():
    """Health check endpoint for Kubernetes liveness/readiness probes."""
    return {
        "status": "healthy",
        "service": "autonomous-underwriting-engine",
        "sla_target_ms": 180.0,
        "engine": "LangGraph + Groq Llama-3.1-8b",
        "jurisdictions": ["UAE (FTA)", "KSA (SAMA / ZATCA)"]
    }


@router.post(
    "/v1/underwrite/transaction",
    response_model=UnderwritingDecision,
    status_code=status.HTTP_200_OK,
    tags=["Underwriting"]
)
async def underwrite_single_transaction(payload: CorporateTransactionPayload) -> UnderwritingDecision:
    """Evaluates a single corporate invoice or card transaction event under 180ms.
    
    Runs through:
    1. FTA / SAMA statutory compliance check (TRN & VAT)
    2. Corporate policy budget limit check
    3. Anomaly / Duplicate transaction detector
    4. LangGraph fast-path short circuit (or cognitive adjudication)
    """
    try:
        raw_dict = payload.model_dump()
        decision = await evaluate_transaction(raw_dict)
        return decision
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Underwriting evaluation error: {str(e)}"
        )


@router.post(
    "/v1/underwrite/batch",
    response_model=List[UnderwritingDecision],
    status_code=status.HTTP_200_OK,
    tags=["Underwriting"]
)
async def underwrite_batch_transactions(payloads: List[CorporateTransactionPayload]) -> List[UnderwritingDecision]:
    """Evaluates multiple transactions concurrently using asyncio.gather."""
    if len(payloads) > 100:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Maximum batch size is 100 transactions per request."
        )

    tasks = [evaluate_transaction(p.model_dump()) for p in payloads]
    results = await asyncio.gather(*tasks, return_exceptions=False)
    return results
