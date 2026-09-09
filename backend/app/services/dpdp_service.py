"""
dpdp_service.py - DPDP Act capability: consent, data retention, right-to-erasure
(Phase 4b; see docs/CONFIG_MIGRATION_PLAN.md).

Safety model (important):
  - Retention purge is OPT-IN: only policies with is_active=True act, and
    enforce() never runs automatically (no startup hook, no scheduler here).
    preview() is always non-destructive.
  - Erasure ANONYMISES PII columns rather than hard-deleting rows, so
    statutorily-required financial/transaction records remain intact. It runs
    only on an explicit, admin-triggered process() call against a logged request.
"""
from datetime import datetime, date, timedelta
from typing import Optional, List

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.models import (
    ConsentPurpose, ConsentRecord, DataRetentionPolicy, ErasureRequest,
    ActivityLog, LoginHistory, ActiveSession, Customer, Vendor, User,
)
from app.services.audit import audit


# ── Consent ──────────────────────────────────────────────────────

class ConsentService:

    @staticmethod
    def list_purposes(db: Session) -> List[dict]:
        rows = db.query(ConsentPurpose).filter(ConsentPurpose.is_active == True).all()
        return [{
            "purpose_key": p.purpose_key, "name": p.name,
            "description": p.description, "requires_explicit": p.requires_explicit,
            "version": p.version,
        } for p in rows]

    @staticmethod
    def record(db: Session, principal_type: str, principal_id: int, purpose_key: str,
               granted: bool, source: str = None, notes: str = None,
               user_id: int = None) -> dict:
        purpose = db.query(ConsentPurpose).filter(
            ConsentPurpose.purpose_key == purpose_key).first()
        if not purpose:
            raise HTTPException(status_code=404, detail="Unknown consent purpose")
        now = datetime.utcnow()
        rec = ConsentRecord(
            principal_type=principal_type, principal_id=principal_id,
            purpose_key=purpose_key, purpose_version=purpose.version,
            status="granted" if granted else "withdrawn",
            granted_at=now if granted else None,
            withdrawn_at=None if granted else now,
            source=source, notes=notes, created_by=user_id,
        )
        db.add(rec)
        db.commit()
        db.refresh(rec)
        audit(db, user_id, "update", "dpdp",
              f"Consent {rec.status} for {principal_type}#{principal_id} / {purpose_key}",
              record_type="consent_record", record_id=rec.id)
        return {"id": rec.id, "status": rec.status, "purpose_key": purpose_key}

    @staticmethod
    def status(db: Session, principal_type: str, principal_id: int) -> List[dict]:
        """Latest consent state per purpose for a principal."""
        rows = (
            db.query(ConsentRecord)
            .filter(ConsentRecord.principal_type == principal_type,
                    ConsentRecord.principal_id == principal_id)
            .order_by(ConsentRecord.id.asc())
            .all()
        )
        latest = {}
        for r in rows:
            latest[r.purpose_key] = r
        return [{
            "purpose_key": k, "status": r.status,
            "granted_at": r.granted_at, "withdrawn_at": r.withdrawn_at,
            "source": r.source,
        } for k, r in latest.items()]

    @staticmethod
    def has_consent(db: Session, principal_type: str, principal_id: int,
                    purpose_key: str) -> bool:
        r = (
            db.query(ConsentRecord)
            .filter(ConsentRecord.principal_type == principal_type,
                    ConsentRecord.principal_id == principal_id,
                    ConsentRecord.purpose_key == purpose_key)
            .order_by(ConsentRecord.id.desc())
            .first()
        )
        return bool(r and r.status == "granted")


# ── Data retention ───────────────────────────────────────────────

