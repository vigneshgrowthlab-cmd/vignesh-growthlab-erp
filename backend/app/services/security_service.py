import json
from sqlalchemy.orm import Session
from sqlalchemy import func, desc
from fastapi import HTTPException
from datetime import datetime, timedelta, date
from typing import Optional, List
import io

from app.models.models import User, ActivityLog, ActiveSession, LoginHistory
from app.utils.helpers import paginate
from app.core.config import settings
from app.services.config_service import ConfigService


def _role_of(user) -> str:
    """Extract role as plain string, unwrapping enum if present."""
    if user is None:
        return ""
    role = getattr(user, "role", None)
    return role.value if hasattr(role, "value") else (role or "")


_PRIVILEGED_ROLES = {"admin", "super_admin"}


def _get_wid(db, user_id):
    """Read warehouse_id via raw SQL to bypass ORM column mapping issues."""
    try:
        from sqlalchemy import text as _t2
        row = db.execute(_t2("SELECT warehouse_id FROM users WHERE id=:id"), {"id": user_id}).fetchone()
        return row[0] if row else None
    except Exception:
        return None


def _get_admin_warehouse_ids(db, user_id) -> list:
    """Warehouse IDs assigned to an admin user via the user_warehouses join table."""
    try:
        from sqlalchemy import text as _t3
        rows = db.execute(
            _t3("SELECT warehouse_id FROM user_warehouses WHERE user_id=:id ORDER BY warehouse_id"),
            {"id": user_id},
        ).fetchall()
        return [r[0] for r in rows]
    except Exception:
        return []


