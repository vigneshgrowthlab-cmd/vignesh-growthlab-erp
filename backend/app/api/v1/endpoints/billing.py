from fastapi import APIRouter, Depends, Query, HTTPException, UploadFile, File
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from typing import Optional
from datetime import date
import io

from sqlalchemy import func, desc
from app.db.session import get_db
from app.models.models import User, Invoice, Customer, Warehouse
from app.core.config import settings
from app.core.security import (
    get_current_user, require_admin, require_admin_or_accountant,
    is_super_admin,
)
from app.schemas.billing import (
    CustomerCreate, CustomerUpdate, CustomerAddressCreate, CustomerBulkStatus,
    InvoiceCreate, CustomerPaymentCreate, CreditNoteCreate
)
from app.services.customer_service import CustomerService
from app.services.billing_service import BillingService, CustomerPaymentService

# ── Customer Router ───────────────────────────────────────────
customer_router = APIRouter(prefix="/customers", tags=["customers"])

@customer_router.get("/")
async def list_customers(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=500),
    search: Optional[str] = None,
    is_active: Optional[bool] = True,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    return CustomerService.list_customers(db, page, page_size, search, is_active)


@customer_router.post("/", status_code=201)
async def create_customer(
    payload: CustomerCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return CustomerService.create(db, payload, current_user.id)


@customer_router.post("/bulk-status")
async def bulk_set_customer_status(
    payload: CustomerBulkStatus,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return CustomerService.bulk_set_status(
        db, payload.customer_ids, payload.is_active, current_user.id
    )


@customer_router.get("/import/template")
async def download_customer_import_template(_: User = Depends(require_admin)):
    content = CustomerService.get_import_csv_template()
    return StreamingResponse(
        io.StringIO(content),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=customer_import_template.csv"},
    )


@customer_router.post("/import")
async def bulk_import_customers(
    file: UploadFile = File(...),
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    if not file.filename.endswith(".csv"):
        raise HTTPException(status_code=400, detail="Only CSV files accepted")
    max_bytes = settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024
    content_bytes = await file.read()
    if len(content_bytes) > max_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"File too large. Maximum allowed size is {settings.MAX_UPLOAD_SIZE_MB} MB",
        )
    try:
        content = content_bytes.decode("utf-8")
    except UnicodeDecodeError:
        raise HTTPException(status_code=400, detail="CSV must be UTF-8 encoded")
    return CustomerService.bulk_import(db, content, current_user.id)


@customer_router.get("/gstin-lookup/{gstin}")
async def lookup_gstin(
    gstin: str,
    _: User = Depends(get_current_user),
):
    return await CustomerService.fetch_gstin_details(gstin)


@customer_router.get("/{customer_id}")
async def get_customer(
    customer_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    return CustomerService.get_by_id(db, customer_id)


@customer_router.put("/{customer_id}")
async def update_customer(
    customer_id: int,
    payload: CustomerUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    # Sensitive fields that only admins may change. Sales/accountant could
    # otherwise pump credit_limit and bypass the credit-limit check on
    # invoice creation.
    admin_only_fields = {"credit_limit", "credit_days", "gst_status", "is_active"}
    role = str(getattr(current_user, "role", "")).lower().replace("userrole.", "")
    if role not in ("admin", "super_admin"):
        sent = payload.dict(exclude_none=True)
        forbidden = admin_only_fields.intersection(sent.keys())
        if forbidden:
            raise HTTPException(
                status_code=403,
                detail=f"Only admins may modify: {', '.join(sorted(forbidden))}",
            )
    return CustomerService.update(db, customer_id, payload, current_user.id)


@customer_router.post("/{customer_id}/addresses", status_code=201)
async def add_customer_address(
    customer_id: int,
    payload: CustomerAddressCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return CustomerService.add_address(db, customer_id, payload, current_user.id)


@customer_router.put("/{customer_id}/addresses/{address_id}")
async def update_customer_address(
    customer_id: int,
    address_id: int,
    payload: CustomerAddressCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return CustomerService.update_address(db, customer_id, address_id, payload, current_user.id)


@customer_router.get("/{customer_id}/ledger")
async def get_customer_ledger(
    customer_id: int,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=500),
    db: Session = Depends(get_db),
    _: User = Depends(require_admin_or_accountant),
):
    return CustomerService.get_ledger(db, customer_id, page, page_size)


@customer_router.get("/{customer_id}/statement")
async def get_customer_statement(
    customer_id: int,
    date_from: date = Query(...),
    date_to: date = Query(...),
    db: Session = Depends(get_db),
    _: User = Depends(require_admin_or_accountant),
):
    return CustomerService.generate_statement(db, customer_id, date_from, date_to)


@customer_router.get("/{customer_id}/last-price/{product_id}")
async def get_last_price(
    customer_id: int,
    product_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    price = CustomerService.get_last_price(db, customer_id, product_id)
    return {"last_price": price}


# ── Invoice Router ────────────────────────────────────────────
invoice_router = APIRouter(prefix="/invoices", tags=["invoices"])

@invoice_router.get("/")
async def list_invoices(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=500),
    customer_id: Optional[int] = None,
    document_type: Optional[str] = None,
    financial_year: Optional[str] = None,
    search: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # DC visibility RBAC: non-super-admin users mapped to a warehouse only see
    # DCs where they're source OR destination. Other document types unaffected.
    restrict_wh = None
    if not is_super_admin(current_user):
        uwh = getattr(current_user, "warehouse_id", None)
        if uwh:
            try:
                restrict_wh = int(uwh)
            except (TypeError, ValueError):
                pass
    return BillingService.list_invoices(
        db, page, page_size, customer_id, document_type, financial_year, search,
        restrict_to_warehouse_id=restrict_wh,
    )


@invoice_router.post("/", status_code=201)
async def create_invoice(
    payload: InvoiceCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return BillingService.create(db, payload, current_user.id, current_user.role)


@invoice_router.get("/{invoice_id}")
async def get_invoice(
    invoice_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    return BillingService.get_by_id(db, invoice_id)


@invoice_router.post("/{invoice_id}/cancel")
async def cancel_invoice(
    invoice_id: int,
    payload: dict,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    reason = payload.get("reason", "")
    if not reason:
        raise HTTPException(status_code=400, detail="Cancellation reason is required")
    return BillingService.cancel(db, invoice_id, reason, current_user.id)


@invoice_router.post("/{invoice_id}/convert-to-invoice", status_code=201)
async def convert_quotation_to_invoice(
    invoice_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin_or_accountant),
):
    role = str(getattr(current_user, "role", "")).lower().replace("userrole.", "")
    return BillingService.convert_quotation(db, invoice_id, current_user.id, role)


@invoice_router.post("/{invoice_id}/mark-invoiced")
async def mark_quotation_invoiced(
    invoice_id: int,
    payload: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin_or_accountant),
):
    """Mark a quotation as invoiced after manual invoice creation."""
    quot = db.query(Invoice).filter(Invoice.id == invoice_id).first()
    if not quot:
        raise HTTPException(status_code=404, detail="Quotation not found")
    # Let errors propagate instead of silently swallowing them.
    quot.quotation_status = "invoiced"
    quot.original_invoice_id = payload.get("invoice_id")
    db.commit()
    return {"status": "ok"}


@invoice_router.post("/credit-note", status_code=201)
async def create_credit_note(
    payload: CreditNoteCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return BillingService.create_credit_note(db, payload, current_user.id, current_user.role)


@invoice_router.get("/{invoice_id}/whatsapp")
async def get_whatsapp_url(
    invoice_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    return BillingService.get_whatsapp_url(invoice_id, db)


# ── Customer Payment Router ───────────────────────────────────
receipt_router = APIRouter(prefix="/receipts", tags=["receipts"])

@receipt_router.get("/")
async def list_receipts(
    customer_id: Optional[int] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=500),
    db: Session = Depends(get_db),
    _: User = Depends(require_admin_or_accountant),
):
    return CustomerPaymentService.list_payments(db, customer_id, page, page_size)


@receipt_router.post("/", status_code=201)
async def create_receipt(
    payload: CustomerPaymentCreate,
    current_user: User = Depends(require_admin_or_accountant),
    db: Session = Depends(get_db),
):
    return CustomerPaymentService.create(db, payload, current_user.id)


@invoice_router.get("/list/delivery-challans")
async def list_delivery_challans(
    source_warehouse_id: Optional[int] = Query(None),
    destination_warehouse_id: Optional[int] = Query(None),
    unlinked_only: bool = Query(True),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """List DCs for linking to stock transfers.

    Visibility rules:
      - super-admin: sees all DCs.
      - Any other user WITH a mapped warehouse: only sees DCs where
        warehouse_id = user.warehouse_id OR dc_destination_warehouse_id = user.warehouse_id.
      - Other users without a mapping: see all (unchanged).
    """
    import json
    from app.models.models import Warehouse

    # Resolve current user's warehouse mapping (used for RBAC visibility filter)
    user_wh = None
    is_super = is_super_admin(current_user)
    if not is_super:
        uwh = getattr(current_user, "warehouse_id", None)
        if uwh:
            try:
                user_wh = int(uwh)
            except (TypeError, ValueError):
                pass

    q = db.query(Invoice).filter(
        Invoice.is_cancelled == False,
        func.lower(Invoice.document_type).in_(["delivery_challan", "documenttype.delivery_challan"])
    )
    if source_warehouse_id:
        q = q.filter(Invoice.warehouse_id == source_warehouse_id)

    # Visibility filter: non-super-admin user mapped to a warehouse only sees
    # DCs where they are source OR destination.
    if not is_super and user_wh is not None:
        from sqlalchemy import or_ as _or, text as _sqltxt
        # Use raw column to dodge any ORM-vs-auto-migrated mismatch
        q = q.filter(_or(
            Invoice.warehouse_id == user_wh,
            _sqltxt("invoices.dc_destination_warehouse_id = :uwh").bindparams(uwh=user_wh),
        ))

    invoices = q.order_by(desc(Invoice.invoice_date)).all()

    if unlinked_only:
        from app.models.models import StockTransfer
        linked = set()
        transfers = db.query(StockTransfer).filter(StockTransfer.dc_ids.isnot(None)).all()
        for t in transfers:
            try:
                ids = json.loads(t.dc_ids or "[]")
                linked.update(ids)
            except Exception:
                pass
        invoices = [i for i in invoices if i.id not in linked]

    from sqlalchemy import text as _sql
    result = []
    for inv in invoices:
        cust = db.query(Customer).filter(Customer.id == inv.customer_id).first() if inv.customer_id else None
        src_wh = db.query(Warehouse).filter(Warehouse.id == inv.warehouse_id).first()
        # Read DC-specific fields via raw SQL
        try:
            dc_row = db.execute(_sql(
                "SELECT dc_destination_warehouse_id, vehicle_number, dc_status "
                "FROM invoices WHERE id = :id"
            ), {"id": inv.id}).fetchone()
            dst_wh_id = dc_row[0] if dc_row else None
            vnum = dc_row[1] if dc_row else None
            dc_status = dc_row[2] if dc_row else "pending"
        except Exception:
            dst_wh_id = getattr(inv, 'dc_destination_warehouse_id', None)
            vnum = getattr(inv, 'vehicle_number', None)
            dc_status = getattr(inv, 'dc_status', 'pending')
        dst_wh = db.query(Warehouse).filter(Warehouse.id == dst_wh_id).first() if dst_wh_id else None
        result.append({
            "id": inv.id,
            "invoice_number": inv.invoice_number,
            "invoice_date": str(inv.invoice_date) if inv.invoice_date else None,
            "customer_name": cust.trade_name if cust else None,
            "vehicle_number": vnum,
            "dc_status": dc_status or "pending",
            "total_amount": float(inv.total_amount or 0),
            "warehouse_id": inv.warehouse_id,
            "source_warehouse_name": src_wh.name if src_wh else None,
            "dc_destination_warehouse_id": dst_wh_id,
            "destination_warehouse_name": dst_wh.name if dst_wh else None,
        })
    return result


@invoice_router.post("/{invoice_id}/cancel-dc")
async def cancel_dc(
    invoice_id: int,
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    """Cancel a DC with Pending status."""
    from sqlalchemy import text as _sql
    inv = db.query(Invoice).filter(Invoice.id == invoice_id).first()
    if not inv:
        raise HTTPException(status_code=404, detail="Invoice not found")
    doc_type = str(inv.document_type).lower().replace("documenttype.", "")
    if doc_type != "delivery_challan":
        raise HTTPException(status_code=400, detail="Only Delivery Challans can be cancelled via this endpoint")
    try:
        row = db.execute(_sql("SELECT dc_status FROM invoices WHERE id=:id"), {"id": invoice_id}).fetchone()
        dc_status = row[0] if row else None
    except Exception:
        dc_status = getattr(inv, 'dc_status', None)
    if dc_status != 'pending':
        raise HTTPException(status_code=400, detail=f"Only Pending DCs can be cancelled. Current status: {dc_status}")
    db.execute(_sql("UPDATE invoices SET dc_status='cancelled', is_cancelled=1 WHERE id=:id"), {"id": invoice_id})
    db.commit()
    return {"status": "cancelled", "invoice_id": invoice_id}



@invoice_router.patch("/{invoice_id}/eway-bill")
async def update_eway_bill(
    invoice_id: int,
    payload: dict,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Manually record portal-generated e-way bill details on an invoice.

    Accepts eway_bill_number (required) plus optional vehicle_number,
    transporter_name, transport_mode, distance_km, valid_upto. Sets
    eway_bill_status and writes an EWayBillLog audit row.
    """
    return BillingService.set_eway_manual(db, invoice_id, payload, current_user.id)


@invoice_router.patch("/{invoice_id}/einvoice")
async def update_einvoice(
    invoice_id: int,
    payload: dict,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Manually record portal-generated e-invoice details on an invoice.

    Accepts irn (required) plus optional ack_number, ack_date, signed_qr.
    Validation is advisory only (returned as 'warnings'); the portal has
    already accepted the invoice. Editable until the invoice is cancelled.
    """
    return BillingService.set_einvoice_manual(db, invoice_id, payload, current_user.id)


@invoice_router.patch("/{invoice_id}/eway-bill/vehicle")
async def update_eway_vehicle(
    invoice_id: int,
    payload: dict,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Record a Part-B / vehicle update for an existing e-way bill (Rule 138(5)).

    Accepts vehicle_number (required), transport_mode, reason.
    """
    return BillingService.update_eway_vehicle(db, invoice_id, payload, current_user.id)


@invoice_router.post("/{invoice_id}/eway-bill/cancel")
async def cancel_eway_bill(
    invoice_id: int,
    payload: dict,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Record cancellation of an e-way bill (Rule 138(9), within 24h).

    Accepts reason. The 24-hour window is advisory (returned as 'warnings').
    """
    return BillingService.cancel_eway_manual(db, invoice_id, payload, current_user.id)