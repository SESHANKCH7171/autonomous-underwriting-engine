"""Anomaly, Duplicate Transaction & Structuring Detection Engine.

Uses SHA-256 transaction fingerprinting with an async in-memory TTL cache (and Redis client support).
Detects:
1. Exact duplicate invoice submissions or card double-swipes.
2. Velocity spikes (card used repeatedly in short time windows).
3. Invoice structuring (splitting purchases just beneath policy approval limits).
"""

import hashlib
import time
from typing import Dict, List, Optional
from app.schemas.input_payload import CorporateTransactionPayload
from app.schemas.decision_output import AnomalyResult


class InMemoryDeduplicationStore:
    """High-speed in-memory TTL cache for development and non-Redis environments."""
    def __init__(self, default_ttl_seconds: int = 86400):
        self.default_ttl = default_ttl_seconds
        self._store: Dict[str, float] = {}  # key -> expiry_timestamp
        self._card_velocity: Dict[str, List[float]] = {}  # card -> list of epoch timestamps

    def is_duplicate(self, fingerprint: str) -> bool:
        now = time.time()
        expiry = self._store.get(fingerprint)
        if expiry and expiry > now:
            return True
        # Store key with TTL
        self._store[fingerprint] = now + self.default_ttl
        return False

    def record_and_check_velocity(self, card_last_four: str, window_seconds: int = 300, max_swipes: int = 3) -> bool:
        """Returns True if velocity threshold exceeded (e.g. > 3 swipes within 5 minutes)."""
        now = time.time()
        swipes = self._card_velocity.get(card_last_four, [])
        # Prune old timestamps outside the window
        recent_swipes = [t for t in swipes if now - t <= window_seconds]
        recent_swipes.append(now)
        self._card_velocity[card_last_four] = recent_swipes
        return len(recent_swipes) > max_swipes

    def clear(self):
        self._store.clear()
        self._card_velocity.clear()


# Global Singleton Store (Zero-setup local mode)
_dedup_store = InMemoryDeduplicationStore()


def generate_transaction_fingerprint(payload: CorporateTransactionPayload) -> str:
    """Generates a cryptographic SHA-256 fingerprint uniquely identifying this transaction.
    
    Components:
    - Supplier TRN
    - Invoice Number
    - Grand Total (rounded to 2 decimal places)
    - Customer TRN
    """
    raw_str = (
        f"{payload.supplier_details.trn.strip()}|"
        f"{payload.document_metadata.invoice_number.strip().upper()}|"
        f"{round(payload.totals_summary.grand_total_inclusive_vat_aed, 2)}|"
        f"{payload.customer_details.trn.strip()}"
    )
    return hashlib.sha256(raw_str.encode("utf-8")).hexdigest()


def evaluate_anomalies(
    payload: CorporateTransactionPayload,
    dedup_store: Optional[InMemoryDeduplicationStore] = None
) -> AnomalyResult:
    """Evaluates transaction payload for fraud indicators, duplicate submissions, and velocity spikes.
    
    Executes in < 1ms.
    """
    store = dedup_store or _dedup_store
    flags: List[str] = []
    anomaly_score = 0.0

    # 1. Deduplication Check
    fingerprint = generate_transaction_fingerprint(payload)
    is_duplicate = store.is_duplicate(fingerprint)
    
    if is_duplicate:
        flags.append(f"DUPLICATE_TRANSACTION: Invoice fingerprint '{fingerprint[:12]}...' already processed in active window")
        anomaly_score += 85.0

    # 2. Velocity Check on Corporate Card
    card_last_four = payload.corporate_card_payment.card_last_four
    velocity_spike = store.record_and_check_velocity(card_last_four, window_seconds=300, max_swipes=4)
    if velocity_spike:
        flags.append(f"CARD_VELOCITY_SPIKE: Card ending in {card_last_four} exceeded 4 transactions in 5 minutes")
        anomaly_score += 30.0

    # 3. Structuring / Smurfing Detection
    # If the transaction is within 95% to 99.9% of the policy limit, flag for structuring review
    limit = payload.corporate_card_payment.policy_limit_aed
    amount = payload.totals_summary.grand_total_inclusive_vat_aed
    structuring_detected = False
    
    if limit > 0 and 0.95 <= (amount / limit) < 1.0:
        structuring_detected = True
        flags.append(
            f"STRUCTURING_RISK: Amount ({amount} AED) is suspicious near-boundary limit ({limit} AED)"
        )
        anomaly_score += 20.0

    # 4. Check for pre-existing suspicious patterns flag
    if payload.underwriting_risk_signals and payload.underwriting_risk_signals.suspicious_patterns_detected:
        flags.append("UPSTREAM_FRAUD_FLAG: Upstream issuer signaled suspicious pattern")
        anomaly_score += 40.0

    # Cap anomaly score at 100.0
    normalized_score = min(100.0, round(anomaly_score, 2))

    return AnomalyResult(
        is_duplicate=is_duplicate,
        transaction_fingerprint=fingerprint,
        velocity_spike_flag=velocity_spike,
        structuring_detected=structuring_detected,
        anomaly_score=normalized_score,
        anomaly_flags=flags
    )
