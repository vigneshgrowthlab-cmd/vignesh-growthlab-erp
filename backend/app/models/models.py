from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, Text, Boolean, DateTime, Date,
    Numeric, ForeignKey, Enum, SmallInteger, BigInteger, Index, UniqueConstraint
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.db.session import Base
import enum


# ─── Enums ──────────────────────────────────────────────────

class UserRole(str, enum.Enum):
    super_admin = "super_admin"
    admin = "admin"
    accountant = "accountant"
    sales = "sales"

class DocumentType(str, enum.Enum):
    b2b_invoice = "b2b_invoice"
    b2c_invoice = "b2c_invoice"
    quotation = "quotation"
    delivery_challan = "delivery_challan"
    credit_note = "credit_note"

class PaymentMode(str, enum.Enum):
    cash = "cash"
    bank = "bank"
    cheque = "cheque"
    upi = "upi"
    neft = "neft"
    rtgs = "rtgs"

class TransactionType(str, enum.Enum):
    debit = "debit"
    credit = "credit"

class GSTType(str, enum.Enum):
    cgst_sgst = "cgst_sgst"
    igst = "igst"

class EInvoiceStatus(str, enum.Enum):
    pending = "pending"
    generated = "generated"
    cancelled = "cancelled"
    failed = "failed"

class EWayBillStatus(str, enum.Enum):
    pending = "pending"
    generated = "generated"
    cancelled = "cancelled"
    failed = "failed"

class StockTransactionType(str, enum.Enum):
    purchase = "purchase"
    sale = "sale"
    return_in = "return_in"
    return_out = "return_out"
    transfer_in = "transfer_in"
    transfer_out = "transfer_out"
    adjustment_in = "adjustment_in"
    adjustment_out = "adjustment_out"


class ChequeStatus(str, enum.Enum):
    received    = "received"
    deposited   = "deposited"
    cleared     = "cleared"
    bounced     = "bounced"
    pdc_pending = "pdc_pending"


class WriteoffStatus(str, enum.Enum):
    pending  = "pending"
    approved = "approved"
    rejected = "rejected"


class ExpenseStatus(str, enum.Enum):
    pending_approval = "pending_approval"
    approved         = "approved"
    rejected         = "rejected"


class CashClosingStatus(str, enum.Enum):
    draft    = "draft"
    approved = "approved"


class AddressType(str, enum.Enum):
    billing = "billing"
    shipping = "shipping"
    both = "both"

class AlertType(str, enum.Enum):
    cost_rise = "cost_rise"
    low_margin = "low_margin"
    low_stock = "low_stock"


# ─── Mixins ─────────────────────────────────────────────────

class TimestampMixin:
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)
    created_by = Column(Integer, nullable=True)
    updated_by = Column(Integer, nullable=True)


# ─── Users & Auth ───────────────────────────────────────────

