"""
seed_workflow.py - Phase 5c seed for the workflow advisory layer.
See docs/CONFIG_MIGRATION_PLAN.md.

Seeds display metadata (labels/colours/order) for each entity's statuses and the
allowed transitions between them. Used in ADVISORY mode (transitions are logged,
never blocked). Safe to re-run: only seeds rows that don't already exist.

Run (backend venv active, DB migrated to head):
    python seed_workflow.py
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.db.session import SessionLocal
from app.models.models import WorkflowStatusMaster, WorkflowTransitionMaster

A, G, R, B, Y = "gray", "green", "red", "blue", "amber"

# entity, status_code, label, color, sort, is_terminal
STATUSES = [
    ("einvoice", "pending", "Pending", Y, 0, False),
    ("einvoice", "generated", "Generated", G, 1, False),
    ("einvoice", "cancelled", "Cancelled", R, 2, True),
    ("einvoice", "failed", "Failed", R, 3, False),
    ("eway", "pending", "Pending", Y, 0, False),
    ("eway", "generated", "Generated", G, 1, False),
    ("eway", "cancelled", "Cancelled", R, 2, True),
    ("eway", "failed", "Failed", R, 3, False),
    ("cheque", "received", "Received", Y, 0, False),
    ("cheque", "deposited", "Deposited", B, 1, False),
    ("cheque", "cleared", "Cleared", G, 2, True),
    ("cheque", "bounced", "Bounced", R, 3, True),
    ("cheque", "pdc_pending", "PDC Pending", A, 4, False),
    ("expense", "pending_approval", "Pending Approval", Y, 0, False),
    ("expense", "approved", "Approved", G, 1, True),
    ("expense", "rejected", "Rejected", R, 2, True),
    ("cash_closing", "draft", "Draft", A, 0, False),
    ("cash_closing", "approved", "Approved", G, 1, True),
    ("stock_writeoff", "pending", "Pending", Y, 0, False),
    ("stock_writeoff", "approved", "Approved", G, 1, True),
    ("stock_writeoff", "rejected", "Rejected", R, 2, True),
    ("stock_transfer", "pending", "Pending", Y, 0, False),
    ("stock_transfer", "completed", "Completed", G, 1, True),
    ("delivery_challan", "pending", "Pending", Y, 0, False),
    ("delivery_challan", "delivered", "Delivered", G, 1, True),
    ("delivery_challan", "rejected", "Rejected", R, 2, False),
    ("delivery_challan", "cancelled", "Cancelled", R, 3, True),
    ("quotation", "pending", "Pending", Y, 0, False),
    ("quotation", "invoiced", "Invoiced", G, 1, True),
    ("bank_reconciliation", "draft", "Draft", A, 0, False),
    ("bank_reconciliation", "finalized", "Finalized", G, 1, True),
]

# entity, from_status, to_status
TRANSITIONS = [
    ("einvoice", "pending", "generated"), ("einvoice", "pending", "failed"),
    ("einvoice", "generated", "cancelled"),
    ("eway", "pending", "generated"), ("eway", "pending", "failed"),
    ("eway", "generated", "cancelled"),
    ("cheque", "received", "deposited"), ("cheque", "received", "bounced"),
    ("cheque", "deposited", "cleared"), ("cheque", "deposited", "bounced"),
    ("cheque", "pdc_pending", "deposited"),
    ("expense", "pending_approval", "approved"), ("expense", "pending_approval", "rejected"),
    ("cash_closing", "draft", "approved"),
    ("stock_writeoff", "pending", "approved"), ("stock_writeoff", "pending", "rejected"),
    ("stock_transfer", "pending", "completed"),
    ("delivery_challan", "pending", "delivered"), ("delivery_challan", "pending", "rejected"),
    ("delivery_challan", "pending", "cancelled"),
    ("quotation", "pending", "invoiced"),
    ("bank_reconciliation", "draft", "finalized"),
]


def main():
    db = SessionLocal()
    try:
        existing_s = {(r.entity, r.status_code)
                      for r in db.query(WorkflowStatusMaster.entity, WorkflowStatusMaster.status_code).all()}
        ns = 0
        for entity, code, label, color, order, terminal in STATUSES:
            if (entity, code) in existing_s:
                continue
            db.add(WorkflowStatusMaster(entity=entity, status_code=code, label=label,
                                        color=color, sort_order=order, is_terminal=terminal))
            ns += 1
        print(f"  OK  workflow_status_master: {ns} rows added")

        existing_t = {(r.entity, r.from_status, r.to_status)
                      for r in db.query(WorkflowTransitionMaster.entity,
                                        WorkflowTransitionMaster.from_status,
                                        WorkflowTransitionMaster.to_status).all()}
        nt = 0
        for entity, frm, to in TRANSITIONS:
            if (entity, frm, to) in existing_t:
                continue
            db.add(WorkflowTransitionMaster(entity=entity, from_status=frm,
                                            to_status=to, is_allowed=True))
            nt += 1
        print(f"  OK  workflow_transition_master: {nt} rows added")
        db.commit()
        print("\nDone.\n")
    except Exception as e:
        db.rollback()
        print(f"\nERROR: {e}\n")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    print("\nSeeding workflow status/transition masters (Phase 5c)...\n")
    main()
