"""Strict Pydantic v2 Underwriting Decision and Risk Evaluation Schemas.

Returned under 180ms by the FastAPI underwriting gateway.
Contains full audit trails required by UAE FTA, SAMA, and enterprise controllers.
"""

from datetime import datetime, timezone
from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, Field


class UnderwritingVerdict(str, Enum):
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    FLAGGED_MANUAL_REVIEW = "FLAGGED_MANUAL_REVIEW"


class ComplianceResult(BaseModel):
    jurisdiction: str = Field(..., description="Regulatory jurisdiction (UAE / KSA)")
    regulatory_authority: str = Field(..., description="FTA / SAMA / ZATCA")
    supplier_trn_valid: bool = Field(..., description="TRN passed statutory length and checksum rules")
    customer_trn_valid: bool = Field(..., description="Client TRN passed format verification")
    statutory_vat_rate: float = Field(..., description="Expected statutory VAT rate (0.05 or 0.15)")
    vat_reconciled: bool = Field(..., description="True if declared VAT matches calculated line item VAT within tolerance")
    calculated_vat_aed: float = Field(..., description="Math engine computed VAT amount")
    declared_vat_aed: float = Field(..., description="Invoice declared total VAT")
    vat_discrepancy_aed: float = Field(..., description="Absolute variance between declared and calculated VAT")
    vat_reclaimable: bool = Field(..., description="Eligible for corporate VAT input tax credit")
    compliance_flags: List[str] = Field(default_factory=list, description="Regulatory warning codes or audit notes")


class BudgetEvaluationResult(BaseModel):
    policy_limit_aed: float = Field(..., description="Authorized single or daily policy limit in AED")
    transaction_amount_aed: float = Field(..., description="Total transaction amount inclusive of VAT")
    utilization_pct: float = Field(..., description="Percentage of policy limit consumed (amount / limit * 100)")
    within_budget: bool = Field(..., description="True if amount does not exceed policy limit")
    cost_center_authorized: bool = Field(..., description="Cost center matches authorized department ledger")
    expense_classification: str = Field("OpEx", description="Classified as OpEx (operating) or CapEx (capital)")
    budget_flags: List[str] = Field(default_factory=list, description="Budget warnings or exceptions")


class AnomalyResult(BaseModel):
    is_duplicate: bool = Field(..., description="Identical transaction hash seen in active deduplication window")
    transaction_fingerprint: str = Field(..., description="SHA-256 hash of TRN + Invoice + Amount")
    velocity_spike_flag: bool = Field(False, description="Unusual card swipe velocity detected within 5 minutes")
    structuring_detected: bool = Field(False, description="Pattern of repeated sub-threshold amounts (smurfing/structuring)")
    anomaly_score: float = Field(..., ge=0.0, le=100.0, description="0 = Clean, 100 = Severe Fraud Risk")
    anomaly_flags: List[str] = Field(default_factory=list, description="Specific fraud signals identified")


class UnderwritingDecision(BaseModel):
    """The root decision payload returned to the caller within 180ms SLA."""
    decision_id: str = Field(..., description="Unique UUID for this underwriting evaluation")
    invoice_number: str = Field(..., description="Vendor invoice number evaluated")
    verdict: UnderwritingVerdict = Field(..., description="Final underwriting status")
    risk_score: float = Field(..., ge=0.0, le=100.0, description="Composite risk index (0=Safe, 100=Critical Risk)")
    summary_reason: str = Field(..., description="Executive plain-text summary of the decision rationale")
    compliance: ComplianceResult = Field(..., description="Tax and regulatory checks breakdown")
    budget: BudgetEvaluationResult = Field(..., description="Corporate spend and policy compliance breakdown")
    anomaly: AnomalyResult = Field(..., description="Fraud, deduplication, and velocity breakdown")
    audit_trail: List[str] = Field(default_factory=list, description="Chronological log of rule evaluations")
    latency_ms: float = Field(..., description="End-to-end execution time in milliseconds")
    evaluated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="UTC timestamp")
