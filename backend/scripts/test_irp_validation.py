"""
Unit test for the IRP (e-invoice) pre-flight validation layer.

Tests the PURE validation logic in app/utils/irp_validation.py — no live
server, no DB, no Cleartax. Stubs fastapi + app.core.config so it runs with
a plain interpreter:

    cd backend
    python scripts/test_irp_validation.py

Exit code 0 only if every case behaves as expected. Complements the live-API
smoke test scripts/test_einvoice_module.py (which needs uvicorn + MariaDB).
"""
import importlib.util
import os
import sys
import types
from datetime import date
from decimal import Decimal

# ── Stub heavy deps so the module imports under a bare interpreter ────────
_fast = types.ModuleType("fastapi")


class HTTPException(Exception):
    def __init__(self, status_code=400, detail=""):
        self.status_code = status_code
        self.detail = detail
        super().__init__(detail)


_fast.HTTPException = HTTPException
sys.modules["fastapi"] = _fast

_app = types.ModuleType("app")
_core = types.ModuleType("app.core")
_cfg = types.ModuleType("app.core.config")


class _Settings:
    HSN_MIN_DIGITS = 6


_cfg.settings = _Settings()
sys.modules.setdefault("app", _app)
sys.modules.setdefault("app.core", _core)
sys.modules["app.core.config"] = _cfg

# ── Load the real module by path ─────────────────────────────────────────
_HERE = os.path.dirname(os.path.abspath(__file__))
_MODPATH = os.path.join(_HERE, "..", "app", "utils", "irp_validation.py")
_spec = importlib.util.spec_from_file_location("irp_validation", _MODPATH)
irp = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(irp)


# ── Tiny helpers ─────────────────────────────────────────────────────────
class Obj:
    def __init__(self, **kw):
        self.__dict__.update(kw)


SELLER_GSTIN = "29AAAAA0000A1Z5"
SELLER_STATE = 29

results = []


def check(name, fn, should_pass):
    """fn() runs the validator. should_pass=True means no exception expected."""
    try:
        fn()
        ok = should_pass
        detail = "" if ok else "validation PASSED but should have FAILED"
    except HTTPException as e:
        ok = not should_pass
        detail = "" if ok else f"unexpectedly FAILED: {e.detail[:160]}"
    tag = "[PASS]" if ok else "[FAIL]"
    print(f"{tag} {name}" + (f"  -- {detail}" if detail else ""))
    results.append((name, ok))


def base_invoice(**over):
    """A valid intra-state B2B invoice: 2 x 1000 + 18% GST = 1180."""
    item = Obj(hsn_code="85167200", quantity=Decimal("2"), gst_percent=Decimal("18"))
    inv = Obj(
        invoice_number="INV-001",
        invoice_date=date(2026, 1, 1),
        items=[item],
        taxable_amount=Decimal("1000"),
        total_cgst=Decimal("90"),
        total_sgst=Decimal("90"),
        total_igst=Decimal("0"),
        total_amount=Decimal("1180"),
    )
    for k, v in over.items():
        setattr(inv, k, v)
    return inv


def validate(inv, cust=None, bill=None, ship=None):
    if cust is None:
        cust = Obj(gstin=SELLER_GSTIN)
    if bill is None:
        bill = Obj(state_code=29)
    if ship is None:
        ship = Obj(state_code=29)
    irp.validate_einvoice(inv, cust, bill, ship, SELLER_GSTIN, SELLER_STATE)


