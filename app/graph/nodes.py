"""LangGraph Nodes for the Autonomous Underwriting Engine.

Nodes:
1. node_ingest_and_parse: Validates raw payload into strict Pydantic model.
2. node_deterministic_rules: Executes FTA/SAMA compliance, budget limits, and deduplication.
3. node_cognitive_adjudication: Calls ultra-low latency Groq SLM for ambiguous/high-value transactions.
4. node_synthesize_decision: Creates final UnderwritingDecision contract with latency and audit logs.
"""

import time
import uuid
from typing import Any, Dict
from app.graph.state import UnderwritingState
from app.schemas.input_payload import CorporateTransactionPayload
from app.schemas.decision_output import (
    UnderwritingDecision,
    UnderwritingVerdict,
    ComplianceResult,
    BudgetEvaluationResult,
    AnomalyResult,
)
from app.rules.fta_sama_compliance import evaluate_tax_compliance
from app.rules.policy_budget import evaluate_policy_and_budget
from app.rules.anomaly_detector import evaluate_anomalies
from app.core.llm_gateway import llm_gateway
from app.core.jev_gateway import jev_gateway


def node_ingest_and_parse(state: UnderwritingState) -> Dict[str, Any]:
    """Validates raw JSON dictionary into CorporateTransactionPayload."""
    start_time = time.perf_counter()
    raw = state.get("raw_payload", {})
    
    try:
        payload = CorporateTransactionPayload.model_validate(raw)
        return {
            "payload": payload,
            "start_time": start_time,
            "audit_trail": [
                f"INGESTION: Ingested invoice {payload.document_metadata.invoice_number} "
                f"from {payload.supplier_details.legal_entity_name}"
            ]
        }
    except Exception as e:
        # Schema validation error
        return {
            "payload": None,
            "start_time": start_time,
            "verdict": UnderwritingVerdict.REJECTED,
            "summary_reason": f"Payload validation failed: {str(e)}",
            "audit_trail": [f"INGESTION_ERROR: Invalid payload schema: {str(e)}"]
        }


def node_deterministic_rules(state: UnderwritingState) -> Dict[str, Any]:
    """Executes all deterministic rules: TRN checksum, VAT match, Budget cap, Deduplication."""
    payload: CorporateTransactionPayload = state.get("payload")
    if not payload:
        return {}

    trail = list(state.get("audit_trail", []))

    # 1. Tax & Regulatory Compliance
    compliance: ComplianceResult = evaluate_tax_compliance(payload)
    if compliance.compliance_flags:
        trail.append(f"COMPLIANCE_FLAGS: {'; '.join(compliance.compliance_flags)}")
    else:
        trail.append(
            f"COMPLIANCE_PASS: Valid {compliance.jurisdiction} TRN ({payload.supplier_details.trn}) "
            f"and reconciled VAT {compliance.calculated_vat_aed} AED"
        )

    # 2. Corporate Budget & Spend Policy
    budget: BudgetEvaluationResult = evaluate_policy_and_budget(payload)
    if budget.budget_flags:
        trail.append(f"BUDGET_FLAGS: {'; '.join(budget.budget_flags)}")
    else:
        trail.append(
            f"BUDGET_PASS: Approved {budget.transaction_amount_aed} AED within limit "
            f"{budget.policy_limit_aed} AED ({budget.utilization_pct}% used)"
        )

    # 3. Anomaly & Duplicate Detection
    anomaly: AnomalyResult = evaluate_anomalies(payload)
    if anomaly.anomaly_flags:
        trail.append(f"ANOMALY_FLAGS: {'; '.join(anomaly.anomaly_flags)}")
    else:
        trail.append(f"ANOMALY_PASS: Unique hash {anomaly.transaction_fingerprint[:12]} verified")

    # 4. Composite Risk Score Calculation (0 to 100)
    score = 0.0
    if not compliance.supplier_trn_valid:
        score += 35.0
    if not compliance.vat_reconciled:
        score += 25.0
    if not budget.within_budget:
        score += 45.0
    if not budget.cost_center_authorized:
        score += 20.0
    if anomaly.is_duplicate:
        score += 85.0
    if anomaly.structuring_detected:
        score += 25.0
    if anomaly.velocity_spike_flag:
        score += 30.0

    normalized_risk = min(100.0, round(score, 2))

    # 5. Routing Decision: Is cognitive adjudication required?
    # Hard failures (duplicate or severe budget overage) short-circuit directly to reject!
    # Pristine transactions short-circuit directly to approve!
    # Cognitive path is only invoked for ambiguous cases (e.g. high-value near boundary or unmapped OpEx)
    is_hard_fail = anomaly.is_duplicate or (not budget.within_budget and budget.utilization_pct > 120.0)
    is_clean_pass = (normalized_risk == 0.0) and budget.within_budget and compliance.vat_reconciled

    requires_cognitive = (not is_hard_fail) and (not is_clean_pass)

    return {
        "compliance": compliance,
        "budget": budget,
        "anomaly": anomaly,
        "risk_score": normalized_risk,
        "requires_cognitive_review": requires_cognitive,
        "audit_trail": trail
    }


