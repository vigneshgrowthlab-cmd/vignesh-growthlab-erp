"""
gst_master_service.py - Effective-dated resolvers for the GST structured
masters (Phase 1b; see docs/CONFIG_MIGRATION_PLAN.md).

Mirrors ConfigService semantics: a row resolves for an `as_of` date when it is
within its [effective_from, effective_to] window and its status is one that was
genuinely in force ({active, superseded, expired}). Callers pass the
transaction's own date so historical documents validate against the rules that
applied when they were issued.

Every resolver returns plain Python data; when a master is empty the caller
falls back to the in-code constants in app/utils/irp_validation.py (so an
unseeded install behaves exactly as before).
"""
from datetime import date, datetime
from typing import Optional

from sqlalchemy.orm import Session

from app.models.models import GstRateMaster, StateMaster, UqcMaster
from app.services.config_service import _RESOLVABLE_STATUSES


def _as_of(d: Optional[date]) -> date:
    if d is None:
        return date.today()
    if isinstance(d, datetime):
        return d.date()
    return d


class GstMasterService:

    # ── GST rates ────────────────────────────────────────────────

    @staticmethod
    def _live_rate_rows(db: Session, as_of: Optional[date]):
        a = _as_of(as_of)
        return (
            db.query(GstRateMaster)
            .filter(
                GstRateMaster.status.in_(_RESOLVABLE_STATUSES),
                GstRateMaster.effective_from <= a,
                (GstRateMaster.effective_to.is_(None)) | (GstRateMaster.effective_to >= a),
            )
            .order_by(GstRateMaster.effective_from.asc(), GstRateMaster.rate.asc())
            .all()
        )

    @staticmethod
    def valid_gst_rates(db: Session, as_of: Optional[date] = None) -> set:
        """All IRP-valid GST rates as floats (empty set if master unseeded)."""
        return {float(r.rate) for r in GstMasterService._live_rate_rows(db, as_of)}

    @staticmethod
    def selectable_gst_rates(db: Session, as_of: Optional[date] = None) -> list:
        """Picker list: [{"rate": int|float, "label": str}], dedup by rate."""
        out, seen = [], set()
        for r in GstMasterService._live_rate_rows(db, as_of):
            if not r.is_selectable:
                continue
            rv = float(r.rate)
            rv = int(rv) if rv == int(rv) else rv
            if rv in seen:
                continue
            seen.add(rv)
            out.append({"id": r.id, "rate": rv, "label": r.label or f"{rv}%"})
        return out

    # ── States ───────────────────────────────────────────────────

    @staticmethod
    def _live_state_rows(db: Session, as_of: Optional[date]):
        a = _as_of(as_of)
        return (
            db.query(StateMaster)
            .filter(
                StateMaster.status.in_(_RESOLVABLE_STATUSES),
                StateMaster.effective_from <= a,
                (StateMaster.effective_to.is_(None)) | (StateMaster.effective_to >= a),
            )
            .order_by(StateMaster.effective_from.asc(), StateMaster.state_code.asc())
            .all()
        )

    @staticmethod
    def valid_state_codes(db: Session, as_of: Optional[date] = None) -> set:
        """All valid GST state codes as ints (empty set if master unseeded)."""
        return {int(s.state_code) for s in GstMasterService._live_state_rows(db, as_of)}

    @staticmethod
    def states(db: Session, as_of: Optional[date] = None) -> list:
        """Picker list: [{"code": int, "name": str}], dedup by code."""
        out, seen = [], set()
        for s in GstMasterService._live_state_rows(db, as_of):
            if not s.is_selectable or int(s.state_code) in seen:
                continue
            seen.add(int(s.state_code))
            out.append({"code": int(s.state_code), "name": s.name})
        return out

    # ── UQC ──────────────────────────────────────────────────────

    @staticmethod
    def uqc_map(db: Session, as_of: Optional[date] = None) -> dict:
        """{normalized_unit_text: uqc_code} (empty dict if master unseeded).
        Later effective_from wins on duplicate keys."""
        a = _as_of(as_of)
        rows = (
            db.query(UqcMaster)
            .filter(
                UqcMaster.status.in_(_RESOLVABLE_STATUSES),
                UqcMaster.effective_from <= a,
                (UqcMaster.effective_to.is_(None)) | (UqcMaster.effective_to >= a),
            )
            .order_by(UqcMaster.effective_from.asc())
            .all()
        )
        return {r.unit_text: r.uqc_code for r in rows}
