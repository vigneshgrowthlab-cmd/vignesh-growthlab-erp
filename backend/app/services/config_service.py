"""
config_service.py - Resolver + lifecycle for the configuration-driven
parameter store (Phase 0; see docs/CONFIG_MIGRATION_PLAN.md).

Every consuming call site reads a value through this service instead of a
literal or settings.X constant, ALWAYS passing the transaction's own date as
`as_of` and the current behaviour as `default`:

    ConfigService.get_decimal(
        db, "gst.eway_bill_threshold",
        as_of=invoice.invoice_date,
        default=settings.EWAY_BILL_THRESHOLD,
    )

If no active row matches, `default` is returned -> identical to today's
behaviour. This is what keeps every rollout phase backward-compatible.

Resolution precedence (highest -> lowest):
    scoped config_value (scope_value match) -> global config_value -> default

Within the same scope, the latest effective_from / version wins.
"""
import json
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.models import ConfigDefinition, ConfigValue


# Status used when activating / superseding the currently-open row.
_LIVE_STATUS = "active"

# Statuses that count as "was genuinely in force during its date window" and so
# participate in as-of resolution. A row keeps resolving for dates inside its
# [effective_from, effective_to] window even after a newer version supersedes
# it (historical correctness) or it expires. `draft`, `scheduled`, and `revoked`
# never resolve.
_RESOLVABLE_STATUSES = ("active", "superseded", "expired")