class UserService:

    @staticmethod
    def list_users(db: Session, page: int = 1, page_size: int = 20,
                   search: Optional[str] = None, role: Optional[str] = None,
                   is_active: Optional[bool] = None) -> dict:
        q = db.query(User)
        if search:
            q = q.filter(
                (User.username.ilike(f"%{search}%")) |
                (User.full_name.ilike(f"%{search}%")) |
                (User.email.ilike(f"%{search}%"))
            )
        if role:
            q = q.filter(User.role == role)
        if is_active is not None:
            q = q.filter(User.is_active == is_active)
        result = paginate(q.order_by(User.full_name), page, page_size)
        items = []
        for u in result["items"]:
            last = db.query(ActivityLog).filter(
                ActivityLog.user_id == u.id,
                ActivityLog.action == "login"
            ).order_by(desc(ActivityLog.created_at)).first()
            role_str = u.role.value if hasattr(u.role, "value") else (u.role or "")
            items.append({
                "id": u.id, "username": u.username, "full_name": u.full_name,
                "email": u.email, "role": u.role, "is_active": u.is_active,
                "warehouse_id": _get_wid(db, u.id),
                "warehouse_ids": _get_admin_warehouse_ids(db, u.id) if role_str == "admin" else [],
                "is_locked": getattr(u, 'is_locked', False),
                "locked_until": getattr(u, 'locked_until', None),
                "failed_login_count": getattr(u, 'failed_login_count', 0),
                "last_login": last.created_at if last else None,
                "created_at": u.created_at,
            })
        result["items"] = items
        return result

    @staticmethod
    def get_by_id(db: Session, user_id: int) -> dict:
        u = db.query(User).filter(User.id == user_id).first()
        if not u:
            raise HTTPException(status_code=404, detail="User not found")
        role_str = u.role.value if hasattr(u.role, "value") else (u.role or "")
        return {
            "id": u.id, "username": u.username, "full_name": u.full_name,
            "email": u.email, "role": u.role, "is_active": u.is_active,
            "warehouse_id": _get_wid(db, u.id),
            "warehouse_ids": _get_admin_warehouse_ids(db, u.id) if role_str == "admin" else [],
            "is_locked": getattr(u, 'is_locked', False),
            "locked_until": getattr(u, 'locked_until', None),
            "failed_login_count": getattr(u, 'failed_login_count', 0),
            "created_at": u.created_at,
        }

    @staticmethod
    def create_user(db: Session, username: str, full_name: str, email: str,
                    password: str, role: str, creator: User,
                    warehouse_id: int = None, warehouse_ids: list = None) -> dict:
        # Only super_admin can mint admin or super_admin users
        if role in _PRIVILEGED_ROLES and _role_of(creator) != "super_admin":
            raise HTTPException(
                status_code=403,
                detail="Only super-admin can create admin or super-admin users",
            )
        # Admin must have at least one warehouse assigned
        if role == "admin":
            if not warehouse_ids:
                raise HTTPException(
                    status_code=400,
                    detail="Admin users must be assigned to at least one warehouse.",
                )
        email = email.strip() if email else None
        email = email if email else None
        from app.core.security import hash_password
        if db.query(User).filter(User.username == username).first():
            raise HTTPException(status_code=400, detail="Username already exists")
        u = User(
            username=username, full_name=full_name, email=email,
            hashed_password=hash_password(password), role=role,
            is_active=True, created_by=creator.id,
        )
        try:
            u.is_locked = False
            u.failed_login_count = 0
        except Exception:
            pass
        db.add(u)
        db.flush()
        # Save warehouse_id via raw SQL (column may not be ORM-mapped yet)
        if warehouse_id:
            try:
                from sqlalchemy import text as _t
                db.execute(_t("UPDATE users SET warehouse_id=:w WHERE id=:id"),
                           {"w": int(warehouse_id), "id": u.id})
            except Exception as _e:
                print(f"[USER] warehouse_id save failed: {_e}")
        # Admin: save multi-warehouse assignments via user_warehouses join table
        if role == "admin" and warehouse_ids:
            try:
                from sqlalchemy import text as _tw
                for wid in warehouse_ids:
                    db.execute(
                        _tw("INSERT IGNORE INTO user_warehouses (user_id, warehouse_id, assigned_by) VALUES (:uid, :wid, :by)"),
                        {"uid": u.id, "wid": int(wid), "by": creator.id},
                    )
            except Exception as _e:
                print(f"[USER] warehouse_ids save failed: {_e}")
        db.commit()
        db.refresh(u)
        ActivityLogService.log(db, creator.id, "user_created",
                               f"Created user {username} ({role})", "user", u.id)
        return UserService.get_by_id(db, u.id)

    @staticmethod
    def update_user(db: Session, user_id: int, updates: dict, updater: User) -> dict:
        u = db.query(User).filter(User.id == user_id).first()
        if not u:
            raise HTTPException(status_code=404, detail="User not found")
        is_self = (user_id == updater.id)
        updater_role = _role_of(updater)
        if is_self and updates.get("is_active") is False:
            raise HTTPException(status_code=400, detail="Cannot deactivate your own account")
        # Role-change gate: only super_admin can change another user's role,
        # and even super_admin can't change their own role here (use a fresh
        # super_admin account to do that — prevents accidental self-demotion).
        if "role" in updates and updates.get("role") and updates["role"] != _role_of(u):
            if is_self:
                raise HTTPException(status_code=400, detail="Cannot change your own role")
            if updater_role != "super_admin":
                raise HTTPException(status_code=403, detail="Only super-admin can change user roles")
        # Protect super_admin targets from non-super_admin updaters
        if _role_of(u) == "super_admin" and updater_role != "super_admin" and not is_self:
            raise HTTPException(status_code=403, detail="Only super-admin can manage another super-admin's account")
        # Normalize + validate full_name
        if "full_name" in updates:
            name = (updates.get("full_name") or "").strip()
            if not name:
                raise HTTPException(status_code=400, detail="Full name cannot be empty")
            updates["full_name"] = name
        # Normalize + validate email (uniqueness check against other users)
        if "email" in updates:
            email = (updates.get("email") or "").strip()
            if not email:
                # email is NOT NULL in schema — refuse to clear it
                raise HTTPException(status_code=400, detail="Email cannot be empty")
            if email != (u.email or ""):
                existing = db.query(User).filter(
                    User.email == email, User.id != user_id
                ).first()
                if existing:
                    raise HTTPException(status_code=400, detail="Email already in use by another user")
            updates["email"] = email
        # Save warehouse_id via raw SQL — bypasses ORM column mapping issues
        if "warehouse_id" in updates:
            wid = updates.pop("warehouse_id")
            try:
                from sqlalchemy import text as _text2
                db.execute(_text2("UPDATE users SET warehouse_id=:w WHERE id=:id"),
                           {"w": int(wid) if wid else None, "id": user_id})
                db.flush()
                print(f"[USER] warehouse_id updated to {wid} for user {user_id}")
            except Exception as _we:
                print(f"[USER] warehouse_id update failed: {_we}")
        # Admin multi-warehouse update — replace all assignments
        if "warehouse_ids" in updates:
            new_wids = updates.pop("warehouse_ids") or []
            target_role = _role_of(u) if "role" not in updates else (updates.get("role") or _role_of(u))
            if target_role == "admin":
                if not new_wids:
                    raise HTTPException(
                        status_code=400,
                        detail="Admin users must be assigned to at least one warehouse.",
                    )
                try:
                    from sqlalchemy import text as _tw2
                    db.execute(_tw2("DELETE FROM user_warehouses WHERE user_id=:uid"), {"uid": user_id})
                    for wid in new_wids:
                        db.execute(
                            _tw2("INSERT IGNORE INTO user_warehouses (user_id, warehouse_id, assigned_by) VALUES (:uid, :wid, :by)"),
                            {"uid": user_id, "wid": int(wid), "by": updater.id},
                        )
                    db.flush()
                except Exception as _we2:
                    print(f"[USER] warehouse_ids update failed: {_we2}")
        for k, v in updates.items():
            if v is not None and hasattr(u, k):
                setattr(u, k, v)
        u.updated_by = updater.id
        try:
            db.commit()
        except Exception as e:
            db.rollback()
            # Catch any DB-level integrity errors we didn't pre-empt
            msg = str(getattr(e, "orig", e)).lower()
            if "duplicate" in msg or "unique" in msg:
                raise HTTPException(status_code=400, detail="A field value conflicts with another user")
            raise HTTPException(status_code=500, detail="Failed to update user")
        ActivityLogService.log(db, updater.id, "user_updated",
                               f"Updated user {u.username}", "user", user_id)
        return UserService.get_by_id(db, user_id)

    @staticmethod
    def _guard_super_admin_target(target: User, actor: User) -> None:
        """Block actions against a super_admin target unless the actor is also super_admin."""
        if _role_of(target) == "super_admin" and _role_of(actor) != "super_admin":
            raise HTTPException(
                status_code=403,
                detail="Only super-admin can manage another super-admin's account",
            )

    @staticmethod
    def reset_password(db: Session, user_id: int, new_password: str, actor: User) -> dict:
        from app.core.security import hash_password
        u = db.query(User).filter(User.id == user_id).first()
        if not u:
            raise HTTPException(status_code=404, detail="User not found")
        UserService._guard_super_admin_target(u, actor)
        u.hashed_password = hash_password(new_password)
        try:
            u.is_locked = False
            u.failed_login_count = 0
        except Exception:
            pass
        db.commit()
        # Kill active sessions
        db.query(ActiveSession).filter(ActiveSession.user_id == user_id).delete()
        db.commit()
        LoginHistoryService.record_logout(db, user_id)
        ActivityLogService.log(db, actor.id, "password_reset",
                               f"Password reset for {u.username}", "user", user_id)
        return {"message": f"Password reset for {u.username}. User must log in again."}

    @staticmethod
    def force_logout(db: Session, user_id: int, actor: User) -> dict:
        u = db.query(User).filter(User.id == user_id).first()
        if not u:
            raise HTTPException(status_code=404, detail="User not found")
        UserService._guard_super_admin_target(u, actor)
        db.query(ActiveSession).filter(ActiveSession.user_id == user_id).delete()
        db.commit()
        LoginHistoryService.record_logout(db, user_id)
        ActivityLogService.log(db, actor.id, "force_logout",
                               f"Force logged out {u.username}", "user", user_id)
        return {"message": f"User {u.username} logged out from all sessions"}

    @staticmethod
    def suspend(db: Session, user_id: int, actor: User) -> dict:
        u = db.query(User).filter(User.id == user_id).first()
        if not u:
            raise HTTPException(status_code=404, detail="User not found")
        if user_id == actor.id:
            raise HTTPException(status_code=400, detail="Cannot suspend your own account")
        UserService._guard_super_admin_target(u, actor)
        u.is_active = False
        db.query(ActiveSession).filter(ActiveSession.user_id == user_id).delete()
        db.commit()
        LoginHistoryService.record_logout(db, user_id)
        ActivityLogService.log(db, actor.id, "account_suspended",
                               f"Suspended {u.username}", "user", user_id)
        return {"message": f"User {u.username} suspended"}

    @staticmethod
    def unsuspend(db: Session, user_id: int, actor: User) -> dict:
        u = db.query(User).filter(User.id == user_id).first()
        if not u:
            raise HTTPException(status_code=404, detail="User not found")
        UserService._guard_super_admin_target(u, actor)
        u.is_active = True
        db.commit()
        ActivityLogService.log(db, actor.id, "account_unsuspended",
                               f"Unsuspended {u.username}", "user", user_id)
        return {"message": f"User {u.username} unsuspended"}

    @staticmethod
    def unlock(db: Session, user_id: int, actor: User) -> dict:
        u = db.query(User).filter(User.id == user_id).first()
        if not u:
            raise HTTPException(status_code=404, detail="User not found")
        UserService._guard_super_admin_target(u, actor)
        try:
            u.is_locked = False
            u.locked_until = None
            u.failed_login_count = 0
        except Exception:
            pass
        db.commit()
        ActivityLogService.log(db, actor.id, "account_unlocked",
                               f"Unlocked account for {u.username}", "user", user_id)
        return {"message": f"Account unlocked for {u.username}"}


