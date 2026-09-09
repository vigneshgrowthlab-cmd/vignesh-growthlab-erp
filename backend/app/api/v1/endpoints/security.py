from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from typing import Optional, List
from datetime import date
from pydantic import BaseModel, Field

from app.db.session import get_db
from app.models.models import User
from app.core.security import (
    get_current_user, require_admin, require_admin_or_accountant,
    require_super_admin, is_super_admin, assert_can_assign_role,
)
from app.services.security_service import (
    UserService, SessionService, ActivityLogService, TwoFAService, LoginHistoryService
)

# ── User Management ───────────────────────────────────────────
users_router = APIRouter(prefix="/users-admin", tags=["user-management"])


class UserCreatePayload(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    warehouse_id: Optional[int] = None           # warehouse role: single warehouse
    warehouse_ids: Optional[List[int]] = None    # admin role: 1..N warehouses (min 1)
    full_name: str = Field(..., min_length=1, max_length=100)
    email: Optional[str] = None
    password: str = Field(..., min_length=8)
    role: str = Field(default="sales", min_length=1, max_length=30)


class UserUpdatePayload(BaseModel):
    full_name: Optional[str] = None
    email: Optional[str] = None
    role: Optional[str] = None
    warehouse_id: Optional[int] = None           # warehouse role
    warehouse_ids: Optional[List[int]] = None    # admin role
    is_active: Optional[bool] = None


class PasswordResetPayload(BaseModel):
    new_password: str = Field(..., min_length=8)


@users_router.get("/")
async def list_users(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=500),
    search: Optional[str] = None,
    role: Optional[str] = None,
    is_active: Optional[bool] = None,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin_or_accountant),
):
    return UserService.list_users(db, page, page_size, search, role, is_active)


@users_router.post("/", status_code=201)
async def create_user(
    payload: UserCreatePayload,
    current_user: User = Depends(require_admin_or_accountant),
    db: Session = Depends(get_db),
):
    assert_can_assign_role(current_user, payload.role)
    return UserService.create_user(
        db, payload.username, payload.full_name, payload.email or None,
        payload.password, payload.role, current_user,
        warehouse_id=payload.warehouse_id,
        warehouse_ids=payload.warehouse_ids,
    )


@users_router.get("/{user_id}")
async def get_user(
    user_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin_or_accountant),
):
    return UserService.get_by_id(db, user_id)


@users_router.put("/{user_id}")
async def update_user(
    user_id: int,
    payload: UserUpdatePayload,
    current_user: User = Depends(require_admin_or_accountant),
    db: Session = Depends(get_db),
):
    target = db.query(User).filter(User.id == user_id).first()
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    assert_can_assign_role(current_user, payload.role, target)
    update_data = payload.dict(exclude_none=True)
    # Always pass warehouse_ids if provided (even if empty list means clearing all)
    if payload.warehouse_ids is not None:
        update_data["warehouse_ids"] = payload.warehouse_ids
    return UserService.update_user(db, user_id, update_data, current_user)


@users_router.post("/{user_id}/reset-password")
async def reset_password(
    user_id: int,
    payload: PasswordResetPayload,
    current_user: User = Depends(require_admin_or_accountant),
    db: Session = Depends(get_db),
):
    return UserService.reset_password(db, user_id, payload.new_password, current_user)


@users_router.post("/{user_id}/force-logout")
async def force_logout(
    user_id: int,
    current_user: User = Depends(require_admin_or_accountant),
    db: Session = Depends(get_db),
):
    return UserService.force_logout(db, user_id, current_user)


@users_router.post("/{user_id}/suspend")
async def suspend_user(
    user_id: int,
    current_user: User = Depends(require_admin_or_accountant),
    db: Session = Depends(get_db),
):
    return UserService.suspend(db, user_id, current_user)


@users_router.post("/{user_id}/unsuspend")
async def unsuspend_user(
    user_id: int,
    current_user: User = Depends(require_admin_or_accountant),
    db: Session = Depends(get_db),
):
    return UserService.unsuspend(db, user_id, current_user)


@users_router.post("/{user_id}/unlock")
async def unlock_user(
    user_id: int,
    current_user: User = Depends(require_admin_or_accountant),
    db: Session = Depends(get_db),
):
    return UserService.unlock(db, user_id, current_user)


# ── Sessions ──────────────────────────────────────────────────
sessions_router = APIRouter(prefix="/sessions", tags=["sessions"])


@sessions_router.get("/active")
async def get_active_sessions(
    db: Session = Depends(get_db),
    _: User = Depends(require_super_admin),
):
    return SessionService.get_active_sessions(db)


# ── Activity Log ──────────────────────────────────────────────
activity_router = APIRouter(prefix="/activity-log", tags=["activity-log"])


@activity_router.get("/")
async def list_logs(
    user_id: Optional[int] = None,
    action: Optional[str] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=500),
    db: Session = Depends(get_db),
    _: User = Depends(require_super_admin),
):
    return ActivityLogService.list_logs(db, user_id, action, date_from, date_to, page, page_size)


@activity_router.get("/suspicious")
async def get_suspicious(
    db: Session = Depends(get_db),
    _: User = Depends(require_super_admin),
):
    return ActivityLogService.get_suspicious(db)


# ── Audit Trail (super-admin only) ────────────────────────────
@activity_router.get("/audit")
async def audit_trail(
    user_id: Optional[int] = None,
    action: Optional[str] = None,
    module: Optional[str] = None,
    record_type: Optional[str] = None,
    search: Optional[str] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=500),
    db: Session = Depends(get_db),
    _: User = Depends(require_super_admin),
):
    return ActivityLogService.list_logs(
        db, user_id, action, date_from, date_to, page, page_size,
        module=module, record_type=record_type, search=search,
    )


# ── Login History ─────────────────────────────────────────────
login_history_router = APIRouter(prefix="/login-history", tags=["login-history"])


@login_history_router.get("/")
async def list_login_history(
    user_id: Optional[int] = None,
    username: Optional[str] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=500),
    db: Session = Depends(get_db),
    _: User = Depends(require_super_admin),
):
    return LoginHistoryService.list_history(
        db, user_id, username, date_from, date_to, page, page_size
    )


# ── 2FA ───────────────────────────────────────────────────────
twofa_router = APIRouter(prefix="/2fa", tags=["2fa"])


class OTPVerify(BaseModel):
    user_id: int
    otp: str


@twofa_router.post("/verify")
async def verify_otp(payload: OTPVerify, db: Session = Depends(get_db)):
    from app.core.security import create_access_token, create_refresh_token
    user = db.query(User).filter(User.id == payload.user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if not TwoFAService.verify(payload.user_id, payload.otp):
        raise HTTPException(status_code=401, detail="Invalid or expired OTP")
    access_token = create_access_token(user.id, user.role)
    refresh_token = create_refresh_token(user.id)
    user.refresh_token = refresh_token
    db.commit()
    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "user": {
            "id": user.id, "username": user.username,
            "full_name": user.full_name, "role": user.role,
        },
    }