class User(Base, TimestampMixin):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, nullable=False, index=True)
    email = Column(String(100), unique=True, nullable=False)
    full_name = Column(String(100), nullable=False)
    hashed_password = Column(String(255), nullable=False)
    role = Column(String(30), nullable=False, default='sales')
    warehouse_id = Column(Integer, ForeignKey("warehouses.id"), nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    is_locked = Column(Boolean, default=False, nullable=False)
    locked_until = Column(DateTime, nullable=True)
    failed_login_count = Column(Integer, default=0, nullable=False)
    two_fa_enabled = Column(Boolean, default=False, nullable=False)
    two_fa_secret = Column(String(32), nullable=True)
    last_login = Column(DateTime, nullable=True)
    refresh_token = Column(Text, nullable=True)
    page_permissions = Column(Text, nullable=True)  # JSON list[str] or NULL=full access

    activity_logs = relationship("ActivityLog", back_populates="user", foreign_keys="ActivityLog.user_id")
    active_sessions = relationship("ActiveSession", back_populates="user")
    login_history = relationship("LoginHistory", back_populates="user")
    admin_warehouses = relationship(
        "UserWarehouse", foreign_keys="UserWarehouse.user_id", cascade="all, delete-orphan"
    )


class ActiveSession(Base):
    __tablename__ = "active_sessions"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    ip_address = Column(String(45), nullable=True)
    device_info = Column(String(200), nullable=True)
    location = Column(String(100), nullable=True)
    token_hash = Column(String(255), nullable=True)
    refresh_token_hash = Column(String(64), nullable=True)
    login_time = Column(DateTime, nullable=True)
    last_seen = Column(DateTime, nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)

    user = relationship("User", back_populates="active_sessions")


class ActivityLog(Base):
    __tablename__ = "activity_logs"
    id = Column(BigInteger, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    action = Column(String(100), nullable=True)
    module = Column(String(50), nullable=True)
    record_id = Column(Integer, nullable=True)
    record_type = Column(String(50), nullable=True)
    resource_id = Column(Integer, nullable=True)
    resource_type = Column(String(50), nullable=True)
    details = Column(Text, nullable=True)
    old_values = Column(Text, nullable=True)
    new_values = Column(Text, nullable=True)
    ip_address = Column(String(45), nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)

    user = relationship("User", back_populates="activity_logs", foreign_keys=[user_id])


class LoginHistory(Base):
    __tablename__ = "login_history"
    id = Column(BigInteger, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    username = Column(String(50), nullable=False, index=True)
    full_name = Column(String(100), nullable=True)
    login_at = Column(DateTime, nullable=False, server_default=func.now())
    logout_at = Column(DateTime, nullable=True)
    session_duration_seconds = Column(Integer, nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)

    user = relationship("User", back_populates="login_history")


class UserWarehouse(Base):
    """Admin users can be assigned to 1..N warehouses (min 1, max all).
    warehouse-role users continue to use User.warehouse_id (single FK)."""
    __tablename__ = "user_warehouses"
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    warehouse_id = Column(Integer, ForeignKey("warehouses.id", ondelete="CASCADE"), primary_key=True)
    assigned_at = Column(DateTime, server_default=func.now())
    assigned_by = Column(Integer, ForeignKey("users.id"), nullable=True)

    user = relationship("User", foreign_keys=[user_id], back_populates="admin_warehouses")
    warehouse = relationship("Warehouse", foreign_keys=[warehouse_id])


# ─── Categories ─────────────────────────────────────────────

class Category(Base, TimestampMixin):
    __tablename__ = "categories"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    prefix = Column(String(10), unique=True, nullable=False)
    default_hsn = Column(String(8), nullable=True)
    default_gst_percent = Column(Numeric(5, 2), nullable=True)
    description = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    sequence_counter = Column(Integer, default=0, nullable=False)

    products = relationship("Product", back_populates="category")


# ─── Products ───────────────────────────────────────────────

class Product(Base, TimestampMixin):
    __tablename__ = "products"
    id = Column(Integer, primary_key=True, index=True)
    part_code = Column(String(20), unique=True, nullable=False, index=True)
    part_name = Column(String(200), nullable=False)
    category_id = Column(Integer, ForeignKey("categories.id"), nullable=False)
    hsn_code = Column(String(8), nullable=True)
    gst_percent = Column(Numeric(5, 2), nullable=True, default=18)
    purchase_cost = Column(Numeric(12, 2), nullable=False, default=0)
    b2b_price = Column(Numeric(12, 2), nullable=True, default=0)
    b2c_price = Column(Numeric(12, 2), nullable=True, default=0)
    mrp = Column(Numeric(12, 2), nullable=True, default=0)
    floor_price = Column(Numeric(12, 2), nullable=False, default=0)
    unit_of_measure = Column(String(20), nullable=False, default="Nos")
    low_stock_threshold = Column(Numeric(12, 3), default=0, nullable=False)
    description = Column(Text, nullable=True)
    image_path = Column(String(255), nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    cost_alert_threshold_pct = Column(Numeric(5, 2), default=5.00)
    min_margin_pct = Column(Numeric(5, 2), default=10.00)

    category = relationship("Category", back_populates="products")
    stock_entries = relationship("StockEntry", back_populates="product")
    warehouse_stocks = relationship("WarehouseStock", back_populates="product")
    cost_history = relationship("ProductCostHistory", back_populates="product")
    vendor_products = relationship("VendorProduct", back_populates="product")
    alerts = relationship("CostAlert", back_populates="product")

    __table_args__ = (Index("ix_product_category", "category_id"),)


class ProductCostHistory(Base):
    __tablename__ = "product_cost_history"
    id = Column(BigInteger, primary_key=True, index=True)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    vendor_id = Column(Integer, ForeignKey("vendors.id"), nullable=True)
    purchase_id = Column(Integer, ForeignKey("purchases.id"), nullable=True)
    unit_cost = Column(Numeric(12, 2), nullable=False)
    quantity = Column(Numeric(12, 3), nullable=False)
    recorded_at = Column(DateTime, server_default=func.now(), nullable=False)
    financial_year = Column(String(7), nullable=True)

    product = relationship("Product", back_populates="cost_history")
    vendor = relationship("Vendor", back_populates="cost_history")


class CostAlert(Base):
    __tablename__ = "cost_alerts"
    id = Column(Integer, primary_key=True, index=True)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    alert_type = Column(Enum(AlertType), nullable=False)
    message = Column(Text, nullable=False)
    old_value = Column(Numeric(12, 2), nullable=True)
    new_value = Column(Numeric(12, 2), nullable=True)
    suggested_price = Column(Numeric(12, 2), nullable=True)
    is_resolved = Column(Boolean, default=False)
    resolved_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    resolved_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)

    product = relationship("Product", back_populates="alerts")


# ─── Warehouses ─────────────────────────────────────────────

class Warehouse(Base, TimestampMixin):
    __tablename__ = "warehouses"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    code = Column(String(10), unique=True, nullable=False)
    address = Column(Text, nullable=True)
    city = Column(String(50), nullable=True)
    state = Column(String(50), nullable=True)
    state_code = Column(SmallInteger, nullable=True)
    pincode = Column(String(6), nullable=True)
    contact_person = Column(String(100), nullable=True)
    phone = Column(String(15), nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    is_default = Column(Boolean, default=False, nullable=False)
    use_company_bank = Column(Boolean, default=True, nullable=False)
    bank_name = Column(String(100), nullable=True)
    bank_account_number = Column(String(30), nullable=True)
    bank_ifsc = Column(String(11), nullable=True)
    bank_branch = Column(String(100), nullable=True)
    bank_account_name = Column(String(100), nullable=True)
    upi_id = Column(String(50), nullable=True)

    warehouse_stocks = relationship("WarehouseStock", back_populates="warehouse")
    stock_entries = relationship("StockEntry", back_populates="warehouse")


class WarehouseStock(Base):
    __tablename__ = "warehouse_stocks"
    id = Column(Integer, primary_key=True, index=True)
    warehouse_id = Column(Integer, ForeignKey("warehouses.id"), nullable=False)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    quantity = Column(Numeric(12, 3), default=0, nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    warehouse = relationship("Warehouse", back_populates="warehouse_stocks")
    product = relationship("Product", back_populates="warehouse_stocks")

    __table_args__ = (UniqueConstraint("warehouse_id", "product_id", name="uq_warehouse_product"),)


class StockEntry(Base):
    __tablename__ = "stock_entries"
    id = Column(BigInteger, primary_key=True, index=True)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    warehouse_id = Column(Integer, ForeignKey("warehouses.id"), nullable=False)
    transaction_type = Column(Enum(StockTransactionType), nullable=True)
    quantity = Column(Numeric(12, 3), nullable=True)
    unit_cost = Column(Numeric(12, 2), nullable=True)
    reference_type = Column(String(50), nullable=True)
    reference_id = Column(Integer, nullable=True)
    batch_date = Column(Date, nullable=True)
    entry_date = Column(Date, nullable=True)
    remaining_qty = Column(Numeric(12, 3), nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)

    product = relationship("Product", back_populates="stock_entries")
    warehouse = relationship("Warehouse", back_populates="stock_entries")

    __table_args__ = (
        Index("ix_stock_product_warehouse", "product_id", "warehouse_id"),
        Index("ix_stock_reference", "reference_type", "reference_id"),
    )


class StockTransfer(Base, TimestampMixin):
    __tablename__ = "stock_transfers"
    id = Column(Integer, primary_key=True, index=True)
    transfer_number = Column(String(30), unique=True, nullable=True)
    source_warehouse_id = Column(Integer, ForeignKey("warehouses.id"), nullable=False)
    destination_warehouse_id = Column(Integer, ForeignKey("warehouses.id"), nullable=False)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=True)
    quantity = Column(Numeric(12, 3), nullable=True)
    transfer_date = Column(Date, nullable=True)
    notes = Column(Text, nullable=True)
    dc_ids = Column(Text, nullable=True)  # JSON array of linked DC invoice IDs
    transfer_status = Column(String(20), nullable=True, default="pending")
    financial_year = Column(String(7), nullable=True)
    created_by = Column(Integer, nullable=True)

    items = relationship("StockTransferItem", back_populates="transfer")


class StockTransferItem(Base):
    __tablename__ = "stock_transfer_items"
    id = Column(Integer, primary_key=True, index=True)
    transfer_id = Column(Integer, ForeignKey("stock_transfers.id"), nullable=False)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    quantity = Column(Numeric(12, 3), nullable=False)

    transfer = relationship("StockTransfer", back_populates="items")


class StockAdjustment(Base, TimestampMixin):
    __tablename__ = "stock_adjustments"
    id = Column(Integer, primary_key=True, index=True)
    adjustment_number = Column(String(30), unique=True, nullable=True)
    warehouse_id = Column(Integer, ForeignKey("warehouses.id"), nullable=False)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    adjustment_type = Column(String(10), nullable=True)
    quantity = Column(Numeric(12, 3), nullable=False)
    unit_cost = Column(Numeric(12, 2), nullable=True)
    reason = Column(Text, nullable=True)
    notes = Column(Text, nullable=True)
    adjustment_date = Column(Date, nullable=True)


# ─── Stock Writeoff ─────────────────────────────────────────

class StockWriteoff(Base, TimestampMixin):
    __tablename__ = "stock_writeoffs"
    id = Column(Integer, primary_key=True, index=True)
    writeoff_number = Column(String(30), unique=True, nullable=True)
    warehouse_id = Column(Integer, ForeignKey("warehouses.id"), nullable=False)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    quantity = Column(Numeric(12, 3), nullable=False)
    reason_type = Column(String(30), nullable=True)
    reason_detail = Column(Text, nullable=True)
    writeoff_date = Column(Date, nullable=True)
    status = Column(String(20), default="pending", nullable=True)
    approved_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    approved_at = Column(DateTime, nullable=True)
    admin_notes = Column(Text, nullable=True)
    notes = Column(Text, nullable=True)

    warehouse = relationship("Warehouse")
    product = relationship("Product")


# ─── Accounting ──────────────────────────────────────────────

class Cheque(Base, TimestampMixin):
    __tablename__ = "cheques"
    id = Column(Integer, primary_key=True, index=True)
    cheque_number = Column(String(30), nullable=False)
    cheque_date = Column(Date, nullable=False)
    bank_name = Column(String(100), nullable=False)
    amount = Column(Numeric(12, 2), nullable=False)
    status = Column(String(20), default="received", nullable=True)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=True)
    vendor_id = Column(Integer, ForeignKey("vendors.id"), nullable=True)
    receipt_id = Column(Integer, nullable=True)
    payment_id = Column(Integer, nullable=True)
    is_pdc = Column(Boolean, default=False, nullable=False)
    deposit_date = Column(Date, nullable=True)
    clearance_date = Column(Date, nullable=True)
    bounce_date = Column(Date, nullable=True)
    bounce_reason = Column(Text, nullable=True)
    bounce_charges = Column(Numeric(10, 2), default=0)
    notes = Column(Text, nullable=True)
    bank_account_code = Column(String(20), nullable=True)

    customer = relationship("Customer")
    vendor = relationship("Vendor")


class CashClosing(Base):
    __tablename__ = "cash_closings"
    id = Column(Integer, primary_key=True, index=True)
    closing_date = Column(Date, unique=True, nullable=False)
    opening_balance = Column(Numeric(14, 2), default=0, nullable=False)
    total_receipts = Column(Numeric(14, 2), default=0, nullable=False)
    total_payments = Column(Numeric(14, 2), default=0, nullable=False)
    total_expenses = Column(Numeric(14, 2), default=0, nullable=False)
    total_deposits = Column(Numeric(14, 2), default=0, nullable=False)
    closing_balance = Column(Numeric(14, 2), default=0, nullable=False)
    status = Column(Enum(CashClosingStatus), default=CashClosingStatus.draft, nullable=False)
    approved_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    approved_at = Column(DateTime, nullable=True)
    financial_year = Column(String(7), nullable=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)


class Expense(Base, TimestampMixin):
    __tablename__ = "expenses"
    id = Column(Integer, primary_key=True, index=True)
    expense_number = Column(String(30), unique=True, nullable=True)
    expense_date = Column(Date, nullable=True)
    category = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)
    amount = Column(Numeric(12, 2), nullable=False)
    payment_mode = Column(String(20), default="cash", nullable=True)
    reference_number = Column(String(100), nullable=True)
    vendor_id = Column(Integer, ForeignKey("vendors.id"), nullable=True)
    financial_year = Column(String(7), nullable=True)
    status = Column(Enum(ExpenseStatus), default=ExpenseStatus.pending_approval, nullable=False)
    approved_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    approved_at = Column(DateTime, nullable=True)
    admin_notes = Column(Text, nullable=True)
    notes = Column(Text, nullable=True)


class TDSEntry(Base, TimestampMixin):
    __tablename__ = "tds_entries"
    id = Column(Integer, primary_key=True, index=True)
    tds_number = Column(String(30), unique=True, nullable=True)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=False)
    receipt_id = Column(Integer, nullable=True)
    deduction_date = Column(Date, nullable=True)
    invoice_amount = Column(Numeric(12, 2), nullable=False)
    tds_amount = Column(Numeric(12, 2), nullable=False)
    tds_percent = Column(Numeric(5, 2), nullable=True)
    section_code = Column(String(10), default="194C", nullable=False)
    tan_number = Column(String(10), nullable=True)
    financial_year = Column(String(7), nullable=True)
    is_reconciled = Column(Boolean, default=False, nullable=False)
    notes = Column(Text, nullable=True)

    customer = relationship("Customer")


# ─── GST Masters ─────────────────────────────────────────────

class Transporter(Base, TimestampMixin):
    __tablename__ = "transporters"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(200), nullable=False)
    gstin = Column(String(15), nullable=True)
    contact_person = Column(String(100), nullable=True)
    phone = Column(String(15), nullable=True)
    email = Column(String(100), nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)

    vehicles = relationship("Vehicle", back_populates="transporter")


