"""Verification and Conformance Test Suite for Phase 1 Rule Engines.

Validates:
1. Ingestion of canonical alaan_corporate_sample.json.
2. Deterministic FTA TRN and VAT 5% reconciliation.
3. Policy budget limit authorization against CC-AI-INFRA-04.
4. Cryptographic SHA-256 fingerprinting and deduplication.
5. End-to-end execution latency (< 15ms target).
"""

import json
import time
from pathlib import Path
from app.schemas.input_payload import CorporateTransactionPayload
from app.rules.fta_sama_compliance import evaluate_tax_compliance
from app.rules.policy_budget import evaluate_policy_and_budget
from app.rules.anomaly_detector import evaluate_anomalies, InMemoryDeduplicationStore


def test_alaan_canonical_sample_evaluation():
    # 1. Load canonical fixture
    sample_path = Path(__file__).parent.parent / "data" / "alaan_corporate_sample.json"
    assert sample_path.exists(), f"Sample fixture not found at {sample_path}"

    with open(sample_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    start_time = time.perf_counter()

    # 2. Schema Ingestion
    payload = CorporateTransactionPayload.model_validate(data)
    assert payload.supplier_details.trn == "100458923100003"
    assert payload.customer_details.cost_center == "CC-AI-INFRA-04"

    # 3. Tax & FTA Compliance Engine
    compliance = evaluate_tax_compliance(payload)
    assert compliance.supplier_trn_valid is True
    assert compliance.customer_trn_valid is True
    assert compliance.vat_reconciled is True
    assert compliance.calculated_vat_aed == 2900.0
    assert compliance.vat_reclaimable is True
    assert len(compliance.compliance_flags) == 0

    # 4. Policy & Budget Limit Engine
    budget = evaluate_policy_and_budget(payload)
    assert budget.within_budget is True
    assert budget.utilization_pct == 60.9
    assert budget.cost_center_authorized is True
    assert budget.expense_classification == "OpEx"

    # 5. Anomaly & Duplicate Detection Engine
    custom_store = InMemoryDeduplicationStore()
    anomaly_first_pass = evaluate_anomalies(payload, dedup_store=custom_store)
    assert anomaly_first_pass.is_duplicate is False
    assert anomaly_first_pass.anomaly_score == 0.0

    # Test second submission with same store (must trigger duplicate!)
    anomaly_second_pass = evaluate_anomalies(payload, dedup_store=custom_store)
    assert anomaly_second_pass.is_duplicate is True
    assert anomaly_second_pass.anomaly_score >= 80.0
    assert any("DUPLICATE_TRANSACTION" in f for f in anomaly_second_pass.anomaly_flags)

    total_latency_ms = (time.perf_counter() - start_time) * 1000.0

    print("\n=======================================================")
    print("PHASE 1 CONFORMANCE TEST PASSED")
    print(f"Total Execution Time: {total_latency_ms:.3f} ms (Target < 15ms)")
    print(f"Supplier TRN Status : {'VALID' if compliance.supplier_trn_valid else 'INVALID'}")
    print(f"VAT Reconciled      : {compliance.vat_reconciled} ({compliance.calculated_vat_aed} AED)")
    print(f"Budget Utilization  : {budget.utilization_pct}% ({budget.transaction_amount_aed} / {budget.policy_limit_aed} AED)")
    print(f"Dedup Fingerprint   : {anomaly_first_pass.transaction_fingerprint[:16]}...")
    print("=======================================================\n")

    # Assert that all 3 engines executed well under 15ms
    assert total_latency_ms < 15.0, f"Latency {total_latency_ms}ms exceeded 15ms target!"


if __name__ == "__main__":
    test_alaan_canonical_sample_evaluation()