class RetentionService:

    # entity -> ORM model (all use created_at as the age column)
    ENTITY_MODELS = {
        "activity_log": ActivityLog,
        "login_history": LoginHistory,
        "active_session": ActiveSession,
    }

    @staticmethod
    def list_policies(db: Session) -> List[dict]:
        rows = db.query(DataRetentionPolicy).all()
        return [{
            "id": p.id, "entity": p.entity, "retention_days": p.retention_days,
            "action": p.action, "legal_basis": p.legal_basis,
            "is_active": p.is_active, "notes": p.notes,
        } for p in rows]

    @staticmethod
    def _cutoff(retention_days: int) -> datetime:
        return datetime.utcnow() - timedelta(days=retention_days)

    @staticmethod
    def preview(db: Session) -> List[dict]:
        """Non-destructive: how many rows each ACTIVE policy would purge now."""
        out = []
        for p in db.query(DataRetentionPolicy).filter(
                DataRetentionPolicy.is_active == True).all():
            model = RetentionService.ENTITY_MODELS.get(p.entity)
            if not model:
                out.append({"entity": p.entity, "error": "unknown entity", "count": 0})
                continue
            cutoff = RetentionService._cutoff(p.retention_days)
            cnt = db.query(model).filter(model.created_at < cutoff).count()
            out.append({"entity": p.entity, "retention_days": p.retention_days,
                        "action": p.action, "would_purge": cnt, "cutoff": cutoff})
        return out

    @staticmethod
    def enforce(db: Session, dry_run: bool = True, user_id: int = None) -> List[dict]:
        """Apply ACTIVE retention policies. dry_run=True only reports counts.
        Never called automatically — admin/cron must invoke it explicitly."""
        results = []
        for p in db.query(DataRetentionPolicy).filter(
                DataRetentionPolicy.is_active == True).all():
            model = RetentionService.ENTITY_MODELS.get(p.entity)
            if not model:
                results.append({"entity": p.entity, "error": "unknown entity"})
                continue
            cutoff = RetentionService._cutoff(p.retention_days)
            q = db.query(model).filter(model.created_at < cutoff)
            cnt = q.count()
            if not dry_run and cnt and p.action == "delete":
                q.delete(synchronize_session=False)
                db.commit()
                audit(db, user_id, "delete", "dpdp",
                      f"Retention purge: {cnt} {p.entity} rows older than "
                      f"{p.retention_days}d", record_type="data_retention_policy",
                      record_id=p.id)
            results.append({"entity": p.entity, "purged" if not dry_run else "would_purge": cnt})
        return results


# ── Right to erasure ─────────────────────────────────────────────

class ErasureService:

    _SUBJECTS = {"customer": Customer, "vendor": Vendor, "user": User}

    @staticmethod
    def _label(db: Session, subject_type: str, subject_id: int) -> Optional[str]:
        model = ErasureService._SUBJECTS.get(subject_type)
        if not model:
            return None
        obj = db.query(model).filter(model.id == subject_id).first()
        if not obj:
            return None
        return getattr(obj, "trade_name", None) or getattr(obj, "full_name", None) or str(subject_id)

    @staticmethod
    def request(db: Session, subject_type: str, subject_id: int,
                reason: str = None, user_id: int = None) -> dict:
        if subject_type not in ErasureService._SUBJECTS:
            raise HTTPException(status_code=400, detail="Invalid subject_type")
        req = ErasureRequest(
            subject_type=subject_type, subject_id=subject_id,
            subject_label=ErasureService._label(db, subject_type, subject_id),
            status="pending", reason=reason, requested_by=user_id,
        )
        db.add(req)
        db.commit()
        db.refresh(req)
        audit(db, user_id, "create", "dpdp",
              f"Erasure requested for {subject_type}#{subject_id}",
              record_type="erasure_request", record_id=req.id)
        return ErasureService._fmt(req)

    @staticmethod
    def list(db: Session, status: Optional[str] = None) -> List[dict]:
        q = db.query(ErasureRequest)
        if status:
            q = q.filter(ErasureRequest.status == status)
        return [ErasureService._fmt(r) for r in q.order_by(ErasureRequest.requested_at.desc()).all()]

    @staticmethod
    def process(db: Session, request_id: int, user_id: int = None) -> dict:
        """Anonymise the subject's PII (contact fields), keeping the row and its
        financial linkage intact (required for statutory record retention)."""
        req = db.query(ErasureRequest).filter(ErasureRequest.id == request_id).first()
        if not req:
            raise HTTPException(status_code=404, detail="Erasure request not found")
        if req.status == "completed":
            raise HTTPException(status_code=400, detail="Already processed")
        model = ErasureService._SUBJECTS.get(req.subject_type)
        obj = db.query(model).filter(model.id == req.subject_id).first() if model else None
        if not obj:
            req.status = "rejected"
            req.result_note = "Subject not found"
            req.processed_by = user_id
            req.processed_at = datetime.utcnow()
            db.commit()
            return ErasureService._fmt(req)

        tag = f"[ERASED #{req.subject_id}]"
        for field in ("email", "phone", "contact_person"):
            if hasattr(obj, field):
                setattr(obj, field, None)
        if hasattr(obj, "trade_name"):
            obj.trade_name = tag
        if hasattr(obj, "full_name"):
            obj.full_name = tag
        req.status = "completed"
        req.processed_by = user_id
        req.processed_at = datetime.utcnow()
        req.result_note = "PII anonymised; financial records retained"
        db.commit()
        audit(db, user_id, "update", "dpdp",
              f"Erasure processed (anonymised) for {req.subject_type}#{req.subject_id}",
              record_type="erasure_request", record_id=req.id)
        return ErasureService._fmt(req)

    @staticmethod
    def _fmt(r: ErasureRequest) -> dict:
        return {
            "id": r.id, "subject_type": r.subject_type, "subject_id": r.subject_id,
            "subject_label": r.subject_label, "status": r.status, "reason": r.reason,
            "requested_by": r.requested_by, "requested_at": r.requested_at,
            "processed_by": r.processed_by, "processed_at": r.processed_at,
            "result_note": r.result_note,
        }