class ConfigService:

    # ── Resolution ───────────────────────────────────────────────

    @staticmethod
    def _resolve_row(
        db: Session,
        key: str,
        as_of: Optional[date] = None,
        scope_value: Optional[str] = None,
    ) -> Optional[ConfigValue]:
        """Return the single effective ConfigValue for (key, scope) as of a date,
        or None. Scoped value beats global; latest effective beats older."""
        if as_of is None:
            as_of = date.today()
        if isinstance(as_of, datetime):
            as_of = as_of.date()

        q = (
            db.query(ConfigValue)
            .filter(
                ConfigValue.config_key == key,
                ConfigValue.status.in_(_RESOLVABLE_STATUSES),
                ConfigValue.effective_from <= as_of,
                (ConfigValue.effective_to.is_(None))
                | (ConfigValue.effective_to >= as_of),
            )
        )
        if scope_value is not None:
            # scoped rows first, then global (scope_value IS NULL) as fallback
            q = q.filter(
                (ConfigValue.scope_value == scope_value)
                | (ConfigValue.scope_value.is_(None))
            )
            rows = q.all()
            if not rows:
                return None
            rows.sort(
                key=lambda r: (
                    0 if r.scope_value == scope_value else 1,  # scoped wins
                    -_ord(r.effective_from),
                    -(r.version or 0),
                )
            )
            return rows[0]

        q = q.filter(ConfigValue.scope_value.is_(None))
        return (
            q.order_by(ConfigValue.effective_from.desc(), ConfigValue.version.desc())
            .first()
        )

    @staticmethod
    def _raw_value(
        db: Session,
        key: str,
        as_of: Optional[date] = None,
        scope_value: Optional[str] = None,
    ) -> Any:
        row = ConfigService._resolve_row(db, key, as_of, scope_value)
        if row is None or row.value_json is None:
            return None
        try:
            payload = json.loads(row.value_json)
        except (ValueError, TypeError):
            return None
        if isinstance(payload, dict) and "v" in payload:
            return payload["v"]
        return payload

    # ── Typed getters (all return `default` when unset) ──────────

    @staticmethod
    def get_json(db, key, as_of=None, scope_value=None, default=None):
        val = ConfigService._raw_value(db, key, as_of, scope_value)
        return default if val is None else val

    @staticmethod
    def get_string(db, key, as_of=None, scope_value=None, default=None):
        val = ConfigService._raw_value(db, key, as_of, scope_value)
        return default if val is None else str(val)

    @staticmethod
    def get_decimal(db, key, as_of=None, scope_value=None, default=None):
        val = ConfigService._raw_value(db, key, as_of, scope_value)
        if val is None:
            return default
        try:
            return Decimal(str(val))
        except (InvalidOperation, ValueError):
            return default

    @staticmethod
    def get_int(db, key, as_of=None, scope_value=None, default=None):
        val = ConfigService._raw_value(db, key, as_of, scope_value)
        if val is None:
            return default
        try:
            return int(val)
        except (ValueError, TypeError):
            return default

    @staticmethod
    def get_bool(db, key, as_of=None, scope_value=None, default=None):
        val = ConfigService._raw_value(db, key, as_of, scope_value)
        if val is None:
            return default
        if isinstance(val, bool):
            return val
        return str(val).strip().lower() in ("1", "true", "yes", "y", "on")

    # ── Definition catalog ───────────────────────────────────────

    @staticmethod
    def upsert_definition(
        db: Session,
        config_key: str,
        domain: str,
        data_type: str,
        unit: str = None,
        scope_type: str = "global",
        description: str = None,
        is_regulatory: bool = False,
        owner_role: str = "super_admin",
        validation: dict = None,
    ) -> ConfigDefinition:
        d = (
            db.query(ConfigDefinition)
            .filter(ConfigDefinition.config_key == config_key)
            .first()
        )
        if d is None:
            d = ConfigDefinition(config_key=config_key)
            db.add(d)
        d.domain = domain
        d.data_type = data_type
        d.unit = unit
        d.scope_type = scope_type
        d.description = description
        d.is_regulatory = is_regulatory
        d.owner_role = owner_role
        d.validation_json = json.dumps(validation) if validation else None
        db.flush()
        return d

    # ── Value lifecycle (add / modify / activate / expire / revoke) ──

    @staticmethod
    def _next_version(db: Session, key: str, scope_value: Optional[str]) -> int:
        q = db.query(func.max(ConfigValue.version)).filter(
            ConfigValue.config_key == key
        )
        q = (
            q.filter(ConfigValue.scope_value == scope_value)
            if scope_value is not None
            else q.filter(ConfigValue.scope_value.is_(None))
        )
        cur = q.scalar()
        return (cur or 0) + 1

    @staticmethod
    def propose(
        db: Session,
        key: str,
        value: Any,
        effective_from: date,
        scope_value: Optional[str] = None,
        status: str = "draft",
        regulatory_reference: str = None,
        note: str = None,
        user_id: int = None,
    ) -> ConfigValue:
        """Create a new version row (default status='draft'). Does NOT activate
        or supersede anything until activate() is called."""
        numeric = None
        try:
            numeric = Decimal(str(value))
        except (InvalidOperation, ValueError, TypeError):
            numeric = None
        cv = ConfigValue(
            config_key=key,
            scope_value=scope_value,
            value_json=json.dumps({"v": value}),
            value_numeric=numeric,
            effective_from=effective_from,
            version=ConfigService._next_version(db, key, scope_value),
            status=status,
            regulatory_reference=regulatory_reference,
            note=note,
            created_by=user_id,
        )
        db.add(cv)
        db.flush()
        return cv

    @staticmethod
    def activate(db: Session, value_id: int, user_id: int = None) -> ConfigValue:
        """Activate a row and supersede the currently-open active row for the
        same (key, scope): close it at the new row's effective_from - 1 day."""
        cv = db.query(ConfigValue).filter(ConfigValue.id == value_id).first()
        if cv is None:
            raise ValueError("config value not found")
        prior_q = db.query(ConfigValue).filter(
            ConfigValue.config_key == cv.config_key,
            ConfigValue.id != cv.id,
            ConfigValue.status == _LIVE_STATUS,
        )
        prior_q = (
            prior_q.filter(ConfigValue.scope_value == cv.scope_value)
            if cv.scope_value is not None
            else prior_q.filter(ConfigValue.scope_value.is_(None))
        )
        for prior in prior_q.all():
            if prior.effective_to is None or prior.effective_to >= cv.effective_from:
                prior.effective_to = cv.effective_from - timedelta(days=1)
                prior.status = "superseded"
                prior.approved_by = user_id
        cv.status = _LIVE_STATUS
        cv.approved_by = user_id
        cv.approved_at = datetime.utcnow()
        db.flush()
        return cv

    @staticmethod
    def expire(db: Session, value_id: int, effective_to: date, user_id: int = None) -> ConfigValue:
        cv = db.query(ConfigValue).filter(ConfigValue.id == value_id).first()
        if cv is None:
            raise ValueError("config value not found")
        cv.effective_to = effective_to
        cv.status = "expired"
        cv.approved_by = user_id
        db.flush()
        return cv

    @staticmethod
    def revoke(db: Session, value_id: int, user_id: int = None) -> ConfigValue:
        cv = db.query(ConfigValue).filter(ConfigValue.id == value_id).first()
        if cv is None:
            raise ValueError("config value not found")
        cv.status = "revoked"
        cv.approved_by = user_id
        db.flush()
        return cv

    # ── Admin / governance helpers (Phase 6) ─────────────────────

    @staticmethod
    def list_definitions(db: Session, domain: Optional[str] = None) -> list:
        q = db.query(ConfigDefinition)
        if domain:
            q = q.filter(ConfigDefinition.domain == domain)
        out = []
        for d in q.order_by(ConfigDefinition.domain, ConfigDefinition.config_key).all():
            out.append({
                "config_key": d.config_key, "domain": d.domain,
                "data_type": d.data_type, "unit": d.unit, "scope_type": d.scope_type,
                "description": d.description, "is_regulatory": d.is_regulatory,
                "owner_role": d.owner_role,
                "validation": json.loads(d.validation_json) if d.validation_json else None,
            })
        return out

    @staticmethod
    def _fmt_value(cv: ConfigValue) -> dict:
        try:
            payload = json.loads(cv.value_json) if cv.value_json else None
            value = payload["v"] if isinstance(payload, dict) and "v" in payload else payload
        except (ValueError, TypeError):
            value = None
        return {
            "id": cv.id, "config_key": cv.config_key, "scope_value": cv.scope_value,
            "value": value, "effective_from": cv.effective_from,
            "effective_to": cv.effective_to, "version": cv.version,
            "status": cv.status, "regulatory_reference": cv.regulatory_reference,
            "note": cv.note, "created_by": cv.created_by, "created_at": cv.created_at,
            "approved_by": cv.approved_by, "approved_at": cv.approved_at,
        }

    @staticmethod
    def list_values(db: Session, key: str, scope_value: Optional[str] = None,
                    include_history: bool = True) -> list:
        q = db.query(ConfigValue).filter(ConfigValue.config_key == key)
        if scope_value is not None:
            q = q.filter(ConfigValue.scope_value == scope_value)
        if not include_history:
            q = q.filter(ConfigValue.status.in_(_RESOLVABLE_STATUSES))
        rows = q.order_by(ConfigValue.effective_from.desc(), ConfigValue.version.desc()).all()
        return [ConfigService._fmt_value(r) for r in rows]

    @staticmethod
    def effective_detail(db: Session, key: str, as_of: Optional[date] = None,
                         scope_value: Optional[str] = None) -> Optional[dict]:
        row = ConfigService._resolve_row(db, key, as_of, scope_value)
        return ConfigService._fmt_value(row) if row else None

    @staticmethod
    def validate_value(db: Session, key: str, value) -> None:
        """Validate a proposed value against its definition (type + rules).
        Raises ValueError with a message on failure."""
        d = db.query(ConfigDefinition).filter(
            ConfigDefinition.config_key == key).first()
        if d is None:
            raise ValueError(f"Unknown config key '{key}'")
        dt = d.data_type
        # type check
        try:
            if dt == "int":
                int(value)
            elif dt == "decimal":
                Decimal(str(value))
            elif dt == "bool":
                if not isinstance(value, bool) and str(value).lower() not in (
                        "true", "false", "0", "1", "yes", "no"):
                    raise ValueError()
            # string/json accept anything
        except (ValueError, InvalidOperation, TypeError):
            raise ValueError(f"Value '{value}' is not a valid {dt}")
        rules = json.loads(d.validation_json) if d.validation_json else None
        if not rules:
            return
        if dt in ("int", "decimal"):
            num = Decimal(str(value))
            if rules.get("min") is not None and num < Decimal(str(rules["min"])):
                raise ValueError(f"Value {value} below minimum {rules['min']}")
            if rules.get("max") is not None and num > Decimal(str(rules["max"])):
                raise ValueError(f"Value {value} above maximum {rules['max']}")
        if rules.get("enum") and value not in rules["enum"]:
            raise ValueError(f"Value {value} not in allowed set {rules['enum']}")
        if rules.get("regex") and dt == "string":
            import re
            if not re.match(rules["regex"], str(value)):
                raise ValueError(f"Value '{value}' does not match required pattern")

    @staticmethod
    def activate_due_scheduled(db: Session, as_of: Optional[date] = None,
                               user_id: int = None) -> int:
        """Flip any `scheduled` rows whose effective_from has arrived to active
        (superseding the prior open row). Returns the count activated. Intended
        to be invoked by an admin endpoint or cron — never auto-runs."""
        if as_of is None:
            as_of = date.today()
        due = db.query(ConfigValue).filter(
            ConfigValue.status == "scheduled",
            ConfigValue.effective_from <= as_of,
        ).all()
        for cv in due:
            ConfigService.activate(db, cv.id, user_id)
        return len(due)


def _ord(d: Optional[date]) -> int:
    """Sort helper: ordinal of a date (0 if None)."""
    return d.toordinal() if d else 0
