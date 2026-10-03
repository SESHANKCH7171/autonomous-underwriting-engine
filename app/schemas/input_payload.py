"""Input payload schemas for Corporate Invoices and Card Transactions.

Designed to ingest payloads matching the Alaan Corporate Spend model:
- Document metadata (Jurisdiction, FTA/SAMA TRN, QR code status)
- Supplier & Customer details
- Card payment authorization limits
- Line items & totals breakdown
- Pre-existing risk signals
"""

from typing import List, Optional
from pydantic import BaseModel, Field, field_validator


class DocumentMetadata(BaseModel):
    document_type: str = Field(..., description="e.g. TAX_INVOICE, SIMPLIFIED_TAX_INVOICE, RECEIPT")
    jurisdiction: str = Field(..., description="Jurisdiction code e.g. UAE, KSA")
    regulatory_authority: str = Field(..., description="Regulatory body e.g. Federal Tax Authority (FTA), SAMA, ZATCA")
    invoice_number: str = Field(..., description="Vendor invoice number")
    issue_date: str = Field(..., description="ISO Date YYYY-MM-DD")
    supply_date: Optional[str] = Field(None, description="Date of supply if different from issue date")
    po_number: Optional[str] = Field(None, description="Associated Purchase Order number")
    qr_verification_status: Optional[str] = Field("NOT_VERIFIED", description="QR code compliance status")


class SupplierDetails(BaseModel):
    legal_entity_name: str = Field(..., description="Registered legal name of vendor")
    trade_license_zone: Optional[str] = Field(None, description="Free Zone or Mainland jurisdiction e.g. Dubai Internet City")
    city: str = Field(..., description="Supplier city")
    country: str = Field(..., description="Supplier country")
    trn: str = Field(..., description="15-digit Tax Registration Number")
    billing_contact: Optional[str] = Field(None, description="Supplier billing email")
    phone: Optional[str] = Field(None, description="Supplier contact phone")

    @field_validator("trn")
    @classmethod
    def clean_trn(cls, v: str) -> str:
        # Strip spaces and hyphens commonly added by OCR or human data entry
        return v.replace(" ", "").replace("-", "").strip()


class CustomerDetails(BaseModel):
    billed_to: str = Field(..., description="Client corporate entity name")
    corporate_account: str = Field(..., description="Card program or spend management platform account name")
    headquarters: Optional[str] = Field(None, description="HQ address or free zone")
    city: str = Field(..., description="Client city")
    country: str = Field(..., description="Client country")
    trn: str = Field(..., description="15-digit Client Tax Registration Number")
    cost_center: str = Field(..., description="Cost center code e.g. CC-AI-INFRA-04")
    department: str = Field(..., description="Department e.g. Engineering & Core AI")

    @field_validator("trn")
    @classmethod
    def clean_trn(cls, v: str) -> str:
        return v.replace(" ", "").replace("-", "").strip()


class CorporateCardPayment(BaseModel):
    payment_method: str = Field(..., description="Corporate Card tier e.g. Alaan Visa Corporate Platinum Card")
    card_last_four: str = Field(..., min_length=4, max_length=4, description="Last 4 digits of card")
    cardholder_name: str = Field(..., description="Name of employee cardholder")
    transaction_date: str = Field(..., description="ISO Date YYYY-MM-DD")
    payment_status: str = Field(..., description="e.g. PAID_SETTLED, PENDING_AUTHORIZATION")
    policy_limit_aed: float = Field(..., gt=0, description="Authorized spending limit for this card/transaction")
    policy_check: Optional[str] = Field(None, description="Upstream initial policy status")


class FinancialLineItem(BaseModel):
    item_id: int = Field(..., description="Line item sequential identifier")
    description: str = Field(..., description="Description of services or goods rendered")
    quantity: float = Field(..., gt=0, description="Quantity delivered")
    unit_price_aed: float = Field(..., ge=0, description="Unit price exclusive of VAT")
    vat_rate_percentage: float = Field(..., ge=0, description="VAT rate as percentage e.g. 5.0 for UAE, 15.0 for KSA")
    vat_amount_aed: float = Field(..., ge=0, description="VAT amount for this item")
    total_item_amount_aed: float = Field(..., ge=0, description="Total amount inclusive of VAT")


class TotalsSummary(BaseModel):
    subtotal_exclusive_vat_aed: float = Field(..., ge=0, description="Subtotal before VAT")
    vat_rate_standard: float = Field(..., ge=0, description="Standard statutory rate (e.g. 0.05 for 5%)")
    total_vat_amount_aed: float = Field(..., ge=0, description="Total VAT declared")
    grand_total_inclusive_vat_aed: float = Field(..., gt=0, description="Total payable inclusive of VAT")
    currency: str = Field("AED", description="Currency code (AED, SAR, USD)")
    fx_fixed_usd_peg: Optional[float] = Field(3.6725, description="UAE Central Bank fixed USD-AED peg")
    grand_total_equivalent_usd: Optional[float] = Field(None, description="Equivalent in USD")


class UnderwritingRiskSignals(BaseModel):
    is_recurring_expense: Optional[bool] = Field(False, description="Whether this is a known recurring SaaS/cloud provider")
    supplier_verified_trn: Optional[bool] = Field(False, description="Initial check on supplier TRN verification")
    vat_reclaimable: Optional[bool] = Field(True, description="Whether VAT can be claimed as input credit")
    cash_flow_impact: Optional[str] = Field("OpEx", description="Expense classification (OpEx / CapEx)")
    suspicious_patterns_detected: Optional[bool] = Field(False, description="Flag for upstream detected fraud patterns")


class CorporateTransactionPayload(BaseModel):
    """Canonical root schema matching corporate spend and invoice payloads (e.g. alaan_corporate_sample.json)."""
    document_metadata: DocumentMetadata
    supplier_details: SupplierDetails
    customer_details: CustomerDetails
    corporate_card_payment: CorporateCardPayment
    financial_line_items: List[FinancialLineItem] = Field(..., min_length=1)
    totals_summary: TotalsSummary
    underwriting_risk_signals: Optional[UnderwritingRiskSignals] = None
