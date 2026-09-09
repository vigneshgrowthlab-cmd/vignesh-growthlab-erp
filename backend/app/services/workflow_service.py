"""
workflow_service.py - Configurable workflow status labels + transition policy
(Phase 5c; see docs/CONFIG_MIGRATION_PLAN.md).

ADVISORY by design: the Python status enums stay the structural source of truth.
`check_transition` logs a policy warning for a disallowed move but NEVER raises,
so existing flows are unaffected. Enforcement (raising) is a deliberate later
opt-in. When an entity has no transition rules, everything is permitted (so an
unseeded install logs nothing).
"""
from typing import List, Optional

from sqlalchemy.orm import Session

from app.models.models import WorkflowStatusMaster, WorkflowTransitionMaster
from app.services.audit import audit


class WorkflowService:

    # ── Status metadata (for UI) ─────────────────────────────────

    @staticmethod
    def get_statuses(db: Session, entity: str) -> List[dict]:
        rows = (
            db.query(WorkflowStatusMaster)
            .filter(WorkflowStatusMaster.entity == entity,
                    WorkflowStatusMaster.is_active == True)
            .order_by(WorkflowStatusMaster.sort_order.asc())
            .all()
        )
        return [{
            "status_code": r.status_code, "label": r.label, "color": r.color,
            "sort_order": r.sort_order, "is_terminal": r.is_terminal,
        } for r in rows]

    @staticmethod
    def get_transitions(db: Session, entity: str) -> List[dict]:
        rows = (
            db.query(WorkflowTransitionMaster)
            .filter(WorkflowTransitionMaster.entity == entity)
            .all()
        )
        return [{
            "from_status": r.from_status, "to_status": r.to_status,
            "required_role": r.required_role, "is_allowed": r.is_allowed,
        } for r in rows]

    # ── Transition policy (advisory) ─────────────────────────────

    @staticmethod
    def is_allowed(db: Session, entity: str, from_status: str, to_status: str) -> bool:
        """Permissive: if the entity has no transition rules at all, allow.
        Otherwise allow only an explicit is_allowed=True (from -> to) row."""
        rules = db.query(WorkflowTransitionMaster).filter(
            WorkflowTransitionMaster.entity == entity).all()
        if not rules:
            return True
        for r in rules:
            if r.from_status == from_status and r.to_status == to_status:
                return bool(r.is_allowed)
        return False

    @staticmethod
    def check_transition(db: Session, entity: str, from_status: str, to_status: str,
                         user_id: int = None) -> dict:
        """Advisory check. Logs a policy warning if the move isn't allowed but
        NEVER raises. Returns {'allowed': bool, 'advisory': True}."""
        allowed = WorkflowService.is_allowed(db, entity, from_status, to_status)
        if not allowed:
            try:
                audit(db, user_id, "policy", "workflow",
                      f"ADVISORY: disallowed transition {entity}: "
                      f"{from_status} -> {to_status}",
                      record_type="workflow_transition", record_id=None)
            except Exception:
                pass
        return {"allowed": allowed, "advisory": True}
