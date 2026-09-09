from fastapi import APIRouter, Depends, Query, HTTPException, UploadFile, File
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from typing import Optional
from datetime import date
import io

from app.db.session import get_db
from app.models.models import User
from app.core.config import settings
from app.core.security import get_current_user, require_admin, require_admin_or_accountant
from app.schemas.purchase import (
    VendorCreate, VendorUpdate, VendorAddressCreate,
    PurchaseCreate, PurchaseUpdate, VendorPaymentCreate
)
from app.services.vendor_service import VendorService
from app.services.purchase_service import PurchaseService, VendorPaymentService

# ── Vendor Router ─────────────────────────────────────────────
vendor_router = APIRouter(prefix="/vendors", tags=["vendors"])

@vendor_router.get("/")
async def list_vendors(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=500),
    search: Optional[str] = None,
    is_active: Optional[bool] = True,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    return VendorService.list_vendors(db, page, page_size, search, is_active)


@vendor_router.post("/", status_code=201)
async def create_vendor(
    payload: VendorCreate,
    current_user: User = Depends(require_admin_or_accountant),
    db: Session = Depends(get_db),
):
    return VendorService.create(db, payload, current_user.id)


@vendor_router.get("/import/template")
async def download_vendor_import_template(_: User = Depends(require_admin_or_accountant)):
    content = VendorService.get_import_csv_template()
    return StreamingResponse(
        io.StringIO(content),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=vendor_import_template.csv"},
    )


@vendor_router.post("/import")
async def bulk_import_vendors(
    file: UploadFile = File(...),
    current_user: User = Depends(require_admin_or_accountant),
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
    return VendorService.bulk_import(db, content, current_user.id)


@vendor_router.get("/gstin-lookup/{gstin}")
async def lookup_gstin(
    gstin: str,
    _: User = Depends(get_current_user),
):
    return await VendorService.fetch_gstin_details(gstin)


@vendor_router.get("/{vendor_id}")
async def get_vendor(
    vendor_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    return VendorService.get_by_id(db, vendor_id)


@vendor_router.put("/{vendor_id}")
async def update_vendor(
    vendor_id: int,
    payload: VendorUpdate,
    current_user: User = Depends(require_admin_or_accountant),
    db: Session = Depends(get_db),
):
    # Activating / deactivating a vendor is reserved to admins & super-admins.
    # Accountants may edit every other vendor field.
    if payload.is_active is not None:
        role = str(getattr(current_user, "role", "")).lower().replace("userrole.", "")
        if role not in ("admin", "super_admin"):
            raise HTTPException(
                status_code=403,
                detail="Only admins may change a vendor's active status",
            )
    return VendorService.update(db, vendor_id, payload, current_user.id)


@vendor_router.post("/{vendor_id}/addresses", status_code=201)
async def add_vendor_address(
    vendor_id: int,
    payload: VendorAddressCreate,
    current_user: User = Depends(require_admin_or_accountant),
    db: Session = Depends(get_db),
):
    return VendorService.add_address(db, vendor_id, payload, current_user.id)


@vendor_router.get("/{vendor_id}/ledger")
async def get_vendor_ledger(
    vendor_id: int,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=500),
    db: Session = Depends(get_db),
    _: User = Depends(require_admin_or_accountant),
):
    return VendorService.get_ledger(db, vendor_id, page, page_size)


# ── Purchase Router ───────────────────────────────────────────
purchase_router = APIRouter(prefix="/purchases", tags=["purchases"])

@purchase_router.get("/")
async def list_purchases(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=500),
    vendor_id: Optional[int] = None,
    financial_year: Optional[str] = None,
    search: Optional[str] = None,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin_or_accountant),
):
    return PurchaseService.list_purchases(db, page, page_size, vendor_id, financial_year, search)


@purchase_router.post("/", status_code=201)
async def create_purchase(
    payload: PurchaseCreate,
    current_user: User = Depends(require_admin_or_accountant),
    db: Session = Depends(get_db),
):
    return PurchaseService.create(db, payload, current_user.id)


@purchase_router.get("/{purchase_id}")
async def get_purchase(
    purchase_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin_or_accountant),
):
    return PurchaseService.get_by_id(db, purchase_id)


@purchase_router.put("/{purchase_id}")
async def update_purchase(
    purchase_id: int,
    payload: PurchaseUpdate,
    current_user: User = Depends(require_admin_or_accountant),
    db: Session = Depends(get_db),
):
    return PurchaseService.update(db, purchase_id, payload, current_user.id)


@purchase_router.post("/{purchase_id}/cancel")
async def cancel_purchase(
    purchase_id: int,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return PurchaseService.cancel(db, purchase_id, current_user.id)


# ── Vendor Payment Router ─────────────────────────────────────
payment_router = APIRouter(prefix="/vendor-payments", tags=["vendor-payments"])

@payment_router.get("/")
async def list_vendor_payments(
    vendor_id: Optional[int] = None,
    purchase_id: Optional[int] = None,
    financial_year: Optional[str] = None,
    include_voided: bool = False,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=500),
    db: Session = Depends(get_db),
    _: User = Depends(require_admin_or_accountant),
):
    return VendorPaymentService.list_payments(
        db, vendor_id, purchase_id, financial_year, page, page_size,
        include_voided=include_voided,
    )


@payment_router.post("/", status_code=201)
async def create_vendor_payment(
    payload: VendorPaymentCreate,
    current_user: User = Depends(require_admin_or_accountant),
    db: Session = Depends(get_db),
):
    return VendorPaymentService.create(db, payload, current_user.id)


@payment_router.delete("/{payment_id}")
async def void_vendor_payment(
    payment_id: int,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return VendorPaymentService.void(db, payment_id, current_user.id)
