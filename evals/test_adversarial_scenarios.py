"""Adversarial and Regulatory Edge-Case Test Suite.

Proves the system rejects:
1. Forged UAE TRN (non-FTA compliant)
2. Declared VAT mismatch
3. Budget limit overrun
4. Duplicate invoice resubmission
"""

import asyncio
import json
from pathlib import Path
from app.graph.workflow import evaluate_transaction
from app.schemas.decision_output import UnderwritingVerdict


async def run_adversarial_tests():
    sample_path = Path(__file__).parent.parent / "data" / "alaan_corporate_sample.json"
    with open(sample_path, "r", encoding="utf-8") as f:
        base_data = json.load(f)

    print("\n=======================================================")
    print("RUNNING ADVERSARIAL & REGULATORY ATTACK TESTS")
    print("=======================================================")

    # Test 1: Forged TRN Attack
    bad_trn_payload = json.loads(json.dumps(base_data))
    bad_trn_payload["supplier_details"]["trn"] = "999888777666555"  # Fails 100...3 rule
    bad_trn_payload["document_metadata"]["invoice_number"] = "INV-FAKE-TRN"
    d1 = await evaluate_transaction(bad_trn_payload)
    print(f"Test 1 [Forged TRN]       -> Verdict: {d1.verdict.value} (Risk: {d1.risk_score})")
    assert d1.verdict == UnderwritingVerdict.REJECTED
    assert d1.compliance.supplier_trn_valid is False

    # Test 2: VAT Discrepancy Attack
    bad_vat_payload = json.loads(json.dumps(base_data))
    bad_vat_payload["totals_summary"]["total_vat_amount_aed"] = 500.0  # Should be 2900.0
    bad_vat_payload["document_metadata"]["invoice_number"] = "INV-BAD-VAT"
    d2 = await evaluate_transaction(bad_vat_payload)
    print(f"Test 2 [VAT Discrepancy]  -> Verdict: {d2.verdict.value} (Reconciled: {d2.compliance.vat_reconciled})")
    assert d2.verdict == UnderwritingVerdict.FLAGGED_MANUAL_REVIEW
    assert d2.compliance.vat_reconciled is False

    # Test 3: Budget Overrun
    over_budget_payload = json.loads(json.dumps(base_data))
    over_budget_payload["totals_summary"]["grand_total_inclusive_vat_aed"] = 150000.0  # Limit is 100k
    over_budget_payload["document_metadata"]["invoice_number"] = "INV-OVER-BUDGET"
    d3 = await evaluate_transaction(over_budget_payload)
    print(f"Test 3 [Budget Overrun]   -> Verdict: {d3.verdict.value} (Within Budget: {d3.budget.within_budget})")
    assert d3.verdict == UnderwritingVerdict.REJECTED
    assert d3.budget.within_budget is False

    # Test 4: Duplicate Submission Attack
    dupe_payload = json.loads(json.dumps(base_data))
    dupe_payload["document_metadata"]["invoice_number"] = "INV-DUPE-TEST"
    first_pass = await evaluate_transaction(dupe_payload)
    second_pass = await evaluate_transaction(dupe_payload)
    print(f"Test 4 [Duplicate Attack] -> Pass 1: {first_pass.verdict.value} | Pass 2: {second_pass.verdict.value}")
    assert second_pass.verdict == UnderwritingVerdict.REJECTED
    assert second_pass.anomaly.is_duplicate is True

    print("\n=======================================================")
    print("ALL 4 ADVERSARIAL ATTACKS SUCCESSFULLY DEFENDED")
    print("=======================================================\n")


if __name__ == "__main__":
    asyncio.run(run_adversarial_tests())
