import io
from datetime import date
from fastapi import APIRouter, Depends, Query, HTTPException, UploadFile, File
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from typing import Optional

from app.core.config import settings
from app.db.session import get_db
from app.models.models import User
from app.core.security import (
    get_current_user, require_admin, require_admin_or_accountant,
    require_super_admin, require_warehouse_ops, is_super_admin,
)
from app.schemas.warehouse import (
    WarehouseCreate, WarehouseUpdate,
    StockTransferCreate, StockAdjustmentCreate,
    StockWriteoffCreate, StockWriteoffApprove,
    OpeningBalanceCreate,
)
from app.services.warehouse_service import (
    WarehouseService, StockTransferService,
    StockAdjustmentService, StockWriteoffService,
    StockAgeingService, OpeningBalanceService,
)


def _user_warehouse_id(user: User) -> Optional[int]:
    val = getattr(user, "warehouse_id", None)
    try:
        return int(val) if val is not None else None
    except (TypeError, ValueError):
        return None


def _role_str(user: User) -> str:
    role = getattr(user, "role", None)
    return role.value if hasattr(role, "value") else (role or "")


def _admin_warehouse_ids(db: Session, user_id: int) -> list:
    """Warehouse IDs assigned to an admin via user_warehouses join table."""
    from sqlalchemy import text as _t
    try:
        rows = db.execute(_t("SELECT warehouse_id FROM user_warehouses WHERE user_id=:id"), {"id": user_id}).fetchall()
        return [r[0] for r in rows]
    except Exception:
        return []


def _assert_user_can_transfer(db: Session, user: User, source_id: int, destination_id: int):
    """Transfer create: super-admin = unrestricted. Admin = must be assigned
    to source or destination warehouse via user_warehouses. Warehouse role =
    must match source or destination via User.warehouse_id."""
    if is_super_admin(user):
        return
    role = _role_str(user)
    if role == "admin":
        wh_ids = _admin_warehouse_ids(db, user.id)
        if not wh_ids:
            raise HTTPException(
                status_code=403,
                detail="Admin must be assigned to at least one warehouse. "
                       "Ask a super-admin to configure your warehouse assignments.",
            )
        if source_id not in wh_ids and destination_id not in wh_ids:
            raise HTTPException(
                status_code=403,
                detail="You can only create transfers involving your assigned warehouses.",
            )
        return
    user_wh = _user_warehouse_id(user)
    if user_wh is None:
        raise HTTPException(
            status_code=403,
            detail="You must be mapped to a warehouse to create transfers. "
                   "Ask a super-admin to assign your warehouse.",
        )
    if int(user_wh) != int(source_id) and int(user_wh) != int(destination_id):
        raise HTTPException(
            status_code=403,
            detail="You can only create transfers involving your assigned warehouse.",
        )


def _assert_user_can_approve_destination(db: Session, user: User, transfer_destination_id: int):
    """Approve/reject DC: super-admin = unrestricted. Admin = destination must
    be in their assigned warehouses. Warehouse role = must match destination."""
    if is_super_admin(user):
        return
    role = _role_str(user)
    if role == "admin":
        wh_ids = _admin_warehouse_ids(db, user.id)
        if transfer_destination_id not in wh_ids:
            raise HTTPException(
                status_code=403,
                detail="Only a user mapped to the destination warehouse can approve "
                       "or reject this transfer.",
            )
        return
    user_wh = _user_warehouse_id(user)
    if user_wh is None or int(user_wh) != int(transfer_destination_id):
        raise HTTPException(
            status_code=403,
            detail="Only a user mapped to the destination warehouse can approve "
                   "or reject this transfer.",
        )

# ── Warehouse Router ──────────────────────────────────────────
warehouse_router = APIRouter(prefix="/warehouses", tags=["warehouses"])

