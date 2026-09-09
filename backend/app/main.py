from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager
import os

from app.core.config import settings
from app.api.v1.router import api_router
from app.db.session import engine
from app.models import models


def _auto_migrate():
    """Run on startup - add any missing columns silently."""
    from sqlalchemy import text
    cols = [
        # customers
        ("customers","nature_of_business","VARCHAR(100)"),
        ("customers","gst_registration_date","DATE"),
        ("customers","state_code","SMALLINT"),
        ("customers","credit_limit","DECIMAL(12,2) DEFAULT 0"),
        ("customers","credit_days","INT DEFAULT 0"),
        ("customers","is_b2b","BOOLEAN DEFAULT TRUE"),
        # vendors
        ("vendors","nature_of_business","VARCHAR(100)"),
        ("vendors","gst_registration_date","DATE"),
        ("vendors","bank_name","VARCHAR(100)"),
        ("vendors","bank_account","VARCHAR(20)"),
        ("vendors","bank_ifsc","VARCHAR(11)"),
        ("vendors","state_code","SMALLINT"),
        ("vendors","credit_days","INT DEFAULT 0"),
        # products
        ("products","floor_price","DECIMAL(12,2) DEFAULT 0"),
        ("products","cost_alert_threshold_pct","DECIMAL(5,2) DEFAULT 5"),
        ("products","min_margin_pct","DECIMAL(5,2) DEFAULT 10"),
        ("products","description","TEXT"),
        # purchases
        ("purchases","purchase_number","VARCHAR(30)"),
        ("purchases","received_date","DATE"),
        ("purchases","payment_due_date","DATE"),
        ("purchases","financial_year","VARCHAR(7)"),
        ("purchases","gst_type","VARCHAR(20)"),
        ("purchases","is_cancelled","BOOLEAN DEFAULT FALSE"),
        # vendor_payments
        ("vendor_payments","is_void","BOOLEAN DEFAULT FALSE"),
        ("vendor_payments","voided_at","DATETIME"),
        ("vendor_payments","voided_by","INT"),
        # invoices
        ("invoices","billing_address_id","INT"),
        ("invoices","shipping_address_id","INT"),
        ("invoices","financial_year","VARCHAR(7)"),
        ("invoices","gst_type","VARCHAR(20)"),
        ("invoices","invoice_discount","DECIMAL(12,2) DEFAULT 0"),
        ("invoices","round_off","DECIMAL(12,2) DEFAULT 0"),
        ("invoices","outstanding_amount","DECIMAL(12,2) DEFAULT 0"),
        ("invoices","paid_amount","DECIMAL(12,2) DEFAULT 0"),
        ("invoices","place_of_supply","SMALLINT"),
        # warehouses
        ("warehouses","state_code","SMALLINT"),
        # stock
        ("stock_entries","remaining_qty","DECIMAL(12,3)"),
        ("stock_entries","unit_cost","DECIMAL(12,2) DEFAULT 0"),
        ("stock_entries","created_by","INT"),
        ("warehouse_stocks","updated_at","DATETIME"),
        # categories
        ("categories","prefix","VARCHAR(10)"),
        ("categories","sequence_counter","INT DEFAULT 0"),
        ("categories","default_gst_percent","DECIMAL(5,2) DEFAULT 18"),
        # customer_addresses
        ("customer_addresses","address_type","VARCHAR(20) DEFAULT 'both'"),
        ("customer_addresses","is_preferred_billing","BOOLEAN DEFAULT FALSE"),
        ("customer_addresses","is_preferred_shipping","BOOLEAN DEFAULT FALSE"),
        # vendor_addresses
        ("vendor_addresses","address_type","VARCHAR(20) DEFAULT 'both'"),
        ("vendor_addresses","is_preferred","BOOLEAN DEFAULT FALSE"),
        # journal
        ("journal_lines","narration","VARCHAR(200)"),
        # accounts
        ("accounts","name","VARCHAR(100) NOT NULL DEFAULT ''"),
        ("accounts","account_type","VARCHAR(30) NOT NULL DEFAULT 'asset'"),
        ("accounts","is_system","BOOLEAN DEFAULT FALSE"),
        ("accounts","is_active","BOOLEAN DEFAULT TRUE"),
        ("accounts","opening_balance","DECIMAL(14,2) DEFAULT 0"),
        ("accounts","current_balance","DECIMAL(14,2) DEFAULT 0"),
        # ── cash_closings ──
        ("cash_closings","approved_at","DATETIME"),
        ("cash_closings","closing_balance","DECIMAL(14,2) DEFAULT 0"),
        ("cash_closings","created_by","INT"),
        ("cash_closings","total_deposits","DECIMAL(14,2) DEFAULT 0"),
        ("cash_closings","total_expenses","DECIMAL(14,2) DEFAULT 0"),
        ("cash_closings","total_payments","DECIMAL(14,2) DEFAULT 0"),
        ("cash_closings","total_receipts","DECIMAL(14,2) DEFAULT 0"),
        # ── categories ──
        ("categories","default_hsn","VARCHAR(8)"),
        # ── cheques ──
        ("cheques","bank_account_code","VARCHAR(20)"),
        ("cheques","bounce_charges","DECIMAL(10,2) DEFAULT 0"),
        ("cheques","bounce_date","DATE"),
        ("cheques","bounce_reason","TEXT"),
        ("cheques","clearance_date","DATE"),
        ("cheques","deposit_date","DATE"),
        ("cheques","is_pdc","BOOLEAN DEFAULT FALSE"),
        ("cheques","payment_id","INT"),
        ("cheques","receipt_id","INT"),
        # ── cost_alerts ──
        ("cost_alerts","is_resolved","BOOLEAN DEFAULT FALSE"),
        ("cost_alerts","new_value","DECIMAL(12,2)"),
        ("cost_alerts","old_value","DECIMAL(12,2)"),
        ("cost_alerts","resolved_at","DATETIME"),
        ("cost_alerts","suggested_price","DECIMAL(12,2)"),
        # ── customer_payments ──
        ("customer_payments","financial_year","VARCHAR(7)"),
        ("customer_payments","is_advance","BOOLEAN DEFAULT FALSE"),
        # ── expenses ──
        ("expenses","approved_at","DATETIME"),
        ("expenses","expense_number","VARCHAR(30)"),
        # ── invoice_sequences ──
        ("invoice_sequences","financial_year","VARCHAR(7)"),
        ("invoice_sequences","prefix","VARCHAR(20)"),
        # ── invoices ──
        ("invoices","credited_amount","DECIMAL(12,2) DEFAULT 0"),
        ("invoices","eway_bill_status","VARCHAR(20)"),
        ("invoices","irn_status","VARCHAR(20)"),
        ("invoices","qr_code_path","VARCHAR(255)"),
        # ── journal_entries ──
        ("journal_entries","financial_year","VARCHAR(7)"),
        # ── ledger_entries ──
        ("ledger_entries","financial_year","VARCHAR(7)"),
        # ── product_cost_history ──
        ("product_cost_history","financial_year","VARCHAR(7)"),
        ("product_cost_history","recorded_at","DATETIME"),
        # ── products ──
        ("products","image_path","VARCHAR(255)"),
        # ── stock_transfers ──
        ("stock_transfers","financial_year","VARCHAR(7)"),
        ("stock_transfers","transfer_number","VARCHAR(30)"),
        # ── stock_writeoffs ──
        ("stock_writeoffs","admin_notes","TEXT"),
        ("stock_writeoffs","approved_at","DATETIME"),
        ("stock_writeoffs","reason_detail","TEXT"),
        # ── tds_entries ──
        ("tds_entries","deduction_date","DATE"),
        ("tds_entries","financial_year","VARCHAR(7)"),
        ("tds_entries","is_reconciled","BOOLEAN DEFAULT FALSE"),
        ("tds_entries","tan_number","VARCHAR(10)"),
        ("tds_entries","tds_number","VARCHAR(30)"),
        # ── users ──
        ("users","failed_login_count","INT DEFAULT 0"),
        ("users","locked_until","DATETIME"),
        ("users","last_login","DATETIME"),
        ("users","refresh_token","TEXT"),
        ("users","page_permissions","TEXT"),
        ("users","warehouse_id","INT"),
        ("users","two_fa_enabled","BOOLEAN DEFAULT FALSE"),
        ("users","two_fa_secret","VARCHAR(32)"),
        # ── active_sessions ──
        ("active_sessions","refresh_token_hash","VARCHAR(64)"),
        # ── vendor_payments ──
        ("vendor_payments","financial_year","VARCHAR(7)"),
        ("vendor_payments","is_advance","BOOLEAN DEFAULT FALSE"),
        ("expenses","vendor_id","INT"),
        ("expenses","admin_notes","TEXT"),
        ("customer_payments","tds_amount","DECIMAL(12,2) DEFAULT 0"),
        ("einvoice_logs","created_by","INT"),
        ("eway_bill_logs","created_by","INT"),
        ("eway_bill_logs","vehicle_id","INT"),
        ("eway_bill_logs","vehicle_number","VARCHAR(20)"),
        ("eway_bill_logs","driver_name","VARCHAR(100)"),
        ("eway_bill_logs","lr_number","VARCHAR(50)"),
        ("eway_bill_logs","transporter_name","VARCHAR(100)"),
        ("eway_bill_logs","transport_mode","VARCHAR(20)"),
        ("eway_bill_logs","distance_km","INT"),
        ("eway_bill_logs","from_pincode","VARCHAR(6)"),
        ("eway_bill_logs","to_pincode","VARCHAR(6)"),
        ("eway_bill_logs","dc_destination_warehouse_id","INT"),
        ("eway_bill_logs","dc_status","VARCHAR(20)"),
        ("eway_bill_logs","valid_upto","DATETIME"),
        ("eway_bill_logs","status","VARCHAR(20)"),
        ("eway_bill_logs","request_payload","TEXT"),
        ("eway_bill_logs","response_payload","TEXT"),
        ("eway_bill_logs","error_message","TEXT"),
        ("bank_stock_statements","financial_year","VARCHAR(10)"),
        ("bank_stock_statements","notes","TEXT"),
        ("invoices","salesperson_id","INT"),
        ("invoices","quotation_status","VARCHAR(20)"),
        ("invoices","quotation_id","INT"),
        ("invoices","vehicle_number","VARCHAR(20)"),
        ("invoices","vehicle_id","INT"),
        ("invoices","driver_name","VARCHAR(100)"),
        ("invoices","lr_number","VARCHAR(50)"),
        ("invoices","dc_destination_warehouse_id","INT"),
        ("invoices","dc_status","VARCHAR(20)"),
        ("eway_bill_logs","irn","VARCHAR(100)"),
        ("expenses","financial_year","VARCHAR(7)"),
        ("cash_closings","financial_year","VARCHAR(7)"),
        ("cash_closings","notes","TEXT"),
        ("cash_closings","approved_by","INT"),
        ("cash_closings","approved_at","DATETIME"),
        ("cash_closings","total_receipts","DECIMAL(14,2) DEFAULT 0"),
        ("cash_closings","total_payments","DECIMAL(14,2) DEFAULT 0"),
        ("cash_closings","total_expenses","DECIMAL(14,2) DEFAULT 0"),
        ("cash_closings","total_deposits","DECIMAL(14,2) DEFAULT 0"),
        ("cash_closings","closing_balance","DECIMAL(14,2) DEFAULT 0"),
        ("cash_closings","opening_balance","DECIMAL(14,2) DEFAULT 0"),
        ("cash_closings","status","VARCHAR(20) DEFAULT 'draft'"),
        ("cash_closings","created_by","INT"),
        ("stock_transfers","product_id","INT"),
        ("stock_transfers","quantity","DECIMAL(12,3)"),
        ("activity_logs","module","VARCHAR(50)"),
        ("activity_logs","action","VARCHAR(100)"),
        ("activity_logs","record_id","INT"),
        ("activity_logs","record_type","VARCHAR(50)"),
        ("activity_logs","old_values","TEXT"),
        ("activity_logs","new_values","TEXT"),
        ("activity_logs","ip_address","VARCHAR(45)"),
        ("activity_logs","resource_id","INT"),
        ("activity_logs","resource_type","VARCHAR(50)"),
        ("activity_logs","details","TEXT"),
        ("accounts","account_name","VARCHAR(100)"),
        ("bank_stock_statements","bank_name","VARCHAR(100)"),
        ("bank_stock_statements","account_number","VARCHAR(30)"),
        ("bank_stock_statements","statement_number","VARCHAR(30)"),
        ("bank_stock_statements","cc_limit","DECIMAL(14,2)"),
        ("bank_stock_statements","stock_breakup","TEXT"),
        ("bank_stock_statements","debtor_breakup","TEXT"),
        # ── bank_stock_statements (ORM columns absent from legacy table) ──
        ("bank_stock_statements","statement_month","VARCHAR(7)"),
        ("bank_stock_statements","margin_percent","DECIMAL(5,2)"),
        ("bank_stock_statements","locked_at","DATETIME"),
        ("bank_stock_statements","locked_by","INT"),
        ("bank_stock_statements","excel_path","VARCHAR(255)"),
        ("bank_stock_statements","pdf_path","VARCHAR(255)"),
        ("tds_entries","receipt_id","INT"),
        ("stock_adjustments","unit_cost","DECIMAL(12,2)"),
        ("stock_adjustments","notes","TEXT"),
        ("stock_transfers","source_warehouse_id","INT"),
        ("stock_transfers","destination_warehouse_id","INT"),
        # ── products (new price columns) ──
        ("products","b2b_price","DECIMAL(12,2) DEFAULT 0"),
        ("products","b2c_price","DECIMAL(12,2) DEFAULT 0"),
        ("products","mrp","DECIMAL(12,2) DEFAULT 0"),
        # ── invoice_items ──
        ("invoice_items","notes","TEXT"),
        ("invoice_items","original_item_id","INT"),
        ("customer_addresses","state_code","SMALLINT"),
        ("company_settings","bank_name","VARCHAR(100)"),
        ("company_settings","bank_account_number","VARCHAR(30)"),
        ("company_settings","bank_ifsc","VARCHAR(11)"),
        ("company_settings","bank_branch","VARCHAR(100)"),
        ("company_settings","bank_account_name","VARCHAR(100)"),
        ("company_settings","upi_id","VARCHAR(50)"),
        ("company_settings","state_code","SMALLINT"),
        ("company_settings","default_min_margin_pct","DECIMAL(5,2) DEFAULT 10.00"),
        ("company_settings","terms_b2b_invoice","TEXT"),
        ("company_settings","terms_b2c_invoice","TEXT"),
        ("company_settings","terms_quotation","TEXT"),
        ("company_settings","terms_delivery_challan","TEXT"),
    ]
    # Also make old NOT NULL columns nullable
    make_nullable = [
        ("purchases","vendor_invoice_number","VARCHAR(50)"),
        ("purchases","subtotal","DECIMAL(12,2)"),
        ("purchases","total_amount","DECIMAL(12,2)"),
        ("purchases","paid_amount","DECIMAL(12,2) DEFAULT 0"),
        ("purchases","outstanding_amount","DECIMAL(12,2) DEFAULT 0"),
        ("invoices","invoice_number","VARCHAR(30)"),
        ("invoices","document_type","VARCHAR(30)"),
        ("stock_entries","remaining_quantity","DECIMAL(12,3)"),
        ("stock_entries","transaction_type","VARCHAR(30)"),
        ("stock_entries","quantity","DECIMAL(12,3)"),
        ("purchase_items","unit_cost","DECIMAL(12,2)"),
        ("purchase_items","unit_price","DECIMAL(12,2)"),
        ("purchase_items","gst_percent","DECIMAL(5,2)"),
        ("purchase_items","line_total","DECIMAL(12,2)"),
        ("purchase_items","quantity","DECIMAL(12,3)"),
        ("invoice_items","unit_price","DECIMAL(12,2)"),
        ("invoice_items","gst_percent","DECIMAL(5,2)"),
        ("invoice_items","taxable_amount","DECIMAL(12,2)"),
        ("invoice_items","line_total","DECIMAL(12,2)"),
        ("invoice_items","quantity","DECIMAL(12,3)"),
    ]
    try:
        with engine.connect() as c:
            for table, col, defn in cols:
                try:
                    c.execute(text(f"ALTER TABLE `{table}` ADD COLUMN `{col}` {defn}"))
                    c.commit()
                except Exception:
                    pass
            for table, col, defn in make_nullable:
                try:
                    c.execute(text(f"ALTER TABLE `{table}` MODIFY COLUMN `{col}` {defn} NULL DEFAULT 0"))
                    c.commit()
                except Exception:
                    pass
            # Create missing tables inline
            _tables = [
            ("product_prices", """CREATE TABLE IF NOT EXISTS product_prices (
            id INT AUTO_INCREMENT PRIMARY KEY,
            product_id INT NOT NULL,
            price_type VARCHAR(20) NOT NULL,
            price DECIMAL(12,2) NOT NULL,
            previous_price DECIMAL(12,2),
            effective_from DATE NOT NULL,
            effective_to DATE,
            is_active BOOLEAN DEFAULT TRUE,
            is_scheduled BOOLEAN DEFAULT FALSE,
            change_reason VARCHAR(200),
            notes TEXT,
            created_by INT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            INDEX idx_pp_product_type (product_id, price_type),
            INDEX idx_pp_active (product_id, is_active)
        )"""),
    ("price_alerts", """CREATE TABLE IF NOT EXISTS price_alerts (
            id INT AUTO_INCREMENT PRIMARY KEY,
            product_id INT NOT NULL,
            alert_type VARCHAR(30) NOT NULL,
            message TEXT NOT NULL,
            severity VARCHAR(10) DEFAULT 'warning',
            is_read BOOLEAN DEFAULT FALSE,
            email_sent BOOLEAN DEFAULT FALSE,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            INDEX idx_pa_unread (is_read)
        )"""),
    ("stock_adjustments", """CREATE TABLE IF NOT EXISTS stock_adjustments (
            id INT AUTO_INCREMENT PRIMARY KEY,
            adjustment_number VARCHAR(30) UNIQUE,
            warehouse_id INT NOT NULL,
            product_id INT NOT NULL,
            adjustment_type VARCHAR(10),
            quantity DECIMAL(12,3) NOT NULL,
            unit_cost DECIMAL(12,2),
            reason TEXT,
            notes TEXT,
            adjustment_date DATE,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            created_by INT,
            updated_by INT
        )"""),
    ("stock_writeoffs", """CREATE TABLE IF NOT EXISTS stock_writeoffs (
            id INT AUTO_INCREMENT PRIMARY KEY,
            writeoff_number VARCHAR(30) UNIQUE,
            warehouse_id INT NOT NULL,
            product_id INT NOT NULL,
            quantity DECIMAL(12,3) NOT NULL,
            reason_type VARCHAR(30),
            reason_detail TEXT,
            writeoff_date DATE,
            status VARCHAR(20) DEFAULT 'pending',
            approved_by INT,
            approved_at DATETIME,
            admin_notes TEXT,
            notes TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            created_by INT,
            updated_by INT
        )"""),
    ("active_sessions", """CREATE TABLE IF NOT EXISTS `active_sessions` (
        id INT AUTO_INCREMENT PRIMARY KEY,
        user_id INT NOT NULL,
        ip_address VARCHAR(45),
        device_info VARCHAR(200),
        location VARCHAR(100),
        token_hash VARCHAR(255),
        login_time DATETIME,
        last_seen DATETIME,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
    )"""),
    ("login_history", """CREATE TABLE IF NOT EXISTS `login_history` (
        id BIGINT AUTO_INCREMENT PRIMARY KEY,
        user_id INT NOT NULL,
        username VARCHAR(50) NOT NULL,
        full_name VARCHAR(100),
        login_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
        logout_at DATETIME,
        session_duration_seconds INT,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        INDEX idx_lh_user (user_id),
        INDEX idx_lh_username (username),
        INDEX idx_lh_login_at (login_at),
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
    )"""),
    ("company_settings", """CREATE TABLE IF NOT EXISTS `company_settings` (
                id INT AUTO_INCREMENT PRIMARY KEY,
                company_name VARCHAR(200) NOT NULL DEFAULT 'My Company',
                gstin VARCHAR(15), state VARCHAR(100), state_code SMALLINT DEFAULT 0,
                address_line1 VARCHAR(200), address_line2 VARCHAR(200),
                city VARCHAR(100), pincode VARCHAR(6), phone VARCHAR(15), email VARCHAR(100),
                logo_path VARCHAR(255), signature_path VARCHAR(255), terms_conditions TEXT,
                b2b_invoice_prefix VARCHAR(20) DEFAULT 'BINV',
                b2c_invoice_prefix VARCHAR(20) DEFAULT 'CINV',
                quotation_prefix VARCHAR(20) DEFAULT 'QT',
                challan_prefix VARCHAR(20) DEFAULT 'DC',
                credit_note_prefix VARCHAR(20) DEFAULT 'CN',
                eway_threshold DECIMAL(12,2) DEFAULT 50000,
                bank_stock_margin DECIMAL(5,2) DEFAULT 25.00,
                default_min_margin_pct DECIMAL(5,2) DEFAULT 10.00,
                financial_year_start SMALLINT DEFAULT 4,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                created_by INT, updated_at DATETIME, updated_by INT
            )"""),
            ("invoice_sequences", """CREATE TABLE IF NOT EXISTS `invoice_sequences` (
                id INT AUTO_INCREMENT PRIMARY KEY,
                document_type VARCHAR(30) NOT NULL,
                prefix VARCHAR(20) DEFAULT 'INV',
                financial_year VARCHAR(7),
                last_number INT DEFAULT 0,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )"""),
            ("accounts", """CREATE TABLE IF NOT EXISTS `accounts` (
                id INT AUTO_INCREMENT PRIMARY KEY,
                account_code VARCHAR(20) UNIQUE NOT NULL,
                name VARCHAR(100) NOT NULL DEFAULT '',
                account_type VARCHAR(30) NOT NULL DEFAULT 'asset',
                parent_id INT, is_system BOOLEAN DEFAULT FALSE,
                is_active BOOLEAN DEFAULT TRUE,
                opening_balance DECIMAL(14,2) DEFAULT 0,
                current_balance DECIMAL(14,2) DEFAULT 0,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                created_by INT, updated_at DATETIME, updated_by INT
            )"""),
            ]
            for tbl, sql in _tables:
                try:
                    c.execute(text(sql))
                    c.commit()
                except Exception:
                    pass

            # Column type fixes (Integer → Numeric where schema expects Decimal)
            type_changes = [
                # products.low_stock_threshold was INT; ProductCreate accepts Decimal.
                # Migrate to NUMERIC(12,3) so fractional thresholds aren't truncated.
                ("products", "low_stock_threshold", "DECIMAL(12,3) NOT NULL DEFAULT 0"),
                # product_cost_history.recorded_at was added by an earlier auto-migrate
                # as nullable / no default, so legacy rows have NULL. The ORM model
                # declares NOT NULL + server_default=now(); align the DB to match.
                ("product_cost_history", "recorded_at", "DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP"),
                # categories.prefix drifted to varchar(4) on some live DBs; the ORM
                # model and Pydantic schemas allow up to 10 chars, so a 5-10 char
                # prefix raised "Data too long for column 'prefix'". Widen to match.
                ("categories", "prefix", "VARCHAR(10) NOT NULL"),
            ]
            for table, col, defn in type_changes:
                try:
                    c.execute(text(f"ALTER TABLE `{table}` MODIFY COLUMN `{col}` {defn}"))
                    c.commit()
                except Exception:
                    pass

            # One-time data backfill — set recorded_at to created_at (or NOW()) for
            # any legacy rows that slipped in before the NOT NULL constraint above.
            # Idempotent — once no NULLs remain, this is a no-op.
            try:
                c.execute(text(
                    "UPDATE product_cost_history "
                    "SET recorded_at = COALESCE(recorded_at, CURRENT_TIMESTAMP) "
                    "WHERE recorded_at IS NULL"
                ))
                c.commit()
            except Exception:
                pass

            # Backfill bank_stock_statements.statement_month from statement_date
            # (YYYY-MM) for any rows that pre-date the column addition.  After
            # backfill, enforce NOT NULL so the ORM model constraint is satisfied.
            # margin_percent defaults to 25.00 where still NULL.
            try:
                c.execute(text(
                    "UPDATE bank_stock_statements "
                    "SET statement_month = DATE_FORMAT(statement_date, '%Y-%m') "
                    "WHERE statement_month IS NULL AND statement_date IS NOT NULL"
                ))
                c.commit()
            except Exception:
                pass
            try:
                c.execute(text(
                    "ALTER TABLE bank_stock_statements "
                    "MODIFY COLUMN statement_month VARCHAR(7) NOT NULL"
                ))
                c.commit()
            except Exception:
                pass
            try:
                c.execute(text(
                    "UPDATE bank_stock_statements "
                    "SET margin_percent = 25.00 WHERE margin_percent IS NULL"
                ))
                c.commit()
            except Exception:
                pass
    except Exception:
        pass  # never crash startup