class Vehicle(Base, TimestampMixin):
    __tablename__ = "vehicles"
    id = Column(Integer, primary_key=True, index=True)
    vehicle_number = Column(String(20), unique=True, nullable=False)
    vehicle_type = Column(String(20), nullable=False)
    owner_name = Column(String(100), nullable=True)
    transporter_id = Column(Integer, ForeignKey("transporters.id"), nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)

    transporter = relationship("Transporter", back_populates="vehicles")


# ─── Vendors ────────────────────────────────────────────────

class Vendor(Base, TimestampMixin):
    __tablename__ = "vendors"
    id = Column(Integer, primary_key=True, index=True)
    trade_name = Column(String(200), nullable=False)
    legal_name = Column(String(200), nullable=True)
    gstin = Column(String(15), unique=True, nullable=True, index=True)
    business_type = Column(String(50), nullable=True)
    gst_status = Column(String(20), nullable=True)
    gst_registration_date = Column(Date, nullable=True)
    nature_of_business = Column(String(100), nullable=True)
    state = Column(String(50), nullable=True)
    state_code = Column(SmallInteger, nullable=True)
    phone = Column(String(15), nullable=True)
    email = Column(String(100), nullable=True)
    contact_person = Column(String(100), nullable=True)
    bank_name = Column(String(100), nullable=True)
    bank_account = Column(String(20), nullable=True)
    bank_ifsc = Column(String(11), nullable=True)
    credit_days = Column(Integer, default=0)
    is_active = Column(Boolean, default=True, nullable=False)

    addresses = relationship("VendorAddress", back_populates="vendor")
    purchases = relationship("Purchase", back_populates="vendor")
    cost_history = relationship("ProductCostHistory", back_populates="vendor")
    vendor_products = relationship("VendorProduct", back_populates="vendor")
    ledger_entries = relationship("LedgerEntry", back_populates="vendor")


class VendorAddress(Base, TimestampMixin):
    __tablename__ = "vendor_addresses"
    id = Column(Integer, primary_key=True, index=True)
    vendor_id = Column(Integer, ForeignKey("vendors.id"), nullable=False)
    label = Column(String(50), nullable=False)
    address_line1 = Column(String(200), nullable=False)
    address_line2 = Column(String(200), nullable=True)
    city = Column(String(50), nullable=False)
    state = Column(String(50), nullable=False)
    state_code = Column(SmallInteger, nullable=True)
    pincode = Column(String(6), nullable=False)
    contact_person = Column(String(100), nullable=True)
    phone = Column(String(15), nullable=True)
    address_type = Column(Enum(AddressType), default=AddressType.both)
    is_preferred = Column(Boolean, default=False)

    vendor = relationship("Vendor", back_populates="addresses")


class VendorProduct(Base):
    __tablename__ = "vendor_products"
    id = Column(Integer, primary_key=True, index=True)
    vendor_id = Column(Integer, ForeignKey("vendors.id"), nullable=False)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    vendor_part_code = Column(String(50), nullable=True)
    last_price = Column(Numeric(12, 2), nullable=True)
    last_purchase_date = Column(Date, nullable=True)

    vendor = relationship("Vendor", back_populates="vendor_products")
    product = relationship("Product", back_populates="vendor_products")

    __table_args__ = (UniqueConstraint("vendor_id", "product_id", name="uq_vendor_product"),)


# ─── Customers ──────────────────────────────────────────────

