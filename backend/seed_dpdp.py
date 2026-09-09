"""
seed_dpdp.py - Phase 4b seed for DPDP tables. See docs/CONFIG_MIGRATION_PLAN.md.

  consent_purpose        <- a usable default catalogue of processing purposes
  data_retention_policy  <- example policies, seeded is_active=FALSE (INERT —
                            nothing is purged until an admin activates one)

No consent_record / erasure_request rows are seeded. Safe to re-run: a table is
seeded only if currently empty.

Run (backend venv active, DB migrated to head):
    python seed_dpdp.py
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.db.session import SessionLocal
from app.models.models import ConsentPurpose, DataRetentionPolicy

# purpose_key, name, requires_explicit, description
PURPOSES = [
    ("account_management", "Account & order management", False,
     "Maintain the customer/vendor account and fulfil orders."),
    ("transaction_processing", "Invoicing, payments & statutory filing", False,
     "Process invoices, payments, GST and income-tax filings (legal obligation)."),
    ("marketing_communications", "Marketing communications", True,
     "Send promotional offers and updates."),
    ("data_analytics", "Usage analytics", True,
     "Analyse usage to improve the service."),
]

# entity, retention_days, action, legal_basis
RETENTION = [
    ("activity_log", 365, "delete", "Operational audit; purge after 1 year."),
    ("login_history", 365, "delete", "Security audit; purge after 1 year."),
    ("active_session", 30, "delete", "Session hygiene; purge stale sessions after 30 days."),
]


def main():
    db = SessionLocal()
    try:
        if db.query(ConsentPurpose.id).first() is None:
            for key, name, req, desc in PURPOSES:
                db.add(ConsentPurpose(purpose_key=key, name=name,
                                      requires_explicit=req, description=desc,
                                      is_active=True))
            print(f"  OK  consent_purpose: {len(PURPOSES)} rows")
        else:
            print("  SKIP consent_purpose (not empty)")

        if db.query(DataRetentionPolicy.id).first() is None:
            for entity, days, action, basis in RETENTION:
                db.add(DataRetentionPolicy(entity=entity, retention_days=days,
                                           action=action, legal_basis=basis,
                                           is_active=False,  # INERT until activated
                                           notes="Phase 4b example policy (inactive)"))
            print(f"  OK  data_retention_policy: {len(RETENTION)} rows (INACTIVE)")
        else:
            print("  SKIP data_retention_policy (not empty)")

        db.commit()
        print("\nDone.\n")
    except Exception as e:
        db.rollback()
        print(f"\nERROR: {e}\n")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    print("\nSeeding DPDP tables (Phase 4b — consent purposes + INACTIVE retention policies)...\n")
    main()
