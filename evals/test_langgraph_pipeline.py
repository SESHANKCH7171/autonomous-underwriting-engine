"""Live Pipeline Evaluation for LangGraph Underwriting State Machine."""

import asyncio
import json
import time
from pathlib import Path
from app.graph.workflow import evaluate_transaction
from app.schemas.decision_output import UnderwritingVerdict


async def test_live_workflow():
    fixture_path = Path(__file__).parent.parent / "data" / "alaan_corporate_sample.json"
    with open(fixture_path, "r", encoding="utf-8") as f:
        data = json.load(f)
        
    from app.rules.anomaly_detector import _dedup_store
    
    # Warmup run to initialize TLS handshakes for Logfire and LangSmith
    _dedup_store.clear()
    warmup_data = json.loads(json.dumps(data))
    warmup_data["document_metadata"]["invoice_number"] = "WARMUP/001"
    await evaluate_transaction(warmup_data)
    _dedup_store.clear()

    start = time.perf_counter()
    decision = await evaluate_transaction(data)
    total_time_ms = (time.perf_counter() - start) * 1000.0

    print("\n=======================================================")
    print("LANGGRAPH UNDERWRITING PIPELINE TEST")
    print(f"Decision ID       : {decision.decision_id}")
    print(f"Invoice Number    : {decision.invoice_number}")
    print(f"Final Verdict     : {decision.verdict.value}")
    print(f"Risk Score        : {decision.risk_score} / 100")
    print(f"Internal Latency  : {decision.latency_ms:.2f} ms")
    print(f"Wall Clock Time   : {total_time_ms:.2f} ms (Target < 180ms)")
    print(f"Summary           : {decision.summary_reason}")
    print("\nAudit Trail:")
    for step in decision.audit_trail:
        print(f"  -> {step}")
    print("=======================================================\n")

    assert decision.verdict == UnderwritingVerdict.APPROVED
    assert total_time_ms < 180.0, f"Latency {total_time_ms}ms exceeded 180ms SLA!"


if __name__ == "__main__":
    asyncio.run(test_live_workflow())
