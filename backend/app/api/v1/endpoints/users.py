"""
Legacy /api/v1/users/ endpoints.

DEPRECATED — kept alive as shims for external API compatibility. All handlers
delegate to UserService (the same service backing /api/v1/users-admin/).
New clients should use /api/v1/users-admin/ — see app/api/v1/endpoints/security.py.
"""
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel, EmailStr
from typing import Optional

from app.db.session import get_db
from app.models.models import User, UserRole
from app.core.security import require_admin, assert_can_assign_role
from app.services.security_service import UserService

router = APIRouter(prefix="/users", tags=["users (deprecated)"])


# ── Legacy schemas (kept for stricter inbound validation) ──
class UserCreate(BaseModel):
    username: str
    email: EmailStr
    full_name: str
    password: str
    role: UserRole


class UserUpdate(BaseModel):
    email: Optional[EmailStr] = None
    full_name: Optional[str] = None
    role: Optional[UserRole] = None
    is_active: Optional[bool] = None


class PasswordReset(BaseModel):
    new_password: str


def _role_str(role) -> Optional[str]:
    """Unwrap UserRole enum to its string value, leave str/None alone."""
    if role is None:
        return None
    return role.value if hasattr(role, "value") else str(role)


# ── Endpoints (all deprecated) ──
@router.get("/", deprecated=True)
async def list_users(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=500),
    role: Optional[UserRole] = None,
    is_active: Optional[bool] = None,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    return UserService.list_users(db, page, page_size, None, _role_str(role), is_active)


@router.post("/", status_code=201, deprecated=True)
async def create_user(
    payload: UserCreate,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    assert_can_assign_role(current_user, _role_str(payload.role))
    return UserService.create_user(
        db, payload.username, payload.full_name, payload.email,
        payload.password, _role_str(payload.role), current_user,
    )


@router.get("/{user_id}", deprecated=True)
async def get_user(
    user_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    return UserService.get_by_id(db, user_id)


@router.put("/{user_id}", deprecated=True)
async def update_user(
    user_id: int,
    payload: UserUpdate,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    updates = payload.dict(exclude_none=True)
    if "role" in updates:
        updates["role"] = _role_str(updates["role"])
    target = db.query(User).filter(User.id == user_id).first()
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    assert_can_assign_role(current_user, updates.get("role"), target)
    return UserService.update_user(db, user_id, updates, current_user)


@router.post("/{user_id}/reset-password", deprecated=True)
async def reset_password(
    user_id: int,
    payload: PasswordReset,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return UserService.reset_password(db, user_id, payload.new_password, current_user)


@router.get("/activity-logs/all", deprecated=True)
async def get_activity_logs(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    module: Optional[str] = None,
    user_id: Optional[int] = None,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    """Legacy activity log endpoint. Filter by `module` is preserved here for
    backward compat; the new /api/v1/activity-log/ filters by `action` + date range."""
    from app.models.models import ActivityLog
    from sqlalchemy import desc
    from app.utils.helpers import paginate
    q = db.query(ActivityLog)
    if module:
        q = q.filter(ActivityLog.module == module)
    if user_id:
        q = q.filter(ActivityLog.user_id == user_id)
    return paginate(q.order_by(desc(ActivityLog.created_at)), page, page_size)