async def node_cognitive_adjudication(state: UnderwritingState) -> Dict[str, Any]:
    """Hierarchical Cognitive Node:
    1. System 1 (TypeSafe Jev via Mesh API): Calibrated, typed choice (OPEX_APPROVED, CAPEX_REVIEW, SUSPICIOUS_PERSONAL).
    2. System 2 (Groq SLM / LLM): Narrative justification memo synthesis based on Jev decision.
    """
    payload: CorporateTransactionPayload = state.get("payload")
    if not payload:
        return {}

    trail = list(state.get("audit_trail", []))
    lines_summary = "; ".join([f"{item.description} ({item.total_item_amount_aed} AED)" for item in payload.financial_line_items])

    # 1. System 1 Evaluation via TypeSafe Jev (Mesh API)
    jev_result = await jev_gateway.evaluate_expense_legitimacy(
        vendor_name=payload.supplier_details.legal_entity_name,
        line_item_summary=lines_summary,
        amount_aed=payload.totals_summary.grand_total_inclusive_vat_aed
    )
    jev_choice = jev_result.get("choice", "OPEX_APPROVED")
    jev_conf = jev_result.get("confidence", 0.9)
    trail.append(f"JEV_SYSTEM1: Semantic Classification='{jev_choice}' (Confidence: {int(jev_conf * 100)}%, Source: {jev_result.get('source')})")

    context_notes = (
        f"System 1 Jev result: {jev_choice} (confidence: {jev_conf}). "
        f"Deterministic risk score: {state.get('risk_score', 0)}. "
        f"Cost center: {payload.customer_details.cost_center}."
    )
    
    # 2. System 2 Narrative Synthesis via LLM
    adjudication = await llm_gateway.adjudicate_expense(
        vendor_name=payload.supplier_details.legal_entity_name,
        line_items_summary=lines_summary,
        department=payload.customer_details.department,
        amount_aed=payload.totals_summary.grand_total_inclusive_vat_aed,
        context_notes=context_notes
    )

    verdict_str = adjudication.get("adjudication_verdict", "APPROVE")
    reasoning = adjudication.get("reasoning", "")
    flags = adjudication.get("recommended_flags", [])

    trail.append(f"COGNITIVE_ADJUDICATION: Verdict={verdict_str}, Confidence={adjudication.get('confidence_score', 1.0)} | {reasoning}")
    if flags:
        trail.append(f"COGNITIVE_FLAGS: {'; '.join(flags)}")

    # Adjust risk score based on System 1 Jev + System 2 LLM insights
    current_risk = state.get("risk_score", 0.0)
    if jev_choice == "SUSPICIOUS_PERSONAL":
        current_risk = min(100.0, current_risk + 50.0)
    elif jev_choice == "CAPEX_REVIEW":
        current_risk = min(100.0, current_risk + 25.0)

    if verdict_str == "REJECT":
        current_risk = min(100.0, current_risk + 40.0)
    elif verdict_str == "APPROVE" and current_risk < 40.0 and jev_choice == "OPEX_APPROVED":
        current_risk = max(0.0, current_risk - 15.0)

    return {
        "risk_score": current_risk,
        "cognitive_notes": reasoning,
        "audit_trail": trail
    }