@asynccontextmanager
async def lifespan(app: FastAPI):
    _auto_migrate()
    os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
    os.makedirs(settings.EXPORT_DIR, exist_ok=True)
    # Activate any scheduled prices whose effective_from <= today.
    # Otherwise they only activate when an invoice/purchase is created.
    try:
        from app.db.session import SessionLocal
        from app.services.price_history_service import activate_scheduled_prices
        _db = SessionLocal()
        try:
            count = activate_scheduled_prices(_db)
            if count:
                _db.commit()
                print(f"[STARTUP] Activated {count} scheduled price(s)")
        finally:
            _db.close()
    except Exception as _e:
        print(f"[STARTUP] price activation skipped: {_e}")
    # Prune ActiveSession rows whose refresh token has expired (older than TTL).
    # These rows can never be used again — the JWT exp has already passed.
    try:
        from datetime import datetime, timedelta
        from app.db.session import SessionLocal
        from app.models.models import ActiveSession
        _db = SessionLocal()
        try:
            cutoff = datetime.utcnow() - timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
            deleted = _db.query(ActiveSession).filter(ActiveSession.login_time < cutoff).delete()
            if deleted:
                _db.commit()
                print(f"[STARTUP] Pruned {deleted} expired session(s)")
        finally:
            _db.close()
    except Exception as _e:
        print(f"[STARTUP] session pruning skipped: {_e}")
    yield


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    docs_url="/api/docs" if settings.DEBUG else None,
    redoc_url="/api/redoc" if settings.DEBUG else None,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.get_allowed_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


app.include_router(api_router)

# Serve uploaded files
import os
os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=settings.UPLOAD_DIR), name="uploads")


@app.get("/health")
async def health():
    return {"status": "ok", "version": settings.APP_VERSION}


# Serve frontend static assets & SPA fallback (production / Railway)
from fastapi.responses import FileResponse
dist_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../frontend/dist"))
if not os.path.exists(dist_dir):
    dist_dir = os.path.abspath("./frontend/dist")

if os.path.exists(dist_dir):
    assets_dir = os.path.join(dist_dir, "assets")
    if os.path.exists(assets_dir):
        app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        if full_path.startswith("api") or full_path.startswith("uploads"):
            return JSONResponse(status_code=404, content={"detail": "Not found"})
        file_path = os.path.join(dist_dir, full_path)
        if full_path and os.path.isfile(file_path):
            return FileResponse(file_path)
        return FileResponse(os.path.join(dist_dir, "index.html"))