class SessionService:

    @staticmethod
    def get_active_sessions(db: Session) -> List[dict]:
        cutoff = datetime.utcnow() - timedelta(hours=24)
        sessions = db.query(ActiveSession).filter(
            ActiveSession.last_seen >= cutoff
        ).order_by(desc(ActiveSession.last_seen)).all()
        result = []
        for s in sessions:
            u = db.query(User).filter(User.id == s.user_id).first()
            result.append({
                "id": s.id, "user_id": s.user_id,
                "username": u.username if u else None,
                "full_name": u.full_name if u else None,
                "role": u.role if u else None,
                "ip_address": s.ip_address,
                "device_info": s.device_info,
                "location": getattr(s, 'location', None),
                "login_time": s.login_time,
                "last_seen": s.last_seen,
            })
        return result


class ActivityLogService:

    @staticmethod
    def log(db: Session, user_id: int, action: str, details: str,
            resource_type: Optional[str] = None, resource_id: Optional[int] = None,
            ip_address: Optional[str] = None):
        entry = ActivityLog(
            user_id=user_id, action=action, details=details,
            resource_type=resource_type, resource_id=resource_id,
            ip_address=ip_address,
        )
        db.add(entry)
        try:
            db.commit()
        except Exception:
            db.rollback()

    @staticmethod
    def list_logs(db: Session, user_id: Optional[int] = None,
                  action: Optional[str] = None,
                  date_from: Optional[date] = None,
                  date_to: Optional[date] = None,
                  page: int = 1, page_size: int = 50,
                  module: Optional[str] = None,
                  record_type: Optional[str] = None,
                  search: Optional[str] = None) -> dict:
        q = db.query(ActivityLog)
        if user_id:
            q = q.filter(ActivityLog.user_id == user_id)
        if action:
            q = q.filter(ActivityLog.action.ilike(f"%{action}%"))
        if module:
            q = q.filter(ActivityLog.module == module)
        if record_type:
            q = q.filter(ActivityLog.record_type == record_type)
        if search:
            q = q.filter(ActivityLog.details.ilike(f"%{search}%"))
        if date_from:
            q = q.filter(func.date(ActivityLog.created_at) >= date_from)
        if date_to:
            q = q.filter(func.date(ActivityLog.created_at) <= date_to)
        result = paginate(q.order_by(desc(ActivityLog.created_at)), page, page_size)
        # Batch the user lookup to avoid one query per row.
        uids = {log.user_id for log in result["items"] if log.user_id}
        umap = {}
        if uids:
            for u in db.query(User).filter(User.id.in_(uids)).all():
                umap[u.id] = u
        items = []
        for log in result["items"]:
            u = umap.get(log.user_id)
            items.append({
                "id": log.id, "user_id": log.user_id,
                "username": u.username if u else None,
                "full_name": u.full_name if u else None,
                "action": log.action, "details": log.details,
                "module": log.module,
                "record_type": log.record_type, "record_id": log.record_id,
                "resource_type": log.resource_type, "resource_id": log.resource_id,
                "old_values": log.old_values, "new_values": log.new_values,
                "ip_address": log.ip_address, "created_at": log.created_at,
            })
        result["items"] = items
        return result

    @staticmethod
    def get_suspicious(db: Session) -> List[dict]:
        window_h = ConfigService.get_int(db, "dpdp.suspicious_window_hours", default=24)
        fail_thresh = ConfigService.get_int(db, "dpdp.suspicious_failed_logins", default=3)
        export_thresh = ConfigService.get_int(db, "dpdp.suspicious_exports", default=5)
        cutoff = datetime.utcnow() - timedelta(hours=window_h)
        suspicious = []

        # Multiple failed logins
        failed = db.query(
            ActivityLog.user_id,
            func.count(ActivityLog.id).label("cnt")
        ).filter(
            ActivityLog.action == "login_failed",
            ActivityLog.created_at >= cutoff,
        ).group_by(ActivityLog.user_id).having(
            func.count(ActivityLog.id) >= fail_thresh
        ).all()
        for row in failed:
            u = db.query(User).filter(User.id == row.user_id).first()
            suspicious.append({
                "type": "multiple_failed_logins",
                "description": f"{row.cnt} failed login attempts",
                "user": u.username if u else None,
                "severity": "high", "count": row.cnt,
            })

        # Bulk exports
        exports = db.query(
            ActivityLog.user_id,
            func.count(ActivityLog.id).label("cnt")
        ).filter(
            ActivityLog.action == "export",
            ActivityLog.created_at >= cutoff,
        ).group_by(ActivityLog.user_id).having(
            func.count(ActivityLog.id) >= export_thresh
        ).all()
        for row in exports:
            u = db.query(User).filter(User.id == row.user_id).first()
            suspicious.append({
                "type": "bulk_exports",
                "description": f"{row.cnt} data exports in last 24 hours",
                "user": u.username if u else None,
                "severity": "high", "count": row.cnt,
            })

        return suspicious


