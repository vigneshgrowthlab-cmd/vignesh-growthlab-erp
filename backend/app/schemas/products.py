"""Product schemas."""
from pydantic import BaseModel, Field, field_validator
from typing import Optional
from decimal import Decimal
from datetime import date


# Indian HSN codes are 2, 4, 6, or 8 digits depending on turnover band.
# This project accepts 4 / 6 / 8 (2-digit chapter level not used here).
ALLOWED_HSN_LENGTHS = (4, 6, 8)


def _validate_hsn(v: Optional[str]) -> Optional[str]:
    if v is None or v == "":
        return None
    v = v.strip()
    if not v.isdigit() or len(v) not in ALLOWED_HSN_LENGTHS:
        raise ValueError(
            f"hsn_code must be {'/'.join(str(n) for n in ALLOWED_HSN_LENGTHS)} digits, numeric only"
        )
    return v


def _validate_hsn_required(v: Optional[str]) -> str:
    v = _validate_hsn(v)
    if v is None:
        raise ValueError("hsn_code is required")
    return v


class CategoryCreate(BaseModel):
    name: str
    prefix: str = Field(..., min_length=1, max_length=10)
    default_hsn: Optional[str] = Field(None, max_length=8)
    default_gst_percent: Optional[Decimal] = Field(Decimal("18"), ge=0, le=100)
    description: Optional[str] = None

    @field_validator("prefix")
    @classmethod
    def _upper_prefix(cls, v: str) -> str:
        return v.strip().upper() if v else v

    @field_validator("default_hsn")
    @classmethod
    def _check_hsn(cls, v: Optional[str]) -> Optional[str]:
        return _validate_hsn(v)


class CategoryUpdate(BaseModel):
    name: Optional[str] = None
    prefix: Optional[str] = Field(None, min_length=1, max_length=10)
    default_hsn: Optional[str] = Field(None, max_length=8)
    default_gst_percent: Optional[Decimal] = Field(None, ge=0, le=100)
    description: Optional[str] = None
    is_active: Optional[bool] = None

    @field_validator("prefix")
    @classmethod
    def _upper_prefix(cls, v: Optional[str]) -> Optional[str]:
        return v.strip().upper() if v else v

    @field_validator("default_hsn")
    @classmethod
    def _check_hsn(cls, v: Optional[str]) -> Optional[str]:
        return _validate_hsn(v)


class ProductCreate(BaseModel):
    part_name: str
    category_id: int
    hsn_code: str
    gst_percent: Decimal = Field(Decimal("18"), ge=0, le=100)
    purchase_cost: Decimal = Field(Decimal("0"), ge=0)
    b2b_price: Decimal = Field(Decimal("0"), ge=0)
    b2c_price: Decimal = Field(Decimal("0"), ge=0)
    mrp: Decimal = Field(Decimal("0"), ge=0)
    floor_price: Decimal = Field(Decimal("0"), ge=0)
    unit_of_measure: str = "Nos"
    low_stock_threshold: Decimal = Field(Decimal("0"), ge=0)
    description: Optional[str] = None
    # None -> service fills the effective default from config
    # (business.cost_alert_pct / business.min_margin_pct)
    cost_alert_threshold_pct: Optional[Decimal] = Field(None, ge=0)
    min_margin_pct: Optional[Decimal] = Field(None, ge=0)

    @field_validator("hsn_code")
    @classmethod
    def _check_hsn(cls, v: str) -> str:
        return _validate_hsn_required(v)


class ProductUpdate(BaseModel):
    part_name: Optional[str] = None
    category_id: Optional[int] = None
    hsn_code: Optional[str] = None
    gst_percent: Optional[Decimal] = None
    purchase_cost: Optional[Decimal] = None
    b2b_price: Optional[Decimal] = None
    b2c_price: Optional[Decimal] = None
    mrp: Optional[Decimal] = None
    floor_price: Optional[Decimal] = None
    unit_of_measure: Optional[str] = None
    low_stock_threshold: Optional[Decimal] = None
    description: Optional[str] = None
    cost_alert_threshold_pct: Optional[Decimal] = None
    min_margin_pct: Optional[Decimal] = None
    is_active: Optional[bool] = None

    @field_validator("hsn_code")
    @classmethod
    def _check_hsn(cls, v: Optional[str]) -> Optional[str]:
        return _validate_hsn(v)


class StockAdjustmentCreate(BaseModel):
    product_id: int
    warehouse_id: int
    adjustment_type: str = Field(..., pattern="^(in|out)$")
    quantity: Decimal = Field(..., gt=0)
    unit_cost: Optional[Decimal] = Field(None, ge=0)
    reason: Optional[str] = None
    adjustment_date: Optional[date] = None
    notes: Optional[str] = None


class AlertApproveRequest(BaseModel):
    approve: bool
    reason: Optional[str] = None


class BulkPriceUpdate(BaseModel):
    """Bulk update prices for multiple products."""
    product_ids: list
    price_type: str  # b2b_price | b2c_price | mrp | purchase_cost
    price: Decimal = Field(..., ge=0)
    effective_from: Optional[date] = None
    change_reason: Optional[str] = None