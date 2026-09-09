"""
seed_gst_masters.py - Phase 1b seed for the GST structured masters
(gst_rate_master, state_master, uqc_master). See docs/CONFIG_MIGRATION_PLAN.md.

Seeds each master to mirror the CURRENT in-code literals exactly, so resolution
is behaviour-neutral:
  - gst_rate_master  <- irp_validation.VALID_GST_RATES (5 selectable display
                        slabs keep their labels; the 7 intermediate rates are
                        valid-but-not-selectable)
  - state_master     <- irp_validation.VALID_STATE_CODES (the 37 named states
                        from the /states endpoint are selectable; 25/96/97/99
                        are valid POS codes but not shown in pickers)
  - uqc_master       <- irp_validation.UQC_MAP

Safe to re-run: a master is seeded only if its table is currently empty.

Run (backend venv active, DB migrated to head):
    python seed_gst_masters.py
"""
import sys, os
from datetime import date
from decimal import Decimal

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.db.session import SessionLocal
from app.models.models import GstRateMaster, StateMaster, UqcMaster
from app.utils.irp_validation import VALID_GST_RATES, VALID_STATE_CODES, UQC_MAP

BASELINE_FROM = date(2025, 4, 1)

# Display labels for the selectable slabs (mirror the /gst-rates endpoint).
RATE_LABELS = {
    0:  "0% — Exempt / Zero-rated",
    5:  "5% — Essential goods",
    12: "12% — Standard goods",
    18: "18% — Standard services",
    28: "28% — Luxury / demerit goods",
}

# code -> (name, is_selectable). Names mirror the /states endpoint; 25/96/97/99
# are valid POS codes (in VALID_STATE_CODES) but not shown in dropdowns.
STATE_INFO = {
    1: ("Jammu & Kashmir", True), 2: ("Himachal Pradesh", True), 3: ("Punjab", True),
    4: ("Chandigarh", True), 5: ("Uttarakhand", True), 6: ("Haryana", True),
    7: ("Delhi", True), 8: ("Rajasthan", True), 9: ("Uttar Pradesh", True),
    10: ("Bihar", True), 11: ("Sikkim", True), 12: ("Arunachal Pradesh", True),
    13: ("Nagaland", True), 14: ("Manipur", True), 15: ("Mizoram", True),
    16: ("Tripura", True), 17: ("Meghalaya", True), 18: ("Assam", True),
    19: ("West Bengal", True), 20: ("Jharkhand", True), 21: ("Odisha", True),
    22: ("Chhattisgarh", True), 23: ("Madhya Pradesh", True), 24: ("Gujarat", True),
    25: ("Daman & Diu (old)", False),
    26: ("Dadra and Nagar Haveli and Daman and Diu", True), 27: ("Maharashtra", True),
    28: ("Andhra Pradesh (New)", True), 29: ("Karnataka", True), 30: ("Goa", True),
    31: ("Lakshadweep", True), 32: ("Kerala", True), 33: ("Tamil Nadu", True),
    34: ("Puducherry", True), 35: ("Andaman & Nicobar Islands", True),
    36: ("Telangana", True), 37: ("Andhra Pradesh (Residual)", True), 38: ("Ladakh", True),
    96: ("Other Country", False), 97: ("Other Territory", False), 99: ("Unspecified", False),
}


def main():
    db = SessionLocal()
    try:
        n_rates = n_states = n_uqc = 0

        if db.query(GstRateMaster.id).first() is None:
            for r in sorted(VALID_GST_RATES):
                rv = int(r) if float(r) == int(r) else r
                db.add(GstRateMaster(
                    rate=Decimal(str(r)),
                    label=RATE_LABELS.get(rv, f"{rv}%"),
                    is_selectable=rv in RATE_LABELS,
                    effective_from=BASELINE_FROM,
                    regulatory_reference="baseline",
                    note="Phase 1b baseline mirror of VALID_GST_RATES",
                ))
                n_rates += 1
            print(f"  OK  gst_rate_master: {n_rates} rows")
        else:
            print("  SKIP gst_rate_master (not empty)")

        if db.query(StateMaster.id).first() is None:
            for code in sorted(VALID_STATE_CODES):
                name, selectable = STATE_INFO.get(code, (f"State {code}", False))
                db.add(StateMaster(
                    state_code=code, name=name, is_selectable=selectable,
                    effective_from=BASELINE_FROM, regulatory_reference="baseline",
                    note="Phase 1b baseline mirror of VALID_STATE_CODES",
                ))
                n_states += 1
            print(f"  OK  state_master: {n_states} rows")
        else:
            print("  SKIP state_master (not empty)")

        if db.query(UqcMaster.id).first() is None:
            for unit_text, uqc_code in sorted(UQC_MAP.items()):
                db.add(UqcMaster(
                    unit_text=unit_text, uqc_code=uqc_code,
                    effective_from=BASELINE_FROM, regulatory_reference="baseline",
                    note="Phase 1b baseline mirror of UQC_MAP",
                ))
                n_uqc += 1
            print(f"  OK  uqc_master: {n_uqc} rows")
        else:
            print("  SKIP uqc_master (not empty)")

        db.commit()
        print("\nDone.\n")
    except Exception as e:
        db.rollback()
        print(f"\nERROR: {e}\n")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    print("\nSeeding GST structured masters (Phase 1b baseline)...\n")
    main()
