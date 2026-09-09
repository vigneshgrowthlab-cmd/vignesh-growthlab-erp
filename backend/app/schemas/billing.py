from pydantic import BaseModel, Field, EmailStr, field_validator
from typing import Optional, List
from datetime import datetime, date
from decimal import Decimal
from app.models.models import DocumentType, GSTType, PaymentMode
from app.schemas.products import _validate_hsn  # reuse 4/6/8-digit HSN rule


# ── Customer Address Schemas ─────────────────────────────────

class CustomerAddressBase(BaseModel):
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
    is_preferred_billing: bool = False
    is_preferred_shipping: bool = False


class CustomerAddressCreate(CustomerAddressBase):
    pass


class CustomerAddressResponse(CustomerAddressBase):
    id: int
    customer_id: int

    class Config:
        from_attributes = True


# ── Customer Schemas ──────────────────────────────────────────

class CustomerBase(BaseModel):
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
    credit_limit: Decimal = Decimal("0")
    credit_days: int = 0
    is_b2b: bool = True


class CustomerCreate(CustomerBase):
    pass


class CustomerUpdate(BaseModel):
    trade_name: Optional[str] = None
    legal_name: Optional[str] = None
    gstin: Optional[str] = Field(None, max_length=15)
    business_type: Optional[str] = None
    state: Optional[str] = None
    state_code: Optional[int] = None
    is_b2b: Optional[bool] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    contact_person: Optional[str] = None
    credit_limit: Optional[Decimal] = None
    credit_days: Optional[int] = None
    gst_status: Optional[str] = None
    is_active: Optional[bool] = None


class CustomerBulkStatus(BaseModel):
    customer_ids: List[int] = Field(..., min_length=1)
    is_active: bool


class CustomerResponse(CustomerBase):
    id: int
    is_active: bool
    created_at: datetime
    addresses: List[CustomerAddressResponse] = []
    outstanding_balance: Optional[Decimal] = Decimal("0")

    class Config:
        from_attributes = True


class CustomerListResponse(BaseModel):
    id: int
    trade_name: str
    gstin: Optional[str]
    state: Optional[str]
    phone: Optional[str]
    credit_limit: Decimal
    is_active: bool
    outstanding_balance: Optional[Decimal] = Decimal("0")
    is_b2b: bool

    class Config:
        from_attributes = True


# ── Invoice Item Schemas ──────────────────────────────────────

class InvoiceItemCreate(BaseModel):
    product_id: int
    quantity: Decimal = Field(..., gt=0)
    unit_price: Decimal = Field(Decimal("0"), ge=0)
    discount_percent: Decimal = Field(Decimal("0"), ge=0, le=100)
    gst_percent: Decimal = Field(Decimal("0"), ge=0, le=100)
    hsn_code: Optional[str] = None
    notes: Optional[str] = None

    @field_validator("hsn_code")
    @classmethod
    def _check_hsn(cls, v: Optional[str]) -> Optional[str]:
        return _validate_hsn(v)


class InvoiceItemResponse(BaseModel):
    id: int
    product_id: int
    part_code: Optional[str] = None
    part_name: Optional[str] = None
    quantity: Decimal
    unit_price: Decimal
    discount_percent: Decimal
    discount_amount: Decimal
    taxable_amount: Decimal
    gst_percent: Decimal
    cgst_percent: Decimal
    sgst_percent: Decimal
    igst_percent: Decimal
    cgst_amount: Decimal
    sgst_amount: Decimal
    igst_amount: Decimal
    line_total: Decimal
    hsn_code: str
    fifo_cost: Optional[Decimal]

    class Config:
        from_attributes = True


# ── Invoice Schemas ───────────────────────────────────────────

