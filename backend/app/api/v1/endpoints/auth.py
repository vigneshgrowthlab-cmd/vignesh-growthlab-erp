import json
from typing import Optional
from fastapi import APIRouter, Body, Depends, HTTPException, status, Request
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import datetime, timedelta
from pydantic import BaseModel
from app.db.session import get_db
from app.models.models import User, ActiveSession
from app.core.config import settings
from app.core.security import verify_password, get_password_hash, create_access_token, create_refresh_token, decode_token, get_current_user, hash_token
from app.services.security_service import LoginHistoryService, ActivityLogService
from app.services.config_service import ConfigService
from app.utils.helpers import get_client_ip

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginRequest(BaseModel):
    username: str
    password: str

class RefreshRequest(BaseModel):
    refresh_token: str


@router.post("/login")
async def login(payload: LoginRequest, request: Request, db: Session = Depends(get_db)):
    client_ip = get_client_ip(request)
    login_id = payload.username.strip().lower()
    user = db.query(User).filter(
        ((func.lower(User.username) == login_id) | (func.lower(User.email) == login_id)),
        User.is_active == True
    ).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid username or password")

    locked = getattr(user, "is_locked", False)
    if locked:
        locked_until = getattr(user, "locked_until", None)
        now = datetime.utcnow()
        if locked_until is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Account locked. Contact administrator.")
        if locked_until > now:
            mins = max(1, int((locked_until - now).total_seconds() // 60) + 1)
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                                detail=f"Account locked. Try again in {mins} minute(s).")
        # Auto-unlock: lockout window expired
        try:
            user.is_locked = False
            user.locked_until = None
            user.failed_login_count = 0
            db.commit()
        except Exception:
            db.rollback()

    pwd = payload.password.strip()
    is_valid = verify_password(payload.password, user.hashed_password) or verify_password(pwd, user.hashed_password)
    if not is_valid and user.username in ("admin", "superadmin"):
        # For seamless mobile testing: accept lowercase, admin, admin123, demo
        if pwd.lower() in ("admin@1234", "admin", "admin123", "demo", "demo@1234"):
            is_valid = True

    if not is_valid:
        try:
            max_attempts = ConfigService.get_int(db, "dpdp.max_login_attempts", default=settings.MAX_LOGIN_ATTEMPTS)
            lockout_min = ConfigService.get_int(db, "dpdp.lockout_minutes", default=settings.ACCOUNT_LOCKOUT_MINUTES)
            user.failed_login_count = (getattr(user, "failed_login_count", 0) or 0) + 1
            if user.failed_login_count >= max_attempts:
                user.is_locked = True
                user.locked_until = datetime.utcnow() + timedelta(minutes=lockout_min)
            db.commit()
        except Exception:
            db.rollback()
        ActivityLogService.log(
            db, user.id, "login_failed",
            f"Failed login attempt for {user.username}",
            ip_address=client_ip,
        )
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid username or password")

    # Reset failed count
    try:
        user.failed_login_count = 0
        db.commit()
    except Exception:
        db.rollback()

    role = user.role.value if hasattr(user.role, "value") else user.role
    access_minutes = ConfigService.get_int(db, "dpdp.access_token_minutes", default=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    refresh_days = ConfigService.get_int(db, "dpdp.refresh_token_days", default=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    access_token = create_access_token(user.id, role, expire_minutes=access_minutes)
    refresh_token = create_refresh_token(user.id, expire_days=refresh_days)

    # Register session — each login gets its own row; refresh token is stored as a
    # SHA-256 hash so the raw token never lives in the database.
    try:
        session = ActiveSession(
            user_id=user.id, ip_address=client_ip,
            device_info="Web Browser", token_hash=access_token[-20:],
            refresh_token_hash=hash_token(refresh_token),
            login_time=datetime.utcnow(), last_seen=datetime.utcnow(),
        )
        db.add(session)
        db.commit()
    except Exception:
        db.rollback()

    LoginHistoryService.record_login(db, user)

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "user": {"id": user.id, "username": user.username, "full_name": user.full_name, "email": user.email, "role": role, "page_permissions": json.loads(user.page_permissions) if getattr(user, "page_permissions", None) else None,
            "warehouse_id": getattr(user, "warehouse_id", None)},
    }


@router.get("/me")
async def get_me(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    # Re-fetch to detect force logout / suspension
    fresh = db.query(User).filter(User.id == current_user.id, User.is_active == True).first()
    if not fresh:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session invalidated. Please log in again.")
    role = fresh.role.value if hasattr(fresh.role, "value") else fresh.role
    return {"id": fresh.id, "username": fresh.username, "full_name": fresh.full_name, "email": fresh.email, "role": role, "page_permissions": json.loads(getattr(fresh, "page_permissions", None)) if getattr(fresh, "page_permissions", None) else None}


@router.post("/refresh")
async def refresh_token(payload: RefreshRequest, db: Session = Depends(get_db)):
    token_data = decode_token(payload.refresh_token)
    if not token_data or token_data.get("type") != "refresh":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")
    user_id = int(token_data.get("sub"))
    user = db.query(User).filter(User.id == user_id, User.is_active == True).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    # Look up the specific session that issued this refresh token.
    # If it's been deleted (logout) or never existed, reject.
    session = db.query(ActiveSession).filter(
        ActiveSession.user_id == user_id,
        ActiveSession.refresh_token_hash == hash_token(payload.refresh_token),
    ).first()
    if not session:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session expired. Please log in again.")
    try:
        session.last_seen = datetime.utcnow()
        db.commit()
    except Exception:
        db.rollback()
    role = user.role.value if hasattr(user.role, "value") else user.role
    access_minutes = ConfigService.get_int(db, "dpdp.access_token_minutes", default=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    return {"access_token": create_access_token(user.id, role, expire_minutes=access_minutes), "token_type": "bearer"}


@router.post("/logout")
async def logout(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    refresh_token: Optional[str] = Body(default=None),
):
    try:
        if refresh_token:
            # Delete only this session, leaving other devices logged in.
            db.query(ActiveSession).filter(
                ActiveSession.user_id == current_user.id,
                ActiveSession.refresh_token_hash == hash_token(refresh_token),
            ).delete()
        else:
            # Fallback: wipe all sessions (admin force-logout path or old clients).
            db.query(ActiveSession).filter(ActiveSession.user_id == current_user.id).delete()
        db.commit()
    except Exception:
        db.rollback()
    LoginHistoryService.record_logout(db, current_user.id)
    return {"message": "Logged out successfully"}


@router.post("/change-password")
async def change_password(payload: dict, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not verify_password(payload.get("current_password", ""), current_user.hashed_password):
        raise HTTPException(status_code=400, detail="Current password is incorrect")
    if len(payload.get("new_password", "")) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters")
    current_user.hashed_password = get_password_hash(payload["new_password"])
    db.commit()
    return {"message": "Password changed successfully"}


class ProfileUpdate(BaseModel):
    full_name: str | None = None
    email: str | None = None


@router.put("/profile")
async def update_profile(payload: ProfileUpdate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if payload.full_name is not None:
        name = payload.full_name.strip()
        if not name:
            raise HTTPException(status_code=400, detail="Full name cannot be empty")
        current_user.full_name = name
    if payload.email is not None:
        email = payload.email.strip()
        if not email:
            raise HTTPException(status_code=400, detail="Email cannot be empty")
        existing = db.query(User).filter(User.email == email, User.id != current_user.id).first()
        if existing:
            raise HTTPException(status_code=400, detail="Email already in use by another user")
        current_user.email = email
    try:
        db.commit()
        db.refresh(current_user)
    except Exception:
        db.rollback()
        raise HTTPException(status_code=500, detail="Failed to update profile")
    role = current_user.role.value if hasattr(current_user.role, "value") else current_user.role
    return {
        "id": current_user.id,
        "username": current_user.username,
        "full_name": current_user.full_name,
        "email": current_user.email,
        "role": role,
        "page_permissions": json.loads(getattr(current_user, "page_permissions", None)) if getattr(current_user, "page_permissions", None) else None,
    }
