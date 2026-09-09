"""DPDP Act endpoints: consent, data retention, right-to-erasure (Phase 4b).

All routes are additive. Destructive operations (retention enforce, erasure
process) are restricted to super-admin and never run automatically.
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional

from app.db.session import get_db
from app.core.security import get_current_user, require_admin, require_super_admin
from app.services.dpdp_service import ConsentService, RetentionService, ErasureService

router = APIRouter(prefix="/dpdp", tags=["dpdp"])


# ── Schemas ───────────────────────────────────────────────────

class ConsentRecordIn(BaseModel):
    principal_type: str          # user/customer/vendor
    principal_id: int
    purpose_key: str
    granted: bool
    source: Optional[str] = None
    notes: Optional[str] = None


class ErasureRequestIn(BaseModel):
    subject_type: str            # customer/vendor/user
    subject_id: int
    reason: Optional[str] = None


# ── Consent ───────────────────────────────────────────────────

@router.get("/purposes")
async def list_purposes(db: Session = Depends(get_db), _=Depends(get_current_user)):
    return ConsentService.list_purposes(db)


@router.post("/consent")
async def record_consent(payload: ConsentRecordIn, db: Session = Depends(get_db),
                         user=Depends(get_current_user)):
    return ConsentService.record(
        db, payload.principal_type, payload.principal_id, payload.purpose_key,
        payload.granted, source=payload.source, notes=payload.notes, user_id=user.id)


@router.get("/consent/{principal_type}/{principal_id}")
async def consent_status(principal_type: str, principal_id: int,
                         db: Session = Depends(get_db), _=Depends(require_admin)):
    return ConsentService.status(db, principal_type, principal_id)


# ── Data retention ────────────────────────────────────────────

@router.get("/retention-policies")
async def retention_policies(db: Session = Depends(get_db), _=Depends(require_admin)):
    return RetentionService.list_policies(db)


@router.get("/retention-preview")
async def retention_preview(db: Session = Depends(get_db), _=Depends(require_super_admin)):
    return RetentionService.preview(db)


@router.post("/retention-enforce")
async def retention_enforce(dry_run: bool = Query(True),
                            db: Session = Depends(get_db),
                            user=Depends(require_super_admin)):
    return RetentionService.enforce(db, dry_run=dry_run, user_id=user.id)


# ── Right to erasure ──────────────────────────────────────────

@router.post("/erasure-requests")
async def create_erasure(payload: ErasureRequestIn, db: Session = Depends(get_db),
                         user=Depends(require_admin)):
    return ErasureService.request(db, payload.subject_type, payload.subject_id,
                                  reason=payload.reason, user_id=user.id)


@router.get("/erasure-requests")
async def list_erasure(status: Optional[str] = None, db: Session = Depends(get_db),
                       _=Depends(require_admin)):
    return ErasureService.list(db, status)


@router.post("/erasure-requests/{request_id}/process")
async def process_erasure(request_id: int, db: Session = Depends(get_db),
                          user=Depends(require_super_admin)):
    return ErasureService.process(db, request_id, user_id=user.id)