class Customer(Base, TimestampMixin):
    __tablename__ = "customers"
    id = Column(Integer, primary_key=True, index=True)
    trade_name = Column(String(200), nullable=False, index=True)
    legal_name = Column(String(200), nullable=True)
    gstin = Column(String(15), unique=True, nullable=True, index=True)
    business_type = Column(String(50), nullable=True)
    gst_status = Column(String(20), nullable=True)
    gst_registration_date = Column(Date, nullable=True)
    nature_of_business = Column(String(100), nullable=True)
    state = Column(String(50), nullable=True)
    state_code = Column(SmallInteger, nullable=True)
    phone = Column(String(15), nullable=True)
    email = Column(String(100), nullable=True)
    contact_person = Column(String(100), nullable=True)
    credit_limit = Column(Numeric(12, 2), default=0)
    credit_days = Column(Integer, default=0)
    is_b2b = Column(Boolean, default=True)
    is_active = Column(Boolean, default=True, nullable=False)

    addresses = relationship("CustomerAddress", back_populates="customer")
    invoices = relationship("Invoice", back_populates="customer")
    ledger_entries = relationship("LedgerEntry", back_populates="customer")
    customer_discounts = relationship("CustomerDiscount", back_populates="customer")


class CustomerAddress(Base, TimestampMixin):
    __tablename__ = "customer_addresses"
    id = Column(Integer, primary_key=True, index=True)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=False)
    label = Column(String(50), nullable=False)
    address_line1 = Column(String(200), nullable=False)
    address_line2 = Column(String(200), nullable=True)
    city = Column(String(50), nullable=False)
    state = Column(String(50), nullable=False)
    state_code = Column(SmallInteger, nullable=True)
    pincode = Column(String(6), nullable=False)
    contact_person = Column(String(100), nullable=True)
    phone = Column(String(15), nullable=True)
    address_type = Column(Enum(AddressType), default=AddressType.both)
    is_preferred_billing = Column(Boolean, default=False)
    is_preferred_shipping = Column(Boolean, default=False)

    customer = relationship("Customer", back_populates="addresses")


class CustomerDiscount(Base, TimestampMixin):
    __tablename__ = "customer_discounts"
    id = Column(Integer, primary_key=True, index=True)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=False)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    discount_percent = Column(Numeric(5, 2), nullable=False, default=0)
    is_active = Column(Boolean, default=True)

    customer = relationship("Customer", back_populates="customer_discounts")

    __table_args__ = (UniqueConstraint("customer_id", "product_id", name="uq_customer_product_discount"),)


# ─── Invoice Numbering ──────────────────────────────────────

class InvoiceSequence(Base):
    __tablename__ = "invoice_sequences"
    id = Column(Integer, primary_key=True, index=True)
    document_type = Column(String(30), nullable=False)
    prefix = Column(String(10), nullable=False)
    financial_year = Column(String(7), nullable=True)
    last_number = Column(Integer, default=0, nullable=False)

    __table_args__ = (UniqueConstraint("document_type", "financial_year", name="uq_doc_type_fy"),)


# ─── Purchases ──────────────────────────────────────────────

class Purchase(Base, TimestampMixin):
    __tablename__ = "purchases"
    id = Column(Integer, primary_key=True, index=True)
    purchase_number = Column(String(30), unique=True, nullable=True)
    vendor_id = Column(Integer, ForeignKey("vendors.id"), nullable=False)
    warehouse_id = Column(Integer, ForeignKey("warehouses.id"), nullable=False)
    vendor_invoice_number = Column(String(50), nullable=True)
    invoice_date = Column(Date, nullable=True)
    received_date = Column(Date, nullable=True)
    payment_due_date = Column(Date, nullable=True)
    subtotal = Column(Numeric(12, 2), default=0)
    total_cgst = Column(Numeric(12, 2), default=0)
    total_sgst = Column(Numeric(12, 2), default=0)
    total_igst = Column(Numeric(12, 2), default=0)
    total_amount = Column(Numeric(12, 2), default=0)
    paid_amount = Column(Numeric(12, 2), default=0)
    outstanding_amount = Column(Numeric(12, 2), default=0)
    gst_type = Column(Enum(GSTType), nullable=True)
    notes = Column(Text, nullable=True)
    financial_year = Column(String(7), nullable=True)
    is_cancelled = Column(Boolean, default=False)

    vendor = relationship("Vendor", back_populates="purchases")
    items = relationship("PurchaseItem", back_populates="purchase")
    payments = relationship("VendorPayment", back_populates="purchase")

    __table_args__ = (Index("ix_purchase_vendor_fy", "vendor_id", "financial_year"),)


class PurchaseItem(Base):
    __tablename__ = "purchase_items"
    id = Column(Integer, primary_key=True, index=True)
    purchase_id = Column(Integer, ForeignKey("purchases.id"), nullable=False)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    quantity = Column(Numeric(12, 3), nullable=True)
    unit_cost = Column(Numeric(12, 2), nullable=True, default=0)
    gst_percent = Column(Numeric(5, 2), nullable=True, default=0)
    cgst_amount = Column(Numeric(12, 2), default=0)
    sgst_amount = Column(Numeric(12, 2), default=0)
    igst_amount = Column(Numeric(12, 2), default=0)
    line_total = Column(Numeric(12, 2), nullable=True, default=0)
    hsn_code = Column(String(8), nullable=True)

    purchase = relationship("Purchase", back_populates="items")


# ─── Invoices ───────────────────────────────────────────────

class Invoice(Base, TimestampMixin):
    __tablename__ = "invoices"
    id = Column(Integer, primary_key=True, index=True)
    invoice_number = Column(String(30), unique=True, nullable=True, index=True)
    document_type = Column(String(30), nullable=True)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=True)
    warehouse_id = Column(Integer, ForeignKey("warehouses.id"), nullable=False)
    billing_address_id = Column(Integer, ForeignKey("customer_addresses.id"), nullable=True)
    shipping_address_id = Column(Integer, ForeignKey("customer_addresses.id"), nullable=True)
    invoice_date = Column(Date, nullable=False)
    due_date = Column(Date, nullable=True)
    subtotal = Column(Numeric(12, 2), default=0)
    item_discount = Column(Numeric(12, 2), default=0)
    invoice_discount = Column(Numeric(12, 2), default=0)
    taxable_amount = Column(Numeric(12, 2), default=0)
    total_cgst = Column(Numeric(12, 2), default=0)
    total_sgst = Column(Numeric(12, 2), default=0)
    total_igst = Column(Numeric(12, 2), default=0)
    round_off = Column(Numeric(12, 2), nullable=True, default=0)
    total_amount = Column(Numeric(12, 2), default=0)
    paid_amount = Column(Numeric(12, 2), default=0)
    outstanding_amount = Column(Numeric(12, 2), default=0)
    credited_amount = Column(Numeric(12, 2), default=0)
    gst_type = Column(Enum(GSTType), nullable=True)
    # GST place of supply (destination state code), frozen at creation so a
    # later customer-address edit can't retroactively change a filed invoice.
    place_of_supply = Column(SmallInteger, nullable=True)
    terms_conditions = Column(Text, nullable=True)
    notes = Column(Text, nullable=True)
    financial_year = Column(String(7), nullable=True)
    is_cancelled = Column(Boolean, default=False)
    cancelled_at = Column(DateTime, nullable=True)
    cancelled_reason = Column(Text, nullable=True)
    salesperson_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    original_invoice_id = Column(Integer, ForeignKey("invoices.id"), nullable=True)
    quotation_id = Column(Integer, nullable=True)  # which quotation this was converted from
    quotation_status = Column(String(20), nullable=True)  # pending / invoiced
    irn = Column(String(100), nullable=True)
    irn_status = Column(Enum(EInvoiceStatus), nullable=True)
    qr_code_path = Column(String(255), nullable=True)
    qr_code = Column(Text, nullable=True)
    signed_invoice = Column(Text, nullable=True)
    irn_ack_number = Column(String(50), nullable=True)
    irn_ack_date = Column(DateTime, nullable=True)
    irn_generated_at = Column(DateTime, nullable=True)
    irn_error = Column(Text, nullable=True)
    eway_bill_number = Column(String(20), nullable=True)
    eway_bill_status = Column(Enum(EWayBillStatus), nullable=True)
    transporter_id = Column(Integer, ForeignKey("transporters.id"), nullable=True)
    transporter_name = Column(String(100), nullable=True)
    show_transport_on_print = Column(Boolean, nullable=True)

    customer = relationship("Customer", back_populates="invoices")
    items = relationship("InvoiceItem", back_populates="invoice")
    payments = relationship("CustomerPayment", back_populates="invoice")
    billing_address = relationship("CustomerAddress", foreign_keys=[billing_address_id])
    shipping_address = relationship("CustomerAddress", foreign_keys=[shipping_address_id])

    __table_args__ = (Index("ix_invoice_customer_fy", "customer_id", "financial_year"),)


