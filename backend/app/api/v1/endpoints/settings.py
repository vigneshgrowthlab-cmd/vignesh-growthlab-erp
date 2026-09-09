from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
import json
import shutil, os, uuid
from datetime import date
from sqlalchemy.orm import Session
from typing import Optional, List
from pydantic import BaseModel, EmailStr
from decimal import Decimal

from app.db.session import get_db
from app.models.models import CompanySettings, InvoiceSequence, DocumentType, User, GstRateMaster, TdsSectionMaster
from app.core.security import get_current_user, require_admin, require_super_admin
from app.services.gst_master_service import GstMasterService
from app.services.tax_master_service import TaxMasterService
from app.services.workflow_service import WorkflowService

router = APIRouter(prefix="/settings", tags=["settings"])


# ── Schemas ───────────────────────────────────────────────────

class TdsSectionCreate(BaseModel):
    section_code: str
    description: Optional[str] = None
    rate: Decimal
    threshold_single: Optional[Decimal] = None
    threshold_annual: Optional[Decimal] = None
    deductee_type: Optional[str] = None
    effective_from: Optional[date] = None
    regulatory_reference: Optional[str] = None
    note: Optional[str] = None


class GstRateCreate(BaseModel):
    rate: Decimal
    label: Optional[str] = None
    is_selectable: bool = True
    effective_from: Optional[date] = None
    effective_to: Optional[date] = None
    regulatory_reference: Optional[str] = None
    note: Optional[str] = None


class CompanySettingsUpdate(BaseModel):
    company_name: Optional[str] = None
    gstin: Optional[str] = None
    state: Optional[str] = None
    state_code: Optional[int] = None
    address_line1: Optional[str] = None
    address_line2: Optional[str] = None
    city: Optional[str] = None
    pincode: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    terms_conditions: Optional[str] = None
    terms_b2b_invoice: Optional[str] = None
    terms_b2c_invoice: Optional[str] = None
    terms_quotation: Optional[str] = None
    terms_delivery_challan: Optional[str] = None
    b2b_invoice_prefix: Optional[str] = None
    b2c_invoice_prefix: Optional[str] = None
    quotation_prefix: Optional[str] = None
    challan_prefix: Optional[str] = None
    credit_note_prefix: Optional[str] = None
    eway_threshold: Optional[Decimal] = None
    bank_stock_margin: Optional[Decimal] = None
    default_min_margin_pct: Optional[Decimal] = None
    financial_year_start: Optional[int] = None
    bank_name: Optional[str] = None
    bank_account_number: Optional[str] = None
    bank_ifsc: Optional[str] = None
    bank_branch: Optional[str] = None
    bank_account_name: Optional[str] = None
    upi_id: Optional[str] = None
    show_transport_on_invoice: Optional[bool] = None
    show_transport_on_challan: Optional[bool] = None


class InvoiceSequenceUpdate(BaseModel):
    prefix: str
    last_number: Optional[int] = None
    financial_year: Optional[str] = None


# ── Helpers ───────────────────────────────────────────────────

def _fmt_settings(s: CompanySettings) -> dict:
    return {
        "id": s.id,
        "company_name": s.company_name,
        "gstin": s.gstin,
        "state": s.state,
        "state_code": s.state_code,
        "address_line1": s.address_line1,
        "address_line2": s.address_line2,
        "city": s.city,
        "pincode": s.pincode,
        "phone": s.phone,
        "email": s.email,
        "logo_path": s.logo_path,
        "signature_path": s.signature_path,
        "terms_conditions": s.terms_conditions,
        "terms_b2b_invoice": getattr(s, 'terms_b2b_invoice', None),
        "terms_b2c_invoice": getattr(s, 'terms_b2c_invoice', None),
        "terms_quotation": getattr(s, 'terms_quotation', None),
        "terms_delivery_challan": getattr(s, 'terms_delivery_challan', None),
        "b2b_invoice_prefix": s.b2b_invoice_prefix,
        "b2c_invoice_prefix": s.b2c_invoice_prefix,
        "quotation_prefix": s.quotation_prefix,
        "challan_prefix": s.challan_prefix,
        "credit_note_prefix": s.credit_note_prefix,
        "eway_threshold": s.eway_threshold,
        "bank_stock_margin": s.bank_stock_margin,
        "default_min_margin_pct": getattr(s, 'default_min_margin_pct', None),
        "financial_year_start": s.financial_year_start,
        "bank_name": getattr(s, 'bank_name', None),
        "bank_account_number": getattr(s, 'bank_account_number', None),
        "bank_ifsc": getattr(s, 'bank_ifsc', None),
        "bank_branch": getattr(s, 'bank_branch', None),
        "bank_account_name": getattr(s, 'bank_account_name', None),
        "upi_id": getattr(s, 'upi_id', None),
        "show_transport_on_invoice": getattr(s, 'show_transport_on_invoice', True),
        "show_transport_on_challan": getattr(s, 'show_transport_on_challan', True),
    }