def node_synthesize_decision(state: UnderwritingState) -> Dict[str, Any]:
    """Compiles all outputs into a strict UnderwritingDecision schema and computes latency."""
    start_time = state.get("start_time", time.perf_counter())
    latency_ms = round((time.perf_counter() - start_time) * 1000.0, 2)
    
    payload = state.get("payload")
    trail = list(state.get("audit_trail", []))
    risk_score = state.get("risk_score", 0.0)
    compliance = state.get("compliance")
    budget = state.get("budget")
    anomaly = state.get("anomaly")

    # Fatal Rejections
    if anomaly and anomaly.is_duplicate:
        verdict = UnderwritingVerdict.REJECTED
        summary = "Duplicate transaction hash detected in active deduplication window."
    elif budget and not budget.within_budget:
        verdict = UnderwritingVerdict.REJECTED
        summary = f"Transaction amount exceeds authorized policy limit by {round(budget.transaction_amount_aed - budget.policy_limit_aed, 2)} AED."
    elif compliance and not compliance.supplier_trn_valid:
        verdict = UnderwritingVerdict.REJECTED
        summary = "Invalid statutory Tax Registration Number (TRN) under FTA/SAMA regulations."
    elif compliance and not compliance.vat_reconciled:
        verdict = UnderwritingVerdict.FLAGGED_MANUAL_REVIEW
        summary = f"VAT reconciliation mismatch: Declared {compliance.declared_vat_aed} AED deviates from calculated statutory {compliance.calculated_vat_aed} AED."
    elif risk_score >= 45.0:
        verdict = UnderwritingVerdict.FLAGGED_MANUAL_REVIEW
        summary = f"Risk score ({risk_score}/100) exceeds auto-approval threshold; routed for controller review."
    else:
        verdict = UnderwritingVerdict.APPROVED
        summary = f"Auto-approved: Full statutory tax compliance, verified OpEx budget limit, and zero anomaly signals."

    invoice_num = payload.document_metadata.invoice_number if payload else "UNKNOWN"
    trail.append(f"DECISION: {verdict.value} (Risk: {risk_score}/100, Latency: {latency_ms}ms)")

    decision = UnderwritingDecision(
        decision_id=str(uuid.uuid4()),
        invoice_number=invoice_num,
        verdict=verdict,
        risk_score=risk_score,
        summary_reason=summary,
        compliance=compliance or ComplianceResult(
            jurisdiction="UNKNOWN",
            regulatory_authority="UNKNOWN",
            supplier_trn_valid=False,
            customer_trn_valid=False,
            statutory_vat_rate=0.05,
            vat_reconciled=False,
            calculated_vat_aed=0.0,
            declared_vat_aed=0.0,
            vat_discrepancy_aed=0.0,
            vat_reclaimable=False,
            compliance_flags=["COMPLIANCE_UNAVAILABLE"]
        ),
        budget=budget or BudgetEvaluationResult(
            policy_limit_aed=0.0,
            transaction_amount_aed=0.0,
            utilization_pct=0.0,
            within_budget=False,
            cost_center_authorized=False,
            expense_classification="Unknown",
            budget_flags=["BUDGET_UNAVAILABLE"]
        ),
        anomaly=anomaly or AnomalyResult(
            is_duplicate=False,
            transaction_fingerprint="NONE",
            velocity_spike_flag=False,
            structuring_detected=False,
            anomaly_score=0.0,
            anomaly_flags=[]
        ),
        audit_trail=trail,
        latency_ms=latency_ms
    )

    return {
        "verdict": verdict,
        "summary_reason": summary,
        "latency_ms": latency_ms,
        "audit_trail": trail,
        "final_decision": decision
    }
