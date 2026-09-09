from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime, date
from decimal import Decimal


class BankStockStatementCreate(BaseModel):
    statement_date: date
    bank_name: str = Field(..., min_length=1, max_length=100)
    account_number: str = Field(..., min_length=1, max_length=50)
    cc_limit: Optional[Decimal] = None
    # None -> resolve effective default from config (rbi.bank_stock_margin)
    margin_percent: Optional[Decimal] = Field(None, ge=0, le=100)
    notes: Optional[str] = None


class BankStockStatementResponse(BaseModel):
    id: int
    statement_number: str
    statement_date: date
    bank_name: str
    account_number: str
    stock_value: Decimal
    debtors_value: Decimal
    total_value: Decimal
    margin_percent: Decimal
    drawing_power: Decimal
    cc_limit: Optional[Decimal]
    is_locked: bool
    notes: Optional[str]
    stock_breakup: Optional[List[dict]] = []
    debtor_breakup: Optional[List[dict]] = []
    created_at: datetime
    generated_by_name: Optional[str] = None

    class Config:
        from_attributes = True


class BankStatementEntryImport(BaseModel):
    entry_date: date
    description: str
    debit: Optional[Decimal] = Decimal("0")
    credit: Optional[Decimal] = Decimal("0")
    reference: Optional[str] = None
    balance: Optional[Decimal] = None


class BankReconciliationImport(BaseModel):
    bank_account_code: str
    period_from: date
    period_to: date
    entries: List[BankStatementEntryImport]


class BankReconCreate(BaseModel):
    account_code: str = "BANK"
    period_from: date
    period_to: date
    entries: List[BankStatementEntryImport] = []
    notes: Optional[str] = None


class ManualMatchRequest(BaseModel):
    line_id: int
    journal_line_id: int


class UnmatchRequest(BaseModel):
    line_id: int


class AdjustmentRequest(BaseModel):
    kind: str = Field(..., pattern="^(charge|interest)$")
    amount: Decimal = Field(..., gt=0)
    narration: Optional[str] = None
    line_id: Optional[int] = None


class NotificationSettingsUpdate(BaseModel):
    smtp_host: Optional[str] = None
    smtp_port: Optional[int] = None
    smtp_username: Optional[str] = None
    smtp_password: Optional[str] = None
    smtp_from_email: Optional[str] = None
    admin_email: Optional[str] = None
    accountant_email: Optional[str] = None
    notify_overdue: bool = True
    notify_low_stock: bool = True
    notify_large_invoice: bool = True
    large_invoice_threshold: Optional[Decimal] = None
    notify_einvoice_failure: bool = True
    notify_cheque_bounce: bool = True
    notify_daily_summary: bool = True
    notify_unknown_ip: bool = True
    notify_vendor_due: bool = True
    notify_backup: bool = True


class ScheduledReportSettings(BaseModel):
    daily_sales_enabled: bool = True
    daily_sales_time: str = "08:00"
    weekly_outstanding_enabled: bool = True
    monthly_pnl_enabled: bool = True
    monthly_stock_enabled: bool = True
    monthly_gst_enabled: bool = True
    monthly_bank_statement_reminder: bool = True
    recipient_emails: List[str] = []