class InvoiceItem(Base):
    __tablename__ = "invoice_items"
    id = Column(Integer, primary_key=True, index=True)
    invoice_id = Column(Integer, ForeignKey("invoices.id"), nullable=False)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    quantity = Column(Numeric(12, 3), nullable=True)
    unit_price = Column(Numeric(12, 2), nullable=True, default=0)
    discount_percent = Column(Numeric(5, 2), default=0)
    discount_amount = Column(Numeric(12, 2), default=0)
    taxable_amount = Column(Numeric(12, 2), nullable=True, default=0)
    gst_percent = Column(Numeric(5, 2), nullable=True, default=0)
    cgst_percent = Column(Numeric(5, 2), default=0)
    sgst_percent = Column(Numeric(5, 2), default=0)
    igst_percent = Column(Numeric(5, 2), default=0)
    cgst_amount = Column(Numeric(12, 2), default=0)
    sgst_amount = Column(Numeric(12, 2), default=0)
    igst_amount = Column(Numeric(12, 2), default=0)
    line_total = Column(Numeric(12, 2), nullable=True, default=0)
    hsn_code = Column(String(8), nullable=True)
    fifo_cost = Column(Numeric(12, 2), nullable=True)
    notes = Column(Text, nullable=True)
    original_item_id = Column(Integer, ForeignKey("invoice_items.id"), nullable=True)

    invoice = relationship("Invoice", back_populates="items")


# ─── Accounting ─────────────────────────────────────────────

class Account(Base, TimestampMixin):
    __tablename__ = "accounts"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    account_code = Column(String(20), unique=True, nullable=False)
    account_name = Column(String(100), nullable=True)
    account_type = Column(String(30), nullable=False)
    parent_id = Column(Integer, ForeignKey("accounts.id"), nullable=True)
    is_system = Column(Boolean, default=False)
    is_active = Column(Boolean, default=True)
    opening_balance = Column(Numeric(14, 2), default=0)
    current_balance = Column(Numeric(14, 2), default=0)


class JournalEntry(Base, TimestampMixin):
    __tablename__ = "journal_entries"
    id = Column(BigInteger, primary_key=True, index=True)
    entry_number = Column(String(30), unique=True, nullable=True)
    entry_date = Column(Date, nullable=True)
    reference_type = Column(String(50), nullable=True)
    reference_id = Column(Integer, nullable=True)
    narration = Column(Text, nullable=True)
    financial_year = Column(String(7), nullable=True)
    is_cancelled = Column(Boolean, default=False)

    lines = relationship("JournalLine", back_populates="journal_entry")

    __table_args__ = (Index("ix_journal_reference", "reference_type", "reference_id"),)


class JournalLine(Base):
    __tablename__ = "journal_lines"
    id = Column(BigInteger, primary_key=True, index=True)
    journal_entry_id = Column(BigInteger, ForeignKey("journal_entries.id"), nullable=False)
    account_id = Column(Integer, ForeignKey("accounts.id"), nullable=False)
    transaction_type = Column(Enum(TransactionType), nullable=True)
    amount = Column(Numeric(14, 2), nullable=False)
    narration = Column(String(200), nullable=True)
    is_reconciled = Column(Boolean, default=False)
    reconciliation_id = Column(Integer, ForeignKey("bank_reconciliations.id"), nullable=True)

    journal_entry = relationship("JournalEntry", back_populates="lines")


class LedgerEntry(Base):
    __tablename__ = "ledger_entries"
    id = Column(BigInteger, primary_key=True, index=True)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=True)
    vendor_id = Column(Integer, ForeignKey("vendors.id"), nullable=True)
    transaction_type = Column(String(20), nullable=True)
    amount = Column(Numeric(14, 2), nullable=True)
    balance = Column(Numeric(14, 2), nullable=True)
    reference_type = Column(String(50), nullable=True)
    reference_id = Column(Integer, nullable=True)
    narration = Column(Text, nullable=True)
    entry_date = Column(Date, nullable=True)
    financial_year = Column(String(7), nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)

    customer = relationship("Customer", back_populates="ledger_entries")
    vendor = relationship("Vendor", back_populates="ledger_entries")


class CustomerPayment(Base, TimestampMixin):
    __tablename__ = "customer_payments"
    id = Column(Integer, primary_key=True, index=True)
    payment_number = Column(String(30), unique=True, nullable=True)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=False)
    invoice_id = Column(Integer, ForeignKey("invoices.id"), nullable=True)
    payment_date = Column(Date, nullable=True)
    amount = Column(Numeric(12, 2), nullable=True)
    payment_mode = Column(String(20), nullable=True)
    reference_number = Column(String(50), nullable=True)
    tds_amount = Column(Numeric(12, 2), default=0, nullable=True)
    notes = Column(Text, nullable=True)
    is_advance = Column(Boolean, default=False)
    financial_year = Column(String(7), nullable=True)

    invoice = relationship("Invoice", back_populates="payments")


class VendorPayment(Base, TimestampMixin):
    __tablename__ = "vendor_payments"
    id = Column(Integer, primary_key=True, index=True)
    payment_number = Column(String(30), unique=True, nullable=True)
    vendor_id = Column(Integer, ForeignKey("vendors.id"), nullable=False)
    purchase_id = Column(Integer, ForeignKey("purchases.id"), nullable=True)
    payment_date = Column(Date, nullable=True)
    amount = Column(Numeric(12, 2), nullable=True)
    payment_mode = Column(String(20), nullable=True)
    reference_number = Column(String(50), nullable=True)
    notes = Column(Text, nullable=True)
    is_advance = Column(Boolean, default=False)
    financial_year = Column(String(7), nullable=True)
    is_void = Column(Boolean, default=False, nullable=False)
    voided_at = Column(DateTime, nullable=True)
    voided_by = Column(Integer, ForeignKey("users.id"), nullable=True)

    purchase = relationship("Purchase", back_populates="payments")


# ─── GST / E-Invoice ────────────────────────────────────────