class LoginHistoryService:

    @staticmethod
    def record_login(db: Session, user: User) -> Optional[LoginHistory]:
        try:
            entry = LoginHistory(
                user_id=user.id,
                username=user.username,
                full_name=user.full_name,
                login_at=datetime.utcnow(),
            )
            db.add(entry)
            db.commit()
            db.refresh(entry)
            return entry
        except Exception:
            db.rollback()
            return None

    @staticmethod
    def record_logout(db: Session, user_id: int) -> None:
        try:
            open_rows = db.query(LoginHistory).filter(
                LoginHistory.user_id == user_id,
                LoginHistory.logout_at.is_(None),
            ).order_by(desc(LoginHistory.login_at)).all()
            now = datetime.utcnow()
            for row in open_rows:
                row.logout_at = now
                if row.login_at:
                    delta = now - row.login_at
                    row.session_duration_seconds = max(0, int(delta.total_seconds()))
            if open_rows:
                db.commit()
        except Exception:
            db.rollback()

    @staticmethod
    def list_history(db: Session, user_id: Optional[int] = None,
                     username: Optional[str] = None,
                     date_from: Optional[date] = None,
                     date_to: Optional[date] = None,
                     page: int = 1, page_size: int = 50) -> dict:
        q = db.query(LoginHistory)
        if user_id:
            q = q.filter(LoginHistory.user_id == user_id)
        if username:
            q = q.filter(LoginHistory.username.ilike(f"%{username}%"))
        if date_from:
            q = q.filter(func.date(LoginHistory.login_at) >= date_from)
        if date_to:
            q = q.filter(func.date(LoginHistory.login_at) <= date_to)
        result = paginate(q.order_by(desc(LoginHistory.login_at)), page, page_size)
        items = []
        for row in result["items"]:
            items.append({
                "id": row.id,
                "user_id": row.user_id,
                "username": row.username,
                "full_name": row.full_name,
                "login_at": row.login_at,
                "logout_at": row.logout_at,
                "session_duration_seconds": row.session_duration_seconds,
            })
        result["items"] = items
        return result


