from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime, date
from decimal import Decimal
from app.models.models import PaymentMode


# ── Cheque Register Schemas ───────────────────────────────────

class ChequeCreate(BaseModel):
    cheque_number: str = Field(..., min_length=1, max_length=30)
    cheque_date: date
    bank_name: str = Field(..., min_length=1, max_length=100)
    amount: Decimal = Field(..., gt=0)
    customer_id: Optional[int] = None
    vendor_id: Optional[int] = None
    receipt_id: Optional[int] = None
    payment_id: Optional[int] = None
    is_pdc: bool = False
    deposit_date: Optional[date] = None
    notes: Optional[str] = None


class ChequeDepositUpdate(BaseModel):
    deposit_date: date
    bank_account_code: str = "BANK"
    notes: Optional[str] = None


class ChequeClearanceUpdate(BaseModel):
    clearance_date: date
    notes: Optional[str] = None


class ChequeBounceUpdate(BaseModel):
    bounce_date: date
    bounce_reason: str
    bounce_charges: Decimal = Decimal("0")
    notes: Optional[str] = None


class ChequeResponse(BaseModel):
    id: int
    cheque_number: str
    cheque_date: date
    bank_name: str
    amount: Decimal
    customer_name: Optional[str]
    vendor_name: Optional[str]
    status: str
    is_pdc: bool
    deposit_date: Optional[date]
    clearance_date: Optional[date]
    bounce_date: Optional[date]
    bounce_reason: Optional[str]
    bounce_charges: Optional[Decimal]
    notes: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True


# ── Cash Closing Schemas ──────────────────────────────────────

class CashClosingResponse(BaseModel):
    id: int
    closing_date: date
    opening_balance: Decimal
    total_receipts: Decimal
    total_payments: Decimal
    total_expenses: Decimal
    total_deposits: Decimal
    closing_balance: Decimal
    status: str
    approved_by_name: Optional[str]
    approved_at: Optional[datetime]
    financial_year: str
    created_at: datetime
    entries: Optional[List[dict]] = []

    class Config:
        from_attributes = True


class CashClosingCreate(BaseModel):
    closing_date: date
    total_deposits: Decimal = Field(Decimal("0"), ge=0)
    notes: Optional[str] = None


class CashClosingApprove(BaseModel):
    notes: Optional[str] = None


# ── Expense Schemas ───────────────────────────────────────────

class ExpenseCreate(BaseModel):
    expense_date: date
    category: str = Field(..., min_length=1, max_length=100)
    description: str = Field(..., min_length=1, max_length=500)
    amount: Decimal = Field(..., gt=0)
    payment_mode: PaymentMode
    reference_number: Optional[str] = None
    vendor_id: Optional[int] = None
    notes: Optional[str] = None


class ExpenseApprove(BaseModel):
    approved: bool
    admin_notes: Optional[str] = None


class ExpenseResponse(BaseModel):
    id: int
    expense_number: str
    expense_date: date
    category: str
    description: str
    amount: Decimal
    payment_mode: str
    reference_number: Optional[str]
    vendor_name: Optional[str]
    status: str
    admin_notes: Optional[str]
    notes: Optional[str]
    financial_year: str
    created_at: datetime

    class Config:
        from_attributes = True


# ── TDS Schemas ───────────────────────────────────────────────

class TDSEntryCreate(BaseModel):
    customer_id: int
    receipt_id: Optional[int] = None
    tds_amount: Decimal = Field(..., gt=0)
    tds_percent: Decimal = Field(..., gt=0, le=100)
    invoice_amount: Decimal = Field(..., gt=0)
    deduction_date: date
    tan_number: Optional[str] = None
    section_code: str = "194C"
    financial_year: str
    notes: Optional[str] = None


class TDSEntryResponse(BaseModel):
    id: int
    tds_number: str
    customer_name: Optional[str]
    receipt_id: Optional[int]
    tds_amount: Decimal
    tds_percent: Decimal
    invoice_amount: Decimal
    deduction_date: date
    tan_number: Optional[str]
    section_code: str
    financial_year: str
    is_reconciled: bool
    created_at: datetime

    class Config:
        from_attributes = True


class Form26ASImport(BaseModel):
    financial_year: str
    entries: List[dict]


# ── Customer Ageing Schemas ───────────────────────────────────

class CustomerAgeingItem(BaseModel):
    customer_id: int
    customer_name: str
    gstin: Optional[str]
    phone: Optional[str]
    bucket_0_30: Decimal
    bucket_31_60: Decimal
    bucket_61_90: Decimal
    bucket_90_plus: Decimal
    total_outstanding: Decimal
    collection_priority_score: Decimal
    last_payment_date: Optional[date]
    credit_days: int
    credit_limit: Decimal


# ── Journal Schemas ───────────────────────────────────────────

class JournalLineCreate(BaseModel):
    account_code: str = Field(..., min_length=1, max_length=20)
    transaction_type: str = Field(..., pattern="^(debit|credit)$")
    amount: Decimal = Field(..., gt=0)
    narration: Optional[str] = None


class JournalEntryCreate(BaseModel):
    entry_date: date
    narration: str = Field(..., min_length=1, max_length=500)
    reference_type: Optional[str] = "manual"
    lines: List[JournalLineCreate] = Field(..., min_length=2)


class JournalEntryResponse(BaseModel):
    id: int
    entry_number: str
    entry_date: date
    reference_type: str
    reference_id: int
    narration: str
    financial_year: str
    created_at: datetime
    lines: List[dict] = []

    class Config:
        from_attributes = True


# ── Trial Balance ─────────────────────────────────────────────

class TrialBalanceItem(BaseModel):
    account_code: str
    account_name: str
    account_type: str
    debit_total: Decimal
    credit_total: Decimal
    net_balance: Decimal
