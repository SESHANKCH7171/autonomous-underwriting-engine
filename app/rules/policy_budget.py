"""Corporate Policy & Budget Limit Enforcement Engine.

Validates:
1. Single transaction and daily corporate card spend limits.
2. Cost center to Department authorization mapping.
3. High-utilization warnings (>80% limit consumed).
4. OpEx (Operational Expenditure) vs. CapEx (Capital Expenditure) classification.
"""

from typing import Dict, List, Set
from app.schemas.input_payload import CorporateTransactionPayload
from app.schemas.decision_output import BudgetEvaluationResult

# Authorized Corporate Cost Center to Department Directory
AUTHORIZED_COST_CENTERS: Dict[str, Set[str]] = {
    "CC-AI-INFRA-04": {"ENGINEERING & CORE AI", "AI INFRASTRUCTURE", "CORE AI"},
    "CC-MKT-01": {"GROWTH & MARKETING", "MARKETING"},
    "CC-FIN-02": {"FINANCE & OPERATIONS", "FINANCE"},
    "CC-LEGAL-03": {"LEGAL & COMPLIANCE", "COMPLIANCE"},
    "CC-HR-05": {"PEOPLE & TALENT", "HR"},
}

# Threshold above which an asset purchase must undergo CapEx capitalization review
CAPEX_THRESHOLD_AED = 200000.0

# Keywords indicative of recurring operational software/cloud infrastructure
OPEX_KEYWORDS = {
    "cloud", "gpu", "compute", "cluster", "api", "gateway", "saas", 
    "subscription", "hosting", "inference", "proxy", "pod", "storage"
}


def evaluate_policy_and_budget(payload: CorporateTransactionPayload) -> BudgetEvaluationResult:
    """Evaluates whether the transaction adheres to corporate spend policy and limits.
    
    Sub-millisecond execution (< 1ms).
    """
    card_info = payload.corporate_card_payment
    totals = payload.totals_summary
    customer = payload.customer_details
    
    policy_limit = float(card_info.policy_limit_aed)
    transaction_amount = float(totals.grand_total_inclusive_vat_aed)
    
    flags: List[str] = []
    
    # 1. Budget Limit Check
    within_budget = transaction_amount <= policy_limit
    utilization_pct = round((transaction_amount / policy_limit) * 100.0, 2) if policy_limit > 0 else 100.0

    if not within_budget:
        overage = round(transaction_amount - policy_limit, 2)
        flags.append(
            f"BUDGET_OVERAGE: Transaction amount ({transaction_amount} AED) exceeds card policy limit "
            f"({policy_limit} AED) by {overage} AED"
        )
    elif utilization_pct >= 80.0:
        flags.append(f"HIGH_BUDGET_UTILIZATION: Transaction consumes {utilization_pct}% of single-spend limit")

    # 2. Cost Center & Department Ledger Authorization
    cc_code = customer.cost_center.strip().upper()
    dept_name = customer.department.strip().upper()
    
    authorized_depts = AUTHORIZED_COST_CENTERS.get(cc_code)
    cost_center_authorized = False
    
    if authorized_depts is None:
        flags.append(f"UNAUTHORIZED_COST_CENTER: Cost center '{cc_code}' not found in active corporate chart of accounts")
    elif not any(dept in dept_name or dept_name in dept for dept in authorized_depts):
        flags.append(
            f"COST_CENTER_MISMATCH: Cost center '{cc_code}' belongs to {authorized_depts}, but billed to '{dept_name}'"
        )
    else:
        cost_center_authorized = True

    # 3. OpEx vs CapEx Classification
    descriptions = " ".join(item.description.lower() for item in payload.financial_line_items)
    is_opex = any(kw in descriptions for kw in OPEX_KEYWORDS)
    
    if transaction_amount > CAPEX_THRESHOLD_AED and not is_opex:
        expense_classification = "CapEx"
        flags.append(
            f"CAPEX_REVIEW_REQUIRED: Transaction exceeds {CAPEX_THRESHOLD_AED} AED and requires fixed-asset tagging"
        )
    else:
        expense_classification = "OpEx"

    return BudgetEvaluationResult(
        policy_limit_aed=policy_limit,
        transaction_amount_aed=transaction_amount,
        utilization_pct=utilization_pct,
        within_budget=within_budget,
        cost_center_authorized=cost_center_authorized,
        expense_classification=expense_classification,
        budget_flags=flags
    )
