from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime, date
from decimal import Decimal


# ── Warehouse Schemas ─────────────────────────────────────────

class WarehouseBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    # Server-generated on create; any client-supplied value is ignored.
    code: Optional[str] = Field(None, max_length=20)
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    pincode: Optional[str] = None
    contact_person: Optional[str] = None
    phone: Optional[str] = None
    is_default: bool = False


class WarehouseCreate(WarehouseBase):
    pass


class WarehouseUpdate(BaseModel):
    name: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    pincode: Optional[str] = None
    contact_person: Optional[str] = None
    phone: Optional[str] = None
    is_default: Optional[bool] = None
    is_active: Optional[bool] = None


class WarehouseResponse(WarehouseBase):
    id: int
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True


# ── Stock Transfer Schemas ────────────────────────────────────

class StockTransferCreate(BaseModel):
    source_warehouse_id: int
    destination_warehouse_id: int
    product_id: int
    quantity: Decimal = Field(..., gt=0)
    transfer_date: date
    notes: Optional[str] = None
    dc_number: Optional[str] = None  # legacy text field
    dc_ids: Optional[List[int]] = None  # linked DC invoice IDs


class StockTransferResponse(BaseModel):
    id: int
    transfer_number: str
    source_warehouse_id: int
    source_warehouse_name: Optional[str] = None
    destination_warehouse_id: int
    destination_warehouse_name: Optional[str] = None
    product_id: int
    part_code: Optional[str] = None
    part_name: Optional[str] = None
    quantity: Decimal
    transfer_date: date
    notes: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True


# ── Stock Adjustment Schemas ──────────────────────────────────

class StockAdjustmentCreate(BaseModel):
    warehouse_id: int
    product_id: int
    adjustment_type: str = Field(..., pattern="^(in|out)$")
    quantity: Decimal = Field(..., gt=0)
    reason: str = Field(..., min_length=3, max_length=500)
    adjustment_date: date
    unit_cost: Optional[Decimal] = None
    notes: Optional[str] = None


class StockAdjustmentResponse(BaseModel):
    id: int
    adjustment_number: str
    warehouse_id: int
    warehouse_name: Optional[str] = None
    product_id: int
    part_code: Optional[str] = None
    part_name: Optional[str] = None
    adjustment_type: str
    quantity: Decimal
    reason: str
    adjustment_date: date
    unit_cost: Optional[Decimal]
    notes: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True


# ── Stock Write-off Schemas ───────────────────────────────────

class StockWriteoffCreate(BaseModel):
    warehouse_id: int
    product_id: int
    quantity: Decimal = Field(..., gt=0)
    reason_type: str = Field(..., pattern="^(damaged|expired|theft|shortage|other)$")
    reason_detail: str = Field(..., min_length=3, max_length=500)
    writeoff_date: date
    notes: Optional[str] = None


class StockWriteoffApprove(BaseModel):
    approved: bool
    admin_notes: Optional[str] = None


class StockWriteoffResponse(BaseModel):
    id: int
    writeoff_number: str
    warehouse_id: int
    warehouse_name: Optional[str] = None
    product_id: int
    part_code: Optional[str] = None
    part_name: Optional[str] = None
    quantity: Decimal
    reason_type: str
    reason_detail: str
    writeoff_date: date
    status: str
    admin_notes: Optional[str]
    notes: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True


# ── Opening Balance Schemas ───────────────────────────────────

class OpeningStockItem(BaseModel):
    product_id: int
    warehouse_id: int
    quantity: Decimal = Field(..., gt=0)
    unit_cost: Decimal = Field(..., gt=0)
    opening_date: date


class OpeningCustomerBalance(BaseModel):
    customer_id: int
    opening_balance: Decimal = Field(..., gt=0)
    opening_date: date
    notes: Optional[str] = None


class OpeningVendorBalance(BaseModel):
    vendor_id: int
    opening_balance: Decimal = Field(..., gt=0)
    opening_date: date
    notes: Optional[str] = None


class OpeningCashBalance(BaseModel):
    amount: Decimal = Field(..., ge=0)
    opening_date: date
    notes: Optional[str] = None


class OpeningBankBalance(BaseModel):
    account_code: str
    bank_name: str
    account_number: str
    amount: Decimal = Field(..., ge=0)
    opening_date: date
    notes: Optional[str] = None


class OpeningBalanceCreate(BaseModel):
    financial_year: str
    opening_date: date
    stock_items: List[OpeningStockItem] = []
    customer_balances: List[OpeningCustomerBalance] = []
    vendor_balances: List[OpeningVendorBalance] = []
    cash_balance: Optional[OpeningCashBalance] = None
    bank_balances: List[OpeningBankBalance] = []


# ── Stock Report Schemas ──────────────────────────────────────

class StockSummaryItem(BaseModel):
    product_id: int
    part_code: str
    part_name: str
    category_name: Optional[str]
    unit_of_measure: str
    total_quantity: Decimal
    warehouse_breakdown: List[dict] = []
    fifo_value: Decimal
    last_purchase_date: Optional[date]
    low_stock_threshold: Decimal
    is_low_stock: bool


class StockAgeingItem(BaseModel):
    product_id: int
    part_code: str
    part_name: str
    warehouse_name: str
    batch_date: date
    quantity: Decimal
    unit_cost: Decimal
    value: Decimal
    age_days: int
    age_bucket: str
