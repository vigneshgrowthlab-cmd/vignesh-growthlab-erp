"""Central audit-trail helper.

Writes one `activity_logs` row per business action (create/update/transfer/
delete/approve/cancel/payment). Logging is best-effort: every write is wrapped
in try/except and uses its own commit, so an audit failure can never roll back
or block the underlying business transaction.

Call `record(...)` AFTER the service has committed, so record_id is final and the
captured state reflects what was actually persisted.
"""
import json
from decimal import Decimal
from datetime import date, datetime
from typing import Optional

from sqlalchemy.orm import Session

from app.models.models import ActivityLog


def _json_default(o):
    if isinstance(o, Decimal):
        return str(o)
    if isinstance(o, (date, datetime)):
        return o.isoformat()
    return str(o)


def _dump(d: Optional[dict]) -> Optional[str]:
    if not d:
        return None
    try:
        return json.dumps(d, default=_json_default, ensure_ascii=False)
    except Exception:
        return None


def _norm(v):
    """Normalise for equality so 100 == Decimal('100.00') and ''/None compare."""
    if v is None:
        return None
    if isinstance(v, Decimal):
        return Decimal(str(v))
    if isinstance(v, (int, float)):
        try:
            return Decimal(str(v))
        except Exception:
            return v
    return v


def _fmt(v) -> str:
    if v is None or v == "":
        return "—"
    if isinstance(v, Decimal):
        return f"{v}"
    return str(v)


def diff(old: dict, new: dict, fields=None):
    """Compare two field dicts.

    Returns (changed, summary) where changed is {field: [old, new]} for fields
    that actually changed and summary is a human-readable string such as
    "b2b_price 100.00 → 120.00; mrp 150.00 → 160.00".
    """
    changed = {}
    keys = list(fields) if fields is not None else list(set(old) | set(new))
    for k in keys:
        ov = old.get(k)
        nv = new.get(k)
        if _norm(ov) != _norm(nv):
            changed[k] = [ov, nv]
    summary = "; ".join(f"{k} {_fmt(v[0])} → {_fmt(v[1])}" for k, v in changed.items())
    return changed, summary


def audit(db: Session, user_id: Optional[int], action: str, module: str,
          description: str, record_type: Optional[str] = None,
          record_id: Optional[int] = None, old: Optional[dict] = None,
          new: Optional[dict] = None, ip_address: Optional[str] = None) -> None:
    """Write a single audit row. Best-effort — never raises."""
    try:
        entry = ActivityLog(
            user_id=user_id,
            action=action,
            module=module,
            details=description,
            record_type=record_type,
            record_id=record_id,
            resource_type=record_type,
            resource_id=record_id,
            old_values=_dump(old),
            new_values=_dump(new),
            ip_address=ip_address,
        )
        db.add(entry)
        db.commit()
    except Exception:
        try:
            db.rollback()
        except Exception:
            pass