class EInvoiceLog(Base):
    __tablename__ = "einvoice_logs"
    id = Column(Integer, primary_key=True, index=True)
    invoice_id = Column(Integer, ForeignKey("invoices.id"), nullable=False)
    irn = Column(String(100), nullable=True)
    ack_number = Column(String(50), nullable=True)
    ack_date = Column(DateTime, nullable=True)
    status = Column(Enum(EInvoiceStatus), nullable=False)
    request_payload = Column(Text, nullable=True)
    response_payload = Column(Text, nullable=True)
    error_message = Column(Text, nullable=True)
    retry_count = Column(SmallInteger, default=0)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    created_by = Column(Integer, nullable=True)


class EWayBillLog(Base):
    __tablename__ = "eway_bill_logs"
    id = Column(Integer, primary_key=True, index=True)
    invoice_id = Column(Integer, ForeignKey("invoices.id"), nullable=False)
    eway_bill_number = Column(String(20), nullable=True)
    irn = Column(String(100), nullable=True)
    vehicle_number = Column(String(20), nullable=True)
    vehicle_id = Column(Integer, ForeignKey("vehicles.id"), nullable=True)
    driver_name = Column(String(100), nullable=True)
    lr_number = Column(String(50), nullable=True)
    dc_destination_warehouse_id = Column(Integer, ForeignKey("warehouses.id"), nullable=True)
    dc_status = Column(String(20), nullable=True, default="pending")
    dc_approved_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    dc_approved_at = Column(DateTime, nullable=True)
    dc_rejected_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    dc_rejected_at = Column(DateTime, nullable=True)
    dc_rejection_reason = Column(Text, nullable=True)
    created_by = Column(Integer, nullable=True)
    transporter_name = Column(String(100), nullable=True)
    transport_mode = Column(String(20), nullable=True)
    distance_km = Column(Integer, nullable=True)
    from_pincode = Column(String(6), nullable=True)
    to_pincode = Column(String(6), nullable=True)
    valid_upto = Column(DateTime, nullable=True)
    status = Column(Enum(EWayBillStatus), nullable=False)
    entry_type = Column(String(20), nullable=True)  # generate | update_vehicle | cancel
    cancel_reason = Column(String(200), nullable=True)
    cancelled_at = Column(DateTime, nullable=True)
    request_payload = Column(Text, nullable=True)
    response_payload = Column(Text, nullable=True)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)


# ─── Bank Stock Statement ────────────────────────────────────

class BankStockStatement(Base, TimestampMixin):
    __tablename__ = "bank_stock_statements"
    id = Column(Integer, primary_key=True, index=True)
    statement_date = Column(Date, unique=True, nullable=False)
    statement_month = Column(String(7), nullable=False)
    stock_value = Column(Numeric(14, 2), nullable=False)
    debtors_value = Column(Numeric(14, 2), nullable=False)
    total_value = Column(Numeric(14, 2), nullable=False)
    margin_percent = Column(Numeric(5, 2), default=25.00)
    drawing_power = Column(Numeric(14, 2), nullable=False)
    is_locked = Column(Boolean, default=False)
    locked_at = Column(DateTime, nullable=True)
    locked_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    excel_path = Column(String(255), nullable=True)
    pdf_path = Column(String(255), nullable=True)
    bank_name = Column(String(100), nullable=True)
    account_number = Column(String(30), nullable=True)
    statement_number = Column(String(30), nullable=True)
    cc_limit = Column(Numeric(14, 2), nullable=True)
    stock_breakup = Column(Text, nullable=True)
    debtor_breakup = Column(Text, nullable=True)
    financial_year = Column(String(10), nullable=True)
    notes = Column(Text, nullable=True)


# ─── Bank Reconciliation ─────────────────────────────────────

class BankReconciliation(Base, TimestampMixin):
    __tablename__ = "bank_reconciliations"
    id = Column(Integer, primary_key=True, index=True)
    reconciliation_number = Column(String(30), unique=True, nullable=True)
    account_code = Column(String(20), nullable=False, default="BANK")
    period_from = Column(Date, nullable=False)
    period_to = Column(Date, nullable=False)
    statement_closing_balance = Column(Numeric(14, 2), default=0)
    books_closing_balance = Column(Numeric(14, 2), default=0)
    difference = Column(Numeric(14, 2), default=0)
    status = Column(String(20), nullable=False, default="draft")
    notes = Column(Text, nullable=True)
    financial_year = Column(String(10), nullable=True)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    finalized_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    finalized_at = Column(DateTime, nullable=True)

    lines = relationship("BankReconciliationLine", back_populates="reconciliation",
                         cascade="all, delete-orphan")


class BankReconciliationLine(Base):
    __tablename__ = "bank_reconciliation_lines"
    id = Column(BigInteger, primary_key=True, index=True)
    reconciliation_id = Column(Integer, ForeignKey("bank_reconciliations.id"), nullable=False)
    bank_date = Column(Date, nullable=True)
    bank_description = Column(String(255), nullable=True)
    bank_debit = Column(Numeric(14, 2), default=0)
    bank_credit = Column(Numeric(14, 2), default=0)
    bank_reference = Column(String(100), nullable=True)
    journal_line_id = Column(BigInteger, ForeignKey("journal_lines.id"), nullable=True)
    previous_journal_line_id = Column(BigInteger, nullable=True)
    match_type = Column(String(20), nullable=False, default="unmatched")
    match_reason = Column(String(200), nullable=True)
    is_adjustment = Column(Boolean, default=False)
    adjustment_journal_entry_id = Column(BigInteger, nullable=True)
    matched_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    matched_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)

    reconciliation = relationship("BankReconciliation", back_populates="lines")


# ─── Company Settings ────────────────────────────────────────

class CompanySettings(Base, TimestampMixin):
    __tablename__ = "company_settings"
    id = Column(Integer, primary_key=True, index=True)
    company_name = Column(String(200), nullable=False)
    gstin = Column(String(15), nullable=False)
    state = Column(String(50), nullable=False)
    state_code = Column(SmallInteger, nullable=False)
    address_line1 = Column(String(200), nullable=False)
    address_line2 = Column(String(200), nullable=True)
    city = Column(String(50), nullable=False)
    pincode = Column(String(6), nullable=False)
    phone = Column(String(15), nullable=True)
    email = Column(String(100), nullable=True)
    logo_path = Column(String(255), nullable=True)
    signature_path = Column(String(255), nullable=True)
    terms_conditions = Column(Text, nullable=True)
    terms_b2b_invoice = Column(Text, nullable=True)
    terms_b2c_invoice = Column(Text, nullable=True)
    terms_quotation = Column(Text, nullable=True)
    terms_delivery_challan = Column(Text, nullable=True)
    b2b_invoice_prefix = Column(String(10), default="BINV")
    b2c_invoice_prefix = Column(String(10), default="CINV")
    quotation_prefix = Column(String(10), default="QT")
    challan_prefix = Column(String(10), default="DC")
    credit_note_prefix = Column(String(10), default="CN")
    eway_threshold = Column(Numeric(12, 2), default=50000)
    bank_stock_margin = Column(Numeric(5, 2), default=25.00)
    default_min_margin_pct = Column(Numeric(5, 2), default=10.00)
    financial_year_start = Column(SmallInteger, default=4)
    bank_name = Column(String(100), nullable=True)
    bank_account_number = Column(String(30), nullable=True)
    bank_ifsc = Column(String(11), nullable=True)
    bank_branch = Column(String(100), nullable=True)
    bank_account_name = Column(String(100), nullable=True)
    upi_id = Column(String(50), nullable=True)
    show_transport_on_invoice = Column(Boolean, default=True, nullable=True)
    show_transport_on_challan = Column(Boolean, default=True, nullable=True)

class PriceTypeEnum(str, enum.Enum):
    purchase_cost = "purchase_cost"
    b2b_price = "b2b_price"
    b2c_price = "b2c_price"
    mrp = "mrp"


