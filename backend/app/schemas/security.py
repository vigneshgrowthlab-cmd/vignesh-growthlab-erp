from pydantic import BaseModel, Field, EmailStr
from typing import Optional, List
from datetime import datetime, date
from decimal import Decimal


# ── User Management Schemas ───────────────────────────────────

class UserCreate(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    email: str = Field(..., min_length=5, max_length=200)
    full_name: str = Field(..., min_length=1, max_length=200)
    role: str = Field(..., pattern="^(admin|accountant|sales)$")
    password: str = Field(..., min_length=8)
    is_active: bool = True


class UserUpdate(BaseModel):
    full_name: Optional[str] = None
    email: Optional[str] = None
    role: Optional[str] = None
    is_active: Optional[bool] = None


class UserPasswordReset(BaseModel):
    new_password: str = Field(..., min_length=8)


class UserResponse(BaseModel):
    id: int
    username: str
    email: str
    full_name: str
    role: str
    is_active: bool
    is_locked: bool
    failed_login_attempts: int
    last_login_at: Optional[datetime]
    last_login_ip: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True


# ── Session Schemas ───────────────────────────────────────────

class ActiveSessionResponse(BaseModel):
    user_id: int
    username: str
    full_name: str
    role: str
    session_id: str
    login_at: datetime
    last_active_at: datetime
    ip_address: Optional[str]
    user_agent: Optional[str]
    location: Optional[str]


# ── Activity Log Schemas ──────────────────────────────────────

class ActivityLogResponse(BaseModel):
    id: int
    user_id: int
    username: Optional[str]
    full_name: Optional[str]
    action: str
    resource_type: Optional[str]
    resource_id: Optional[int]
    description: str
    ip_address: Optional[str]
    user_agent: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True


# ── Export Audit Log ──────────────────────────────────────────

class ExportLogResponse(BaseModel):
    id: int
    user_id: int
    username: Optional[str]
    full_name: Optional[str]
    export_type: str
    module: str
    record_count: Optional[int]
    file_name: Optional[str]
    ip_address: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True


# ── System Settings ───────────────────────────────────────────

class SystemSettings(BaseModel):
    company_name: str = "My Wholesale Company"
    company_gstin: str = "29AAAAA0000A1Z5"
    company_address: str = "123 Main Street"
    company_city: str = "Bangalore"
    company_state: str = "Karnataka"
    company_state_code: int = 29
    company_pincode: str = "560001"
    company_phone: str = "9999999999"
    company_email: str = "info@company.com"
    financial_year_start: str = "April"
    currency_symbol: str = "₹"
    invoice_prefix_b2b: str = "BINV"
    invoice_prefix_b2c: str = "CINV"
    invoice_prefix_quotation: str = "QT"
    invoice_prefix_challan: str = "DC"
    invoice_prefix_credit_note: str = "CN"
    eway_bill_threshold: float = 50000.0
    expense_approval_threshold: float = 5000.0
    drawing_power_margin_pct: float = 25.0
    cleartax_sandbox: bool = True
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_use_tls: bool = True
    backup_retention_days: int = 30
