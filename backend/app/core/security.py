from datetime import datetime, timedelta
from typing import Optional
import hashlib
import bcrypt as _bcrypt
from jose import JWTError, jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from app.core.config import settings
from app.db.session import get_db

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")


# ── Password Hashing ─────────────────────────────────────────

def hash_password(password: str) -> str:
    return _bcrypt.hashpw(password.encode("utf-8"), _bcrypt.gensalt()).decode("utf-8")

def verify_password(plain: str, hashed: str) -> bool:
    try:
        return _bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except Exception:
        return False

# Aliases for original code compatibility
get_password_hash = hash_password

def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


# ── JWT ───────────────────────────────────────────────────────

def create_access_token(user_id_or_data, role: str = "sales", expire_minutes: int = None) -> str:
    """Supports both create_access_token(id, role) and create_access_token({"sub":...}).

    `expire_minutes` lets a caller (with a db handle) inject the effective-dated
    token TTL from config; None falls back to settings.ACCESS_TOKEN_EXPIRE_MINUTES.
    """
    mins = expire_minutes if expire_minutes is not None else settings.ACCESS_TOKEN_EXPIRE_MINUTES
    if isinstance(user_id_or_data, dict):
        data = user_id_or_data.copy()
        expire = datetime.utcnow() + timedelta(minutes=mins)
        data.update({"exp": expire, "type": "access"})
        return jwt.encode(data, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    else:
        expire = datetime.utcnow() + timedelta(minutes=mins)
        return jwt.encode(
            {"sub": str(user_id_or_data), "role": role, "exp": expire, "type": "access"},
            settings.SECRET_KEY, algorithm=settings.ALGORITHM
        )

def create_refresh_token(user_id: int, expire_days: int = None) -> str:
    days = expire_days if expire_days is not None else settings.REFRESH_TOKEN_EXPIRE_DAYS
    expire = datetime.utcnow() + timedelta(days=days)
    return jwt.encode(
        {"sub": str(user_id), "exp": expire, "type": "refresh"},
        settings.SECRET_KEY, algorithm=settings.ALGORITHM
    )

def decode_token(token: str) -> Optional[dict]:
    try:
        return jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
    except JWTError:
        return None


# ── Dependencies ──────────────────────────────────────────────

def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    from app.models.models import User
    exc = HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Could not validate credentials", headers={"WWW-Authenticate": "Bearer"})
    payload = decode_token(token)
    if not payload:
        raise exc
    user_id = payload.get("sub")
    if not user_id:
        raise exc
    user = db.query(User).filter(User.id == int(user_id), User.is_active == True).first()
    if not user:
        raise exc
    return user

def _role_str(user) -> str:
    role = getattr(user, "role", None)
    return role.value if hasattr(role, "value") else (role or "")

def is_super_admin(user) -> bool:
    """True if the user is a super-admin (role='super_admin')."""
    return _role_str(user) == "super_admin"

def require_admin(current_user=Depends(get_current_user)):
    role = _role_str(current_user)
    if role not in ("admin", "super_admin"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
    return current_user

def require_admin_or_accountant(current_user=Depends(get_current_user)):
    role = _role_str(current_user)
    if role not in ("admin", "accountant", "super_admin"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin or Accountant access required")
    return current_user

def require_super_admin(current_user=Depends(get_current_user)):
    if not is_super_admin(current_user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Super-admin access required")
    return current_user

def require_warehouse_ops(current_user=Depends(get_current_user)):
    """Stock adjustments, write-offs and ageing — super-admin, admin or warehouse."""
    role = _role_str(current_user)
    if role not in ("super_admin", "admin", "warehouse"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Warehouse operations access required")
    return current_user


def assert_can_assign_role(actor, requested_role: Optional[str], target=None) -> None:
    """Granting or revoking the super_admin role is reserved to super-admins.

    - Assigning role='super_admin' (create or update) requires actor to be super-admin.
    - Demoting an existing super_admin (changing their role to anything else)
      also requires actor to be super-admin — otherwise a regular admin could
      strip privileges from the only super-admin and lock everyone out.
    """
    touches_super = requested_role == "super_admin"
    if target is not None and requested_role and requested_role != "super_admin":
        current_role = str(getattr(target, "role", "")).replace("UserRole.", "")
        if current_role == "super_admin":
            touches_super = True
    if touches_super and not is_super_admin(actor):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only a super-admin can assign or revoke the super_admin role",
        )
