from fastapi import APIRouter, Depends, Query, HTTPException, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from typing import Optional
import io
import json

from app.db.session import get_db
from app.models.models import User
from app.core.security import get_current_user, require_admin, require_admin_or_accountant
from app.services.security_service import ActivityLogService
from app.utils.helpers import get_client_ip
from app.schemas.gst import (
    TransporterCreate, TransporterUpdate, VehicleCreate, VehicleUpdate,
    EInvoiceGenerateRequest, EInvoiceCancelRequest,
    EWayBillGenerateRequest, GSTR2BImport,
)
from app.services.gst_service import (
    TransporterService, EInvoiceService,
    EWayBillService, GSTR1Service, GSTR1ExportService,
    GSTR2BService, GSTR3BService,
)

# ── Transporter Router ────────────────────────────────────────
transporter_router = APIRouter(prefix="/transporters", tags=["transporters"])

@transporter_router.get("/")
async def list_transporters(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    return TransporterService.list_transporters(db)


@transporter_router.post("/", status_code=201)
async def create_transporter(
    payload: TransporterCreate,
    current_user: User = Depends(require_admin_or_accountant),
    db: Session = Depends(get_db),
):
    return TransporterService.create_transporter(db, payload, current_user.id)



@transporter_router.put("/{transporter_id}")
async def update_transporter(
    transporter_id: int,
    payload: TransporterUpdate,
    current_user: User = Depends(require_admin_or_accountant),
    db: Session = Depends(get_db),
):
    try:
        return TransporterService.update_transporter(db, transporter_id, payload, current_user.id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@transporter_router.delete("/{transporter_id}")
async def delete_transporter(
    transporter_id: int,
    current_user: User = Depends(require_admin_or_accountant),
    db: Session = Depends(get_db),
):
    try:
        return TransporterService.delete_transporter(db, transporter_id, current_user.id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


# ── Vehicle Router ────────────────────────────────────────────
vehicle_router = APIRouter(prefix="/vehicles", tags=["vehicles"])

@vehicle_router.get("/")
async def list_vehicles(
    transporter_id: Optional[int] = None,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    return TransporterService.list_vehicles(db, transporter_id)


@vehicle_router.post("/", status_code=201)
async def create_vehicle(
    payload: VehicleCreate,
    current_user: User = Depends(require_admin_or_accountant),
    db: Session = Depends(get_db),
):
    return TransporterService.create_vehicle(db, payload, current_user.id)


@vehicle_router.put("/{vehicle_id}")
async def update_vehicle(
    vehicle_id: int,
    payload: VehicleUpdate,
    current_user: User = Depends(require_admin_or_accountant),
    db: Session = Depends(get_db),
):
    try:
        return TransporterService.update_vehicle(db, vehicle_id, payload, current_user.id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@vehicle_router.delete("/{vehicle_id}")
async def delete_vehicle(
    vehicle_id: int,
    current_user: User = Depends(require_admin_or_accountant),
    db: Session = Depends(get_db),
):
    try:
        return TransporterService.delete_vehicle(db, vehicle_id, current_user.id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


# ── E-Invoice Router ──────────────────────────────────────────
einvoice_router = APIRouter(prefix="/einvoice", tags=["einvoice"])

@einvoice_router.get("/logs")
async def list_einvoice_logs(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=500),
    db: Session = Depends(get_db),
    _: User = Depends(require_admin_or_accountant),
):
    return EInvoiceService.list_einvoice_logs(db, page, page_size)


@einvoice_router.post("/generate")
async def generate_einvoice(
    payload: EInvoiceGenerateRequest,
    current_user: User = Depends(require_admin_or_accountant),
    db: Session = Depends(get_db),
):
    return await EInvoiceService.generate(db, payload.invoice_id, current_user.id)


@einvoice_router.post("/cancel")
async def cancel_einvoice(
    payload: EInvoiceCancelRequest,
    current_user: User = Depends(require_admin_or_accountant),
    db: Session = Depends(get_db),
):
    return await EInvoiceService.cancel_irn(
        db, payload.invoice_id, payload.cancel_reason, current_user.id,
        remark=payload.cancel_remark,
    )


# ── E-Way Bill Router ─────────────────────────────────────────
eway_router = APIRouter(prefix="/ewaybill", tags=["ewaybill"])

@eway_router.get("/logs")
async def list_eway_logs(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=500),
    db: Session = Depends(get_db),
    _: User = Depends(require_admin_or_accountant),
):
    return EWayBillService.list_eway_logs(db, page, page_size)


@eway_router.post("/generate")
async def generate_eway_bill(
    payload: EWayBillGenerateRequest,
    current_user: User = Depends(require_admin_or_accountant),
    db: Session = Depends(get_db),
):
    return await EWayBillService.generate(db, payload, current_user.id)


# ── GSTR-1 Router ─────────────────────────────────────────────
gstr1_router = APIRouter(prefix="/gstr1", tags=["gstr1"])

@gstr1_router.get("/")
async def get_gstr1(
    period: str = Query(..., description="MM-YYYY format e.g. 01-2026"),
    financial_year: str = Query(..., description="e.g. 2025-26"),
    db: Session = Depends(get_db),
    _: User = Depends(require_admin_or_accountant),
):
    return GSTR1Service.generate(db, period, financial_year)


@gstr1_router.get("/export/excel")
async def export_gstr1_excel(
    request: Request,
    period: str = Query(..., description="MM-YYYY format e.g. 01-2026"),
    financial_year: str = Query(..., description="e.g. 2025-26"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin_or_accountant),
):
    content = GSTR1ExportService.build_excel(db, period, financial_year)
    ActivityLogService.log(db, current_user.id, "export",
                           f"Exported GSTR-1 Excel for {period}", ip_address=get_client_ip(request))
    return StreamingResponse(
        io.BytesIO(content),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename=GSTR1_{period}.xlsx"},
    )


@gstr1_router.get("/export/json")
async def export_gstr1_json(
    request: Request,
    period: str = Query(..., description="MM-YYYY format e.g. 01-2026"),
    financial_year: str = Query(..., description="e.g. 2025-26"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin_or_accountant),
):
    data = GSTR1ExportService.build_gov_json(db, period, financial_year)
    ActivityLogService.log(db, current_user.id, "export",
                           f"Exported GSTR-1 JSON for {period}", ip_address=get_client_ip(request))
    payload = json.dumps(data, indent=2)
    return StreamingResponse(
        io.StringIO(payload),
        media_type="application/json",
        headers={"Content-Disposition": f"attachment; filename=GSTR1_{period}.json"},
    )


# ── GSTR-2B Router ────────────────────────────────────────────
gstr2b_router = APIRouter(prefix="/gstr2b", tags=["gstr2b"])

@gstr2b_router.post("/reconcile")
async def reconcile_gstr2b(
    payload: GSTR2BImport,
    current_user: User = Depends(require_admin_or_accountant),
    db: Session = Depends(get_db),
):
    return GSTR2BService.reconcile(db, payload)


# ── GSTR-3B Router ────────────────────────────────────────────
gstr3b_router = APIRouter(prefix="/gstr3b", tags=["gstr3b"])

@gstr3b_router.get("/")
async def get_gstr3b(
    period: str = Query(..., description="MM-YYYY format e.g. 01-2026"),
    financial_year: str = Query(..., description="e.g. 2025-26"),
    db: Session = Depends(get_db),
    _: User = Depends(require_admin_or_accountant),
):
    return GSTR3BService.generate(db, period, financial_year)
