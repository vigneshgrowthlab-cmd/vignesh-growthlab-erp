"""
seed_incometax_masters.py - Phase 2 seed for the income-tax / accounting
masters. See docs/CONFIG_MIGRATION_PLAN.md.

  chart_of_account_map  <- helpers._ACCOUNT_TYPE_MAP (exact mirror, so
                           get_or_create_account resolves identically)
  aging_bucket_master   <- the current 30/60/90 buckets + 1/2/3/5 weights
  tds_section_master    <- common Indian TDS sections (reference rates/
                           thresholds; freely editable per Income-Tax changes)

Safe to re-run: a master is seeded only if its table is currently empty.

Run (backend venv active, DB migrated to head):
    python seed_incometax_masters.py
"""
import sys, os
from datetime import date
from decimal import Decimal

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.db.session import SessionLocal
from app.models.models import TdsSectionMaster, AgingBucketMaster, ChartOfAccountMap
from app.utils.helpers import _ACCOUNT_TYPE_MAP

BASELINE_FROM = date(2025, 4, 1)

# code, description, rate, threshold_single, threshold_annual
TDS_SECTIONS = [
    ("194C",    "Payment to contractors (individual/HUF)", "1.00", "30000", "100000"),
    ("194J",    "Professional / technical fees",           "10.00", "30000", None),
    ("194H",    "Commission or brokerage",                 "5.00", "15000", None),
    ("194I(a)", "Rent of plant & machinery",               "2.00", None, "240000"),
    ("194I(b)", "Rent of land / building",                 "10.00", None, "240000"),
    ("194A",    "Interest other than on securities",       "10.00", None, "40000"),
    ("194D",    "Insurance commission",                    "5.00", None, "15000"),
    ("194Q",    "Purchase of goods",                       "0.10", None, "5000000"),
    ("194O",    "E-commerce operator",                     "1.00", None, "500000"),
]

# seq, label, from_days, to_days, weight (mirrors current hardcoded buckets)
AGING_BUCKETS = [
    (1, "0-30",  0,  30,  "1"),
    (2, "31-60", 31, 60,  "2"),
    (3, "61-90", 61, 90,  "3"),
    (4, "90+",   91, None, "5"),
]


def main():
    db = SessionLocal()
    try:
        if db.query(ChartOfAccountMap.id).first() is None:
            n = 0
            for code, (atype, name) in _ACCOUNT_TYPE_MAP.items():
                db.add(ChartOfAccountMap(
                    code=code, account_type=atype, default_name=name,
                    effective_from=BASELINE_FROM, regulatory_reference="baseline",
                    note="Phase 2 baseline mirror of _ACCOUNT_TYPE_MAP",
                ))
                n += 1
            print(f"  OK  chart_of_account_map: {n} rows")
        else:
            print("  SKIP chart_of_account_map (not empty)")

        if db.query(AgingBucketMaster.id).first() is None:
            for seq, label, fd, td, w in AGING_BUCKETS:
                db.add(AgingBucketMaster(
                    seq=seq, label=label, from_days=fd, to_days=td,
                    weight=Decimal(w), effective_from=BASELINE_FROM,
                    regulatory_reference="baseline",
                    note="Phase 2 baseline mirror of hardcoded ageing buckets",
                ))
            print(f"  OK  aging_bucket_master: {len(AGING_BUCKETS)} rows")
        else:
            print("  SKIP aging_bucket_master (not empty)")

        if db.query(TdsSectionMaster.id).first() is None:
            for code, desc, rate, ts, ta in TDS_SECTIONS:
                db.add(TdsSectionMaster(
                    section_code=code, description=desc, rate=Decimal(rate),
                    threshold_single=Decimal(ts) if ts else None,
                    threshold_annual=Decimal(ta) if ta else None,
                    effective_from=BASELINE_FROM, regulatory_reference="baseline",
                    note="Phase 2 baseline TDS sections (editable per IT changes)",
                ))
            print(f"  OK  tds_section_master: {len(TDS_SECTIONS)} rows")
        else:
            print("  SKIP tds_section_master (not empty)")

        db.commit()
        print("\nDone.\n")
    except Exception as e:
        db.rollback()
        print(f"\nERROR: {e}\n")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    print("\nSeeding income-tax / accounting masters (Phase 2 baseline)...\n")
    main()
