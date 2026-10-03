"""LangGraph State Definition for the Autonomous Underwriting Engine.

The state acts as an immutable or append-only ledger that transitions through:
1. Ingestion & Sanitization
2. Deterministic Rule Assessment (Compliance, Budget, Anomaly)
3. Routing Gate (Fast-Path vs Cognitive Path)
4. Cognitive Adjudication (if ambiguous)
5. Decision Synthesis & Strict Pydantic Serialization
"""

from typing import Any, Dict, List, Optional
from typing_extensions import TypedDict
from app.schemas.input_payload import CorporateTransactionPayload
from app.schemas.decision_output import (
    UnderwritingDecision,
    ComplianceResult,
    BudgetEvaluationResult,
    AnomalyResult,
    UnderwritingVerdict,
)


class UnderwritingState(TypedDict, total=False):
    """The central state dictionary passed across all LangGraph nodes."""
    # Raw & Validated Payloads
    raw_payload: Dict[str, Any]
    payload: Optional[CorporateTransactionPayload]

    # Evaluation Outputs from Deterministic Nodes
    compliance: Optional[ComplianceResult]
    budget: Optional[BudgetEvaluationResult]
    anomaly: Optional[AnomalyResult]

    # Composite Scoring & Flags
    risk_score: float
    requires_cognitive_review: bool
    cognitive_notes: Optional[str]

    # Final Decision Attributes
    verdict: Optional[UnderwritingVerdict]
    summary_reason: str
    audit_trail: List[str]

    # Performance & Final Contract
    start_time: float
    latency_ms: float
    final_decision: Optional[UnderwritingDecision]