class ProductPrice(Base):
    """Multi-type price store with effective date support."""
    __tablename__ = "product_prices"
    id = Column(Integer, primary_key=True, index=True)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    price_type = Column(String(20), nullable=False)  # purchase_cost|selling_price|b2b_price|b2c_price|mrp
    price = Column(Numeric(12, 2), nullable=False)
    previous_price = Column(Numeric(12, 2), nullable=True)
    effective_from = Column(Date, nullable=False)
    effective_to = Column(Date, nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    is_scheduled = Column(Boolean, default=False, nullable=False)
    change_reason = Column(String(200), nullable=True)
    notes = Column(Text, nullable=True)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index("ix_pp_product_type", "product_id", "price_type"),
        Index("ix_pp_active", "product_id", "is_active"),
    )


class PriceAlert(Base):
    """In-app and email alerts for price anomalies."""
    __tablename__ = "price_alerts"
    id = Column(Integer, primary_key=True, index=True)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    alert_type = Column(String(30), nullable=False)  # low_margin|below_cost|price_change|scheduled_activated
    message = Column(Text, nullable=False)
    severity = Column(String(10), default="warning")  # info|warning|critical
    is_read = Column(Boolean, default=False)
    email_sent = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (Index("ix_pa_unread", "is_read"),)


class ProductPriceHistory(Base):
    __tablename__ = "product_price_history"
    id = Column(Integer, primary_key=True, autoincrement=True)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    recorded_at = Column(DateTime, default=datetime.utcnow)
    purchase_cost = Column(Numeric(12, 2), nullable=True)
    b2b_price = Column(Numeric(12, 2), nullable=True)
    b2c_price = Column(Numeric(12, 2), nullable=True)
    selling_price = Column(Numeric(12, 2), nullable=True)
    vendor_id = Column(Integer, ForeignKey("vendors.id"), nullable=True)
    vendor_name = Column(String(200), nullable=True)
    purchase_invoice_id = Column(Integer, nullable=True)
    purchase_invoice_number = Column(String(50), nullable=True)
    notes = Column(String(200), nullable=True)
    created_by = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


# ─── Configuration-driven parameter store (see docs/CONFIG_MIGRATION_PLAN.md) ──

class ConfigDefinition(Base, TimestampMixin):
    """Catalog of every configurable parameter — the metadata, not the value."""
    __tablename__ = "config_definitions"
    id = Column(Integer, primary_key=True, index=True)
    config_key = Column(String(120), nullable=False, unique=True, index=True)
    domain = Column(String(30), nullable=False)            # GST/INCOME_TAX/RBI/DPDP/STATE/COMPANY/BUSINESS
    data_type = Column(String(20), nullable=False)         # decimal/int/bool/string/json
    unit = Column(String(20), nullable=True)               # INR/percent/days/hours/km/digits
    scope_type = Column(String(30), nullable=False, default="global")
    validation_json = Column(Text, nullable=True)          # {"min":..,"max":..,"enum":[..],"regex":".."}
    description = Column(Text, nullable=True)
    is_regulatory = Column(Boolean, nullable=False, default=False)
    owner_role = Column(String(30), nullable=True, default="super_admin")


class ConfigValue(Base):
    """Effective-dated, versioned value for a ConfigDefinition.config_key."""
    __tablename__ = "config_values"
    id = Column(Integer, primary_key=True, index=True)
    config_key = Column(String(120), nullable=False, index=True)
    scope_value = Column(String(60), nullable=True)        # e.g. state code "29"; NULL = global
    value_json = Column(Text, nullable=True)               # canonical typed value: {"v": <value>}
    value_numeric = Column(Numeric(18, 4), nullable=True)  # mirror of numeric value for range queries
    effective_from = Column(Date, nullable=False)          # inclusive
    effective_to = Column(Date, nullable=True)             # inclusive; NULL = open-ended
    version = Column(Integer, nullable=False, default=1)
    status = Column(String(15), nullable=False, default="active")  # draft/scheduled/active/expired/superseded/revoked
    regulatory_reference = Column(String(200), nullable=True)
    note = Column(String(500), nullable=True)
    created_by = Column(Integer, nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    approved_by = Column(Integer, nullable=True)
    approved_at = Column(DateTime, nullable=True)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)

    __table_args__ = (
        Index("ix_config_values_lookup", "config_key", "scope_value", "effective_from"),
        Index("ix_config_values_status", "config_key", "status"),
    )


# ─── GST structured masters (effective-dated; see CONFIG_MIGRATION_PLAN.md) ────

class GstRateMaster(Base):
    """GST rate slabs accepted by the IRP + which appear in pickers."""
    __tablename__ = "gst_rate_master"
    id = Column(Integer, primary_key=True, index=True)
    rate = Column(Numeric(5, 2), nullable=False)
    label = Column(String(80), nullable=True)
    is_selectable = Column(Boolean, nullable=False, default=True)  # shown in dropdowns
    effective_from = Column(Date, nullable=False)
    effective_to = Column(Date, nullable=True)
    status = Column(String(15), nullable=False, default="active")
    regulatory_reference = Column(String(200), nullable=True)
    note = Column(String(500), nullable=True)
    created_by = Column(Integer, nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)
    __table_args__ = (Index("ix_gst_rate_master_window", "rate", "effective_from"),)


class StateMaster(Base):
    """GST state/UT codes — valid place-of-supply set + named picker list."""
    __tablename__ = "state_master"
    id = Column(Integer, primary_key=True, index=True)
    state_code = Column(SmallInteger, nullable=False)
    name = Column(String(80), nullable=False)
    is_selectable = Column(Boolean, nullable=False, default=True)  # shown in dropdowns
    effective_from = Column(Date, nullable=False)
    effective_to = Column(Date, nullable=True)
    status = Column(String(15), nullable=False, default="active")
    regulatory_reference = Column(String(200), nullable=True)
    note = Column(String(500), nullable=True)
    created_by = Column(Integer, nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)
    __table_args__ = (Index("ix_state_master_window", "state_code", "effective_from"),)


class UqcMaster(Base):
    """Free-text unit -> NIC UQC code mapping."""
    __tablename__ = "uqc_master"
    id = Column(Integer, primary_key=True, index=True)
    unit_text = Column(String(30), nullable=False)   # normalized: upper-case, no spaces
    uqc_code = Column(String(10), nullable=False)
    effective_from = Column(Date, nullable=False)
    effective_to = Column(Date, nullable=True)
    status = Column(String(15), nullable=False, default="active")
    regulatory_reference = Column(String(200), nullable=True)
    note = Column(String(500), nullable=True)
    created_by = Column(Integer, nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)
    __table_args__ = (Index("ix_uqc_master_window", "unit_text", "effective_from"),)


# ─── Income-tax / accounting masters (effective-dated; Phase 2) ────────────────

class TdsSectionMaster(Base):
    """TDS sections with their statutory rate + threshold (Income Tax Act)."""
    __tablename__ = "tds_section_master"
    id = Column(Integer, primary_key=True, index=True)
    section_code = Column(String(10), nullable=False)
    description = Column(String(120), nullable=True)
    rate = Column(Numeric(5, 2), nullable=False)
    threshold_single = Column(Numeric(14, 2), nullable=True)  # per-transaction exemption
    threshold_annual = Column(Numeric(14, 2), nullable=True)  # aggregate exemption
    deductee_type = Column(String(20), nullable=True)         # e.g. individual/company
    effective_from = Column(Date, nullable=False)
    effective_to = Column(Date, nullable=True)
    status = Column(String(15), nullable=False, default="active")
    regulatory_reference = Column(String(200), nullable=True)
    note = Column(String(500), nullable=True)
    created_by = Column(Integer, nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)
    __table_args__ = (Index("ix_tds_section_master_window", "section_code", "effective_from"),)