@warehouse_router.get("/")
async def list_warehouses(
    include_inactive: bool = False,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    return WarehouseService.list_warehouses(db, include_inactive)


@warehouse_router.post("/", status_code=201)
async def create_warehouse(
    payload: WarehouseCreate,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return WarehouseService.create(db, payload, current_user.id)


@warehouse_router.get("/stock")
async def get_stock(
    warehouse_id: Optional[int] = None,
    product_id: Optional[int] = None,
    search: Optional[str] = None,
    low_stock_only: bool = False,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    return WarehouseService.get_stock(db, warehouse_id, product_id, search, low_stock_only)


@warehouse_router.get("/stock/consolidated/{product_id}")
async def get_consolidated_stock(
    product_id: int,
    warehouse_id: int = Query(..., description="Selected warehouse ID"),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    return WarehouseService.get_consolidated_stock(db, product_id, warehouse_id)


@warehouse_router.get("/stock/ageing")
async def get_stock_ageing(
    warehouse_id: Optional[int] = None,
    db: Session = Depends(get_db),
    _: User = Depends(require_warehouse_ops),
):
    return StockAgeingService.get_ageing(db, warehouse_id)


@warehouse_router.get("/{warehouse_id}")
async def get_warehouse(
    warehouse_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    return WarehouseService.get_by_id(db, warehouse_id)


@warehouse_router.put("/{warehouse_id}")
async def update_warehouse(
    warehouse_id: int,
    payload: WarehouseUpdate,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return WarehouseService.update(db, warehouse_id, payload, current_user.id)


# ── Stock Transfer Router ─────────────────────────────────────
transfer_router = APIRouter(prefix="/stock-transfers", tags=["stock-transfers"])

@transfer_router.get("/")
async def list_transfers(
    warehouse_id: Optional[int] = None,
    product_id: Optional[int] = None,
    pending_for_me: bool = False,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=500),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List transfers. When pending_for_me=true, restrict to transfers whose
    destination warehouse = current user's warehouse and which still have
    at least one linked DC awaiting approval (status pending or linked)."""
    pending_dest_whs = None
    if pending_for_me:
        if is_super_admin(current_user):
            pass  # super-admin sees all pending; honor warehouse_id filter if passed
        elif _role_str(current_user) == "admin":
            wh_ids = _admin_warehouse_ids(db, current_user.id)
            if not wh_ids:
                return {"items": [], "total": 0, "page": page, "page_size": page_size}
            pending_dest_whs = wh_ids
        else:
            user_wh = _user_warehouse_id(current_user)
            if not user_wh:
                return {"items": [], "total": 0, "page": page, "page_size": page_size}
            pending_dest_whs = [user_wh]
    return StockTransferService.list_transfers(
        db, warehouse_id, product_id, page, page_size,
        pending_dest_whs=pending_dest_whs,
    )


@transfer_router.post("/", status_code=201)
async def create_transfer(
    payload: StockTransferCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _assert_user_can_transfer(
        db, current_user,
        payload.source_warehouse_id,
        payload.destination_warehouse_id,
    )
    return StockTransferService.create(db, payload, current_user.id)




@transfer_router.post("/{transfer_id}/confirm-dc")
async def confirm_dc(
    transfer_id: int,
    payload: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Approve a DC at the destination warehouse — adds stock to destination,
    marks DC delivered, and records approved_by + approved_at."""
    dc_id = payload.get("dc_id")
    if not dc_id:
        raise HTTPException(status_code=400, detail="dc_id required")
    from app.models.models import StockTransfer
    t = db.query(StockTransfer).filter(StockTransfer.id == transfer_id).first()
    if not t:
        raise HTTPException(status_code=404, detail="Transfer not found")
    _assert_user_can_approve_destination(db, current_user, t.destination_warehouse_id)
    return StockTransferService.confirm_dc(db, transfer_id, dc_id, current_user.id)


@transfer_router.post("/{transfer_id}/reject-dc")
async def reject_dc(
    transfer_id: int,
    payload: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Reject a DC at the destination warehouse — restores source stock,
    marks DC rejected, and records rejected_by + rejected_at + reason."""
    dc_id = payload.get("dc_id")
    reason = (payload.get("reason") or "").strip()
    if not dc_id:
        raise HTTPException(status_code=400, detail="dc_id required")
    if len(reason) < 3:
        raise HTTPException(status_code=400, detail="Rejection reason required (min 3 chars)")
    from app.models.models import StockTransfer
    t = db.query(StockTransfer).filter(StockTransfer.id == transfer_id).first()
    if not t:
        raise HTTPException(status_code=404, detail="Transfer not found")
    _assert_user_can_approve_destination(db, current_user, t.destination_warehouse_id)
    return StockTransferService.reject_dc(db, transfer_id, dc_id, reason, current_user.id)


@transfer_router.get("/{transfer_id}")
async def get_transfer(
    transfer_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin_or_accountant),
):
    from app.models.models import StockTransfer, Invoice as InvoiceModel, Warehouse
    import json
    t = db.query(StockTransfer).filter(StockTransfer.id == transfer_id).first()
    if not t:
        raise HTTPException(status_code=404, detail="Transfer not found")
    dc_ids = json.loads(t.dc_ids or "[]")
    linked_dcs = []
    for dc_id in dc_ids:
        dc = db.query(InvoiceModel).filter(InvoiceModel.id == dc_id).first()
        if dc:
            src = db.query(Warehouse).filter(Warehouse.id == dc.warehouse_id).first()
            dst_id = getattr(dc, 'dc_destination_warehouse_id', None)
            dst = db.query(Warehouse).filter(Warehouse.id == dst_id).first() if dst_id else None
            linked_dcs.append({
                "id": dc.id,
                "invoice_number": dc.invoice_number,
                "invoice_date": str(dc.invoice_date) if dc.invoice_date else None,
                "dc_status": getattr(dc, 'dc_status', 'pending'),
                "source_warehouse_name": src.name if src else None,
                "destination_warehouse_name": dst.name if dst else None,
                "vehicle_number": getattr(dc, 'vehicle_number', None),
            })
    return {
        "id": t.id,
        "transfer_number": t.transfer_number,
        "source_warehouse_id": t.source_warehouse_id,
        "destination_warehouse_id": t.destination_warehouse_id,
        "transfer_date": t.transfer_date,
        "notes": t.notes,
        "dc_ids": dc_ids,
        "linked_dcs": linked_dcs,
    }


@transfer_router.put("/{transfer_id}/link-dc")
async def link_dc_to_transfer(
    transfer_id: int,
    payload: dict,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    from app.models.models import StockTransfer, Invoice as InvoiceModel
    import json
    t = db.query(StockTransfer).filter(StockTransfer.id == transfer_id).first()
    if not t:
        raise HTTPException(status_code=404, detail="Transfer not found")
    dc_id = payload.get("dc_id")
    if not dc_id:
        raise HTTPException(status_code=400, detail="dc_id required")
    
    # Check DC not linked elsewhere
    all_transfers = db.query(StockTransfer).filter(
        StockTransfer.id != transfer_id,
        StockTransfer.dc_ids.isnot(None)
    ).all()
    for ot in all_transfers:
        try:
            if dc_id in json.loads(ot.dc_ids or "[]"):
                raise HTTPException(status_code=400, detail=f"DC already linked to transfer {ot.transfer_number}")
        except HTTPException:
            raise
        except Exception:
            pass
    
    current = json.loads(t.dc_ids or "[]")
    if dc_id not in current:
        current.append(dc_id)
        t.dc_ids = json.dumps(current)
    
    # Set DC status to linked
    dc = db.query(InvoiceModel).filter(InvoiceModel.id == dc_id).first()
    if dc:
        try:
            dc.dc_status = 'linked'
        except Exception:
            pass
    
    db.commit()
    return {"status": "linked", "dc_ids": current}


@transfer_router.put("/{transfer_id}/unlink-dc")
async def unlink_dc_from_transfer(
    transfer_id: int,
    payload: dict,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    from app.models.models import StockTransfer, Invoice as InvoiceModel
    import json
    t = db.query(StockTransfer).filter(StockTransfer.id == transfer_id).first()
    if not t:
        raise HTTPException(status_code=404, detail="Transfer not found")
    dc_id = payload.get("dc_id")
    current = json.loads(t.dc_ids or "[]")
    if dc_id in current:
        current.remove(dc_id)
        t.dc_ids = json.dumps(current)
    
    # Immediately revert DC status to pending
    dc = db.query(InvoiceModel).filter(InvoiceModel.id == dc_id).first()
    if dc:
        try:
            dc.dc_status = 'pending'
        except Exception:
            pass
    
    db.commit()
    return {"status": "unlinked", "dc_ids": current}


# ── Stock Adjustment Router ───────────────────────────────────
adjustment_router = APIRouter(prefix="/stock-adjustments", tags=["stock-adjustments"])

@adjustment_router.get("/")
async def list_adjustments(
    warehouse_id: Optional[int] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=500),
    db: Session = Depends(get_db),
    _: User = Depends(require_warehouse_ops),
):
    return StockAdjustmentService.list_adjustments(db, warehouse_id, page, page_size)


@adjustment_router.post("/", status_code=201)
async def create_adjustment(
    payload: StockAdjustmentCreate,
    current_user: User = Depends(require_warehouse_ops),
    db: Session = Depends(get_db),
):
    return StockAdjustmentService.create(db, payload, current_user.id)


# ── Stock Write-off Router ────────────────────────────────────
writeoff_router = APIRouter(prefix="/stock-writeoffs", tags=["stock-writeoffs"])

@writeoff_router.get("/")
async def list_writeoffs(
    status: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=500),
    db: Session = Depends(get_db),
    _: User = Depends(require_warehouse_ops),
):
    return StockWriteoffService.list_writeoffs(db, status, page, page_size)


@writeoff_router.post("/", status_code=201)
async def create_writeoff(
    payload: StockWriteoffCreate,
    current_user: User = Depends(require_warehouse_ops),
    db: Session = Depends(get_db),
):
    return StockWriteoffService.create(db, payload, current_user.id)


@writeoff_router.post("/{writeoff_id}/approve")
async def approve_writeoff(
    writeoff_id: int,
    payload: StockWriteoffApprove,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return StockWriteoffService.approve(db, writeoff_id, payload, current_user.id)


# ── Opening Balance Router ────────────────────────────────────
opening_router = APIRouter(prefix="/opening-balances", tags=["opening-balances"])

@opening_router.post("/", status_code=201)
async def create_opening_balances(
    payload: OpeningBalanceCreate,
    current_user: User = Depends(require_super_admin),
    db: Session = Depends(get_db),
):
    return OpeningBalanceService.create(db, payload, current_user.id)


@opening_router.get("/stock-template/csv")
async def download_opening_stock_template(_: User = Depends(require_super_admin)):
    content = OpeningBalanceService.get_stock_csv_template()
    return StreamingResponse(
        io.StringIO(content),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=opening_stock_template.csv"},
    )


@opening_router.post("/stock/bulk-upload")
async def bulk_upload_opening_stock(
    opening_date: date = Query(..., description="Default opening date for rows that omit it"),
    file: UploadFile = File(...),
    current_user: User = Depends(require_super_admin),
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
    return OpeningBalanceService.bulk_upload_stock(db, content, opening_date, current_user.id)


@warehouse_router.get("/{warehouse_id}/validate-obsolete")
async def validate_obsolete_warehouse(
    warehouse_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_super_admin),
):
    return WarehouseService.validate_obsolete(db, warehouse_id)


@warehouse_router.put("/{warehouse_id}/rename")
async def rename_warehouse(
    warehouse_id: int,
    payload: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not is_super_admin(current_user):
        # Admin with no warehouse assigned can edit any warehouse;
        # admin with a warehouse mapping can only edit their warehouse.
        user_wh = _user_warehouse_id(current_user)
        if user_wh is not None and int(user_wh) != int(warehouse_id):
            raise HTTPException(status_code=403, detail="You can only edit your assigned warehouse")
    return WarehouseService.rename_warehouse(db, warehouse_id, payload, current_user.id)


@warehouse_router.post("/{warehouse_id}/obsolete")
async def obsolete_warehouse(
    warehouse_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_super_admin),
):
    return WarehouseService.obsolete_warehouse(db, warehouse_id, current_user.id)


@warehouse_router.get("/{warehouse_id}/validate-delete")
async def validate_delete_warehouse(
    warehouse_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_super_admin),
):
    return WarehouseService.validate_delete(db, warehouse_id)


@warehouse_router.delete("/{warehouse_id}")
async def delete_warehouse(
    warehouse_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_super_admin),
):
    return WarehouseService.delete_warehouse(db, warehouse_id, current_user.id)