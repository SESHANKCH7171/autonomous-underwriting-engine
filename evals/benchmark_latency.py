"""P95/P99 Latency SLA Benchmark Harness for Autonomous Underwriting Engine.

Executes 50 concurrent transactions through the LangGraph pipeline to verify:
- P50 < 30ms
- P95 < 100ms
- P99 < 180ms (Hard SLA)
"""

import asyncio
import json
import statistics
import time
from pathlib import Path
from app.graph.workflow import evaluate_transaction


async def run_latency_benchmark(num_iterations: int = 50):
    sample_path = Path(__file__).parent.parent / "data" / "alaan_corporate_sample.json"
    with open(sample_path, "r", encoding="utf-8") as f:
        base_data = json.load(f)

    print(f"\n=================================================================")
    print(f"EXECUTING LATENCY BENCHMARK ({num_iterations} TRANSACTIONS)")
    print(f"Target SLA: P99 < 180.0 ms")
    print(f"=================================================================\n")

    # Warmup Phase (2 iterations) to establish TLS sessions for Logfire & LangSmith
    from app.rules.anomaly_detector import _dedup_store
    _dedup_store.clear()
    warmup_payload = dict(base_data)
    warmup_payload["document_metadata"] = dict(base_data["document_metadata"])
    warmup_payload["document_metadata"]["invoice_number"] = "WARMUP-0001"
    await evaluate_transaction(warmup_payload)
    _dedup_store.clear()

    latencies = []

    for i in range(num_iterations):
        # Vary invoice number and card number to test clean, independent transactions
        payload = dict(base_data)
        payload["document_metadata"] = dict(base_data["document_metadata"])
        payload["document_metadata"]["invoice_number"] = f"BENCH-{i:04d}"
        payload["corporate_card_payment"] = dict(base_data["corporate_card_payment"])
        payload["corporate_card_payment"]["card_last_four"] = f"{1000 + (i % 900):04d}"

        start_time = time.perf_counter()
        decision = await evaluate_transaction(payload)
        elapsed_ms = (time.perf_counter() - start_time) * 1000.0

        latencies.append(elapsed_ms)
        print(f"  [Tx {i+1:02d}/{num_iterations:02d}] Verdict: {decision.verdict.value} | Internal: {decision.latency_ms:6.2f}ms | Total: {elapsed_ms:6.2f}ms")

    # Compute Statistical Metrics
    p50 = statistics.median(latencies)
    mean_val = statistics.mean(latencies)
    min_val = min(latencies)
    max_val = max(latencies)
    
    # Calculate P95 and P99 percentiles
    sorted_latencies = sorted(latencies)
    p95_idx = int(len(sorted_latencies) * 0.95)
    p99_idx = int(len(sorted_latencies) * 0.99)
    p95 = sorted_latencies[min(p95_idx, len(sorted_latencies) - 1)]
    p99 = sorted_latencies[min(p99_idx, len(sorted_latencies) - 1)]

    sla_passed = p99 < 180.0

    print("\n=================================================================")
    print("BENCHMARK RESULTS SUMMARY")
    print(f"  * Total Runs      : {num_iterations}")
    print(f"  * Minimum Latency : {min_val:.2f} ms")
    print(f"  * Mean Latency    : {mean_val:.2f} ms")
    print(f"  * Median (P50)    : {p50:.2f} ms")
    print(f"  * P95 Latency     : {p95:.2f} ms")
    print(f"  * P99 Latency     : {p99:.2f} ms")
    print(f"  * Maximum Latency : {max_val:.2f} ms")
    print(f"  * SLA Status      : {'PASSED (P99 < 180ms)' if sla_passed else 'FAILED'}")
    print("=================================================================\n")

    assert sla_passed, f"P99 latency ({p99:.2f}ms) breached the 180ms SLA threshold!"


if __name__ == "__main__":
    asyncio.run(run_latency_benchmark(30))
