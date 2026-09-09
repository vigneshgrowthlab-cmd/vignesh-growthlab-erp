from fastapi import APIRouter, Depends, Query, UploadFile, File, HTTPException, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from typing import Optional
from datetime import date
import io
import os
import shutil
import uuid

from app.db.session import get_db
from app.models.models import User, UserRole, Product
from app.core.config import settings
from app.core.security import get_current_user, require_admin, require_admin_or_accountant
from app.services.security_service import ActivityLogService
from app.utils.helpers import get_client_ip
from app.schemas.products import (
    CategoryCreate, CategoryUpdate, ProductCreate, ProductUpdate,
    StockAdjustmentCreate, AlertApproveRequest, BulkPriceUpdate
)
from app.services.product_service import (
    CategoryService, ProductService, CostTrackingService, StockService
)

router = APIRouter(prefix="/products", tags=["products"])
cat_router = APIRouter(prefix="/categories", tags=["categories"])


# ─── Category Endpoints ──────────────────────────────────────

@cat_router.get("/")
async def list_categories(
    include_inactive: bool = False,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    cats = CategoryService.get_all(db, include_inactive)
    return [
        {
            "id": c.id, "name": c.name, "prefix": c.prefix,
            "default_hsn": c.default_hsn, "default_gst_percent": c.default_gst_percent,
            "description": c.description, "is_active": c.is_active,
            "sequence_counter": c.sequence_counter,
            "product_count": len(c.products),
        }
        for c in cats
    ]


@cat_router.post("/", status_code=201)
async def create_category(
    payload: CategoryCreate,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return CategoryService.create(db, payload, current_user.id)


@cat_router.get("/{category_id}")
async def get_category(
    category_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    return CategoryService.get_by_id(db, category_id)


@cat_router.put("/{category_id}")
async def update_category(
    category_id: int,
    payload: CategoryUpdate,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return CategoryService.update(db, category_id, payload, current_user.id)


@cat_router.delete("/{category_id}")
async def delete_category(
    category_id: int,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return CategoryService.delete(db, category_id, current_user.id)


# ─── Product Endpoints ───────────────────────────────────────

@router.get("/")
async def list_products(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=500),
    category_id: Optional[int] = None,
    search: Optional[str] = None,
    is_active: Optional[bool] = True,
    low_stock_only: bool = False,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = ProductService.list_products(db, page, page_size, category_id, search, is_active, low_stock_only)
    # Hide purchase cost from sales users
    if current_user.role == UserRole.sales:
        for item in result["items"]:
            item.pop("purchase_cost", None)
    return result


@router.post("/", status_code=201)
async def create_product(
    payload: ProductCreate,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return ProductService.create(db, payload, current_user.id)


@router.get("/search/billing")
async def search_for_billing(
    q: str = Query(..., min_length=2),
    warehouse_id: Optional[int] = None,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    return ProductService.search_for_billing(db, q, warehouse_id)


@router.get("/template/csv")
async def download_csv_template(_: User = Depends(require_admin)):
    content = ProductService.get_csv_template()
    return StreamingResponse(
        io.StringIO(content),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=product_upload_template.csv"}
    )


@router.get("/export/csv")
async def export_products_csv(
    request: Request,
    category_id: Optional[int] = Query(None),
    search: Optional[str] = Query(None),
    is_active: Optional[bool] = Query(None),
    current_user: User = Depends(require_admin_or_accountant),
    db: Session = Depends(get_db),
):
    content = ProductService.export_csv(db, category_id, search, is_active)
    ActivityLogService.log(db, current_user.id, "export",
                           "Exported products to CSV", ip_address=get_client_ip(request))
    return StreamingResponse(
        io.StringIO(content),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=products_export.csv"}
    )


@router.post("/bulk-upload")
async def bulk_upload_products(
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
    return ProductService.bulk_upload(db, content, current_user.id)


@router.post("/bulk-price-update")
async def bulk_price_update(
    payload: BulkPriceUpdate,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Apply one price (immediate or scheduled) to many products at once.

    Reuses the price-history engine: each product gets a versioned
    product_prices row, the product column is updated (or scheduled for a
    future effective_from), and below-cost / low-margin alerts fire as usual.
    """
    return ProductService.bulk_price_update(db, payload, current_user.id)


@router.get("/{product_id}")
async def get_product(
    product_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = ProductService.get_by_id(db, product_id)
    if current_user.role == UserRole.sales:
        result.pop("purchase_cost", None)
        result.pop("profit_percent", None)
        result.pop("profit_value", None)
    return result


@router.put("/{product_id}")
async def update_product(
    product_id: int,
    payload: ProductUpdate,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return ProductService.update(db, product_id, payload, current_user.id)


# ─── Product Image (optional) ────────────────────────────────

_IMAGE_TYPES = ("image/png", "image/jpeg", "image/jpg", "image/webp", "image/gif")


@router.post("/{product_id}/image")
async def upload_product_image(
    product_id: int,
    file: UploadFile = File(...),
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Attach an image to a product. Optional — products work without one."""
    if file.content_type not in _IMAGE_TYPES:
        raise HTTPException(status_code=400, detail="Only image files are allowed (PNG, JPG, WebP, GIF)")
    if file.size and file.size > settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024:
        raise HTTPException(
            status_code=413,
            detail=f"File too large. Maximum allowed size is {settings.MAX_UPLOAD_SIZE_MB} MB",
        )
    if not db.query(Product.id).filter(Product.id == product_id).first():
        raise HTTPException(status_code=404, detail="Product not found")

    upload_dir = os.path.join(settings.UPLOAD_DIR, "products")
    os.makedirs(upload_dir, exist_ok=True)
    ext = (file.filename.rsplit(".", 1)[-1] if "." in file.filename else "png").lower()
    filename = f"prod_{product_id}_{uuid.uuid4().hex[:8]}.{ext}"
    with open(os.path.join(upload_dir, filename), "wb") as f_out:
        shutil.copyfileobj(file.file, f_out)

    return ProductService.update_image(db, product_id, f"/uploads/products/{filename}", current_user.id)


@router.delete("/{product_id}/image")
async def delete_product_image(
    product_id: int,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Remove a product's image reference."""
    return ProductService.update_image(db, product_id, None, current_user.id)


# ─── Stock Endpoints ─────────────────────────────────────────

@router.get("/{product_id}/stock")
async def get_product_stock(
    product_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    return StockService.get_warehouse_stock(db, product_id)


@router.get("/{product_id}/fifo-layers")
async def get_fifo_layers(
    product_id: int,
    warehouse_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin_or_accountant),
):
    return StockService.get_fifo_layers(db, product_id, warehouse_id)


@router.post(
    "/stock/adjust",
    deprecated=True,
    summary="DEPRECATED: use POST /api/v1/stock-adjustments/ instead",
)
async def adjust_stock(
    payload: StockAdjustmentCreate,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Deprecated alias kept for backward compatibility. New code should call
    POST /api/v1/stock-adjustments/ (warehouse module). Both paths are now
    backed by FIFO-correct logic, but only one will be maintained going forward."""
    import logging
    logging.getLogger(__name__).warning(
        "Deprecated endpoint /api/v1/products/stock/adjust called by user_id=%s",
        current_user.id,
    )
    return StockService.adjust_stock(db, payload, current_user.id)


@router.get("/stock/ageing")
async def stock_ageing_report(
    warehouse_id: Optional[int] = None,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin_or_accountant),
):
    return StockService.get_ageing_report(db, warehouse_id)


# ─── Cost Trend Endpoints ────────────────────────────────────

@router.get("/{product_id}/cost-trend")
async def get_cost_trend(
    product_id: int,
    vendor_id: Optional[int] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin_or_accountant),
):
    return CostTrackingService.get_trend(db, product_id, vendor_id, date_from, date_to)


@router.get("/alerts/pending")
async def get_pending_alerts(
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    from app.models.models import CostAlert, Product
    alerts = db.query(CostAlert).filter(CostAlert.is_resolved == False)\
               .order_by(CostAlert.created_at.desc()).all()
    result = []
    for a in alerts:
        p = db.query(Product).filter(Product.id == a.product_id).first()
        result.append({
            "id": a.id, "product_id": a.product_id,
            "part_code": p.part_code if p else None,
            "part_name": p.part_name if p else None,
            "alert_type": a.alert_type, "message": a.message,
            "old_value": a.old_value, "new_value": a.new_value,
            "suggested_price": a.suggested_price, "is_resolved": a.is_resolved,
            "created_at": a.created_at,
        })
    return result


@router.post("/alerts/{alert_id}/resolve")
async def resolve_alert(
    alert_id: int,
    payload: AlertApproveRequest,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return CostTrackingService.approve_price_suggestion(db, alert_id, payload.approve, current_user)
