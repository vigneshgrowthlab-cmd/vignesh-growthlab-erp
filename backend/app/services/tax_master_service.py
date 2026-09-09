"""
tax_master_service.py - Effective-dated resolvers for the income-tax /
accounting masters (Phase 2; see docs/CONFIG_MIGRATION_PLAN.md).

Same temporal semantics as ConfigService/GstMasterService: a row resolves for
an `as_of` date when it is within its [effective_from, effective_to] window and
its status is one that was genuinely in force. Callers pass the transaction's
own date and fall back to the in-code constants when a master is empty.
"""
from datetime import date, datetime
from typing import Optional

from sqlalchemy.orm import Session

from app.models.models import TdsSectionMaster, AgingBucketMaster
from app.services.config_service import _RESOLVABLE_STATUSES


def _as_of(d: Optional[date]) -> date:
    if d is None:
        return date.today()
    if isinstance(d, datetime):
        return d.date()
    return d


class TaxMasterService:

    # ── TDS sections ─────────────────────────────────────────────

    @staticmethod
    def _live_tds_rows(db: Session, as_of: Optional[date]):
        a = _as_of(as_of)
        return (
            db.query(TdsSectionMaster)
            .filter(
                TdsSectionMaster.status.in_(_RESOLVABLE_STATUSES),
                TdsSectionMaster.effective_from <= a,
                (TdsSectionMaster.effective_to.is_(None)) | (TdsSectionMaster.effective_to >= a),
            )
            .order_by(TdsSectionMaster.effective_from.asc())
            .all()
        )

    @staticmethod
    def tds_section(db: Session, code: str, as_of: Optional[date] = None) -> Optional[dict]:
        """Return the effective row for a TDS section code, or None."""
        latest = None
        for r in TaxMasterService._live_tds_rows(db, as_of):
            if r.section_code == code:
                latest = r  # rows are asc by effective_from; last match wins
        if latest is None:
            return None
        return {
            "section_code": latest.section_code,
            "description": latest.description,
            "rate": float(latest.rate),
            "threshold_single": float(latest.threshold_single) if latest.threshold_single is not None else None,
            "threshold_annual": float(latest.threshold_annual) if latest.threshold_annual is not None else None,
            "deductee_type": latest.deductee_type,
        }

    @staticmethod
    def tds_sections(db: Session, as_of: Optional[date] = None) -> list:
        """List of effective TDS sections (dedup by code, latest wins)."""
        by_code = {}
        for r in TaxMasterService._live_tds_rows(db, as_of):
            by_code[r.section_code] = r
        out = []
        for code in sorted(by_code):
            r = by_code[code]
            out.append({
                "id": r.id,
                "section_code": r.section_code,
                "description": r.description,
                "rate": float(r.rate),
                "threshold_single": float(r.threshold_single) if r.threshold_single is not None else None,
                "threshold_annual": float(r.threshold_annual) if r.threshold_annual is not None else None,
                "deductee_type": r.deductee_type,
            })
        return out

    # ── Ageing buckets ───────────────────────────────────────────

    @staticmethod
    def aging_buckets(db: Session, as_of: Optional[date] = None) -> list:
        """Ordered ageing buckets [{seq,label,from_days,to_days,weight}] for the
        date, or [] when the master is empty (caller falls back to 30/60/90)."""
        a = _as_of(as_of)
        rows = (
            db.query(AgingBucketMaster)
            .filter(
                AgingBucketMaster.status.in_(_RESOLVABLE_STATUSES),
                AgingBucketMaster.effective_from <= a,
                (AgingBucketMaster.effective_to.is_(None)) | (AgingBucketMaster.effective_to >= a),
            )
            .order_by(AgingBucketMaster.seq.asc(), AgingBucketMaster.effective_from.desc())
            .all()
        )
        seen, out = set(), []
        for r in rows:
            if r.seq in seen:
                continue
            seen.add(r.seq)
            out.append({
                "seq": r.seq, "label": r.label,
                "from_days": r.from_days, "to_days": r.to_days,
                "weight": float(r.weight),
            })
        return out
