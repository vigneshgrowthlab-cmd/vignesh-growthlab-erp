"""Config governance API (Phase 6a): browse the catalogue, view value history,
resolve the effective value, and run the maker-checker lifecycle (propose →
activate / expire / revoke) with validation against each definition.

All write operations are super-admin only. Proposing creates a `draft`;
activating supersedes the prior open row. When
`governance.require_separate_checker` is true, the approver must differ from the
proposer. A scheduler endpoint activates due `scheduled` rows (never auto-runs).
"""
from datetime import date
from typing import Optional, Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.db.session import get_db
from app.core.security import get_current_user, require_super_admin
from app.services.config_service import ConfigService
from app.models.models import ConfigValue
from app.services.audit import audit

router = APIRouter(prefix="/config", tags=["config-admin"])


# ── Schemas ───────────────────────────────────────────────────

class ProposeValueIn(BaseModel):
    config_key: str
    value: Any
    effective_from: date
    scope_value: Optional[str] = None
    status: str = "draft"          # draft | scheduled
    regulatory_reference: Optional[str] = None
    note: Optional[str] = None


class ExpireIn(BaseModel):
    effective_to: date


# ── Read ──────────────────────────────────────────────────────

@router.get("/definitions")
async def list_definitions(domain: Optional[str] = None, db: Session = Depends(get_db),
                           _=Depends(get_current_user)):
    return ConfigService.list_definitions(db, domain)


@router.get("/values")
async def list_values(key: str, scope_value: Optional[str] = None,
                      include_history: bool = True, db: Session = Depends(get_db),
                      _=Depends(get_current_user)):
    return ConfigService.list_values(db, key, scope_value, include_history)


@router.get("/effective")
async def effective(key: str, as_of: Optional[date] = None,
                    scope_value: Optional[str] = None, db: Session = Depends(get_db),
                    _=Depends(get_current_user)):
    row = ConfigService.effective_detail(db, key, as_of, scope_value)
    if row is None:
        raise HTTPException(status_code=404, detail="No effective value for that key/date")
    return row


# ── Maker-checker lifecycle ───────────────────────────────────

@router.post("/values")
async def propose_value(payload: ProposeValueIn, db: Session = Depends(get_db),
                        user=Depends(require_super_admin)):
    try:
        ConfigService.validate_value(db, payload.config_key, payload.value)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if payload.status not in ("draft", "scheduled"):
        raise HTTPException(status_code=400, detail="status must be draft or scheduled")
    cv = ConfigService.propose(
        db, key=payload.config_key, value=payload.value,
        effective_from=payload.effective_from, scope_value=payload.scope_value,
        status=payload.status, regulatory_reference=payload.regulatory_reference,
        note=payload.note, user_id=user.id)
    db.commit()
    audit(db, user.id, "create", "config",
          f"Proposed {payload.config_key} = {payload.value} (eff {payload.effective_from})",
          record_type="config_value", record_id=cv.id)
    return ConfigService._fmt_value(cv)


@router.post("/values/{value_id}/activate")
async def activate_value(value_id: int, db: Session = Depends(get_db),
                         user=Depends(require_super_admin)):
    cv = db.query(ConfigValue).filter(ConfigValue.id == value_id).first()
    if cv is None:
        raise HTTPException(status_code=404, detail="Config value not found")
    if ConfigService.get_bool(db, "governance.require_separate_checker", default=False) \
            and cv.created_by is not None and cv.created_by == user.id:
        raise HTTPException(status_code=403,
                            detail="A different user must approve this change (maker-checker)")
    ConfigService.activate(db, value_id, user.id)
    db.commit()
    audit(db, user.id, "approve", "config",
          f"Activated {cv.config_key} v{cv.version} = (id {cv.id})",
          record_type="config_value", record_id=cv.id)
    return ConfigService._fmt_value(cv)


@router.post("/values/{value_id}/expire")
async def expire_value(value_id: int, payload: ExpireIn, db: Session = Depends(get_db),
                       user=Depends(require_super_admin)):
    try:
        ConfigService.expire(db, value_id, payload.effective_to, user.id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    db.commit()
    audit(db, user.id, "update", "config", f"Expired config value {value_id}",
          record_type="config_value", record_id=value_id)
    return {"id": value_id, "status": "expired", "effective_to": payload.effective_to}


@router.post("/values/{value_id}/revoke")
async def revoke_value(value_id: int, db: Session = Depends(get_db),
                       user=Depends(require_super_admin)):
    try:
        ConfigService.revoke(db, value_id, user.id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    db.commit()
    audit(db, user.id, "delete", "config", f"Revoked config value {value_id}",
          record_type="config_value", record_id=value_id)
    return {"id": value_id, "status": "revoked"}


@router.post("/run-scheduler")
async def run_scheduler(db: Session = Depends(get_db), user=Depends(require_super_admin)):
    """Activate any scheduled values whose effective date has arrived."""
    n = ConfigService.activate_due_scheduled(db, user_id=user.id)
    db.commit()
    if n:
        audit(db, user.id, "update", "config",
              f"Scheduler activated {n} due config value(s)",
              record_type="config_value", record_id=None)
    return {"activated": n}
