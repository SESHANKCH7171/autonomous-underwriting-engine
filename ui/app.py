"""Autonomous Financial Risk & Underwriting Cockpit.

Streamlit interactive dashboard for real-time GCC corporate spend evaluation:
- Loads canonical and adversarial test cases (Alaan sample, Duplicate fraud, TRN spoofing, Budget overages).
- Runs LangGraph State Machine asynchronously.
- Renders sub-180ms latency telemetry, risk gauges, and FTA/SAMA audit trails.
"""

import asyncio
import json
import os
import sys
import time
from pathlib import Path

# Add project root to sys.path
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

# Prevent Streamlit script name 'app.py' from colliding with the top-level 'app' package
if "app" in sys.modules and not hasattr(sys.modules["app"], "__path__"):
    del sys.modules["app"]

import streamlit as st
from app.graph.workflow import evaluate_transaction
from app.schemas.decision_output import UnderwritingVerdict

st.set_page_config(
    page_title="Autonomous Financial Risk Engine | GCC Underwriting",
    page_icon="💳",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom Styling
st.markdown("""
<style>
    .main-header {
        font-size: 2.2rem;
        font-weight: 800;
        color: #1E293B;
        margin-bottom: 0.2rem;
    }
    .sub-header {
        font-size: 1.05rem;
        color: #64748B;
        margin-bottom: 1.5rem;
    }
    .metric-card {
        background-color: #F8FAFC;
        border: 1px solid #E2E8F0;
        border-radius: 8px;
        padding: 1rem;
        text-align: center;
    }
    .verdict-approved {
        background-color: #ECFDF5;
        border: 2px solid #10B981;
        color: #065F46;
        padding: 1rem;
        border-radius: 8px;
        font-size: 1.6rem;
        font-weight: 700;
        text-align: center;
    }
    .verdict-rejected {
        background-color: #FEF2F2;
        border: 2px solid #EF4444;
        color: #991B1B;
        padding: 1rem;
        border-radius: 8px;
        font-size: 1.6rem;
        font-weight: 700;
        text-align: center;
    }
    .verdict-review {
        background-color: #FFFBEB;
        border: 2px solid #F59E0B;
        color: #92400E;
        padding: 1rem;
        border-radius: 8px;
        font-size: 1.6rem;
        font-weight: 700;
        text-align: center;
    }
    [data-testid="stMetricValue"] {
        font-size: 1.35rem !important;
        white-space: nowrap;
        overflow: visible !important;
    }
    [data-testid="stMetricDelta"] {
        font-size: 0.78rem !important;
        white-space: nowrap;
        overflow: visible !important;
    }
</style>
""", unsafe_allow_html=True)

# Header
st.markdown('<div class="main-header">Autonomous Financial Risk & Underwriting Engine</div>', unsafe_allow_html=True)
st.markdown('<div class="sub-header">Real-Time FTA (UAE) & SAMA (KSA) Compliance State Machine | Target SLA: Sub-180ms P99</div>', unsafe_allow_html=True)

# Load Canonical Sample
SAMPLE_PATH = ROOT_DIR / "data" / "alaan_corporate_sample.json"
default_payload = {}
if SAMPLE_PATH.exists():
    with open(SAMPLE_PATH, "r", encoding="utf-8") as f:
        default_payload = json.load(f)

# Sidebar Scenario Selector
st.sidebar.header("🎯 Pre-configured Scenarios")
scenario = st.sidebar.selectbox(
    "Select Underwriting Case:",
    [
        "1. Canonical Alaan Invoice (Valid OpEx Cloud Pod)",
        "2. Fraud Attack: Duplicate Invoice Resubmission",
        "3. Regulatory Attack: Forged UAE TRN Syntax",
        "4. Policy Violation: Exceeded Card Policy Limit",
        "5. Accounting Error: 5% VAT Calculation Discrepancy"
    ]
)

st.sidebar.markdown("---")
if st.sidebar.button("🧹 Reset Deduplication & Velocity Cache", use_container_width=True):
    from app.rules.anomaly_detector import _dedup_store
    _dedup_store.clear()
    st.sidebar.success("✅ Cache cleared! Ready for fresh testing.")
st.sidebar.caption("ℹ️ *Note: Only click reset if you want to test from scratch. Testing duplicate fraud requires an active cache.*")

# Mutate payload based on scenario
test_payload = json.loads(json.dumps(default_payload))

if "Duplicate" in scenario:
    from app.rules.anomaly_detector import _dedup_store, generate_transaction_fingerprint
    from app.schemas.input_payload import CorporateTransactionPayload
    try:
        p_obj = CorporateTransactionPayload(**test_payload)
        _fp = generate_transaction_fingerprint(p_obj)
        _dedup_store._store[_fp] = time.time() + 86400.0  # Pre-seed so evaluation catches it as duplicate!
    except Exception:
        pass
    st.sidebar.error("🚨 Duplicate fingerprint primed in cache! Click Evaluate to verify instant rejection.")
elif "Forged UAE TRN" in scenario:
    test_payload["document_metadata"]["invoice_number"] = "INV-2023-AML-4491"
    test_payload["supplier_details"]["trn"] = "999888777666555"  # Fails 100...3 FTA syntax
elif "Exceeded Card Policy" in scenario:
    test_payload["document_metadata"]["invoice_number"] = "INV-2023-CAP-7712"
    test_payload["totals_summary"]["grand_total_inclusive_vat_aed"] = 145000.0  # Limit is 100,000 AED
elif "VAT Calculation Discrepancy" in scenario:
    test_payload["document_metadata"]["invoice_number"] = "INV-2023-VAT-9021"
    test_payload["totals_summary"]["total_vat_amount_aed"] = 999.0  # Should be 2900.0 AED

# Layout Columns
col_left, col_right = st.columns([1, 1], gap="large")

with col_left:
    st.subheader("📄 Transaction Payload (JSON)")
    payload_str = st.text_area(
        "Edit or inspect invoice payload:",
        value=json.dumps(test_payload, indent=2),
        height=520,
        key=f"payload_area_{scenario}"
    )
    
    evaluate_clicked = st.button("🚀 Evaluate Underwriting Decision", type="primary", use_container_width=True)

with col_right:
    st.subheader("⚡ Real-Time Decision Matrix")
    
    if evaluate_clicked:
        try:
            parsed_data = json.loads(payload_str)
        except json.JSONDecodeError as e:
            st.error(f"Invalid JSON syntax: {e}")
            st.stop()

        # Run Async Underwriting State Machine
        t0 = time.perf_counter()
        with st.spinner("Executing LangGraph State Machine..."):
            decision = asyncio.run(evaluate_transaction(parsed_data))
        total_time_ms = round((time.perf_counter() - t0) * 1000.0, 2)

        # Verdict Banner
        if decision.verdict == UnderwritingVerdict.APPROVED:
            st.markdown(f'<div class="verdict-approved">APPROVED &nbsp;•&nbsp; {total_time_ms} ms</div>', unsafe_allow_html=True)
        elif decision.verdict == UnderwritingVerdict.REJECTED:
            st.markdown(f'<div class="verdict-rejected">REJECTED &nbsp;•&nbsp; {total_time_ms} ms</div>', unsafe_allow_html=True)
        else:
            st.markdown(f'<div class="verdict-review">MANUAL REVIEW &nbsp;•&nbsp; {total_time_ms} ms</div>', unsafe_allow_html=True)

        st.caption(f"**Executive Summary:** {decision.summary_reason}")

        # Metrics Row
        m1, m2, m3, m4 = st.columns([1.2, 1, 1, 1])
        sla_threshold = 180.0
        with m1:
            if total_time_ms <= sla_threshold:
                st.metric(
                    "Total Latency",
                    f"{total_time_ms} ms",
                    delta=f"< {int(sla_threshold)}ms SLA (PASSED)",
                    delta_color="normal"  # Green
                )
            else:
                over_by = round(total_time_ms - sla_threshold, 1)
                st.metric(
                    "Total Latency",
                    f"{total_time_ms} ms",
                    delta=f"- BREACH: >180ms (+{over_by}ms)",
                    delta_color="normal"  # Starts with '-' so Streamlit automatically renders RED
                )
        with m2:
            st.metric("Risk Score", f"{decision.risk_score:.1f} / 100")
        with m3:
            st.metric("Budget Used", f"{decision.budget.utilization_pct:.1f}%")
        with m4:
            st.metric("VAT Reclaimable", "YES" if decision.compliance.vat_reclaimable else "NO")

        # Real-Time Unit Economics Strip
        is_fast_path = not any("JEV_SYSTEM1" in step for step in decision.audit_trail)
        jev_cost = 0.000000 if is_fast_path else 0.000010
        groq_cost = 0.000000 if is_fast_path else 0.000030
        engine_cost = jev_cost + groq_cost
        gpt4_cost = 0.009000
        savings_pct = round(((gpt4_cost - engine_cost) / gpt4_cost) * 100.0, 2)

        st.markdown(
            f"""
            <div style="background: #0F172A; border-radius: 8px; padding: 0.75rem 1rem; margin: 1rem 0; border: 1px solid #334155; display: flex; justify-content: space-between; align-items: center;">
                <span style="color: #94A3B8; font-size: 0.85rem;">💰 <b>Unit Economics:</b> {"⚡ Fast-Path (Pure Python)" if is_fast_path else "🧠 Cognitive Path (Jev + Groq)"}</span>
                <span style="color: #10B981; font-weight: 700; font-size: 0.95rem;">Cost: ${engine_cost:.6f}</span>
                <span style="color: #EF4444; font-size: 0.85rem; text-decoration: line-through;">GPT-4o: ${gpt4_cost:.6f}</span>
                <span style="background: #064E3B; color: #34D399; padding: 2px 8px; border-radius: 4px; font-weight: 700; font-size: 0.8rem;">{savings_pct}% SAVINGS</span>
            </div>
            """,
            unsafe_allow_html=True
        )

        # Detailed Breakdown Tabs
        tab1, tab2, tab3, tab4, tab5 = st.tabs(["🏛️ Tax & Compliance", "💼 Budget & Policy", "🔍 Fraud & Anomalies", "📜 Audit Log", "💰 Unit Economics & ROI"])

        with tab1:
            st.markdown(f"**Jurisdiction:** `{decision.compliance.jurisdiction}` ({decision.compliance.regulatory_authority})")
            st.markdown(f"**Supplier TRN Valid:** `{'✅ VALID' if decision.compliance.supplier_trn_valid else '❌ INVALID'}`")
            st.markdown(f"**Customer TRN Valid:** `{'✅ VALID' if decision.compliance.customer_trn_valid else '❌ INVALID'}`")
            st.markdown(f"**Statutory VAT Rate:** `{int(decision.compliance.statutory_vat_rate * 100)}%`")
            st.markdown(f"**VAT Reconciled:** `{'✅ MATCHED' if decision.compliance.vat_reconciled else '❌ MISMATCH'}` (Calc: {decision.compliance.calculated_vat_aed} AED vs Declared: {decision.compliance.declared_vat_aed} AED)")
            if decision.compliance.compliance_flags:
                st.error("Compliance Warnings:")
                for f in decision.compliance.compliance_flags:
                    st.write(f"- {f}")

        with tab2:
            st.markdown(f"**Authorized Limit:** `{decision.budget.policy_limit_aed:,.2f} AED`")
            st.markdown(f"**Transaction Amount:** `{decision.budget.transaction_amount_aed:,.2f} AED`")
            st.markdown(f"**Within Policy Limit:** `{'✅ YES' if decision.budget.within_budget else '❌ EXCEEDED'}`")
            st.markdown(f"**Cost Center Authorized:** `{'✅ YES' if decision.budget.cost_center_authorized else '❌ UNMAPPED'}`")
            st.markdown(f"**Classification:** `{decision.budget.expense_classification}`")
            if decision.budget.budget_flags:
                st.warning("Budget Warnings:")
                for f in decision.budget.budget_flags:
                    st.write(f"- {f}")

        with tab3:
            st.markdown(f"**Duplicate Detected:** `{'🚨 DUPLICATE HASH' if decision.anomaly.is_duplicate else '✅ UNIQUE'}`")
            st.markdown(f"**Transaction Fingerprint:** `{decision.anomaly.transaction_fingerprint}`")
            st.markdown(f"**Velocity Spike:** `{'⚠️ VELOCITY EXCEEDED' if decision.anomaly.velocity_spike_flag else '✅ NORMAL'}`")
            st.markdown(f"**Structuring Risk:** `{'⚠️ STRUCTURING PATTERN' if decision.anomaly.structuring_detected else '✅ CLEAN'}`")
            if decision.anomaly.anomaly_flags:
                st.error("Fraud Flags:")
                for f in decision.anomaly.anomaly_flags:
                    st.write(f"- {f}")

        with tab4:
            st.markdown("**Chronological Execution Steps:**")
            for step in decision.audit_trail:
                st.code(step, language="text")

        with tab5:
            st.subheader("💵 Financial Unit Economics & Infrastructure ROI")
            st.markdown("Compare the exact processing cost of this transaction against traditional monolithic LLMs and manual human underwriting.")
            
            c_cost1, c_cost2, c_cost3 = st.columns(3)
            with c_cost1:
                st.metric("This Engine Run", f"${engine_cost:.6f}", delta="Fast-Path 90%" if is_fast_path else "Cognitive 10%")
            with c_cost2:
                st.metric("Monolithic GPT-4o", f"${gpt4_cost:.6f}", delta="-99.5% cheaper")
            with c_cost3:
                st.metric("Human Underwriter", "$4.500000", delta="-100% automated")

            st.markdown("---")
            st.markdown("#### 🔬 Cost Component Breakdown for This Execution")
            st.write(f"- **Deterministic Rules (TRN + VAT + SHA-256 Dedup)**: `$0.000000` *(Pure Python, in-process)*")
            st.write(f"- **System 1 (TypeSafe Jev via Mesh API)**: `${jev_cost:.6f}` *(Calibrated 70ms categorization)*")
            st.write(f"- **System 2 (Groq Ultra-Fast Llama/Mixtral)**: `${groq_cost:.6f}` *(Statutory audit memo synthesis)*")
            st.write(f"- **Telemetry (Logfire & LangSmith)**: `$0.000000` *(Included in telemetry tier)*")

            st.markdown("---")
            st.markdown("#### 📈 Enterprise Scale Projections (Corporate Card Fleet)")
            st.markdown("""
            | Monthly Volume | This Engine (90/10 Fast-Path) | Monolithic LLM (GPT-4o) | Human Underwriting Team | Net Monthly Savings |
            | :--- | :--- | :--- | :--- | :--- |
            | **10,000 Swipes** | **$0.04** | $90.00 | $45,000.00 | **$89.96 (99.95%)** |
            | **100,000 Swipes** | **$0.40** | $900.00 | $450,000.00 | **$899.60 (99.95%)** |
            | **1,000,000 Swipes** | **$4.00** | $9,000.00 | $4,500,000.00 | **$8,996.00 (99.95%)** |
            """)
            st.caption("ℹ️ *Pricing Model: Mesh API Jev ~$0.042/1M tokens; Groq ~$0.08/1M tokens; GPT-4o ~$2.50 in / $10 out per 1M tokens; Human Underwriter ~$4.50/review.*")

    else:
        st.info("👈 Select a test scenario and click **Evaluate Underwriting Decision** to inspect real-time state machine execution.")
