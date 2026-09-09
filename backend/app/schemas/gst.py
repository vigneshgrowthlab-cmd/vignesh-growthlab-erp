from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime, date
from decimal import Decimal


# ── Transporter & Vehicle Schemas ─────────────────────────────

class TransporterCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    gstin: Optional[str] = None
    contact_person: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None


class TransporterUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    gstin: Optional[str] = None
    contact_person: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None


class TransporterResponse(TransporterCreate):
    id: int
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True


class VehicleCreate(BaseModel):
    vehicle_number: str = Field(..., min_length=1, max_length=20)
    # vehicle_type is a free-text label used for display only (Truck, Mini Truck,
    # Van, Tempo, Bike, Auto, Car, Other, ...). No backend logic branches on it,
    # so a strict regex over-restricted the UI dropdown.
    vehicle_type: str = Field(..., min_length=1, max_length=20)
    owner_name: Optional[str] = None
    transporter_id: Optional[int] = None


class VehicleUpdate(BaseModel):
    vehicle_number: Optional[str] = Field(None, min_length=1, max_length=20)
    vehicle_type: Optional[str] = Field(None, min_length=1, max_length=20)
    owner_name: Optional[str] = None
    transporter_id: Optional[int] = None


class VehicleResponse(VehicleCreate):
    id: int
    is_active: bool
    transporter_name: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


# ── E-Invoice Schemas ─────────────────────────────────────────

class EInvoiceGenerateRequest(BaseModel):
    invoice_id: int


class EInvoiceCancelRequest(BaseModel):
    invoice_id: int
    cancel_reason: str = Field(..., min_length=1, max_length=200)
    cancel_remark: Optional[str] = None


class EInvoiceResponse(BaseModel):
    invoice_id: int
    invoice_number: str
    irn: Optional[str]
    irn_status: Optional[str]
    qr_code: Optional[str]
    signed_invoice: Optional[str]
    ack_number: Optional[str]
    ack_date: Optional[str]
    error_message: Optional[str]


# ── E-Way Bill Schemas ────────────────────────────────────────

class EWayBillGenerateRequest(BaseModel):
    invoice_id: int
    transporter_id: Optional[int] = None
    vehicle_id: Optional[int] = None
    vehicle_number: Optional[str] = None
    transporter_name: Optional[str] = None
    transport_mode: str = Field("road", pattern="^(road|rail|air|ship)$")
    distance_km: Optional[int] = None


class EWayBillResponse(BaseModel):
    invoice_id: int
    invoice_number: str
    eway_bill_number: Optional[str]
    eway_bill_date: Optional[str]
    valid_upto: Optional[str]
    error_message: Optional[str]


# ── GSTR Schemas ──────────────────────────────────────────────

class GSTR1B2BInvoice(BaseModel):
    invoice_number: str
    invoice_date: date
    customer_gstin: str
    customer_name: str
    invoice_value: Decimal
    taxable_value: Decimal
    igst: Decimal
    cgst: Decimal
    sgst: Decimal
    irn: Optional[str]


class GSTR1B2CInvoice(BaseModel):
    invoice_number: str
    invoice_date: date
    state: Optional[str]
    invoice_value: Decimal
    taxable_value: Decimal
    igst: Decimal
    cgst: Decimal
    sgst: Decimal


class GSTR1HSNEntry(BaseModel):
    hsn_code: str
    description: Optional[str]
    uom: str
    total_quantity: Decimal
    taxable_value: Decimal
    igst: Decimal
    cgst: Decimal
    sgst: Decimal
    gst_rate: Decimal


class GSTR1Summary(BaseModel):
    period: str
    financial_year: str
    b2b_invoices: List[GSTR1B2BInvoice] = []
    b2c_invoices: List[GSTR1B2CInvoice] = []
    b2cl_invoices: List[dict] = []
    b2cs_summary: List[dict] = []
    hsn_summary: List[GSTR1HSNEntry] = []
    credit_notes: List[dict] = []
    total_taxable: Decimal
    total_igst: Decimal
    total_cgst: Decimal
    total_sgst: Decimal
    total_tax: Decimal
    invoice_count: int
    b2b_count: int
    b2c_count: int
    b2cl_count: int = 0
    b2cs_count: int = 0
    b2cl_threshold: Optional[Decimal] = None
    credit_note_count: int = 0


class GSTR2BImportEntry(BaseModel):
    supplier_gstin: str
    supplier_name: str
    invoice_number: str
    invoice_date: date
    invoice_value: Decimal
    taxable_value: Decimal
    igst: Decimal
    cgst: Decimal
    sgst: Decimal


class GSTR2BImport(BaseModel):
    financial_year: str
    period: str
    entries: List[GSTR2BImportEntry]


class GSTR2BReconciliation(BaseModel):
    period: str
    financial_year: str
    matched: List[dict] = []
    unmatched_in_gstr2b: List[dict] = []
    unmatched_in_books: List[dict] = []
    matched_count: int
    unmatched_gstr2b_count: int
    unmatched_books_count: int
    total_itc_available: Decimal
    total_itc_claimed: Decimal
    itc_at_risk: Decimal


class GSTR3BSummary(BaseModel):
    period: str
    financial_year: str
    output_igst: Decimal
    output_cgst: Decimal
    output_sgst: Decimal
    total_output_tax: Decimal
    itc_igst: Decimal
    itc_cgst: Decimal
    itc_sgst: Decimal
    total_itc: Decimal
    net_tax_payable: Decimal
    net_igst_payable: Decimal
    net_cgst_payable: Decimal
    net_sgst_payable: Decimal
