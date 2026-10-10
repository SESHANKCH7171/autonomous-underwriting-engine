import asyncio
import time
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# pyrefly: ignore [missing-import]
from app.core.jev_gateway import jev_gateway
# pyrefly: ignore [missing-import]
from app.core.llm_gateway import llm_gateway
# pyrefly: ignore [missing-import]
from app.graph.workflow import evaluate_transaction
# pyrefly: ignore [missing-import]
from app.schemas.input_payload import CorporateTransactionPayload

async def main():
    print("--- 1. Testing Jev Gateway alone ---")
    t0 = time.perf_counter()
    j = await jev_gateway.evaluate_expense_legitimacy('CloudScale MENA', 'Cloud GPU Pod', 60900.0)
    print(f"Jev Gateway: {round((time.perf_counter() - t0) * 1000, 2)} ms | result: {j}")

    print("\n--- 2. Testing Groq Gateway alone ---")
    t1 = time.perf_counter()
    g = await llm_gateway.adjudicate_expense('CloudScale MENA', 'Cloud GPU Pod', 'AI Engineering', 60900.0)
    print(f"Groq Gateway: {round((time.perf_counter() - t1) * 1000, 2)} ms | result: {g}")

    print("\n--- 3. Testing Scenario 5 Full Workflow ---")
    import json
    from pathlib import Path
    data = json.loads(Path("data/alaan_corporate_sample.json").read_text(encoding="utf-8"))
    data["document_metadata"]["invoice_number"] = f"BENCH-{int(time.time())}"
    data["totals_summary"]["total_vat_amount_aed"] = 999.0
    
    t2 = time.perf_counter()
    res = await evaluate_transaction(data)
    print(f"Full Workflow: {round((time.perf_counter() - t2) * 1000, 2)} ms | verdict: {res.verdict.value}")

if __name__ == "__main__":
    asyncio.run(main())
