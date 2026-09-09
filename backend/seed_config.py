"""
seed_config.py - Phase 0 baseline seed for the configuration-driven parameter
store (see docs/CONFIG_MIGRATION_PLAN.md).

Registers the catalog (config_definitions) and seeds one `active` value per key
from the CURRENT config.py constants, so the store starts as a faithful mirror
of today's behaviour. Safe to run multiple times:
  - definitions are upserted
  - a baseline value is inserted ONLY if the key has no value rows yet

Run (backend venv active, DB migrated to head):
    python seed_config.py
"""
import sys, os
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.db.session import SessionLocal
from app.core.config import settings
from app.models.models import ConfigValue
from app.services.config_service import ConfigService

# Baseline effective date = start of the current Indian FY mirror. Using a
# fixed early date means every historical document resolves to these values.
BASELINE_FROM = date(2025, 4, 1)

# (key, domain, data_type, unit, is_regulatory, value, description)
CATALOG = [
    # ── GST (regulatory) ──
    ("gst.eway_bill_threshold", "GST", "decimal", "INR", True,
     settings.EWAY_BILL_THRESHOLD,
     "E-Way Bill mandatory above this invoice value (inter-state movement)."),
    ("gst.gstr1_b2cl_threshold", "GST", "decimal", "INR", True,
     settings.GSTR1_B2CL_THRESHOLD,
     "Inter-state B2C invoice above this value is reported invoice-wise (B2CL Table 5)."),
    ("gst.hsn_min_digits", "GST", "int", "digits", True,
     settings.HSN_MIN_DIGITS,
     "Minimum HSN digits required on e-invoices (turnover-band dependent)."),
    ("gst.irn_cancel_window_hours", "GST", "int", "hours", True,
     24,
     "Hours after IRN generation within which an e-invoice may be cancelled (NIC rule)."),
    ("gst.eway_cancel_window_hours", "GST", "int", "hours", True,
     24,
     "Hours after e-way bill generation within which it may be cancelled (Rule 138(9))."),
    ("gst.eway_km_per_day", "GST", "int", "km", True,
     200,
     "E-Way Bill validity: distance (km, or part thereof) granting one day of validity (NIC rule)."),
    ("gst.gstr1_json_version", "GST", "string", None, True,
     "GST3.1.4",
     "Schema version string emitted in the GSTR-1 government JSON export."),

    # ── Income Tax / Company ──
    ("company.fy_start_month", "INCOME_TAX", "int", "month", True,
     settings.FINANCIAL_YEAR_START_MONTH,
     "Financial-year start month (India = April = 4)."),
    ("company.expense_approval_threshold", "COMPANY", "decimal", "INR", False,
     settings.EXPENSE_APPROVAL_THRESHOLD,
     "Expenses above this amount require approval before posting."),
    ("company.credit_days_default", "COMPANY", "int", "days", False,
     settings.CREDIT_DAYS_DEFAULT,
     "Default credit period when a customer/vendor has none set."),

    # ── RBI / banking ──
    ("rbi.bank_stock_margin", "RBI", "decimal", "percent", False,
     25,
     "Default margin % applied to stock+debtors to derive bank drawing power."),
    ("rbi.recon_amount_tolerance", "RBI", "decimal", "INR", False,
     1,
     "Max amount difference (₹) to auto-match a bank line to a book entry."),
    ("rbi.recon_date_window_days", "RBI", "int", "days", False,
     2,
     "Max date gap (days) to auto-match a bank line to a book entry."),
    ("company.pdc_alert_days", "COMPANY", "int", "days", False,
     7,
     "Look-ahead window (days) for post-dated cheque deposit alerts."),

    # ── Business strategy ──
    ("business.low_stock_default", "BUSINESS", "int", "units", False,
     settings.LOW_STOCK_THRESHOLD_DEFAULT,
     "Default low-stock alert threshold when a product has none set."),
    ("business.cost_alert_pct", "BUSINESS", "decimal", "percent", False,
     5,
     "Default cost-rise alert threshold (%) applied to new products."),
    ("business.min_margin_pct", "BUSINESS", "decimal", "percent", False,
     10,
     "Default minimum-margin threshold (%) for new products and low-margin alerts."),
    ("business.cost_avg_window_days", "BUSINESS", "int", "days", False,
     90,
     "Look-back window (days) for the average vendor-cost calculation."),

    # ── Governance ──
    ("governance.require_separate_checker", "COMPANY", "bool", None, False,
     False,
     "If true, a config change must be approved by a different user than the proposer (maker-checker)."),

    # ── DPDP / security ──
    ("dpdp.access_token_minutes", "DPDP", "int", "minutes", False,
     settings.ACCESS_TOKEN_EXPIRE_MINUTES,
     "JWT access-token validity."),
    ("dpdp.refresh_token_days", "DPDP", "int", "days", False,
     settings.REFRESH_TOKEN_EXPIRE_DAYS,
     "JWT refresh-token validity."),
    ("dpdp.max_login_attempts", "DPDP", "int", "count", False,
     settings.MAX_LOGIN_ATTEMPTS,
     "Failed login attempts before account lockout."),
    ("dpdp.lockout_minutes", "DPDP", "int", "minutes", False,
     settings.ACCOUNT_LOCKOUT_MINUTES,
     "Account lockout duration after max failed attempts."),
    ("dpdp.suspicious_window_hours", "DPDP", "int", "hours", False,
     24,
     "Look-back window (hours) for suspicious-activity detection."),
    ("dpdp.suspicious_failed_logins", "DPDP", "int", "count", False,
     3,
     "Failed logins within the window that flag a user as suspicious."),
    ("dpdp.suspicious_exports", "DPDP", "int", "count", False,
     5,
     "Bulk exports within the window that flag a user as suspicious."),
]


def main():
    db = SessionLocal()
    created, skipped = 0, 0
    try:
        for key, domain, dtype, unit, is_reg, value, desc in CATALOG:
            ConfigService.upsert_definition(
                db, config_key=key, domain=domain, data_type=dtype,
                unit=unit, description=desc, is_regulatory=is_reg,
            )
            has_value = (
                db.query(ConfigValue.id)
                .filter(ConfigValue.config_key == key)
                .first()
            )
            if has_value:
                skipped += 1
                print(f"  SKIP (exists): {key}")
                continue
            cv = ConfigService.propose(
                db, key=key, value=value, effective_from=BASELINE_FROM,
                status="draft", regulatory_reference="baseline",
                note="Phase 0 baseline mirror of config.py",
            )
            ConfigService.activate(db, cv.id)
            created += 1
            print(f"  OK  {key} = {value}")
        db.commit()
        print(f"\nDone. {created} baseline values created, {skipped} skipped.\n")
    except Exception as e:
        db.rollback()
        print(f"\nERROR: {e}\n")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    print("\nSeeding configuration-driven parameter store (Phase 0 baseline)...\n")
    main()