class InvoiceCreate(BaseModel):
    document_type: str
    customer_id: Optional[int] = None  # optional for DC
    warehouse_id: int
    vehicle_id: Optional[int] = None
    vehicle_number: Optional[str] = None
    driver_name: Optional[str] = None
    lr_number: Optional[str] = None
    dc_destination_warehouse_id: Optional[int] = None
    transporter_id: Optional[int] = None
    transporter_name: Optional[str] = None
    show_transport_on_print: Optional[bool] = None
    billing_address_id: Optional[int] = None
    shipping_address_id: Optional[int] = None
    invoice_date: date
    due_date: Optional[date] = None
    invoice_discount: Decimal = Field(Decimal("0"), ge=0)
    terms_conditions: Optional[str] = None
    notes: Optional[str] = None
    items: List[InvoiceItemCreate] = Field(..., min_length=1)


class InvoiceResponse(BaseModel):
    id: int
    invoice_number: str
    document_type: str
    customer_id: int
    customer_name: Optional[str] = None
    customer_gstin: Optional[str] = None
    warehouse_id: int
    warehouse_name: Optional[str] = None
    billing_address_id: int
    shipping_address_id: int
    billing_address: Optional[dict] = None
    shipping_address: Optional[dict] = None
    invoice_date: date
    due_date: Optional[date]
    subtotal: Decimal
    item_discount: Decimal
    invoice_discount: Decimal
    taxable_amount: Decimal
    total_cgst: Decimal
    total_sgst: Decimal
    total_igst: Decimal
    round_off: Decimal = Decimal("0")
    total_amount: Decimal
    paid_amount: Decimal
    outstanding_amount: Decimal
    credited_amount: Decimal = Decimal("0")
    gst_type: str
    terms_conditions: Optional[str]
    notes: Optional[str]
    financial_year: str
    is_cancelled: bool
    cancelled_reason: Optional[str]
    irn: Optional[str]
    irn_status: Optional[str]
    eway_bill_number: Optional[str]
    salesperson_id: Optional[int]
    salesperson_name: Optional[str]
    transporter_id: Optional[int] = None
    transporter_name: Optional[str] = None
    vehicle_number: Optional[str] = None
    lr_number: Optional[str] = None
    show_transport_on_print: Optional[bool] = None
    created_at: datetime
    items: List[InvoiceItemResponse] = []

    class Config:
        from_attributes = True


class InvoiceListResponse(BaseModel):
    id: int
    invoice_number: str
    document_type: str
    customer_name: Optional[str] = None
    invoice_date: date
    due_date: Optional[date]
    total_amount: Decimal
    paid_amount: Decimal
    outstanding_amount: Decimal
    credited_amount: Decimal = Decimal("0")
    gst_type: str
    is_cancelled: bool
    irn_status: Optional[str]
    financial_year: str
    salesperson_name: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True


# ── Customer Payment Schemas ──────────────────────────────────

class CustomerPaymentCreate(BaseModel):
    customer_id: int
    invoice_id: Optional[int] = None
    payment_date: date
    amount: Decimal = Field(..., gt=0)
    payment_mode: str = "cash"
    reference_number: Optional[str] = None
    tds_amount: Decimal = Field(Decimal("0"), ge=0)
    notes: Optional[str] = None
    is_advance: bool = False


class CustomerPaymentResponse(BaseModel):
    id: int
    payment_number: str
    customer_id: int
    customer_name: Optional[str] = None
    invoice_id: Optional[int]
    payment_date: date
    amount: Decimal
    tds_amount: Decimal
    payment_mode: str
    reference_number: Optional[str]
    is_advance: bool
    financial_year: str
    created_at: datetime

    class Config:
        from_attributes = True


# ── Return / Credit Note ──────────────────────────────────────

class ReturnItemCreate(BaseModel):
    invoice_item_id: int
    quantity: Decimal = Field(..., gt=0)
    reason: Optional[str] = None


class CreditNoteCreate(BaseModel):
    original_invoice_id: int
    return_date: date
    items: List[ReturnItemCreate]
    notes: Optional[str] = None