def main():
    print("=== validate_einvoice: should PASS ===")
    check("valid intra-state B2B invoice",
          lambda: validate(base_invoice()), True)
    check("URP / unregistered buyer (GSTIN None)",
          lambda: validate(base_invoice(), cust=Obj(gstin=None)), True)
    check("round-off 0.40 within tolerance",
          lambda: validate(base_invoice(total_amount=Decimal("1180.40"))), True)

    def interstate():
        inv = base_invoice(total_cgst=Decimal("0"), total_sgst=Decimal("0"),
                           total_igst=Decimal("180"))
        validate(inv, cust=Obj(gstin="27AAAAA0000A1Z5"),
                 bill=Obj(state_code=27), ship=Obj(state_code=27))
    check("valid inter-state IGST invoice", interstate, True)

    check("6-digit HSN accepted",
          lambda: validate(base_invoice(
              items=[Obj(hsn_code="851672", quantity=Decimal("1"),
                         gst_percent=Decimal("18"))],
              taxable_amount=Decimal("1000"), total_cgst=Decimal("90"),
              total_sgst=Decimal("90"), total_igst=Decimal("0"),
              total_amount=Decimal("1180"))), True)

    print("\n=== validate_einvoice: should FAIL ===")

    def short_hsn():
        inv = base_invoice()
        inv.items[0].hsn_code = "8516"
        validate(inv)
    check("HSN below HSN_MIN_DIGITS (4 < 6)", short_hsn, False)

    def non_numeric_hsn():
        inv = base_invoice()
        inv.items[0].hsn_code = "85AB72"
        validate(inv)
    check("non-numeric HSN", non_numeric_hsn, False)

    def bad_rate():
        inv = base_invoice()
        inv.items[0].gst_percent = Decimal("15")
        validate(inv)
    check("GST rate not in IRP whitelist (15%)", bad_rate, False)

    def zero_qty():
        inv = base_invoice()
        inv.items[0].quantity = Decimal("0")
        validate(inv)
    check("zero quantity", zero_qty, False)

    check("buyer GSTIN state != billing state",
          lambda: validate(base_invoice(), cust=Obj(gstin="27AAAAA0000A1Z5")), False)
    check("malformed buyer GSTIN",
          lambda: validate(base_invoice(), cust=Obj(gstin="29ABC")), False)
    check("invalid seller GSTIN",
          lambda: irp.validate_einvoice(base_invoice(), Obj(gstin=SELLER_GSTIN),
                                        Obj(state_code=29), Obj(state_code=29),
                                        "BADGSTIN", 29), False)
    check("doc number starts with '0'",
          lambda: validate(base_invoice(invoice_number="0INV1")), False)
    check("doc number starts with '/'",
          lambda: validate(base_invoice(invoice_number="/INV1")), False)
    check("doc number over 16 chars",
          lambda: validate(base_invoice(invoice_number="INV-1234567890123456")), False)
    check("future-dated invoice",
          lambda: validate(base_invoice(invoice_date=date(2099, 1, 1))), False)
    check("place of supply unresolvable",
          lambda: validate(base_invoice(), ship=Obj(state_code=None),
                           bill=Obj(state_code=None)), False)
    check("totals do not reconcile (>Rs1)",
          lambda: validate(base_invoice(total_amount=Decimal("5000"))), False)
    check("empty item list",
          lambda: validate(base_invoice(items=[])), False)

    print("\n=== normalize_uqc ===")
    uqc_cases = [
        ("Nos", "NOS"), ("pieces", "PCS"), ("KG", "KGS"), ("litre", "LTR"),
        ("DOZEN", "DOZ"), ("box", "BOX"), ("", "NOS"), (None, "NOS"),
        ("totally-unknown-unit", "NOS"),
    ]
    for raw, expected in uqc_cases:
        got = irp.normalize_uqc(raw)
        ok = got == expected
        tag = "[PASS]" if ok else "[FAIL]"
        print(f"{tag} normalize_uqc({raw!r}) -> {got!r}" +
              ("" if ok else f"  -- expected {expected!r}"))
        results.append((f"uqc {raw!r}", ok))

    print("\n=== compute_round_off ===")
    ro_cases = [
        (Decimal("1180.00"), 0.0),
        (Decimal("1180.40"), 0.40),
        (Decimal("1179.60"), -0.40),
    ]
    for total, expected in ro_cases:
        got = irp.compute_round_off(base_invoice(total_amount=total))
        ok = abs(got - expected) < 0.001
        tag = "[PASS]" if ok else "[FAIL]"
        print(f"{tag} compute_round_off(total={total}) -> {got}" +
              ("" if ok else f"  -- expected {expected}"))
        results.append((f"roundoff {total}", ok))

    # Summary
    passed = sum(1 for _, ok in results if ok)
    failed = sum(1 for _, ok in results if not ok)
    print("\n" + "=" * 60)
    print(f"IRP validation tests: {passed} passed, {failed} failed")
    print("=" * 60)
    if failed:
        for name, ok in results:
            if not ok:
                print(f"  FAILED: {name}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