class WatermarkService:

    @staticmethod
    def watermark_text(username: str) -> str:
        from datetime import datetime
        ts = datetime.now().strftime("%d/%m/%Y %H:%M")
        return f"Downloaded by: {username} | {ts}"

    @staticmethod
    def add_excel_metadata(excel_bytes: bytes, username: str, user_id: int) -> bytes:
        try:
            from openpyxl import load_workbook
            wb = load_workbook(io.BytesIO(excel_bytes))
            ws = wb.create_sheet("_audit", -1)
            ws.sheet_state = "hidden"
            from datetime import datetime
            ws["A1"] = "Downloaded By"; ws["B1"] = username
            ws["A2"] = "User ID"; ws["B2"] = user_id
            ws["A3"] = "Timestamp"; ws["B3"] = datetime.now().isoformat()
            ws["A4"] = "System"; ws["B4"] = "Wholesale ERP — Confidential"
            out = io.BytesIO()
            wb.save(out)
            return out.getvalue()
        except Exception:
            return excel_bytes


class TwoFAService:
    _store = {}

    @classmethod
    def generate_and_send(cls, user: User) -> str:
        import random
        otp = str(random.randint(100000, 999999))
        from datetime import datetime, timedelta
        cls._store[user.id] = {
            "otp": otp,
            "expires": datetime.utcnow() + timedelta(minutes=10),
        }
        # In dev mode print to console; in prod send email
        print(f"[2FA OTP] User: {user.username} | OTP: {otp}")
        return otp

    @classmethod
    def verify(cls, user_id: int, otp: str) -> bool:
        from datetime import datetime
        stored = cls._store.get(user_id)
        if not stored:
            return False
        if datetime.utcnow() > stored["expires"]:
            del cls._store[user_id]
            return False
        if stored["otp"] == otp:
            del cls._store[user_id]
            return True
        return False