# ── Company Settings ──────────────────────────────────────────

@router.get("/company")
async def get_company_settings(
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    s = db.query(CompanySettings).first()
    if not s:
        # Return defaults
        return {
            "id": None,
            "company_name": "My Wholesale Company",
            "gstin": "", "state": "", "state_code": 0,
            "address_line1": "", "address_line2": "",
            "city": "", "pincode": "", "phone": "", "email": "",
            "logo_path": None, "signature_path": None, "terms_conditions": "",
            "terms_b2b_invoice": None, "terms_b2c_invoice": None,
            "terms_quotation": None, "terms_delivery_challan": None,
            "b2b_invoice_prefix": "BINV", "b2c_invoice_prefix": "CINV",
            "quotation_prefix": "QT", "challan_prefix": "DC",
            "credit_note_prefix": "CN", "eway_threshold": 50000,
            "bank_stock_margin": 25.00, "default_min_margin_pct": 10.00,
            "financial_year_start": 4,
            "show_transport_on_invoice": True,
            "show_transport_on_challan": True,
        }
    return _fmt_settings(s)


@router.put("/company")
async def update_company_settings(
    payload: CompanySettingsUpdate,
    db: Session = Depends(get_db),
    current_user=Depends(require_super_admin),
):
    s = db.query(CompanySettings).first()
    if not s:
        # Create from payload
        data = payload.dict(exclude_none=True)
        data.setdefault("company_name", "My Company")
        data.setdefault("gstin", "")
        data.setdefault("state", "")
        data.setdefault("state_code", 0)
        data.setdefault("address_line1", "")
        data.setdefault("city", "")
        data.setdefault("pincode", "")
        s = CompanySettings(**data, created_by=current_user.id)
        db.add(s)
    else:
        for field, value in payload.dict(exclude_none=True).items():
            setattr(s, field, value)
        s.updated_by = current_user.id
    db.commit()
    db.refresh(s)
    return _fmt_settings(s)


# ── Invoice Sequences ─────────────────────────────────────────

@router.get("/invoice-sequences")
async def get_invoice_sequences(
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    seqs = db.query(InvoiceSequence).all()
    return [
        {
            "id": s.id,
            "document_type": s.document_type,
            "prefix": s.prefix,
            "financial_year": s.financial_year,
            "last_number": s.last_number,
        }
        for s in seqs
    ]


@router.put("/invoice-sequences/{seq_id}")
async def update_invoice_sequence(
    seq_id: int,
    payload: InvoiceSequenceUpdate,
    db: Session = Depends(get_db),
    _=Depends(require_super_admin),
):
    seq = db.query(InvoiceSequence).filter(InvoiceSequence.id == seq_id).first()
    if not seq:
        raise HTTPException(status_code=404, detail="Sequence not found")
    seq.prefix = payload.prefix
    if payload.last_number is not None:
        seq.last_number = payload.last_number
    if payload.financial_year:
        seq.financial_year = payload.financial_year
    db.commit()
    return {"id": seq.id, "document_type": seq.document_type,
            "prefix": seq.prefix, "last_number": seq.last_number,
            "financial_year": seq.financial_year}


# ── GST Rates master ──────────────────────────────────────────

@router.get("/gst-rates")
async def get_gst_rates(db: Session = Depends(get_db), _=Depends(get_current_user)):
    rows = GstMasterService.selectable_gst_rates(db)
    if rows:
        return rows
    return [
        {"rate": 0,  "label": "0% — Exempt / Zero-rated"},
        {"rate": 5,  "label": "5% — Essential goods"},
        {"rate": 12, "label": "12% — Standard goods"},
        {"rate": 18, "label": "18% — Standard services"},
        {"rate": 28, "label": "28% — Luxury / demerit goods"},
    ]


@router.delete("/gst-rates/{rate_id}", status_code=200)
async def delete_gst_rate(
    rate_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(require_admin),
):
    row = db.query(GstRateMaster).filter(GstRateMaster.id == rate_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Rate not found")
    if row.status == "revoked":
        raise HTTPException(status_code=409, detail="Rate already removed")
    row.status = "revoked"
    row.effective_to = date.today()
    db.commit()
    return {"id": row.id, "rate": float(row.rate), "status": row.status}


@router.post("/gst-rates", status_code=201)
async def create_gst_rate(
    body: GstRateCreate,
    db: Session = Depends(get_db),
    current_user=Depends(require_admin),
):
    existing = db.query(GstRateMaster).filter(
        GstRateMaster.rate == body.rate,
        GstRateMaster.status == "active",
        GstRateMaster.effective_to.is_(None),
    ).first()
    if existing:
        raise HTTPException(status_code=409, detail=f"Rate {body.rate}% already active")
    row = GstRateMaster(
        rate=body.rate,
        label=body.label or f"{body.rate}%",
        is_selectable=body.is_selectable,
        effective_from=body.effective_from or date.today(),
        effective_to=body.effective_to,
        status="active",
        regulatory_reference=body.regulatory_reference,
        note=body.note,
        created_by=current_user.id,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    rate_val = float(row.rate)
    rate_val = int(rate_val) if rate_val == int(rate_val) else rate_val
    return {"id": row.id, "rate": rate_val, "label": row.label, "status": row.status,
            "effective_from": str(row.effective_from)}


# ── TDS sections master ───────────────────────────────────────

@router.get("/tds-sections")
async def get_tds_sections(db: Session = Depends(get_db), _=Depends(get_current_user)):
    """Effective TDS sections (code, rate, thresholds) for pickers/auto-fill.
    Empty list until tds_section_master is seeded."""
    return TaxMasterService.tds_sections(db)


@router.post("/tds-sections", status_code=201)
async def create_tds_section(
    body: TdsSectionCreate,
    db: Session = Depends(get_db),
    current_user=Depends(require_admin),
):
    existing = db.query(TdsSectionMaster).filter(
        TdsSectionMaster.section_code == body.section_code.strip(),
        TdsSectionMaster.status == "active",
        TdsSectionMaster.effective_to.is_(None),
    ).first()
    if existing:
        raise HTTPException(status_code=409, detail=f"Section {body.section_code} already active")
    row = TdsSectionMaster(
        section_code=body.section_code.strip().upper(),
        description=body.description,
        rate=body.rate,
        threshold_single=body.threshold_single,
        threshold_annual=body.threshold_annual,
        deductee_type=body.deductee_type,
        effective_from=body.effective_from or date.today(),
        status="active",
        regulatory_reference=body.regulatory_reference,
        note=body.note,
        created_by=current_user.id,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return {
        "id": row.id, "section_code": row.section_code,
        "description": row.description, "rate": float(row.rate),
        "threshold_single": float(row.threshold_single) if row.threshold_single else None,
        "threshold_annual": float(row.threshold_annual) if row.threshold_annual else None,
        "status": row.status, "effective_from": str(row.effective_from),
    }


@router.delete("/tds-sections/{section_id}", status_code=200)
async def delete_tds_section(
    section_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(require_admin),
):
    row = db.query(TdsSectionMaster).filter(TdsSectionMaster.id == section_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Section not found")
    if row.status == "revoked":
        raise HTTPException(status_code=409, detail="Section already removed")
    row.status = "revoked"
    row.effective_to = date.today()
    db.commit()
    return {"id": row.id, "section_code": row.section_code, "status": row.status}


# ── Workflow status / transition masters ──────────────────────

@router.get("/workflow-statuses")
async def get_workflow_statuses(entity: str, db: Session = Depends(get_db),
                                _=Depends(get_current_user)):
    """Configurable status labels/colours/order for an entity's workflow."""
    return WorkflowService.get_statuses(db, entity)


@router.get("/workflow-transitions")
async def get_workflow_transitions(entity: str, db: Session = Depends(get_db),
                                   _=Depends(get_current_user)):
    """Allowed status transitions for an entity (advisory policy)."""
    return WorkflowService.get_transitions(db, entity)


# ── Indian States master ──────────────────────────────────────

@router.get("/states")
async def get_states(db: Session = Depends(get_db), _=Depends(get_current_user)):
    rows = GstMasterService.states(db)
    if rows:
        return rows
    return [
        {"code": 1,  "name": "Jammu & Kashmir"},
        {"code": 2,  "name": "Himachal Pradesh"},
        {"code": 3,  "name": "Punjab"},
        {"code": 4,  "name": "Chandigarh"},
        {"code": 5,  "name": "Uttarakhand"},
        {"code": 6,  "name": "Haryana"},
        {"code": 7,  "name": "Delhi"},
        {"code": 8,  "name": "Rajasthan"},
        {"code": 9,  "name": "Uttar Pradesh"},
        {"code": 10, "name": "Bihar"},
        {"code": 11, "name": "Sikkim"},
        {"code": 12, "name": "Arunachal Pradesh"},
        {"code": 13, "name": "Nagaland"},
        {"code": 14, "name": "Manipur"},
        {"code": 15, "name": "Mizoram"},
        {"code": 16, "name": "Tripura"},
        {"code": 17, "name": "Meghalaya"},
        {"code": 18, "name": "Assam"},
        {"code": 19, "name": "West Bengal"},
        {"code": 20, "name": "Jharkhand"},
        {"code": 21, "name": "Odisha"},
        {"code": 22, "name": "Chhattisgarh"},
        {"code": 23, "name": "Madhya Pradesh"},
        {"code": 24, "name": "Gujarat"},
        {"code": 26, "name": "Dadra and Nagar Haveli and Daman and Diu"},
        {"code": 27, "name": "Maharashtra"},
        {"code": 28, "name": "Andhra Pradesh (New)"},
        {"code": 29, "name": "Karnataka"},
        {"code": 30, "name": "Goa"},
        {"code": 31, "name": "Lakshadweep"},
        {"code": 32, "name": "Kerala"},
        {"code": 33, "name": "Tamil Nadu"},
        {"code": 34, "name": "Puducherry"},
        {"code": 35, "name": "Andaman & Nicobar Islands"},
        {"code": 36, "name": "Telangana"},
        {"code": 37, "name": "Andhra Pradesh (Residual)"},
        {"code": 38, "name": "Ladakh"},
    ]


# ── Logo Upload ───────────────────────────────────────────────

@router.post("/company/logo")
async def upload_logo(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user=Depends(require_super_admin),
):
    # Validate file type
    if file.content_type not in ("image/png", "image/jpeg", "image/jpg", "image/webp", "image/gif"):
        raise HTTPException(status_code=400, detail="Only image files are allowed (PNG, JPG, WebP)")
    if file.size and file.size > 2 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="File size must be under 2MB")

    upload_dir = "./uploads/logos"
    os.makedirs(upload_dir, exist_ok=True)

    ext = file.filename.split(".")[-1].lower()
    filename = f"logo_{uuid.uuid4().hex[:8]}.{ext}"
    filepath = os.path.join(upload_dir, filename)

    with open(filepath, "wb") as f_out:
        shutil.copyfileobj(file.file, f_out)

    url_path = f"/uploads/logos/{filename}"

    # Save to company settings
    s = db.query(CompanySettings).first()
    if s:
        s.logo_path = url_path
        s.updated_by = current_user.id
        db.commit()

    return {"logo_path": url_path, "message": "Logo uploaded successfully"}


# ── User Page Permissions ─────────────────────────────────────

class PermissionsUpdate(BaseModel):
    page_permissions: Optional[List[str]] = None  # None = full access; [] = no access


def _parse_perms(raw):
    if raw is None or raw == "":
        return None
    try:
        val = json.loads(raw)
        return val if isinstance(val, list) else None
    except Exception:
        return None


@router.get("/users-permissions")
async def list_user_permissions(
    db: Session = Depends(get_db),
    _=Depends(require_super_admin),
):
    """List users (excluding admin / super_admin) with their page_permissions."""
    users = (
        db.query(User)
        .filter(~User.role.in_(("admin", "super_admin")))
        .order_by(User.full_name)
        .all()
    )
    return [
        {
            "id": u.id,
            "username": u.username,
            "full_name": u.full_name,
            "email": u.email,
            "role": u.role,
            "is_active": u.is_active,
            "page_permissions": _parse_perms(getattr(u, "page_permissions", None)),
        }
        for u in users
    ]


@router.put("/users-permissions/{user_id}")
async def update_user_permissions(
    user_id: int,
    payload: PermissionsUpdate,
    db: Session = Depends(get_db),
    current_user=Depends(require_super_admin),
):
    u = db.query(User).filter(User.id == user_id).first()
    if not u:
        raise HTTPException(status_code=404, detail="User not found")
    if u.role in ("admin", "super_admin"):
        raise HTTPException(
            status_code=400,
            detail="Cannot restrict page access for admin or super-admin users",
        )
    # Store None → NULL (full access); list → JSON string
    u.page_permissions = (
        json.dumps(payload.page_permissions)
        if payload.page_permissions is not None
        else None
    )
    u.updated_by = current_user.id
    try:
        db.commit()
        db.refresh(u)
    except Exception:
        db.rollback()
        raise HTTPException(status_code=500, detail="Failed to save permissions")
    return {
        "id": u.id,
        "page_permissions": _parse_perms(getattr(u, "page_permissions", None)),
    }