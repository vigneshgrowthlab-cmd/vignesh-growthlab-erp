import re
from pydantic import BaseModel, Field, field_validator, model_validator
from typing import Optional, List
from datetime import datetime, date
from decimal import Decimal
from app.models.models import GSTType, PaymentMode


GSTIN_PATTERN = re.compile(r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]$")


def _validate_gstin(v: Optional[str]) -> Optional[str]:
    if v in (None, ""):
        return v
    v = v.strip().upper()
    if not GSTIN_PATTERN.match(v):
        raise ValueError("Invalid GSTIN format (expected 15 chars: 2-digit state + 10-char PAN + entity + 'Z' + checksum)")
    return v


# ── Vendor Schemas ───────────────────────────────────────────

class VendorAddressBase(BaseModel):
    label: str = Field(..., max_length=50)
    address_line1: str = Field(..., max_length=200)
    address_line2: Optional[str] = None
    city: str = Field(..., max_length=50)
    state: str = Field(..., max_length=50)
    state_code: Optional[int] = None
    pincode: str = Field(..., min_length=4, max_length=6)
    contact_person: Optional[str] = None
    phone: Optional[str] = None
    address_type: str = "both"
    is_preferred: bool = False


class VendorAddressCreate(VendorAddressBase):
    pass


class VendorAddressResponse(VendorAddressBase):
    id: int
    vendor_id: int

    class Config:
        from_attributes = True


class VendorBase(BaseModel):
    trade_name: str = Field(..., min_length=1, max_length=200)
    legal_name: Optional[str] = None
    gstin: Optional[str] = Field(None, max_length=15)
    business_type: Optional[str] = None
    gst_status: Optional[str] = None
    state: Optional[str] = None
    state_code: Optional[int] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    contact_person: Optional[str] = None
    bank_name: Optional[str] = None
    bank_account: Optional[str] = None
    bank_ifsc: Optional[str] = None
    credit_days: int = 0

    @field_validator("gstin")
    @classmethod
    def _check_gstin(cls, v: Optional[str]) -> Optional[str]:
        return _validate_gstin(v)


class VendorCreate(VendorBase):
    pass


class VendorUpdate(BaseModel):
    trade_name: Optional[str] = None
    legal_name: Optional[str] = None
    gstin: Optional[str] = Field(None, max_length=15)
    state: Optional[str] = None
    state_code: Optional[int] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    contact_person: Optional[str] = None
    bank_name: Optional[str] = None
    bank_account: Optional[str] = None
    bank_ifsc: Optional[str] = None
    credit_days: Optional[int] = None
    gst_status: Optional[str] = None
    is_active: Optional[bool] = None

    @field_validator("gstin")
    @classmethod
    def _check_gstin(cls, v: Optional[str]) -> Optional[str]:
        return _validate_gstin(v)


class VendorResponse(VendorBase):
    id: int
    is_active: bool
    created_at: datetime
    addresses: List[VendorAddressResponse] = []
    outstanding_balance: Optional[Decimal] = Decimal("0")

    class Config:
        from_attributes = True


class VendorListResponse(BaseModel):
    id: int
    trade_name: str
    gstin: Optional[str]
    state: Optional[str]
    phone: Optional[str]
    is_active: bool
    outstanding_balance: Optional[Decimal] = Decimal("0")

    class Config:
        from_attributes = True


# ── Purchase Item Schemas ─────────────────────────────────────

class PurchaseItemCreate(BaseModel):
    product_id: int
    quantity: Decimal = Field(..., gt=0)
    unit_cost: Decimal = Field(..., gt=0)
    gst_percent: Decimal = Field(..., ge=0, le=100)
    hsn_code: str = Field(..., min_length=4, max_length=8)


class PurchaseItemResponse(BaseModel):
    id: int
    product_id: int
    part_code: Optional[str] = None
    part_name: Optional[str] = None
    quantity: Decimal
    unit_cost: Decimal
    gst_percent: Decimal
    cgst_amount: Decimal
    sgst_amount: Decimal
    igst_amount: Decimal
    line_total: Decimal
    hsn_code: str

    class Config:
        from_attributes = True


# ── Purchase Schemas ─────────────────────────────────────────

class PurchaseCreate(BaseModel):
    vendor_id: int
    warehouse_id: int
    vendor_invoice_number: str = Field(..., min_length=1, max_length=50)
    invoice_date: date
    received_date: Optional[date] = None
    payment_due_date: Optional[date] = None
    notes: Optional[str] = None
    items: List[PurchaseItemCreate] = Field(..., min_items=1)

    @model_validator(mode="after")
    def _check_dates(self):
        if self.received_date and self.received_date < self.invoice_date:
            raise ValueError("received_date cannot be earlier than invoice_date")
        if self.payment_due_date and self.payment_due_date < self.invoice_date:
            raise ValueError("payment_due_date cannot be earlier than invoice_date")
        return self


class PurchaseUpdate(BaseModel):
    notes: Optional[str] = None
    received_date: Optional[date] = None
    payment_due_date: Optional[date] = None


class PurchaseResponse(BaseModel):
    id: int
    vendor_id: int
    vendor_name: Optional[str] = None
    warehouse_id: int
    warehouse_name: Optional[str] = None
    vendor_invoice_number: str
    invoice_date: date
    received_date: Optional[date]
    payment_due_date: Optional[date]
    subtotal: Decimal
    total_cgst: Decimal
    total_sgst: Decimal
    total_igst: Decimal
    total_amount: Decimal
    gst_type: str
    notes: Optional[str]
    financial_year: str
    is_cancelled: bool
    created_at: datetime
    items: List[PurchaseItemResponse] = []

    class Config:
        from_attributes = True


class PurchaseListResponse(BaseModel):
    id: int
    vendor_name: Optional[str] = None
    warehouse_name: Optional[str] = None
    vendor_invoice_number: str
    invoice_date: date
    total_amount: Decimal
    gst_type: str
    financial_year: str
    is_cancelled: bool
    created_at: datetime

    class Config:
        from_attributes = True


# ── Vendor Payment Schemas ───────────────────────────────────

class VendorPaymentCreate(BaseModel):
    vendor_id: int
    purchase_id: Optional[int] = None
    payment_date: date
    amount: Decimal = Field(..., gt=0)
    payment_mode: PaymentMode
    reference_number: Optional[str] = None
    notes: Optional[str] = None
    is_advance: bool = False


class VendorPaymentResponse(BaseModel):
    id: int
    payment_number: str
    vendor_id: int
    vendor_name: Optional[str] = None
    purchase_id: Optional[int]
    payment_date: date
    amount: Decimal
    payment_mode: str
    reference_number: Optional[str]
    notes: Optional[str]
    is_advance: bool
    financial_year: str
    created_at: datetime

    class Config:
        from_attributes = True