class AgingBucketMaster(Base):
    """Receivables ageing bucket boundaries + collection-priority weights."""
    __tablename__ = "aging_bucket_master"
    id = Column(Integer, primary_key=True, index=True)
    seq = Column(Integer, nullable=False)               # 1..N order
    label = Column(String(40), nullable=True)
    from_days = Column(Integer, nullable=False)         # inclusive lower bound
    to_days = Column(Integer, nullable=True)            # inclusive upper bound; NULL = open
    weight = Column(Numeric(5, 2), nullable=False, default=1)
    effective_from = Column(Date, nullable=False)
    effective_to = Column(Date, nullable=True)
    status = Column(String(15), nullable=False, default="active")
    regulatory_reference = Column(String(200), nullable=True)
    note = Column(String(500), nullable=True)
    created_by = Column(Integer, nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)
    __table_args__ = (Index("ix_aging_bucket_master_window", "seq", "effective_from"),)


class ChartOfAccountMap(Base):
    """Logical account code -> (account_type, default name) for auto-created
    ledger accounts. Replaces the in-code _ACCOUNT_TYPE_MAP in helpers.py."""
    __tablename__ = "chart_of_account_map"
    id = Column(Integer, primary_key=True, index=True)
    code = Column(String(30), nullable=False)
    account_type = Column(String(30), nullable=False)  # asset/liability/income/expense
    default_name = Column(String(120), nullable=False)
    effective_from = Column(Date, nullable=False)
    effective_to = Column(Date, nullable=True)
    status = Column(String(15), nullable=False, default="active")
    regulatory_reference = Column(String(200), nullable=True)
    note = Column(String(500), nullable=True)
    created_by = Column(Integer, nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)
    __table_args__ = (Index("ix_chart_of_account_map_code", "code", "effective_from"),)


# ─── DPDP Act — consent, retention, erasure (Phase 4b) ────────────────────────

class ConsentPurpose(Base):
    """Catalog of processing purposes a data principal can consent to."""
    __tablename__ = "consent_purpose"
    id = Column(Integer, primary_key=True, index=True)
    purpose_key = Column(String(50), nullable=False, unique=True)
    name = Column(String(120), nullable=False)
    description = Column(Text, nullable=True)
    requires_explicit = Column(Boolean, nullable=False, default=True)
    version = Column(Integer, nullable=False, default=1)
    is_active = Column(Boolean, nullable=False, default=True)
    created_by = Column(Integer, nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)


class ConsentRecord(Base):
    """A data principal's grant/withdrawal of consent for a purpose."""
    __tablename__ = "consent_record"
    id = Column(Integer, primary_key=True, index=True)
    principal_type = Column(String(20), nullable=False)   # user/customer/vendor
    principal_id = Column(Integer, nullable=False)
    purpose_key = Column(String(50), nullable=False)
    purpose_version = Column(Integer, nullable=False, default=1)
    status = Column(String(15), nullable=False, default="granted")  # granted/withdrawn
    granted_at = Column(DateTime, nullable=True)
    withdrawn_at = Column(DateTime, nullable=True)
    source = Column(String(50), nullable=True)            # web/import/api
    notes = Column(String(255), nullable=True)
    created_by = Column(Integer, nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    __table_args__ = (
        Index("ix_consent_record_principal", "principal_type", "principal_id", "purpose_key"),
    )


class DataRetentionPolicy(Base):
    """Per-entity retention window + action. Inert unless is_active=True."""
    __tablename__ = "data_retention_policy"
    id = Column(Integer, primary_key=True, index=True)
    entity = Column(String(50), nullable=False)           # activity_log/login_history/active_session
    retention_days = Column(Integer, nullable=False)
    action = Column(String(20), nullable=False, default="delete")  # delete/anonymize
    legal_basis = Column(String(200), nullable=True)
    is_active = Column(Boolean, nullable=False, default=False)     # opt-in; off by default
    notes = Column(String(255), nullable=True)
    effective_from = Column(Date, nullable=True)
    effective_to = Column(Date, nullable=True)
    created_by = Column(Integer, nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)


class ErasureRequest(Base):
    """Right-to-erasure request + its processing lifecycle (audit trail)."""
    __tablename__ = "erasure_request"
    id = Column(Integer, primary_key=True, index=True)
    subject_type = Column(String(20), nullable=False)     # customer/vendor/user
    subject_id = Column(Integer, nullable=False)
    subject_label = Column(String(120), nullable=True)
    status = Column(String(15), nullable=False, default="pending")  # pending/completed/rejected
    reason = Column(String(255), nullable=True)
    requested_by = Column(Integer, nullable=True)
    requested_at = Column(DateTime, server_default=func.now(), nullable=False)
    processed_by = Column(Integer, nullable=True)
    processed_at = Column(DateTime, nullable=True)
    result_note = Column(String(255), nullable=True)
    __table_args__ = (Index("ix_erasure_request_subject", "subject_type", "subject_id"),)


# ─── Document number formats for internal docs (Phase 5b) ─────────────────────

class DocumentNumberFormat(Base):
    """Prefix / padding / separator for internal document numbers
    (JE/PO/VP/ADJ/WO/EXP/TDS/BSS). Pattern: {prefix}{sep}{FYnodash}{sep}{seq:0Nd}.
    Invoice numbering stays on CompanySettings prefixes + invoice_sequences."""
    __tablename__ = "document_number_format"
    id = Column(Integer, primary_key=True, index=True)
    doc_type = Column(String(20), nullable=False, unique=True)
    prefix = Column(String(10), nullable=False)
    padding = Column(Integer, nullable=False, default=4)
    separator = Column(String(3), nullable=False, default="-")
    description = Column(String(120), nullable=True)
    status = Column(String(15), nullable=False, default="active")
    created_by = Column(Integer, nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)


# ─── Workflow status / transition advisory layer (Phase 5c) ───────────────────
# The Python status enums remain the structural source of truth; these masters
# add configurable labels/colours + a transition policy used in ADVISORY mode
# (violations are logged, never blocked).

class WorkflowStatusMaster(Base):
    """Display metadata for an entity's status values."""
    __tablename__ = "workflow_status_master"
    id = Column(Integer, primary_key=True, index=True)
    entity = Column(String(40), nullable=False)
    status_code = Column(String(30), nullable=False)
    label = Column(String(60), nullable=False)
    color = Column(String(20), nullable=True)
    sort_order = Column(Integer, nullable=False, default=0)
    is_terminal = Column(Boolean, nullable=False, default=False)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)
    __table_args__ = (
        Index("ix_workflow_status_entity", "entity"),
        UniqueConstraint("entity", "status_code", name="uq_workflow_status"),
    )


class WorkflowTransitionMaster(Base):
    """Allowed status transitions per entity (+ optional required role)."""
    __tablename__ = "workflow_transition_master"
    id = Column(Integer, primary_key=True, index=True)
    entity = Column(String(40), nullable=False)
    from_status = Column(String(30), nullable=False)
    to_status = Column(String(30), nullable=False)
    required_role = Column(String(30), nullable=True)
    is_allowed = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)
    __table_args__ = (Index("ix_workflow_transition_entity", "entity"),)
