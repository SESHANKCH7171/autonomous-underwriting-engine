"""Compiled LangGraph State Machine for the Autonomous Underwriting Engine.

Architecture:
  [START]
     │
     ▼
  [ingest_and_parse]
     │
     ▼
  [deterministic_rules]
     │
     ├─────────────────────────────────┐
     │ (Fast-Path Short Circuit: 90%)   │ (Ambiguous / Policy Exception: 10%)
     ▼                                 ▼
     │                      [cognitive_adjudication]
     │                                 │
     └────────────────► ◄──────────────┘
                        │
                        ▼
              [synthesize_decision]
                        │
                        ▼
                      [END]
"""

from typing import Any, Dict, Literal
from langgraph.graph import StateGraph, START, END
from app.graph.state import UnderwritingState
from app.graph.nodes import (
    node_ingest_and_parse,
    node_deterministic_rules,
    node_cognitive_adjudication,
    node_synthesize_decision,
)
from app.schemas.decision_output import UnderwritingDecision


def route_after_deterministic_rules(state: UnderwritingState) -> Literal["cognitive_adjudication", "synthesize_decision"]:
    """Conditional Edge Router:
    
    If transaction has zero ambiguity (clean pass) or fatal violation (duplicate/overage),
    short-circuit immediately to decision synthesis in < 15ms.
    Only route to Groq LLM if human/policy ambiguity exists.
    """
    if state.get("requires_cognitive_review", False):
        return "cognitive_adjudication"
    return "synthesize_decision"


def create_underwriting_graph():
    """Builds and compiles the underwriting state graph."""
    builder = StateGraph(UnderwritingState)

    # 1. Register Nodes
    builder.add_node("ingest_and_parse", node_ingest_and_parse)
    builder.add_node("deterministic_rules", node_deterministic_rules)
    builder.add_node("cognitive_adjudication", node_cognitive_adjudication)
    builder.add_node("synthesize_decision", node_synthesize_decision)

    # 2. Register Edges
    builder.add_edge(START, "ingest_and_parse")
    builder.add_edge("ingest_and_parse", "deterministic_rules")

    # 3. Conditional Edge for Sub-180ms Optimization
    builder.add_conditional_edges(
        "deterministic_rules",
        route_after_deterministic_rules,
        {
            "cognitive_adjudication": "cognitive_adjudication",
            "synthesize_decision": "synthesize_decision",
        }
    )

    builder.add_edge("cognitive_adjudication", "synthesize_decision")
    builder.add_edge("synthesize_decision", END)

    return builder.compile()


# Compiled Singleton Graph
underwriting_graph = create_underwriting_graph()


async def evaluate_transaction(raw_payload: Dict[str, Any]) -> UnderwritingDecision:
    """Convenience async entry point to run a payload through the LangGraph engine."""
    from app.telemetry.logfire_setup import configure_logfire
    configure_logfire()
    
    invoice_num = (
        raw_payload.get("document_metadata", {}).get("invoice_number", "UNKNOWN")
        if isinstance(raw_payload, dict) else "UNKNOWN"
    )

    try:
        import logfire
        span_context = logfire.span("evaluate_transaction", invoice_number=invoice_num)
    except Exception:
        from contextlib import nullcontext
        span_context = nullcontext()

    with span_context:
        initial_state: UnderwritingState = {
            "raw_payload": raw_payload
        }
        final_state = await underwriting_graph.ainvoke(initial_state)
        decision: UnderwritingDecision = final_state["final_decision"]
        try:
            import logfire
            logfire.info(
                "Underwriting verdict produced",
                invoice=invoice_num,
                verdict=decision.verdict.value,
                risk_score=decision.risk_score,
                latency_ms=decision.latency_ms
            )
        except Exception:
            pass
        return decision
